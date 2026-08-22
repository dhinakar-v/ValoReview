"""
The two measurements that decided what a decoded coordinate may be used for.

Neither is a unit test.  Both march a whole reference capture through the C#
decoder and check a fact about the world that no decoding bug could invent,
which is the only kind of evidence available here: nothing in a `.vrf`, in
val-content-v1 or in the asset manifest states where a player was or which way
they were looking, so the decode cannot be checked against a published answer.

`PitchPointsAtTheVictim` settled the *sign* of `Position.pitch`, which had been
decoded from the first and rendered by nothing because no source says whether
350 degrees is up or down.  `SpawnLocationsAreRealCoordinates` settled that
`Decoded.spawn_locations` holds coordinates at all, which is what let an
ability have a place on the map.

These used to live in `tests/test_movement.py` beside the unit tests for the
pure-Python movement bitstream.  That decoder is gone -- the C# one replaced it
and `libraries/vrfnet/` is now the build table and nothing else -- but these
two are about the decode this project actually runs, so they outlived it.
"""

from __future__ import annotations

import math
import statistics
import unittest
from pathlib import Path
from typing import ClassVar

import pytest

DEMO_12_10 = Path("Demos/03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf")


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

# How near a player the planted spike has to be, and how often.  A spike is
# planted at the planter's feet, so across the library the median gap is 69.5
# uu and 94.5% are inside 100.  It is a share rather than a maximum because
# `Track.at` refuses to interpolate across a long gap: at a few plants the
# planter has no sample at all and the nearest other player is a room away,
# which is a fact about the 10 Hz thinning rather than about the coordinate.
PLANT_NEAR_PLAYER_UU = 100.0
PLANT_NEAR_PLAYER_SHARE = 0.85


def infer_with_positions():
    """
    The reference capture, decoded, with its plants paired onto its events.

    `cache=False` deliberately.  A ground-truth measurement that reads the
    machine's cache passes or fails on what some earlier run happened to leave
    there -- and a sidecar written before the plants were measured is a real,
    readable v3 file with no plants in it, so this would fail on a developer's
    machine and pass on a clean one.  The decode is seconds; the ambiguity is
    not worth saving them.
    """
    from vrfview import infer, loader, tracks

    replay = infer.annotate(loader.load(DEMO_12_10))
    tracks.attach(replay, DEMO_12_10, tracks.Options(decode=True, cache=False))
    return replay


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

        replay = pipeline.open_replay(DEMO_12_10)
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


class SpikePlantsAreRealCoordinates(unittest.TestCase):
    """
    The check that let the spike have a place on the map for the first time.

    A `spikePlanted` event carries no arguments at all -- `args` is just the
    type ID -- so for a long time the plant's coordinate was taken to be one of
    the things a `.vrf` simply does not hold.  It holds it twice removed:
    planting spawns a `/Game/GameModes/Bomb/TimedBomb` actor, `csharpdecode`
    has carried every actor's spawn transform since it was written, and
    `tracks` kept the ones under `/Game/Characters/` and dropped the rest.

    Three facts settled that these are the plant rather than an actor that
    happens to appear nearby, and none of them could be satisfied by a
    decoding bug.  Measured over the 21 playable captures, 274 plants:

      * the TimedBomb spawn count equals the plant count in **every** capture,
        and all 274 pair one-to-one with none left over;
      * the pairing offset is a constant +8..15 ms -- the decoder's own time
        base, the same offset the first actors of the match are seen at, not
        jitter;
      * the coordinate is a median 69.5 uu from some player's own decoded
        position at that instant and 94.5% are within 100 uu, which is what
        "planted at the planter's feet" looks like through a 10 Hz thinning;
      * and **274 of 274 land inside the radar image's playable silhouette**,
        where a coordinate drawn at random lands inside about a third of the
        time.

    Only the plant is read.  `Bomb_Defuser` actors carry transforms too and
    nothing has measured them, so nothing reads them: an unmeasured coordinate
    drawn on a map is indistinguishable from a decoded one.
    """

    decoded: ClassVar = None
    replay: ClassVar = None

    @classmethod
    def setUpClass(cls):
        from vrfview import csharpdecode, infer, loader

        try:
            csharpdecode.locate(None)
        except csharpdecode.DecodeError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.decoded = csharpdecode.run(DEMO_12_10)
        cls.replay = infer.annotate(loader.load(DEMO_12_10))

    def _plants(self):
        from vrfview import tracks

        return tracks._plants_from(
            self.decoded.archetypes,
            self.decoded.first_seen,
            self.decoded.spawn_locations,
        )

    def test_every_plant_event_has_exactly_one_plant_actor(self):
        """
        Counted, not matched: a spare actor would mean the archetype is wrong.

        Pairing by nearest time can always find *something*, so the count is
        the check that cannot be fudged -- if `TimedBomb` named anything other
        than the planted spike there would be a different number of them.
        """
        events = [s for s in self.replay.spike if s.kind == "planted"]
        assert len(self._plants()) == len(events)

    def test_the_two_clocks_differ_by_a_constant_and_not_by_noise(self):
        from vrfview import tracks

        events = sorted(s.t_ms for s in self.replay.spike if s.kind == "planted")
        offsets = [
            plant[0] - t_ms
            for plant, t_ms in zip(sorted(self._plants()), events, strict=True)
        ]
        assert offsets, "the reference capture has no plant"
        # A time base, so every offset is small and positive and they agree
        # with each other; noise would straddle zero and spread.
        assert min(offsets) >= 0
        assert max(offsets) <= tracks.PLANT_PAIR_MS
        assert max(offsets) - min(offsets) <= 50

    def test_a_plant_sits_where_somebody_was_standing(self):
        """
        A spike is planted at the planter's feet, and every player's position
        at that instant is already known -- so the plant coordinate has to fall
        on one of them.  Not all of them: `Track.at` refuses to interpolate
        across a long gap, so at some plants the planter has no sample and the
        nearest *other* player is genuinely far away.  That is a property of
        the thinning, which is why this is a share rather than a maximum.
        """

        replay = infer_with_positions()
        events = [s for s in replay.spike if s.kind == "planted"]
        assert events, "the reference capture has no plant"
        assert all(s.placed for s in events), "a plant was not paired"

        near = 0
        for event in events:
            x, y, _z = event.location
            gaps = [
                math.dist((pos.x, pos.y), (x, y))
                for player in replay.players
                if (track := replay.positions.get(player.actor_id)) is not None
                and (pos := track.at(event.t_ms)) is not None
            ]
            if gaps and min(gaps) <= PLANT_NEAR_PLAYER_UU:
                near += 1
        share = near / len(events)
        assert share >= PLANT_NEAR_PLAYER_SHARE, (
            f"only {share:.0%} of plants are within {PLANT_NEAR_PLAYER_UU:.0f} uu "
            f"of any player's own position at that instant"
        )
