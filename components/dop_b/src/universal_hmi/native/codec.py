"""Original codec for the observed BMP + gzip + XOR native envelopes.

This recognizes an envelope, not a model's vendor qualification. The thumbnail
and unknown prefix data are retained. A source-matched declared body length is
updated for length-changing edits; this does not qualify other prefix fields.
"""
from dataclasses import dataclass
import gzip
import struct
import zlib

from ..errors import HmiError

MAX_PAYLOAD = 256 * 1024 * 1024
FAMILIES = {"delta_diascreen": b"PDAB", "delta_dopsoft2": b"\0\0\0\0"}
_XOR = bytes(i ^ 0x64 for i in range(256))


@dataclass(frozen=True)
class Envelope:
    thumbnail: bytes
    prefix: bytes
    body: bytes

    @classmethod
    def decode(cls, data, family):
        if not isinstance(family, str) or family not in FAMILIES:
            raise HmiError("UNSUPPORTED_FAMILY", "Unknown native family", family=family)
        if not isinstance(data, bytes) or len(data) < 54 or data[:2] != b"BM":
            raise HmiError("NATIVE_HEADER", "Native file needs a complete BMP header")
        if data[6:10] != FAMILIES[family]:
            raise HmiError("NATIVE_FAMILY", "Native envelope marker does not match the family")
        offset = 54 + struct.unpack_from("<I", data, 34)[0]
        if offset >= len(data):
            raise HmiError("NATIVE_HEADER", "Thumbnail size exceeds the native file")
        compressed = data[offset:]
        try:
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            payload = decoder.decompress(compressed, MAX_PAYLOAD + 1)
            if len(payload) > MAX_PAYLOAD or decoder.unconsumed_tail:
                raise HmiError("NATIVE_LIMIT", "Expanded payload exceeds 256 MiB")
            if not decoder.eof or decoder.unused_data:
                raise HmiError("NATIVE_GZIP", "Gzip must be one complete member with no trailing bytes")
        except zlib.error as exc:
            raise HmiError("NATIVE_GZIP", "Invalid gzip framing or checksum") from exc
        payload = payload.translate(_XOR)
        if len(payload) < 41 or not payload[41:].startswith(b"[Application]\r\n"):
            raise HmiError("NATIVE_PAYLOAD", "Expected the observed 41-byte prefix and Application section")
        return cls(data[:offset], payload[:41], payload[41:])

    def declared_body_length(self):
        """Observed in nine genuine vendor sources across both envelopes."""
        return struct.unpack('<I', self.prefix[37:41].translate(_XOR))[0]

    def prefix_for_body(self, body):
        # Synthetic or unknown prefix shapes are preserved. Real candidate
        # contracts separately require a matching source/candidate declaration.
        if self.declared_body_length() != len(self.body):
            return self.prefix
        return self.prefix[:37] + struct.pack('<I', len(body)).translate(_XOR)

    def encode(self, body):
        payload = self.prefix_for_body(body) + body
        if len(payload) > MAX_PAYLOAD:
            raise HmiError("NATIVE_LIMIT", "Expanded payload exceeds 256 MiB")
        return self.thumbnail + gzip.compress(payload.translate(_XOR), mtime=0)
