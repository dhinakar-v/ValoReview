"""
LSB-first bit cursor for the Unreal replication stream.

Mirrors Unreal's FBitReader.  Everything inside a playback packet is
bit-addressed and nothing is byte-aligned, so this is the primitive the whole
net decoder is built on.

Bit order
---------
  bit 0 of the stream is the *least* significant bit of byte 0, bit 8 is the
  LSB of byte 1, and so on.  That makes the whole buffer one little-endian
  integer whose bit i is stream bit i, which is how this class stores it:
  reads become a shift and a mask.

  Backing the reader with a Python int is only cheap for small buffers, since
  the shift is O(size).  Construct one BitReader per playback packet (<= 2048
  bytes), never one per decompressed block.

Encodings
---------
  read_int_packed()   UE SerializeIntPacked: groups of 1 continuation bit
                      (the LSB) + 7 payload bits, little-endian group order,
                      at most 5 groups.  Read from the current bit position;
                      it is *not* a byte-aligned varint.
  read_int(max)       UE FBitReader::ReadInt, a range-bounded encoding whose
                      width depends on `max`.  Unrelated to the above.
"""

from __future__ import annotations

import struct

from vrf_reader import VrfError


class NetError(VrfError):
    """Malformed or desynced replication stream."""


# UE caps SerializeIntPacked at 5 groups of 7 payload bits.
_PACKED_MAX_GROUPS = 5


class BitReader:
    """Bit cursor over a bytes buffer, LSB-first within each byte."""

    def __init__(self, buf: bytes, num_bits: int | None = None):
        self.buf = buf
        self._val = int.from_bytes(buf, "little")
        self.num_bits = len(buf) * 8 if num_bits is None else num_bits
        if self.num_bits > len(buf) * 8:
            raise NetError(
                f"num_bits={self.num_bits} exceeds buffer of {len(buf)} bytes"
            )
        self.pos = 0

    # -- state ------------------------------------------------------------

    @property
    def bits_left(self) -> int:
        return self.num_bits - self.pos

    def at_end(self) -> bool:
        return self.pos >= self.num_bits

    def _need(self, n: int) -> None:
        if n < 0:
            raise NetError(f"negative read of {n} bits at bit {self.pos}")
        if self.pos + n > self.num_bits:
            raise NetError(
                f"read past end: want {n} bits at bit {self.pos} "
                f"of {self.num_bits}"
            )

    def skip_bits(self, n: int) -> None:
        self._need(n)
        self.pos += n

    # -- raw bits ---------------------------------------------------------

    def read_bit(self) -> int:
        self._need(1)
        bit = (self._val >> self.pos) & 1
        self.pos += 1
        return bit

    def read_bool(self) -> bool:
        return self.read_bit() == 1

    def read_bits(self, n: int) -> int:
        """n bits as an integer, first bit read = least significant."""
        self._need(n)
        if n == 0:
            return 0
        value = (self._val >> self.pos) & ((1 << n) - 1)
        self.pos += n
        return value

    def read_bits_bytes(self, n: int) -> bytes:
        """n bits packed back into (n + 7) // 8 bytes, LSB-first."""
        value = self.read_bits(n)
        return value.to_bytes((n + 7) // 8, "little")

    def peek_bits(self, n: int) -> int:
        self._need(n)
        return (self._val >> self.pos) & ((1 << n) - 1)

    # -- fixed-width scalars ----------------------------------------------

    def read_u8(self) -> int:
        return self.read_bits(8)

    def read_u16(self) -> int:
        return self.read_bits(16)

    def read_u32(self) -> int:
        return self.read_bits(32)

    def read_u64(self) -> int:
        return self.read_bits(64)

    def read_i32(self) -> int:
        value = self.read_bits(32)
        return value - (1 << 32) if value & (1 << 31) else value

    def read_f32(self) -> float:
        return struct.unpack("<f", self.read_bits(32).to_bytes(4, "little"))[0]

    def read_bytes(self, n: int) -> bytes:
        """n whole bytes from the current bit position (need not be aligned)."""
        return self.read_bits(n * 8).to_bytes(n, "little")

    # -- UE variable-width integers ---------------------------------------

    def read_int_packed(self) -> int:
        """UE SerializeIntPacked.  See the module docstring."""
        result = 0
        shift = 0
        for _ in range(_PACKED_MAX_GROUPS):
            group = self.read_bits(8)
            result |= (group >> 1) << shift
            shift += 7
            if not group & 1:  # continuation bit is the LSB
                break
        return result

    def read_int(self, max_value: int) -> int:
        """UE FBitReader::ReadInt -- range-bounded, width depends on max_value.

        Emits just enough bits that no encodable value can reach max_value.
        """
        if max_value <= 1:
            return 0
        value = 0
        mask = 1
        while value + mask < max_value:
            if self.read_bit():
                value |= mask
            mask <<= 1
        return value

    # -- UE strings and names ---------------------------------------------

    def read_fstring(self) -> str:
        """int32 length then payload; negative length means UTF-16LE.

        The stored length includes the trailing NUL, matching Reader.fstring().
        """
        n = self.read_i32()
        if n == 0:
            return ""
        if n < 0:
            raw = self.read_bytes(-n * 2)
            return raw[:-2].decode("utf-16-le", "replace")
        raw = self.read_bytes(n)
        return raw[:-1].decode("utf-8", "replace")

    def read_fname(self, hardcoded_packed: bool = True) -> str:
        """UE net FName: a hardcoded EName index, or an inline string+number.

        Hardcoded names index UE's built-in EName table, which we do not carry;
        they come back as "#<index>".  Which indices Valorant actually uses for
        channel names is settled empirically during calibration, not guessed.

        hardcoded_packed selects the modern packed-int index encoding over the
        pre-HISTORY_CHANNEL_NAMES raw uint32.
        """
        if self.read_bit():
            idx = self.read_int_packed() if hardcoded_packed else self.read_u32()
            return f"#{idx}"
        text = self.read_fstring()
        self.read_i32()  # FName number suffix, unused
        return text

    def __repr__(self) -> str:
        return (
            f"<BitReader pos={self.pos}/{self.num_bits} "
            f"({len(self.buf)} bytes)>"
        )
