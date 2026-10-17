"""Exact numeric edits on a qualified, datatype-matched native donor.

The profile supplies vendor enum values. This module never invents a width
enum or changes the donor's storage representation to fit a requested tag.
"""
from decimal import Decimal, InvalidOperation
import math
import re
import struct

from ..errors import HmiError


NUMERIC_FIELDS = {"MemLen", "MemFmt", "MinValue", "MaxValue", "IntNum", "DotNum",
                  "GainValue", "OffsetValue"}
_TYPES = {
    "INT": (16, "signed", Decimal(-32768), Decimal(32767)),
    "UINT": (16, "unsigned", Decimal(0), Decimal(65535)),
    "DINT": (32, "signed", Decimal(-2147483648), Decimal(2147483647)),
    "UDINT": (32, "unsigned", Decimal(0), Decimal(4294967295)),
    "REAL": (32, "floating", Decimal("-3.4028234663852886e38"), Decimal("3.4028234663852886e38")),
    "LREAL": (64, "floating", Decimal("-1.7976931348623157e308"), Decimal("1.7976931348623157e308")),
}
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?")
# Fixed-form IEEE64 subnormals need up to 326 characters. One shared bound
# keeps every emitted literal readable by final verification and repeated edits.
MAX_NUMBER_CHARS = 384
FIXED_DECIMAL_MODEL = "integer_fixed_decimal"
_FIXED_DECIMAL_FIELDS = {"qualified", "contract_version", "mode", "types",
                         "max_fractional_digits", "max_total_digits", "storage_domain",
                         "limit_domain", "input_lowering", "source_sha256",
                         "authority_sha256", "review_reference"}


def fixed_decimal_contract(schema):
    """Validate the separately qualified stored-display contract.

    This bounded descriptor does not qualify keypad/compiler lowering. It
    grants only the exact UINT presentation model declared here. External
    source/authority provenance must additionally be checked by the caller.
    All container shapes and scalar bounds are validated before copying.
    """
    if (not isinstance(schema, dict) or not isinstance(schema.get("numeric"), dict)
            or schema["numeric"].get("qualified") is not True):
        raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fixed decimal requires a separate numeric value-model contract")
    models = schema["numeric"].get("value_models")
    if not isinstance(models, dict) or set(models) != {FIXED_DECIMAL_MODEL}:
        raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Only the separately qualified fixed-decimal value model is supported")
    spec = models[FIXED_DECIMAL_MODEL]
    if not isinstance(spec, dict) or set(spec) != _FIXED_DECIMAL_FIELDS:
        raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fixed-decimal descriptor must declare its exact bounded fields")
    if (spec["qualified"] is not True or type(spec["contract_version"]) is not int or spec["contract_version"] != 1
            or spec["mode"] != FIXED_DECIMAL_MODEL or not isinstance(spec["types"], list) or spec["types"] != ["UINT"]
            or type(spec["max_fractional_digits"]) is not int or spec["max_fractional_digits"] != 4
            or type(spec["max_total_digits"]) is not int or spec["max_total_digits"] != 5
            or spec["storage_domain"] != "raw_integer" or spec["limit_domain"] != "display"
            or spec["input_lowering"] != "UNVERIFIED"):
        raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fixed-decimal descriptor differs from the qualified UINT display contract")
    for field in ("source_sha256", "authority_sha256"):
        value = spec[field]
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fixed-decimal provenance requires canonical SHA-256", field=field)
    review = spec["review_reference"]
    if (not isinstance(review, str) or not 1 <= len(review) <= 256 or review != review.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in review)):
        raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fixed-decimal review reference must be bounded single-line text")
    return dict(spec, types=list(spec["types"]))


def _number(value, name):
    if type(value) is int:
        if value.bit_length() > 256:
            raise HmiError("NUMERIC_LIMIT", "Numeric argument exceeds the decimal resource limit", field=name)
        value = str(value)
    elif type(value) is float:
        if not math.isfinite(value):
            raise HmiError("NUMERIC_LIMIT", "Numeric argument must be finite", field=name)
        value = str(value)
    if not isinstance(value, str) or len(value) > MAX_NUMBER_CHARS or not _NUMBER.fullmatch(value):
        raise HmiError("NUMERIC_LIMIT", "Numeric argument must be a bounded exact decimal", field=name)
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise HmiError("NUMERIC_LIMIT", "Numeric argument is invalid", field=name) from exc
    if not number.is_finite() or not -324 <= number.adjusted() <= 308:
        raise HmiError("NUMERIC_LIMIT", "Numeric argument exceeds the supported decimal range", field=name)
    return number


