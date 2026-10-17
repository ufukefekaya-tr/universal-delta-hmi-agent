"""Fail-closed validation of common design intent, independent of vendor files."""

import math
import re

from .value_model import FIXED_MODEL, INTEGER_RANGES, MAX_FRACTIONAL


KINDS = {"text", "button", "numeric_input", "numeric_display", "indicator", "goto",
         "alarm_strip", "alarm_table", "alarm_history", "native_preserved", "native_presentation", "native_integer_numeric", "native_entry_permission", "native_control_clone"}
ALARM_VIEWS = frozenset({"alarm_strip", "alarm_table", "alarm_history"})
NUMERIC = {
    "INT": (-32768, 32767, 0), "UINT": (0, 65535, 0),
    "DINT": (-2147483648, 2147483647, 0), "UDINT": (0, 4294967295, 0),
    "REAL": (-3.4028234663852886e38, 3.4028234663852886e38, 7),
    "LREAL": (-1.7976931348623157e308, 1.7976931348623157e308, 15),
    "TIME": (0, 4294967295, 0),
}
TYPES = {"BOOL", *NUMERIC}
SUPPORTED = {"OFFLINE_PASS", "VENDOR_PASS", "PHYSICAL_PASS"}
COLORS = re.compile(r"^(?:#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8})$")
SOURCE_OWNER_SHA = re.compile(r"[0-9a-f]{64}")
NATIVE_PRESERVED_FIELDS = frozenset({"id", "native_id", "kind", "x", "y", "width", "height", "text", "source_owner_sha256"})
IR_FIELDS = {
    "document": frozenset({"schema_version", "project_id", "profile_id", "screens", "tags", "macros", "alarms"}),
    "screen": frozenset({"id", "native_id", "name", "width", "height", "elements", "native_background"}),
    "element": frozenset({"id", "native_id", "kind", "x", "y", "width", "height", "text", "font_size", "color", "fill", "unit", "unit_label", "states", "binding", "behavior", "minimum", "maximum", "fractional", "format", "value_model", "target_screen", "role", "view_policy", "source_owner_sha256", "presentation", "integer_numeric", "entry_permission", "clone"}),
    "binding": frozenset({"read", "write"}),
    "tag": frozenset({"id", "address", "data_type", "access", "unit", "channel", "station", "byte_order", "word_order", "native_binding"}),
    "state": frozenset({"value", "text", "fill"}),
    "macro": frozenset({"id", "trigger", "statements"}),
    "statement": frozenset({"op", "tag", "value", "comparison", "then", "else"}),
    "alarm": frozenset({"id", "tag", "text", "history_policy"}),
    "native_binding": frozenset({"link", "mem_type"}),
}
_BASE_ELEMENT = {"id", "native_id", "kind", "x", "y", "width", "height", "text", "font_size", "color", "fill"}
_KIND_FIELDS = {
    "text": set(), "button": {"states", "binding", "behavior", "role"},
    "indicator": {"states", "binding", "role"},
    "numeric_input": {"binding", "role", "unit", "unit_label", "minimum", "maximum", "fractional", "format", "value_model"},
    "numeric_display": {"binding", "role", "unit", "unit_label", "minimum", "maximum", "fractional", "format", "value_model"},
    "goto": {"target_screen"}, "alarm_strip": {"view_policy"}, "alarm_table": {"view_policy"}, "alarm_history": {"view_policy"},
    "native_preserved": {"source_owner_sha256"},
    "native_presentation": {"source_owner_sha256", "presentation"},
    "native_integer_numeric": {"source_owner_sha256", "presentation", "integer_numeric", "entry_permission"},
    "native_entry_permission": {"source_owner_sha256", "presentation", "entry_permission"},
    "native_control_clone": {"source_owner_sha256", "clone"},
}


def _check_keys(obj, section, owner, error):
    for key in obj:
        if key not in IR_FIELDS[section]:
            error("UNKNOWN_PROPERTY", f"Unsupported {section} property {key!r}; it cannot be silently omitted", owner)


def _native_integer(value):
    if _integer(value):
        return 0 <= value <= 2147483647
    return isinstance(value, str) and bool(re.fullmatch(r"0|[1-9][0-9]{0,9}", value)) and int(value) <= 2147483647


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value):
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, float) and math.isfinite(value))


def _member(value, choices):
    return isinstance(value, str) and value in choices


def _identifier(value):
    return isinstance(value, str) and bool(value) and value.strip() == value


