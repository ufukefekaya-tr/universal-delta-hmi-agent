"""Original source-local compiler for a deliberately bounded REV instruction subset.

This module does not manufacture vendor opcodes, flags, aliases or external
bindings. Every emitted instruction is cloned from an exact source-local line;
both its source tokens and its compiled operands are updated together.
"""
from dataclasses import dataclass
import hashlib
import re
import struct

from ..errors import HmiError
from .macros import EMPTY_LINE, MARKER, MacroLine, MacroProgram


OWNER_FIELDS = {
    "application": frozenset({"InitialMacroLen", "BackgroundMacroLen", "ClockMacroLen"}),
    "screen": frozenset({"OpenMacroLen", "CloseMacroLen", "CycleMacroLen"}),
    "element": frozenset({"BeforeExecMacroLen", "AfterExecMacroLen", "ButtonOnMacroLen", "ButtonOffMacroLen"}),
}
SCHEDULE_FIELDS = {
    "application": ("ClockMacroDelayTime", "ClockMacroPriority", "LineBrkBackgndMacro"),
    "screen": ("CycleMacroDelayTime", "EnableCycleMacro"),
    "element": (),
}
DESCRIPTORS = {"assign": "2507031e", "add": "240f0700", "bit_on": "0a00011b",
               "bit_off": "0a00011c", "if": "140e0348", "else": "0000005c", "endif": "0000005d"}
_DESCRIPTOR_OPS = {bytes.fromhex(value): key for key, value in DESCRIPTORS.items()}
_TYPES = {"UINT": (0, 65535, 0, 0), "UDINT": (0, 4294967295, 1, 0),
          "DINT": (-2147483648, 2147483647, 1, 1), "BOOL": (0, 1, 0, 0),
          "CONTROL": (0, 0, 0, 0)}
MAX_STATEMENTS = 4096
MAX_DEPTH = 16
MAX_SOURCE_BYTES = 1024
_WORD = r"\$(?:0|[1-9][0-9]{0,9})"
_BIT = _WORD + r"\.(?:0|[1-9]|1[0-5])"
_LITERAL = r"(?:0|-?[1-9][0-9]{0,9})"
_OPERAND = "(?:" + _WORD + "|" + _LITERAL + ")"
_SUFFIX = r"(?P<suffix>\s+\((?:Signed\s+)?DW\))?\s*"
_PATTERNS = {
    "assign": re.compile(r"\s*(?P<address>" + _WORD + r")\s*=\s*(?P<value>" + _OPERAND + ")" + _SUFFIX, re.I),
    "add": re.compile(r"\s*(?P<address>" + _WORD + r")\s*=\s*(?P<left>" + _OPERAND
                      + r")\s*\+\s*(?P<right>" + _OPERAND + ")" + _SUFFIX, re.I),
    "bit_on": re.compile(r"\s*BITON\s+(?P<address>" + _BIT + r")\s*", re.I),
    "bit_off": re.compile(r"\s*BITOFF\s+(?P<address>" + _BIT + r")\s*", re.I),
    "if": re.compile(r"\s*IF\s+(?P<address>" + _WORD + r")\s*==\s*(?P<value>" + _LITERAL + r")\s*", re.I),
    "else": re.compile(r"\s*ELSE\s*", re.I),
    "endif": re.compile(r"\s*ENDIF\s*", re.I),
}
_ACTIVE = {"assign": ("address", "value"), "add": ("address", "left", "right"),
           "bit_on": ("address",), "bit_off": ("address",), "if": ("address", "value"),
           "else": (), "endif": ()}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _hash(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise HmiError("INVALID_MACRO", "Macro guards require a canonical SHA-256", field=label)
    return value


def _id(value):
    maximum = str(0x7FFFFFFF)
    if (not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]*", value)
            or len(value) > len(maximum) or (len(value) == len(maximum) and value > maximum)):
        raise HmiError("INVALID_MACRO_OWNER", "Macro identity requires a canonical native ID")
    return value


