"""Regression for vendor's separately encoded body-size prefix field."""
import struct
import unittest

from universal_hmi.native.codec import Envelope, FAMILIES


class DeclaredBodyLength(unittest.TestCase):
    def fixture(self, family, body):
        bmp = bytearray(54)
        bmp[:2] = b'BM'
        bmp[6:10] = FAMILIES[family]
        # Original byte-assembled fixture, not a redistributed vendor asset.
        prefix = bytes(range(37)) + bytes(v ^ 0x64 for v in struct.pack('<I', len(body)))
        return Envelope(bytes(bmp), prefix, body)

    def test_growing_and_shrinking_preserves_other_prefix_bytes_both_families(self):
        initial = b'[Application]\r\nName=Example\r\n'
        for family in FAMILIES:
            source = self.fixture(family, initial)
            for body in (initial, initial + b'Caption=New\r\n', b'[Application]\r\n'):
                with self.subTest(family=family, size=len(body)):
                    result = Envelope.decode(source.encode(body), family)
                    self.assertEqual(result.body, body)
                    self.assertEqual(result.declared_body_length(), len(body))
                    self.assertEqual(result.prefix[:37], source.prefix[:37])
                    self.assertEqual(result.thumbnail, source.thumbnail)

    def test_subsequent_edit_uses_new_saved_length(self):
        source = self.fixture('delta_dopsoft2', b'[Application]\r\n')
        once = Envelope.decode(source.encode(source.body + b'Name=A\r\n'), 'delta_dopsoft2')
        twice = Envelope.decode(once.encode(once.body + b'Name2=B\r\n'), 'delta_dopsoft2')
        self.assertEqual(twice.declared_body_length(), len(twice.body))

    def test_unknown_prefix_not_silently_interpreted(self):
        source = self.fixture('delta_diascreen', b'[Application]\r\n')
        unknown = Envelope(source.thumbnail, source.prefix[:37] + b'????', source.body)
        after = Envelope.decode(unknown.encode(unknown.body + b'Name=A\r\n'), 'delta_diascreen')
        self.assertEqual(after.prefix, unknown.prefix)
        self.assertNotEqual(after.declared_body_length(), len(after.body))


if __name__ == '__main__':
    unittest.main()
