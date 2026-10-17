"""Bounded opaque PNG decoding and same-size existing DIB pixel conversion.

This pure byte primitive does not qualify a native background resource, its
page references or its renderer. Integration must separately prove those
contracts. The source DIB's fourth byte is reserved, not alpha: only the
witnessed FF convention is writable here. No artwork or vendor code is used.
"""
import struct
import zlib

from ..errors import HmiError


MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_DIMENSION = 8192
MAX_CHUNKS = 4096
_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _canvas(width, height, channels):
    if type(width) is not int or type(height) is not int:
        raise HmiError("IMAGE_INPUT", "Canvas dimensions must be positive integers")
    if not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION:
        raise HmiError("IMAGE_LIMIT", "Canvas dimensions exceed the bounded image subset")
    if height * (1 + width * channels) > MAX_IMAGE_BYTES:
        raise HmiError("IMAGE_LIMIT", "Decoded image exceeds the bounded byte budget")


def _paeth(left, above, diagonal):
    estimate = left + above - diagonal
    dl, da, dd = abs(estimate - left), abs(estimate - above), abs(estimate - diagonal)
    if dl <= da and dl <= dd:
        return left
    return above if da <= dd else diagonal


def decode_opaque_png(raw, width, height):
    """Decode exact-canvas RGB8/opaque RGBA8 to top-down interleaved RGB.

    Only IHDR, consecutive IDAT chunks and a terminal empty IEND are accepted.
    Color profiles, palette/transparency chunks, animation, interlacing and
    every other extension are explicitly refused instead of approximated.
    """
    if not isinstance(raw, bytes):
        raise HmiError("PNG_INPUT", "PNG input must be immutable bytes")
    _canvas(width, height, 3)
    if len(raw) > MAX_IMAGE_BYTES:
        raise HmiError("IMAGE_LIMIT", "PNG file exceeds the bounded byte budget")
    if raw[:8] != _SIGNATURE:
        raise HmiError("PNG_FRAME", "PNG signature is missing or invalid")

    pos, chunks, channels, ended = 8, 0, None, False
    pieces = []
    compressed_size = 0
    while pos < len(raw):
        chunks += 1
        if chunks > MAX_CHUNKS:
            raise HmiError("IMAGE_LIMIT", "PNG chunk count exceeds the bounded subset")
        if len(raw) - pos < 12:
            raise HmiError("PNG_FRAME", "PNG chunk has an incomplete header or CRC")
        length = struct.unpack_from(">I", raw, pos)[0]
        if length > MAX_IMAGE_BYTES:
            raise HmiError("IMAGE_LIMIT", "PNG chunk exceeds the bounded byte budget")
        end = pos + 12 + length
        if end > len(raw):
            raise HmiError("PNG_FRAME", "PNG chunk exceeds its input frame")
        kind = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + length]
        crc = struct.unpack_from(">I", raw, end - 4)[0]
        if zlib.crc32(data, zlib.crc32(kind)) != crc:
            raise HmiError("PNG_CRC", "PNG chunk CRC does not match", chunk=chunks)

        if chunks == 1:
            if kind != b"IHDR" or length != 13:
                raise HmiError("PNG_FRAME", "PNG must begin with one 13-byte IHDR")
            pw, ph, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", data)
            if (pw, ph) != (width, height):
                raise HmiError("PNG_CANVAS", "PNG dimensions differ from the exact destination canvas")
            if depth != 8 or color not in (2, 6) or any((compression, filtering, interlace)):
                raise HmiError("UNSUPPORTED_PNG", "PNG format is outside noninterlaced RGB8/opaque RGBA8")
            channels = 3 if color == 2 else 4
            _canvas(width, height, channels)
        elif kind == b"IDAT":
            compressed_size += length
            if compressed_size > MAX_IMAGE_BYTES:
                raise HmiError("IMAGE_LIMIT", "PNG compressed stream exceeds the bounded byte budget")
            pieces.append(data)
        elif kind == b"IEND":
            if length or not pieces or end != len(raw):
                raise HmiError("PNG_FRAME", "PNG requires one terminal empty IEND after IDAT")
            ended = True
            break
        elif kind == b"IHDR":
            raise HmiError("PNG_FRAME", "PNG IHDR cannot be repeated")
        else:
            raise HmiError("UNSUPPORTED_PNG", "PNG extension chunks are outside the opaque subset")
        pos = end
    if not ended:
        raise HmiError("PNG_FRAME", "PNG lacks its terminal IEND")

    stride = width * channels
    expected = height * (stride + 1)
    decoder = zlib.decompressobj()
    try:
        expanded = decoder.decompress(b"".join(pieces), expected + 1)
    except zlib.error as exc:
        raise HmiError("PNG_DEFLATE", "PNG has an invalid zlib stream") from exc
    # No flush: only one bounded stream with its checksum and exact output is
    # accepted. A second member, junk trailer, bomb or truncated stream fails.
    if (len(expanded) != expected or not decoder.eof
            or decoder.unused_data or decoder.unconsumed_tail):
        raise HmiError("PNG_DEFLATE", "PNG zlib stream is incomplete, excessive or has trailing data")

    rgb = bytearray()
    previous = bytes(stride)
    for row_index in range(height):
        start = row_index * (stride + 1)
        mode = expanded[start]
        if mode > 4:
            raise HmiError("PNG_FILTER", "PNG scanline filter is unsupported", row=row_index)
        row = bytearray(expanded[start + 1:start + 1 + stride])
        if mode:
            for index in range(stride):
                left = row[index - channels] if index >= channels else 0
                above = previous[index]
                diagonal = previous[index - channels] if index >= channels else 0
                if mode == 1:
                    predictor = left
                elif mode == 2:
                    predictor = above
                elif mode == 3:
                    predictor = (left + above) // 2
                else:
                    predictor = _paeth(left, above, diagonal)
                row[index] = (row[index] + predictor) & 255
        if channels == 3:
            rgb.extend(row)
        else:
            for index in range(0, stride, 4):
                if row[index + 3] != 255:
                    raise HmiError("PNG_ALPHA", "PNG contains nonopaque pixels; no alpha loss is allowed")
                rgb.extend(row[index:index + 3])
        previous = row
    return bytes(rgb)