def normalize_owner(owner):
    if not isinstance(owner, dict) or not isinstance(owner.get("kind"), str):
        raise HmiError("INVALID_MACRO_OWNER", "Macro owner must be an explicit object")
    kind = owner["kind"]
    keys = {"application": {"kind"}, "screen": {"kind", "screen_id"},
            "element": {"kind", "screen_id", "element_id"}}.get(kind)
    if keys is None or set(owner) != keys:
        raise HmiError("INVALID_MACRO_OWNER", "Macro owner keys do not identify one supported owner")
    return {key: (owner[key] if key == "kind" else _id(owner[key])) for key in sorted(keys)}


def _field(section, name):
    record = section.one(name)
    return record.value.decode("latin-1")


def owner_sections(document):
    """Actual section owners only; State/auxiliary/global records inherit none."""
    screen_id = None
    owners = {}
    for index, section in enumerate(document.sections):
        if section.name == "Application":
            owners[index] = {"kind": "application"}
            screen_id = None
        elif section.name == "Screen":
            screen_id = _id(_field(section, "ID"))
            owners[index] = {"kind": "screen", "screen_id": screen_id}
        elif section.name == "Element" and screen_id is not None:
            owners[index] = {"kind": "element", "screen_id": screen_id,
                             "element_id": _id(_field(section, "nPartsID"))}
    return owners


def macro_record(document, owner, field):
    owner = normalize_owner(owner)
    if not isinstance(field, str) or field not in OWNER_FIELDS[owner["kind"]]:
        raise HmiError("INVALID_MACRO_OWNER", "Macro field is not valid for this exact owner")
    if sum(section.name == "Application" for section in document.sections) != 1:
        raise HmiError("AMBIGUOUS_MACRO_OWNER", "Macro changes require exactly one Application section")
    matches = [document.sections[index] for index, value in owner_sections(document).items() if value == owner]
    if len(matches) != 1:
        raise HmiError("AMBIGUOUS_MACRO_OWNER", "Macro owner does not identify exactly one native section")
    for key in SCHEDULE_FIELDS[owner["kind"]]:
        matches[0].one(key, False)
    record = matches[0].one(field)
    if record.kind != "macro" or not isinstance(record.blob, bytes):
        raise HmiError("INVALID_MACRO_OWNER", "Owner field is not a native framed macro")
    return record


def inventory(document):
    owners = owner_sections(document)
    counts = {}
    for value in owners.values():
        key = tuple(sorted(value.items()))
        counts[key] = counts.get(key, 0) + 1
    result = []
    for index, section in enumerate(document.sections):
        owner = owners.get(index)
        for record_index, record in enumerate(section.records):
            if record.kind != "macro":
                continue
            qualified = owner is not None and record.key in OWNER_FIELDS[owner["kind"]]
            ambiguous = qualified and (counts[tuple(sorted(owner.items()))] != 1
                                       or sum(item.key == record.key for item in section.records) != 1)
            schedule = {}
            if qualified:
                for key in SCHEDULE_FIELDS[owner["kind"]]:
                    matches = [item for item in section.records if item.key == key]
                    if len(matches) == 1:
                        schedule[key] = matches[0].value.decode("latin-1")
                    elif len(matches) > 1:
                        ambiguous = True
            payload = record.blob
            item = {"owner": owner if qualified else None, "field": record.key,
                    "section_index": index, "record_index": record_index,
                    "owner_status": "AMBIGUOUS" if ambiguous else ("QUALIFIED" if qualified else "UNQUALIFIED"),
                    "sha256": sha(payload), "byte_count": len(payload), "schedule": schedule}
            if not payload:
                item["status"] = "EMPTY"
            elif not payload.startswith(MARKER):
                item["status"] = "OPAQUE_UNSUPPORTED"
            else:
                try:
                    parsed = MacroProgram.parse(payload)
                    item.update(status="REV_FRAMING_PASS", line_count=len(parsed.lines),
                                empty_line_count=sum(line.descriptor == EMPTY_LINE for line in parsed.lines))
                except HmiError as exc:
                    item.update(status="MALFORMED_REV", error_code=exc.code)
            result.append(item)
    return result


