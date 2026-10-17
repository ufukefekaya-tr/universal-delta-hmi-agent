# SPDX-License-Identifier: Apache-2.0
import unittest
from universal_diascreen_hmi.errors import AgentError
from universal_diascreen_hmi.native import NativeFile, NativeIndex, Patch, Project, apply_spans, encode_token, restore_spans
from universal_diascreen_hmi.resources import embedded_xml, resource, resource_patch
from tests.fixtures import native, payload, wrap, wide, xml


class NativeTests(unittest.TestCase):
    def test_noop_original_container(self):
        data = native()
        project = Project(data)
        self.assertEqual(project.file.encode(project.file.payload), data)
        self.assertEqual((len(project.pages), sum(len(p.elements) for p in project.pages)), (2, 4))

    def test_frame_injection_stays_binary(self):
        q = Project(native())
        self.assertEqual([p.page_id for p in q.pages], [1, 2])
        self.assertIn(b'ID=999', q.app.one('MeMeCode').blob(q.file.payload))

    def test_counted_unicode(self):
        data = b'[Application]\r\n' + wide('wTextLen0', 'Çığ öŞÜ İğne')
        idx = NativeIndex(data)
        self.assertEqual(idx.sections[0].one('wTextLen0').text(data), 'Çığ öŞÜ İğne')

    def test_declared_huge_truncated_blob_rejected(self):
        for body in (b'[Application]\r\nwTextLen0=999\r\nx', b'[Application]\r\nwTextLen0=-1\r\n',
                     b'[Application]\r\nwTextLen0=9999999999999999999\r\n'):
            with self.assertRaises(AgentError):
                NativeIndex(body)

    def test_opaque_tail_without_eol_is_exact(self):
        q = Project(native())
        self.assertTrue(q.file.payload.endswith(b'WithoutCRLF\x00\xff'))
        t = q.element(1, 10).section.one('X')
        body, ledger = apply_spans(q.file.payload, [Patch(t.start, t.end, t.raw(q.file.payload), encode_token(t, 20, q.file.payload), 'x')])
        self.assertTrue(body.endswith(b'WithoutCRLF\x00\xff'))
        self.assertEqual(restore_spans(body, ledger), q.file.payload)

    def test_unknown_fields_survive_edit(self):
        q = Project(native()); sec = q.element(1, 10).section
        t = sec.one('Width')
        body, ledger = apply_spans(q.file.payload, [Patch(t.start, t.end, t.raw(q.file.payload), encode_token(t, 100, q.file.payload), 'width')])
        candidate = Project(q.file.encode(body))
        self.assertEqual(candidate.index.number(candidate.element(1, 10).section, 'FontUnknownControl'), 7)
        self.assertEqual(restore_spans(candidate.file.payload, ledger), q.file.payload)

    def test_wrong_family_and_corrupt_gzip(self):
        for data in (native()[:6] + b'\0\0\0\0' + native()[10:], native()[:-4], native() + b'junk'):
            with self.assertRaises(AgentError):
                NativeFile(data)

    def test_negative_identity_is_not_list_index(self):
        q = Project(native())
        with self.assertRaises(AgentError):
            q.element(1, -1)

    def test_duplicate_identity_rejected(self):
        with self.assertRaises(AgentError):
            Project(wrap(payload().replace(b'nPartsID=11', b'nPartsID=10')))

    def test_duplicate_property_is_not_last_wins(self):
        q = Project(wrap(payload().replace(b'Width=110\r\n', b'Width=110\r\nWidth=200\r\n', 1)))
        with self.assertRaises(AgentError):
            q.element(1, 10).section.one('Width')

    def test_length_cannot_be_patched_as_scalar(self):
        q = Project(native()); t = q.element(1, 10).states[0].one('wTextLen0')
        with self.assertRaises(AgentError):
            encode_token(t, 1000, q.file.payload)

    def test_resource_xml_and_exact_metadata(self):
        q = Project(native()); frame, data = embedded_xml(q)
        self.assertEqual(data, xml())
        self.assertEqual(frame.metadata['DiaTagXmlPath'], 'neutral.xml')

    def test_nested_background_inside_picture_is_not_a_resource(self):
        from universal_diascreen_hmi.resources import resource_frames
        nested = b'\r\n[Background]\r\nSize=3\r\nabc'
        body = b'[Application]\r\n[Picture]\r\nSize=' + str(len(nested)).encode() + b'\r\n' + nested + b'\r\n[END]\r\n'
        self.assertEqual(resource_frames(Project(wrap(body)), 'Background', 'Size'), [])

    def test_unknown_outer_resource_does_not_grant_nested_ownership(self):
        from universal_diascreen_hmi.resources import resource_frames
        body = b'[Application]\r\n[UnknownOwner]\r\nBytes=99\r\n[Background]\r\nSize=3\r\nabc\r\n'
        with self.assertRaises(AgentError):
            resource_frames(Project(wrap(body)), 'Background', 'Size')

    def test_patch_precondition_and_overlap(self):
        for changes in ([Patch(0, 1, b'x', b'z', 'bad')], [Patch(0, 2, b'ab', b'z', 'one'), Patch(1, 3, b'bc', b'z', 'overlap')]):
            with self.assertRaises(AgentError):
                apply_spans(b'abc', changes)


if __name__ == '__main__':
    unittest.main()
