"""Original driver/namespace fixtures; ranges are test contracts, not hardware proof."""
from copy import deepcopy
import hashlib
import json
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups, _element, _screen
from universal_hmi.native.address_contract import AddressNamespace, source_driver_fingerprint
from universal_hmi.native.program import BlankProgram
from test_native import control_generation_fixture, qualify_control_generation
from test_program import blank_program_fixture, repin


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


_DRIVER = (b"ControllerSection0=Neutral Company\r\nControllerName0=Original Decimal Driver\r\n"
           b"CommName0=Link2\r\nDefPLCStationNr0=1\r\nPrivateCredential0=never-export-this-value\r\n"
           b"Interface0=0\r\nPrinterSection0=NULL\r\n")


def qualify_address_namespace(adapter):
    return {"qualified": True, "contract_version": 1, "mode": "source_driver_decimal_regions",
            "source_sha256": sha(adapter.original), "prefix": "{Link2}1@",
            "driver": {"native_index": "0", "company": "Neutral Company", "name": "Original Decimal Driver",
                       "raw_span_sha256": source_driver_fingerprint(adapter, "0")},
            "regions": {"BOOL": [{"area": "M", "minimum": 0, "maximum": 4095}, {"area": "S", "minimum": 0, "maximum": 1023}],
                        "UINT": [{"area": "D", "minimum": 0, "maximum": 11999}]},
            "authority_sha256": sha(b"ORIGINAL SYNTHETIC DECIMAL ADDRESS AUTHORITY"),
            "review_reference": "SYNTHETIC_NAMESPACE_TEST_ONLY"}


def qualify_radix_namespace(adapter):
    contract = qualify_address_namespace(adapter)
    contract.update(contract_version=2, mode="source_driver_radix_regions",
                    authority_sha256=sha(b"ORIGINAL SYNTHETIC RADIX AND ACCESS AUTHORITY"))
    for entries in contract["regions"].values():
        for entry in entries:
            entry.update(radix=10, access="ReadWrite")
    contract["regions"]["BOOL"] += [
        {"area": "X", "minimum": 0, "maximum": 255, "radix": 8, "access": "Read"},
        {"area": "Y", "minimum": 0, "maximum": 255, "radix": 8, "access": "ReadWrite"}]
    return contract


def address_generation_fixture(family="delta_dopsoft2"):
    raw, profile = control_generation_fixture(family)
    adapter = NativeAdapter(raw, family)
    body = adapter.envelope.body.replace(b"[Multi-Language]\r\n", _DRIVER + b"[Multi-Language]\r\n", 1)
    raw = adapter.envelope.encode(body)
    profile = qualify_control_generation(raw, profile)
    adapter = NativeAdapter(raw, family)
    profile["native_schema"]["address_namespace"] = qualify_address_namespace(adapter)
    return raw, profile


def address_operations(profile, addresses=("M1", "M10", "S2", "M4095", "D10000", "D11999")):
    result = []
    kinds = ("set_on", "set_off", "momentary", "maintained", "numeric_input", "numeric_display")
    for identity, (kind, address) in enumerate(zip(kinds, addresses), 20):
        pin = profile["native_schema"]["control_generation"]["donors"][kind]
        result.append({"op": "clone_element", "source_screen": pin["screen_id"], "source_element": pin["element_id"],
                       "target_screen": "1", "element_id": str(identity)})
        directions = ("read",) if kind == "numeric_display" else ("read", "write")
        result.append({"op": "bind", "screen_id": "1", "element_id": str(identity),
                       **{direction: {"address": "{Link2}1@" + address, "link": 1, "mem_type": 0} for direction in directions}})
    return result


class AddressNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.profile = address_generation_fixture()
        self.adapter = NativeAdapter(self.raw, self.profile["family"])
        self.schema = self.profile["native_schema"]
        self.contract = self.schema["address_namespace"]
        self.namespace = AddressNamespace(self.contract)

    def error(self, call, code=None):
        with self.assertRaises(HmiError) as caught:
            call()
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        self.assertNotIn("never-export-this-value", json.dumps(caught.exception.as_dict()))

    def changed(self, before, after):
        self.assertIn(before, self.adapter.envelope.body)
        body = self.adapter.envelope.body.replace(before, after, 1)
        return NativeAdapter(self.adapter.envelope.encode(body), self.adapter.family)

    def requalified(self, adapter):
        contract = deepcopy(self.contract)
        contract["source_sha256"] = sha(adapter.original)
        # Same immutable driver pin intentionally remains until a test chooses
        # to rehash the raw span too; source identity alone is insufficient.
        return AddressNamespace(contract)

    def test_both_envelopes_source_validation_and_canonical_region_endpoints(self):
        cases = {"BOOL": ("M0", "M1", "M10", "M20", "M4095", "S0", "S2", "S1023"),
                 "UINT": ("D0", "D1", "D9999", "D10000", "D11999")}
        for family in ("delta_dopsoft2", "delta_diascreen"):
            raw, profile = address_generation_fixture(family)
            adapter = NativeAdapter(raw, family)
            namespace = AddressNamespace(profile["native_schema"]["address_namespace"])
            self.assertTrue(namespace.validate_source(adapter, "{Link2}1@"))
            for data_type, suffixes in cases.items():
                for suffix in suffixes:
                    address = "{Link2}1@" + suffix
                    self.assertEqual(namespace.match(address, data_type, "{Link2}1@"), address)
            self.assertEqual(adapter.apply([], profile), raw)

    def test_invalid_address_spelling_datatype_prefix_and_region_are_typed(self):
        suffixes = ("M4096", "S1024", "D12000", "M-1", "M+1", "M01", "M00", "m1", "M1.0", "M1.1", "M1x", " M1", "M1 ",
                    "M1\r\n", "M2147483648", "M999999999999999999999999", "X1", "M", "1M", "\u041c1", "M\u0661")
        for suffix in suffixes:
            self.error(lambda: self.namespace.match("{Link2}1@" + suffix, "BOOL", "{Link2}1@"), "CONTROL_ADDRESS_SCOPE")
        for address in ("{Link1}1@M1", "{Link2}2@M1", "{Link02}1@M1", "{Link2}01@M1", "None", None, [], 1):
            self.error(lambda: self.namespace.match(address, "BOOL", "{Link2}1@"), "CONTROL_ADDRESS_SCOPE")
        for data_type, suffix in (("UINT", "M1"), ("BOOL", "D1"), ("REAL", "D1"), ("bool", "M1"), (None, "M1"), ([], "M1")):
            self.error(lambda: self.namespace.match("{Link2}1@" + suffix, data_type, "{Link2}1@"), "CONTROL_ADDRESS_SCOPE")
        for prefix in ("{Link2}2@", "{Link1}1@", None, [], 1):
            self.error(lambda: self.namespace.match("{Link2}1@M1", "BOOL", prefix), "CONTROL_ADDRESS_SCOPE")

    def test_contract_shapes_fingerprints_driver_and_review_are_exact(self):
        for value in (None, [], True, "contract", {}):
            self.error(lambda: AddressNamespace(value), "UNQUALIFIED_ADDRESS_NAMESPACE")
        for key, value in (("qualified", 1), ("contract_version", True), ("mode", "other"), ("source_sha256", "A" * 64),
                           ("authority_sha256", None), ("prefix", "{Link02}1@"), ("driver", []), ("regions", None),
                           ("review_reference", ""), ("review_reference", "a\nb"), ("review_reference", "a\u2028b"),
                           ("review_reference", "x" * 257), ("review_reference", " spaces "), ("extra", 1)):
            contract = deepcopy(self.contract); contract[key] = value
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        for key, value in (("native_index", "00"), ("native_index", 0), ("company", ""), ("name", "a\rb"),
                           ("raw_span_sha256", "invalid"), ("extra", 0)):
            contract = deepcopy(self.contract); contract["driver"][key] = value
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        for key in self.contract:
            contract = deepcopy(self.contract); del contract[key]
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")

    def test_deep_or_cyclic_malformed_namespace_is_rejected_before_copy(self):
        nested = "not a review reference"
        for _ in range(500):
            nested = [nested]
        cyclic = []
        cyclic.append(cyclic)
        for field in ("review_reference", "driver", "regions"):
            for value in (nested, cyclic):
                contract = deepcopy(self.contract)
                contract[field] = value
                self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        contract = deepcopy(self.contract)
        contract["driver"]["company"] = contract
        self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        # Successful construction still takes an isolated immutable-source
        # snapshot; later edits to the caller's shape cannot widen its bounds.
        contract = deepcopy(self.contract)
        namespace = AddressNamespace(contract)
        contract["regions"]["BOOL"][0]["maximum"] = 10000
        self.error(lambda: namespace.match("{Link2}1@M4096", "BOOL", "{Link2}1@"), "CONTROL_ADDRESS_SCOPE")

    def test_regions_exact_typed_bounds_no_overlap_or_ambiguous_area(self):
        for value in (None, [], {}, {"BOOL": []}, {"BOOL": [], "UINT": []}, {"BOOL": [], "UINT": [], "REAL": []}):
            contract = deepcopy(self.contract); contract["regions"] = value
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        for value in (None, [], {}, {"area": "M", "minimum": 0, "maximum": 1, "extra": 0},
                      {"area": "m", "minimum": 0, "maximum": 1}, {"area": "M1", "minimum": 0, "maximum": 1},
                      {"area": "M" * 9, "minimum": 0, "maximum": 1}, {"area": "M", "minimum": True, "maximum": 1},
                      {"area": "M", "minimum": 0.0, "maximum": 1}, {"area": "M", "minimum": "0", "maximum": 1},
                      {"area": "M", "minimum": -1, "maximum": 1}, {"area": "M", "minimum": 2, "maximum": 1},
                      {"area": "M", "minimum": 0, "maximum": 2147483648}):
            contract = deepcopy(self.contract); contract["regions"]["BOOL"] = [value]
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        for data_type, entry in (("BOOL", {"area": "M", "minimum": 4095, "maximum": 5000}),
                                 ("BOOL", {"area": "M", "minimum": 0, "maximum": 4095}),
                                 ("UINT", {"area": "M", "minimum": 1, "maximum": 2})):
            contract = deepcopy(self.contract); contract["regions"][data_type].append(entry)
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        contract = deepcopy(self.contract)
        contract["regions"]["BOOL"] = [{"area": "AB", "minimum": 0, "maximum": 0}, {"area": "AB", "minimum": 5, "maximum": 2147483647}]
        namespace = AddressNamespace(contract)
        self.assertEqual(namespace.match("{Link2}1@AB2147483647", "BOOL", "{Link2}1@"), "{Link2}1@AB2147483647")
        self.error(lambda: namespace.match("{Link2}1@AB1", "BOOL", "{Link2}1@"), "CONTROL_ADDRESS_SCOPE")

    def test_source_hash_span_company_name_channel_station_are_separately_pinned(self):
        for key, value in (("source_sha256", "0" * 64), ("prefix", "{Link2}2@")):
            contract = deepcopy(self.contract); contract[key] = value
            namespace = AddressNamespace(contract)
            self.error(lambda: namespace.validate_source(self.adapter, value if key == "prefix" else "{Link2}1@"), "INVALID_ADDRESS_SOURCE")
        for key, value in (("native_index", "1"), ("company", "Other"), ("name", "Other"), ("raw_span_sha256", "0" * 64)):
            contract = deepcopy(self.contract); contract["driver"][key] = value
            self.error(lambda: AddressNamespace(contract).validate_source(self.adapter, "{Link2}1@"), "INVALID_ADDRESS_SOURCE")
        for before, after in ((b"DefPLCStationNr0=1", b"DefPLCStationNr0=01"), (b"CommName0=Link2", b"CommName0=Link02"),
                              (b"ControllerName0=Original Decimal Driver", b"ControllerName0=Other Driver"),
                              (b"Interface0=0", b"Interface0=1")):
            adapter = self.changed(before, after)
            self.error(lambda: self.requalified(adapter).validate_source(adapter, "{Link2}1@"), "INVALID_ADDRESS_SOURCE")
        self.error(lambda: self.namespace.validate_source(None, "{Link2}1@"), "INVALID_ADDRESS_SOURCE")
        adapter = NativeAdapter(self.raw, self.adapter.family); adapter.application.one("CommName0").value = b"Link99"
        self.error(lambda: self.namespace.validate_source(adapter, "{Link2}1@"), "INVALID_ADDRESS_SOURCE")

    def test_driver_marker_field_boundary_ambiguities_fail_even_rehashed(self):
        cases = ((b"ControllerSection0=", b"ControllerSection00="),
                 (b"PrinterSection0=NULL\r\n", b""), (b"PrinterSection0=NULL", b"PrinterSection00=NULL"),
                 (b"PrinterSection0=NULL\r\n", b"PrinterSection0=NULL\r\nPrinterSection0=NULL\r\n"),
                 (b"ControllerSection0=Neutral Company\r\n", b"ControllerSection0=Neutral Company\r\nControllerSection0=Neutral Company\r\n"),
                 (b"DefPLCStationNr0=1\r\n", b"DefPLCStationNr0=1\r\nDefPLCStationNr0=2\r\n"),
                 (b"CommName0=Link2\r\n", b""), (b"Interface0=0\r\n", b"Interface0=0\r\nInterface0=1\r\n"),
                 (b"[Multi-Language]\r\n", b"CommName0=Link2\r\n[Multi-Language]\r\n"),
                 (b"PrinterSection0=NULL\r\n", b"PrinterSection0=NULL\r\nControllerSection1=Other\r\n"))
        for before, after in cases:
            adapter = self.changed(before, after)
            self.error(lambda: source_driver_fingerprint(adapter, "0"), "INVALID_ADDRESS_SOURCE")
            self.error(lambda: self.requalified(adapter).validate_source(adapter, "{Link2}1@"), "INVALID_ADDRESS_SOURCE")
        for index in (None, [], 0, "00", "99999", "missing"):
            self.error(lambda: source_driver_fingerprint(self.adapter, index), "INVALID_ADDRESS_SOURCE")

    def test_complete_multiple_driver_spans_and_opaque_marker_text_do_not_alias(self):
        second = (b"ControllerSection1=Other Company\r\nControllerName1=Other Driver\r\n"
                  b"CommName1=Link1\r\nDefPLCStationNr1=2\r\nPrivateCredential1=never-export-this-value\r\n")
        adapter = self.changed(b"PrinterSection0=NULL\r\n", second + b"PrinterSection0=NULL\r\n")
        # Adding the next complete driver changes the file, but not driver0's
        # bounded raw span. The requalified source pin may admit that identity.
        namespace = self.requalified(adapter)
        self.assertTrue(namespace.validate_source(adapter, "{Link2}1@"))
        self.assertEqual(source_driver_fingerprint(adapter, "0"), self.contract["driver"]["raw_span_sha256"])
        self.assertNotEqual(source_driver_fingerprint(adapter, "1"), source_driver_fingerprint(adapter, "0"))
        broken = NativeAdapter(adapter.envelope.encode(adapter.envelope.body.replace(b"DefPLCStationNr1=2\r\n", b"", 1)), adapter.family)
        self.error(lambda: self.requalified(broken).validate_source(broken, "{Link2}1@"), "INVALID_ADDRESS_SOURCE")
        # A marker-looking string is inside an owned UTF-16 frame, not a
        # controller record. The private walker uses parsed record ownership.
        from test_native import _wide
        opaque = _wide("wUnknownLen", "ControllerSection00=spoof\r\nPrinterSection0=spoof")
        adapter = self.changed(b"[Application]\r\n", b"[Application]\r\n" + opaque)
        self.assertTrue(self.requalified(adapter).validate_source(adapter, "{Link2}1@"))

    def test_native_cloned_bindings_distinct_areas_and_only_binding_records_change(self):
        for family in ("delta_dopsoft2", "delta_diascreen"):
            raw, profile = address_generation_fixture(family)
            source = NativeAdapter(raw, family)
            operations = address_operations(profile)
            output = source.apply(operations, profile)
            candidate = NativeAdapter(output, family)
            self.assertTrue(candidate.verify_control_generation(profile["native_schema"], source))
            self.assertEqual(candidate._preserved_prefix(candidate.document), source._preserved_prefix(source.document))
            self.assertEqual(candidate.document.tail, source.document.tail)
            for identity in range(1, 7):
                self.assertEqual(candidate.owner_extent_sha256("1", str(identity)), source.owner_extent_sha256("1", str(identity)))
            expected = ("M1", "M10", "S2", "M4095", "D10000", "D11999")
            for identity, suffix in enumerate(expected, 20):
                owner = _element(_screen(candidate.document, "1"), str(identity))
                self.assertEqual(owner["section"].one("ReadVar").value, ("{Link2}1@" + suffix).encode())
                for field in ("ReadLink", "WriteLink"):
                    self.assertEqual(owner["section"].one(field).value, b"1")
                for field in ("ReadMemType", "WriteMemType"):
                    self.assertEqual(owner["section"].one(field).value, b"0")
                donor = _groups(source.document)[0]["elements"][identity - 20]
                normalized = candidate._literal_normalized(owner["section"], donor["section"], {"nPartsID", "ReadVar", "WriteVar"})
                self.assertEqual(normalized, donor["section"].bytes())
            self.assertEqual(source.original, raw)

    def test_exact_record_rebinding_m1_cannot_change_m10(self):
        operations = address_operations(self.profile)[:4]
        operations.append({"op": "bind", "screen_id": "1", "element_id": "20", "write": {"address": "{Link2}1@M20", "link": 1, "mem_type": 0}})
        candidate = NativeAdapter(self.adapter.apply(operations, self.profile), self.adapter.family)
        self.assertEqual(_element(_screen(candidate.document, "1"), "20")["section"].one("WriteVar").value, b"{Link2}1@M20")
        self.assertEqual(_element(_screen(candidate.document, "1"), "21")["section"].one("WriteVar").value, b"{Link2}1@M10")
        self.assertTrue(candidate.verify_control_generation(self.schema, self.adapter))

    def test_namespace_source_gate_precedes_donor_and_address_access(self):
        for value in (None, [], {}, True):
            profile = deepcopy(self.profile); profile["native_schema"]["address_namespace"] = value
            profile["native_schema"]["control_generation"]["donors"] = None
            self.error(lambda: self.adapter.apply([], profile), "UNQUALIFIED_ADDRESS_NAMESPACE")
        profile = deepcopy(self.profile); profile["native_schema"]["address_namespace"]["driver"]["raw_span_sha256"] = "0" * 64
        profile["native_schema"]["control_generation"]["donors"] = None
        self.error(lambda: self.adapter.apply([], profile), "INVALID_ADDRESS_SOURCE")

    def test_native_wrong_area_metadata_saved_address_and_old_mode_unchanged(self):
        for suffix in ("M4096", "S1024", "D1", "X0", "M01", "m1"):
            operations = address_operations(self.profile); operations[1]["write"]["address"] = "{Link2}1@" + suffix
            self.error(lambda: self.adapter.apply(operations, self.profile), "CONTROL_ADDRESS_SCOPE")
        for key in ("link", "mem_type"):
            operations = address_operations(self.profile); operations[1]["write"][key] = 2
            self.error(lambda: self.adapter.apply(operations, self.profile), "CONTROL_ADDRESS_SCOPE")
        output = NativeAdapter(self.adapter.apply(address_operations(self.profile), self.profile), self.adapter.family)
        body = output.envelope.body.replace(b"WriteVar={Link2}1@M1\r\n", b"WriteVar={Link2}1@M4096\r\n", 1)
        candidate = NativeAdapter(output.envelope.encode(body), output.family)
        self.error(lambda: candidate.verify_control_generation(self.schema, self.adapter), "CONTROL_ADDRESS_SCOPE")
        profile = deepcopy(self.profile); del profile["native_schema"]["address_namespace"]
        self.error(lambda: self.adapter.apply(address_operations(profile), profile), "CONTROL_ADDRESS_SCOPE")
        self.assertEqual(self.adapter.apply([], profile), self.raw)

    def test_clean_blank_program_keeps_namespace_and_excludes_library_donors(self):
        for family in ("delta_dopsoft2", "delta_diascreen"):
            target_raw, library_raw, schema = blank_program_fixture(family)
            target, library = NativeAdapter(target_raw, family), NativeAdapter(library_raw, family)
            target_raw = target.envelope.encode(target.envelope.body.replace(b"[Multi-Language]\r\n", _DRIVER + b"[Multi-Language]\r\n", 1))
            library_raw = library.envelope.encode(library.envelope.body.replace(b"[Multi-Language]\r\n", _DRIVER + b"[Multi-Language]\r\n", 1))
            schema = repin(target_raw, library_raw, schema)
            target, library = NativeAdapter(target_raw, family), NativeAdapter(library_raw, family)
            schema["blank_program"]["library_schema"]["address_namespace"] = qualify_address_namespace(library)
            program = BlankProgram(target, library, schema)
            self.assertTrue(program.check())
            profile = program.library_profile()
            candidate = NativeAdapter(program.apply(address_operations(profile)), family)
            self.assertTrue(program.verify(candidate))
            self.assertEqual([owner["id"] for owner in _groups(candidate.document)[0]["elements"]], ["20", "21", "22", "23", "24", "25"])
            self.assertEqual(candidate._preserved_prefix(candidate.document), target._preserved_prefix(target.document))