def _bounds(spec):
    bounds = spec.get("address_bounds")
    if (not isinstance(bounds, dict) or set(bounds) != {"minimum", "maximum"}
            or type(bounds["minimum"]) is not int or type(bounds["maximum"]) is not int
            or not 0 <= bounds["minimum"] <= bounds["maximum"] <= 0x7FFFFFFF):
        raise HmiError("INVALID_SCHEMA", "Macro internal word range needs explicit bounded target evidence")
    return bounds


def _address(value, datatype, bounds):
    pattern = _BIT if datatype == "BOOL" else _WORD
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise HmiError("UNSUPPORTED_MACRO_ADDRESS", "Macro subset requires canonical direct internal addresses")
    number = int(value[1:].split(".")[0])
    span = 2 if datatype in {"UDINT", "DINT"} else 1
    if number < bounds["minimum"] or number + span - 1 > bounds["maximum"]:
        raise HmiError("MACRO_ADDRESS_RANGE", "Internal address span exceeds the qualified target range")
    return value


def _literal(value, datatype):
    if type(value) is not int or datatype not in _TYPES or datatype in {"BOOL", "CONTROL"}:
        raise HmiError("INVALID_MACRO_VALUE", "Macro literal requires an exact supported integer datatype")
    low, high, _, _ = _TYPES[datatype]
    if not low <= value <= high:
        raise HmiError("MACRO_VALUE_RANGE", "Macro value exceeds the exact donor storage width")
    return str(value)


def _operand(value, datatype, bounds):
    return _address(value, datatype, bounds) if isinstance(value, str) and value.startswith("$") else _literal(value, datatype)


@dataclass(frozen=True)
class ParsedLine:
    op: str
    datatype: str
    source: str
    match: object
    arguments: tuple[str, ...]


def _parse_line(line, bounds):
    op = _DESCRIPTOR_OPS.get(line.descriptor)
    if op is None:
        raise HmiError("UNSUPPORTED_MACRO_COMMAND", "Macro instruction descriptor lacks an implemented semantic contract")
    if len(line.strings[0]) > MAX_SOURCE_BYTES:
        raise HmiError("MACRO_LIMIT", "Semantic macro source exceeds its bounded token limit")
    try:
        source = line.strings[0].decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise HmiError("UNSUPPORTED_MACRO_SOURCE", "Aliases and non-ASCII native source are not qualified") from exc
    if any(character in source for character in "\r\n\0"):
        raise HmiError("UNSUPPORTED_MACRO_SOURCE", "Semantic source must contain one instruction only")
    match = _PATTERNS[op].fullmatch(source)
    if match is None:
        raise HmiError("UNSUPPORTED_MACRO_SOURCE", "Source does not match the observed direct-internal instruction grammar")
    width, signed = struct.unpack("<II", line.flags[4:])
    if op in {"else", "endif"}:
        datatype = "CONTROL"
    elif op in {"bit_on", "bit_off"}:
        datatype = "BOOL"
    elif op == "if":
        datatype = "UINT"
    else:
        datatype = {(0, 0): "UINT", (1, 0): "UDINT", (1, 1): "DINT"}.get((width, signed))
    if datatype is None or (width, signed) != _TYPES[datatype][2:]:
        raise HmiError("UNSUPPORTED_MACRO_FLAGS", "Macro width or signedness has no observed instruction contract")
    if op in {"assign", "add"}:
        suffix = " ".join((match.group("suffix") or "").upper().split())
        if suffix != {"UINT": "", "UDINT": "(DW)", "DINT": "(SIGNED DW)"}[datatype]:
            raise HmiError("MACRO_SOURCE_OPERAND_MISMATCH", "Source width annotation disagrees with compiled flags")
    names = _ACTIVE[op]
    arguments = tuple(match.group(name) for name in names)
    for index, argument in enumerate(arguments, 1):
        if line.strings[index] != argument.encode("ascii"):
            raise HmiError("MACRO_SOURCE_OPERAND_MISMATCH", "Source token disagrees with its compiled operand", operand=index)
        if argument.startswith("$"):
            _address(argument, datatype, bounds)
        elif _literal(int(argument), datatype) != argument:
            raise HmiError("INVALID_MACRO_VALUE", "Macro literal spelling is not canonical")
    return ParsedLine(op, datatype, source, match, arguments)


