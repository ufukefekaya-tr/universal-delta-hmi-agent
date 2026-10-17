# SPDX-License-Identifier: Apache-2.0
"""Neutral synthetic symbol metadata; no vendor or customer fixtures."""
import hashlib
import unittest

from universal_diascreen_hmi.errors import AgentError
from universal_diascreen_hmi.symbols import parse_address, parse_symbols, validate_reference


XML = b'''<?xml version="1.0" encoding="utf-8"?>
<Symbolconfiguration xmlns="http://www.3s-software.com/schemas/Symbolconfiguration.xsd">
<TypeList>
 <TypeSimple name="Flag" size="1" typeclass="Bool" iecname="BOOL"/>
 <TypeSimple name="Count" size="2" typeclass="UInt" iecname="UINT"/>
 <TypeSimple name="Span" size="4" typeclass="Time" iecname="TIME"/>
 <TypeSimple name="Bit" size="1" typeclass="Bool" iecname="BIT" bitoffset="3"/>
 <TypeArray name="Vector" size="6" nativesize="6" typeclass="Array" iecname="ARRAY [-1..1] OF UINT" basetype="Count"><ArrayDim minrange="-1" maxrange="1"/></TypeArray>
 <TypeUserDef name="Mode" size="2" typeclass="Enum" iecname="Mode" basetype="Count"><UserDefElement type="Mode" iecname="Idle" enumvalue="0"/><UserDefElement type="Mode" iecname="Ready" enumvalue="7"/></TypeUserDef>
 <TypeUserDef name="Inner" size="3" nativesize="4" typeclass="Userdef" pouclass="STRUCTURE" iecname="Inner"><UserDefElement iecname="active" type="Flag" byteoffset="0" access="ReadWrite"/><UserDefElement iecname="value" type="Count" byteoffset="2" access="ReadWrite"/></TypeUserDef>
 <TypeArray name="Rows" size="6" nativesize="8" typeclass="Array" iecname="ARRAY [2..3] OF Inner" basetype="Inner"><ArrayDim minrange="2" maxrange="3"/></TypeArray>
 <TypeUserDef name="Settings" size="21" nativesize="24" typeclass="Userdef" pouclass="STRUCTURE" iecname="Settings"><UserDefElement iecname="inner" type="Inner" byteoffset="4" access="ReadWrite"/><UserDefElement iecname="samples" type="Vector" byteoffset="10" access="ReadWrite"/><UserDefElement iecname="rows" type="Rows" byteoffset="16" access="ReadWrite"/></TypeUserDef>
</TypeList><NodeList><Node name="Runtime"><Node name="Shared" access="ReadWrite">
 <Node name="settings" type="Settings" access="ReadWrite"/>
 <Node name="status" type="Settings" access="Read"/>
 <Node name="request" type="Flag" access="Write"/>
 <Node name="duration" type="Span" access="ReadWrite"/>
 <Node name="mode" type="Mode" access="Read"/>
 <Node name="bit" type="Bit" access="Read"/>
</Node><Node name="Unspecified"><Node name="flag" type="Flag"/></Node></Node></NodeList>
</Symbolconfiguration>'''