def validate_design(design, profile):
    """Return structured errors without mutating either input.

    A passing result is common-model validation only. Feature support remains
    tied to the exact supplied profile and evidence status.
    """
    issues = []

    def error(code, message, element_id=None):
        issue = {"severity": "error", "code": code, "message": message}
        if element_id is not None:
            issue["element_id"] = element_id
        issues.append(issue)

    if not isinstance(design, dict) or not isinstance(profile, dict):
        error("INVALID_DOCUMENT", "Design and profile must be JSON objects")
        return issues
    _check_keys(design, "document", None, error)
    if design.get("schema_version") != 1 or isinstance(design.get("schema_version"), bool):
        error("SCHEMA_VERSION", "Only design schema version 1 is supported")
    if not _identifier(design.get("project_id")):
        error("PROJECT_ID", "Project ID must be an exact nonempty string")
    if design.get("profile_id") != profile.get("id") or not _identifier(profile.get("id")):
        error("PROFILE_MISMATCH", "Design profile ID must exactly match the selected profile")
    resolution = profile.get("resolution")
    if not (isinstance(resolution, list) and len(resolution) == 2
            and all(_integer(v) and v > 0 for v in resolution)):
        error("PROFILE_RESOLUTION", "Profile resolution must contain two positive integers")
        resolution = None
    capabilities = profile.get("capabilities", {})
    if not isinstance(capabilities, dict):
        error("PROFILE_CAPABILITIES", "Profile capabilities must be an object")
        capabilities = {}

    def feature(name, owner=None):
        status = capabilities.get(name)
        if isinstance(status, dict):
            status = status.get("status")
        if name == "native_preserved" and status == "SYNTHETIC_ONLY" and profile.get("fixture_kind") == "synthetic":
            return True
        if not _member(status, SUPPORTED):
            error("FEATURE_UNSUPPORTED", f"Profile has no qualified support for {name}", owner)
            return False
        return True

    sections = {}
    identifiers = set()
    for name in ("screens", "tags", "macros", "alarms"):
        value = design.get(name)
        if not isinstance(value, list):
            error("SECTION_TYPE", f"{name} must be an explicit array")
            value = []
        sections[name] = value
    if not sections["screens"]:
        error("NO_SCREENS", "A validated design must contain at least one screen")

    def record_id(obj, kind):
        identifier = obj.get("id")
        if not _identifier(identifier):
            error("INVALID_ID", f"{kind} ID must be an exact nonempty string")
            return None
        if identifier in identifiers:
            error("DUPLICATE_ID", f"ID {identifier} is used more than once", identifier)
        identifiers.add(identifier)
        return identifier

    tags = {}
    addresses = set()
    numeric_types = profile.get("numeric_types", [])
    if not isinstance(numeric_types, list):
        error("PROFILE_NUMERIC_TYPES", "Profile numeric_types must be an array")
        numeric_types = []
    for tag in sections["tags"]:
        if not isinstance(tag, dict):
            error("TAG_TYPE", "Each tag must be an object")
            continue
        tid = record_id(tag, "Tag")
        _check_keys(tag, "tag", tid, error)
        if tid is not None:
            tags[tid] = tag
        address = tag.get("address")
        if not _identifier(address):
            error("TAG_ADDRESS", "Tag address must be an exact nonempty string", tid)
        else:
            # Identical addresses on distinct declared stations/channels are distinct.
            key = (str(tag.get("channel", "")), str(tag.get("station", "")), address)
            if key in addresses:
                error("DUPLICATE_ADDRESS", f"Address {address} is duplicated on its channel/station", tid)
            addresses.add(key)
        data_type = tag.get("data_type")
        if not _member(data_type, TYPES):
            error("TAG_DATA_TYPE", f"Unsupported tag data type {data_type}", tid)
        elif data_type != "BOOL" and data_type not in numeric_types:
            error("NUMERIC_TYPE_UNSUPPORTED", f"Profile does not support {data_type}; no type conversion is allowed", tid)
        if not _member(tag.get("access"), {"Read", "ReadWrite"}):
            error("TAG_ACCESS", "Tag access must be Read or ReadWrite", tid)
        for ordering in ("byte_order", "word_order"):
            if ordering in tag and not _identifier(tag[ordering]):
                error("TAG_ORDER", f"{ordering} must be explicitly named when supplied", tid)
        if "unit" in tag and not isinstance(tag["unit"], str):
            error("TAG_UNIT", "Tag unit must be a string", tid)
        for key in ("channel", "station"):
            if key in tag and not (_identifier(tag[key]) or _integer(tag[key]) and tag[key] >= 0):
                error("TAG_CONNECTION_ID", f"{key} must be an exact nonempty string or nonnegative integer", tid)
        if "native_binding" in tag:
            metadata = tag["native_binding"]
            if not isinstance(metadata, dict):
                error("NATIVE_BINDING_TYPE", "native_binding must be an object with explicit link and mem_type", tid)
            else:
                _check_keys(metadata, "native_binding", tid, error)
                if set(metadata) != IR_FIELDS["native_binding"]:
                    error("NATIVE_BINDING_FIELDS", "native_binding requires exactly link and mem_type", tid)
                for key in ("link", "mem_type"):
                    if not _native_integer(metadata.get(key)):
                        error("NATIVE_BINDING_VALUE", f"native_binding.{key} must be an integer or canonical integer string in 0..2147483647", tid)

    screen_ids = set()
    elements = []
    for screen in sections["screens"]:
        if not isinstance(screen, dict):
            error("SCREEN_TYPE", "Each screen must be an object")
            continue
        sid = record_id(screen, "Screen")
        _check_keys(screen, "screen", sid, error)
        if "native_id" in screen and not (isinstance(screen["native_id"], str) and _native_integer(screen["native_id"])):
            error("NATIVE_ID", "Native screen ID must be a canonical nonnegative integer string in 0..2147483647", sid)
        if sid is not None:
            screen_ids.add(sid)
        if not isinstance(screen.get("name"), str) or not screen.get("name"):
            error("SCREEN_NAME", "Screen name must be nonempty text", sid)
        size = (screen.get("width"), screen.get("height"))
        if not all(_integer(v) and v > 0 for v in size):
            error("SCREEN_GEOMETRY", "Screen dimensions must be positive integers", sid)
        elif resolution and list(size) != resolution:
            # Only this source-pinned stored-clone mode retains heterogeneous
            # source Doc canvases. Service checks pins against actual bytes;
            # this does not authorize arbitrary page resizing.
            schema = profile.get("native_schema", {})
            candidate = schema.get("native_candidate") if isinstance(schema, dict) else None
            descriptor = schema.get("diascreen_control_append") if isinstance(schema, dict) else None
            pages = descriptor.get("pages") if isinstance(descriptor, dict) else None
            pinned = [p for p in pages if isinstance(p, dict) and p.get("screen_id") == screen.get("native_id")] if isinstance(pages, list) else []
            if (profile.get("family") != "delta_diascreen" or not isinstance(candidate, dict)
                    or candidate.get("mode") != "diascreen_control_append" or len(pinned) != 1
                    or any(type(pinned[0].get(k)) is not int or pinned[0][k] <= 0 for k in ("doc_width", "doc_height"))
                    or list(size) != [pinned[0]["doc_width"], pinned[0]["doc_height"]]):
                error("RESOLUTION_MISMATCH", "Screen dimensions must match the profile or exact retained source canvas", sid)
        screen_elements = screen.get("elements")
        if "native_background" in screen:
            feature("native_background", sid)
            _validate_native_background(screen["native_background"], sid, error)
        if not isinstance(screen_elements, list):
            error("ELEMENTS_TYPE", "Screen elements must be an explicit array", sid)
            continue
        for element in screen_elements:
            if not isinstance(element, dict):
                error("ELEMENT_TYPE", "Each element must be an object", sid)
                continue
            eid = record_id(element, "Element")
            _check_keys(element, "element", eid, error)
            if "native_id" in element and not (isinstance(element["native_id"], str) and _native_integer(element["native_id"])):
                error("NATIVE_ID", "Native element ID must be a canonical nonnegative integer string in 0..2147483647", eid)
            elements.append((element, eid, screen))
            kind = element.get("kind")
            if not _member(kind, KINDS):
                error("ELEMENT_KIND", f"Unsupported element kind {kind}", eid)
            else:
                feature(kind, eid)
                for key in element:
                    if key in IR_FIELDS["element"] and key not in _BASE_ELEMENT | _KIND_FIELDS[kind]:
                        error("KIND_PROPERTY", f"Property {key} is not supported for {kind}; it cannot be silently omitted", eid)
            if _member(kind, {"native_preserved", "native_presentation", "native_integer_numeric", "native_entry_permission", "native_control_clone"}):
                fields = NATIVE_PRESERVED_FIELDS | ({"presentation"} if kind in {"native_presentation", "native_integer_numeric", "native_entry_permission"} else set())
                if kind == "native_integer_numeric":
                    fields |= {"integer_numeric"}
                    if "entry_permission" in element:
                        fields |= {"entry_permission"}
                elif kind == "native_entry_permission":
                    fields |= {"entry_permission"}
                elif kind == "native_control_clone":
                    fields |= {"clone"}
                missing = sorted(fields - element.keys())
                if missing:
                    error("NATIVE_PRESERVED_FIELDS", f"Source retention requires explicit fields: {', '.join(missing)}", eid)
                if not (isinstance(element.get("native_id"), str) and _native_integer(element["native_id"])):
                    error("NATIVE_PRESERVED_ID", "Source retention requires its existing canonical native ID", eid)
                fingerprint = element.get("source_owner_sha256")
                if not isinstance(fingerprint, str) or not SOURCE_OWNER_SHA.fullmatch(fingerprint):
                    error("NATIVE_PRESERVED_HASH", "Source retention requires an exact lowercase SHA-256 of its complete native owner", eid)
                if element.get("text") != "":
                    error("NATIVE_PRESERVED_TEXT", "Source-retained objects require explicit empty text; their native content is not modeled", eid)
                for key in element:
                    if key not in fields:
                        error("NATIVE_PRESERVED_PROPERTY", f"Source-retained objects cannot override or interpret {key}", eid)
                if kind in {"native_presentation", "native_integer_numeric", "native_entry_permission"}:
                    _validate_native_presentation(element.get("presentation"), eid, error)
                if kind == "native_integer_numeric":
                    _validate_existing_integer_numeric(element.get("integer_numeric"), eid, error)
                if kind == "native_control_clone":
                    _validate_control_clone(element.get("clone"), eid, error)
                if kind == "native_entry_permission" or kind == "native_integer_numeric" and "entry_permission" in element:
                    if kind != "native_entry_permission":
                        feature("native_entry_permission", eid)
                    _validate_entry_permission(element.get("entry_permission"), eid, error)
            if "view_policy" in element:
                if not _member(element["view_policy"], {"preserve_source"}):
                    error("ALARM_VIEW_POLICY", "Alarm view_policy must be the exact string preserve_source", eid)
                if _member(kind, ALARM_VIEWS):
                    # Presentation belongs to the source-native view. Even an
                    # empty override must not claim it was compiled or ignored.
                    if element.get("text") != "":
                        error("ALARM_VIEW_TEXT", "A source-preserved alarm view requires explicit empty text; use a separate text heading", eid)
                    allowed = {"id", "native_id", "kind", "x", "y", "width", "height", "text", "view_policy"}
                    for key in element:
                        if key in IR_FIELDS["element"] and key not in allowed:
                            error("ALARM_VIEW_PROPERTY", f"Source-preserved alarm view cannot override {key}", eid)
            geometry = [element.get(k) for k in ("x", "y", "width", "height")]
            if not all(_integer(v) for v in geometry) or not (
                    geometry[0] >= 0 and geometry[1] >= 0 and geometry[2] > 0 and geometry[3] > 0):
                error("ELEMENT_GEOMETRY", "Element x/y must be nonnegative integers and width/height positive integers", eid)
            elif all(_integer(v) and v > 0 for v in size) and (
                    geometry[0] + geometry[2] > size[0] or geometry[1] + geometry[3] > size[1]):
                error("ELEMENT_OUTSIDE_SCREEN", "Element must fit inside its screen", eid)
            if "font_size" in element and not (_integer(element["font_size"]) and 6 <= element["font_size"] <= 96):
                error("FONT_SIZE", "Font size must be an integer from 6 to 96", eid)
            for key in ("text", "unit"):
                if key in element and not isinstance(element[key], str):
                    error("ELEMENT_TEXT", f"{key} must be text", eid)
            for key in ("color", "fill"):
                if key in element and not (isinstance(element[key], str) and COLORS.fullmatch(element[key])):
                    error("ELEMENT_COLOR", f"{key} must be a hex color", eid)
            if "role" in element and not _member(element["role"], {"request", "feedback"}):
                error("ELEMENT_ROLE", "Element role must be request or feedback", eid)

        # Text has one owner. No duplicate background labels behind another object.
        for index, left in enumerate(screen_elements):
            if not isinstance(left, dict) or left.get("kind") != "text":
                continue
            for right in screen_elements[index + 1:]:
                if not isinstance(right, dict):
                    continue
                if _overlap(left, right):
                    error("TEXT_OVERLAP", f"Text {left.get('id')} overlaps {right.get('id')}; move its single owner", left.get("id"))
        # Also detect text appearing later in document order.
        for index, left in enumerate(screen_elements):
            if not isinstance(left, dict) or left.get("kind") == "text":
                continue
            for right in screen_elements[index + 1:]:
                if isinstance(right, dict) and right.get("kind") == "text" and _overlap(left, right):
                    error("TEXT_OVERLAP", f"Text {right.get('id')} overlaps {left.get('id')}; move its single owner", right.get("id"))

    for element, eid, _ in elements:
        if _member(element.get("kind"), ALARM_VIEWS) and not sections["alarms"]:
            error("ALARM_VIEW_ALARMS", "An alarm view requires at least one explicitly declared alarm", eid)

    _validate_unit_labels(elements, tags, error)

    command_tags = set()
    for element, eid, screen in elements:
        if _member(element.get("kind"), {"native_preserved", "native_presentation", "native_integer_numeric", "native_entry_permission", "native_control_clone"}):
            # Retention has no common-model command, sample or navigation
            # semantics. Forbidden fields were rejected above, not projected.
            continue
        binding = element.get("binding", {})
        if not isinstance(binding, dict):
            error("BINDING_TYPE", "Binding must be an object", eid)
            binding = {}
        _check_keys(binding, "binding", eid, error)
        for direction in ("read", "write"):
            reference = binding.get(direction)
            if reference is not None and (not isinstance(reference, str) or reference not in tags):
                error("UNKNOWN_TAG", f"{direction} must reference an exact existing tag ID", eid)
            elif direction == "write" and reference is not None:
                if tags[reference].get("access") != "ReadWrite":
                    error("READ_ONLY_WRITE", f"Cannot write read-only tag {reference}", eid)
                command_tags.add(reference)
        read = tags.get(binding.get("read")) if isinstance(binding.get("read"), str) else None
        write = tags.get(binding.get("write")) if isinstance(binding.get("write"), str) else None
        kind = element.get("kind")
        if kind == "button":
            if not write or write.get("data_type") != "BOOL":
                error("BUTTON_BOOL_WRITE", "Buttons require an explicit writable BOOL binding", eid)
            if read and read.get("data_type") != "BOOL":
                error("BUTTON_BOOL_READ", "Button read binding must be BOOL", eid)
            if element.get("role") == "feedback":
                error("COMMAND_AS_FEEDBACK", "A command button cannot claim physical feedback", eid)
            behavior = element.get("behavior")
            if not _member(behavior, {"momentary", "maintained", "set_on", "set_off"}):
                error("BUTTON_BEHAVIOR", "Button behavior must be explicit", eid)
            if behavior == "maintained":
                if not read:
                    error("MAINTAINED_READ", "Maintained buttons require a BOOL read binding", eid)
            if behavior == "maintained" or "states" in element:
                _validate_states(element, eid, error)
        if kind == "indicator":
            if not read or read.get("data_type") != "BOOL":
                error("INDICATOR_BOOL_READ", "Indicators require an explicit BOOL read binding", eid)
            if binding.get("write") is not None:
                error("INDICATOR_WRITE", "An indicator cannot issue a command", eid)
            if not _member(element.get("role"), {"request", "feedback"}):
                error("INDICATOR_ROLE", "Indicator must explicitly identify request state or independent feedback", eid)
            _validate_states(element, eid, error)
        if _member(kind, {"numeric_input", "numeric_display"}):
            if element.get("value_model") == FIXED_MODEL:
                feature("numeric_value_model:" + FIXED_MODEL, eid)
            numeric_tag = write if kind == "numeric_input" else read
            if not numeric_tag or not _member(numeric_tag.get("data_type"), NUMERIC):
                error("NUMERIC_BINDING", f"{kind} requires an explicit numeric {'write' if kind == 'numeric_input' else 'read'} binding", eid)
            else:
                _validate_numeric(element, numeric_tag, eid, error)
            if read and numeric_tag and read.get("data_type") != numeric_tag.get("data_type"):
                error("NUMERIC_TYPE_MISMATCH", "Numeric read/write types must match exactly", eid)
            if kind == "numeric_input":
                if not read:
                    error("NUMERIC_INPUT_READ", "Numeric input requires an explicit read sample binding", eid)
                elif write:
                    if read.get("unit", "") != write.get("unit", ""):
                        error("NUMERIC_UNIT_MISMATCH", "Numeric input read/write units must match exactly; V1 performs no conversion", eid)
                    if binding.get("read") != binding.get("write"):
                        error("NUMERIC_PROCESS_MISMATCH", "V1 numeric input read/write bindings must identify the same logical process tag", eid)
            if numeric_tag and element.get("unit", numeric_tag.get("unit", "")) != numeric_tag.get("unit", ""):
                error("UNIT_MISMATCH", "Element and bound tag units must match exactly", eid)
            if kind == "numeric_display" and binding.get("write") is not None:
                error("DISPLAY_WRITE", "A numeric display cannot issue a command", eid)
        if kind == "goto":
            if not isinstance(element.get("target_screen"), str) or element.get("target_screen") not in screen_ids:
                error("NAVIGATION_TARGET", "Navigation must target an exact existing screen ID", eid)
            if binding.get("write") is not None:
                error("NAVIGATION_WRITE", "Navigation cannot issue a controller command", eid)

    # Macro writes are command state too, even when no button owns that tag.
    def macro_commands(statements, depth=0):
        if depth > 16 or not isinstance(statements, list):
            return
        for statement in statements:
            if not isinstance(statement, dict):
                continue
            if statement.get("op") in ("assign", "bit_on", "bit_off") and isinstance(statement.get("tag"), str):
                command_tags.add(statement["tag"])
            if statement.get("op") == "if":
                macro_commands(statement.get("then"), depth + 1)
                macro_commands(statement.get("else"), depth + 1)
    for macro in sections["macros"]:
        if isinstance(macro, dict):
            macro_commands(macro.get("statements"))
    for element, eid, _ in elements:
        binding = element.get("binding", {})
        if isinstance(binding, dict) and element.get("role") == "feedback" and isinstance(binding.get("read"), str) and binding.get("read") in command_tags:
            error("COMMAND_AS_FEEDBACK", "Command state cannot be presented as independent physical feedback", eid)

    for macro in sections["macros"]:
        if not isinstance(macro, dict):
            error("MACRO_TYPE", "Each macro must be an object")
            continue
        mid = record_id(macro, "Macro")
        _check_keys(macro, "macro", mid, error)
        feature("macros", mid)
        trigger = macro.get("trigger")
        if not _member(trigger, {"startup", "clock", "button"}):
            error("MACRO_TRIGGER", "Unsupported macro trigger", mid)
        else:
            feature("macro_trigger:" + trigger, mid)
        _validate_statements(macro.get("statements"), tags, mid, error, feature)

    for alarm in sections["alarms"]:
        if not isinstance(alarm, dict):
            error("ALARM_TYPE", "Each alarm must be an object")
            continue
        aid = record_id(alarm, "Alarm")
        _check_keys(alarm, "alarm", aid, error)
        feature("alarms", aid)
        tag = tags.get(alarm.get("tag")) if isinstance(alarm.get("tag"), str) else None
        if not tag or tag.get("data_type") != "BOOL":
            error("ALARM_BOOL_TAG", "Alarm must reference an existing BOOL tag", aid)
        if not isinstance(alarm.get("text"), str) or not alarm["text"]:
            error("ALARM_TEXT", "Alarm text must be nonempty", aid)
        if not _member(alarm.get("history_policy"), {"retain", "clear", "preserve_source"}):
            error("ALARM_HISTORY_POLICY", "Alarm history_policy must explicitly be retain, clear or preserve_source", aid)
    return issues


