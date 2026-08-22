"""
The committed fixtures still say what Python says.

`tests/golden/` is the contract between two implementations of one model: the
Python one in `vrfview.model`, `state`, `clock`, `art` and `sight`, and the
TypeScript port in `web/src/model/` that the browser actually renders from.
`scripts/make_golden.py` writes the files; this asserts Python still reproduces
them, and `web/src/model/__tests__/parity.test.ts` asserts TypeScript computes
the same values from the same inputs.

The ordering is the point.  A Python change that would break the browser fails
here first, in a suite that runs in twenty-five seconds with no npm involved,
and regenerating a fixture is a deliberate act that arrives as a diff someone
has to read.

Byte for byte, and only on this side
------------------------------------
Python compares bytes because Python wrote them.  TypeScript compares *values*,
because `json.dumps` and `JSON.stringify` disagree about how to spell a float --
`1.0` against `1`, `1e-05` against `0.00001` -- while both recover the identical
double from either spelling.  Asserting bytes across the two would be a test of
number formatting rather than of the model.

Everything either side compares is exact, with one stated exception: `atan2`,
`cos` and `sin` are specified as *approximate* in both languages and
implemented differently in each.  So `sight.ray_directions` is written into
`cone.json` beside every polygon, the far end compares those within a bound and
then marches Python's own directions through arithmetic that is exact.  The
occlusion a cone actually depends on -- which cell stopped which ray -- is
therefore pinned to the bit; three library calls are not.

The tests below the regeneration check are not duplicates of it.  They assert
that each fixture still *contains the case it was written for*: a regenerated
file always matches itself, so nothing but a named assertion stops a case
quietly disappearing from the generator.
"""

from __future__ import annotations

import base64
import json
import math
import unittest
from pathlib import Path

import make_golden
from vrfview import sight

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "golden"

STALE = "tests/golden/ is out of date; run runners\\make-golden.bat"


