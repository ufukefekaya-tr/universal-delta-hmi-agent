"""Pure source-qualified DIAScreen address lowering prerequisite.

This owns immutable input snapshots. It writes no native bytes, allocates no
memory, opens no transport and exposes no ordinary-control capability. File
freshness and clean program assembly belong to the later public transaction.
"""
from copy import deepcopy
import hashlib
import json
import re

from ..errors import HmiError
from . import NativeAdapter, _groups
from .address_contract import _source_driver_span


_SHA = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"0|[1-9][0-9]{0,9}")
_PREFIX = re.compile(r"\{(EtherLink[1-9][0-9]{0,3})\}(0|[1-9][0-9]{0,3})@")
_SUFFIX = re.compile(r"([A-Z]{1,8})(0|[1-9][0-9]{0,9})")
_FAMILY = "delta_diascreen"
_MODE = "diascreen_source_driver_decimal_regions_v1"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(value, maximum=256):
    return (isinstance(value, str) and 1 <= len(value) <= maximum
            and value.isascii() and value == value.strip()
            and all(32 <= ord(c) < 127 for c in value))


def _pin(value):
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _identity(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None and int(value) <= 0xffffffff


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate authority field")
        result[key] = value
    return result


def _regions(regions):
    if not isinstance(regions, dict) or set(regions) != {"BOOL", "UINT"}:
        raise HmiError("DIA_ADDRESS_CONTRACT", "Separate exact BOOL and UINT regions are required")
    result = {}
    # The first scalar subset keeps an area assigned to one storage domain.
    # D.n/X.n/Y.n require a separately proven word-bit grammar, not widening.
    seen = {}
    for datatype, entries in regions.items():
        if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
            raise HmiError("DIA_ADDRESS_CONTRACT", "Region lists must be nonempty and bounded")
        result[datatype] = []
        for entry in entries:
            if (not isinstance(entry, dict)
                    or set(entry) != {"area", "minimum", "maximum", "radix", "access"}
                    or not isinstance(entry.get("area"), str)
                    or re.fullmatch(r"[A-Z]{1,8}", entry["area"]) is None
                    or any(type(entry.get(k)) is not int for k in ("minimum", "maximum", "radix"))
                    or entry["radix"] != 10
                    or not 0 <= entry["minimum"] <= entry["maximum"] <= 2147483647
                    or not isinstance(entry.get("access"), str)
                    or entry["access"] not in {"Read", "ReadWrite"}):
                raise HmiError("DIA_ADDRESS_CONTRACT", "Regions need exact decimal endpoints and access policy")
            area, lower, upper = entry["area"], entry["minimum"], entry["maximum"]
            for previous_type, left, right in seen.get(area, []):
                if previous_type != datatype or not (upper < left or lower > right):
                    raise HmiError("DIA_ADDRESS_CONTRACT", "Areas cannot overlap or change storage domains")
            seen.setdefault(area, []).append((datatype, lower, upper))
            result[datatype].append((area, lower, upper, entry["access"]))
    return result


class DiaScreenAddressNamespace:
    """Validate a source/authority snapshot and canonical address requests.

    Source witness validation proves stored address syntax/width/link fields.
    It does not qualify the witness's visibility, trigger, macros or actions.
    Caller-owned contract dictionaries cannot change this validated snapshot.
    """

    def __init__(self, source, contract, authority_raw):
        if not isinstance(source, bytes) or not isinstance(authority_raw, bytes):
            raise HmiError("DIA_ADDRESS_SOURCE", "Source and raw authority require immutable bytes")
        self._check_contract(contract)
        if not 1 <= len(authority_raw) <= 1024 * 1024:
            raise HmiError("DIA_ADDRESS_AUTHORITY", "Authority size is empty or exceeds its bound")
        if _sha(authority_raw) != contract["authority_sha256"]:
            raise HmiError("DIA_ADDRESS_AUTHORITY", "Raw authority differs from its immutable pin")
        try:
            authority = json.loads(authority_raw, object_pairs_hook=_object_pairs,
                                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise HmiError("DIA_ADDRESS_AUTHORITY", "Authority must be bounded unique-field JSON") from exc
        required = {"schema_version", "authority_kind", "family", "serialized_version", "driver",
                    "regions", "evidence", "acceptance_scope"}
        if (not isinstance(authority, dict) or set(authority) != required
                or type(authority.get("schema_version")) is not int or authority["schema_version"] != 1
                or not isinstance(authority.get("authority_kind"), str)
                or authority.get("authority_kind") not in {"manufacturer_static_driver_contract", "original_neutral_fixture"}
                or authority.get("family") != _FAMILY
                or authority.get("serialized_version") != contract["serialized_version"]
                or authority.get("acceptance_scope") != "OFFLINE_DRIVER_SYNTAX_ONLY"
                or not isinstance(authority.get("evidence"), dict)
                or authority.get("driver") != {k: contract["driver"][k] for k in ("company", "name")}
                or authority.get("regions") != contract["regions"]):
            raise HmiError("DIA_ADDRESS_AUTHORITY", "Authority identity, regions or acceptance scope differs")
        _regions(authority["regions"])
        self._contract = deepcopy(contract)
        self._regions = _regions(contract["regions"])
        self._prefix = contract["prefix"]
        self._source_sha256 = _sha(source)
        self._authority_sha256 = _sha(authority_raw)
        self._validate_source(NativeAdapter(source, _FAMILY))

    @staticmethod
    def _check_contract(contract):
        keys = {"qualified", "contract_version", "mode", "family", "source_sha256", "model_id",
                "serialized_version", "prefix", "driver", "regions", "authority_sha256", "witnesses"}
        if (not isinstance(contract, dict) or set(contract) != keys
                or contract.get("qualified") is not True or type(contract.get("contract_version")) is not int
                or contract["contract_version"] != 1 or contract.get("mode") != _MODE
                or contract.get("family") != _FAMILY
                or not all(_pin(contract.get(k)) for k in ("source_sha256", "authority_sha256"))
                or not _identity(contract.get("model_id"))
                or not _text(contract.get("serialized_version"))
                or not isinstance(contract.get("prefix"), str) or _PREFIX.fullmatch(contract["prefix"]) is None):
            raise HmiError("DIA_ADDRESS_CONTRACT", "An exact separately pinned DIAScreen source namespace is required")
        driver = contract.get("driver")
        if (not isinstance(driver, dict)
                or set(driver) != {"native_index", "native_link", "company", "name", "raw_span_sha256"}
                or not _identity(driver.get("native_index")) or int(driver["native_index"]) > 9999
                or not _identity(driver.get("native_link")) or not 1 <= int(driver["native_link"]) <= 65535
                or not _text(driver.get("company")) or not _text(driver.get("name"))
                or not _pin(driver.get("raw_span_sha256"))):
            raise HmiError("DIA_ADDRESS_CONTRACT", "Driver identity, native link and span must be explicit")
        _regions(contract.get("regions"))
        witnesses = contract.get("witnesses")
        if not isinstance(witnesses, dict) or set(witnesses) != {"BOOL", "UINT"}:
            raise HmiError("DIA_ADDRESS_CONTRACT", "Both storage domains require exact source witnesses")
        for domain in witnesses.values():
            if not isinstance(domain, dict) or set(domain) != {"read", "write"}:
                raise HmiError("DIA_ADDRESS_CONTRACT", "Read and write witnesses must be explicit")
            for pin in domain.values():
                if (not isinstance(pin, dict) or set(pin) != {"screen_id", "element_id", "owner_sha256"}
                        or not _identity(pin.get("screen_id")) or not _identity(pin.get("element_id"))
                        or not _pin(pin.get("owner_sha256"))):
                    raise HmiError("DIA_ADDRESS_CONTRACT", "Each witness needs exact page, owner and full extent SHA")

    def _validate_source(self, adapter):
        contract, driver = self._contract, self._contract["driver"]
        NativeAdapter._control_prefix_length(adapter)
        if (self._source_sha256 != contract["source_sha256"]
                or adapter.model_id != contract["model_id"]
                or adapter.editor_version != contract["serialized_version"]):
            raise HmiError("DIA_ADDRESS_SOURCE", "Source bytes, model or serialized version differs")
        raw, fields = _source_driver_span(adapter, driver["native_index"])
        if _sha(raw) != driver["raw_span_sha256"]:
            raise HmiError("DIA_ADDRESS_SOURCE", "Native source driver span differs")
        match = _PREFIX.fullmatch(self._prefix)
        index = driver["native_index"]
        expected = {"ControllerSection" + index: driver["company"], "ControllerName" + index: driver["name"],
                    "CommName" + index: match[1], "DefPLCStationNr" + index: match[2]}
        if any(fields[k].value != v.encode("ascii") for k, v in expected.items()):
            raise HmiError("DIA_ADDRESS_SOURCE", "Source company, driver, channel or station differs")
        owners = {(p["id"], o["id"]): o for p in _groups(adapter.document) for o in p["elements"]}
        for datatype, directions in contract["witnesses"].items():
            for direction, witness in directions.items():
                owner = owners.get((witness["screen_id"], witness["element_id"]))
                if owner is None or adapter.owner_extent_sha256(witness["screen_id"], witness["element_id"]) != witness["owner_sha256"]:
                    raise HmiError("DIA_ADDRESS_WITNESS", "Source address witness extent differs")
                fields = owner["section"].fields()
                stem = direction.title()
                expected_fields = {stem + "Link": driver["native_link"], stem + "MemType": "0",
                                   "MemLen": "0" if datatype == "BOOL" else "1", "MemFmt": "2"}
                if any(fields.get(k) != v for k, v in expected_fields.items()):
                    raise HmiError("DIA_ADDRESS_WITNESS", "Witness requires observed active direct addressing and exact width")
                self.match(fields.get(stem + "Var"), datatype, direction)

    def match(self, address, datatype, direction="read"):
        if (not isinstance(address, str) or len(address) > 128
                or not isinstance(datatype, str) or datatype not in self._regions
                or not isinstance(direction, str) or direction not in {"read", "write"}
                or not address.startswith(self._prefix)):
            raise HmiError("DIA_ADDRESS_SCOPE", "Address storage, direction, channel or station differs")
        suffix = _SUFFIX.fullmatch(address[len(self._prefix):])
        if suffix is None:
            raise HmiError("DIA_ADDRESS_SCOPE", "Only canonical unsigned scalar decimal addresses are qualified")
        area, number = suffix[1], int(suffix[2])
        for candidate, lower, upper, access in self._regions[datatype]:
            if candidate == area and lower <= number <= upper:
                if direction == "write" and access != "ReadWrite":
                    raise HmiError("DIA_ADDRESS_SCOPE", "The registered area permits reads only")
                return {"address": address, "data_type": datatype, "direction": direction,
                        "native_link": self._contract["driver"]["native_link"], "native_mem_type": "0",
                        "channel": _PREFIX.fullmatch(self._prefix)[1], "station": _PREFIX.fullmatch(self._prefix)[2],
                        "area": area, "index": number, "access": access,
                        "scope": "OFFLINE_SOURCE_DRIVER_SYNTAX_ONLY"}
        raise HmiError("DIA_ADDRESS_SCOPE", "Address is outside the source-qualified datatype region")

    def inspect(self):
        """Public metadata excludes source driver settings and witness actions."""
        return {"scope": "OFFLINE_SOURCE_DRIVER_SYNTAX_ONLY", "source_sha256": self._source_sha256,
                "authority_sha256": self._authority_sha256, "prefix": self._prefix,
                "regions": deepcopy(self._contract["regions"]), "native_output": "NOT_CREATED",
                "public_control_capability": "NOT_OPENED", "runtime": "NOT_RUN", "vendor": "NOT_RUN"}
