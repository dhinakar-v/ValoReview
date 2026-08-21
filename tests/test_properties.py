"""
Tests for the property loop, on plaintext bits.

The transform is tested separately and exhaustively in
`test_payload_transform.py`, so these fixtures are deliberately *not*
obfuscated: the two layers fail in different ways and mixing them would make a
framing bug look like a transform bug.  `decode_content_block` is the only
place they meet, and the one test that exercises it is the round-trip through
a real capture at the bottom of this file.

The writer here mirrors `BitReader` exactly -- LSB-first, UE's packed ints with
the continuation flag in the low bit, and UE's range-coded ints -- because a
fixture built by a subtly different writer would test the writer.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from vrfnet.actors import ContentBlock
from vrfnet.bitreader import BitReader
from vrfnet.model import NetFieldExport, NetFieldExportGroup
from vrfnet.properties import (
    CLASS_NET_CACHE,
    REP_LAYOUT,
    PropertyStats,
    decode_content_block,
    read_class_net_cache,
    read_rep_layout,
)

# A 12.10 capture, needed only by the end-to-end test.  Demos/ is gitignored,
# so this skips on a fresh checkout exactly like the other capture-backed tests.
DEMO_12_10 = Path("Demos/03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf")


class BitWriter:
    """The inverse of BitReader, for building fixtures."""

    def __init__(self):
        self.bits: list[int] = []

    def bit(self, value):
        self.bits.append(int(bool(value)))

    def raw(self, value, count):
        self.bits.extend((value >> i) & 1 for i in range(count))

    def packed(self, value):
        """UE SerializeIntPacked: 7 bits per byte, continuation in the LSB."""
        while True:
            group = (value & 0x7F) << 1
            value >>= 7
            if value:
                group |= 1
            self.raw(group, 8)
            if not value:
                return

    def ranged(self, value, max_value):
        """UE FBitReader::ReadInt, written back to front."""
        if max_value <= 1:
            return
        emitted = 0
        mask = 1
        while emitted + mask < max_value:
            self.bit(value & mask)
            emitted |= value & mask
            mask <<= 1

    def done(self):
        """(bytes, bit count) as a content block would carry them."""
        out = bytearray((len(self.bits) + 7) // 8)
        for i, b in enumerate(self.bits):
            if b:
                out[i // 8] |= 1 << (i % 8)
        return bytes(out), len(self.bits)


def group_with(path, names, num_exports=None):
    group = NetFieldExportGroup(
        path_name=path,
        path_name_index=1,
        num_exports=num_exports if num_exports is not None else len(names) + 1,
    )
    for handle, name in names.items():
        group.exports[handle] = NetFieldExport(handle=handle, checksum=0, name=name)
    return group


class RepLayout(unittest.TestCase):
    def test_reads_a_chain_and_lands_exactly(self):
        w = BitWriter()
        w.bit(1)  # bDoChecksum
        for handle, value_bits in ((4, 3), (13, 8)):
            w.packed(handle)
            w.packed(value_bits)
            w.raw(0b101, value_bits)
        w.packed(0)  # terminator
        data, count = w.done()

        block = read_rep_layout(BitReader(data, count))
        assert block.kind == REP_LAYOUT
        assert block.ok
        assert [(f.handle, f.num_bits) for f in block.fields] == [(4, 3), (13, 8)]

    def test_handles_are_named_from_the_export_group(self):
        w = BitWriter()
        w.bit(0)
        w.packed(7)
        w.packed(4)
        w.raw(0b1010, 4)
        w.packed(0)
        data, count = w.done()

        group = group_with("/Script/X.Y", {7: "NumUltimatePoints"})
        block = read_rep_layout(BitReader(data, count), group)
        assert block.fields[0].name == "NumUltimatePoints"
        assert block.fields[0].described == "7:NumUltimatePoints"

    def test_a_field_longer_than_the_block_is_reported_not_raised(self):
        # One bad block must cost that block, the way a bad packet costs one
        # packet -- not the replay.
        w = BitWriter()
        w.bit(0)
        w.packed(4)
        w.packed(9999)
        data, count = w.done()

        block = read_rep_layout(BitReader(data, count))
        assert not block.ok
        assert "9999" in block.error

    def test_trailing_bits_after_the_terminator_are_not_exact(self):
        w = BitWriter()
        w.bit(0)
        w.packed(0)
        w.raw(0, 5)  # bits nobody accounted for
        data, count = w.done()

        assert not read_rep_layout(BitReader(data, count)).exact


class ClassNetCache(unittest.TestCase):
    def test_reads_range_coded_handles(self):
        group = group_with("/Script/X.Y_ClassNetCache", {2: "MulticastBeep"}, 32)
        w = BitWriter()
        w.ranged(2, 32)
        w.packed(12)
        w.raw(0xABC, 12)
        data, count = w.done()

        block = read_class_net_cache(BitReader(data, count), group)
        assert block.kind == CLASS_NET_CACHE
        assert block.ok
        assert [(f.handle, f.name) for f in block.fields] == [(2, "MulticastBeep")]

    def test_without_a_group_the_handle_width_is_unknown(self):
        # Not a soft failure: the handle's width comes from the export count,
        # so there is nothing to guess with.
        block = read_class_net_cache(BitReader(b"\xff\xff", 16), None)
        assert not block.ok
        assert block.error == "no export group"

    def test_a_short_tail_is_padding_not_a_truncated_call(self):
        group = group_with("/Script/X.Y_ClassNetCache", {1: "Ping"}, 32)
        w = BitWriter()
        w.ranged(1, 32)
        w.packed(8)
        w.raw(0xFF, 8)
        w.raw(0, 5)  # too few bits to hold another call
        data, count = w.done()

        block = read_class_net_cache(BitReader(data, count), group)
        assert block.ok
        assert len(block.fields) == 1


class Stats(unittest.TestCase):
    def test_rates_are_tracked_per_kind(self):
        stats = PropertyStats()
        stats.record(read_rep_layout(BitReader(*_terminated_chain())))
        stats.record(read_rep_layout(BitReader(b"\x00", 1)))
        assert stats.rep_layout == 2
        assert stats.rep_layout_ok == 1
        assert stats.rep_layout_rate == 0.5

    def test_the_failure_list_is_capped(self):
        stats = PropertyStats()
        for i in range(50):
            stats.fail(f"kind {i}")
        report = stats.report()
        assert "rarer kinds" in report
        assert report.count("kind ") <= 10


def _terminated_chain():
    w = BitWriter()
    w.bit(0)
    w.packed(0)
    return w.done()


class ZeroLengthBlock(unittest.TestCase):
    def test_an_empty_payload_is_trivially_exact(self):
        block = decode_content_block(
            ContentBlock(flag_a=True, flag_b=False, num_bits=0, payload=b""),
            actor_guid=5,
            branch="++Ares-Core+release-12.10",
        )
        assert block.ok


@pytest.mark.skipif(not DEMO_12_10.exists(), reason="needs the 12.10 capture")
class AgainstARealCapture(unittest.TestCase):
    """
    The only test where the transform and the property loop meet.

    Rep-layout blocks are the honest measure here: the RPC path has no
    terminator, so a wrong reading of it can still look tidy, whereas a
    rep-layout chain either lands on handle 0 with no bits left or it does not.
    """

    def test_rep_layout_blocks_parse_almost_perfectly(self):
        from vrf_reader import REPLAYDATA, Oodle, VrfFile
        from vrfnet.calibrate import load
        from vrfnet.session import ReplaySession

        vrf = VrfFile(str(DEMO_12_10))
        session = ReplaySession(features=load(), branch=vrf.demo.build)
        oodle = Oodle.discover(None)
        for i, block in enumerate(vrf.data_blocks(kinds=(REPLAYDATA,))):
            if i >= 2:
                break
            session.feed_block(
                oodle.decompress(block.blob(vrf.data), block.decompressed_size),
            )

        assert session.props.rep_layout > 5000
        assert session.props.rep_layout_rate > 0.99
        # Names come from the export table, so this also pins the archetype ->
        # class path mapping that finds the group in the first place.
        assert session.props.fields_named > session.props.fields * 0.8
