"""
Byte cursor with the same method names as BitReader.

The NetGUID and export-group decoders run over two different archives: a plain
byte archive (the demo frame prologue, and the length-prefixed GUID blobs
inside it) and a bit archive (the same structures arriving inside a bunch).
The field layout is identical; only the underlying cursor differs.

Rather than fork those decoders, ByteReader adapts vrf_reader.Reader to the
BitReader surface, so one implementation serves both.  vrf_reader.Reader is
left untouched -- its terse names (u32, fstring) stay valid for its existing
callers, and the read_* aliases here are additive.
"""

from __future__ import annotations

import struct

from vrf_reader import Reader

from vrfnet.bitreader import NetError


class ByteReader(Reader):
    """vrf_reader.Reader exposing the BitReader method surface."""

    # -- aliases onto the existing terse names ----------------------------

    def read_u32(self) -> int:
        return self.u32()

    def read_i32(self) -> int:
        return self.i32()

    def read_f32(self) -> float:
        return self.f32()

    def read_fstring(self) -> str:
        return self.fstring()

    def read_bytes(self, n: int) -> bytes:
        return self.bytes(n)

    # -- widths vrf_reader.Reader does not carry --------------------------

    def read_u8(self) -> int:
        return self._unpack("<B", 1)

    def read_u16(self) -> int:
        return self._unpack("<H", 2)

    def read_u64(self) -> int:
        return self._unpack("<Q", 8)

    def peek_u32(self) -> int:
        if self.pos + 4 > len(self.buf):
            raise NetError(f"peek past end at {self.pos}")
        return struct.unpack_from("<I", self.buf, self.pos)[0]

    # -- shared state ------------------------------------------------------

    def at_end(self) -> bool:
        return self.remaining <= 0

    @property
    def bits_left(self) -> int:
        return self.remaining * 8

    def read_int_packed(self) -> int:
        """UE SerializeIntPacked; on a byte archive the groups are whole bytes."""
        result = 0
        shift = 0
        for _ in range(5):
            group = self.read_u8()
            result |= (group >> 1) << shift
            shift += 7
            if not group & 1:
                break
        return result

    def read_bool(self) -> bool:
        """UE serializes a bool on a byte archive as a single byte."""
        return self.read_u8() != 0

    def read_fname(self, hardcoded_packed: bool = True) -> str:
        """See BitReader.read_fname; the leading flag is a byte here, not a bit."""
        if self.read_u8():
            idx = self.read_int_packed() if hardcoded_packed else self.read_u32()
            return f"#{idx}"
        text = self.read_fstring()
        self.read_i32()  # FName number suffix, unused
        return text

    def __repr__(self) -> str:
        return f"<ByteReader pos={self.pos}/{len(self.buf)}>"
