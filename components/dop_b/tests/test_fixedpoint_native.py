"""Original explicit fixed-decimal fixtures; no vendor runtime claim follows."""
from copy import deepcopy
import hashlib
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups, _element, _screen
from universal_hmi.native.numeric import fixed_decimal_contract, verify_numeric_fields
from universal_hmi.native.program import BlankProgram
from test_native import (control_generation_fixture, numeric_fixture, numeric_profile,
                         qualify_control_generation)
from test_program import blank_program_fixture


def fixed_spec(source):
    return {"qualified": True, "contract_version": 1, "mode": "integer_fixed_decimal",
            "types": ["UINT"], "max_fractional_digits": 4, "max_total_digits": 5,
            "storage_domain": "raw_integer", "limit_domain": "display", "input_lowering": "UNVERIFIED",
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "authority_sha256": hashlib.sha256(b"ORIGINAL STATIC DISPLAY TEST AUTHORITY").hexdigest(),
            "review_reference": "SYNTHETIC_FIXED_DECIMAL_DISPLAY_TEST_ONLY"}


def qualify_fixed(profile, source):
    result = deepcopy(profile)
    numeric = result["native_schema"]["numeric"]
    numeric["max_fractional_digits"] = 4
    numeric["value_models"] = {"integer_fixed_decimal": fixed_spec(source)}
    return result


def operation(kind="numeric_display", **changes):
    result = {"op": "configure_numeric", "screen_id": "1", "element_id": "1", "kind": kind,
              "data_type": "UINT", "integer_digits": 3, "fractional_digits": 2,
              "value_model": "integer_fixed_decimal", "gain": 1, "offset": 0}
    if kind == "numeric_input":
        result.update(minimum=0, maximum=999)
    return result | changes


def control_operations(profile, kind="numeric_display", **changes):
    pin = profile["native_schema"]["control_generation"]["donors"][kind]
    configure = operation(kind, **({"element_id": "20"} | changes))
    element_id = configure["element_id"]
    return [{"op": "clone_element", "source_screen": pin["screen_id"], "source_element": pin["element_id"],
             "target_screen": "1", "element_id": element_id},
            {"op": "bind", "screen_id": "1", "element_id": element_id,
             "read" if kind == "numeric_display" else "write": {"address": "{Link2}1@D0", "link": 1, "mem_type": 0}},
            configure]