@dataclass(frozen=True)
class Template:
    line: MacroLine
    parsed: ParsedLine

    def emit(self, arguments):
        # Token spans are replaced right to left. A literal 1 cannot alter $1.
        source = self.parsed.source
        names = _ACTIVE[self.parsed.op]
        for name, value in reversed(tuple(zip(names, arguments, strict=True))):
            start, end = self.parsed.match.span(name)
            source = source[:start] + value + source[end:]
        strings = list(self.line.strings)
        strings[0] = source.encode("ascii")
        for index, value in enumerate(arguments, 1):
            strings[index] = value.encode("ascii")
        return MacroLine(self.line.descriptor, tuple(strings), self.line.flags)


def calibrated_templates(source_document, schema):
    if not isinstance(schema, dict):
        raise HmiError("INVALID_SCHEMA", "Macro schema must be an object")
    spec = schema.get("macros")
    if not isinstance(spec, dict) or spec.get("qualified") is not True:
        raise HmiError("UNQUALIFIED_MACRO", "Semantic mutation requires source-local calibrated macro templates")
    if set(spec) - {"qualified", "address_bounds", "templates"}:
        raise HmiError("INVALID_SCHEMA", "Macro schema contains unimplemented settings")
    bounds = _bounds(spec)
    values = spec.get("templates")
    if not isinstance(values, list) or not values or len(values) > 64:
        raise HmiError("INVALID_SCHEMA", "Macro templates must be a nonempty bounded array")
    templates = {}
    for value in values:
        if not isinstance(value, dict) or set(value) != {"op", "datatype", "donor", "descriptor_hex", "flags_hex"}:
            raise HmiError("INVALID_SCHEMA", "Macro template needs exact donor metadata")
        op, datatype = value["op"], value["datatype"]
        if not isinstance(op, str) or op not in DESCRIPTORS or not isinstance(datatype, str) or datatype not in _TYPES:
            raise HmiError("INVALID_SCHEMA", "Template command/datatype is not implemented")
        key = (op, datatype)
        if key in templates:
            raise HmiError("INVALID_SCHEMA", "Macro command/datatype has duplicate donor templates")
        donor = value["donor"]
        if (not isinstance(donor, dict) or set(donor) != {"owner", "field", "program_sha256", "line_index", "line_sha256"}
                or type(donor["line_index"]) is not int or not 0 <= donor["line_index"] < 100_000):
            raise HmiError("INVALID_SCHEMA", "Macro donor requires exact owner/program/line guards")
        record = macro_record(source_document, donor["owner"], donor["field"])
        if sha(record.blob) != _hash(donor["program_sha256"], "donor.program_sha256"):
            raise HmiError("STALE_MACRO_DONOR", "Donor program differs from its source-local calibration")
        program = MacroProgram.parse(record.blob)
        if donor["line_index"] >= len(program.lines):
            raise HmiError("INVALID_SCHEMA", "Donor line does not exist")
        line = program.lines[donor["line_index"]]
        if sha(line.bytes()) != _hash(donor["line_sha256"], "donor.line_sha256"):
            raise HmiError("STALE_MACRO_DONOR", "Donor line differs from its source-local calibration")
        if (value["descriptor_hex"] != DESCRIPTORS[op] or value["descriptor_hex"] != line.descriptor.hex()
                or value["flags_hex"] != line.flags.hex()):
            raise HmiError("MACRO_DONOR_MISMATCH", "Descriptor and all twelve flags must match the exact donor")
        parsed = _parse_line(line, bounds)
        if (parsed.op, parsed.datatype) != key:
            raise HmiError("MACRO_DONOR_MISMATCH", "Declared command width/signedness disagrees with the native donor")
        templates[key] = Template(line, parsed)
    return templates, bounds


def _template(templates, op, datatype):
    value = templates.get((op, datatype))
    if value is None:
        raise HmiError("UNQUALIFIED_MACRO_COMMAND", "This command/datatype has no source-local calibrated template", command=op, datatype=datatype)
    return value


