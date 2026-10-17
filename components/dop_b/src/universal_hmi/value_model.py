"""Exact common raw-integer/display intent; no vendor compiler is invoked.

Bounds and samples stay in PLC storage units. Decimal position is explicit
per element, never inferred from a tag's unit or fractional display setting.
Native input-limit lowering requires its own independently qualified policy.
"""
import re

from .errors import HmiError

INTEGER_RANGES = {"INT": (-32768, 32767), "UINT": (0, 65535),
                  "DINT": (-2147483648, 2147483647), "UDINT": (0, 4294967295)}
FIXED_MODEL = "integer_fixed_decimal"
MAX_FRACTIONAL = 15
_DISPLAY = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")


def fixed_parameters(data_type, fractional):
    if not isinstance(data_type, str) or data_type not in INTEGER_RANGES:
        raise HmiError("NUMERIC_VALUE_MODEL", "Fixed decimal requires explicit integer storage; TIME/floating conversion is forbidden")
    if type(fractional) is not int or not 0 <= fractional <= MAX_FRACTIONAL:
        raise HmiError("NUMERIC_VALUE_MODEL", "Fixed decimal exponent must be an integer from 0 to 15")
    return INTEGER_RANGES[data_type]


def _raw(value, data_type, fractional):
    lower, upper = fixed_parameters(data_type, fractional)
    if type(value) is not int or not lower <= value <= upper:
        raise HmiError("NUMERIC_RAW_RANGE", "Raw sample or bound must be an integer within its exact storage width")
    return value


def raw_to_display(value, data_type, fractional):
    """Return exact display text by digit insertion, including zero padding."""
    _raw(value, data_type, fractional)
    sign = "-" if value < 0 else ""
    digits = str(abs(value))
    if not fractional:
        return sign + digits
    digits = digits.zfill(fractional + 1)
    return sign + digits[:-fractional] + "." + digits[-fractional:]


def display_to_raw(text, data_type, fractional):
    """Parse exact displayed text onto the raw grid; never round a value."""
    fixed_parameters(data_type, fractional)
    if not isinstance(text, str) or len(text) > 96 or not _DISPLAY.fullmatch(text):
        raise HmiError("NUMERIC_DISPLAY_VALUE", "Display input must be bounded canonical decimal text")
    negative = text.startswith("-")
    unsigned = text[1:] if negative else text
    whole, _, fraction = unsigned.partition(".")
    excess = fraction[fractional:]
    if any(char != "0" for char in excess):
        raise HmiError("NUMERIC_DISPLAY_GRID", "Display value cannot be represented without rounding")
    fraction = fraction[:fractional].ljust(fractional, "0")
    value = int(whole) * 10 ** fractional + (int(fraction) if fraction else 0)
    return _raw(-value if negative else value, data_type, fractional)


def integer_digits(minimum, maximum, data_type, fractional):
    """Count integer display digits; a sign is not part of IntNum."""
    _raw(minimum, data_type, fractional)
    _raw(maximum, data_type, fractional)
    if minimum > maximum:
        raise HmiError("NUMERIC_LIMIT_ORDER", "Raw minimum exceeds raw maximum")
    return max(1, len(str(abs(minimum))) - fractional,
               len(str(abs(maximum))) - fractional)