class RadixAddressNamespaceTests(unittest.TestCase):
    """Per-area radix and normal-operation access; never runtime/CPU proof."""

    error = AddressNamespaceTests.error

    def setUp(self):
        self.raw, self.profile = address_generation_fixture()
        self.adapter = NativeAdapter(self.raw, self.profile["family"])
        self.legacy = deepcopy(self.profile)
        self.profile["native_schema"]["address_namespace"] = qualify_radix_namespace(self.adapter)
        self.schema = self.profile["native_schema"]
        self.contract = self.schema["address_namespace"]
        self.namespace = AddressNamespace(self.contract)

    def test_all_256_octal_coordinates_direction_policy_and_v1_byte_behavior(self):
        self.assertTrue(self.namespace.validate_source(self.adapter, "{Link2}1@"))
        for coordinate in range(256):
            # Independent octal formatting establishes the physical coordinate
            # intent; a one-point region verifies the parser's exact radix.
            spelling = format(coordinate, "o")
            point = deepcopy(self.contract)
            point["regions"]["BOOL"][-2].update(minimum=coordinate, maximum=coordinate)
            namespace = AddressNamespace(point)
            x = "{Link2}1@X" + spelling
            y = "{Link2}1@Y" + spelling
            self.assertEqual(namespace.match(x, "BOOL", "{Link2}1@", "read"), x)
            self.error(lambda: namespace.match(x, "BOOL", "{Link2}1@", "write"), "CONTROL_ADDRESS_SCOPE")
            self.assertEqual(namespace.match(y, "BOOL", "{Link2}1@", "read"), y)
            self.assertEqual(namespace.match(y, "BOOL", "{Link2}1@", "write"), y)
        old = AddressNamespace(self.legacy["native_schema"]["address_namespace"])
        for direction in ("read", "write"):
            self.assertEqual(old.match("{Link2}1@M10", "BOOL", "{Link2}1@", direction), "{Link2}1@M10")
            self.error(lambda: old.match("{Link2}1@X0", "BOOL", "{Link2}1@", direction), "CONTROL_ADDRESS_SCOPE")
        legacy_operations = address_operations(self.legacy)
        self.assertEqual(self.adapter.apply(legacy_operations, self.legacy), self.adapter.apply(legacy_operations, self.profile))
        self.assertEqual(self.adapter.apply([], self.legacy), self.raw)
        self.assertEqual(self.adapter.apply([], self.profile), self.raw)

    def test_radix_transition_boundaries_and_canonical_grammar(self):
        for coordinate, spelling in ((7, "7"), (8, "10"), (63, "77"), (64, "100"), (255, "377")):
            point = deepcopy(self.contract)
            point["regions"]["BOOL"][-1].update(minimum=coordinate, maximum=coordinate)
            namespace = AddressNamespace(point)
            address = "{Link2}1@Y" + spelling
            self.assertEqual(namespace.match(address, "BOOL", "{Link2}1@", "write"), address)
            if spelling != str(coordinate):
                self.error(lambda: namespace.match("{Link2}1@Y" + str(coordinate), "BOOL", "{Link2}1@"), "CONTROL_ADDRESS_SCOPE")
        for suffix in ("X8", "X9", "X18", "Y79", "Y400", "X400", "X777", "X01", "X00", "Y+1", "Y-1", "Y1.0",
                       "Y1.1", "Y0x10", "x1", "X 1", "X1 ", " X1", "X1\r\n", "X\u0661", "\u04250",
                       "X999999999999999999999999", "X", "Y"):
            self.error(lambda: self.namespace.match("{Link2}1@" + suffix, "BOOL", "{Link2}1@"), "CONTROL_ADDRESS_SCOPE")
        for direction in (None, [], {}, True, 0, "Read", "WRITE", "", "read "):
            self.error(lambda: self.namespace.match("{Link2}1@Y0", "BOOL", "{Link2}1@", direction), "CONTROL_ADDRESS_SCOPE")
            self.error(lambda: self.adapter._control_address("{Link2}1@Y0", "{Link2}1@", "M", self.schema, direction), "CONTROL_ADDRESS_SCOPE")
        for area in ("M8", "M9", "M10", "S9", "D11999"):
            datatype = "UINT" if area.startswith("D") else "BOOL"
            self.assertEqual(self.namespace.match("{Link2}1@" + area, datatype, "{Link2}1@", "write"), "{Link2}1@" + area)

    def test_v2_exact_entry_shape_radix_access_and_no_mixed_bases_or_overlap(self):
        for field, value in (("radix", True), ("radix", 8.0), ("radix", "8"), ("radix", 2), ("radix", 16), ("radix", []),
                             ("access", None), ("access", []), ("access", {}), ("access", True), ("access", "Write"),
                             ("access", "read"), ("access", "ReadWrite "), ("maximum", True), ("minimum", "0"), ("extra", 0)):
            contract = deepcopy(self.contract); contract["regions"]["BOOL"][-2][field] = value
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        for field in ("radix", "access"):
            contract = deepcopy(self.contract); del contract["regions"]["BOOL"][-2][field]
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        for version, mode in ((1, "source_driver_radix_regions"), (2, "source_driver_decimal_regions"),
                              (3, "source_driver_radix_regions"), (True, "source_driver_decimal_regions")):
            contract = deepcopy(self.contract); contract.update(contract_version=version, mode=mode)
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        old = deepcopy(self.legacy["native_schema"]["address_namespace"])
        old["regions"]["BOOL"][0].update(radix=10, access="ReadWrite")
        self.error(lambda: AddressNamespace(old), "UNQUALIFIED_ADDRESS_NAMESPACE")
        for datatype, region in (("BOOL", {"area": "X", "minimum": 256, "maximum": 300, "radix": 10, "access": "Read"}),
                                 ("BOOL", {"area": "X", "minimum": 255, "maximum": 300, "radix": 8, "access": "Read"}),
                                 ("UINT", {"area": "Y", "minimum": 0, "maximum": 255, "radix": 8, "access": "ReadWrite"})):
            contract = deepcopy(self.contract); contract["regions"][datatype].append(region)
            self.error(lambda: AddressNamespace(contract), "UNQUALIFIED_ADDRESS_NAMESPACE")
        # Generic core supports independently qualified octal regions up to
        # its common integer bound; installed authority supplies X/Y=0..255.
        generic = deepcopy(self.contract)
        generic["regions"]["BOOL"][-2].update(maximum=2147483647)
        namespace = AddressNamespace(generic)
        self.assertEqual(namespace.match("{Link2}1@X17777777777", "BOOL", "{Link2}1@"), "{Link2}1@X17777777777")
        self.error(lambda: namespace.match("{Link2}1@X20000000000", "BOOL", "{Link2}1@"), "CONTROL_ADDRESS_SCOPE")

    def test_saved_native_read_x_write_y_reopens_and_x_write_is_refused(self):
        operations = address_operations(self.profile, ("Y0", "Y7", "Y10", "Y377", "D10000", "D11999"))
        for operation, x in zip((op for op in operations if op["op"] == "bind"), ("X0", "X7", "X10", "X377")):
            operation["read"]["address"] = "{Link2}1@" + x
        candidate = NativeAdapter(self.adapter.apply(operations, self.profile), self.adapter.family)
        self.assertTrue(candidate.verify_control_generation(self.schema, self.adapter))
        self.assertEqual(candidate._preserved_prefix(candidate.document), self.adapter._preserved_prefix(self.adapter.document))
        self.assertEqual(candidate.document.tail, self.adapter.document.tail)
        for identity, x, y in ((20, "X0", "Y0"), (21, "X7", "Y7"), (22, "X10", "Y10"), (23, "X377", "Y377")):
            owner = _element(_screen(candidate.document, "1"), str(identity))["section"]
            self.assertEqual(owner.one("ReadVar").value, ("{Link2}1@" + x).encode())
            self.assertEqual(owner.one("WriteVar").value, ("{Link2}1@" + y).encode())
            self.assertEqual(owner.one("ReadMemType").value, b"0")
            self.assertEqual(owner.one("WriteMemType").value, b"0")
        for suffix in ("X0", "X7", "X10", "X377", "Y8", "Y400"):
            bad = deepcopy(operations); bad[1]["write"]["address"] = "{Link2}1@" + suffix
            self.error(lambda: self.adapter.apply(bad, self.profile), "CONTROL_ADDRESS_SCOPE")
            self.assertEqual(self.adapter.original, self.raw)
        body = candidate.envelope.body.replace(b"WriteVar={Link2}1@Y0\r\n", b"WriteVar={Link2}1@X0\r\n", 1)
        forged = NativeAdapter(candidate.envelope.encode(body), candidate.family)
        self.error(lambda: forged.verify_control_generation(self.schema, self.adapter), "CONTROL_ADDRESS_SCOPE")

    def test_v2_source_span_metadata_and_numeric_type_cannot_be_rehashed_away(self):
        altered = NativeAdapter(self.adapter.envelope.encode(self.adapter.envelope.body.replace(b"Interface0=0", b"Interface0=1", 1)), self.adapter.family)
        contract = deepcopy(self.contract); contract["source_sha256"] = sha(altered.original)
        self.error(lambda: AddressNamespace(contract).validate_source(altered, "{Link2}1@"), "INVALID_ADDRESS_SOURCE")
        for suffix in ("X0", "Y0"):
            self.error(lambda: self.namespace.match("{Link2}1@" + suffix, "UINT", "{Link2}1@"), "CONTROL_ADDRESS_SCOPE")
        for memtype in (128, 129):
            operations = address_operations(self.profile, ("Y0", "Y7", "Y10", "Y377", "D10000", "D11999"))
            operations[1]["write"]["mem_type"] = memtype
            self.error(lambda: self.adapter.apply(operations, self.profile), "CONTROL_ADDRESS_SCOPE")
        changed = deepcopy(self.profile)
        changed["native_schema"]["address_namespace"]["regions"]["BOOL"][-2]["radix"] = []
        changed["native_schema"]["control_generation"]["donors"] = None
        self.error(lambda: self.adapter.apply([], changed), "UNQUALIFIED_ADDRESS_NAMESPACE")

    def test_v2_same_prefix_m1_m10_rebinding_and_readonly_subregions_are_exact(self):
        operations = address_operations(self.profile)[:4]
        operations.append({"op": "bind", "screen_id": "1", "element_id": "20",
                           "write": {"address": "{Link2}1@Y10", "link": 1, "mem_type": 0}})
        candidate = NativeAdapter(self.adapter.apply(operations, self.profile), self.adapter.family)
        self.assertEqual(_element(_screen(candidate.document, "1"), "20")["section"].one("ReadVar").value, b"{Link2}1@M1")
        self.assertEqual(_element(_screen(candidate.document, "1"), "20")["section"].one("WriteVar").value, b"{Link2}1@Y10")
        self.assertEqual(_element(_screen(candidate.document, "1"), "21")["section"].one("WriteVar").value, b"{Link2}1@M10")
        self.assertTrue(candidate.verify_control_generation(self.schema, self.adapter))
        separate = deepcopy(self.contract)
        separate["regions"]["BOOL"][-1].update(maximum=7, access="Read")
        separate["regions"]["BOOL"].append({"area": "Y", "minimum": 8, "maximum": 255, "radix": 8, "access": "ReadWrite"})
        namespace = AddressNamespace(separate)
        self.assertEqual(namespace.match("{Link2}1@Y7", "BOOL", "{Link2}1@", "read"), "{Link2}1@Y7")
        self.error(lambda: namespace.match("{Link2}1@Y7", "BOOL", "{Link2}1@", "write"), "CONTROL_ADDRESS_SCOPE")
        self.assertEqual(namespace.match("{Link2}1@Y10", "BOOL", "{Link2}1@", "write"), "{Link2}1@Y10")


if __name__ == "__main__":
    unittest.main()
