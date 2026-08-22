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
import math
import statistics
import unittest
from pathlib import Path
from typing import ClassVar

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
            features=load(),
            branch=vrf.demo.build,
            collect_movement=True,
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


# How near a player pawn's own first movement sample its spawn location has to
# sit.  A player's first decoded position is ground truth for where they
# spawned, so the two describe the same instant and the same actor: across the
# 21 playable captures the median gap is 0.0 uu and the largest is 91.7.
SPAWN_GAP_UU = 100.0

# How far the killer's pitch may be from the true angle to the victim before
# the reading is not a reading.  Yaw, which nothing disputes, is inside 10
# degrees at 98.7% of kills; pitch reaches 98.4% with the same rule.
PITCH_TOLERANCE_DEGREES = 10.0
PITCH_AGREEMENT = 0.90

# Kills closer than this are excluded from the *angle*: a point-blank bearing
# is dominated by the offset between two capsule origins rather than by where
# anybody was looking.  They still count toward the separation below.
POINT_BLANK_UU = 100.0

# How far apart a killer and their victim may be.  Measured: at every one of
# the 190 characterDeath events in the reference capture the two are within
# 4,440 Unreal units and most within 2,000, which is weapon range.  A wrong
# transform or a wrong actor-to-track join scatters them across the map, and
# `clean_packet_rate` is blind to both.
WEAPON_RANGE_UU = 5000.0


def _signed(degrees):
    """An angle in 0..360 as one in -180..180.  Positive pitch is looking up."""
    wrapped = degrees % 360.0
    return wrapped - 360.0 if wrapped > 180.0 else wrapped


@pytest.mark.skipif(not DEMO_12_10.exists(), reason="needs the 12.10 capture")
class PitchPointsAtTheVictim(unittest.TestCase):
    """
    The measurement that decided pitch could be rendered at all.

    `Position.pitch` had been decoded since the movement layer was written and
    **rendered by nothing**, because nothing in the file, the catalogue or the
    manifest says whether 350 degrees is looking up or looking down.  Drawing a
    view direction on an unverified sign is the plausible wrong answer this
    project refuses, so it was measured the way the coordinates were: at every
    kill the killer's pitch is compared with the true angle to the victim,
    whose z is also known.

    Across the whole reference library that is 2,949 kills, a median error of
    0.91 degrees and 98.4% inside ten -- against yaw's 98.7%, which is the
    control.  The negated reading is four times worse.  So **positive pitch is
    looking up**, and this capture is the standing check on it.

    The separation check rides along here because it is the same geometry: two
    people in a gunfight are within weapon range of each other, and that is the
    one thing a wrong transform or a wrong actor-to-track join cannot fake.

    It also caught a bug on the way.  `Track.at` interpolated pitch *linearly*
    while interpolating yaw as an angle, so a player crossing the horizon
    between two samples -- 359.0 to 1.0 -- landed at 180, pointing backwards.
    With the shortest-arc rule the 99th-percentile error goes from 159 degrees
    to 11.4.
    """

    rows: ClassVar[list] = []
    separations: ClassVar[list] = []

    @classmethod
    def setUpClass(cls):
        from vrfview import pipeline, tracks

        replay = pipeline.open_replay(DEMO_12_10, None)
        tracks.attach(replay, DEMO_12_10)
        if not replay.has_positions:
            raise unittest.SkipTest(replay.position_source)

        cls.rows = []
        cls.separations = []
        for kill in replay.kills:
            if kill.is_suicide:
                continue
            killer = replay.track(kill.killer)
            victim = replay.track(kill.victim)
            if killer is None or victim is None:
                continue
            here = killer.at(kill.t_ms)
            there = victim.at(kill.t_ms)
            if here is None or there is None:
                continue
            flat = math.hypot(there.x - here.x, there.y - here.y)
            cls.separations.append(flat)
            if flat < POINT_BLANK_UU:
                continue
            bearing = math.degrees(math.atan2(there.y - here.y, there.x - here.x))
            cls.rows.append(
                (
                    _signed(here.pitch),
                    math.degrees(math.atan2(there.z - here.z, flat)),
                    _signed(bearing - here.yaw),
                ),
            )

    def _errors(self, sign):
        return sorted(
            abs(_signed(sign * pitch - truth)) for pitch, truth, _yaw in self.rows
        )

    def test_there_are_enough_kills_to_measure_anything(self):
        assert len(self.rows) > 50

    def test_the_killer_and_the_victim_are_within_weapon_range(self):
        """
        The ground-truth check that catches a wrong transform.

        `clean_packet_rate` cannot see this layer at all -- it is computed from
        bunch headers and never enters a payload -- so it will read 99.98%
        while every coordinate is wrong.  This is the check that cannot: two
        people in a gunfight are within weapon range of each other, and if the
        coordinates or the actor-to-track join were wrong they would be
        scattered across the map instead.
        """
        assert self.separations
        worst = max(self.separations)
        assert worst <= WEAPON_RANGE_UU, f"a kill spans {worst:.0f} uu"

    def test_the_killer_is_looking_at_the_victim(self):
        errors = self._errors(1.0)
        inside = sum(1 for e in errors if e <= PITCH_TOLERANCE_DEGREES) / len(errors)
        assert inside >= PITCH_AGREEMENT, f"only {inside:.1%} of kills inside tolerance"

    def test_the_negated_reading_is_worse_which_is_what_fixes_the_sign(self):
        """
        Agreement on its own is not enough: it has to beat the alternative.

        There are only two candidate signs, and if both agreed this would be
        measuring something other than where the killer was looking.
        """
        assert statistics.median(self._errors(1.0)) < statistics.median(
            self._errors(-1.0),
        )

    def test_pitch_is_no_worse_than_yaw_which_is_the_control(self):
        """
        Yaw is already validated by the cone work and by the spawn clusters.

        If pitch were being read out of the wrong bits it would be noise beside
        it, not within a few degrees of it.
        """
        pitch = statistics.median(self._errors(1.0))
        yaw = statistics.median(abs(_signed(y)) for _p, _t, y in self.rows)
        assert pitch < yaw + PITCH_TOLERANCE_DEGREES

    def test_no_player_sample_is_more_than_a_right_angle_off_the_horizon(self):
        """
        A pitch outside 90 degrees is a bug and not a look.

        Measured over 2,967,869 player samples across the library, 93.5% are
        within 15 degrees of level and not one exceeds 90.  This is also what
        the linear pitch interpolation used to break: it produced values near
        180, which no player ever holds.
        """
        for pitch, _truth, _yaw in self.rows:
            assert abs(pitch) <= 90.0


