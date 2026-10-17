"""Compare a raw native model number with its equivalent uint32 spelling."""
import re

from ..errors import HmiError


def canonical_model_id(value):
    """Return uint32 identity or an exact opaque qualification-fixture ID.

    Some genuine DPS files spell the same 32-bit model number as signed. This
    comparison never rewrites that native field, permits another model, or
    removes the independent family/editor checks.
    """
    if type(value) is int:
        if not -0x80000000 <= value <= 0xFFFFFFFF:
            raise HmiError("INVALID_PROFILE", "Model number is outside the native 32-bit identity range")
        return value & 0xFFFFFFFF
    if not isinstance(value, str) or not value or any(c in value for c in "\r\n\0"):
        raise HmiError("INVALID_PROFILE", "Model identity must be a nonempty exact string or 32-bit integer")
    if value.lstrip("+-").isascii() and value.lstrip("+-").isdigit():
        if len(value) > 11 or not re.fullmatch(r"0|[1-9][0-9]*|-[1-9][0-9]*", value):
            raise HmiError("INVALID_PROFILE", "Model number must have canonical bounded decimal spelling")
        number = int(value)
        if not -0x80000000 <= number <= 0xFFFFFFFF:
            raise HmiError("INVALID_PROFILE", "Model number is outside the native 32-bit identity range")
        return number & 0xFFFFFFFF
    if len(value) > 128:
        raise HmiError("INVALID_PROFILE", "Opaque qualification model ID exceeds the resource limit")
    return value


def model_ids_match(first, second):
    return canonical_model_id(first) == canonical_model_id(second)
