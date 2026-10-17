# SPDX-License-Identifier: Apache-2.0
"""Read-only symbol metadata and role-aware object address checks.

Offsets are relative to the first typed symbol in a path, never PLC addresses.
Missing layout information stays unknown. Raw XML is retained without rewriting.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import xml.etree.ElementTree as ET

from .errors import AgentError


SYMBOL_NAMESPACE = "http://www.3s-software.com/schemas/Symbolconfiguration.xsd"
_NAME = r"[A-Za-z_][A-Za-z_0-9]*"
_PART = re.compile(rf"({_NAME})((?:\[-?\d+(?:,-?\d+)*\])*)\Z")
_ADDRESS = re.compile(rf"DIA_TAG@\{{({_NAME})\}}(\d+)\.(.+)\Z")
_RIGHTS = {"Read": frozenset({"read"}), "Write": frozenset({"write"}),
           "ReadWrite": frozenset({"read", "write"})}
_NUMERIC = frozenset({"SINT", "USINT", "BYTE", "INT", "UINT", "WORD", "DINT",
                      "UDINT", "DWORD", "LINT", "ULINT", "LWORD", "REAL", "LREAL"})


def _fail(code: str, message: str, **details):
    raise AgentError(code, message, **details)


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _integer(value: str | None, label: str, *, signed: bool = False) -> int:
    if value is None or not re.fullmatch(r"-?\d+" if signed else r"\d+", value):
        _fail("SYMBOL_INTEGER", "Invalid symbol metadata integer", field=label)
    if len(value.lstrip("-")) > 20:
        _fail("SYMBOL_LIMIT", "Symbol metadata integer exceeds the bounded profile", field=label)
    return int(value)


def _children(node: ET.Element, kind: str) -> list[ET.Element]:
    return [child for child in node if _tag(child) == kind]


def _unique(nodes: list[ET.Element], attribute: str) -> dict[str, ET.Element]:
    result = {}
    for node in nodes:
        name = node.get(attribute)
        if not name or not re.fullmatch(_NAME, name):
            _fail("SYMBOL_NAME", "Unsupported or absent symbol name", attribute=attribute)
        if name in result:
            _fail("SYMBOL_DUPLICATE", "Duplicate symbol identity", name=name)
        result[name] = node
    return result


def _parts(path: str) -> list[tuple[str, list[int]]]:
    if not isinstance(path, str) or not path or len(path) > 4096:
        _fail("SYMBOL_PATH", "Invalid or oversized symbol path")
    parts = []
    for component in path.split("."):
        match = _PART.fullmatch(component)
        if not match:
            _fail("SYMBOL_PATH", "Unsupported symbol path grammar", component=component)
        indexes = [int(value) for group in re.findall(r"\[([^]]+)\]", match[2])
                   for value in group.split(",")]
        parts.append((match[1], indexes))
    if len(parts) > 128:
        _fail("SYMBOL_LIMIT", "Symbol path depth exceeds the bounded resolver")
    return parts


@dataclass
class SymbolCatalog:
    raw: bytes
    sha256: str
    root_name: str
    _root: ET.Element
    _types: dict[str, ET.Element]

    def resolve(self, symbolpath: str) -> dict:
        """Resolve optional-root-qualified names without changing their storage type."""
        parts = _parts(symbolpath)
        if parts[0][0] == self.root_name:
            if parts[0][1]:
                _fail("SYMBOL_PATH", "The application root cannot be indexed")
            parts = parts[1:]
        if not parts:
            _fail("SYMBOL_PATH", "A typed symbol is required below the application root")
        rights = frozenset({"read", "write"})
        rights_seen = False

        def apply_access(node):
            nonlocal rights, rights_seen
            access = node.get("access")
            if access is not None:
                rights &= _RIGHTS[access]
                rights_seen = True

        apply_access(self._root)
        scope = _unique(_children(self._root, "Node"), "name")
        typ = None
        offset = None
        offset_base = None
        dimensions = []
        canonical = [self.root_name]
        direct_address = None
        for step, (name, indexes) in enumerate(parts):
            if name not in scope:
                _fail("SYMBOL_MISSING", "Symbol path does not resolve uniquely", component=name)
            node = scope[name]
            apply_access(node)
            canonical.append(name + ("[" + ",".join(map(str, indexes)) + "]" if indexes else ""))
            if node.get("directaddress") is not None:
                direct_address = node.get("directaddress")
            type_name = node.get("type")
            if type_name is None:
                if indexes:
                    _fail("SYMBOL_NOT_ARRAY", "A grouping node cannot be indexed", component=name)
                scope = _unique(_children(node, "Node"), "name")
                typ = None
                if not scope:
                    _fail("SYMBOL_TYPE", "Untyped leaf in symbol tree", component=name)
                continue
            typ = self._types[type_name]
            if offset_base is None:
                offset_base = ".".join(canonical[:-1] + [name])
                offset = 0
            elif node.get("byteoffset") is not None and offset is not None:
                offset += _integer(node.get("byteoffset"), "byteoffset")
            else:
                # An omitted member offset is not a packed-layout invitation.
                offset = None
            remaining = list(indexes)
            while _tag(typ) == "TypeArray":
                bounds = _children(typ, "ArrayDim")
                selected = None
                if remaining:
                    if len(remaining) < len(bounds):
                        _fail("SYMBOL_ARRAY_RANK", "Incomplete array index tuple")
                    selected, remaining = remaining[:len(bounds)], remaining[len(bounds):]
                for number, dim in enumerate(bounds):
                    low = _integer(dim.get("minrange"), "minrange", signed=True)
                    high = _integer(dim.get("maxrange"), "maxrange", signed=True)
                    index = selected[number] if selected is not None else None
                    if index is not None and not low <= index <= high:
                        _fail("SYMBOL_ARRAY_BOUNDS", "Array index is outside inclusive bounds",
                              index=index, minimum=low, maximum=high)
                    dimensions.append({"min": low, "max": high, "index": index,
                                       "array_type": typ.get("name"), "dimension": number})
                if selected is None:
                    break
                base = self._types[typ.get("basetype")]
                stride = base.get("nativesize")
                if stride is None and _tag(base) == "TypeSimple":
                    stride = base.get("size")
                if offset is not None and len(bounds) == 1 and stride is not None:
                    offset += (selected[0] - int(bounds[0].get("minrange"))) * int(stride)
                else:
                    # Multidimensional stride/order is not established by these exports.
                    offset = None
                typ = base
            if remaining:
                _fail("SYMBOL_NOT_ARRAY", "Too many indexes for the symbol type")
            explicit = _children(node, "Node")
            if explicit:
                scope = _unique(explicit, "name")
            elif _tag(typ) == "TypeUserDef" and typ.get("typeclass", "").lower() != "enum":
                scope = _unique(_children(typ, "UserDefElement"), "iecname")
            else:
                scope = {}
            if step < len(parts) - 1 and not scope:
                _fail("SYMBOL_NOT_STRUCT", "Path continues through a scalar, enum or unindexed array")
        if typ is None:
            _fail("SYMBOL_TYPE", "Symbol path ends at an untyped group")
        size = int(typ.get("size"))
        iec_type = typ.get("iecname")
        is_enum = typ.get("typeclass", "").lower() == "enum"
        time_type = iec_type.upper() in {"TIME", "LTIME", "TIME_OF_DAY", "TOD", "DATE", "DT", "DATE_AND_TIME"}
        return {"path": ".".join(canonical), "iec_type": iec_type,
                "bits": 1 if iec_type.upper() in {"BOOL", "BIT"} else size * 8,
                "readable": rights_seen and "read" in rights,
                "writable": rights_seen and "write" in rights,
                "access_status": "DECLARED" if rights_seen else "UNSPECIFIED",
                "size": size,
                "native_size": int(typ.get("nativesize")) if typ.get("nativesize") is not None else None,
                "byte_offset": offset, "offset_base": offset_base,
                "bit_offset": int(typ.get("bitoffset")) if typ.get("bitoffset") is not None else None,
                "dimensions": dimensions, "type_name": typ.get("name"),
                "type_kind": _tag(typ), "direct_address": direct_address,
                "numeric_coercion_supported": not time_type and (iec_type.upper() in _NUMERIC or is_enum),
                "numeric_coercion_status": "UNSUPPORTED_TIME_COERCION" if time_type else
                    "DECLARED_NUMERIC_TYPE" if iec_type.upper() in _NUMERIC or is_enum else "NOT_NUMERIC",
                "enum_values": [{"name": member.get("iecname"), "value": int(member.get("enumvalue"))}
                                for member in _children(typ, "UserDefElement")] if is_enum else []}

    def inventory(self) -> list[dict]:
        """List published typed nodes; arrays stay bounded, unexpanded entries."""
        output = []
        stack = [(self._root, self.root_name)]
        while stack:
            node, path = stack.pop()
            if node.get("type") is not None:
                output.append(self.resolve(path))
            for child in reversed(_children(node, "Node")):
                stack.append((child, path + "." + child.get("name")))
        return output


def assert_additive_symbols(previous: SymbolCatalog, candidate: SymbolCatalog):
    """XML updates may add definitions; old published shapes cannot be retyped."""
    stack = [(previous._root, candidate._root)]
    while stack:
        old_node, new_node = stack.pop()
        if old_node.attrib != new_node.attrib:
            _fail('XML_TYPE_DRIFT', 'Existing published node metadata must remain exact')
        for key in ('name', 'type', 'access', 'directaddress', 'byteoffset'):
            if old_node.get(key) != new_node.get(key):
                _fail('XML_TYPE_DRIFT', 'An existing published node was redirected or reinterpreted')
        old_children, new_children = _children(old_node, 'Node'), _children(new_node, 'Node')
        if old_node.get('type') is not None and not old_children and new_children:
            _fail('XML_TYPE_DRIFT', 'New explicit children cannot shadow existing implicit type members')
        for child in old_children:
            found = [n for n in new_children if n.get('name') == child.get('name')]
            if len(found) != 1:
                _fail('XML_TYPE_DRIFT', 'An existing published node disappeared')
            stack.append((child, found[0]))
    for name, old in previous._types.items():
        new = candidate._types.get(name)
        if new is None or _tag(old) != _tag(new):
            _fail('XML_TYPE_DRIFT', 'An existing type definition was removed or reinterpreted')
        if set(old.attrib) != set(new.attrib):
            _fail('XML_TYPE_DRIFT', 'Existing type metadata keys changed')
        struct_type = _tag(old) == 'TypeUserDef' and old.get('typeclass', '').lower() != 'enum'
        for key, value in old.attrib.items():
            if key in ('size', 'nativesize') and struct_type:
                if int(new.get(key, '-1')) < int(value):
                    _fail('XML_TYPE_DRIFT', 'Existing structure storage shrank')
            elif new.get(key) != value:
                _fail('XML_TYPE_DRIFT', 'An existing type attribute changed')
        for member in _children(old, 'UserDefElement'):
            found = [m for m in _children(new, 'UserDefElement') if m.get('iecname') == member.get('iecname')]
            if len(found) != 1 or found[0].attrib != member.attrib:
                _fail('XML_TYPE_DRIFT', 'An existing member type, offset, access or enumeration changed')
        if _tag(old) == 'TypeArray' and [d.attrib for d in _children(old, 'ArrayDim')] != [d.attrib for d in _children(new, 'ArrayDim')]:
            _fail('XML_TYPE_DRIFT', 'Existing array bounds changed')
    for row in previous.inventory():
        new = candidate.resolve(row['path'])
        if row['iec_type'] != new['iec_type'] or row['type_kind'] != new['type_kind'] or row['type_name'] != new['type_name'] or (row['readable'] and not new['readable']) or (row['writable'] and not new['writable']):
            _fail('XML_TYPE_DRIFT', 'An existing published symbol changed its type or access')


def parse_symbols(xmlbytes: bytes) -> SymbolCatalog:
    if not isinstance(xmlbytes, bytes):
        _fail("SYMBOL_INPUT", "Symbol XML must be bytes")
    if not xmlbytes or len(xmlbytes) > 16 * 1024 * 1024:
        _fail("SYMBOL_LIMIT", "Empty or oversized symbol XML")
    declaration_view = xmlbytes.replace(b"\0", b"").upper()
    if b"<!DOCTYPE" in declaration_view or b"<!ENTITY" in declaration_view:
        _fail("SYMBOL_DTD", "DTD and entity declarations are not supported")
    try:
        root = ET.fromstring(xmlbytes)
    except (ET.ParseError, ValueError, LookupError) as exc:
        _fail("SYMBOL_XML", "Malformed or unsupported symbol XML", reason=str(exc))
    if _tag(root) != "Symbolconfiguration":
        _fail("SYMBOL_ROOT", "Expected a Symbolconfiguration root")
    namespace = root.tag.partition("}")[0][1:] if root.tag.startswith("{") else ""
    if namespace not in {"", SYMBOL_NAMESPACE}:
        _fail("SYMBOL_NAMESPACE", "Unrecognized symbol XML namespace")
    stack, count = [(root, 0)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > 100000 or depth > 128:
            _fail("SYMBOL_LIMIT", "Symbol XML tree exceeds bounded limits")
        node_namespace = node.tag.partition("}")[0][1:] if node.tag.startswith("{") else ""
        if node_namespace != namespace:
            _fail("SYMBOL_NAMESPACE", "Mixed XML namespaces are not supported")
        if node.get("access") is not None and node.get("access") not in _RIGHTS:
            _fail("SYMBOL_ACCESS", "Unknown access declaration", access=node.get("access"))
        for field in ("byteoffset", "bitoffset"):
            if node.get(field) is not None:
                _integer(node.get(field), field)
        _unique(_children(node, "Node"), "name")
        stack.extend((child, depth + 1) for child in node)
    typelists, nodelists = _children(root, "TypeList"), _children(root, "NodeList")
    if len(typelists) != 1 or len(nodelists) != 1:
        _fail("SYMBOL_STRUCTURE", "Exactly one TypeList and NodeList is required")
    types = _unique(list(typelists[0]), "name")
    nodes = _children(nodelists[0], "Node")
    if len(nodes) != 1:
        _fail("SYMBOL_STRUCTURE", "Exactly one named application root is required")
    _unique(nodes, "name")
    for typ in types.values():
        kind = _tag(typ)
        if kind not in {"TypeSimple", "TypeArray", "TypeUserDef"}:
            _fail("SYMBOL_TYPE", "Unsupported symbol type declaration", kind=kind)
        _integer(typ.get("size"), "size")
        if kind == "TypeSimple" and int(typ.get("size")) == 0:
            _fail("SYMBOL_TYPE", "A scalar type cannot have zero storage size")
        if not typ.get("iecname"):
            _fail("SYMBOL_TYPE", "Missing IEC type name")
        if typ.get("nativesize") is not None:
            _integer(typ.get("nativesize"), "nativesize")
        if kind == "TypeArray":
            dims = _children(typ, "ArrayDim")
            if not dims or len(dims) > 16 or typ.get("basetype") not in types:
                _fail("SYMBOL_TYPE", "Invalid array rank or base type")
            for dim in dims:
                if _integer(dim.get("minrange"), "minrange", signed=True) > _integer(dim.get("maxrange"), "maxrange", signed=True):
                    _fail("SYMBOL_ARRAY_BOUNDS", "Array bounds are inverted")
        if kind == "TypeUserDef":
            members = _children(typ, "UserDefElement")
            _unique(members, "iecname")
            if typ.get("typeclass", "").lower() == "enum":
                if typ.get("basetype") not in types:
                    _fail("SYMBOL_TYPE", "Unknown enum base type")
                for member in members:
                    _integer(member.get("enumvalue"), "enumvalue", signed=True)
                    if member.get("type") != typ.get("name"):
                        _fail("SYMBOL_TYPE", "Unsupported enum member type")
            elif typ.get("pouclass", "").upper() != "STRUCTURE":
                _fail("SYMBOL_TYPE", "Unsupported user-defined type class")
    for node in root.iter():
        reference = node.get("type")
        if reference is not None and reference not in types:
            _fail("SYMBOL_TYPE", "Unknown type reference", type_name=reference)
    visiting, visited = set(), set()

    def visit(name, depth=0):
        if name not in types:
            _fail("SYMBOL_TYPE", "Unknown base type reference", type_name=name)
        if name in visiting or depth > 128:
            _fail("SYMBOL_TYPE_CYCLE", "Cyclic or excessively deep type graph")
        if name in visited:
            return
        visiting.add(name)
        typ = types[name]
        if typ.get("basetype") is not None:
            visit(typ.get("basetype"), depth + 1)
        if _tag(typ) == "TypeUserDef" and typ.get("typeclass", "").lower() != "enum":
            for member in _children(typ, "UserDefElement"):
                if member.get("type") is None:
                    _fail("SYMBOL_TYPE", "Missing structure member type")
                visit(member.get("type"), depth + 1)
        visiting.remove(name)
        visited.add(name)

    for name in types:
        visit(name)
    return SymbolCatalog(xmlbytes, hashlib.sha256(xmlbytes).hexdigest(), nodes[0].get("name"), nodes[0], types)


def parse_address(address: str) -> dict:
    if not isinstance(address, str) or len(address) > 8192:
        _fail("ADDRESS_FORMAT", "Expected a bounded object DIA_TAG address")
    match = _ADDRESS.fullmatch(address)
    if not match:
        _fail("ADDRESS_FORMAT", "Expected object DIA_TAG address syntax")
    if len(match[2]) > 9:
        _fail("ADDRESS_FORMAT", "Station number exceeds the bounded address profile")
    _parts(match[3])
    return {"kind": "dia_tag", "link": match[1], "station": int(match[2]), "path": match[3]}


def validate_reference(address: str, role: str, catalog: SymbolCatalog, link: str, station: int | str) -> dict:
    parsed = parse_address(address)
    if parsed["link"] != link or str(parsed["station"]) != str(station):
        _fail("ADDRESS_TARGET", "Address link or station differs from the selected profile")
    if not isinstance(role, str):
        _fail("ADDRESS_ROLE", "Unknown binding role")
    normalized = role.lower().replace("_", "")
    read_roles = {"read", "readvar", "trigger", "triggervar", "interlock", "interlockvar",
                  "visible", "visiblevar", "displaydotvar", "unitsrcvar", "unitdisplayvar"}
    if normalized not in read_roles | {"write", "writevar"}:
        _fail("ADDRESS_ROLE", "Unknown binding role", role=role)
    symbol = catalog.resolve(parsed["path"])
    permission = "readable" if normalized in read_roles else "writable"
    if not symbol[permission]:
        _fail("ADDRESS_ACCESS", "Symbol access does not permit this binding role", role=role,
              path=symbol["path"])
    return {**parsed, "role": role, "symbol": symbol}