def _setting(section, field, number):
    record = section.one(field)
    try:
        previous = _number(record.value.decode("ascii", "strict"), field)
    except (UnicodeDecodeError, HmiError):
        raise HmiError("NATIVE_NUMERIC", "Donor numeric setting is invalid", field=field) from None
    if previous == number:
        return  # Retain vendor spelling and no-op byte identity.
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if len(text) > MAX_NUMBER_CHARS:
        raise HmiError("NUMERIC_LIMIT", "Numeric setting cannot be emitted within the qualified decimal length", field=field)
    record.set_value(text.encode("ascii"))


def _enum_tuple(spec, name, required):
    if not isinstance(spec, dict) or set(spec) != required:
        raise HmiError("INVALID_SCHEMA", "Numeric mapping must declare its exact native fields", field=name)
    for field in required - {"bits", "format"}:
        value = spec[field]
        if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,9}", value):
            raise HmiError("INVALID_SCHEMA", "Native numeric enum must be a canonical decimal string", field=field)
    return spec


def _numeric_settings(native_fields, operation, schema):
    """Pure contract validation shared by mutation and final-file verification."""
    if not isinstance(native_fields, dict):
        raise HmiError("NATIVE_NUMERIC", "Numeric donor fields must be an object")
    if not isinstance(operation, dict):
        raise HmiError("INVALID_NUMERIC", "Numeric operation must be an object")
    if not isinstance(schema, dict):
        raise HmiError("INVALID_SCHEMA", "Numeric schema must be an object")
    numeric = schema.get("numeric")
    if not isinstance(numeric, dict) or numeric.get("qualified") is not True:
        raise HmiError("UNQUALIFIED_NUMERIC", "Numeric edits require a separately qualified numeric mapping")
    kind = operation.get("kind")
    if not isinstance(kind, str) or kind not in {"numeric_input", "numeric_display"}:
        raise HmiError("INVALID_NUMERIC", "Numeric kind must be input or display")
    kinds, types = numeric.get("kinds"), numeric.get("types")
    if not isinstance(kinds, dict) or not isinstance(types, dict):
        raise HmiError("INVALID_SCHEMA", "Numeric kinds and datatype mappings must be objects")
    native_kind = _enum_tuple(kinds.get(kind), kind, {"Type", "SubType"})
    data_type = operation.get("data_type")
    if not isinstance(data_type, str) or data_type not in _TYPES:
        raise HmiError("UNSUPPORTED_NUMERIC_TYPE", "Numeric datatype is unsupported; no narrowing or TIME fallback is allowed")
    native_type = _enum_tuple(types.get(data_type), data_type, {"MemLen", "MemFmt", "bits", "format"})
    bits, format_name, lower, upper = _TYPES[data_type]
    if type(native_type["bits"]) is not int or native_type["bits"] != bits or native_type["format"] != format_name:
        raise HmiError("INVALID_SCHEMA", "Numeric mapping contradicts the requested datatype width or representation")
    for field, expected in (native_kind | {key: native_type[key] for key in ("MemLen", "MemFmt")}).items():
        if native_fields.get(field) != expected:
            raise HmiError("NUMERIC_DONOR_MISMATCH", "Numeric donor has a different kind or storage datatype", field=field)

    fixed = None
    if "value_model" in operation:
        if operation["value_model"] != FIXED_DECIMAL_MODEL:
            raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Numeric value model must be an explicit qualified fixed decimal")
        fixed = fixed_decimal_contract(schema)
        if data_type not in fixed["types"] or bits != 16 or format_name != "unsigned":
            raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fixed decimal cannot reinterpret the witnessed UINT storage")

    digits = {}
    for argument, default_maximum, minimum in (("integer_digits", 20, 1), ("fractional_digits", 18, 0)):
        maximum = numeric.get("max_" + argument, default_maximum)
        if type(maximum) is not int or not minimum <= maximum <= default_maximum:
            raise HmiError("INVALID_SCHEMA", "Qualified numeric digit range is invalid", field=argument)
        value = operation.get(argument)
        if type(value) is not int or not minimum <= value <= maximum:
            raise HmiError("NUMERIC_DIGITS", "Numeric digit count exceeds the qualified range", field=argument)
        digits[argument] = value

    if fixed is not None:
        if (digits["fractional_digits"] > fixed["max_fractional_digits"]
                or sum(digits.values()) > fixed["max_total_digits"]):
            raise HmiError("NUMERIC_DIGITS", "Fixed-decimal total digits exceed the qualified UINT presentation range")
        if kind == "numeric_input" and digits["fractional_digits"]:
            raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fractional integer keypad-limit lowering remains unqualified")
        if kind == "numeric_display" and ("MinValue" in native_fields or "MaxValue" in native_fields):
            raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fixed-decimal display cannot inherit keypad-limit fields")
        # Fixed decimal moves the printed decimal point; it must not repair
        # a donor with pre-existing nonidentity scaling into that model.
        if (_number(native_fields.get("GainValue"), "GainValue") != 1
                or _number(native_fields.get("OffsetValue"), "OffsetValue") != 0):
            raise HmiError("UNQUALIFIED_SCALING", "Fixed decimal requires an identity-scaled source donor")

    gain = _number(operation.get("gain"), "gain")
    offset = _number(operation.get("offset"), "offset")
    # Only identity scaling has been independently observed as a reusable
    # contract. Nonidentity scaling requires a separately calibrated emitter.
    if gain != 1 or offset != 0:
        raise HmiError("UNQUALIFIED_SCALING", "Nonidentity scaling is not qualified by this emitter")
    settings = {"IntNum": digits["integer_digits"], "DotNum": digits["fractional_digits"],
                "GainValue": gain, "OffsetValue": offset}
    if kind == "numeric_display":
        if "minimum" in operation or "maximum" in operation:
            raise HmiError("INVALID_NUMERIC", "Display donors have no editable input limits")
    else:
        minimum = _number(operation.get("minimum"), "minimum")
        maximum = _number(operation.get("maximum"), "maximum")
        if minimum > maximum or minimum < lower or maximum > upper:
            raise HmiError("NUMERIC_LIMIT", "Numeric limits exceed the declared datatype or are reversed")
        if format_name != "floating" and any(n != n.to_integral_value() for n in (minimum, maximum)):
            raise HmiError("NUMERIC_LIMIT", "Integer storage requires integral raw input limits")
        if format_name == "floating":
            for name, number in (("minimum", minimum), ("maximum", maximum)):
                # Representation check only: preserve the original exact
                # Decimal spelling for output, including ordinary 0.1. IEEE
                # rounding is expected; a nonzero limit becoming zero is not.
                try:
                    represented = float(number)
                    if bits == 32:
                        represented = struct.unpack("<f", struct.pack("<f", represented))[0]
                except (OverflowError, struct.error) as exc:
                    raise HmiError("NUMERIC_LIMIT", "Numeric limit cannot be represented in its declared IEEE width", field=name) from exc
                if not math.isfinite(represented) or (number != 0 and represented == 0):
                    raise HmiError("NUMERIC_LIMIT", "Nonzero numeric limit underflows its declared IEEE width", field=name)
        required_digits = max(1, minimum.copy_abs().adjusted() + 1, maximum.copy_abs().adjusted() + 1)
        if digits["integer_digits"] < required_digits:
            raise HmiError("NUMERIC_DIGITS", "Integer digits cannot display the declared input limits")
        settings.update(MinValue=minimum, MaxValue=maximum)
    return settings


