"""Hand-authored pixel/filter witnesses for the pure background primitive.

No vendor assets, raster libraries, UI, files or matching encoder algorithms.
Chunk framing and stdlib compression only wrap explicit test scanline bytes.
"""
import struct
import unittest
import zlib

from universal_hmi.errors import HmiError
from universal_hmi.native.existing_background import (
    MAX_CHUNKS, MAX_DIMENSION, MAX_IMAGE_BYTES,
    decode_opaque_png, frame_pixels_from_png,
)


SIGNATURE = b"\x89PNG\r\n\x1a\n"
RGB_CORNERS = bytes.fromhex("ff0000 00ff00 0000ff ffff00")
CORNER_ROWS = bytes.fromhex("00 ff0000 00ff00 00 0000ff ffff00")
# Bottom blue/yellow followed by top red/green; BGR then reserved FF.
DIB_CORNERS = bytes.fromhex("ff0000ff 00ffffff 0000ffff 00ff00ff")


def chunk(kind, data=b""):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data)))


def ihdr(width=2, height=2, depth=8, color=2, compression=0, filtering=0, interlace=0):
    return chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color,
                                      compression, filtering, interlace))


def png(scanlines=CORNER_ROWS, width=2, height=2, color=2, compressed=None):
    payload = zlib.compress(scanlines) if compressed is None else compressed
    return SIGNATURE + ihdr(width, height, color=color) + chunk(b"IDAT", payload) + chunk(b"IEND")


def dib(width=2, height=2, pixels=None, **changes):
    pixel_count = abs(width * height)
    fields = dict(size=40, width=width, height=height, planes=1, bits=32,
                  compression=0, image_size=pixel_count * 4,
                  xppm=0, yppm=0, used=0, important=0)
    fields.update(changes)
    header = struct.pack("<IiiHHIIiiII", *fields.values())
    if pixels is None:
        pixels = b"\x00\x00\x00\xff" * pixel_count
    return header + pixels