def _validate_control_clone(value, owner, error):
    if not isinstance(value, dict) or set(value) != {"donor_kind", "captions"}:
        error("NATIVE_CLONE_FIELDS", "Source clone requires exactly donor_kind and captions", owner)
        return
    kind = value["donor_kind"]
    if not _member(kind, {"maintained", "momentary", "numeric_input", "numeric_display"}):
        error("NATIVE_CLONE_KIND", "No source-clone contract exists for this donor kind", owner)
        return
    captions = value["captions"]
    expected = [0, 1] if kind in {"maintained", "momentary"} else []
    if (not isinstance(captions, list) or len(captions) != len(expected)
            or any(not isinstance(caption, dict) or set(caption) != {"value", "text"}
                   or not _integer(caption.get("value")) or caption["value"] != number
                   or not isinstance(caption.get("text"), str)
                   or len(caption["text"]) > 1000 or "\0" in caption["text"]
                   or any(0xD800 <= ord(c) <= 0xDFFF for c in caption["text"])
                   for caption, number in zip(captions, expected))):
        error("NATIVE_CLONE_CAPTIONS", "Buttons require ordered primary 0/1 captions; numeric clones require none", owner)


def _validate_native_background(value, owner, error):
    if not isinstance(value, dict) or set(value) != {"frame_sha256", "asset_path", "asset_sha256"}:
        error("NATIVE_BACKGROUND_FIELDS", "Background requires exact source frame and relative PNG asset pins", owner)
        return
    for key in ("frame_sha256", "asset_sha256"):
        if not isinstance(value[key], str) or not SOURCE_OWNER_SHA.fullmatch(value[key]):
            error("NATIVE_BACKGROUND_HASH", "Background fingerprints require canonical SHA-256", owner)
    path = value["asset_path"]
    if (not _identifier(path) or len(path) > 1024 or path.startswith(("/", "\\"))
            or ":" in path or "\0" in path or ".." in path.replace("\\", "/").split("/")):
        error("NATIVE_BACKGROUND_PATH", "PNG asset must be a bounded relative workspace path", owner)