def compile_statements(statements, templates, bounds):
    lines = []
    normalized = []
    count = 0

    def visit(values, depth):
        nonlocal count
        if depth > MAX_DEPTH or not isinstance(values, list):
            raise HmiError("MACRO_LIMIT", "Macro statements require a bounded nested array")
        result = []
        for statement in values:
            count += 1
            if count > MAX_STATEMENTS:
                raise HmiError("MACRO_LIMIT", "Macro semantic instruction count exceeds its limit")
            if not isinstance(statement, dict) or not isinstance(statement.get("op"), str):
                raise HmiError("INVALID_MACRO", "Macro statement must name one supported instruction")
            op, datatype = statement["op"], statement.get("datatype")
            allowed = {"assign": {"op", "datatype", "address", "value"},
                       "add": {"op", "datatype", "address", "left", "right"},
                       "bit_on": {"op", "datatype", "address"}, "bit_off": {"op", "datatype", "address"},
                       "if": {"op", "datatype", "address", "value", "comparison", "then", "else"}}.get(op)
            required = allowed - ({"comparison", "else"} if op == "if" else set()) if allowed else set()
            if allowed is None or set(statement) - allowed or not required <= set(statement):
                raise HmiError("INVALID_MACRO", "Statement has missing or unsupported arguments")
            if not isinstance(datatype, str) or datatype not in _TYPES or datatype == "CONTROL":
                raise HmiError("UNSUPPORTED_MACRO_TYPE", "Statement datatype is not implemented")
            if ((op in {"bit_on", "bit_off"} and datatype != "BOOL")
                    or (op == "if" and datatype != "UINT") or (op in {"assign", "add"} and datatype == "BOOL")):
                raise HmiError("UNSUPPORTED_MACRO_TYPE", "Command requires its exact observed donor storage type")
            address = _address(statement["address"], datatype, bounds)
            arguments = [address]
            item = {"op": op, "datatype": datatype, "address": address}
            if op in {"assign", "if"}:
                literal = _literal(statement["value"], datatype)
                arguments.append(literal)
                item["value"] = statement["value"]
            elif op == "add":
                for name in ("left", "right"):
                    arguments.append(_operand(statement[name], datatype, bounds))
                    item[name] = statement[name]
            if op == "if" and statement.get("comparison", "eq") != "eq":
                raise HmiError("UNSUPPORTED_MACRO_COMPARISON", "Only the observed UINT equality conditional is implemented")
            lines.append(_template(templates, op, datatype).emit(tuple(arguments)))
            if op == "if":
                if not statement["then"]:
                    raise HmiError("INVALID_MACRO", "Conditional then branch must not be empty")
                item.update(comparison="eq", then=visit(statement["then"], depth + 1))
                if "else" in statement and statement["else"]:
                    lines.append(_template(templates, "else", "CONTROL").emit(()))
                    item["else"] = visit(statement["else"], depth + 1)
                elif "else" in statement:
                    if not isinstance(statement["else"], list):
                        raise HmiError("INVALID_MACRO", "Conditional else branch must be an array")
                lines.append(_template(templates, "endif", "CONTROL").emit(()))
            result.append(item)
        return result

    normalized = visit(statements, 0)
    return (MacroProgram(tuple(lines)).bytes() if lines else b""), normalized


