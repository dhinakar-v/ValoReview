"""
Tests for the movement bitstream.

The unit tests below pin the primitives that are easy to get subtly wrong and
impossible to notice: a VLQ whose continuation flag is the *low* bit, a sign
extension, a quantiser whose scale is applied only when a flag says so, and a
marker cycle that skips 0.  Each of those, done wrong, still yields numbers.

The test that actually proves the decoder is `test_players_start_at_two_spawns`.
It asserts a fact about Haven that no decoding bug could invent: at the first
frame the ten players stand in two tight clusters, one per spawn, matching
coordinates Riot publishes in `assets/manifest.json` -- which this pipeline
never consults while decoding.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pytest

from vrfnet.bitreader import BitReader
from vrfnet.movement import (
    ANGLE_SCALE,
    MOVEMENT_RPC,
    MovementLog,
    _next_marker,
    _read_fixed_vector,
    _read_quantized_vector,
    _read_vlq,
    _sign_extend,
    read_component_data,
)

DEMO_12_10 = Path("Demos/03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf")
MANIFEST = Path("assets/manifest.json")
HAVEN_URL = "/Game/Maps/Triad/Triad"

# How near a spawn a player must start.  Generous, because a spawn callout is
# the centre of a room and ten players cannot stand on one point.
SPAWN_RADIUS = 2500.0


def bits_to_bytes(bits):
    out = bytearray((len(bits) + 7) // 8)
    for i, b in enumerate(bits):
        if b:
            out[i // 8] |= 1 << (i % 8)
    return bytes(out), len(bits)


def raw(value, count):
    return [(value >> i) & 1 for i in range(count)]


class Primitives(unittest.TestCase):
    def test_vlq_continuation_flag_is_the_low_bit(self):
        # 72 fits one group: (72 & 0x7F) << 1, continuation clear.
        assert _read_vlq(BitReader(bytes([72 << 1]), 8)) == 72

    def test_vlq_spans_groups(self):
        # 300 = 0b100101100 -> low 7 bits with the flag set, then the rest.
        low = ((300 & 0x7F) << 1) | 1
        high = (300 >> 7) << 1
        assert _read_vlq(BitReader(bytes([low, high]), 16)) == 300

    def test_sign_extend_round_trips_negatives(self):
        assert _sign_extend(0b0111, 4) == 7
        assert _sign_extend(0b1000, 4) == -8
        assert _sign_extend(0b1111, 4) == -1

    def test_quantised_vector_divides_only_when_flagged(self):
        # 8-bit components, scale flag set: values are hundredths.  200 is
        # -56 once sign-extended, which is the whole point of testing it.
        bits = raw(8 | (1 << 6), 7) + raw(100, 8) + raw(200, 8) + raw(50, 8)
        vec = _read_quantized_vector(BitReader(*bits_to_bytes(bits)), 100)
        assert (vec.x, vec.y, vec.z) == (1.0, -0.56, 0.5)

    def test_quantised_vector_keeps_units_when_unflagged(self):
        bits = raw(8, 7) + raw(100, 8) + raw(200, 8) + raw(50, 8)
        vec = _read_quantized_vector(BitReader(*bits_to_bytes(bits)), 100)
        assert (vec.x, vec.y, vec.z) == (100.0, -56.0, 50.0)

    def test_fixed_vector_is_centred_on_0x8000(self):
        bits = raw(0x8000, 16) + raw(0x8000 + 65536 // 4, 16) + raw(0, 16)
        vec = _read_fixed_vector(BitReader(*bits_to_bytes(bits)))
        assert vec.x == 0.0
        assert vec.y == pytest.approx(0.25)
        assert vec.z == pytest.approx(-0.5)

    def test_marker_cycle_never_returns_to_zero(self):
        # 0 ends a run, so the cycle steps 1..7 and wraps back to 1.
        assert [_next_marker(m) for m in range(1, 8)] == [2, 3, 4, 5, 6, 7, 1]

    def test_angle_scale_covers_one_turn(self):
        assert pytest.approx(360.0, abs=0.01) == 0xFFFF * ANGLE_SCALE


class BadStreams(unittest.TestCase):
    def test_a_wrong_magic_is_reported_not_raised(self):
        data, count = bits_to_bytes(raw(0, 16) + raw(0xFF, 8) + raw(0, 64))
        result = read_component_data(data, count)
        assert not result.magic_ok
        assert result.moves == []
        assert "magic" in result.error

    def test_an_empty_stream_is_not_a_crash(self):
        assert read_component_data(b"", 0).moves == []


class Log(unittest.TestCase):
    def test_the_rpc_name_is_the_one_that_carries_positions(self):
        assert MOVEMENT_RPC.startswith("ReplaysClientReceiveRemoteCharacterUpdates")

    def test_an_empty_log_reports_nothing_rather_than_dividing_by_zero(self):
        log = MovementLog()
        assert log.moves == 0
        assert log.characters == 0
        assert log.bounds(1) == (0.0, 0.0, 0.0, 0.0)


@pytest.mark.skipif(
    not (DEMO_12_10.exists() and MANIFEST.exists()),
    reason="needs the 12.10 capture and a fetched asset manifest",
)
class AgainstARealCapture(unittest.TestCase):
    log: MovementLog

    @classmethod
    def setUpClass(cls):
        from vrf_reader import REPLAYDATA, Oodle, VrfFile
        from vrfnet.calibrate import load
        from vrfnet.session import ReplaySession

        vrf = VrfFile(str(DEMO_12_10))
        cls.map_url = vrf.demo.maps[0] if vrf.demo.maps else ""
        session = ReplaySession(
            features=load(), branch=vrf.demo.build, collect_movement=True,
        )
        oodle = Oodle.discover(None)
        for i, block in enumerate(vrf.data_blocks(kinds=(REPLAYDATA,))):
            if i >= 2:
                break
            session.feed_block(
                oodle.decompress(block.blob(vrf.data), block.decompressed_size),
            )
        cls.log = session.movement

    def test_every_movement_rpc_decodes(self):
        # Movement has no per-record checksum beyond the marker cycle, so a
        # single failure means the layout is wrong, not that the data is noisy.
        assert self.log.batches > 10_000
        assert self.log.batches_failed == 0
        assert self.log.streams_failed == 0

    def test_ten_players_move(self):
        # Ability actors (a turret, a camera) also get movement records, but
        # they never move: only the players accumulate a wide range.
        movers = [
            guid
            for guid in self.log.samples
            if self.log.bounds(guid)[1] - self.log.bounds(guid)[0] > 1000
        ]
        assert len(movers) == 10

    def test_players_start_at_two_spawns(self):
        spawns = self._spawns()
        assert len(spawns) == 2

        starts = []
        for guid, samples in self.log.samples.items():
            x0, x1, _y0, _y1 = self.log.bounds(guid)
            if x1 - x0 > 1000:  # players only
                starts.append((guid, samples[0][1].position))

        near = {0: 0, 1: 0}
        for _guid, pos in starts:
            best = min(
                range(2),
                key=lambda i: (pos.x - spawns[i][0]) ** 2 + (pos.y - spawns[i][1]) ** 2,
            )
            distance = (
                (pos.x - spawns[best][0]) ** 2 + (pos.y - spawns[best][1]) ** 2
            ) ** 0.5
            assert distance < SPAWN_RADIUS, f"{pos} is {distance:.0f} from any spawn"
            near[best] += 1

        assert near[0] == 5
        assert near[1] == 5

    def _spawns(self):
        doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for entry in doc["maps"].values():
            if entry.get("map_url") == HAVEN_URL:
                return [
                    (c["location"]["x"], c["location"]["y"])
                    for c in entry["callouts"]
                    if c["regionName"] == "Spawn"
                ]
        return []