def _validate_native_presentation(value, owner, error):
    if not isinstance(value, dict) or set(value) - {"visual", "states"}:
        error("NATIVE_PRESENTATION_FIELDS", "Presentation requires explicit native visual or state fields", owner)
        return
    if "visual" in value:
        visual = value["visual"]
        if not isinstance(visual, dict) or not visual or set(visual) - {"native_style", "border_color"}:
            error("NATIVE_PRESENTATION_VISUAL", "Visual requires qualified native style or COLORREF border", owner)
        else:
            for key, number in visual.items():
                if not _integer(number) or not 0 <= number <= (3 if key == "native_style" else 0xFFFFFF):
                    error("NATIVE_PRESENTATION_VALUE", "Native style/COLORREF must fit its exact integer domain", owner)
    if "states" in value:
        states = value["states"]
        if not isinstance(states, list) or not states or len(states) > 256:
            error("NATIVE_PRESENTATION_STATES", "Presentation states require a bounded nonempty list", owner)
            return
        seen = set()
        allowed = {"value", "state_sha256", "font_size", "font_ratio", "font_color", "surface_color"}
        for state in states:
            if (not isinstance(state, dict) or not {"value", "state_sha256"} < set(state)
                    or set(state) - allowed):
                error("NATIVE_PRESENTATION_STATE", "Native state requires its original value/hash and requested scalar fields", owner)
                continue
            number = state["value"]
            if not isinstance(number, str) or not re.fullmatch(r"0|[1-9][0-9]{0,9}", number):
                error("NATIVE_PRESENTATION_STATE", "Native state value must be a canonical source string", owner)
            elif number in seen:
                error("NATIVE_PRESENTATION_STATE", "Native state values cannot repeat", owner)
            else:
                seen.add(number)
            if not isinstance(state["state_sha256"], str) or not SOURCE_OWNER_SHA.fullmatch(state["state_sha256"]):
                error("NATIVE_PRESENTATION_HASH", "Native state requires its complete original section SHA", owner)
            for key in state.keys() - {"value", "state_sha256"}:
                number = state[key]
                valid = _integer(number)
                if key == "font_size":
                    valid = valid and number in {8,10,12,14,16,18,20,22,24,28,32,36,40,48,64,72}
                elif key == "font_ratio":
                    valid = valid and number in {33,50,100,150,200}
                else:
                    valid = valid and 0 <= number <= 0xFFFFFF
                if not valid:
                    error("NATIVE_PRESENTATION_VALUE", "Native state scalar is outside the explicit qualified domain", owner)