@pytest.mark.skipif(not DEMO_12_10.exists(), reason="needs the 12.10 capture")
class SpawnLocationsAreRealCoordinates(unittest.TestCase):
    """
    The check that let an ability have a place on the map for the first time.

    `csharp/VrfPositions` reads each channel's `ActorSpawned` transform and
    `csharpdecode` has parsed it into `Decoded.spawn_locations` for as long as
    it has existed -- and nothing consumed it, because nothing had established
    that those numbers were coordinates rather than plausible noise.

    This is the check that settled it, and it uses only data already in hand:
    **a player's first decoded position is ground truth for where they
    spawned**, so `spawn_locations[actor]` has to sit on top of it.  Across the
    21 playable captures every one of 210 player pawns does, to a median of 0.0
    uu and a maximum of 91.7.  A second measurement is in `vrfview.abilities`'
    own docstring: 98% to 100% of each ability kind lands inside the radar
    image's playable silhouette, where a coordinate drawn at random would land
    inside about a third of the time.
    """

    decoded: ClassVar = None

    @classmethod
    def setUpClass(cls):
        from vrfview import csharpdecode

        try:
            csharpdecode.locate(None)
        except csharpdecode.DecodeError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.decoded = csharpdecode.run(DEMO_12_10)

    def test_most_actors_that_move_also_state_where_they_appeared(self):
        """
        Not all of them, and that is the honest bound.

        An actor already open when the recording started never had a spawn
        event to read, so a missing location is a real state rather than a
        failure -- which is why `AbilitySpawn.location` is optional and why a
        cast with none says nothing instead of defaulting to the origin.
        """
        located = sum(
            1
            for actor, samples in self.decoded.samples.items()
            if samples and actor in self.decoded.spawn_locations
        )
        assert located > len(self.decoded.samples) / 2

    def test_a_spawn_location_sits_on_the_actors_own_first_sample(self):
        gaps = []
        for actor, samples in self.decoded.samples.items():
            spawn = self.decoded.spawn_locations.get(actor)
            if spawn is None or not samples:
                continue
            first = samples[0]
            gaps.append(math.dist(spawn, (first.x, first.y, first.z)))
        assert gaps, "no actor had both a spawn location and a sample"
        worst = max(gaps)
        assert worst <= SPAWN_GAP_UU, (
            f"a spawn point is {worst:.0f} uu from its own first sample"
        )