class PngTests(unittest.TestCase):
    def assert_code(self, code, function, *args):
        with self.assertRaises(HmiError) as failure:
            function(*args)
        self.assertEqual(failure.exception.code, code)

    def test_asymmetric_corner_pixels_are_top_down_rgb(self):
        self.assertEqual(decode_opaque_png(png(), 2, 2), RGB_CORNERS)

    def test_rgb_all_filters_in_one_image(self):
        # One RGB pixel per row. Sub has no left; Average floors above/2.
        scanlines = bytes.fromhex("00 010203 01 040506 02 010203 03 0a0a0a 04 010203")
        expected = bytes.fromhex("010203 040506 050709 0c0d0e 0d0f11")
        self.assertEqual(decode_opaque_png(png(scanlines, 1, 5), 1, 5), expected)

    def test_sub_uses_reconstructed_left_pixel(self):
        scanlines = bytes.fromhex("01 0a141e 1e1e1e")
        self.assertEqual(decode_opaque_png(png(scanlines, 2, 1), 2, 1),
                         bytes.fromhex("0a141e 28323c"))

    def test_up_uses_same_column_from_previous_row(self):
        scanlines = bytes.fromhex("00 0a141e 28323c 02 050607 08090a")
        self.assertEqual(decode_opaque_png(png(scanlines), 2, 2),
                         bytes.fromhex("0a141e 28323c 0f1a25 303b46"))

    def test_average_addition_uses_full_precision_then_mod256(self):
        scanlines = bytes.fromhex("00 fafbfc fdfeff 03 7d7e7e 050607")
        self.assertEqual(decode_opaque_png(png(scanlines), 2, 2),
                         bytes.fromhex("fafbfc fdfeff fafbfc 000204"))

    def test_paeth_ties_choose_left_then_above_and_can_choose_diagonal(self):
        # Channel triples (a,b,c): (40,10,20)->left; (10,40,20)->above;
        # (10,30,20)->diagonal. First-pixel reconstruction supplies a.
        scanlines = bytes.fromhex("00 141414 0a281e 04 14f6f6 000000")
        self.assertEqual(decode_opaque_png(png(scanlines), 2, 2),
                         bytes.fromhex("141414 0a281e 280a0a 282814"))

    def test_opaque_rgba_channels_removed_without_premultiplication(self):
        rows = bytes.fromhex("00 ff0000ff 00ff00ff 00 0000ffff ffff00ff")
        self.assertEqual(decode_opaque_png(png(rows, color=6), 2, 2), RGB_CORNERS)

    def test_rgba_sub_has_four_byte_pixel_distance(self):
        rows = bytes.fromhex("01 0a141eff 1e1e1e00")
        self.assertEqual(decode_opaque_png(png(rows, 2, 1, color=6), 2, 1),
                         bytes.fromhex("0a141e 28323c"))

    def test_any_nonopaque_rgba_pixel_is_refused(self):
        for alpha in (0, 17, 254):
            with self.subTest(alpha=alpha):
                self.assert_code("PNG_ALPHA", decode_opaque_png,
                                 png(bytes((0, 10, 20, 30, alpha)), 1, 1, color=6), 1, 1)

    def test_consecutive_split_idat_including_empty_chunks(self):
        data = zlib.compress(CORNER_ROWS)
        split = (SIGNATURE + ihdr() + chunk(b"IDAT") + chunk(b"IDAT", data[:3])
                 + chunk(b"IDAT", data[3:-2]) + chunk(b"IDAT", data[-2:]) + chunk(b"IEND"))
        self.assertEqual(decode_opaque_png(split, 2, 2), RGB_CORNERS)

    def test_every_truncated_prefix_is_refused(self):
        data = png()
        for length in range(len(data)):
            with self.subTest(length=length), self.assertRaises(HmiError):
                decode_opaque_png(data[:length], 2, 2)

    def test_bad_signature(self):
        self.assert_code("PNG_FRAME", decode_opaque_png, b"not PNG!" + png()[8:], 2, 2)

    def test_each_chunk_crc_is_checked(self):
        data = png()
        positions = (29, 33 + 8, len(data) - 1)
        for position in positions:
            with self.subTest(position=position):
                changed = bytearray(data)
                changed[position] ^= 1
                self.assert_code("PNG_CRC", decode_opaque_png, bytes(changed), 2, 2)

    def test_exact_canvas_in_both_dimensions(self):
        for dimensions in ((1, 2), (2, 1), (3, 2), (2, 3)):
            with self.subTest(dimensions=dimensions):
                self.assert_code("PNG_CANVAS", decode_opaque_png, png(), *dimensions)

    def test_header_must_be_first_exactly_13_bytes_and_unique(self):
        for data in (SIGNATURE + chunk(b"IDAT") + ihdr() + chunk(b"IEND"),
                     SIGNATURE + chunk(b"IHDR", b"\0" * 12) + chunk(b"IEND"),
                     SIGNATURE + ihdr() + ihdr() + chunk(b"IDAT", zlib.compress(CORNER_ROWS)) + chunk(b"IEND")):
            with self.subTest(data=data[:24]):
                self.assert_code("PNG_FRAME", decode_opaque_png, data, 2, 2)

    def test_format_extensions_are_refused(self):
        for setting in ({"depth": 16}, {"color": 0}, {"color": 3}, {"color": 4},
                        {"compression": 1}, {"filtering": 1}, {"interlace": 1}):
            with self.subTest(setting=setting):
                data = SIGNATURE + ihdr(**setting) + chunk(b"IDAT", zlib.compress(CORNER_ROWS)) + chunk(b"IEND")
                self.assert_code("UNSUPPORTED_PNG", decode_opaque_png, data, 2, 2)

    def test_all_ancillary_and_unknown_critical_chunks_are_refused(self):
        for kind in (b"gAMA", b"cHRM", b"iCCP", b"sRGB", b"PLTE", b"tRNS", b"acTL", b"fcTL", b"fdAT", b"pHYs", b"tEXt", b"JUNK"):
            with self.subTest(kind=kind):
                data = SIGNATURE + ihdr() + chunk(kind) + chunk(b"IDAT", zlib.compress(CORNER_ROWS)) + chunk(b"IEND")
                self.assert_code("UNSUPPORTED_PNG", decode_opaque_png, data, 2, 2)

    def test_nonconsecutive_idat_is_not_joined_across_an_extension(self):
        data = zlib.compress(CORNER_ROWS)
        broken = (SIGNATURE + ihdr() + chunk(b"IDAT", data[:3]) + chunk(b"tEXt", b"gap")
                  + chunk(b"IDAT", data[3:]) + chunk(b"IEND"))
        self.assert_code("UNSUPPORTED_PNG", decode_opaque_png, broken, 2, 2)

    def test_iend_must_be_empty_unique_and_final(self):
        for data in (png() + b"x", png() + chunk(b"IEND"),
                     png()[:-12] + chunk(b"IEND", b"x"), SIGNATURE + ihdr() + chunk(b"IEND")):
            with self.subTest(length=len(data)):
                self.assert_code("PNG_FRAME", decode_opaque_png, data, 2, 2)

    def test_empty_or_invalid_zlib_stream(self):
        for compressed in (b"", b"garbage", zlib.compress(CORNER_ROWS)[:-1]):
            with self.subTest(compressed=compressed):
                self.assert_code("PNG_DEFLATE", decode_opaque_png, png(compressed=compressed), 2, 2)

    def test_extra_compressed_member_or_junk_is_refused(self):
        for extra in (zlib.compress(b""), zlib.compress(CORNER_ROWS), b"trailer"):
            with self.subTest(extra=extra):
                self.assert_code("PNG_DEFLATE", decode_opaque_png,
                                 png(compressed=zlib.compress(CORNER_ROWS) + extra), 2, 2)

    def test_short_extra_and_bomb_output_are_refused(self):
        for rows in (CORNER_ROWS[:-1], CORNER_ROWS + b"x", b"\0" * 100000):
            with self.subTest(length=len(rows)):
                self.assert_code("PNG_DEFLATE", decode_opaque_png, png(rows), 2, 2)

    def test_adler_checksum_is_required(self):
        payload = bytearray(zlib.compress(CORNER_ROWS))
        payload[-1] ^= 1
        self.assert_code("PNG_DEFLATE", decode_opaque_png, png(compressed=bytes(payload)), 2, 2)

    def test_unknown_filter_is_refused(self):
        self.assert_code("PNG_FILTER", decode_opaque_png, png(b"\5" + CORNER_ROWS[1:]), 2, 2)

    def test_nonbyte_arguments_are_typed_refusals(self):
        for data in (None, "PNG", bytearray(png()), memoryview(png()), 1, True):
            with self.subTest(data_type=type(data)):
                self.assert_code("PNG_INPUT", decode_opaque_png, data, 2, 2)

    def test_dimension_types_and_bounds(self):
        for value in (True, False, None, 2.0, "2"):
            for dimensions in ((value, 2), (2, value)):
                with self.subTest(dimensions=dimensions):
                    self.assert_code("IMAGE_INPUT", decode_opaque_png, png(), *dimensions)
        for dimensions in ((0, 2), (2, -1), (MAX_DIMENSION + 1, 1), (1, 10**100),
                           (MAX_DIMENSION, MAX_DIMENSION)):
            with self.subTest(dimensions=dimensions):
                self.assert_code("IMAGE_LIMIT", decode_opaque_png, png(), *dimensions)

    def test_file_chunk_and_chunk_count_budgets(self):
        self.assert_code("IMAGE_LIMIT", decode_opaque_png, b"\0" * (MAX_IMAGE_BYTES + 1), 2, 2)
        oversized = SIGNATURE + struct.pack(">I", MAX_IMAGE_BYTES + 1) + b"IHDR" + b"\0" * 4
        self.assert_code("IMAGE_LIMIT", decode_opaque_png, oversized, 2, 2)
        many = SIGNATURE + ihdr() + chunk(b"IDAT") * MAX_CHUNKS + chunk(b"IEND")
        self.assert_code("IMAGE_LIMIT", decode_opaque_png, many, 2, 2)

    def test_declared_chunk_length_cannot_escape_file(self):
        data = SIGNATURE + struct.pack(">I", 100) + b"IHDR" + b"\0" * 4
        self.assert_code("PNG_FRAME", decode_opaque_png, data, 2, 2)