def _validate_entry_permission(value, owner, error):
    """Stored entry-only intent, never namespace/action/runtime qualification."""
    fields = {"permission_address", "enable_level", "action_classification_sha256"}
    if not isinstance(value, dict) or set(value) != fields:
        error("ENTRY_PERMISSION_FIELDS", "Entry permission requires its exact address, 0/1 level and action artifact SHA", owner)
        return
    address = value["permission_address"]
    # This is syntax only: source-native link, BOOL/read direction, area radix
    # and bounds are checked against a separately pinned namespace by emission.
    if (not isinstance(address, str) or len(address) > 64
            or re.fullmatch(r"\{Link[1-9][0-9]{0,3}\}(?:0|[1-9][0-9]{0,3})@[A-Z]{1,8}(?:0|[1-9][0-9]{0,10})", address) is None):
        error("ENTRY_PERMISSION_ADDRESS", "Permission address must be a bounded canonical ASCII external native address", owner)
    level = value["enable_level"]
    if not _integer(level) or level not in {0, 1}:
        error("ENTRY_PERMISSION_LEVEL", "Enable level must be the exact integer 0 or 1", owner)
    fingerprint = value["action_classification_sha256"]
    if not isinstance(fingerprint, str) or SOURCE_OWNER_SHA.fullmatch(fingerprint) is None:
        error("ENTRY_PERMISSION_ACTION_HASH", "Entry permission requires the lowercase SHA-256 of its project-owned action classification artifact", owner)