class SymbolTests(unittest.TestCase):
    def setUp(self):
        self.catalog = parse_symbols(XML)

    def test_raw_identity_and_root_alias(self):
        self.assertEqual(self.catalog.raw, XML)
        self.assertEqual(self.catalog.sha256, hashlib.sha256(XML).hexdigest())
        self.assertEqual(self.catalog.resolve("Shared.settings.inner.value"),
                         self.catalog.resolve("Runtime.Shared.settings.inner.value"))

    def test_actual_offsets_and_native_padding(self):
        item = self.catalog.resolve("Shared.settings.inner.value")
        self.assertEqual((item["iec_type"], item["bits"], item["byte_offset"]), ("UINT", 16, 6))
        aggregate = self.catalog.resolve("Shared.settings.inner")
        self.assertEqual((aggregate["size"], aggregate["native_size"]), (3, 4))
        self.assertEqual(self.catalog.resolve("Shared.settings.rows[3].value")["byte_offset"], 22)

    def test_inclusive_array_bounds(self):
        first = self.catalog.resolve("Shared.settings.samples[-1]")
        last = self.catalog.resolve("Shared.settings.samples[1]")
        self.assertEqual((first["byte_offset"], last["byte_offset"]), (10, 14))
        for path in ("Shared.settings.samples[-2]", "Shared.settings.samples[2]"):
            with self.subTest(path=path), self.assertRaises(AgentError):
                self.catalog.resolve(path)
        self.assertEqual(self.catalog.resolve("Shared.settings.samples")["dimensions"][0]["index"], None)

    def test_ancestor_access_cannot_be_restored_by_member(self):
        item = self.catalog.resolve("Shared.status.inner.active")
        self.assertTrue(item["readable"])
        self.assertFalse(item["writable"])
        self.assertFalse(self.catalog.resolve("Unspecified.flag")["readable"])

    def test_enum_and_time_remain_distinct(self):
        mode = self.catalog.resolve("Shared.mode")
        self.assertEqual(mode["enum_values"], [{"name": "Idle", "value": 0}, {"name": "Ready", "value": 7}])
        time = self.catalog.resolve("Shared.duration")
        self.assertEqual((time["iec_type"], time["bits"]), ("TIME", 32))
        self.assertFalse(time["numeric_coercion_supported"])
        self.assertEqual(self.catalog.resolve("Shared.bit")["bit_offset"], 3)
        with self.assertRaises(AgentError):
            self.catalog.resolve("Shared.mode.Ready")

    def test_role_specific_read_and_write_permissions(self):
        request = "DIA_TAG@{ControlLink}0.Shared.request"
        self.assertEqual(parse_address(request)["station"], 0)
        validate_reference(request, "WriteVar", self.catalog, "ControlLink", 0)
        for role in ("ReadVar", "TriggerVar", "InterLockVar", "VisibleVar"):
            with self.subTest(role=role), self.assertRaises(AgentError):
                validate_reference(request, role, self.catalog, "ControlLink", 0)
        readonly = "DIA_TAG@{ControlLink}0.Shared.status.inner.active"
        validate_reference(readonly, "ReadVar", self.catalog, "ControlLink", 0)
        with self.assertRaises(AgentError):
            validate_reference(readonly, "WriteVar", self.catalog, "ControlLink", 0)

    def test_wrong_target_role_and_display_syntax(self):
        address = "DIA_TAG@{ControlLink}0.Shared.mode"
        for link, station in (("OtherLink", 0), ("ControlLink", 1)):
            with self.subTest(link=link, station=station), self.assertRaises(AgentError):
                validate_reference(address, "ReadVar", self.catalog, link, station)
        with self.assertRaises(AgentError):
            validate_reference(address, "whatever", self.catalog, "ControlLink", 0)
        with self.assertRaises(AgentError):
            parse_address("{ControlLink}0@Shared.mode")

    def test_inventory_is_bounded_and_includes_access(self):
        inventory = self.catalog.inventory()
        self.assertEqual(len(inventory), 7)
        self.assertTrue(all("readable" in item and "type_name" in item for item in inventory))

    def test_duplicate_unknown_and_cyclic_types_rejected(self):
        bad = [XML.replace(b'<TypeSimple name="Count"', b'<TypeSimple name="Flag"'),
               XML.replace(b'type="Flag" access="Write"', b'type="Missing" access="Write"'),
               XML.replace(b'iecname="active" type="Flag"', b'iecname="active" type="Settings"'),
               XML.replace(b'<Node name="request"', b'<Node name="mode"'),
               XML.replace(b'access="Write"', b'access="Arbitrary"')]
        for document in bad:
            with self.subTest(document=document[:40]), self.assertRaises(AgentError):
                parse_symbols(document)

    def test_xml_attacks_and_wrong_structure_rejected(self):
        dtd = '<!DOCTYPE Symbolconfiguration [<!ENTITY x "expanded">]><Symbolconfiguration/>'
        for document in (dtd.encode(), dtd.encode("utf-16"), b'<wrong/>', XML.replace(b'maxrange="1"', b'maxrange="-2"'), XML.replace(b'Symbolconfiguration.xsd', b'Other.xsd')):
            with self.subTest(document=document[:40]), self.assertRaises(AgentError):
                parse_symbols(document)

    def test_unknown_member_layout_stays_unknown(self):
        document = XML.replace(b'iecname="inner" type="Inner" byteoffset="4"', b'iecname="inner" type="Inner"')
        self.assertIsNone(parse_symbols(document).resolve("Shared.settings.inner.value")["byte_offset"])
        document = XML.replace(b'name="Inner" size="3" nativesize="4"', b'name="Inner" size="3"')
        self.assertIsNone(parse_symbols(document).resolve("Shared.settings.rows[3].value")["byte_offset"])

    def test_scalar_index_and_unindexed_array_traversal_rejected(self):
        for path in ("Shared.mode[0]", "Shared.settings.rows.value", "Shared.settings.samples[0,1]", "Runtime.Runtime.Shared.mode"):
            with self.subTest(path=path), self.assertRaises(AgentError):
                self.catalog.resolve(path)

    def test_untrusted_integer_and_unknown_base_are_structured_failures(self):
        for document in (XML.replace(b'size="1"', b'size="' + b"1" * 5000 + b'"', 1),
                         XML.replace(b'name="Flag" size="1"', b'name="Flag" size="1" basetype="Missing"'),
                         XML.replace(b'name="Flag" size="1"', b'name="Flag" size="0"')):
            with self.subTest(document=document[:40]), self.assertRaises(AgentError):
                parse_symbols(document)
        with self.assertRaises(AgentError):
            parse_address("DIA_TAG@{ControlLink}" + "1" * 5000 + ".Shared.mode")

    def test_top_level_array_offset_anchor_has_no_index(self):
        document = XML.replace(b'<Node name="bit" type="Bit" access="Read"/>',
                               b'<Node name="bit" type="Rows" access="Read"/>')
        symbol = parse_symbols(document).resolve("Shared.bit[3].value")
        self.assertEqual(symbol["offset_base"], "Runtime.Shared.bit")
        self.assertEqual(symbol["byte_offset"], 6)


if __name__ == "__main__":
    unittest.main()
