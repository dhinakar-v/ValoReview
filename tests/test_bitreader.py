"""
Vectors for vrfnet.bitreader.BitReader.

The hand-computed cases pin the encodings down independently; the round-trip
cases then use a mirror-image writer to sweep every starting bit offset, which
is where an LSB-first reader most often goes wrong.

  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import struct
import unittest
from typing import ClassVar

import pytest

from vrfnet.bitreader import BitReader, NetError


def _f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


class BitWriter:
    """Mirror image of BitReader, for generating round-trip vectors."""

    def __init__(self):
        self.bits: list[int] = []

    def bit(self, b: int) -> BitWriter:
        self.bits.append(b & 1)
        return self

    def bits_of(self, value: int, n: int) -> BitWriter:
        for i in range(n):
            self.bits.append((value >> i) & 1)
        return self

    def int_packed(self, value: int) -> BitWriter:
        while True:
            group = value & 0x7F
            value >>= 7
            self.bits_of((group << 1) | (1 if value else 0), 8)
            if not value:
                return self

    def ranged_int(self, value: int, max_value: int) -> BitWriter:
        acc, mask = 0, 1
        while acc + mask < max_value:
            bit = 1 if value & mask else 0
            self.bit(bit)
            if bit:
                acc |= mask
            mask <<= 1
        return self

    def fstring(self, text: str, *, utf16: bool = False) -> BitWriter:
        if utf16:
            raw = text.encode("utf-16-le") + b"\x00\x00"
            self.bits_of(-(len(text) + 1) & 0xFFFFFFFF, 32)
        else:
            raw = text.encode("utf-8") + b"\x00"
            self.bits_of(len(raw), 32)
        for byte in raw:
            self.bits_of(byte, 8)
        return self

    def to_bytes(self) -> tuple[bytes, int]:
        n = len(self.bits)
        value = 0
        for i, b in enumerate(self.bits):
            value |= b << i
        return value.to_bytes((n + 7) // 8, "little"), n

    def reader(self) -> BitReader:
        buf, n = self.to_bytes()
        return BitReader(buf, n)


class TestBitOrder(unittest.TestCase):
    def test_lsb_first_within_byte(self):
        r = BitReader(bytes([0xB1]))
        assert [r.read_bit() for _ in range(8)] == [1, 0, 0, 0, 1, 1, 0, 1]

    def test_read_bits_first_bit_is_least_significant(self):
        r = BitReader(bytes([0b11010110]))
        assert r.read_bits(4) == 0b0110
        assert r.read_bits(4) == 0b1101

    def test_spans_byte_boundary(self):
        r = BitReader(bytes([0xFF, 0x00]))
        assert r.read_bits(4) == 0xF
        assert r.read_bits(8) == 0x0F
        assert r.read_bits(4) == 0x0

    def test_peek_does_not_advance(self):
        r = BitReader(bytes([0xAB, 0xCD]))
        first = r.peek_bits(12)
        assert r.peek_bits(12) == first
        assert r.pos == 0
        assert r.read_bits(12) == first


class TestIntPacked(unittest.TestCase):
    """1 continuation bit (LSB) + 7 payload bits per group, little-endian."""

    HAND: ClassVar[list[tuple[int, bytes]]] = [
        (0, bytes([0x00])),
        (1, bytes([0x02])),
        (127, bytes([0xFE])),
        (128, bytes([0x01, 0x02])),
        (300, bytes([0x59, 0x04])),
    ]

    def test_hand_computed(self):
        for value, encoded in self.HAND:
            with self.subTest(value=value):
                assert BitReader(encoded).read_int_packed() == value

    def test_hand_computed_consumes_exact_bits(self):
        for value, encoded in self.HAND:
            with self.subTest(value=value):
                r = BitReader(encoded)
                r.read_int_packed()
                assert r.pos == len(encoded) * 8
                assert r.at_end()

    def test_roundtrip_at_every_start_offset(self):
        values = [0, 1, 2, 63, 64, 127, 128, 129, 255, 16383, 16384, 1 << 20, 546, 1462]
        for offset in range(8):
            for value in values:
                with self.subTest(offset=offset, value=value):
                    r = BitWriter().bits_of(0, offset).int_packed(value).reader()
                    r.skip_bits(offset)
                    assert r.read_int_packed() == value
                    assert r.at_end()

    def test_sequence_of_packed_ints_stays_in_sync(self):
        values = [3, 300, 0, 1, 70000, 5]
        w = BitWriter().bit(1)  # deliberately start unaligned
        for v in values:
            w.int_packed(v)
        r = w.reader()
        r.read_bit()
        assert [r.read_int_packed() for _ in values] == values
        assert r.at_end()


class TestRangedInt(unittest.TestCase):
    def test_max_one_reads_nothing(self):
        r = BitReader(bytes([0xFF]))
        assert r.read_int(1) == 0
        assert r.pos == 0

    def test_max_two_is_a_single_bit(self):
        r = BitReader(bytes([0b01]))
        assert r.read_int(2) == 1
        assert r.pos == 1

    def test_max_three_widths(self):
        # value 1 stops after one bit; value 2 needs a second bit
        r = BitReader(bytes([0b01]))
        assert r.read_int(3) == 1
        assert r.pos == 1
        r = BitReader(bytes([0b10]))
        assert r.read_int(3) == 2
        assert r.pos == 2

    def test_roundtrip_over_maxima_and_offsets(self):
        for max_value in (2, 3, 4, 5, 8, 10, 100, 1024, 10240, 16384):
            for value in range(min(max_value, 12)):
                for offset in (0, 1, 5, 7):
                    with self.subTest(max=max_value, value=value, offset=offset):
                        r = (
                            BitWriter()
                            .bits_of(0, offset)
                            .ranged_int(value, max_value)
                            .reader()
                        )
                        r.skip_bits(offset)
                        assert r.read_int(max_value) == value
                        assert r.at_end()

    def test_top_of_range_roundtrips(self):
        for max_value in (2, 3, 4, 7, 8, 100, 1024, 16384):
            value = max_value - 1
            with self.subTest(max=max_value):
                r = BitWriter().ranged_int(value, max_value).reader()
                assert r.read_int(max_value) == value


class TestScalars(unittest.TestCase):
    def test_unaligned_u32(self):
        r = BitWriter().bits_of(0, 3).bits_of(0xDEADBEEF, 32).reader()
        r.skip_bits(3)
        assert r.read_u32() == 0xDEADBEEF

    def test_i32_sign(self):
        r = BitWriter().bits_of(0xFFFFFFFF, 32).reader()
        assert r.read_i32() == -1

    def test_f32_unaligned(self):
        r = BitWriter().bit(1).bits_of(_f32_bits(0.0078125), 32).reader()
        r.read_bit()
        assert r.read_f32() == pytest.approx(0.0078125)

    def test_read_bytes_unaligned(self):
        payload = b"\x01\x02\x03\x04"
        w = BitWriter().bits_of(0, 5)
        for byte in payload:
            w.bits_of(byte, 8)
        r = w.reader()
        r.skip_bits(5)
        assert r.read_bytes(4) == payload

    def test_read_bits_bytes_pads_to_whole_bytes(self):
        r = BitReader(bytes([0b101, 0x00]))
        assert r.read_bits_bytes(3) == bytes([0b101])
        assert r.pos == 3


class TestStringsAndNames(unittest.TestCase):
    def test_ansi_fstring(self):
        r = BitWriter().bit(0).fstring("/Game/Maps/Infinity/Infinity").reader()
        r.read_bit()
        assert r.read_fstring() == "/Game/Maps/Infinity/Infinity"
        assert r.at_end()

    def test_utf16_fstring(self):
        r = BitWriter().fstring("checkpoint0", utf16=True).reader()
        assert r.read_fstring() == "checkpoint0"
        assert r.at_end()

    def test_empty_fstring(self):
        r = BitWriter().bits_of(0, 32).reader()
        assert r.read_fstring() == ""

    def test_fname_hardcoded(self):
        r = BitWriter().bit(1).int_packed(9).reader()
        assert r.read_fname() == "#9"
        assert r.at_end()

    def test_fname_inline(self):
        r = BitWriter().bit(0).fstring("Actor").bits_of(0, 32).reader()
        assert r.read_fname() == "Actor"
        assert r.at_end()

    def test_fname_hardcoded_legacy_uint32(self):
        r = BitWriter().bit(1).bits_of(9, 32).reader()
        assert r.read_fname(hardcoded_packed=False) == "#9"
        assert r.at_end()


class TestBounds(unittest.TestCase):
    def test_read_past_end_raises(self):
        r = BitReader(bytes([0x00]))
        with pytest.raises(NetError):
            r.read_bits(9)

    def test_num_bits_limits_reads_below_buffer_size(self):
        r = BitReader(bytes([0xFF, 0xFF]), num_bits=10)
        r.read_bits(10)
        assert r.at_end()
        with pytest.raises(NetError):
            r.read_bit()

    def test_num_bits_beyond_buffer_rejected(self):
        with pytest.raises(NetError):
            BitReader(bytes([0x00]), num_bits=9)

    def test_error_message_carries_bit_position(self):
        r = BitReader(bytes([0x00, 0x00]))
        r.skip_bits(12)
        with pytest.raises(NetError) as excinfo:
            r.read_bits(8)
        assert "12" in str(excinfo.value)


if __name__ == "__main__":
    unittest.main()
