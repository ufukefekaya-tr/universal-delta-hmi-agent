"""Explicit source-qualified UINT16 to INT16/F0 clone transformation.

Only the native format byte changes. The original source remains unsigned;
this is a primary-static reader/writer/compiler contract, not a fabricated
signed donor, vendor compilation or runtime/physical acceptance.
"""
import hashlib
import re

from ..errors import HmiError
from .identity import canonical_model_id
from .numeric import configure_numeric, verify_numeric_fields, fixed_decimal_contract, _number


_SHA = re.compile(r"[0-9a-f]{64}")
_INTEGER = re.compile(r"0|[1-9][0-9]*|-[1-9][0-9]*")
_PREFIX = re.compile(r"\{Link[1-9][0-9]{0,3}\}(?:0|[1-9][0-9]{0,3})@")
_MODE = "source_uint16_to_int16_f0"
_UINT = {"MemLen": "1", "MemFmt": "2", "bits": 16, "format": "unsigned"}
_INT = {"MemLen": "1", "MemFmt": "1", "bits": 16, "format": "signed"}
_KINDS = {"numeric_input": {"Type": "6", "SubType": "1"},
          "numeric_display": {"Type": "5", "SubType": "1"}}


def _fingerprint(value):
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _mapping(actual, expected):
    return (isinstance(actual, dict) and set(actual) == set(expected)
            and all(type(actual.get(key)) is type(value) and actual[key] == value
                    for key, value in expected.items()))


def storage_contract(schema):
    """Bounded optional descriptor; external authority is checked by service."""
    if not isinstance(schema, dict):
        raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Storage conversion schema must be an object")
    if "storage_conversion" not in schema:
        return None
    spec = schema["storage_conversion"]
    keys = {"qualified", "contract_version", "mode", "source_sha256", "authority_sha256",
            "input_donor_sha256", "display_donor_sha256", "review_reference"}
    if (schema.get("qualified") is not True or not isinstance(spec, dict) or set(spec) != keys
            or spec.get("qualified") is not True or type(spec.get("contract_version")) is not int
            or spec["contract_version"] != 1 or spec.get("mode") != _MODE):
        raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Storage conversion requires its exact bounded source contract")
    for field in ("source_sha256", "authority_sha256", "input_donor_sha256", "display_donor_sha256"):
        if not _fingerprint(spec.get(field)):
            raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Storage conversion provenance requires canonical SHA-256", field=field)
    review = spec.get("review_reference")
    if (not isinstance(review, str) or not 1 <= len(review) <= 256 or review != review.strip()
            or len(review.splitlines()) != 1 or any(ord(char) < 32 or ord(char) == 127 for char in review)):
        raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Storage review reference must be bounded single-line text")
    generation = schema.get("control_generation")
    donors = generation.get("donors") if isinstance(generation, dict) else None
    if (not isinstance(generation, dict) or generation.get("qualified") is not True
            or type(generation.get("contract_version")) is not int or generation["contract_version"] != 1
            or generation.get("mode") != "control_generation"
            or generation.get("source_sha256") != spec["source_sha256"]
            or not isinstance(generation.get("address_prefix"), str)
            or _PREFIX.fullmatch(generation["address_prefix"]) is None or not isinstance(donors, dict)):
        raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Storage conversion must use the immutable unsigned control library")
    for kind, field in (("numeric_input", "input_donor_sha256"), ("numeric_display", "display_donor_sha256")):
        donor = donors.get(kind)
        if not isinstance(donor, dict) or donor.get("owner_sha256") != spec[field]:
            raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Storage conversion donor pin differs from the original unsigned owner", kind=kind)
    numeric = schema.get("numeric")
    types = numeric.get("types") if isinstance(numeric, dict) else None
    kinds = numeric.get("kinds") if isinstance(numeric, dict) else None
    if (not isinstance(numeric, dict) or numeric.get("qualified") is not True
            or not isinstance(types, dict) or set(types) != {"UINT", "INT"}
            or not _mapping(types.get("UINT"), _UINT) or not _mapping(types.get("INT"), _INT)
            or not isinstance(kinds, dict) or set(kinds) != set(_KINDS)
            or any(not _mapping(kinds.get(kind), value) for kind, value in _KINDS.items())
            or type(numeric.get("max_integer_digits")) is not int or numeric["max_integer_digits"] != 5):
        raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Storage contract admits only exact UINT16 and INT16 numeric mappings")
    maximum = numeric.get("max_fractional_digits")
    if type(maximum) is not int or maximum not in {0, 4}:
        raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Storage conversion cannot widen fractional numeric support")
    if maximum == 4:
        fixed = fixed_decimal_contract(schema)
        if fixed["source_sha256"] != spec["source_sha256"]:
            raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Unsigned fixed-display descriptor differs from the storage source")
    elif "value_models" in numeric:
        raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Fixed-display descriptor requires its separately qualified unsigned digit range")
    # Every descriptor value is a bounded primitive; no recursive copy occurs.
    return dict(spec)