def project_program(payload, templates, bounds):
    if not payload:
        return []
    program = MacroProgram.parse(payload)
    result = []
    current = result
    stack = []
    count = 0
    for line in program.lines:
        if line.descriptor == EMPTY_LINE:
            continue
        count += 1
        if count > MAX_STATEMENTS:
            raise HmiError("MACRO_LIMIT", "Macro semantic instruction count exceeds its limit")
        parsed = _parse_line(line, bounds)
        template = _template(templates, parsed.op, parsed.datatype)
        active = len(_ACTIVE[parsed.op])
        if line.flags != template.line.flags or line.strings[active + 1:] != template.line.strings[active + 1:]:
            raise HmiError("MACRO_DONOR_MISMATCH", "Instruction opaque flags/unused operands differ from the exact donor")
        op = parsed.op
        if op == "else":
            if not stack or stack[-1][2]:
                raise HmiError("MACRO_STRUCTURE", "Orphan or repeated ELSE")
            item, parent, _ = stack[-1]
            if not current:
                raise HmiError("MACRO_STRUCTURE", "Conditional then branch is empty")
            item["else"] = []
            current = item["else"]
            stack[-1] = (item, parent, True)
        elif op == "endif":
            if not stack or not current:
                raise HmiError("MACRO_STRUCTURE", "Orphan ENDIF or empty conditional branch")
            _, current, _ = stack.pop()
        else:
            item = {"op": op, "datatype": parsed.datatype, "address": parsed.arguments[0]}
            if op in {"assign", "if"}:
                if parsed.arguments[1].startswith("$"):
                    raise HmiError("UNSUPPORTED_MACRO_SOURCE", "Address-to-address assignment requires a separate common contract")
                item["value"] = int(parsed.arguments[1])
            elif op == "add":
                for name, argument in zip(("left", "right"), parsed.arguments[1:], strict=True):
                    item[name] = argument if argument.startswith("$") else int(argument)
            current.append(item)
            if op == "if":
                if len(stack) >= MAX_DEPTH:
                    raise HmiError("MACRO_LIMIT", "Macro nesting exceeds its limit")
                item.update(comparison="eq", then=[])
                stack.append((item, current, False))
                current = item["then"]
    if stack:
        raise HmiError("MACRO_STRUCTURE", "Conditional macro lacks ENDIF")
    return result


def configure(document, source_document, operation, schema):
    _operation(operation)
    record = macro_record(document, operation.get("owner"), operation.get("field"))
    if sha(record.blob) != _hash(operation.get("expected_program_sha256"), "expected_program_sha256"):
        raise HmiError("STALE_MACRO_PROGRAM", "Target program differs from the explicitly approved source")
    templates, bounds = calibrated_templates(source_document, schema)
    # Replacing unsupported source is not a loophole for silently deleting it.
    existing = project_program(record.blob, templates, bounds)
    payload, requested = compile_statements(operation.get("statements"), templates, bounds)
    # A semantic no-op must preserve blank lines, case, spacing and compression,
    # rather than normalize a valid vendor program into our donor presentation.
    if existing == requested:
        return
    if project_program(payload, templates, bounds) != requested:
        raise HmiError("MACRO_VERIFY", "Emitted program does not project to its requested contract")
    if record.blob != payload:
        record.blob = payload
        record.set_value(str(len(payload)).encode("ascii"), force=True)


def statements(document, source_document, owner, field, schema):
    record = macro_record(document, owner, field)
    templates, bounds = calibrated_templates(source_document, schema)
    return project_program(record.blob, templates, bounds)


def verify(document, source_document, operation, schema):
    _operation(operation)
    original = macro_record(source_document, operation.get("owner"), operation.get("field"))
    if sha(original.blob) != _hash(operation.get("expected_program_sha256"), "expected_program_sha256"):
        raise HmiError("STALE_MACRO_PROGRAM", "Verification source differs from the approved program")
    templates, bounds = calibrated_templates(source_document, schema)
    existing = project_program(original.blob, templates, bounds)
    _, requested = compile_statements(operation.get("statements"), templates, bounds)
    candidate = macro_record(document, operation.get("owner"), operation.get("field"))
    actual = project_program(candidate.blob, templates, bounds)
    if actual != requested:
        raise HmiError("MACRO_VERIFY", "Saved native macro differs from the requested semantic contract")
    if existing == requested and candidate.raw != original.raw:
        raise HmiError("MACRO_NOOP_CHANGED", "A semantic no-op changed the original framed macro bytes")
    return True


def _operation(operation):
    if (not isinstance(operation, dict) or set(operation) != {"op", "owner", "field", "expected_program_sha256", "statements"}
            or operation["op"] != "configure_macro"):
        raise HmiError("INVALID_MACRO", "Macro contract requires the complete configure_macro operation")