class DibTests(unittest.TestCase):
    def assert_code(self, code, frame, data=None):
        with self.assertRaises(HmiError) as failure:
            frame_pixels_from_png(frame, png() if data is None else data)
        self.assertEqual(failure.exception.code, code)

    def test_asymmetric_channels_rows_and_exact_header(self):
        source = dib()
        result = frame_pixels_from_png(source, png())
        self.assertEqual(result[:40], source[:40])
        self.assertEqual(result[40:], DIB_CORNERS)
        self.assertEqual(len(result), len(source))
        self.assertEqual(source[40:], b"\0\0\0\xff" * 4)

    def test_identical_rgb_returns_exact_original_frame(self):
        source = dib(pixels=DIB_CORNERS)
        self.assertIs(frame_pixels_from_png(source, png()), source)
        rgba = bytes.fromhex("00 ff0000ff 00ff00ff 00 0000ffff ffff00ff")
        self.assertIs(frame_pixels_from_png(source, png(rgba, color=6)), source)

    def test_odd_width_has_four_byte_pixels_and_no_extra_row_padding(self):
        data = png(bytes.fromhex("00 ff0000 00ff00 0000ff"), 3, 1)
        result = frame_pixels_from_png(dib(3, 1), data)
        self.assertEqual(result[40:], bytes.fromhex("0000ffff 00ff00ff ff0000ff"))
        self.assertEqual(len(result), 52)

    def test_every_source_reserved_byte_is_checked(self):
        source = dib()
        for index in (43, 47, 51, 55):
            for reserved in (0, 17):
                with self.subTest(index=index, reserved=reserved):
                    altered = bytearray(source)
                    altered[index] = reserved
                    self.assert_code("DIB_RESERVED", bytes(altered))

    def test_malformed_or_unsupported_header_fields(self):
        for setting in ({"size": 108}, {"width": 0}, {"width": -2}, {"height": 0}, {"height": -2},
                        {"planes": 0}, {"planes": 2}, {"bits": 24}, {"compression": 3},
                        {"xppm": 1}, {"yppm": 1}, {"used": 1}, {"important": 1}):
            with self.subTest(setting=setting):
                self.assert_code("UNSUPPORTED_DIB", dib(**setting))

    def test_pixel_extent_must_be_exact_no_suffix_or_second_frame(self):
        source = dib()
        for altered in (source[:-1], source + b"x", source + source,
                        dib(image_size=0), dib(image_size=12), dib(image_size=20)):
            with self.subTest(length=len(altered)):
                self.assert_code("DIB_FRAME", altered)

    def test_short_header_and_nonbytes_are_typed_refusals(self):
        for length in (0, 1, 39):
            self.assert_code("DIB_FRAME", b"\0" * length)
        for data in (None, "DIB", bytearray(dib()), memoryview(dib()), True, 42):
            with self.subTest(data_type=type(data)):
                self.assert_code("DIB_INPUT", data)

    def test_canvas_bounds_precede_pixel_allocation(self):
        for dimensions in ((MAX_DIMENSION + 1, 1), (MAX_DIMENSION, MAX_DIMENSION)):
            fields = (40, *dimensions, 1, 32, 0, 0, 0, 0, 0, 0)
            with self.subTest(dimensions=dimensions):
                self.assert_code("IMAGE_LIMIT", struct.pack("<IiiHHIIiiII", *fields))
        self.assert_code("IMAGE_LIMIT", b"\0" * (MAX_IMAGE_BYTES + 1))

    def test_destination_canvas_and_png_alpha_must_match(self):
        self.assert_code("PNG_CANVAS", dib(), png(b"\0\0\0\0", 1, 1))
        self.assert_code("PNG_ALPHA", dib(1, 1), png(bytes((0, 10, 20, 30, 254)), 1, 1, color=6))

    def test_png_errors_are_not_reinterpreted_as_dib_or_rgb(self):
        self.assert_code("PNG_INPUT", dib(), "not bytes")
        self.assert_code("PNG_FRAME", dib(), dib())


if __name__ == "__main__":
    unittest.main()