def validate_source(adapter, schema):
    """Validate the real unsigned source, never a generated signed witness."""
    from . import NativeAdapter, _screen, _element
    spec = storage_contract(schema)
    if spec is None:
        return None
    if not isinstance(adapter, NativeAdapter):
        raise HmiError("INVALID_STORAGE_SOURCE", "Storage conversion requires a native unsigned source")
    adapter._preserved_byte_binding("INVALID_STORAGE_SOURCE")
    adapter._control_prefix_length(adapter)
    if (adapter.family != "delta_dopsoft2" or canonical_model_id(adapter.model_id) != 2953863504
            or adapter.editor_version != "4.00.07.04"
            or hashlib.sha256(adapter.original).hexdigest() != spec["source_sha256"]):
        raise HmiError("INVALID_STORAGE_SOURCE", "Static storage contract requires its exact DOP-B model, raw editor version and source bytes")
    generation = schema["control_generation"]
    prefix = generation.get("address_prefix")
    for kind, field in (("numeric_input", "input_donor_sha256"), ("numeric_display", "display_donor_sha256")):
        pin = generation["donors"][kind]
        page = _screen(adapter.document, pin.get("screen_id"))
        owner = _element(page, pin.get("element_id"))
        if adapter.owner_extent_sha256(page["id"], owner["id"]) != spec[field]:
            raise HmiError("INVALID_STORAGE_SOURCE", "Original unsigned owner differs from its immutable raw pin", kind=kind)
        # Full source owner/state/disabled-field guard remains unchanged.
        adapter._control_owner(page, owner, kind, prefix, schema, bound=False)
        if (owner["section"].one("MemLen").value != b"1"
                or owner["section"].one("MemFmt").value != b"2"):
            raise HmiError("INVALID_STORAGE_SOURCE", "Storage source must remain the actual UINT16 donor")
    return True


def _element_guard(section, schema, native_format):
    from . import NativeAdapter, _CONTROL_COMMON, _CONTROL_INPUT, _CONTROL_DISPLAY, _value
    if storage_contract(schema) is None:
        raise HmiError("UNQUALIFIED_STORAGE_CONVERSION", "Signed storage requires its explicit separate transformation contract")
    # Section.one/check_unique errors are the existing typed native contract.
    if not hasattr(section, "one"):
        raise HmiError("INVALID_STORAGE_OWNER", "Storage conversion requires a native numeric Element")
    pair = tuple(_value(section, field) for field in ("Type", "SubType"))
    kind = "numeric_input" if pair == ("6", "1") else "numeric_display" if pair == ("5", "1") else None
    if kind is None:
        raise HmiError("STORAGE_CONVERSION_SCOPE", "Only the witnessed numeric input/display clone can change signed representation")
    fields = _CONTROL_COMMON | (_CONTROL_INPUT if kind == "numeric_input" else _CONTROL_DISPLAY)
    NativeAdapter._control_shape(section, fields)
    NativeAdapter._literal_zero(section, {"GroupID", "PrintSuccessiveData", "Level", "OffsetReadMemType",
        "OffsetWriteMemType", "nAngle", "bFreeze", "Roundoff", "LeadingZero", "Variation", "FastRefresh",
        "Active", "UseCustKeypad", "KeypadScreenID", "SetLowSecurity", "ConFirmWindow", "NoMessage", "DispAsterisk"} & fields)
    for field in {"OffsetReadVar", "OffsetWriteVar", "VisibleVar", "InterLockVar", "TriggerVar"} & fields:
        if _value(section, field) != "None":
            raise HmiError("STORAGE_CONVERSION_SCOPE", "Storage conversion cannot acquire a disabled conditional address", field=field)
    if (section.one("MemLen").value != b"1" or section.one("MemFmt").value != native_format.encode("ascii")
            or section.one("DotNum").value != b"0"):
        raise HmiError("STORAGE_CONVERSION_STATE", "Storage conversion requires the exact WORD representation and zero fractional digits")
    if (_number(_value(section, "GainValue"), "GainValue") != 1
            or _number(_value(section, "OffsetValue"), "OffsetValue") != 0):
        raise HmiError("UNQUALIFIED_SCALING", "Storage conversion cannot change or repair nonidentity scaling")
    return kind


