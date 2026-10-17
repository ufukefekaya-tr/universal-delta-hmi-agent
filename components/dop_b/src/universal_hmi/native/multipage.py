"""Source-qualified mixed pages, assembled without importing donor globals.

The blank target, six-control library and auxiliary reference are separate
immutable sources. Only pinned page/owner extents enter the target. This is
stored-file qualification, not vendor compilation, pixels or PLC behavior.
"""
from copy import deepcopy
import hashlib
import math
import re

from ..errors import HmiError
from . import (NativeAdapter, _groups, _screen, _element, _identity, _integer,
               _value, _native_int, _LITERAL_PAGE_FIELDS, _LITERAL_ELEMENT_FIELDS,
               _LITERAL_STATE_FIELDS, _CONTROL_COMMON)
from .codec import MAX_PAYLOAD
from .program import BlankProgram


MAX_PAGES = 256
MAX_OWNERS = 4096
MAX_OPERATIONS = 65536
_SHA = re.compile(r"[0-9a-f]{64}")
_KINDS = {"text": ("10", "6"), "indicator": ("2", "1"), "goto": ("1", "10")}
_TEXT_FIELDS = _LITERAL_ELEMENT_FIELDS - {"wDescTextLen"}
_GOTO_FIELDS = _CONTROL_COMMON | {
    "TriggerLink", "TriggerVar", "GoToScreenName", "GoToScreenID", "CloseScreen",
    "Variation", "Order", "CancelActBit", "SetLowSecurity", "InterLockLink",
    "InterLockVar", "InterLockLevel", "ConFirmWindow", "NoMessage", "DispAsterisk",
    "BeforeExecMacroLen", "AfterExecMacroLen"}
_FIELDS = {"text": _TEXT_FIELDS, "indicator": _CONTROL_COMMON, "goto": _GOTO_FIELDS}
_PAGE_MANAGED = {"ID", "wTextLen", "wScreenDESCTextLen000", "ScreenAction"}
_ELEMENT_MANAGED = {"nPartsID", "X", "Y", "Width", "Height"}
_STATE_MANAGED = {"wTextLen0", "BgColor", "FontColor", "FontSize0"}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded(value):
    """Reject non-JSON/cyclic/deep inputs before any recursive copy."""
    active, pending, nodes, strings = set(), [(False, value, 0)], 0, 0
    while pending:
        leaving, item, depth = pending.pop()
        if leaving:
            active.remove(id(item)); continue
        nodes += 1
        if nodes > 250000 or depth > 64:
            raise HmiError("MULTIPAGE_LIMIT", "Multipage metadata exceeds its structural bound")
        if isinstance(item, (dict, list)):
            if id(item) in active:
                raise HmiError("MULTIPAGE_LIMIT", "Multipage metadata cannot contain a cycle")
            active.add(id(item)); pending.append((True, item, depth))
            if isinstance(item, dict):
                if any(not isinstance(key, str) for key in item):
                    raise HmiError("INVALID_MULTIPAGE_METADATA", "Metadata keys must be strings")
                pending.extend((False, key, depth + 1) for key in item)
                pending.extend((False, child, depth + 1) for child in item.values())
            else:
                pending.extend((False, child, depth + 1) for child in item)
        elif isinstance(item, str):
            strings += len(item)
            if strings > MAX_PAYLOAD:
                raise HmiError("MULTIPAGE_LIMIT", "Multipage text exceeds its aggregate resource bound")
        elif item is None or type(item) is bool:
            continue
        elif type(item) is int:
            if item.bit_length() > 256:
                raise HmiError("MULTIPAGE_LIMIT", "Metadata integer exceeds its resource bound")
        elif type(item) is float and math.isfinite(item):
            continue
        else:
            raise HmiError("INVALID_MULTIPAGE_METADATA", "Metadata must use finite JSON values")


def _pin(value, label):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise HmiError("UNQUALIFIED_MULTIPAGE", "Multipage provenance needs canonical SHA-256", field=label)