def _fixture(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


class Regenerates(unittest.TestCase):
    def test_every_committed_fixture_is_current(self):
        for name, document in make_golden.fixtures().items():
            path = GOLDEN / name
            assert path.is_file(), f"{path} is missing; {STALE}"
            assert path.read_text(encoding="utf-8") == make_golden.render(document), (
                f"{name} does not match what make_golden writes; {STALE}"
            )

    def test_check_agrees_with_the_committed_files(self):
        assert make_golden.main(["--check"]) == 0

    def test_nothing_is_committed_that_the_generator_does_not_write(self):
        """
        A fixture nobody generates is one nobody maintains.

        It would keep passing the parity test on the far end long after the
        rule it describes had moved, which is worse than not having it.
        """
        written = set(make_golden.fixtures())
        found = {p.name for p in GOLDEN.glob("*.json")}
        assert found == written


class TrackAtCoversEveryBranch(unittest.TestCase):
    """
    `Track.at` has three answers and the fixture has to reach all of them.

    Interpolate across a short gap, hold a lone sample briefly, and past that
    report no position at all rather than a stale one dressed as current.  The
    third is the one worth guarding: a fixture that never produces `null`
    would let a port that always guesses a coordinate pass.
    """

    def setUp(self):
        self.doc = _fixture("track_at.json")
        self.cases = self.doc["cases"]

    def test_some_case_refuses_to_answer(self):
        assert any(case["at"] is None for case in self.cases)

    def test_some_case_is_an_exact_sample(self):
        assert any(
            case["at"] is not None and case["at"]["t_ms"] == case["t_ms"]
            for case in self.cases
        )

    def test_some_case_is_a_held_sample_carrying_its_own_older_timestamp(self):
        """
        A held Position keeps the millisecond it was measured at.

        That is how the caller can tell how fresh it is, and a port that
        stamped the requested time onto it would lose the only signal there is.
        """
        assert any(
            case["at"] is not None and case["at"]["t_ms"] != case["t_ms"]
            for case in self.cases
        )

    def test_a_yaw_crossing_zero_interpolates_the_short_way(self):
        """
        The one line a naive TypeScript port gets wrong.

        Python's `%` takes the sign of the divisor and JavaScript's the sign of
        the dividend, so a heading going 350 -> 10 interpolates 340 degrees
        backwards instead of 20 forwards.  It reads as a rendering glitch
        rather than an arithmetic one, so it is pinned on both sides.
        """
        found = [c for c in self.cases if "350 -> 10" in c["why"]]
        assert found, "the yaw-crossing case has gone from make_golden"
        yaw = found[0]["at"]["yaw"]
        assert yaw in (0.0, 360.0) or yaw < 20.0 or yaw > 340.0

    def test_a_negative_yaw_is_carried_rather_than_refused(self):
        assert any("negative yaw" in c["why"] for c in self.cases)


class SnapshotsCoverTheInstantsThatDecideSomething(unittest.TestCase):
    def setUp(self):
        self.doc = _fixture("snapshots.json")
        self.snaps = self.doc["snapshots"]

    def test_there_are_enough_of_them_to_be_worth_having(self):
        assert len(self.snaps) >= 40

    def test_the_first_and_last_instants_are_the_ends_of_the_match(self):
        replay = _fixture("replay.json")
        assert self.snaps[0]["t_ms"] == 0
        assert self.snaps[-1]["t_ms"] == replay["length_ms"]

    def test_past_the_end_is_clamped_rather_than_refused(self):
        """`state_at` clamps, so a scrubber dragged off the end still draws."""
        assert self.snaps[-1]["t_ms"] == _fixture("replay.json")["length_ms"]

    def test_somebody_is_dead_in_some_snapshot_and_alive_in_another(self):
        assert any(snap["dead_since"] for snap in self.snaps)
        assert any(not snap["dead_since"] for snap in self.snaps)

    def test_alive_is_scoped_to_the_round_and_resets_at_a_boundary(self):
        """
        Everyone is alive at a round boundary, which is what the file implies.

        There is no respawn event anywhere in a `.vrf`, so a port that carried
        deaths across a round would empty the map by round three.  The
        exception is a round that opens with a death on its very first
        millisecond -- there is one in the fixture on purpose, because
        `Round.contains` is half-open and getting that backwards moves a kill
        into the wrong round.
        """
        replay = _fixture("replay.json")
        killed_at = {k["t_ms"] for k in replay["kills"]}
        starts = {r["start_ms"] for r in replay["rounds"]} - killed_at
        at_starts = [s for s in self.snaps if s["t_ms"] in starts]
        assert at_starts
        for snap in at_starts:
            assert snap["dead_since"] == []

    def test_a_kill_on_a_round_boundary_belongs_to_the_round_it_opens(self):
        replay = _fixture("replay.json")
        starts = {r["start_ms"]: r["number"] for r in replay["rounds"]}
        on_boundary = [k for k in replay["kills"] if k["t_ms"] in starts]
        assert on_boundary, "the boundary kill has gone from make_golden"
        kill = on_boundary[0]
        snap = next(s for s in self.snaps if s["t_ms"] == kill["t_ms"])
        assert snap["round"] == starts[kill["t_ms"]]
        assert [e["actor_id"] for e in snap["dead_since"]] == [kill["victim"]]

    def test_a_suicide_is_a_death_and_never_a_kill(self):
        replay = _fixture("replay.json")
        suicides = [k for k in replay["kills"] if k["is_suicide"]]
        assert suicides, "the suicide case has gone from make_golden"
        actor = suicides[0]["victim"]
        after = next(s for s in self.snaps if s["t_ms"] > suicides[0]["t_ms"])
        entry = next(e for e in after["kd"] if e["actor_id"] == actor)
        assert entry["deaths"] >= 1

    def test_the_spike_reaches_every_state_it_can(self):
        assert {s["spike_state"] for s in self.snaps} >= {
            "none",
            "planted",
            "defused",
            "exploded",
        }

    def test_a_position_is_absent_in_some_snapshot_rather_than_guessed(self):
        """
        Where `Track.at` refuses, the snapshot has no entry for that actor.

        Never a last-known coordinate promoted to the present: inventing one
        downstream of a refusal is exactly what the refusal exists to prevent.
        """
        counts = {len(s["positions"]) for s in self.snaps}
        assert min(counts) < max(counts)


class TransformPinsTheAxisSwap(unittest.TestCase):
    def setUp(self):
        self.doc = _fixture("transform.json")

    def test_world_y_feeds_u_and_world_x_feeds_v(self):
        transform = self.doc["transform"]
        for point in self.doc["points"]:
            u, v = point["uv"]
            assert u == (
                point["world_y"] * transform["x_multiplier"]
                + transform["x_scalar_to_add"]
            )
            assert v == (
                point["world_x"] * transform["y_multiplier"]
                + transform["y_scalar_to_add"]
            )

    def test_the_swapped_pair_does_not_land_in_the_same_place(self):
        """
        (1000, 2000) and (2000, 1000) are in the fixture for this one test.

        The unswapped form is a plausible wrong answer rather than an obvious
        one -- 200 of 346 callouts still land inside the image -- so the two
        orderings have to be visibly different somewhere a test can see it.
        """
        pairs = {
            (p["world_x"], p["world_y"]): tuple(p["uv"]) for p in self.doc["points"]
        }
        assert pairs[(1000.0, 2000.0)] != pairs[(2000.0, 1000.0)]

    def test_a_negative_multiplier_keeps_its_sign(self):
        far = next(p for p in self.doc["points"] if p["world_x"] == 10000.0)
        assert far["uv"][1] < 0.5

    def test_the_vertical_scale_is_the_average_of_the_two_multipliers(self):
        transform = self.doc["transform"]
        assert (
            transform["vertical_scale"]
            == (abs(transform["x_multiplier"]) + abs(transform["y_multiplier"])) / 2
        )


class ConeCarriesItsOwnCaption(unittest.TestCase):
    def setUp(self):
        self.doc = _fixture("cone.json")

    def test_the_caption_is_sight_pys_own_words(self):
        assert self.doc["caption"] == sight.CAPTION

    def test_the_mask_round_trips_through_base64(self):
        mask = self.doc["mask"]
        cells = base64.b64decode(mask["cells"])
        assert len(cells) == mask["size"] ** 2
        assert set(cells) <= {0, 1}

    def test_an_empty_polygon_is_a_case_and_not_an_accident(self):
        """
        No heading and no radius each mean *draw nothing*.

        Never a fallback circle: a circle where a cone belongs claims the
        player can see in every direction, which is the one thing a sight
        approximation must not say.
        """
        empty = [c for c in self.doc["cones"] if c["polygon"] == []]
        assert len(empty) >= 2

    def test_a_ray_leaving_the_grid_does_not_wrap_to_the_far_side(self):
        """
        `blocked` uses floor, not int.

        `int(-0.8)` is 0, so a ray leaving the left edge would silently
        reappear in column zero -- a cone wrapping onto the other side of the
        map, on any map whose spawn sits near an edge.
        """
        off = [c for c in self.doc["blocked"] if c["u"] < 0 or c["v"] < 0]
        assert off, "the off-the-edge case has gone from make_golden"
        assert all(c["blocked"] for c in off)

    def test_a_wall_stops_a_ray_short_of_the_radius(self):
        into_wall = next(c for c in self.doc["cones"] if "into the wall" in c["why"])
        origin = into_wall["origin"]
        reach = max(abs(u - origin[0]) for u, _v in into_wall["polygon"][1:])
        assert reach < into_wall["radius"]

    def test_a_doorway_lets_a_ray_through_it(self):
        through = next(
            c for c in self.doc["cones"] if "through the doorway" in c["why"]
        )
        wall_u = make_golden.MASK_WALL_COLUMN / make_golden.MASK_SIZE
        assert any(u > wall_u for u, _v in through["polygon"][1:])

    def test_every_cone_carries_the_rays_it_was_marched_along(self):
        """
        The only numbers here that cannot be compared exactly across languages.

        `atan2`, `cos` and `sin` are approximate by specification in both
        Python and JavaScript.  Writing the directions out lets the far end
        march *these* rather than its own, so everything downstream -- which
        cell stopped which ray -- stays exact and the tolerance covers three
        library calls rather than a raycaster.
        """
        for entry in self.doc["cones"]:
            heading = entry["forward"] != [0.0, 0.0]
            # No heading is the one case with no rays: there is no direction to
            # take a field of view around.  A radius of zero still has rays and
            # simply draws none of them.
            assert bool(entry["rays"]) is heading, entry["why"]
            if entry["polygon"]:
                assert len(entry["polygon"]) == len(entry["rays"]) + 1

    def test_the_heading_is_probed_rather_than_computed_in_uv_space(self):
        """
        Every forward vector is a unit vector, which is what the probe returns.

        The trap this guards is not a magnitude, it is a rotation: doing the
        trigonometry in uv space puts every cone ninety degrees out, and it
        looks entirely plausible on screen.  The parity test on the other side
        of the wire compares the actual components against these.
        """
        for entry in self.doc["forward_uv"]:
            du, dv = entry["forward"]
            assert abs((du * du + dv * dv) ** 0.5 - 1.0) < 1e-12


class ClockIsDrivenByDeltasAndNeverByTheWallClock(unittest.TestCase):
    def setUp(self):
        self.doc = _fixture("clock.json")
        self.steps = self.doc["steps"]

    def test_ticking_while_paused_moves_nothing(self):
        """
        No time accumulates across a pause, so resuming does not jump.

        The tick that *ends* playback is deliberately not in this set: it moved
        real time and then stopped, which is a different thing from being
        paused when it arrived.
        """
        paused = [
            step
            for before, step in zip(self.steps, self.steps[1:], strict=False)
            if step["op"] == "tick" and not before["playing"]
        ]
        assert paused
        assert all(step["moved"] == 0.0 for step in paused)
        assert all(
            step["t_ms"] == before["t_ms"]
            for before, step in zip(self.steps, self.steps[1:], strict=False)
            if step["op"] == "tick" and not before["playing"]
        )

    def test_speed_scales_the_delta_and_not_the_frame_rate(self):
        """
        Four times the delta, to within the float the playhead was already at.

        This is the one comparison in the suite that is not exact, and it is
        not a parity assertion: `moved` is the difference of two accumulated
        positions, so it carries the representation error of wherever the
        clock had got to.  The parity test compares this fixture's numbers
        against TypeScript's *exactly*, which is where exactness belongs.
        """
        fast = next(
            s
            for s in self.steps
            if s["op"] == "tick" and s["speed"] == 4.0 and s["moved"]
        )
        assert abs(fast["moved"] - fast["arg"] * fast["speed"]) < 1e-9

    def test_reaching_the_end_stops_playback(self):
        ended = [s for s in self.steps if s["at_end"]]
        assert ended
        assert not ended[0]["playing"]

    def test_seeking_is_clamped_at_both_ends(self):
        assert all(0 <= s["t_ms"] <= self.doc["length_ms"] for s in self.steps)

    def test_a_speed_of_zero_is_refused(self):
        """A stopped clock is what pause is for; a zero speed is a stuck one."""
        zero = next(s for s in self.steps if s["op"] == "set_speed" and s["arg"] == 0.0)
        assert zero["speed"] > 0


class SmokesStopACone(unittest.TestCase):
    """
    The dynamic half of the occluder, which the mask cannot carry.

    A wall is one document per map and is fetched once; a smoke is a fact about
    one millisecond of one round, so it travels as an argument to `cone` rather
    than as cells in the bitmask.  These fixtures are what keeps the TypeScript
    port of that argument honest -- see parity.test.ts.
    """

    def setUp(self):
        self.doc = _fixture("cone.json")
        self.cones = self.doc["smoke_cones"]

    @staticmethod
    def _reach(entry):
        """How far the middle ray of a cone got, which is the one aimed dead on."""
        polygon = entry["polygon"]
        middle = polygon[len(polygon) // 2]
        return math.dist(entry["origin"], middle)

    def _named(self, fragment):
        return next(c for c in self.cones if fragment in c["why"])

    def test_a_smoke_in_the_way_stops_the_ray_short(self):
        smoked = self._named("east into a smoke")
        clear = self._named("no smoke")
        assert self._reach(smoked) < self._reach(clear)

    def test_a_smoke_behind_the_origin_stops_nothing(self):
        """
        Otherwise the test would pass for a rule that just shortens every cone.

        A circle test that used distance from the centre without regard to
        which way the ray went would fail exactly here.
        """
        behind = self._named("behind the origin")
        clear = self._named("no smoke")
        assert self._reach(behind) == self._reach(clear)

    def test_standing_inside_a_smoke_does_not_blank_the_cone(self):
        """
        `SEED_CELLS` gates the circle test as well as the mask.

        Without that a player who threw a smoke at their own feet would have no
        cone at all, which is the same "blinks off exactly when it matters"
        failure the seed exists to prevent.
        """
        inside = self._named("from inside the smoke")
        assert self._reach(inside) > 0
        assert len(inside["polygon"]) == len(inside["rays"]) + 1

    def test_every_cone_still_carries_one_point_per_ray(self):
        """The invariant the whole fixture format rests on."""
        for entry in self.cones:
            assert len(entry["polygon"]) == len(entry["rays"]) + 1, entry["why"]

    def test_the_untouched_cones_prove_the_default_path_did_not_move(self):
        """
        `cones` predates occluders and is regenerated with an empty list.

        If adding the argument had changed the arithmetic of a cone with no
        smokes in it, these six would have moved and the whole port would need
        re-checking.
        """
        assert len(self.doc["cones"]) == 6