def convert_storage(section, operation, schema):
    """Change ONLY MemFmt 2 to 1 on an explicitly fresh clone owned by caller."""
    keys = {"op", "screen_id", "element_id", "data_type"}
    if (not isinstance(operation, dict) or set(operation) != keys
            or operation.get("op") != "convert_numeric_storage" or operation.get("data_type") != "INT"):
        raise HmiError("INVALID_STORAGE_OPERATION", "Storage conversion requires its explicit exact INT clone operation")
    _element_guard(section, schema, "2")
    section.one("MemFmt").set_value(b"1")


def _integral(value, field):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and len(value) <= 6 and _INTEGER.fullmatch(value):
        number = int(value)
    else:
        raise HmiError("STORAGE_CONVERSION_LIMIT", "Signed F0 input requires canonical integral bounds", field=field)
    if not -32768 <= number <= 32767:
        raise HmiError("STORAGE_CONVERSION_LIMIT", "Signed input limit exceeds its exact INT16 representation", field=field)
    return number


def _signed_settings(operation, kind):
    allowed = {"op", "screen_id", "element_id", "kind", "data_type", "integer_digits", "fractional_digits",
               "gain", "offset", "minimum", "maximum"}
    if (not isinstance(operation, dict) or set(operation) - allowed or operation.get("kind") != kind
            or operation.get("data_type") != "INT" or type(operation.get("fractional_digits")) is not int
            or operation["fractional_digits"] != 0 or type(operation.get("integer_digits")) is not int
            or not 1 <= operation["integer_digits"] <= 5
            or ("op" in operation and operation["op"] != "configure_numeric")):
        raise HmiError("UNQUALIFIED_STORAGE_NUMERIC", "Converted INT16 supports only explicit raw F0 numeric settings")
    if _number(operation.get("gain"), "gain") != 1 or _number(operation.get("offset"), "offset") != 0:
        raise HmiError("UNQUALIFIED_SCALING", "Converted INT16 retains identity scaling")
    if kind == "numeric_input":
        minimum, maximum = _integral(operation.get("minimum"), "minimum"), _integral(operation.get("maximum"), "maximum")
        if minimum >= maximum:
            raise HmiError("STORAGE_CONVERSION_LIMIT", "Signed input requires strictly increasing limits")
        digits = max(1, len(str(abs(minimum))), len(str(abs(maximum))))
        if operation["integer_digits"] < digits:
            raise HmiError("NUMERIC_DIGITS", "Signed input digit count cannot display its declared bounds")
    elif "minimum" in operation or "maximum" in operation:
        raise HmiError("INVALID_NUMERIC", "Signed display cannot acquire keypad-limit fields")


def configure_converted(section, operation, schema):
    """Configure a signed clone through the existing immutable-type helper."""
    kind = _element_guard(section, schema, "1")
    _signed_settings(operation, kind)
    configure_numeric(section, operation, schema)


def verify_converted(section, kind, schema):
    """Pure saved-clone guard before normalizing the single managed format."""
    observed_kind = _element_guard(section, schema, "1")
    if kind != observed_kind:
        raise HmiError("STORAGE_CONVERSION_SCOPE", "Saved signed owner differs from its witnessed numeric kind")
    values = section.fields()
    digits = values.get("IntNum")
    if not isinstance(digits, str) or re.fullmatch(r"[1-5]", digits) is None:
        raise HmiError("UNQUALIFIED_STORAGE_NUMERIC", "Signed digit count must retain canonical I1..5/F0 storage")
    operation = {"kind": kind, "data_type": "INT", "integer_digits": int(digits), "fractional_digits": 0,
                 "gain": values.get("GainValue"), "offset": values.get("OffsetValue")}
    if kind == "numeric_input":
        operation.update(minimum=values.get("MinValue"), maximum=values.get("MaxValue"))
    _signed_settings(operation, kind)
    verify_numeric_fields(values, operation, schema)
    return True
