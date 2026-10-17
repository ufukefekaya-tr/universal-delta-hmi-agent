"""Original synthetic storage transformation tests, never signed donor proof."""
from copy import deepcopy
import hashlib
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups, _screen, _element
from universal_hmi.native.numeric import configure_numeric
from universal_hmi.native.storage_conversion import (storage_contract, validate_source,
    convert_storage, configure_converted, verify_converted)
from universal_hmi.native.multipage import MultiPageProgram
from test_native import control_generation_fixture, qualify_control_generation
from test_fixedpoint_native import qualify_fixed, control_operations as fixed_operations
from test_multipage import multipage_fixture, mixed_operations


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def retarget(raw, family, model="2953863504", version="4.00.07.04"):
    adapter = NativeAdapter(raw, family)
    document = deepcopy(adapter.document)
    document.sections[0].one("ModelName").set_value(model.encode("ascii"))
    document.sections[0].one("Version").set_value(version.encode("ascii"))
    return adapter.envelope.encode(document.bytes())


def qualify_storage(profile):
    result = deepcopy(profile)
    schema = result["native_schema"]
    generation = schema["control_generation"]
    schema["numeric"]["types"]["INT"] = {"MemLen": "1", "MemFmt": "1", "bits": 16, "format": "signed"}
    schema["storage_conversion"] = {
        "qualified": True, "contract_version": 1, "mode": "source_uint16_to_int16_f0",
        "source_sha256": generation["source_sha256"],
        "authority_sha256": sha(b"SYNTHETIC STATIC TRANSFORMATION AUTHORITY; NOT VENDOR DONOR"),
        "input_donor_sha256": generation["donors"]["numeric_input"]["owner_sha256"],
        "display_donor_sha256": generation["donors"]["numeric_display"]["owner_sha256"],
        "review_reference": "SYNTHETIC_IDENTITY_SHAPE_TEST_NOT_GENUINE_SIGNED_WITNESS"}
    return result


def storage_fixture(family="delta_dopsoft2", model="2953863504", version="4.00.07.04"):
    raw, profile = control_generation_fixture(family)
    raw = retarget(raw, family, model, version)
    profile.update(model_id=model, editor_version=version)
    profile = qualify_storage(qualify_control_generation(raw, profile))
    return raw, profile


def signed_operations(profile, kind="numeric_input", identity="20", **changes):
    pin = profile["native_schema"]["control_generation"]["donors"][kind]
    configure = {"op": "configure_numeric", "screen_id": "1", "element_id": identity,
                 "kind": kind, "data_type": "INT", "integer_digits": 5,
                 "fractional_digits": 0, "gain": 1, "offset": 0}
    if kind == "numeric_input":
        configure.update(minimum=-32768, maximum=32767)
    configure.update(changes)
    return [{"op": "clone_element", "source_screen": pin["screen_id"], "source_element": pin["element_id"],
             "target_screen": "1", "element_id": identity},
            {"op": "bind", "screen_id": "1", "element_id": identity,
             "read" if kind == "numeric_display" else "write": {"address": "{Link2}1@D0", "link": 1, "mem_type": 0}},
            {"op": "convert_numeric_storage", "screen_id": "1", "element_id": identity, "data_type": "INT"},
            configure]


class StorageConversionTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.profile = storage_fixture()
        self.adapter = NativeAdapter(self.raw, self.profile["family"])
        self.schema = self.profile["native_schema"]

    def error(self, call, code=None):
        with self.assertRaises(HmiError) as caught:
            call()
        if code:
            self.assertEqual(caught.exception.code, code)

    def owner(self, adapter, identity="20"):
        return _element(_screen(adapter.document, "1"), identity)

    def output(self, kind="numeric_input", **changes):
        return NativeAdapter(self.adapter.apply(signed_operations(self.profile, kind, **changes), self.profile), self.adapter.family)

    def mutate_owner(self, candidate, before, after, identity="20"):
        owner = self.owner(candidate, identity)
        block = b"".join(section.bytes() for section in candidate.document.sections[owner["start"]:owner["end"]])
        self.assertIn(before, block)
        body = candidate.envelope.body.replace(block, block.replace(before, after, 1), 1)
        return NativeAdapter(candidate.envelope.encode(body), candidate.family)

    def test_explicit_signed_input_display_saved_types_boundaries_and_complete_source_restoration(self):
        operations = signed_operations(self.profile) + signed_operations(self.profile, "numeric_display", "21")
        candidate = NativeAdapter(self.adapter.apply(operations, self.profile), self.adapter.family)
        self.assertTrue(candidate.verify_control_generation(self.schema, self.adapter))
        input_owner, display_owner = self.owner(candidate), self.owner(candidate, "21")
        fields = input_owner["section"].fields()
        self.assertEqual({key: fields[key] for key in ("MemLen", "MemFmt", "IntNum", "DotNum", "MinValue", "MaxValue")},
                         {"MemLen": "1", "MemFmt": "1", "IntNum": "5", "DotNum": "0", "MinValue": "-32768", "MaxValue": "32767"})
        self.assertNotIn("MinValue", display_owner["section"].fields())
        self.assertNotIn("MaxValue", display_owner["section"].fields())
        self.assertEqual(display_owner["section"].one("MemFmt").value, b"1")
        self.assertEqual(input_owner["section"].one("GainValue").raw, self.owner(self.adapter, "5")["section"].one("GainValue").raw)
        self.assertEqual(input_owner["section"].one("OffsetValue").raw, self.owner(self.adapter, "5")["section"].one("OffsetValue").raw)
        for original in _groups(self.adapter.document)[0]["elements"]:
            self.assertEqual(candidate.owner_extent_sha256("1", original["id"]), self.adapter.owner_extent_sha256("1", original["id"]))
        for owner, original_id in ((input_owner, "5"), (display_owner, "6")):
            donor = self.owner(self.adapter, original_id)
            managed = {"nPartsID", "MemFmt", "IntNum", "MinValue", "MaxValue"} & set(donor["section"].fields())
            self.assertEqual(candidate._literal_normalized(owner["section"], donor["section"], managed), donor["section"].bytes())
            self.assertEqual([state.bytes() for state in owner["states"]], [state.bytes() for state in donor["states"]])
        source_sections = candidate.document.sections[:input_owner["start"]]
        self.assertEqual(b"".join(section.bytes() for section in source_sections) + candidate.document.tail, self.adapter.envelope.body)
        self.assertEqual(candidate.envelope.thumbnail, self.adapter.envelope.thumbnail)
        self.assertEqual(candidate.envelope.prefix, self.adapter.envelope.prefix_for_body(candidate.envelope.body))
        self.assertEqual(self.adapter.original, self.raw)
        self.assertEqual(self.adapter.apply([], self.profile), self.raw)

    def test_transform_helper_changes_only_format_byte_and_numeric_helper_stays_immutable(self):
        owner = deepcopy(self.owner(self.adapter, "5")["section"])
        original = owner.bytes()
        operation = signed_operations(self.profile)[2]
        configure = signed_operations(self.profile)[3]
        self.error(lambda: configure_numeric(owner, configure, self.schema), "NUMERIC_DONOR_MISMATCH")
        self.assertEqual(owner.bytes(), original)
        convert_storage(owner, operation, self.schema)
        self.assertEqual(owner.bytes(), original.replace(b"MemFmt=2\r\n", b"MemFmt=1\r\n", 1))
        self.error(lambda: convert_storage(owner, operation, self.schema), "STORAGE_CONVERSION_STATE")
        configure_converted(owner, configure, self.schema)
        self.assertTrue(verify_converted(owner, "numeric_input", self.schema))
        self.assertEqual(owner.one("MemLen").value, b"1")

    def test_signed_input_range_strict_order_canonical_integral_and_sufficient_digits(self):
        for minimum, maximum, digits in ((-32768, 32767, 5), (-999, 999, 3), (-9, -1, 1), (0, 9, 1),
                                        ("-32768", "32767", 5), (-32768, -32767, 5)):
            candidate = self.output(minimum=minimum, maximum=maximum, integer_digits=digits)
            self.assertTrue(candidate.verify_control_generation(self.schema, self.adapter))
        for minimum, maximum in ((-32769, 32767), (-32768, 32768), (0, 0), (1, 0), (True, 2), (0.0, 1),
                                 ("-0", "1"), ("0.0", "1"), ("0", "1e1"), ("+0", "1"), ("01", "2"),
                                 (" 0", "1"), ("NaN", "1"), (None, 1), ([], 1), ({}, 1)):
            self.error(lambda: self.output(minimum=minimum, maximum=maximum), "STORAGE_CONVERSION_LIMIT")
            self.assertEqual(self.adapter.original, self.raw)
        self.error(lambda: self.output(minimum=-100, maximum=999, integer_digits=2), "NUMERIC_DIGITS")
        for digits in (0, 6, True, "5", [], {}):
            self.error(lambda: self.output(integer_digits=digits), "UNQUALIFIED_STORAGE_NUMERIC")

    def test_fractional_scaling_fixed_models_and_other_types_remain_closed(self):
        for kind in ("numeric_input", "numeric_display"):
            for fractional in (1, 4, True, "0", None, [], {}):
                self.error(lambda: self.output(kind, fractional_digits=fractional), "UNQUALIFIED_STORAGE_NUMERIC")
            for changes in ({"gain": 2}, {"offset": 1}, {"value_model": "integer_fixed_decimal"}):
                self.error(lambda: self.output(kind, **changes))
            for data_type in ("UINT", "DINT", "UDINT", "REAL", "LREAL", "TIME", None, [], {}):
                operations = signed_operations(self.profile, kind); operations[2]["data_type"] = data_type
                self.error(lambda: self.adapter.apply(operations, self.profile), "INVALID_STORAGE_OPERATION")
        for field in ("minimum", "maximum"):
            self.error(lambda: self.output("numeric_display", **{field: 0}), "INVALID_NUMERIC")

    def test_conversion_only_fresh_numeric_clone_original_button_double_and_wrong_order_rejected(self):
        for identity in ("1", "5", "6"):
            operation = {"op": "convert_numeric_storage", "screen_id": "1", "element_id": identity, "data_type": "INT"}
            self.error(lambda: self.adapter.apply([operation], self.profile), "CONTROL_GENERATION_SCOPE")
        button = self.schema["control_generation"]["donors"]["momentary"]
        clone = {"op": "clone_element", "source_screen": button["screen_id"], "source_element": button["element_id"],
                 "target_screen": "1", "element_id": "20"}
        self.error(lambda: self.adapter.apply([clone, signed_operations(self.profile)[2]], self.profile), "STORAGE_CONVERSION_SCOPE")
        operations = signed_operations(self.profile); operations.insert(3, deepcopy(operations[2]))
        self.error(lambda: self.adapter.apply(operations, self.profile), "STORAGE_CONVERSION_STATE")
        operations = signed_operations(self.profile); operations[2], operations[3] = operations[3], operations[2]
        self.error(lambda: self.adapter.apply(operations, self.profile), "STORAGE_CONVERSION_STATE")
        operations = signed_operations(self.profile); del operations[2]
        self.error(lambda: self.adapter.apply(operations, self.profile), "STORAGE_CONVERSION_STATE")
        for extra in ({"bits": 32}, {"kind": "numeric_input"}):
            operations = signed_operations(self.profile); operations[2].update(extra)
            self.error(lambda: self.adapter.apply(operations, self.profile), "INVALID_OPERATION")

    def test_descriptor_exact_shapes_pins_numeric_maps_and_deep_values_reject_before_copy(self):
        self.assertIsNone(storage_contract({}))
        for value in (None, [], {}, True, "descriptor"):
            schema = deepcopy(self.schema); schema["storage_conversion"] = value
            self.error(lambda: storage_contract(schema), "UNQUALIFIED_STORAGE_CONVERSION")
        for field, value in (("qualified", 1), ("contract_version", True), ("mode", "raw"),
            ("source_sha256", "0" * 64), ("authority_sha256", "A" * 64), ("input_donor_sha256", "0" * 64),
            ("display_donor_sha256", []), ("review_reference", "a\nb"), ("review_reference", "a\u2028b"),
            ("review_reference", "x" * 257), ("review_reference", " x"), ("extra", 1)):
            schema = deepcopy(self.schema); schema["storage_conversion"][field] = value
            self.error(lambda: storage_contract(schema), "UNQUALIFIED_STORAGE_CONVERSION")
        for field, value in (("MemLen", "2"), ("MemFmt", "2"), ("bits", 16.0), ("bits", True), ("format", "unsigned")):
            schema = deepcopy(self.schema); schema["numeric"]["types"]["INT"][field] = value
            self.error(lambda: storage_contract(schema), "UNQUALIFIED_STORAGE_CONVERSION")
        for value in (None, {}, [], {"UINT": deepcopy(self.schema["numeric"]["types"]["UINT"])}):
            schema = deepcopy(self.schema); schema["numeric"]["types"] = value
            self.error(lambda: storage_contract(schema), "UNQUALIFIED_STORAGE_CONVERSION")
        schema = deepcopy(self.schema); schema["numeric"]["types"]["DINT"] = {"MemLen": "2", "MemFmt": "1", "bits": 32, "format": "signed"}
        self.error(lambda: storage_contract(schema), "UNQUALIFIED_STORAGE_CONVERSION")
        for field, value in (("qualified", 1), ("contract_version", True), ("mode", "raw"),
                             ("address_prefix", None), ("address_prefix", []), ("address_prefix", {}),
                             ("address_prefix", "{Link02}1@")):
            schema = deepcopy(self.schema); schema["control_generation"][field] = value
            self.error(lambda: storage_contract(schema), "UNQUALIFIED_STORAGE_CONVERSION")
            self.error(lambda: validate_source(self.adapter, schema), "UNQUALIFIED_STORAGE_CONVERSION")
        cyclic = {}; cyclic["cycle"] = cyclic
        deep = 0
        for _ in range(1500):
            deep = [deep]
        for field in ("review_reference", "input_donor_sha256", "source_sha256"):
            for value in (cyclic, deep):
                schema = deepcopy(self.schema); schema["storage_conversion"][field] = value
                self.error(lambda: storage_contract(schema), "UNQUALIFIED_STORAGE_CONVERSION")
        copied = storage_contract(self.schema); copied["review_reference"] = "Changed"
        self.assertNotEqual(copied["review_reference"], self.schema["storage_conversion"]["review_reference"])

    def test_actual_source_identity_family_version_and_unsigned_storage_are_mandatory(self):
        self.assertTrue(validate_source(self.adapter, self.schema))
        self.assertIsNone(validate_source(None, {}))
        self.error(lambda: validate_source(None, self.schema), "INVALID_STORAGE_SOURCE")
        for family, model, version in (("delta_diascreen", "2953863504", "4.00.07.04"),
                                      ("delta_dopsoft2", "2953863505", "4.00.07.04"),
                                      ("delta_dopsoft2", "2953863504", "4.00.07.05")):
            raw, profile = storage_fixture(family, model, version)
            self.error(lambda: NativeAdapter(raw, family).apply([], profile), "INVALID_STORAGE_SOURCE")
        raw, profile = storage_fixture(model="-1341103792")
        self.assertTrue(validate_source(NativeAdapter(raw, "delta_dopsoft2"), profile["native_schema"]))
        document = deepcopy(self.adapter.document)
        _element(_screen(document, "1"), "5")["section"].one("MemFmt").set_value(b"1")
        altered = self.adapter.envelope.encode(document.bytes())
        profile = qualify_storage(qualify_control_generation(altered, self.profile))
        self.error(lambda: NativeAdapter(altered, self.adapter.family).apply([], profile))
        adapter = NativeAdapter(self.raw, self.adapter.family); adapter.document.tail += b"x"
        self.error(lambda: validate_source(adapter, self.schema), "INVALID_STORAGE_SOURCE")

    def test_saved_width_format_limit_digit_scaling_macro_and_unknown_corruption_is_not_normalized(self):
        candidate = self.output()
        for before, after in ((b"MemLen=1", b"MemLen=2"), (b"MemFmt=1", b"MemFmt=3"),
            (b"MinValue=-32768", b"MinValue=-32769"), (b"MaxValue=32767", b"MaxValue=32768"),
            (b"MinValue=-32768", b"MinValue=32767"), (b"MinValue=-32768", b"MinValue=-0"),
            (b"MaxValue=32767", b"MaxValue=32767.0"), (b"DotNum=0", b"DotNum=1"),
            (b"IntNum=5", b"IntNum=05"), (b"GainValue=1.0", b"GainValue=2.0"),
            (b"Roundoff=0", b"Roundoff=1"), (b"ReadMemType=0", b"ReadMemType=128"),
            (b"VisibleVar=None", b"VisibleVar={Link2}1@M0"), (b"UsePictureCoord=0", b"UsePictureCoord=1"),
            (b"BeforeExecMacroLen=0\r\n", b"BeforeExecMacroLen=3\r\nx\r\n"),
            (b"MemFmt=1\r\n", b"MemFmt=1\r\nHiddenNew=1\r\n")):
            bad = self.mutate_owner(candidate, before, after)
            self.error(lambda: bad.verify_control_generation(self.schema, self.adapter))
        display = self.output("numeric_display")
        altered = self.mutate_owner(display, b"MemFmt=1\r\n", b"MemFmt=1\r\nMinValue=0\r\n")
        self.error(lambda: altered.verify_control_generation(self.schema, self.adapter))
        self.assertEqual(self.adapter.original, self.raw)

    def test_original_uint_and_separately_qualified_fixed_display_are_byte_unchanged(self):
        base = deepcopy(self.profile)
        del base["native_schema"]["storage_conversion"]
        del base["native_schema"]["numeric"]["types"]["INT"]
        from test_addresses import address_operations
        # Exact captured M0/D0 bindings retain the prior six-control behavior.
        ops = address_operations(base, ("M0", "M0", "M0", "M0", "D0", "D0"))
        self.assertEqual(self.adapter.apply(ops, base), self.adapter.apply(ops, self.profile))
        fixed = qualify_storage(qualify_fixed(base, self.raw))
        fixed_output = self.adapter.apply(fixed_operations(fixed), fixed)
        self.assertEqual(fixed_output, self.adapter.apply(fixed_operations(qualify_fixed(base, self.raw)), qualify_fixed(base, self.raw)))
        candidate = NativeAdapter(self.adapter.apply(fixed_operations(fixed) + signed_operations(fixed, "numeric_display", "21"), fixed), self.adapter.family)
        self.assertEqual(self.owner(candidate)["section"].one("MemFmt").value, b"2")
        self.assertEqual(self.owner(candidate)["section"].one("DotNum").value, b"2")
        self.assertEqual(self.owner(candidate, "21")["section"].one("MemFmt").value, b"1")
        self.assertEqual(self.owner(candidate, "21")["section"].one("DotNum").value, b"0")
        self.error(lambda: self.adapter.apply(signed_operations(fixed, fractional_digits=1), fixed), "UNQUALIFIED_STORAGE_NUMERIC")

    def test_multipage_forwards_explicit_conversion_without_importing_aux_globals(self):
        target_raw, controls_raw, layout_raw, schema = multipage_fixture()
        target_raw, controls_raw, layout_raw = [retarget(raw, "delta_dopsoft2") for raw in (target_raw, controls_raw, layout_raw)]
        contract = schema["multipage_program"]
        control_profile = {"family": "delta_dopsoft2", "model_id": "2953863504", "editor_version": "4.00.07.04",
                           "native_schema": contract["controls_schema"]}
        control_profile = qualify_storage(qualify_control_generation(controls_raw, control_profile))
        contract.update(target_sha256=sha(target_raw), controls_sha256=sha(controls_raw), layout_sha256=sha(layout_raw),
                        controls_schema=control_profile["native_schema"])
        target, controls, layout = [NativeAdapter(raw, "delta_dopsoft2") for raw in (target_raw, controls_raw, layout_raw)]
        program = MultiPageProgram(target, controls, layout, schema)
        operations = mixed_operations(schema)
        converted = []
        for operation in operations:
            if operation["op"] == "configure_numeric":
                operation = deepcopy(operation)
                operation["data_type"] = "INT"
                if operation["kind"] == "numeric_input":
                    operation.update(minimum=-32768, maximum=32767)
                converted.append({"op": "convert_numeric_storage", "screen_id": operation["screen_id"],
                                  "element_id": operation["element_id"], "data_type": "INT"})
            converted.append(operation)
        candidate = NativeAdapter(program.apply(converted), "delta_dopsoft2")
        self.assertTrue(program.verify(candidate))
        self.assertEqual([page["id"] for page in _groups(candidate.document)], ["1", "2", "3"])
        signed = [owner for page in _groups(candidate.document) for owner in page["elements"] if owner["id"] in {"24", "25"}]
        self.assertEqual([owner["section"].one("MemFmt").value for owner in signed], [b"1", b"1"])
        self.assertNotIn(b"HMIPortNr0=1660265583", candidate.envelope.body)
        self.assertEqual(target.original, target_raw)
        self.assertEqual(controls.original, controls_raw)
        self.assertEqual(layout.original, layout_raw)


if __name__ == "__main__":
    unittest.main()