def _page_id(value):
    value = _identity(value, "screen_id")
    if not 1 <= int(value) <= 65535:
        raise HmiError("INVALID_PAGE_ID", "Normal page identity must fit the qualified positive uint16 range")
    return value


def _name(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 256 or not value.isascii()
            or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise HmiError("INVALID_PAGE_NAME", "Page names require bounded printable ASCII for the navigation companion")
    return value


def _caption(value):
    if not isinstance(value, str) or len(value) > 4096 or "\0" in value:
        raise HmiError("INVALID_TEXT", "Caption must be bounded text without NUL")
    try:
        value.encode("utf-16-le", "strict")
    except UnicodeEncodeError as exc:
        raise HmiError("INVALID_TEXT", "Caption contains invalid Unicode") from exc
    return value


def _color(value):
    _integer(value, "color", 0, 0xFFFFFF)
    # No RGB/COLORREF ordering witness is implied by scalar native fields.
    # Equal red/blue channels have the same value under either interpretation.
    if value & 255 != value >> 16:
        raise HmiError("UNQUALIFIED_COLOR_ORDER", "Color needs equal red/blue channels until color ordering is qualified")
    return value


def multipage_contract(schema):
    """Validate a bounded descriptor; external authority remains caller-owned."""
    _bounded(schema)
    spec = schema.get("multipage_program") if isinstance(schema, dict) else None
    keys = {"qualified", "contract_version", "mode", "target_sha256", "controls_sha256",
            "controls_schema", "layout_sha256", "page_donor", "aux_donors", "authority_sha256"}
    if (not isinstance(schema, dict) or schema.get("qualified") is not True
            or {"blank_program", "control_generation", "literal_generation", "preserved_layout"} & set(schema)
            or not isinstance(spec, dict) or set(spec) != keys or spec.get("qualified") is not True
            or type(spec.get("contract_version")) is not int or spec["contract_version"] != 1
            or spec.get("mode") != "multipage_program" or not isinstance(spec.get("controls_schema"), dict)):
        raise HmiError("UNQUALIFIED_MULTIPAGE", "Multipage assembly requires its exact separate three-source contract")
    for field in ("target_sha256", "controls_sha256", "layout_sha256", "authority_sha256"):
        _pin(spec.get(field), field)
    controls_schema = spec["controls_schema"]
    if (controls_schema.get("qualified") is not True or "control_generation" not in controls_schema
            or {"blank_program", "multipage_program", "native_candidate", "literal_generation", "preserved_layout"} & set(controls_schema)):
        raise HmiError("UNQUALIFIED_MULTIPAGE", "Controls must retain their original distinct generation contract")
    page = spec.get("page_donor")
    if not isinstance(page, dict) or set(page) != {"screen_id", "header_sha256", "aux_sha256"}:
        raise HmiError("UNQUALIFIED_MULTIPAGE", "Page donor requires its exact identity and extent pins")
    _page_id(page.get("screen_id"))
    for field in ("header_sha256", "aux_sha256"):
        _pin(page.get(field), field)
    donors = spec.get("aux_donors")
    if not isinstance(donors, dict) or set(donors) != set(_KINDS):
        raise HmiError("UNQUALIFIED_MULTIPAGE", "Text, bit indicator and navigation need separate witnessed donors")
    seen = set()
    for kind, donor in donors.items():
        fields = {"screen_id", "element_id", "owner_sha256", "property_witness_sha256", "match"}
        if not isinstance(donor, dict) or set(donor) != fields:
            raise HmiError("UNQUALIFIED_MULTIPAGE", "Auxiliary donor requires exact owner and property fingerprints")
        _page_id(donor.get("screen_id")); _identity(donor.get("element_id"), "element_id")
        if donor["element_id"] == "0" or (donor["screen_id"], donor["element_id"]) in seen:
            raise HmiError("UNQUALIFIED_MULTIPAGE", "Auxiliary donor identities must be positive and distinct")
        seen.add((donor["screen_id"], donor["element_id"]))
        for field in ("owner_sha256", "property_witness_sha256"):
            _pin(donor.get(field), field)
        match = donor.get("match")
        if (not isinstance(match, dict) or set(match) != {"Type", "SubType"}
                or tuple(match.get(field) for field in ("Type", "SubType")) != _KINDS[kind]):
            raise HmiError("UNQUALIFIED_MULTIPAGE", "Auxiliary donor kind differs from its witnessed shape")
    return deepcopy(spec)


def _extent(adapter, owner):
    return adapter.document.sections[owner["start"]:owner["end"]]


def _masked_equal(section, source, fields, code="MULTIPAGE_MISMATCH"):
    """Only owned record values may differ, never order/kind/framing/unknowns."""
    if section.header != source.header or len(section.records) != len(source.records):
        raise HmiError(code, "Native extent changed its section or record shape")
    for current, original in zip(section.records, source.records):
        if current.key != original.key or current.kind != original.kind:
            raise HmiError(code, "Native extent changed record order or framing")
        if current.key not in fields and current.raw != original.raw:
            raise HmiError(code, "Native extent changed an unmanaged record", field=current.key)


class MultiPageProgram:
    """Blank target plus separate immutable controls and auxiliary extents."""

    def __init__(self, target, controls, layout, schema):
        multipage_contract(schema)  # Validate bounded shape before copying.
        self.target, self.controls, self.layout = target, controls, layout
        self.schema = deepcopy(schema)

    def _contract(self):
        return multipage_contract(self.schema)

    def _blank(self):
        spec = self._contract()
        schema = {"qualified": True, "blank_program": {
            "qualified": True, "contract_version": 1, "mode": "blank_program",
            "target_sha256": spec["target_sha256"], "library_sha256": spec["controls_sha256"],
            "library_schema": spec["controls_schema"], "tag_resource": "initialize_empty_source_tag_link"}}
        return BlankProgram(self.target, self.controls, schema)

    def library_profile(self):
        return self._blank().library_profile()

    @staticmethod
    def _page_shape(adapter, page, source=True):
        header = page["section"]
        NativeAdapter._control_shape(header, _LITERAL_PAGE_FIELDS)
        if _value(header, "VER") != "16" or _value(header, "ScreenLockVar") != "None":
            raise HmiError("UNQUALIFIED_MULTIPAGE_PAGE", "Normal page requires its observed header version and unlocked baseline")
        NativeAdapter._literal_zero(header, {"IsSubScreen", "IsKeypadScreen", "IsScreenRotate", "IsPrintScreen",
                                            "BaseScreenID", "Hidden", "OpenMacroLen", "CloseMacroLen", "CycleMacroLen"})
        for field in ("DocSizeX", "DocSizeY", "PanelSizeX", "PanelSizeY"):
            _integer(_native_int(header, field), field, 1, 65535)
        action = _native_int(header, "ScreenAction")
        if source:
            _integer(action, "ScreenAction", -2147483648, 2147483647)
        elif action != 0 or header.one("ScreenAction").value != b"0":
            raise HmiError("MULTIPAGE_MISMATCH", "New normal pages require the independently witnessed direct-render action 0")
        if header.one("wTitleTextLen000").blob != b"\0\0":
            raise HmiError("UNQUALIFIED_MULTIPAGE_PAGE", "Page title must retain its empty baseline")
        adapter._plain_extent(page)
        _page_id(page["id"]); _name(header.one("wTextLen").text())

    def _aux_shape(self, adapter, page, owner, kind, source=True):
        element = owner["section"]
        NativeAdapter._control_shape(element, _FIELDS[kind])
        if tuple(_value(element, key) for key in ("Type", "SubType")) != _KINDS[kind]:
            raise HmiError("UNQUALIFIED_MULTIPAGE_OWNER", "Auxiliary owner differs from its witnessed kind")
        zeros = {"GroupID", "Style", "PrintSuccessiveData", "ReadMemType", "WriteMemType", "Level",
                 "OffsetReadMemType", "OffsetWriteMemType", "nAngle", "bFreeze", "PosVary",
                 "Variation", "Order", "SetLowSecurity", "ConFirmWindow", "NoMessage", "DispAsterisk"}
        NativeAdapter._literal_zero(element, zeros & _FIELDS[kind])
        for field in {"WriteVar", "OffsetReadVar", "OffsetWriteVar", "VisibleVar", "TriggerVar",
                      "InterLockVar", "CancelActBit"} & _FIELDS[kind]:
            if _value(element, field) != "None":
                raise HmiError("UNQUALIFIED_MULTIPAGE_OWNER", "Auxiliary owner has an unqualified behavior address", field=field)
        if _value(element, "MemFmt") != "2" or _value(element, "MemLen") != ("1" if kind == "text" else "0"):
            raise HmiError("UNQUALIFIED_MULTIPAGE_OWNER", "Auxiliary storage differs from its witnessed type")
        if kind == "indicator":
            prefix = self._contract()["controls_schema"]["control_generation"]["address_prefix"]
            address = _value(element, "ReadVar")
            if source and address != prefix + "M0":
                raise HmiError("UNQUALIFIED_MULTIPAGE_OWNER", "Indicator source must witness the original driver M0 read context")
            NativeAdapter._control_address(address, prefix, "M", self._contract()["controls_schema"])
            if _value(element, "ReadLink") != "1":
                raise HmiError("UNQUALIFIED_MULTIPAGE_OWNER", "Indicator read metadata differs from its source context")
        elif _value(element, "ReadVar") != "None":
            raise HmiError("UNQUALIFIED_MULTIPAGE_OWNER", "Text/navigation cannot acquire a PLC binding")
        values = [state.one("Value").value for state in owner["states"]]
        if values != ([b"0", b"1"] if kind == "indicator" else [b"0"]):
            raise HmiError("UNQUALIFIED_MULTIPAGE_OWNER", "Auxiliary states require their exact witnessed order and identity")
        for state in owner["states"]:
            NativeAdapter._control_shape(state, _LITERAL_STATE_FIELDS)
            NativeAdapter._literal_zero(state, {"FontBold", "FontItalic", "FontUnderline", "UsePictureCoord",
                "TransEffect", "TransColor", "StretchMode", "PictureStretch", "Twinkles", "SoundIndex"})
            if _value(state, "FontRatio0") != "100" or _value(state, "FontName0") != "Arial":
                raise HmiError("UNQUALIFIED_MULTIPAGE_OWNER", "Auxiliary font baseline differs from its witnessed ratio/name")
            _integer(_native_int(state, "FontSize0"), "FontSize0", 1, 128)
            for field in ("FgColor", "BgColor", "FontColor"):
                _color(_native_int(state, field))
            _caption(state.one("wTextLen0").text())
        if kind == "goto":
            if _value(element, "CloseScreen") != "1":
                raise HmiError("UNQUALIFIED_MULTIPAGE_OWNER", "Navigation requires its witnessed normal-page close behavior")
            _page_id(_value(element, "GoToScreenID")); _name(_value(element, "GoToScreenName"))
        adapter._geometry(page, owner, {})

    def check(self):
        spec = self._contract()
        for label, adapter in (("target", self.target), ("controls", self.controls), ("layout", self.layout)):
            if not isinstance(adapter, NativeAdapter):
                raise HmiError("INVALID_MULTIPAGE_SOURCE", "Three-source program requires native adapters")
            adapter._preserved_byte_binding("INVALID_MULTIPAGE_SOURCE")
            adapter._control_prefix_length(adapter)
            if _sha(adapter.original) != spec[label + "_sha256"]:
                raise HmiError("INVALID_MULTIPAGE_SOURCE", "Source bytes differ from their immutable pin", source=label)
        if (self.target.family != "delta_dopsoft2" or self.layout.family != self.target.family
                or self.layout.model_id != self.target.model_id or self.layout.editor_version != self.target.editor_version):
            raise HmiError("MULTIPAGE_LINEAGE", "Auxiliary source must have the same qualified B model and raw editor version")
        self._blank().check()
        originals = _groups(self.target.document)
        if len(originals) != 1 or len(_groups(self.controls.document)) != 1:
            raise HmiError("UNQUALIFIED_MULTIPAGE", "This assembler requires the witnessed one-page blank/control source lineage")
        self._page_shape(self.target, originals[0])
        donor_page = _screen(self.layout.document, spec["page_donor"]["screen_id"])
        self._page_shape(self.layout, donor_page)
        pin = spec["page_donor"]
        if (_sha(donor_page["section"].bytes()) != pin["header_sha256"]
                or _sha(self.layout._plain_extent(donor_page).bytes()) != pin["aux_sha256"]):
            raise HmiError("INVALID_MULTIPAGE_SOURCE", "Page template differs from its exact source extents")
        if any(_value(donor_page["section"], field) != _value(originals[0]["section"], field)
               for field in ("DocSizeX", "DocSizeY", "PanelSizeX", "PanelSizeY")):
            raise HmiError("MULTIPAGE_LINEAGE", "Page template dimensions differ from the target resolution")
        for kind, pin in spec["aux_donors"].items():
            page = _screen(self.layout.document, pin["screen_id"])
            self.layout._plain_extent(page)
            owner = _element(page, pin["element_id"])
            if self.layout.owner_extent_sha256(page["id"], owner["id"]) != pin["owner_sha256"]:
                raise HmiError("INVALID_MULTIPAGE_SOURCE", "Auxiliary donor differs from its complete raw owner pin")
            self._aux_shape(self.layout, page, owner, kind)
        return True

    def _graph(self, operation):
        if not isinstance(operation, dict) or set(operation) != {"op", "screens"} or operation["op"] != "set_program_layout":
            raise HmiError("INVALID_PROGRAM_LAYOUT", "First operation must define the complete ordered program graph")
        screens = operation["screens"]
        if not isinstance(screens, list) or not 1 <= len(screens) <= MAX_PAGES:
            raise HmiError("INVALID_PROGRAM_LAYOUT", "Program graph must contain a bounded nonempty page list")
        ids, names, owners, locations = set(), set(), set(), {}
        reserved = {owner["id"] for page in _groups(self.controls.document) for owner in page["elements"]}
        graph = []
        for screen in screens:
            if not isinstance(screen, dict) or set(screen) != {"screen_id", "name", "elements"}:
                raise HmiError("INVALID_PROGRAM_LAYOUT", "Each graph page needs exact identity, name and owner order")
            identity, name = _page_id(screen["screen_id"]), _name(screen["name"])
            elements = screen["elements"]
            if identity in ids or name in names or not isinstance(elements, list):
                raise HmiError("INVALID_PROGRAM_LAYOUT", "Page identities/names must be unique and owners an explicit list")
            ids.add(identity); names.add(name)
            for value in elements:
                value = _identity(value, "element_id")
                if value == "0" or value in reserved or value in owners:
                    raise HmiError("DUPLICATE_ELEMENT", "Program owners must be positive, globally fresh and unique")
                owners.add(value); locations[value] = identity
                if len(owners) > MAX_OWNERS:
                    raise HmiError("MULTIPAGE_LIMIT", "Program exceeds its owner count bound")
            graph.append(deepcopy(screen))
        source = _groups(self.target.document)[0]
        if graph[0]["screen_id"] != source["id"] or graph[0]["name"] != source["section"].one("wTextLen").text():
            raise HmiError("INVALID_PROGRAM_LAYOUT", "Original first page identity/name must remain exact")
        return graph, locations

    def _aux_create(self, operation, names):
        common = {"op", "kind", "screen_id", "element_id", "x", "y", "width", "height"}
        optional = {"font_size", "color", "fill"}
        kind = operation.get("kind")
        required = common | ({"states", "read"} if kind == "indicator" else {"text", "target_screen"} if kind == "goto" else {"text"})
        if not isinstance(kind, str) or kind not in _KINDS or not required <= set(operation) or set(operation) - required - optional:
            raise HmiError("INVALID_AUX_OPERATION", "Auxiliary creation needs exact kind-specific arguments")
        if kind == "indicator" and "fill" in operation:
            raise HmiError("INVALID_AUX_OPERATION", "Indicator fills must be explicit per state")
        pin = self._contract()["aux_donors"][kind]
        owner = _element(_screen(self.layout.document, pin["screen_id"]), pin["element_id"])
        sections = deepcopy(_extent(self.layout, owner))
        element = sections[0]
        element.one("nPartsID").set_value(operation["element_id"].encode("ascii"))
        for key, field in (("x", "X"), ("y", "Y"), ("width", "Width"), ("height", "Height")):
            value = _integer(operation[key], key, 0 if key in {"x", "y"} else 1, 65535)
            element.one(field).set_value(str(value).encode("ascii"))
        states = sections[1:]
        if kind == "indicator":
            settings = operation["states"]
            if (not isinstance(settings, list) or len(settings) != 2
                    or any(not isinstance(state, dict) or set(state) != {"value", "text", "fill"}
                           or type(state["value"]) is not int or state["value"] != index
                           for index, state in enumerate(settings))):
                raise HmiError("INVALID_AUX_OPERATION", "Indicator needs ordered exact state 0/1 text and fill")
            binding = operation["read"]
            if (not isinstance(binding, dict) or set(binding) != {"address", "link", "mem_type"}
                    or type(binding["link"]) is not int or type(binding["mem_type"]) is not int
                    or binding["link"] != _native_int(element, "ReadLink")
                    or binding["mem_type"] != _native_int(element, "ReadMemType")):
                raise HmiError("CONTROL_ADDRESS_SCOPE", "Indicator must retain its exact source read metadata")
            schema = self._contract()["controls_schema"]
            prefix = schema["control_generation"]["address_prefix"]
            NativeAdapter._control_address(binding["address"], prefix, "M", schema)
            element.one("ReadVar").set_value(binding["address"].encode("ascii"))
            for state, setting in zip(states, settings):
                state.one("wTextLen0").set_text(_caption(setting["text"]))
                state.one("BgColor").set_value(str(_color(setting["fill"])).encode("ascii"))
        else:
            states[0].one("wTextLen0").set_text(_caption(operation["text"]))
            if kind == "goto":
                target = _page_id(operation["target_screen"])
                if target not in names:
                    raise HmiError("UNKNOWN_SCREEN", "Navigation target is absent from the complete final graph")
                element.one("GoToScreenID").set_value(target.encode("ascii"))
                element.one("GoToScreenName").set_value(names[target].encode("ascii"))
        for key, field in (("font_size", "FontSize0"), ("color", "FontColor"), ("fill", "BgColor")):
            if key in operation:
                value = _integer(operation[key], key, 1, 128) if key == "font_size" else _color(operation[key])
                for state in states:
                    state.one(field).set_value(str(value).encode("ascii"))
        return sections

    def apply(self, operations):
        self.check()
        _bounded(operations)
        if not isinstance(operations, list) or len(operations) > MAX_OPERATIONS:
            raise HmiError("INVALID_OPERATIONS", "Program operations require a bounded list")
        if not operations:
            return self.target.original
        graph, locations = self._graph(operations[0])
        names = {page["screen_id"]: page["name"] for page in graph}
        source_page = _groups(self.controls.document)[0]["id"]
        births, aux, control_ops = {}, {}, []
        for operation in operations[1:]:
            if not isinstance(operation, dict):
                raise HmiError("INVALID_OPERATION", "Program operations must be objects")
            name = operation.get("op")
            if not isinstance(name, str) or name not in {"clone_element", "create_aux", "set_property", "set_text", "bind", "configure_numeric", "convert_numeric_storage"}:
                raise HmiError("PROGRAM_SCOPE", "Multipage transaction contains an unsupported operation")
            sid = operation.get("target_screen" if name == "clone_element" else "screen_id")
            identity = _identity(operation.get("element_id"), "element_id")
            if identity not in locations or sid != locations[identity]:
                raise HmiError("PROGRAM_SCOPE", "Operation owner/destination is absent from the complete final graph")
            if name in {"clone_element", "create_aux"}:
                if identity in births:
                    raise HmiError("DUPLICATE_ELEMENT", "One transaction cannot create the same program owner twice")
                births[identity] = "aux" if name == "create_aux" else "control"
            elif births.get(identity) != "control":
                raise HmiError("PROGRAM_SCOPE", "Control edits require an already created control owner")
            if name == "set_property" and not isinstance(operation.get("key"), str):
                raise HmiError("INVALID_OPERATION", "Control property key must be a string")
            if name == "create_aux":
                aux[identity] = self._aux_create(operation, names)
            else:
                translated = deepcopy(operation)
                translated["target_screen" if name == "clone_element" else "screen_id"] = source_page
                control_ops.append(translated)
        if set(births) != set(locations):
            raise HmiError("PROGRAM_SCOPE", "Every graph owner must have exactly one explicit creation")
        generated = {}
        if control_ops:
            staged = NativeAdapter(self.controls.apply(control_ops, self.library_profile()), self.controls.family)
            old_count = len(_groups(self.controls.document)[0]["elements"])
            for owner in _groups(staged.document)[0]["elements"][old_count:]:
                generated[owner["id"]] = _extent(staged, owner)
        generated.update(aux)
        if set(generated) != set(locations):
            raise HmiError("PROGRAM_SCOPE", "Generated native owner set differs from the complete graph")
        chunks = [section.bytes() for section in BlankProgram._globals(self.target)]
        original = _groups(self.target.document)[0]
        spec = self._contract()
        template = _screen(self.layout.document, spec["page_donor"]["screen_id"])
        has_bindings = bool(control_ops) or any(births[identity] == "aux" and _value(generated[identity][0], "Type") == "2" for identity in generated)
        for index, page in enumerate(graph):
            if index == 0:
                header = original["section"]
                marker = self.target._plain_extent(original)
            else:
                header = deepcopy(template["section"])
                header.one("ID").set_value(page["screen_id"].encode("ascii"))
                header.one("wTextLen").set_text(page["name"])
                header.one("wScreenDESCTextLen000").set_text(page["name"])
                header.one("ScreenAction").set_value(b"0")
                marker = self.layout._plain_extent(template)
            chunks.extend((header.bytes(), marker.bytes()))
            chunks.extend(section.bytes() for identity in page["elements"] for section in generated[identity])
        chunks.append(self._blank().output_tail(has_bindings))
        if sum(map(len, chunks)) > MAX_PAYLOAD:
            raise HmiError("MULTIPAGE_LIMIT", "Generated native body exceeds the aggregate payload limit")
        body = b"".join(chunks)
        if body == self.target.envelope.body:
            return self.target.original
        output = self.target.envelope.encode(body)
        self.verify(NativeAdapter(output, self.target.family))
        return output

    def verify(self, candidate):
        self.check()
        if not isinstance(candidate, NativeAdapter):
            raise HmiError("INVALID_MULTIPAGE_CANDIDATE", "Program verification requires a saved native adapter")
        candidate._preserved_byte_binding("INVALID_MULTIPAGE_CANDIDATE")
        candidate._control_prefix_length(candidate)
        if (candidate.family != self.target.family or candidate.model_id != self.target.model_id
                or candidate.editor_version != self.target.editor_version
                or candidate.envelope.prefix != self.target.envelope.prefix_for_body(candidate.envelope.body)
                or candidate.envelope.thumbnail != self.target.envelope.thumbnail
                or candidate._preserved_prefix(candidate.document) != self.target._preserved_prefix(self.target.document)):
            raise HmiError("MULTIPAGE_MISMATCH", "Program changed target identity, opaque prefix, thumbnail or globals")
        pages, originals = _groups(candidate.document), _groups(self.target.document)
        if not 1 <= len(pages) <= MAX_PAGES or pages[0]["id"] != originals[0]["id"]:
            raise HmiError("MULTIPAGE_MISMATCH", "Program must retain the original first page and bounded graph")
        spec = self._contract()
        page_template = _screen(self.layout.document, spec["page_donor"]["screen_id"])
        names, ids, owners, control_extents = {}, set(), set(), []
        reserved = {owner["id"] for page in _groups(self.controls.document) for owner in page["elements"]}
        has_bindings = False
        for index, page in enumerate(pages):
            _page_id(page["id"])
            name = _name(page["section"].one("wTextLen").text())
            if name in names.values():
                raise HmiError("MULTIPAGE_MISMATCH", "Saved page names must remain unique")
            names[page["id"]] = name; ids.add(page["id"])
            if index == 0:
                if (page["section"].bytes() != originals[0]["section"].bytes()
                        or candidate._plain_extent(page).bytes() != self.target._plain_extent(originals[0]).bytes()):
                    raise HmiError("MULTIPAGE_MISMATCH", "Program changed original first-page header or auxiliary bytes")
            else:
                self._page_shape(candidate, page, source=False)
                _masked_equal(page["section"], page_template["section"], _PAGE_MANAGED)
                if (candidate._plain_extent(page).bytes() != self.layout._plain_extent(page_template).bytes()
                        or page["section"].one("wScreenDESCTextLen000").text() != name):
                    raise HmiError("MULTIPAGE_MISMATCH", "New page changed auxiliary framing or its exact description/name pair")
            for owner in page["elements"]:
                if owner["id"] == "0" or owner["id"] in owners or owner["id"] in reserved:
                    raise HmiError("DUPLICATE_ELEMENT", "Saved owners must remain globally fresh and unique")
                owners.add(owner["id"])
                if len(owners) > MAX_OWNERS:
                    raise HmiError("MULTIPAGE_LIMIT", "Saved program exceeds the owner count bound")
                pair = tuple(_value(owner["section"], key) for key in ("Type", "SubType"))
                kinds = [kind for kind, match in _KINDS.items() if match == pair]
                if not kinds:
                    candidate._geometry(page, owner, {})
                    control_extents.extend(_extent(candidate, owner)); has_bindings = True
                    continue
                kind = kinds[0]
                self._aux_shape(candidate, page, owner, kind, source=False)
                pin = spec["aux_donors"][kind]
                donor = _element(_screen(self.layout.document, pin["screen_id"]), pin["element_id"])
                managed = _ELEMENT_MANAGED | ({"ReadVar"} if kind == "indicator" else {"GoToScreenID", "GoToScreenName"} if kind == "goto" else set())
                _masked_equal(owner["section"], donor["section"], managed)
                for state, old in zip(owner["states"], donor["states"]):
                    _masked_equal(state, old, _STATE_MANAGED)
                has_bindings |= kind == "indicator"
        # Navigation is resolved only after the complete final page set exists.
        for page in pages:
            for owner in page["elements"]:
                if tuple(_value(owner["section"], key) for key in ("Type", "SubType")) == _KINDS["goto"]:
                    destination = _value(owner["section"], "GoToScreenID")
                    if destination not in ids or _value(owner["section"], "GoToScreenName") != names[destination]:
                        raise HmiError("MULTIPAGE_REFERENCE", "Saved navigation target/name differs from the complete final graph")
        if candidate.document.tail != self._blank().output_tail(has_bindings):
            raise HmiError("MULTIPAGE_MISMATCH", "Program changed target resources beyond the witnessed empty Tag initialization")
        # Reuse the strict six-control guard, without extending its kinds or
        # admitting the auxiliary reference's normalized legacy controls.
        if control_extents:
            source_page = _groups(self.controls.document)[0]
            context = [section.bytes() for section in BlankProgram._globals(self.controls)]
            context.extend((source_page["section"].bytes(), self.controls._plain_extent(source_page).bytes()))
            context.extend(section.bytes() for owner in source_page["elements"] for section in _extent(self.controls, owner))
            context.extend(section.bytes() for section in control_extents)
            context.append(self.controls.document.tail)
            body = b"".join(context)
            if len(body) > MAX_PAYLOAD:
                raise HmiError("MULTIPAGE_LIMIT", "Control verification context exceeds its payload bound")
            adapter = NativeAdapter(self.controls.envelope.encode(body), self.controls.family)
            adapter.verify_control_generation(spec["controls_schema"], self.controls)
        if len(pages) == 1 and not owners and candidate.original != self.target.original:
            raise HmiError("MULTIPAGE_MISMATCH", "Empty unchanged graph must preserve every original byte")
        return True
