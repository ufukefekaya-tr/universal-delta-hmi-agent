"""Source-pinned address regions, independent of a PLC brand.

An explicit external authority qualifies regions. Native source validation
pins the driver span and its channel/station; it grants no runtime evidence.
Opaque driver records, including credentials, never enter public results.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import re

from ..errors import HmiError


_SHA = re.compile(r"[0-9a-f]{64}")
_INDEX = re.compile(r"0|[1-9][0-9]{0,3}")
_PREFIX = re.compile(r"\{(Link[1-9][0-9]{0,3})\}((?:0|[1-9][0-9]{0,3}))@")
_MARKER = re.compile(r"ControllerSection(0|[1-9][0-9]{0,3})")
_AREA = re.compile(r"[A-Z]{1,8}")
_ADDRESS = re.compile(r"([A-Z]{1,8})(0|[1-9][0-9]{0,9})")
_RADIX_ADDRESS = re.compile(r"([A-Z]{1,8})(0|[1-9][0-9]{0,10})")
_TYPES = {"BOOL", "UINT"}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _singleline(value, limit=256, ascii_only=False):
    return (isinstance(value, str) and 1 <= len(value) <= limit and value == value.strip()
            and len(value.splitlines()) == 1
            and all(ord(character) >= 32 and ord(character) != 127 for character in value)
            and (not ascii_only or value.isascii()))


def _source_driver_span(adapter, native_index):
    """Private bounded raw bytes for hashing; never serialize this result."""
    from . import NativeAdapter
    if (not isinstance(adapter, NativeAdapter) or not isinstance(native_index, str)
            or not _INDEX.fullmatch(native_index)):
        raise HmiError("INVALID_ADDRESS_SOURCE", "Address namespace needs a canonical native driver identity")
    adapter._preserved_byte_binding("INVALID_ADDRESS_SOURCE")
    records = adapter.application.records
    if len(records) > 250000:
        raise HmiError("INVALID_ADDRESS_SOURCE", "Native application exceeds the bounded driver record limit")
    markers, printer, seen = [], None, set()
    for position, record in enumerate(records):
        key = record.key
        if isinstance(key, str) and key.startswith("ControllerSection"):
            match = _MARKER.fullmatch(key)
            if (match is None or match[1] in seen or record.kind is not None or record.blob is not None):
                raise HmiError("INVALID_ADDRESS_SOURCE", "Native controller markers must be canonical, scalar and unique")
            seen.add(match[1]); markers.append((position, match[1]))
        elif isinstance(key, str) and key.startswith("PrinterSection"):
            if key != "PrinterSection0" or printer is not None or record.kind is not None or record.blob is not None:
                raise HmiError("INVALID_ADDRESS_SOURCE", "Native controller stream needs a unique canonical printer boundary")
            printer = position
    if printer is None or not markers or any(position >= printer for position, _ in markers):
        raise HmiError("INVALID_ADDRESS_SOURCE", "Native controller stream lacks a complete final printer boundary")
    result = None
    all_keys = Counter(record.key for record in records if record.key is not None)
    for number, (start, index) in enumerate(markers):
        stop = markers[number + 1][0] if number + 1 < len(markers) else printer
        span = records[start:stop]
        keys = Counter(record.key for record in span if record.key is not None)
        if any(count != 1 for count in keys.values()) or any(record.key is None and record.raw != b"\r\n" for record in span):
            raise HmiError("INVALID_ADDRESS_SOURCE", "Native driver span contains ambiguous or unframed records")
        required = {stem + index for stem in ("ControllerSection", "ControllerName", "CommName", "DefPLCStationNr")}
        if not required <= set(keys) or any(all_keys[key] != 1 for key in required):
            raise HmiError("INVALID_ADDRESS_SOURCE", "Native driver identity fields are missing, duplicated or outside their span")
        selected = {record.key: record for record in span if record.key in required}
        if any(record.kind is not None or record.blob is not None for record in selected.values()):
            raise HmiError("INVALID_ADDRESS_SOURCE", "Native driver identity must use the observed scalar framing")
        if index == native_index:
            result = (b"".join(record.raw for record in span), selected)
    if result is None:
        raise HmiError("INVALID_ADDRESS_SOURCE", "Requested native driver identity is absent")
    return result


def source_driver_fingerprint(adapter, native_index):
    """Safe driver-span fingerprint for a source-local calibration helper."""
    raw, _ = _source_driver_span(adapter, native_index)
    return _sha(raw)


class AddressNamespace:
    def __init__(self, contract):
        # Reject shape/depth errors before recursive copying. Validated values
        # have a fixed shallow shape with bounded lists and primitive leaves.
        self.contract = contract
        self._check()
        self.contract = deepcopy(contract)

    def _check(self):
        contract = self.contract
        keys = {"qualified", "contract_version", "mode", "source_sha256", "prefix", "driver", "regions", "authority_sha256", "review_reference"}
        if (not isinstance(contract, dict) or set(contract) != keys or contract.get("qualified") is not True
                or type(contract.get("contract_version")) is not int
                or not ((contract["contract_version"] == 1 and contract.get("mode") == "source_driver_decimal_regions")
                        or (contract["contract_version"] == 2 and contract.get("mode") == "source_driver_radix_regions"))):
            raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address namespace requires its exact versioned source-driver region contract")
        radix_contract = contract["contract_version"] == 2
        if any(not isinstance(contract.get(key), str) or not _SHA.fullmatch(contract[key])
               for key in ("source_sha256", "authority_sha256")):
            raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address namespace requires canonical source and authority fingerprints")
        if not isinstance(contract.get("prefix"), str) or not _PREFIX.fullmatch(contract["prefix"]):
            raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address namespace prefix must have a canonical channel and station")
        if not _singleline(contract.get("review_reference")):
            raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address namespace requires a bounded single-line review reference")
        driver = contract.get("driver")
        if (not isinstance(driver, dict) or set(driver) != {"native_index", "company", "name", "raw_span_sha256"}
                or not isinstance(driver.get("native_index"), str) or not _INDEX.fullmatch(driver["native_index"])
                or not _singleline(driver.get("company"), ascii_only=True)
                or not _singleline(driver.get("name"), ascii_only=True)
                or not isinstance(driver.get("raw_span_sha256"), str) or not _SHA.fullmatch(driver["raw_span_sha256"])):
            raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address namespace needs exact bounded native driver identity and span pins")
        regions = contract.get("regions")
        if not isinstance(regions, dict) or set(regions) != _TYPES:
            raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address namespace currently requires separate BOOL and UINT regions")
        normalized, areas, bases = {}, {}, {}
        for data_type, entries in regions.items():
            if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
                raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address region lists must be nonempty and bounded")
            normalized[data_type] = []
            for entry in entries:
                fields = {"area", "minimum", "maximum"} | ({"radix", "access"} if radix_contract else set())
                if (not isinstance(entry, dict) or set(entry) != fields
                        or not isinstance(entry.get("area"), str) or not _AREA.fullmatch(entry["area"])
                        or any(type(entry.get(key)) is not int for key in ("minimum", "maximum"))
                        or not 0 <= entry["minimum"] <= entry["maximum"] <= 2147483647):
                    raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address regions need uppercase areas and inclusive bounded integer endpoints")
                area, lower, upper = entry["area"], entry["minimum"], entry["maximum"]
                radix, access = (entry["radix"], entry["access"]) if radix_contract else (10, "ReadWrite")
                if (type(radix) is not int or radix not in {8, 10}
                        or not isinstance(access, str) or access not in {"Read", "ReadWrite"}):
                    raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address regions require an exact radix and normal-operation access policy")
                if area in bases and bases[area] != radix:
                    raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "One native address area cannot use mixed radices")
                bases[area] = radix
                if any(not (upper < left or lower > right) for left, right in areas.get(area, [])):
                    raise HmiError("UNQUALIFIED_ADDRESS_NAMESPACE", "Address regions cannot overlap or repeat across datatype contracts")
                areas.setdefault(area, []).append((lower, upper))
                normalized[data_type].append((area, lower, upper, radix, access) if radix_contract else (area, lower, upper))
        return normalized

    def validate_source(self, adapter, prefix):
        self._check()
        from . import NativeAdapter
        if not isinstance(adapter, NativeAdapter) or prefix != self.contract["prefix"]:
            raise HmiError("INVALID_ADDRESS_SOURCE", "Address namespace source or prefix differs from its contract")
        adapter._preserved_byte_binding("INVALID_ADDRESS_SOURCE")
        if _sha(adapter.original) != self.contract["source_sha256"]:
            raise HmiError("INVALID_ADDRESS_SOURCE", "Address namespace source bytes differ from their immutable pin")
        driver = self.contract["driver"]
        raw, fields = _source_driver_span(adapter, driver["native_index"])
        if _sha(raw) != driver["raw_span_sha256"]:
            raise HmiError("INVALID_ADDRESS_SOURCE", "Native driver span differs from its immutable pin")
        index = driver["native_index"]
        expected = {"ControllerSection" + index: driver["company"], "ControllerName" + index: driver["name"],
                    "CommName" + index: _PREFIX.fullmatch(prefix)[1], "DefPLCStationNr" + index: _PREFIX.fullmatch(prefix)[2]}
        if any(fields[key].value != value.encode("ascii") for key, value in expected.items()):
            raise HmiError("INVALID_ADDRESS_SOURCE", "Native driver identity, channel or station differs from the address authority")
        return True

    def match(self, address, data_type, prefix, direction="read"):
        regions = self._check()
        if (not isinstance(address, str) or not isinstance(data_type, str) or data_type not in regions
                or prefix != self.contract["prefix"] or not address.startswith(prefix)
                or not isinstance(direction, str) or direction not in {"read", "write"}):
            raise HmiError("CONTROL_ADDRESS_SCOPE", "Control address or datatype differs from its source-qualified namespace")
        suffix = address[len(prefix):]
        radix_contract = self.contract["contract_version"] == 2
        match = (_RADIX_ADDRESS if radix_contract else _ADDRESS).fullmatch(suffix)
        if match is None:
            raise HmiError("CONTROL_ADDRESS_SCOPE", "Control address must use a canonical uppercase area and bounded native digits")
        area, digits = match[1], match[2]
        for entry in regions[data_type]:
            region_area, minimum, maximum = entry[:3]
            if area != region_area:
                continue
            radix, access = entry[3:] if radix_contract else (10, "ReadWrite")
            if radix == 8 and re.fullmatch(r"0|[1-7][0-7]*", digits) is None:
                raise HmiError("CONTROL_ADDRESS_SCOPE", "Control address digits do not belong to the qualified area radix")
            number = int(digits, radix)
            if minimum <= number <= maximum:
                if direction == "write" and access != "ReadWrite":
                    raise HmiError("CONTROL_ADDRESS_SCOPE", "Control write is outside the qualified normal-operation access policy")
                return address
        raise HmiError("CONTROL_ADDRESS_SCOPE", "Control address lies outside the source-qualified typed regions")
