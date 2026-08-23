"""
The measurements that decided what a decoded coordinate may be used for.

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

`WhatTheDrawnLinesCost` is the odd one out: it measures the *art* rather than
the decode, using the decode as its instrument.  It is here because it is the
same kind of evidence -- a fact about the world that no bug on either side
could invent -- and because it needs the same reference library to run at all.

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
ASSETS = Path("assets")


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

# How far from the caster a placement has to be before it is the thing the
# ability left standing rather than the spot the caster stood on.  Measured
# over the 21 playable captures as the distance to the caster's own decoded
# position at that instant: GameObject 2,005 uu, Zone 3,533, Patch 2,017,
# against Ability 259 and Projectile 42 -- two populations an order of
# magnitude apart, so this sits in the gap rather than near either.
LEFT_STANDING_UU = 500.0
THROWN_FROM_UU = 300.0

# How often the placement `landed` chooses lands inside the radar's playable
# silhouette.  A real coordinate does; one drawn at random lands inside about a
# third of the time.  Measured library-wide at 98.6%.
LANDED_INSIDE_SHARE = 0.95

# How many kill sightlines the radar silhouette is allowed to close.  Two
# people in a gunfight can see each other, so a mask that says otherwise is
# wrong about that kill -- and across the library the alpha silhouette is wrong
# about 1.05% of them, which is as good as a 2D approximation with no height
# data gets.  The bound is where it is so that a change to `ALPHA_FLOOR`, to
# the downsample or to the transform has somewhere to fail.
SILHOUETTE_FALSE_BLOCK = 0.03

# And how many the drawn lines close on top of that: 38.17% of the same
# sightlines, or thirty-six times the silhouette's rate.  The lines *are* the
# shipped occluder -- a cone that stops at interior structure was asked for --
# so this is pinned as a band rather than a ceiling.  A floor, because the
# number is evidence about what Riot's lines are and stops being evidence if it
# quietly improves; a ceiling, because a change to `walls.py` that took even
# more of the map would make sight worse still and nothing else would say so.
# See `vrfview/walls.py` for the whole table.
LINES_FALSE_BLOCK_FLOOR = 0.20
LINES_FALSE_BLOCK_CEILING = 0.55


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


@pytest.mark.skipif(not DEMO_12_10.exists(), reason="needs the 12.10 capture")
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

        # The decoder is checked for before it is run, and the capture is
        # checked for by the decorator above.  Without that decorator this
        # class was the one in the file with no `.vrf` gate, so on a machine
        # with a built decoder and no reference capture it *errored* where
        # every sibling skipped -- three red entries that say nothing about
        # the code, in the suite whose whole job is being believable.
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


@pytest.mark.skipif(not DEMO_12_10.exists(), reason="needs the 12.10 capture")
@pytest.mark.skipif(not ASSETS.is_dir(), reason="needs the art cache")
class WhatTheDrawnLinesCost(unittest.TestCase):
    """
    What the drawn walls cost the sight layer, kept where it can be re-run.

    Riot draws walls on every radar, `vrfview.walls` reads them back cleanly,
    and `sight.SightMap.from_image` folds them into the occluder so a cone
    stops at the interior walls the alpha silhouette misses.  That is the
    picture that was wanted.  It is also, by the only measure available here,
    less accurate than the silhouette alone, and this is where that stays
    written down in a form that runs.

    The instrument is the one this file already uses: **at every
    `characterDeath` the killer could see the victim**, so a mask that closes
    the line between them is wrong about that kill.  It cannot say when a mask
    is too *permissive*, and that asymmetry is the whole reason the result is
    stated as a comparison rather than as a score.

    Over 3,128 kills the silhouette closes 1.05% and the silhouette plus the
    lines closes 38.17%, and every attempt to rescue that failed for a reason
    worth knowing: a finer grid does not help (31.27% at full 1024 resolution,
    so it is not the mask being too thick), dropping the lines along the map
    rim does not help (37.15%, so it is not the silhouette's own outline), and
    keeping only lines at least three pixels wide scores 4.60% by discarding
    91% of them.

    What the numbers say is that **the silhouette already is the wall model**:
    a wall you cannot see through is drawn as a hole in the radar, and the
    lines on top of the floor are the readable detail -- doorframes, crates,
    ledges, stair treads -- that a quarter of all kills happen through or over.

    Both rates are asserted, and the second from both sides.  A check that only
    said "the silhouette is good" would pass just as happily on the day the
    lines started closing three-quarters of the map.
    """

    rows: ClassVar[list] = []
    seed: ClassVar[int] = 0

    @classmethod
    def setUpClass(cls):
        from PIL import Image

        from vrfview import art, pipeline, sight, tracks, walls

        cls.seed = sight.SEED_CELLS

        cache = art.load(ASSETS)
        if cache.empty:
            raise unittest.SkipTest(cache.reason)

        replay = pipeline.open_replay(DEMO_12_10)
        tracks.attach(replay, DEMO_12_10)
        if not replay.has_positions:
            raise unittest.SkipTest(replay.position_source)
        entry = cache.map_art(replay.map_path)
        if entry is None or entry.minimap is None or not entry.transform.usable:
            raise unittest.SkipTest("no usable radar for this capture's map")

        with Image.open(entry.minimap) as source:
            rgba = source.convert("RGBA")
            alpha = rgba.resize((sight.GRID, sight.GRID)).getchannel("A").tobytes()
            ink = walls.wall_cells(rgba, sight.GRID, alpha_floor=sight.ALPHA_FLOOR)

        open_cells = [1 if a >= sight.ALPHA_FLOOR else 0 for a in alpha]
        cls.silhouette = sight.SightMap(
            size=sight.GRID,
            cells=bytes(open_cells),
        )
        cls.inked = sight.SightMap(
            size=sight.GRID,
            cells=bytes(0 if w else o for o, w in zip(open_cells, ink, strict=True)),
        )

        cls.rows = []
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
            cls.rows.append(
                (
                    entry.transform.apply(here.x, here.y),
                    entry.transform.apply(there.x, there.y),
                ),
            )

    @classmethod
    def _closes(cls, mask, start, end):
        """
        Whether the mask blocks the straight line between two players.

        Both ends skip `sight.SEED_CELLS`, and not for symmetry: a player
        standing against a wall or in a doorway sits on a blocked cell often
        enough that refusing there would count the *victim's* own cover as an
        obstruction, which is the same reason `sight._march` seeds.
        """
        cell = 1.0 / mask.size
        du = end[0] - start[0]
        dv = end[1] - start[1]
        length = math.hypot(du, dv)
        steps = int(length / cell)
        seed = cls.seed
        if steps <= 2 * seed:
            return False
        for step in range(seed + 1, steps - seed):
            along = (step * cell) / length
            if mask.blocked(start[0] + du * along, start[1] + dv * along):
                return True
        return False

    def _rate(self, mask):
        closed = sum(1 for start, end in self.rows if self._closes(mask, start, end))
        return closed / len(self.rows)

    def test_there_are_enough_kills_to_measure_anything(self):
        assert len(self.rows) > 50

    def test_the_silhouette_lets_a_killer_see_their_victim(self):
        """The check that the sight layer as it ships is worth drawing."""
        rate = self._rate(self.silhouette)
        assert rate <= SILHOUETTE_FALSE_BLOCK, f"the silhouette closes {rate:.1%}"

    def test_the_drawn_lines_cost_what_they_are_recorded_as_costing(self):
        """
        A band, and the floor half is the unusual one.

        The ceiling is ordinary: a `walls.py` change that took more of the map
        would make every cone shorter and nothing else in the suite would
        notice.  The floor is there because this number is *evidence* about
        what Riot's lines are -- that they mark what you can see past rather
        than what stops a bullet -- and a silent improvement would mean the
        measurement had stopped measuring, not that the lines had changed.
        """
        rate = self._rate(self.inked)
        assert LINES_FALSE_BLOCK_FLOOR <= rate <= LINES_FALSE_BLOCK_CEILING, (
            f"the drawn lines close {rate:.1%} of real kill sightlines, outside "
            f"the recorded {LINES_FALSE_BLOCK_FLOOR:.0%}..{LINES_FALSE_BLOCK_CEILING:.0%}; "
            "re-measure vrfview/walls.py rather than moving this bound"
        )

    def test_the_lines_are_far_worse_than_the_silhouette_they_are_added_to(self):
        """The comparison is the finding; either rate alone is just a number."""
        assert self._rate(self.inked) > 5 * self._rate(self.silhouette)


@pytest.mark.skipif(not DEMO_12_10.exists(), reason="needs the 12.10 capture")
@pytest.mark.skipif(not ASSETS.is_dir(), reason="needs the art cache")
class LandedIsTheThingNotTheThrower(unittest.TestCase):
    """
    That `AbilityCast.landed` names where an ability ended up, not where it began.

    `PLACING_KINDS` is a ranking, and a ranking is only as good as the evidence
    for its order.  The evidence is the same shape as the spawn-location check
    above: a placement's distance from the caster's own decoded position at
    that instant separates two populations by an order of magnitude.  The
    things an ability leaves standing sit thousands of units away -- a
    `GameObject_` at a median 2,005 uu, a `Zone_` at 3,533, a `Patch_` at 2,017
    -- and the actors that merely record the decision sit on the caster, an
    `Ability_` at 259 uu and a `Projectile_` at 42, which is inside their own
    capsule.

    It was wrong, and quietly.  `Projectile_` was ranked above the placed kinds,
    so any cast without a `GameObject_` reported the *throw origin* as where it
    landed.  Omen's smoke is a `Zone_`, which the ranking did not name at all,
    so all 241 of them in the library were drawn on top of Omen instead of a
    median 3,061 uu away where the smoke was.  Nothing failed; the smokes were
    simply somewhere else, which is exactly the plausible wrong answer this
    file exists to catch.

    The reference capture carries no Omen and no Gekko, so `Zone_` and `Patch_`
    are checked by the library-wide figures recorded beside `PLACING_KINDS`.
    What runs here is the rule those figures justify.
    """

    casts: ClassVar[list] = []
    gaps: ClassVar[dict] = {}

    @classmethod
    def setUpClass(cls):
        from PIL import Image

        from vrfview import abilities, art, pipeline, sight

        cache = art.load(ASSETS)
        if cache.empty:
            raise unittest.SkipTest(cache.reason)
        replay = pipeline.open_replay(DEMO_12_10)
        if not replay.has_positions or not replay.ability_casts:
            raise unittest.SkipTest(replay.position_source)
        entry = cache.map_art(replay.map_path)
        if entry is None or entry.minimap is None or not entry.transform.usable:
            raise unittest.SkipTest("no usable radar for this capture's map")

        with Image.open(entry.minimap) as source:
            rgba = source.convert("RGBA")
            alpha = rgba.resize((sight.GRID, sight.GRID)).getchannel("A").tobytes()
        cls.silhouette = sight.SightMap(
            size=sight.GRID,
            cells=bytes(1 if a >= sight.ALPHA_FLOOR else 0 for a in alpha),
        )
        cls.transform = entry.transform
        cls.casts = list(replay.ability_casts)
        cls.placing = abilities.PLACING_KINDS

        attribution = abilities.attribute(replay.players)
        gaps: dict[str, list[float]] = {}
        for cast in cls.casts:
            actor = attribution.by_codename.get(cast.codename)
            track = replay.track(actor) if actor is not None else None
            here = track.at(cast.t_ms) if track is not None else None
            if here is None:
                continue
            for place in cast.placements:
                gaps.setdefault(place.kind, []).append(
                    math.hypot(place.x - here.x, place.y - here.y),
                )
        cls.gaps = gaps

    def test_there_are_enough_casts_to_measure_anything(self):
        assert len(self.casts) > 50

    def test_a_left_standing_actor_is_nowhere_near_the_caster(self):
        """The half that says `GameObject_` is worth ranking first."""
        for kind in ("GameObject", "Zone", "Patch"):
            seen = self.gaps.get(kind)
            if not seen:
                continue
            median = statistics.median(seen)
            assert median >= LEFT_STANDING_UU, (
                f"{kind} placements sit a median {median:.0f} uu from the caster, "
                "which is the caster's own feet rather than where the ability went"
            )

    def test_a_throw_origin_is_on_top_of_the_caster(self):
        """
        The other half, and the one that makes the ranking an argument.

        If these were also far away the order would be arbitrary.  They are
        not: a `Projectile_` spawns inside the caster's own capsule.
        """
        for kind in ("Projectile", "Ability"):
            seen = self.gaps.get(kind)
            if not seen:
                continue
            median = statistics.median(seen)
            assert median <= THROWN_FROM_UU, (
                f"{kind} placements sit a median {median:.0f} uu from the caster; "
                "if that is real then PLACING_KINDS is ranked on nothing"
            )

    def test_a_thing_left_standing_always_outranks_a_throw_origin(self):
        """
        The rule itself, on every cast that has both witnesses.

        This is what regressed: `Projectile_` ranked third and `Zone_` not at
        all, so a cast carrying both reported the throw origin.

        Casts with a pawn are skipped rather than asserted on: `landed` refuses
        outright where there is a track, because a track always outranks a
        spawn point and a drone's start is not where the drone is.
        """
        standing = {"GameObject", "Zone", "Patch"}
        for cast in self.casts:
            if cast.pawns:
                continue
            kinds = {p.kind for p in cast.placements}
            if not (kinds & standing) or not (kinds & {"Projectile", "Ability"}):
                continue
            assert cast.landed is not None
            assert cast.landed.kind in standing, (
                f"{cast.codename} {cast.slot} landed on a "
                f"{cast.landed.kind} with {sorted(kinds)} available"
            )

    def test_the_placement_lands_inside_the_playable_area(self):
        """
        Ground truth that no ranking bug could fake.

        A coordinate drawn at random lands inside the silhouette about a third
        of the time, because 47% to 72% of every radar is transparent void.
        """
        landed = [c.landed for c in self.casts if c.landed is not None]
        assert landed
        inside = 0
        for place in landed:
            u, v = self.transform.apply(place.x, place.y)
            if not self.silhouette.blocked(u, v):
                inside += 1
        share = inside / len(landed)
        assert share >= LANDED_INSIDE_SHARE, f"only {share:.1%} land inside the map"