def _validate_existing_integer_numeric(value, owner, error):
    """Intent-only WORD settings; native owner kind and source are separate gates."""
    required = {"data_type", "value_model", "integer_digits", "fractional_digits"}
    optional = {"raw_minimum", "raw_maximum"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        error("EXISTING_INTEGER_NUMERIC_FIELDS", "Existing integer numeric settings require exact explicit fields", owner)
        return
    dtype = value["data_type"]
    if not _member(dtype, {"INT", "UINT"}) or value["value_model"] != FIXED_MODEL:
        error("EXISTING_INTEGER_NUMERIC_TYPE", "Existing WORD settings require INT/UINT and explicit integer_fixed_decimal", owner)
    integer, fractional = value["integer_digits"], value["fractional_digits"]
    if not _integer(integer) or not 1 <= integer <= 5 or not _integer(fractional) or not 0 <= fractional <= 4:
        error("EXISTING_INTEGER_NUMERIC_DIGITS", "Existing WORD digits require I1..5/F0..4", owner)
    elif integer + fractional > 5 or dtype == "INT" and fractional not in {0, 1, 4}:
        error("EXISTING_INTEGER_NUMERIC_DIGITS", "Requested digits exceed the bounded WORD presentation contract", owner)
    if optional & set(value):
        if not optional <= set(value):
            error("EXISTING_INTEGER_NUMERIC_LIMIT", "Raw keypad limits must be supplied as one complete pair", owner)
            return
        if fractional != 0:
            error("EXISTING_INTEGER_NUMERIC_INPUT", "Fractional WORD keypad limits are unqualified", owner)
        low, high = value["raw_minimum"], value["raw_maximum"]
        limits = INTEGER_RANGES.get(dtype) if isinstance(dtype, str) else None
        if (not _integer(low) or not _integer(high) or not limits or not limits[0] <= low < high <= limits[1]):
            error("EXISTING_INTEGER_NUMERIC_LIMIT", "Raw input limits require increasing exact WORD integers", owner)
        elif _integer(integer) and integer < max(len(str(abs(low))), len(str(abs(high)))):
            error("EXISTING_INTEGER_NUMERIC_DIGITS", "Input digits cannot display the declared raw bounds", owner)
    elif _integer(integer) and _integer(fractional) and integer != 5 - fractional:
        error("EXISTING_INTEGER_NUMERIC_DIGITS", "Display digits must cover the complete WORD domain", owner)


def _validate_unit_labels(elements, tags, error):
    """Validate explicit single ownership without inferring unit placement.

    A valid relation is numeric -> literal text, so cycles and chains cannot
    occur. Native embedded-unit suppression is a separate emitter contract.
    """
    by_id = {}
    for element, eid, screen in elements:
        if eid is not None:
            by_id.setdefault(eid, []).append((element, screen))
    owners = {}
    for element, eid, screen in elements:
        if not _member(element.get("kind"), {"numeric_input", "numeric_display"}) or "unit_label" not in element:
            continue
        reference = element["unit_label"]
        if not _identifier(reference):
            error("UNIT_LABEL_REFERENCE", "unit_label must be an exact nonempty element ID", eid)
            continue
        owners.setdefault(reference, []).append(eid)
        if reference == eid:
            error("UNIT_LABEL_REFERENCE", "A numeric element cannot own itself as its unit label", eid)
            continue
        candidates = by_id.get(reference, [])
        if len(candidates) != 1:
            error("UNIT_LABEL_REFERENCE", "unit_label must reference exactly one existing element", eid)
            continue
        label, label_screen = candidates[0]
        if label_screen is not screen:
            error("UNIT_LABEL_SCREEN", "Unit label must belong to the same screen as its numeric owner", eid)
        if label.get("kind") != "text":
            error("UNIT_LABEL_KIND", "Unit label must be a separately declared literal text element", eid)
        if "binding" in label or "unit_label" in label:
            error("UNIT_LABEL_BINDING", "Unit label cannot carry a binding or another unit_label reference", eid)
        required = {"x", "y", "width", "height", "font_size", "color", "fill"}
        missing = sorted(required - label.keys())
        if missing:
            error("UNIT_LABEL_STYLE", f"Unit label requires explicit geometry and style: {', '.join(missing)}", eid)
        unit = element.get("unit")
        if not isinstance(unit, str) or not unit.strip():
            error("UNIT_LABEL_UNIT", "Numeric owner requires an explicit nonempty unit when unit_label is supplied", eid)
        else:
            binding = element.get("binding", {})
            binding = binding if isinstance(binding, dict) else {}
            direction = "write" if element["kind"] == "numeric_input" else "read"
            tag_id = binding.get(direction)
            tag = tags.get(tag_id) if isinstance(tag_id, str) else None
            if not tag or unit != tag.get("unit", ""):
                error("UNIT_LABEL_UNIT", "Unit label owner and bound tag units must match exactly", eid)
            if label.get("text") != unit:
                error("UNIT_LABEL_TEXT", "Unit label literal text must exactly match its numeric owner's unit", eid)
    for reference, numeric_owners in owners.items():
        if len(numeric_owners) > 1:
            for eid in numeric_owners:
                error("UNIT_LABEL_OWNER", f"Unit label {reference} must have exactly one numeric owner", eid)


def _overlap(left, right):
    a = [left.get(k) for k in ("x", "y", "width", "height")]
    b = [right.get(k) for k in ("x", "y", "width", "height")]
    if not all(_integer(v) for v in a + b) or min(a[2:]+b[2:]) <= 0:
        return False
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _validate_states(element, eid, error):
    states = element.get("states")
    if not isinstance(states, list) or len(states) != 2 or not all(isinstance(s, dict) for s in states):
        error("BOOL_STATES", "Boolean state objects must explicitly define 0 and 1", eid)
        return
    values = [s.get("value") for s in states]
    if not all(_integer(v) for v in values) or sorted(values) != [0, 1]:
        error("BOOL_STATES", "Boolean state values must be exactly integers 0 and 1", eid)
    for state in states:
        _check_keys(state, "state", eid, error)
        if not isinstance(state.get("text"), str) or not state.get("text"):
            error("STATE_TEXT", "Every boolean state requires explicit text", eid)
        if not isinstance(state.get("fill"), str) or not COLORS.fullmatch(state["fill"]):
            error("STATE_FILL", "Every boolean state requires a hex fill color", eid)
    if all(isinstance(state.get("text"), str) and isinstance(state.get("fill"), str) and COLORS.fullmatch(state["fill"]) for state in states):
        def normalized_fill(value):
            value = value.lower()[1:]
            if len(value) == 3:
                value = "".join(char * 2 for char in value)
            return value + "ff" if len(value) == 6 else value
        text = [" ".join(state["text"].split()).casefold() for state in states]
        fills = [normalized_fill(state["fill"]) for state in states]
        if text[0] == text[1] and fills[0] == fills[1]:
            error("BOOL_STATE_AMBIGUOUS", "Boolean 0/1 states require distinct text or fill to remain distinguishable", eid)


def _validate_numeric(element, tag, eid, error):
    data_type = tag["data_type"]
    low, high, precision = NUMERIC[data_type]
    fractional = element.get("fractional", 0)
    model = element.get("value_model", "raw")
    fixed = isinstance(model, str) and model == FIXED_MODEL
    if not _member(model, {"raw", FIXED_MODEL}):
        error("NUMERIC_VALUE_MODEL", "Numeric value model must be raw or explicit integer_fixed_decimal", eid)
    if fixed and data_type not in INTEGER_RANGES:
        error("NUMERIC_VALUE_MODEL", "Fixed decimal requires integer storage; TIME/floating conversion is forbidden", eid)
    maximum_precision = MAX_FRACTIONAL if fixed and data_type in INTEGER_RANGES else precision
    if not _integer(fractional) or not 0 <= fractional <= maximum_precision:
        message = (f"Explicit fixed decimal exponent must be 0..{maximum_precision}" if fixed
                   else f"{data_type} fractional digits must be 0..{precision}; integer and TIME types cannot be fractional")
        error("NUMERIC_PRECISION", message, eid)
    for key in ("minimum", "maximum"):
        if key not in element:
            if element.get("kind") == "numeric_input":
                error("NUMERIC_LIMIT_REQUIRED", f"Numeric input requires explicit {key}", eid)
            continue
        value = element[key]
        if not _number(value) or not low <= value <= high or (precision == 0 and not _integer(value)):
            error("NUMERIC_LIMIT", f"{key} must fit exact {data_type} limits and type", eid)
    if _number(element.get("minimum")) and _number(element.get("maximum")) and element["minimum"] > element["maximum"]:
        error("NUMERIC_LIMIT_ORDER", "Minimum must be less than or equal to maximum", eid)
    if element.get("format", "decimal") != "decimal":
        error("NUMERIC_FORMAT", "V1 common model supports only explicit decimal formatting", eid)


def _validate_statements(statements, tags, mid, error, feature, depth=0):
    if depth > 16:
        error("MACRO_DEPTH", "Macro nesting exceeds the supported limit", mid)
        return
    if not isinstance(statements, list) or not statements:
        error("MACRO_STATEMENTS", "Macro statements must be a nonempty array", mid)
        return
    for statement in statements:
        if not isinstance(statement, dict):
            error("MACRO_STATEMENT", "Macro statement must be an object", mid)
            continue
        _check_keys(statement, "statement", mid, error)
        op = statement.get("op")
        if not _member(op, {"assign", "bit_on", "bit_off", "if"}):
            error("MACRO_OP", f"Unsupported macro operation {op}", mid)
            continue
        allowed = {"op", "tag", "value", "comparison", "then", "else"} if op == "if" else ({"op", "tag", "value"} if op == "assign" else {"op", "tag"})
        for key in statement:
            if key in IR_FIELDS["statement"] and key not in allowed:
                error("STATEMENT_PROPERTY", f"Property {key} is not supported for macro operation {op}", mid)
        feature("macro_op:" + op, mid)
        tag = tags.get(statement.get("tag")) if isinstance(statement.get("tag"), str) else None
        if not tag:
            error("MACRO_TAG", "Macro operation requires an exact existing tag ID", mid)
            continue
        if op == "if":
            if not _member(statement.get("comparison", "eq"), {"eq", "ne", "lt", "le", "gt", "ge"}):
                error("MACRO_COMPARISON", "Unsupported if comparison", mid)
            if not _value_matches(statement.get("value"), tag.get("data_type")):
                error("MACRO_VALUE", "If comparison value must fit the exact tag type", mid)
            _validate_statements(statement.get("then"), tags, mid, error, feature, depth + 1)
            if "else" in statement and statement["else"] != []:
                _validate_statements(statement["else"], tags, mid, error, feature, depth + 1)
        else:
            if tag.get("access") != "ReadWrite":
                error("MACRO_READ_ONLY_WRITE", "Macro cannot write a read-only tag", mid)
            if op in {"bit_on", "bit_off"} and tag.get("data_type") != "BOOL":
                error("MACRO_BIT_TYPE", "Bit operations require BOOL", mid)
            if op == "assign" and not _value_matches(statement.get("value"), tag.get("data_type")):
                error("MACRO_VALUE", "Assignment value must fit the exact tag type", mid)


def _value_matches(value, data_type):
    if data_type == "BOOL":
        return _integer(value) and value in (0, 1)
    if not _member(data_type, NUMERIC) or not _number(value):
        return False
    low, high, precision = NUMERIC[data_type]
    return low <= value <= high and (precision > 0 or _integer(value))
