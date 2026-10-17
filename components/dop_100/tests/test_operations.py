# SPDX-License-Identifier: Apache-2.0
import unittest

from universal_diascreen_hmi.errors import AgentError, digest
from universal_diascreen_hmi.native import Project, layout_digest, restore_spans
from universal_diascreen_hmi.operations import compile_changes, address_inventory
from universal_diascreen_hmi.resources import embedded_xml, flat_dib, resource, resource_patch
from universal_diascreen_hmi.macros import MacroProgram, MacroInstruction
from tests.fixtures import native, payload, profile, wrap, line, element, wide, xml


def qualified(data):
    p = profile(); p['indexed_layout_sha256'] = layout_digest(Project(data)); return p


def with_macro():
    program = MacroProgram((MacroInstruction(bytes.fromhex('0a00011b'),
                            (b'BITON DIA_TAG@{Link1}0.Main.Start', b'{Link1}0@Main.Start', b'', b'', b'')),))
    blob = program.to_bytes()
    return wrap(payload().replace(b'InitialMacroLen=0\r\n', line('InitialMacroLen', len(blob)) + blob)), blob


class OperationTests(unittest.TestCase):
    def fail(self, operation, data=None, code=None, p=None, donors=None):
        data = data or native()
        with self.assertRaises(AgentError) as ctx:
            compile_changes(data, [operation], p or qualified(data), donors)
        if code:
            self.assertEqual(ctx.exception.code, code)

    def test_visual_geometry_and_full_inverse(self):
        data = native()
        candidate, steps = compile_changes(data, [{'op': 'set_property', 'page_id': 1, 'element_id': 10, 'field': 'Width', 'value': 100}], profile())
        q = Project(candidate)
        self.assertEqual(q.index.number(q.element(1, 10).section, 'Width'), 100)
        self.assertEqual(restore_spans(q.file.payload, steps[0]['ledger']), Project(data).file.payload)
        self.assertEqual(q.file.thumbnail, Project(data).file.thumbnail)

    def test_r01_r02_invalid_rectangles(self):
        for field, value in [('Width', 0), ('Height', -1), ('X', -1), ('X', 399), ('Y', 240), ('Width', True)]:
            self.fail({'op': 'set_property', 'page_id': 1, 'element_id': 10, 'field': field, 'value': value})

    def test_r03_r11_no_negative_identity_or_state(self):
        self.fail({'op': 'delete_element', 'page_id': 1, 'element_id': -1}, code='INTEGER')
        self.fail({'op': 'set_text', 'page_id': 1, 'element_id': 10, 'state_value': -1, 'text': 'bad'}, code='INTEGER')

    def test_r05_exact_rebind_not_prefix(self):
        op = {'op': 'rebind', 'page_id': 1, 'element_id': 10, 'field': 'WriteVar', 'expected_address': 'DIA_TAG@{Link1}0.Main.Start', 'address': 'DIA_TAG@{Link1}0.Main.Start2'}
        result, _ = compile_changes(native(), [op], profile())
        q = Project(result)
        self.assertEqual(q.index.scalar(q.element(1, 10).section, 'WriteVar'), op['address'])
        self.assertEqual(q.index.scalar(q.element(1, 11).section, 'WriteVar'), op['address'])
        op['expected_address'] = 'Main.Start'; self.fail(op, code='PRECONDITION')
        op['expected_address'] = 'DIA_TAG@{Link1}0.Main.Start'; op['address'] = 'DIA_TAG@{Link1}0.Main.Trigger'; self.fail(op)
        op['address'] = 'DIA_TAG@{Link1}0.Main.Value'; self.fail(op, code='REBIND_TYPE')

    def test_r06_counted_lengths_not_generic_properties(self):
        self.fail({'op': 'set_property', 'page_id': 1, 'element_id': 10, 'field': 'wTextLen0', 'value': 999})

    def test_r12_turkish_caption_and_long_unicode(self):
        text = 'ÇENE İĞNE — ŞÜ öç 𝄞' * 20
        result, _ = compile_changes(native(), [{'op': 'set_text', 'page_id': 1, 'element_id': 10, 'state_value': 1, 'text': text}], profile())
        q = Project(result)
        self.assertEqual(q.index.text(q.element(1, 10).states[1], 'wTextLen0'), text)
        self.assertEqual(q.index.text(q.element(1, 10).states[0], 'wTextLen0'), 'START')

    def test_r14_real_behavior_codes_and_value_text(self):
        result, _ = compile_changes(native(), [{'op': 'button_behavior', 'page_id': 1, 'element_id': 10, 'behavior': 'maintained'},
                   {'op': 'set_text', 'page_id': 1, 'element_id': 10, 'state_value': 1, 'text': 'AÇIK'}], profile())
        q = Project(result)
        self.assertEqual(q.index.number(q.element(1, 10).section, 'SubType'), 4)
        self.assertEqual(q.index.text(q.element(1, 10).states[1], 'wTextLen0'), 'AÇIK')
        self.fail({'op': 'button_behavior', 'page_id': 1, 'element_id': 10, 'behavior': 'set_on'}, code='BEHAVIOR_UNQUALIFIED')

    def test_r15_limits_explicit_and_no_float_extremes_or_time_alias(self):
        spec = {'iec_type': 'LREAL', 'minimum': '-999', 'maximum': '999', 'integer_digits': 3, 'decimals': 2, 'gain': '0.1', 'offset': '0'}
        op = {'op': 'numeric', 'page_id': 1, 'element_id': 12, 'spec': spec}
        result, _ = compile_changes(native(), [op], profile())
        q = Project(result)
        self.assertEqual(q.index.scalar(q.element(1, 12).section, 'MaxValue'), '999')
        for key, value in [('maximum', '1e308'), ('maximum', '1000'), ('minimum', 'NaN'), ('gain', '0'), ('iec_type', 'TIME')]:
            changed = dict(op, spec={**spec, key: value}); self.fail(changed)
        self.fail(dict(op, element_id=10))

    def test_clone_unique_fresh_identity_geometry_and_reorder(self):
        data = native(); donor = Project(data)
        op = {'op': 'clone_element', 'donor_id': 'seed', 'donor_page_id': 1, 'donor_element_id': 10,
              'page_id': 2, 'new_element_id': 20, 'name': 'New', 'retain_bindings': True,
              'rect': {'X': 20, 'Y': 30, 'Width': 120, 'Height': 50}}
        result, _ = compile_changes(data, [op], profile(), {'seed': donor})
        q = Project(result); self.assertEqual(q.index.number(q.element(2, 20).section, 'X'), 20)
        self.fail(dict(op, page_id=1, new_element_id=10), donors={'seed': donor}, code='DUPLICATE_CLONE')
        result, _ = compile_changes(data, [{'op': 'reorder_element', 'page_id': 1, 'order': [13, 12, 11, 10]}], profile())
        q = Project(result); self.assertEqual([q.index.number(e.section, 'nPartsID') for e in q.page(1).elements], [13, 12, 11, 10])

    def test_screen_frame_clone_delete_and_navigation_guards(self):
        data = native()
        result, _ = compile_changes(data, [{'op': 'clone_screen', 'donor_id': 'seed', 'donor_page_id': 2, 'new_page_id': 3, 'name': 'Third'},
                      {'op': 'delete_screen', 'page_id': 2}, {'op': 'default_screen', 'page_id': 3}], profile(), {'seed': Project(data)})
        self.assertEqual([p.page_id for p in Project(result).pages], [1, 3])
        self.fail({'op': 'delete_screen', 'page_id': 1}, code='DEFAULT_PAGE')
        self.fail({'op': 'navigation', 'page_id': 1, 'element_id': 10, 'target_page_id': 2}, code='CONTROL_TYPE')

    def test_frame_clone_inherited_macro_requires_ack(self):
        data, blob = with_macro()
        body = Project(data).file.payload.replace(b'[AuxKeyElement]\r\n', b'[AuxKeyElement]\r\n' + line('OpenMacroLen', len(blob)) + blob, 1)
        data = wrap(body)
        self.fail({'op': 'clone_screen', 'donor_id': 'seed', 'donor_page_id': 1, 'new_page_id': 3, 'name': 'Third'}, data=data, donors={'seed': Project(data)}, code='DONOR_MACROS')

    def test_cross_file_donor_resource_mismatch_rejected(self):
        donor = Project(wrap(payload().replace(b'DiaTagXmlPath=neutral.xml', b'DiaTagXmlPath=another.xml')))
        self.fail({'op': 'clone_screen', 'donor_id': 'seed', 'donor_page_id': 2, 'new_page_id': 3, 'name': 'Third'}, donors={'seed': donor}, code='DONOR_DEPENDENCIES')

    def test_xml_preserves_metadata_and_all_dependencies(self):
        q = Project(native()); frame, old = embedded_xml(q)
        replacement = xml().replace(b'size="32"', b'size="40"')
        result, _ = compile_changes(native(), [{'op': 'replace_xml', 'xml': replacement.decode(), 'expected_xml_sha256': digest(old)}], profile())
        f, new = embedded_xml(Project(result)); self.assertEqual(new, replacement)
        self.assertEqual(f.metadata['DiaTagXmlPath'], frame.metadata['DiaTagXmlPath'])
        removed = xml().replace(b'iecname="Start2"', b'iecname="Removed"')
        self.fail({'op': 'replace_xml', 'xml': removed.decode(), 'expected_xml_sha256': digest(old)})
        retyped = xml().replace(b'name="BoolType" size="1" typeclass="Bool" iecname="BOOL"', b'name="BoolType" size="8" typeclass="Real" iecname="LREAL"')
        self.fail({'op': 'replace_xml', 'xml': retyped.decode(), 'expected_xml_sha256': digest(old)}, code='XML_TYPE_DRIFT')

    def test_xml_unknown_address_dependency_blocks_removal(self):
        data = wrap(payload().replace(b'VisibleVar=None', b'UnknownAddress=DIA_TAG@{Link1}0.Main.Start\r\nVisibleVar=None', 1))
        self.fail({'op': 'replace_xml', 'xml': xml().decode(), 'expected_xml_sha256': digest(xml())}, data=data, code='ADDRESS_ROLE')

    def test_catalog_cannot_use_another_link_permission(self):
        foreign = (b'[DIATag]\r\nDIATagLinkName=OtherLink\r\nDIATagStationNr=9\r\n' + line('size', len(xml())) + xml() + b'\r\n')
        data = wrap(payload().replace(b'[END]\r\n', foreign + b'[END]\r\n'))
        self.fail({'op': 'rebind', 'page_id': 1, 'element_id': 10, 'field': 'WriteVar', 'expected_address': 'DIA_TAG@{Link1}0.Main.Start',
                   'address': 'DIA_TAG@{Link1}0.Main.Start2', 'xml_index': 1}, data=data, code='CATALOG_TARGET')

    def test_partial_foreign_catalog_metadata_not_overridden(self):
        data = wrap(payload().replace(b'DIATagLinkName=Link1\r\nDIATagStationNr=0', b'DIATagLinkName=OtherLink'))
        p = qualified(data); p['catalog_bindings'] = {'0': {'reviewed': True, 'xml_sha256': digest(xml()), 'link': 'Link1', 'station': 0}}
        self.fail({'op': 'rebind', 'page_id': 1, 'element_id': 10, 'field': 'WriteVar', 'expected_address': 'DIA_TAG@{Link1}0.Main.Start',
                   'address': 'DIA_TAG@{Link1}0.Main.Start2'}, data=data, p=p, code='CATALOG_TARGET')

    def test_xml_alternate_anchor_and_explicit_member_shadow_rejected(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml()); ns = '{http://www.3s-software.com/schemas/Symbolconfiguration.xsd}'
        types = root.find(ns + 'TypeList'); original = types.find(ns + 'TypeUserDef')
        alternate = ET.fromstring(ET.tostring(original)); alternate.set('name', 'AlternateMain')
        alternate.find(ns + 'UserDefElement').set('type', 'RealType'); types.append(alternate)
        anchor = root.find('.//' + ns + 'Node[@name="Main"]'); anchor.set('type', 'AlternateMain')
        self.fail({'op': 'replace_xml', 'xml': ET.tostring(root, encoding='unicode'), 'expected_xml_sha256': digest(xml())}, code='XML_TYPE_DRIFT')
        anchor.set('type', 'MainType'); ET.SubElement(anchor, ns + 'Node', {'name': 'Start', 'type': 'RealType', 'access': 'ReadWrite'})
        self.fail({'op': 'replace_xml', 'xml': ET.tostring(root, encoding='unicode'), 'expected_xml_sha256': digest(xml())}, code='XML_TYPE_DRIFT')

    def test_macro_slot_type_access_and_visible_source(self):
        data, blob = with_macro(); p = qualified(data)
        p['macro_slots'] = {'0a00011b:1': {'kind': 'remote', 'role': 'write', 'iec_types': ['BOOL'], 'evidence': 'neutral fixture'}}
        op = {'op': 'patch_macro_operand', 'section_index': 0, 'slot': 'InitialMacroLen', 'expected_macro_sha256': digest(blob),
              'instruction_index': 0, 'field_index': 1, 'expected': '{Link1}0@Main.Start', 'value': '{Link1}0@Main.Start2'}
        result, _ = compile_changes(data, [op], p)
        self.assertIn(b'BITON DIA_TAG@{Link1}0.Main.Start', Project(result).app.one('InitialMacroLen').blob(Project(result).file.payload))
        self.fail(dict(op, field_index=4, expected='', value='{OtherLink}9@NotPublished'), data=data, p=p, code='MACRO_SLOT_UNQUALIFIED')
        self.fail(dict(op, value='{Link1}0@Main.Trigger'), data=data, p=p)
        self.fail(dict(op, value='DIA_TAG@{Link1}0.Main.Start2'), data=data, p=p)
        removed = xml().replace(b'iecname="Start"', b'iecname="Removed"')
        self.fail({'op': 'replace_xml', 'xml': removed.decode(), 'expected_xml_sha256': digest(xml())}, data=data, p=p)

    def test_r18_clear_global_macro_not_default_reenable(self):
        data, blob = with_macro()
        result, _ = compile_changes(data, [{'op': 'clear_macro', 'section_index': 0, 'slot': 'InitialMacroLen', 'expected_macro_sha256': digest(blob)}], qualified(data))
        q = Project(result); self.assertEqual(q.app.one('InitialMacroLen').blob(q.file.payload), b'')

    def test_flat_background_has_real_page_offset_and_no_old_text(self):
        q = Project(native()); f = resource(q, 'Background', 'Size'); old = q.file.payload[f.blob_start:f.blob_end]
        result, _ = compile_changes(native(), [{'op': 'flat_background', 'page_ids': [2], 'rgb': 0x123456, 'expected_bank_sha256': digest(old)}], profile())
        q = Project(result); f = resource(q, 'Background', 'Size'); blob = q.file.payload[f.blob_start:f.blob_end]
        self.assertEqual(q.index.number(q.page(2).section, 'PictureOffset'), len(old))
        self.assertEqual(blob[len(old):], flat_dib(400, 240, 0x123456))
        self.assertEqual(q.index.number(q.page(1).section, 'PictureOffset'), 0)

    def test_r10_all_indexed_address_owners_and_trigger(self):
        data = wrap(payload().replace(b'[AuxKeyElement]\r\n', b'[AuxKeyElement]\r\nReadVar=DIA_TAG@{Link1}0.Main.Display\r\n', 1))
        rows = address_inventory(Project(data), False)
        self.assertTrue(any(r['field'] == 'TriggerVar' for r in rows))
        self.assertTrue(any(r.get('auxiliary') and r['field'] == 'ReadVar' for r in rows))

    def test_future_counted_owner_is_not_editable_screen(self):
        fake = b'[Screen]\r\nID=77\r\n' + wide('wTextLen', 'Fake') + element(77, 'Fake')
        body = payload(); offset = Project(native()).page(1).section.start
        data = wrap(body[:offset] + line('FutureBlobLen', len(fake)) + fake + body[offset:])
        self.assertEqual(Project(data).index.stop_reason, 'unknown_frame:FutureBlobLen')
        self.fail({'op': 'set_property', 'page_id': 77, 'element_id': 77, 'field': 'X', 'value': 20}, data=data, code='INDEX_UNQUALIFIED')

    def test_counted_base64_owner_hides_structure_injection(self):
        fake = b'[Screen]\r\nID=77\r\n'
        data = wrap(payload().replace(b'MeMeCode=', line('EipDTBase64Len', len(fake)) + fake + b'\r\nMeMeCode=', 1))
        self.assertEqual([p.page_id for p in Project(data).pages], [1, 2])

    def test_unsupported_enums_and_unreviewed_index_stop(self):
        for field, value in [('Style', 9999), ('FontBold', 2), ('FontAlign', 10000), ('FontRatio0', 101)]:
            op = {'op': 'set_property', 'page_id': 1, 'element_id': 10, 'field': field, 'value': value}
            if field != 'Style': op['state_value'] = 0
            self.fail(op)
        p = profile(); p.pop('reviewed_index_ack')
        self.fail({'op': 'set_text', 'page_id': 1, 'element_id': 10, 'state_value': 0, 'text': 'x'}, p=p, code='INDEX_REVIEW')
        self.fail({'op': 'set_property', 'page_id': 1, 'element_id': 10, 'field': 'X', 'value': 20, 'overwrite_source': True}, code='OPERATION_FIELDS')

    def test_r21_style_only_preserves_controls_bindings_macro_xml_unknown(self):
        data, _ = with_macro()
        candidate, steps = compile_changes(data, [{'op': 'set_property', 'page_id': 1, 'element_id': 10, 'state_value': 0, 'field': 'FgColor', 'value': 0x123456}], qualified(data))
        old, new = Project(data), Project(candidate)
        self.assertEqual(address_inventory(old), address_inventory(new))
        self.assertEqual(old.app.one('InitialMacroLen').blob(old.file.payload), new.app.one('InitialMacroLen').blob(new.file.payload))
        self.assertEqual(embedded_xml(old)[1], embedded_xml(new)[1])
        self.assertEqual(restore_spans(new.file.payload, steps[0]['ledger']), old.file.payload)


if __name__ == '__main__': unittest.main()
