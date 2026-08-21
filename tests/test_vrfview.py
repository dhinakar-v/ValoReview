"""
Tests for the replay viewer's model, inference, snapshot and geometry layers.

Everything here runs headlessly: no .vrf, no display, no third-party package.
The few tests that do want the reference capture are skipped when it is absent,
because Demos/ and out/ are gitignored and a clean checkout has neither.

The regression that matters most is test_killer_victim_order_is_not_reversed.
The characterDeath argument order was documented backwards, and the symptom was
not a crash but a quietly impossible match: players dying twice in one round and
scoring kills after their own death.  That test pins the corrected reading.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from vrfview import theme  # noqa: E402
from vrfview.clock import PlaybackClock  # noqa: E402
from vrfview.infer import annotate, two_colour  # noqa: E402
from vrfview.layout import compute  # noqa: E402
from vrfview.model import (  # noqa: E402
    TEAM_A,
    TEAM_B,
    TEAM_UNKNOWN,
    WIN_DEFUSE,
    WIN_UNDETERMINED,
    WIN_WIPE,
    Kill,
    Player,
    Replay,
    Round,
    SpikeEvent,
    Ultimate,
)
from vrfview.state import state_at  # noqa: E402

DEMO = os.path.join(REPO, "Demos", "039f3991-5472-4119-bed2-838da0935f60.vrf")
JSON = os.path.join(REPO, "out", "039f3991.json")


def build(kills, rounds, length_ms, ultimates=(), spike=()):
    """A Replay shaped the way loader.load leaves one, ready for annotate."""
    replay = Replay(source="synthetic", length_ms=length_ms)
    replay.kills = [Kill(t, k, v) for t, k, v in kills]
    replay.ultimates = [Ultimate(t, a) for t, a in ultimates]
    replay.spike = [SpikeEvent(t, kind) for t, kind in spike]
    actors = {k.killer for k in replay.kills} | {k.victim for k in replay.kills}
    actors |= {u.actor_id for u in replay.ultimates}
    replay.players = [Player(actor_id=a) for a in sorted(actors)]
    replay.rounds = [
        Round(number=i + 1, index=i, start_ms=s, end_ms=e)
        for i, (s, e) in enumerate(rounds)
    ]
    return replay


TEAM_ODD = [1, 3, 5, 7, 9]
TEAM_EVEN = [2, 4, 6, 8, 10]

# Two setup rounds whose kills form a connected path 1-2-3-...-10.  Connected
# matters: a kill graph in five separate two-actor components has many equally
# valid global splits, so the component-join heuristic would decide the fixture
# rather than the code under test.  A real match is one component.
SETUP_ROUNDS = [(0, 1000), (1000, 2000)]


def establish():
    """Kills that pin all ten actors into one bipartite component."""
    first = [(100 + 50 * i, TEAM_ODD[i], TEAM_EVEN[i]) for i in range(5)]
    second = [(1100 + 50 * i, TEAM_EVEN[i], TEAM_ODD[i + 1]) for i in range(4)]
    return first + second


def scenario(kills, spike=(), ultimates=(), end_ms=60000):
    """A replay with the setup rounds plus one round holding the scenario."""
    return build(
        establish() + list(kills),
        SETUP_ROUNDS + [(2000, end_ms)],
        end_ms,
        ultimates=ultimates,
        spike=spike,
    )


class TestBipartition(unittest.TestCase):
    def test_clean_split_is_exact(self):
        replay = annotate(scenario([]))
        self.assertEqual({p.actor_id for p in replay.team(TEAM_A)}, {1, 3, 5, 7, 9})
        self.assertEqual({p.actor_id for p in replay.team(TEAM_B)}, {2, 4, 6, 8, 10})

    def test_team_a_holds_the_lowest_actor_id(self):
        """Naming must be deterministic so colours are stable between runs."""
        replay = annotate(scenario([]))
        lowest = min(p.actor_id for p in replay.players)
        self.assertEqual(replay.player(lowest).team, TEAM_A)

    def test_self_kill_does_not_break_the_graph(self):
        replay = annotate(scenario([(50000, 1, 1)]))
        self.assertEqual(len(replay.team(TEAM_A)), 5)
        self.assertEqual(len(replay.team(TEAM_B)), 5)

    def test_odd_cycle_leaves_teams_unknown(self):
        kills = [(100, 1, 2), (200, 2, 3), (300, 3, 1)]
        replay = annotate(build(kills, [(0, 5000)], 5000))
        self.assertTrue(all(p.team == TEAM_UNKNOWN for p in replay.players))
        self.assertTrue(any("not bipartite" in n for n in replay.notes))

    def test_two_colour_reports_non_bipartite(self):
        adj = {1: {2, 3}, 2: {1, 3}, 3: {1, 2}}
        _, ok = two_colour(adj)
        self.assertFalse(ok)

    def test_disconnected_components_are_each_coloured(self):
        kills = [(100, 1, 2), (200, 3, 4)]
        replay = annotate(build(kills, [(0, 5000)], 5000))
        self.assertTrue(all(p.known_team for p in replay.players))
        self.assertTrue(any("components" in n for n in replay.notes))

    def test_no_kills_leaves_teams_unknown(self):
        replay = Replay(source="s", length_ms=1000)
        replay.rounds = [Round(number=1, index=0, start_ms=0, end_ms=1000)]
        annotate(replay)
        self.assertEqual(replay.players, [])


class TestReconnectMerge(unittest.TestCase):
    # A sixth actor on team A.  Four of the five originals stay active into
    # the late round, so only actor 9 -- whose last kill is at 1250 ms -- has
    # a span disjoint from the newcomer's.  That is what makes the pairing
    # unique, and it mirrors the real capture, where nine actors span the
    # whole match and only the one that dropped out does not.
    LATE = [
        (50000, 11, 2),
        (50200, 1, 6),
        (50250, 3, 8),
        (50300, 5, 4),
        (50350, 7, 10),
    ]

    def _lopsided(self, extra=()):
        return scenario(list(self.LATE) + list(extra))

    def test_disjoint_spans_merge(self):
        replay = annotate(self._lopsided())
        self.assertEqual(len(replay.team(TEAM_A)), 5)
        self.assertEqual(len(replay.team(TEAM_B)), 5)
        merged = [p for p in replay.players if p.merged_from]
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].actor_id, 9)
        self.assertIn(11, merged[0].merged_from)
        self.assertTrue(any("reconnect" in n for n in replay.notes))

    def test_overlapping_spans_are_not_merged(self):
        """An actor active throughout cannot be someone else rejoining."""
        replay = annotate(self._lopsided(extra=[(350, 2, 11)]))
        self.assertEqual(len(replay.players), 11)
        self.assertTrue(any("none was applied" in n for n in replay.notes))

    def test_merge_rewrites_kills_to_the_kept_actor(self):
        replay = annotate(self._lopsided())
        ids = {p.actor_id for p in replay.players}
        for kill in replay.kills:
            self.assertIn(kill.killer, ids)
            self.assertIn(kill.victim, ids)


class TestRounds(unittest.TestCase):
    def test_windows_are_contiguous_and_half_open(self):
        replay = build(establish(), [(0, 1000), (1000, 2500)], 2500)
        first, second = replay.rounds
        self.assertEqual(first.end_ms, second.start_ms)
        self.assertTrue(first.contains(999))
        self.assertFalse(first.contains(1000))
        self.assertTrue(second.contains(1000))

    def test_wipe_names_the_surviving_team(self):
        """Round 1 of the fixture kills all five of team B."""
        replay = annotate(scenario([]))
        self.assertEqual(replay.rounds[0].reason, WIN_WIPE)
        self.assertEqual(replay.rounds[0].winner, TEAM_A)

    def test_wipe_needs_five_distinct_victims(self):
        """A repeated victim must not count twice toward the wipe threshold."""
        kills = [
            (50000, 1, 2), (50100, 3, 4), (50200, 5, 6),
            (50300, 7, 8), (50400, 9, 8),
        ]
        replay = annotate(scenario(kills))
        self.assertEqual(replay.rounds[2].reason, WIN_UNDETERMINED)

    def test_defuse_records_reason_but_not_a_winner(self):
        """Spike events carry no actor id, so the side is not recoverable."""
        replay = annotate(
            scenario(
                [(50000, 1, 2), (50100, 3, 4)],
                spike=[(49000, "planted"), (50200, "defused")],
            )
        )
        self.assertEqual(replay.rounds[2].reason, WIN_DEFUSE)
        self.assertEqual(replay.rounds[2].winner, TEAM_UNKNOWN)

    def test_no_terminal_condition_is_undetermined(self):
        replay = annotate(scenario([(50000, 1, 2), (50100, 3, 4)]))
        self.assertEqual(replay.rounds[2].reason, WIN_UNDETERMINED)
        self.assertFalse(replay.rounds[2].decided)

    def test_earlier_terminal_condition_wins(self):
        """A wipe before a defuse decides the round; the defuse does not undo it."""
        kills = [
            (50000, 2, 1), (50100, 4, 3), (50200, 6, 5),
            (50300, 8, 7), (50400, 10, 9),
        ]
        replay = annotate(scenario(kills, spike=[(50500, "defused")]))
        self.assertEqual(replay.rounds[2].reason, WIN_WIPE)
        self.assertEqual(replay.rounds[2].winner, TEAM_B)


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.replay = annotate(
            build(
                establish(),
                [(0, 1000), (1000, 3000)],
                3000,
                ultimates=[(1300, 1)],
                spike=[(1500, "planted")],
            )
        )

    def test_everyone_alive_at_zero(self):
        snap = state_at(self.replay, 0)
        self.assertEqual(len(snap.alive), 10)

    def test_victim_is_dead_at_the_exact_kill_time(self):
        kill = self.replay.kills[0]
        snap = state_at(self.replay, kill.t_ms)
        self.assertFalse(snap.is_alive(kill.victim))

    def test_victim_alive_one_ms_before(self):
        kill = self.replay.kills[0]
        if kill.t_ms > 0:
            snap = state_at(self.replay, kill.t_ms - 1)
            self.assertTrue(snap.is_alive(kill.victim))

    def test_round_boundary_revives_everyone(self):
        end_of_first = state_at(self.replay, 999)
        start_of_second = state_at(self.replay, 1000)
        self.assertLess(len(end_of_first.alive), 10)
        self.assertEqual(len(start_of_second.alive), 10)

    def test_kill_arrow_age_runs_zero_to_one(self):
        kill = self.replay.kills[0]
        at_kill = state_at(self.replay, kill.t_ms)
        ages = [age for k, age in at_kill.recent_kills if k.t_ms == kill.t_ms]
        self.assertEqual(ages, [0.0])
        later = state_at(self.replay, kill.t_ms + 2500)
        self.assertFalse(
            any(k.t_ms == kill.t_ms for k, _ in later.recent_kills)
        )

    def test_spike_state_is_scoped_to_the_round(self):
        self.assertEqual(state_at(self.replay, 1600).spike_state, "planted")
        self.assertEqual(state_at(self.replay, 500).spike_state, "none")

    def test_suicide_is_a_death_but_not_a_kill(self):
        """Actor 1 kills actor 2, then kills itself."""
        replay = annotate(scenario([(50000, 1, 1)]))
        final = state_at(replay, 60000)
        self.assertEqual(final.kills_of(1), 1)
        self.assertEqual(final.deaths_of(1), 1)

    def test_kd_accumulates_across_rounds(self):
        replay = annotate(scenario([]))
        after_first = state_at(replay, 999)
        after_second = state_at(replay, 1999)
        self.assertEqual(after_first.kills_of(2), 0)
        self.assertEqual(after_second.kills_of(2), 1)
        self.assertEqual(sum(d for _, d in after_first.kd.values()), 5)
        self.assertEqual(sum(d for _, d in after_second.kd.values()), 9)

    def test_seeking_backwards_matches_seeking_forwards(self):
        """The snapshot is stateless, so order of access cannot matter."""
        forward = [state_at(self.replay, t) for t in range(0, 3000, 250)]
        backward = [state_at(self.replay, t) for t in range(2750, -1, -250)]
        for snap in forward:
            twin = next(s for s in backward if s.t_ms == snap.t_ms)
            self.assertEqual(snap, twin)

    def test_clamps_outside_the_match(self):
        self.assertEqual(state_at(self.replay, -5000).t_ms, 0)
        self.assertEqual(state_at(self.replay, 10**9).t_ms, self.replay.length_ms)

    def test_score_is_not_revealed_before_the_round_ends(self):
        """Round 1 is decided at 300 ms but must not show until it ends."""
        replay = annotate(scenario([]))
        self.assertEqual(state_at(replay, 900).score, (0, 0))
        self.assertEqual(state_at(replay, 1000).score, (1, 0))


class TestClock(unittest.TestCase):
    def test_paused_clock_does_not_advance(self):
        clock = PlaybackClock(10000)
        self.assertEqual(clock.tick(100.0), 0.0)
        self.assertEqual(clock.t_ms, 0)

    def test_speed_scales_the_delta(self):
        clock = PlaybackClock(10000, speed=4.0)
        clock.play()
        clock.tick(100.0)
        self.assertEqual(clock.t_ms, 400)

    def test_clamps_and_auto_pauses_at_the_end(self):
        clock = PlaybackClock(500)
        clock.play()
        clock.tick(10000.0)
        self.assertEqual(clock.t_ms, 500)
        self.assertFalse(clock.playing)

    def test_seek_clamps_both_ends(self):
        clock = PlaybackClock(500)
        clock.seek(-10)
        self.assertEqual(clock.t_ms, 0)
        clock.seek(9999)
        self.assertEqual(clock.t_ms, 500)

    def test_many_small_ticks_do_not_drift(self):
        clock = PlaybackClock(10**6)
        clock.play()
        for _ in range(10000):
            clock.tick(0.1)
        self.assertEqual(clock.t_ms, 1000)


class TestLayoutAndTheme(unittest.TestCase):
    def setUp(self):
        self.replay = annotate(scenario([]))

    def test_every_player_is_placed_inside_the_canvas(self):
        lay = compute(self.replay, 1200, 800)
        self.assertEqual(len(lay.positions), 10)
        for x, y in lay.positions.values():
            self.assertTrue(0 <= x <= 1200 and 0 <= y <= 800)

    def test_nodes_do_not_overlap(self):
        lay = compute(self.replay, 1200, 800)
        points = list(lay.positions.values())
        for i, (x1, y1) in enumerate(points):
            for x2, y2 in points[i + 1:]:
                gap = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
                self.assertGreater(gap, lay.radius * 2)

    def test_teams_sit_on_opposite_sides(self):
        lay = compute(self.replay, 1200, 800)
        mid = lay.centre[0]
        for p in self.replay.team(TEAM_A):
            self.assertLess(lay.of(p.actor_id)[0], mid)
        for p in self.replay.team(TEAM_B):
            self.assertGreater(lay.of(p.actor_id)[0], mid)

    def test_layout_is_deterministic(self):
        self.assertEqual(
            compute(self.replay, 900, 700).positions,
            compute(self.replay, 900, 700).positions,
        )

    def test_blend_hits_both_endpoints(self):
        self.assertEqual(theme.blend("#ffffff", "#000000", 0.0), "#ffffff")
        self.assertEqual(theme.blend("#ffffff", "#000000", 1.0), "#000000")
        self.assertEqual(theme.blend("#ffffff", "#000000", 0.5), "#808080")

    def test_ramp_is_ordered_and_bounded(self):
        table = theme.ramp("#ffffff", "#000000", 8)
        self.assertEqual(len(table), 8)
        self.assertEqual(theme.ramp_at(table, 0.0), "#ffffff")
        self.assertEqual(theme.ramp_at(table, 1.0), "#000000")
        self.assertEqual(theme.ramp_at(table, 5.0), "#000000")


class TestHeadless(unittest.TestCase):
    def test_model_layers_never_import_tkinter(self):
        """The model must stay usable with no display and no Tk build."""
        code = (
            "import sys;"
            "import vrfview.model, vrfview.infer, vrfview.loader,"
            " vrfview.state, vrfview.layout, vrfview.clock, vrfview.theme;"
            "sys.exit(1 if 'tkinter' in sys.modules else 0)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())


@unittest.skipUnless(os.path.exists(JSON), "reference JSON not present")
class TestReferenceCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from vrfview.loader import load

        cls.replay = annotate(load(JSON))

    def test_counts_match_the_capture(self):
        self.assertEqual(len(self.replay.rounds), 15)
        self.assertEqual(len(self.replay.players), 10)
        self.assertEqual(len(self.replay.kills), 108)
        self.assertEqual(len(self.replay.ultimates), 9)
        self.assertEqual(self.replay.length_ms, 1571721)
        self.assertEqual(self.replay.side_swap_ms, 1235236)

    def test_teams_match_the_verified_split(self):
        self.assertEqual(
            {p.actor_id for p in self.replay.team(TEAM_A)},
            {546, 852, 958, 1258, 1362},
        )
        self.assertEqual(
            {p.actor_id for p in self.replay.team(TEAM_B)},
            {646, 744, 1058, 1160, 1462},
        )

    def test_no_same_team_kills(self):
        for kill in self.replay.kills:
            if kill.is_suicide:
                continue
            self.assertNotEqual(
                self.replay.player(kill.killer).team,
                self.replay.player(kill.victim).team,
            )

    def test_killer_victim_order_is_not_reversed(self):
        """No player may die twice in one round -- the ordering regression."""
        for rnd in self.replay.rounds:
            victims = [k.victim for k in self.replay.kills if rnd.contains(k.t_ms)]
            self.assertEqual(
                len(victims), len(set(victims)),
                f"round {rnd.number} has a repeat victim",
            )

    def test_outcome_breakdown_matches_the_measurement(self):
        reasons = [r.reason for r in self.replay.rounds]
        self.assertEqual(reasons.count(WIN_WIPE), 11)
        self.assertEqual(reasons.count(WIN_UNDETERMINED), 2)
        self.assertEqual(self.replay.score, (9, 2))

    @unittest.skipUnless(os.path.exists(DEMO), "reference .vrf not present")
    def test_vrf_and_json_agree(self):
        """The two input paths must produce the same model."""
        from vrfview.loader import load

        from_vrf = annotate(load(DEMO))
        self.assertEqual(from_vrf.kills, self.replay.kills)
        self.assertEqual(from_vrf.rounds, self.replay.rounds)
        self.assertEqual(from_vrf.players, self.replay.players)
        self.assertEqual(from_vrf.length_ms, self.replay.length_ms)

    @unittest.skipUnless(os.path.exists(DEMO), "reference .vrf not present")
    def test_vrf_loads_without_oodle(self):
        """The viewer reads uncompressed chunks only, so no DLL is required."""
        import vrf_reader
        from vrfview.loader import load

        original = vrf_reader.Oodle.discover

        def refuse(*_a, **_k):
            raise AssertionError("Oodle must not be needed to view a replay")

        vrf_reader.Oodle.discover = staticmethod(refuse)
        try:
            self.assertEqual(len(load(DEMO).kills), 108)
        finally:
            vrf_reader.Oodle.discover = original


if __name__ == "__main__":
    unittest.main()