def configure_numeric(section, operation, schema):
    """Change existing numeric fields, retaining all other donor bytes.

    Storage (MemLen/MemFmt) is an immutable precondition, not a conversion.
    Without value_model, limits retain the existing raw-value contract.
    An explicit integer_fixed_decimal descriptor qualifies UINT display
    decimal insertion only. Fractional keypad-limit lowering stays closed.
    """
    section.check_unique(NUMERIC_FIELDS | {"Type", "SubType"})
    settings = _numeric_settings(section.fields(), operation, schema)
    for field, value in settings.items():
        if isinstance(value, Decimal):
            _setting(section, field, value)
        else:
            section.one(field).set_value(str(value).encode("ascii"))


def verify_numeric_fields(native_fields, operation, schema):
    """Read-only final-file contract verification, including no-op plans.

    Enum storage spelling and schema width/format stay exact. Numeric limit
    spelling may differ only when its exact decimal value is unchanged.
    """
    settings = _numeric_settings(native_fields, operation, schema)
    for field, expected in settings.items():
        actual = native_fields.get(field)
        if isinstance(expected, Decimal):
            matches = _number(actual, field) == expected
        else:
            matches = actual == str(expected)
        if not matches:
            raise HmiError("NUMERIC_MISMATCH", "Native numeric settings do not match the requested contract", field=field)
    return True