def frame_pixels_from_png(original_DIBframe, png):
    """Retain a fixed positive-height BI_RGB32 header, replace pixels only.

    Exact 40-byte headers and full same-size bottom-up BGR/reserved-FF frames
    are required. No padding, crop, resize, top-down DIB or alpha reinterpretation
    is performed. An identical decoded RGB result returns the original bytes.
    """
    if not isinstance(original_DIBframe, bytes):
        raise HmiError("DIB_INPUT", "Existing DIB frame must be immutable bytes")
    if len(original_DIBframe) > MAX_IMAGE_BYTES:
        raise HmiError("IMAGE_LIMIT", "Existing DIB frame exceeds the bounded byte budget")
    if len(original_DIBframe) < 40:
        raise HmiError("DIB_FRAME", "Existing DIB lacks its complete 40-byte header")
    header = struct.unpack_from("<IiiHHIIiiII", original_DIBframe)
    size, width, height, planes, bits, compression, image_size, xppm, yppm, used, important = header
    if (size != 40 or width <= 0 or height <= 0 or planes != 1 or bits != 32
            or compression != 0 or any((xppm, yppm, used, important))):
        raise HmiError("UNSUPPORTED_DIB", "Existing frame is outside the fixed positive-height BI_RGB32 subset")
    _canvas(width, height, 4)
    if image_size != width * height * 4 or len(original_DIBframe) != 40 + image_size:
        raise HmiError("DIB_FRAME", "Existing DIB pixel extent differs from its exact canvas")
    if any(original_DIBframe[index] != 255 for index in range(43, len(original_DIBframe), 4)):
        raise HmiError("DIB_RESERVED", "Existing DIB reserved pixel bytes must all use the witnessed FF convention")

    rgb = decode_opaque_png(png, width, height)
    pixels = bytearray(image_size)
    for y in range(height):
        source = y * width * 3
        destination = (height - 1 - y) * width * 4
        for x in range(width):
            src, dst = source + x * 3, destination + x * 4
            pixels[dst:dst + 4] = bytes((rgb[src + 2], rgb[src + 1], rgb[src], 255))
    candidate = original_DIBframe[:40] + pixels
    return original_DIBframe if candidate == original_DIBframe else candidate