class FixedDecimalNativeTests(unittest.TestCase):
    def assert_error(self, call, code=None):
        with self.assertRaises(HmiError) as caught:
            call()
        if code is not None:
            self.assertEqual(caught.exception.code, code)

    def fields(self, raw, family="delta_diascreen", element_id="1"):
        inventory = NativeAdapter(raw, family).inspect()
        return next(e["native_fields"] for s in inventory["screens"] for e in s["elements"] if e["id"] == element_id)

    def test_no_opt_in_retains_raw_numeric_contract_and_exact_noop(self):
        for family in ("delta_dopsoft2", "delta_diascreen"):
            raw = numeric_fixture("UINT", "numeric_input", family)
            adapter = NativeAdapter(raw, family)
            raw_op = operation("numeric_input", maximum=100, integer_digits=5, fractional_digits=0)
            raw_op.pop("value_model")
            self.assertEqual(adapter.apply([raw_op], numeric_profile(family)), raw)
            # Historical synthetic raw fractional settings must not silently
            # start lowering keypad limits into the displayed domain.
            raw_op["fractional_digits"] = 1
            output = adapter.apply([raw_op], numeric_profile(family))
            self.assertEqual(self.fields(output, family)["MaxValue"], "100")

    def test_explicit_display_changes_only_existing_digit_fields(self):
        for family in ("delta_dopsoft2", "delta_diascreen"):
            raw = numeric_fixture("UINT", "numeric_display", family)
            profile = qualify_fixed(numeric_profile(family), raw)
            adapter = NativeAdapter(raw, family)
            output = adapter.apply([operation()], profile)
            expected = adapter.envelope.body.replace(b"IntNum=5\r\n", b"IntNum=3\r\n").replace(b"DotNum=0\r\n", b"DotNum=2\r\n")
            candidate = NativeAdapter(output, family)
            self.assertEqual(candidate.envelope.body, expected)
            self.assertEqual(candidate.envelope.prefix, adapter.envelope.prefix)
            self.assertEqual(candidate.envelope.thumbnail, adapter.envelope.thumbnail)
            fields = self.fields(output, family)
            self.assertEqual((fields["MemLen"], fields["MemFmt"], fields["GainValue"], fields["OffsetValue"]), ("1", "2", "1.0", "0.000000"))
            self.assertNotIn("MinValue", fields)
            self.assertNotIn("MaxValue", fields)
            self.assertTrue(verify_numeric_fields(fields, operation(), profile["native_schema"]))
            self.assertEqual(candidate.apply([operation()], profile), output)

    def test_display_fractional_bounds_and_total_digit_capacity(self):
        raw = numeric_fixture("UINT", "numeric_display")
        profile = qualify_fixed(numeric_profile(), raw)
        adapter = NativeAdapter(raw, "delta_diascreen")
        for integer, fractional in ((5, 0), (4, 1), (3, 2), (2, 3), (1, 4), (1, 1)):
            output = adapter.apply([operation(integer_digits=integer, fractional_digits=fractional)], profile)
            fields = self.fields(output)
            self.assertEqual((fields["IntNum"], fields["DotNum"]), (str(integer), str(fractional)))
        for change in ({"integer_digits": 4}, {"fractional_digits": 5}, {"integer_digits": 0}, {"fractional_digits": True}):
            self.assert_error(lambda: adapter.apply([operation(**change)], profile), "NUMERIC_DIGITS")

    def test_fractional_input_lowering_is_not_silently_enabled(self):
        raw = numeric_fixture("UINT", "numeric_input")
        profile = qualify_fixed(numeric_profile(), raw)
        adapter = NativeAdapter(raw, "delta_diascreen")
        for minimum, maximum in ((0, 999), (29, 58), (0, 123), (0, 65535)):
            self.assert_error(lambda: adapter.apply([operation("numeric_input", minimum=minimum, maximum=maximum)], profile), "UNQUALIFIED_FIXED_DECIMAL")
            self.assertEqual(adapter.apply([], {}), raw)
        # Explicit F0 has no keypad-domain conversion and stays compatible.
        result = adapter.apply([operation("numeric_input", minimum=0, maximum=100, integer_digits=5, fractional_digits=0)], profile)
        self.assertEqual(result, raw)

    def test_fixed_display_cannot_inherit_or_synthesize_keypad_limits(self):
        raw = numeric_fixture("UINT", "numeric_display")
        profile = qualify_fixed(numeric_profile(), raw)
        adapter = NativeAdapter(raw, "delta_diascreen")
        for argument in ("minimum", "maximum"):
            self.assert_error(lambda: adapter.apply([operation(**{argument: 0})], profile), "INVALID_NUMERIC")
        for field in ("MinValue", "MaxValue"):
            body = adapter.envelope.body.replace(b"HiddenNumericSetting=retained\r\n", f"{field}=0\r\nHiddenNumericSetting=retained\r\n".encode())
            modified = NativeAdapter(adapter.envelope.encode(body), adapter.family)
            self.assert_error(lambda: modified.apply([operation()], profile), "UNQUALIFIED_FIXED_DECIMAL")

    def test_descriptor_requires_exact_bounded_types_and_provenance(self):
        raw = numeric_fixture("UINT", "numeric_display")
        profile = qualify_fixed(numeric_profile(), raw)
        for change in ({"qualified": False}, {"contract_version": True}, {"contract_version": 2}, {"mode": "raw"},
                       {"types": ["UINT", "INT"]}, {"types": "UINT"}, {"max_fractional_digits": True}, {"max_fractional_digits": 5},
                       {"max_total_digits": 6}, {"storage_domain": "display"}, {"limit_domain": "raw"}, {"input_lowering": "PASS"},
                       {"source_sha256": "A" * 64}, {"authority_sha256": "0" * 63}, {"review_reference": " x"},
                       {"review_reference": "a\nb"}, {"review_reference": "x" * 257}, {"extra": True}):
            altered = deepcopy(profile)
            altered["native_schema"]["numeric"]["value_models"]["integer_fixed_decimal"].update(change)
            self.assert_error(lambda: NativeAdapter(raw, "delta_diascreen").apply([operation()], altered), "UNQUALIFIED_FIXED_DECIMAL")
        for models in (None, {}, [], {"raw": fixed_spec(raw)}, {"integer_fixed_decimal": None}):
            altered = deepcopy(profile)
            altered["native_schema"]["numeric"]["value_models"] = models
            self.assert_error(lambda: fixed_decimal_contract(altered["native_schema"]), "UNQUALIFIED_FIXED_DECIMAL")
        copied = fixed_decimal_contract(profile["native_schema"])
        copied["types"].append("INT")
        self.assertEqual(profile["native_schema"]["numeric"]["value_models"]["integer_fixed_decimal"]["types"], ["UINT"])

    def test_descriptor_deep_or_cyclic_scalars_are_typed_without_copy_recursion(self):
        raw = numeric_fixture("UINT", "numeric_display")
        for value in ([], {}):
            value.append(value) if isinstance(value, list) else value.update(cycle=value)
            schema = qualify_fixed(numeric_profile(), raw)["native_schema"]
            schema["numeric"]["value_models"]["integer_fixed_decimal"]["review_reference"] = value
            self.assert_error(lambda: fixed_decimal_contract(schema), "UNQUALIFIED_FIXED_DECIMAL")
        deep = 0
        for _ in range(1500):
            deep = [deep]
        schema = qualify_fixed(numeric_profile(), raw)["native_schema"]
        schema["numeric"]["value_models"]["integer_fixed_decimal"]["source_sha256"] = deep
        self.assert_error(lambda: fixed_decimal_contract(schema), "UNQUALIFIED_FIXED_DECIMAL")

    def test_fixed_display_storage_model_and_scaling_cannot_drift(self):
        raw = numeric_fixture("UINT", "numeric_display")
        profile = qualify_fixed(numeric_profile(), raw)
        adapter = NativeAdapter(raw, "delta_diascreen")
        for change in ({"value_model": None}, {"value_model": "raw"}, {"value_model": []}, {"data_type": "INT"},
                       {"data_type": "REAL"}, {"gain": 2}, {"offset": 1}):
            self.assert_error(lambda: adapter.apply([operation(**change)], profile))
        for before, after in ((b"GainValue=1.0", b"GainValue=2.0"), (b"OffsetValue=0.000000", b"OffsetValue=1.000000"),
                              (b"MemLen=1", b"MemLen=2"), (b"MemFmt=2", b"MemFmt=1")):
            modified = NativeAdapter(adapter.envelope.encode(adapter.envelope.body.replace(before, after, 1)), adapter.family)
            self.assert_error(lambda: modified.apply([operation()], profile))

    def test_final_verification_rejects_digit_and_storage_tamper(self):
        raw = numeric_fixture("UINT", "numeric_display")
        profile = qualify_fixed(numeric_profile(), raw)
        output = NativeAdapter(raw, "delta_diascreen").apply([operation()], profile)
        fields = self.fields(output)
        for change in ({"DotNum": "1"}, {"IntNum": "2"}, {"DotNum": "02"}, {"GainValue": "2"},
                       {"MemFmt": "1"}, {"MemLen": "2"}, {"MinValue": "0"}, {"MaxValue": "9.99"}):
            self.assert_error(lambda: verify_numeric_fields(fields | change, operation(), profile["native_schema"]))

    def test_control_generation_accepts_saved_display_and_keeps_source_donors(self):
        raw, base = control_generation_fixture()
        profile = qualify_fixed(base, raw)
        adapter = NativeAdapter(raw, profile["family"])
        self.assertEqual(adapter.apply([], profile), raw)
        output = adapter.apply(control_operations(profile), profile)
        candidate = NativeAdapter(output, profile["family"])
        self.assertTrue(candidate.verify_control_generation(profile["native_schema"], adapter))
        fields = self.fields(output, profile["family"], "20")
        self.assertEqual((fields["IntNum"], fields["DotNum"], fields["MemLen"], fields["MemFmt"]), ("3", "2", "1", "2"))
        before = _groups(adapter.document)[0]["elements"]
        after = _groups(candidate.document)[0]["elements"]
        for old, current in zip(before, after):
            old_bytes = b"".join(s.bytes() for s in adapter.document.sections[old["start"]:old["end"]])
            new_bytes = b"".join(s.bytes() for s in candidate.document.sections[current["start"]:current["end"]])
            self.assertEqual(old_bytes, new_bytes)

    def test_control_descriptor_drift_and_implicit_fractional_operations_are_closed(self):
        raw, base = control_generation_fixture()
        profile = qualify_fixed(base, raw)
        adapter = NativeAdapter(raw, profile["family"])
        for kind in ("numeric_display", "numeric_input"):
            operations = control_operations(profile, kind)
            operations[-1].pop("value_model")
            self.assert_error(lambda: adapter.apply(operations, profile), "UNQUALIFIED_CONTROL_NUMERIC")
        self.assert_error(lambda: adapter.apply(control_operations(profile, "numeric_input"), profile), "UNQUALIFIED_FIXED_DECIMAL")
        changed = deepcopy(profile)
        changed["native_schema"]["numeric"]["value_models"]["integer_fixed_decimal"]["source_sha256"] = "0" * 64
        self.assert_error(lambda: adapter.apply([], changed), "UNQUALIFIED_FIXED_DECIMAL")

    def test_blank_program_saves_fractional_display_without_library_owners(self):
        target_raw, library_raw, schema = blank_program_fixture()
        library_schema = qualify_fixed({"native_schema": schema["blank_program"]["library_schema"]}, library_raw)["native_schema"]
        schema["blank_program"]["library_schema"] = library_schema
        schema["numeric"] = deepcopy(library_schema["numeric"])
        target, library = (NativeAdapter(raw, "delta_dopsoft2") for raw in (target_raw, library_raw))
        program = BlankProgram(target, library, schema)
        output = program.apply(control_operations({"native_schema": library_schema}))
        candidate = NativeAdapter(output, "delta_dopsoft2")
        self.assertTrue(program.verify(candidate))
        self.assertEqual([owner["id"] for page in _groups(candidate.document) for owner in page["elements"]], ["20"])
        self.assertEqual(self.fields(output, "delta_dopsoft2", "20")["DotNum"], "2")
        self.assertEqual(candidate.envelope.prefix[:37], target.envelope.prefix[:37])
        self.assertEqual(candidate.envelope.thumbnail, target.envelope.thumbnail)
        self.assertEqual(target.original, target_raw)
        self.assertEqual(library.original, library_raw)

    def test_saved_fractional_input_cannot_pass_noop_or_requalified_donor_gate(self):
        raw, base = control_generation_fixture()
        adapter = NativeAdapter(raw, base["family"])
        document = deepcopy(adapter.document)
        owner = _element(_screen(document, "1"), "5")
        owner["section"].one("IntNum").set_value(b"3")
        owner["section"].one("DotNum").set_value(b"2")
        owner["section"].one("MaxValue").set_value(b"9.990")
        modified = adapter.envelope.encode(document.bytes())
        # Even manually repinning all source fingerprints does not qualify
        # the compiler's floating keypad-limit lowering.
        profile = qualify_fixed(qualify_control_generation(modified, base), modified)
        self.assert_error(lambda: NativeAdapter(modified, base["family"]).apply([], profile), "UNQUALIFIED_FIXED_DECIMAL")

    def test_failed_fixed_transaction_leaves_source_and_unmanaged_bytes_exact(self):
        raw, base = control_generation_fixture()
        profile = qualify_fixed(base, raw)
        adapter = NativeAdapter(raw, base["family"])
        operations = control_operations(profile)
        operations += control_operations(profile, "numeric_input", element_id="21")
        self.assert_error(lambda: adapter.apply(operations, profile), "UNQUALIFIED_FIXED_DECIMAL")
        self.assertEqual(adapter.original, raw)
        self.assertEqual(adapter.document.bytes(), adapter.envelope.body)
        self.assertEqual(adapter.apply([], profile), raw)


if __name__ == "__main__":
    unittest.main()
