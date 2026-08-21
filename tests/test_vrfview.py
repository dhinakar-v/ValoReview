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

import ast
import json
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

import pytest

import valcatalog
from vrfview import art as art_mod
from vrfview import theme
from vrfview.clock import PlaybackClock
from vrfview.infer import annotate, two_colour
from vrfview.layout import compute
from vrfview.model import (
    TEAM_A,
    TEAM_B,
    TEAM_UNKNOWN,
    WIN_DEFUSE,
    WIN_UNDETERMINED,
    WIN_WIPE,
    Kill,
    Loadout,
    Player,
    Replay,
    Round,
    SpikeEvent,
    Ultimate,
)
from vrfview.names import resolve
from vrfview.state import state_at

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "Demos" / "039f3991-5472-4119-bed2-838da0935f60.vrf"
JSON = REPO / "out" / "039f3991.json"


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
        [*SETUP_ROUNDS, (2000, end_ms)],
        end_ms,
        ultimates=ultimates,
        spike=spike,
    )


class TestBipartition(unittest.TestCase):
    def test_clean_split_is_exact(self):
        replay = annotate(scenario([]))
        assert {p.actor_id for p in replay.team(TEAM_A)} == {1, 3, 5, 7, 9}
        assert {p.actor_id for p in replay.team(TEAM_B)} == {2, 4, 6, 8, 10}

    def test_team_a_holds_the_lowest_actor_id(self):
        """Naming must be deterministic so colours are stable between runs."""
        replay = annotate(scenario([]))
        lowest = min(p.actor_id for p in replay.players)
        assert replay.player(lowest).team == TEAM_A

    def test_self_kill_does_not_break_the_graph(self):
        replay = annotate(scenario([(50000, 1, 1)]))
        assert len(replay.team(TEAM_A)) == 5
        assert len(replay.team(TEAM_B)) == 5

    def test_odd_cycle_leaves_teams_unknown(self):
        kills = [(100, 1, 2), (200, 2, 3), (300, 3, 1)]
        replay = annotate(build(kills, [(0, 5000)], 5000))
        assert all(p.team == TEAM_UNKNOWN for p in replay.players)
        assert any("not bipartite" in n for n in replay.notes)

    def test_two_colour_reports_non_bipartite(self):
        adj = {1: {2, 3}, 2: {1, 3}, 3: {1, 2}}
        _, ok = two_colour(adj)
        assert not ok

    def test_disconnected_components_are_each_coloured(self):
        kills = [(100, 1, 2), (200, 3, 4)]
        replay = annotate(build(kills, [(0, 5000)], 5000))
        assert all(p.known_team for p in replay.players)
        assert any("components" in n for n in replay.notes)

    def test_no_kills_leaves_teams_unknown(self):
        replay = Replay(source="s", length_ms=1000)
        replay.rounds = [Round(number=1, index=0, start_ms=0, end_ms=1000)]
        annotate(replay)
        assert replay.players == []


class TestReconnectMerge(unittest.TestCase):
    # A sixth actor on team A.  Four of the five originals stay active into
    # the late round, so only actor 9 -- whose last kill is at 1250 ms -- has
    # a span disjoint from the newcomer's.  That is what makes the pairing
    # unique, and it mirrors the real capture, where nine actors span the
    # whole match and only the one that dropped out does not.
    LATE: ClassVar[list[tuple[int, int, int]]] = [
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
        assert len(replay.team(TEAM_A)) == 5
        assert len(replay.team(TEAM_B)) == 5
        merged = [p for p in replay.players if p.merged_from]
        assert len(merged) == 1
        assert merged[0].actor_id == 9
        assert 11 in merged[0].merged_from
        assert any("reconnect" in n for n in replay.notes)

    def test_overlapping_spans_are_not_merged(self):
        """An actor active throughout cannot be someone else rejoining."""
        replay = annotate(self._lopsided(extra=[(350, 2, 11)]))
        assert len(replay.players) == 11
        assert any("none was applied" in n for n in replay.notes)

    def test_merge_rewrites_kills_to_the_kept_actor(self):
        replay = annotate(self._lopsided())
        ids = {p.actor_id for p in replay.players}
        for kill in replay.kills:
            assert kill.killer in ids
            assert kill.victim in ids


class TestRounds(unittest.TestCase):
    def test_windows_are_contiguous_and_half_open(self):
        replay = build(establish(), [(0, 1000), (1000, 2500)], 2500)
        first, second = replay.rounds
        assert first.end_ms == second.start_ms
        assert first.contains(999)
        assert not first.contains(1000)
        assert second.contains(1000)

    def test_wipe_names_the_surviving_team(self):
        """Round 1 of the fixture kills all five of team B."""
        replay = annotate(scenario([]))
        assert replay.rounds[0].reason == WIN_WIPE
        assert replay.rounds[0].winner == TEAM_A

    def test_wipe_needs_five_distinct_victims(self):
        """A repeated victim must not count twice toward the wipe threshold."""
        kills = [
            (50000, 1, 2),
            (50100, 3, 4),
            (50200, 5, 6),
            (50300, 7, 8),
            (50400, 9, 8),
        ]
        replay = annotate(scenario(kills))
        assert replay.rounds[2].reason == WIN_UNDETERMINED

    def test_defuse_records_reason_but_not_a_winner(self):
        """Spike events carry no actor id, so the side is not recoverable."""
        replay = annotate(
            scenario(
                [(50000, 1, 2), (50100, 3, 4)],
                spike=[(49000, "planted"), (50200, "defused")],
            ),
        )
        assert replay.rounds[2].reason == WIN_DEFUSE
        assert replay.rounds[2].winner == TEAM_UNKNOWN

    def test_no_terminal_condition_is_undetermined(self):
        replay = annotate(scenario([(50000, 1, 2), (50100, 3, 4)]))
        assert replay.rounds[2].reason == WIN_UNDETERMINED
        assert not replay.rounds[2].decided

    def test_earlier_terminal_condition_wins(self):
        """A wipe before a defuse decides the round; the defuse does not undo it."""
        kills = [
            (50000, 2, 1),
            (50100, 4, 3),
            (50200, 6, 5),
            (50300, 8, 7),
            (50400, 10, 9),
        ]
        replay = annotate(scenario(kills, spike=[(50500, "defused")]))
        assert replay.rounds[2].reason == WIN_WIPE
        assert replay.rounds[2].winner == TEAM_B


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.replay = annotate(
            build(
                establish(),
                [(0, 1000), (1000, 3000)],
                3000,
                ultimates=[(1300, 1)],
                spike=[(1500, "planted")],
            ),
        )

    def test_everyone_alive_at_zero(self):
        snap = state_at(self.replay, 0)
        assert len(snap.alive) == 10

    def test_victim_is_dead_at_the_exact_kill_time(self):
        kill = self.replay.kills[0]
        snap = state_at(self.replay, kill.t_ms)
        assert not snap.is_alive(kill.victim)

    def test_victim_alive_one_ms_before(self):
        kill = self.replay.kills[0]
        if kill.t_ms > 0:
            snap = state_at(self.replay, kill.t_ms - 1)
            assert snap.is_alive(kill.victim)

    def test_round_boundary_revives_everyone(self):
        end_of_first = state_at(self.replay, 999)
        start_of_second = state_at(self.replay, 1000)
        assert len(end_of_first.alive) < 10
        assert len(start_of_second.alive) == 10

    def test_kill_arrow_age_runs_zero_to_one(self):
        kill = self.replay.kills[0]
        at_kill = state_at(self.replay, kill.t_ms)
        ages = [age for k, age in at_kill.recent_kills if k.t_ms == kill.t_ms]
        assert ages == [0.0]
        later = state_at(self.replay, kill.t_ms + 2500)
        assert not any(k.t_ms == kill.t_ms for k, _ in later.recent_kills)

    def test_spike_state_is_scoped_to_the_round(self):
        assert state_at(self.replay, 1600).spike_state == "planted"
        assert state_at(self.replay, 500).spike_state == "none"

    def test_suicide_is_a_death_but_not_a_kill(self):
        """Actor 1 kills actor 2, then kills itself."""
        replay = annotate(scenario([(50000, 1, 1)]))
        final = state_at(replay, 60000)
        assert final.kills_of(1) == 1
        assert final.deaths_of(1) == 1

    def test_kd_accumulates_across_rounds(self):
        replay = annotate(scenario([]))
        after_first = state_at(replay, 999)
        after_second = state_at(replay, 1999)
        assert after_first.kills_of(2) == 0
        assert after_second.kills_of(2) == 1
        assert sum(d for _, d in after_first.kd.values()) == 5
        assert sum(d for _, d in after_second.kd.values()) == 9

    def test_seeking_backwards_matches_seeking_forwards(self):
        """The snapshot is stateless, so order of access cannot matter."""
        forward = [state_at(self.replay, t) for t in range(0, 3000, 250)]
        backward = [state_at(self.replay, t) for t in range(2750, -1, -250)]
        for snap in forward:
            twin = next(s for s in backward if s.t_ms == snap.t_ms)
            assert snap == twin

    def test_clamps_outside_the_match(self):
        assert state_at(self.replay, -5000).t_ms == 0
        assert state_at(self.replay, 10**9).t_ms == self.replay.length_ms

    def test_score_is_not_revealed_before_the_round_ends(self):
        """Round 1 is decided at 300 ms but must not show until it ends."""
        replay = annotate(scenario([]))
        assert state_at(replay, 900).score == (0, 0)
        assert state_at(replay, 1000).score == (1, 0)


class TestClock(unittest.TestCase):
    def test_paused_clock_does_not_advance(self):
        clock = PlaybackClock(10000)
        assert clock.tick(100.0) == 0.0
        assert clock.t_ms == 0

    def test_speed_scales_the_delta(self):
        clock = PlaybackClock(10000, speed=4.0)
        clock.play()
        clock.tick(100.0)
        assert clock.t_ms == 400

    def test_clamps_and_auto_pauses_at_the_end(self):
        clock = PlaybackClock(500)
        clock.play()
        clock.tick(10000.0)
        assert clock.t_ms == 500
        assert not clock.playing

    def test_seek_clamps_both_ends(self):
        clock = PlaybackClock(500)
        clock.seek(-10)
        assert clock.t_ms == 0
        clock.seek(9999)
        assert clock.t_ms == 500

    def test_many_small_ticks_do_not_drift(self):
        clock = PlaybackClock(10**6)
        clock.play()
        for _ in range(10000):
            clock.tick(0.1)
        assert clock.t_ms == 1000


class TestLayoutAndTheme(unittest.TestCase):
    def setUp(self):
        self.replay = annotate(scenario([]))

    def test_every_player_is_placed_inside_the_canvas(self):
        lay = compute(self.replay, 1200, 800)
        assert len(lay.positions) == 10
        for x, y in lay.positions.values():
            assert 0 <= x <= 1200
            assert 0 <= y <= 800

    def test_nodes_do_not_overlap(self):
        lay = compute(self.replay, 1200, 800)
        points = list(lay.positions.values())
        for i, (x1, y1) in enumerate(points):
            for x2, y2 in points[i + 1 :]:
                gap = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
                assert gap > lay.radius * 2

    def test_teams_sit_on_opposite_sides(self):
        lay = compute(self.replay, 1200, 800)
        mid = lay.centre[0]
        for p in self.replay.team(TEAM_A):
            assert lay.of(p.actor_id)[0] < mid
        for p in self.replay.team(TEAM_B):
            assert lay.of(p.actor_id)[0] > mid

    def test_layout_is_deterministic(self):
        assert (
            compute(self.replay, 900, 700).positions
            == compute(self.replay, 900, 700).positions
        )

    def test_blend_hits_both_endpoints(self):
        assert theme.blend("#ffffff", "#000000", 0.0) == "#ffffff"
        assert theme.blend("#ffffff", "#000000", 1.0) == "#000000"
        assert theme.blend("#ffffff", "#000000", 0.5) == "#808080"

    def test_ramp_is_ordered_and_bounded(self):
        table = theme.ramp("#ffffff", "#000000", 8)
        assert len(table) == 8
        assert theme.ramp_at(table, 0.0) == "#ffffff"
        assert theme.ramp_at(table, 1.0) == "#000000"
        assert theme.ramp_at(table, 5.0) == "#000000"


CATALOG = valcatalog.Catalog(
    maps={"/Game/Maps/Infinity/Infinity": "Abyss"},
    agents={"41fb69c1-4189-7b37-f117-bcaf1e96f1bf": "Astra"},
    version="release-13.04",
    source=valcatalog.SOURCE_CONTENT,
)

ASTRA = "41FB69C1-4189-7B37-F117-BCAF1E96F1BF"
UNKNOWN_AGENT = "00000000-0000-0000-0000-000000000000"


def with_roster(character_ids, map_path="/Game/Maps/Infinity/Infinity"):
    """A loaded-but-unresolved replay carrying a roster and a map path."""
    replay = annotate(scenario([]))
    replay.map_path = map_path
    replay.map_name = "Infinity"
    replay.map_name_source = "built-in codename table"
    replay.loadouts = [
        Loadout(index=i, subject=f"subject-{i}", character_id=c)
        for i, c in enumerate(character_ids)
    ]
    return replay


class TestNames(unittest.TestCase):
    """The catalogue join: external knowledge, applied and always attributed."""

    def test_map_name_comes_from_the_catalogue_and_says_so(self):
        replay = resolve(with_roster([]), CATALOG)
        assert replay.map_name == "Abyss"
        assert valcatalog.SOURCE_CONTENT in replay.map_name_source
        assert any("asset path" in n for n in replay.catalog_notes)

    def test_agent_uuids_resolve_across_a_case_difference(self):
        replay = resolve(with_roster([ASTRA]), CATALOG)
        assert replay.roster == ["Astra"]
        assert any("1/1 agent UUIDs resolved" in n for n in replay.catalog_notes)

    def test_an_unknown_uuid_stays_unresolved_and_is_named(self):
        replay = resolve(with_roster([ASTRA, UNKNOWN_AGENT]), CATALOG)
        assert replay.roster == ["Astra"]
        assert replay.loadouts[1].display.startswith("unresolved")
        assert any(UNKNOWN_AGENT in n for n in replay.catalog_notes)

    def test_an_unknown_map_path_keeps_the_built_in_name(self):
        replay = resolve(with_roster([], "/Game/Maps/Newest/Newest"), CATALOG)
        assert replay.map_name == "Infinity"
        assert any("is in no catalogue entry" in n for n in replay.catalog_notes)

    def test_no_catalogue_leaves_everything_as_read(self):
        replay = resolve(with_roster([ASTRA]), None)
        assert replay.map_name == "Infinity"
        assert replay.roster == []
        assert "--no-catalog" in replay.catalog_source

    def test_an_empty_catalogue_says_where_to_get_one(self):
        replay = resolve(with_roster([ASTRA]), valcatalog.Catalog())
        assert replay.roster == []
        assert any("catalog" in n for n in replay.catalog_notes)

    def test_the_roster_is_never_attached_to_a_player(self):
        """
        No field links a loadout to an actor net id, so none may claim to.

        A player may now carry an agent, but only one its own pawn stated.
        Here the roster names Astra and no pawn stated anything, so every
        player must come back with no agent at all.
        """
        replay = resolve(with_roster([ASTRA]), CATALOG)
        assert replay.roster == ["Astra"]
        assert [p.agent for p in replay.players] == [""] * len(replay.players)
        assert any(
            "not attributable to actor net IDs" in n for n in replay.catalog_notes
        )

    def test_subjects_still_read_through_the_loadouts(self):
        replay = with_roster([ASTRA, UNKNOWN_AGENT])
        assert replay.subjects == ["subject-0", "subject-1"]


# A manifest in the shape fetch_assets.py writes, cut down to what art.py
# joins on.  Ascent's four transform scalars are the real ones, because the
# axis-swap test below checks against pixels measured off the real image.
MANIFEST = {
    "version": {"branch": "release-13.04", "version": "13.04.00.5304478"},
    "maps": {
        "Ascent": {
            "uuid": "7eaecc1b-4337-bbf6-6ab9-04b8f06b3319",
            "codename": "Ascent",
            "map_url": "/Game/Maps/Ascent/Ascent",
            "asset_path": "ShooterGame/Content/Maps/Ascent/Ascent_PrimaryAsset",
            "transform": {
                "x_multiplier": 7e-05,
                "y_multiplier": -7e-05,
                "x_scalar_to_add": 0.813895,
                "y_scalar_to_add": 0.573242,
            },
            "files": {
                "minimap.png": "maps/Ascent/minimap.png",
                "listview.png": "maps/Ascent/listview.png",
            },
            "callouts": [
                {
                    "regionName": "Site",
                    "superRegionName": "A",
                    "location": {"x": 6153.585, "y": -6626.2114, "z": 499.999},
                },
                {"regionName": "Broken", "superRegionName": "", "location": {}},
            ],
        },
        "Summit": {
            "uuid": "e0b26e08-4dcb-a55b-ec53-b0862a0f8f2e",
            "codename": None,
            "map_url": "/Game/Maps/Rig/Rig",
            "transform": {},
            "files": {},
            "callouts": [],
        },
    },
    "agents": {
        "KAY/O": {
            "uuid": "601dbbe7-43ce-be57-2a40-4abd24953621",
            "role": "Initiator",
            "files": {"icon.png": "agents/KAY_O/icon.png"},
        },
        "Jett": {
            "uuid": "add6443a-41bd-e414-f6ad-e58d267f4e95",
            "role": "Duelist",
            "files": {},
        },
    },
    "roles": {"Initiator": {"file": "roles/Initiator.png"}},
}

# The five callouts docs/valorant-assets.md measured against the real image.
ASCENT_A_SITE_PX = (358, 146)


class TestArt(unittest.TestCase):
    """Path resolution and the coordinate transform, on a fake cache."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _write(self, doc=None, files=()):
        """A manifest plus whichever PNGs are meant to exist on disk."""
        (self.root / "manifest.json").write_text(
            json.dumps(MANIFEST if doc is None else doc),
            encoding="utf-8",
        )
        for name in files:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_png_bytes(1024, 1024))
        return art_mod.load(self.root)

    def test_a_map_resolves_by_map_url(self):
        cache = self._write(files=["maps/Ascent/minimap.png"])
        entry = cache.map_art("/Game/Maps/Ascent/Ascent")
        assert entry is not None
        assert entry.name == "Ascent"
        assert entry.minimap == self.root / "maps/Ascent/minimap.png"

    def test_the_asset_path_is_deliberately_not_the_join_key(self):
        """valcatalog measured this; art.py must not quietly widen it."""
        cache = self._write()
        path = "ShooterGame/Content/Maps/Ascent/Ascent_PrimaryAsset"
        assert cache.map_art(path) is None

    def test_a_map_falls_back_to_the_codename_leaf(self):
        cache = self._write()
        assert cache.map_art("/Game/Maps/Other/Ascent").name == "Ascent"

    def test_a_null_codename_never_matches_a_leaf(self):
        """Summit has codename null; an empty codename must not match ''."""
        cache = self._write()
        assert cache.map_art("/Game/Maps/Nowhere/") is None

    def test_an_agent_resolves_across_a_case_difference(self):
        cache = self._write(files=["agents/KAY_O/icon.png"])
        entry = cache.agent_art("601DBBE7-43CE-BE57-2A40-4ABD24953621")
        assert entry is not None
        assert entry.name == "KAY/O"

    def test_the_sanitised_folder_is_read_and_never_built(self):
        """KAY/O lives in agents/KAY_O/; the path comes out of `files`."""
        cache = self._write(files=["agents/KAY_O/icon.png"])
        entry = cache.agent_art("601dbbe7-43ce-be57-2a40-4abd24953621")
        assert entry.icon == self.root / "agents/KAY_O/icon.png"
        assert "KAY/O" not in str(entry.icon)

    def test_a_role_badge_comes_from_the_roles_table(self):
        cache = self._write(files=["agents/KAY_O/icon.png", "roles/Initiator.png"])
        entry = cache.agent_art("601dbbe7-43ce-be57-2a40-4abd24953621")
        assert entry.role == "Initiator"
        assert entry.role_icon == self.root / "roles/Initiator.png"

    def test_a_manifest_entry_whose_file_is_absent_resolves_to_none(self):
        """A half-fetched cache degrades to text, not to a broken image."""
        cache = self._write()
        entry = cache.agent_art("601dbbe7-43ce-be57-2a40-4abd24953621")
        assert entry is not None
        assert entry.icon is None

    def test_an_agent_with_no_files_still_resolves_its_name(self):
        cache = self._write()
        entry = cache.agent_art("add6443a-41bd-e414-f6ad-e58d267f4e95")
        assert entry.name == "Jett"
        assert entry.icon is None

    def test_a_missing_cache_is_empty_and_raises_nothing(self):
        cache = art_mod.load(self.root / "nowhere")
        assert cache.empty
        assert "nowhere" in cache.reason
        assert cache.map_art("/Game/Maps/Ascent/Ascent") is None

    def test_unreadable_json_is_empty_and_raises_nothing(self):
        (self.root / "manifest.json").write_text("{not json", encoding="utf-8")
        cache = art_mod.load(self.root)
        assert cache.empty
        assert "readable JSON" in cache.reason

    def test_the_transform_swaps_x_and_y(self):
        """
        The measured form, not the obvious one.

        docs/valorant-assets.md: the unswapped reading puts 200 of 346 callouts
        inside the image and this one puts 346 of 346.  Neither crashes, which
        is exactly why it needs pinning.
        """
        cache = self._write()
        entry = cache.map_art("/Game/Maps/Ascent/Ascent")
        (callout,) = entry.callouts
        assert callout.name == "A Site"

        x, y = entry.to_pixels(callout, 1024, 1024)
        assert (round(x), round(y)) == ASCENT_A_SITE_PX

        t = entry.transform
        unswapped_u = callout.world_x * t.x_multiplier + t.x_scalar_to_add
        assert round(unswapped_u * 1024) != ASCENT_A_SITE_PX[0]

    def test_a_callout_with_no_location_is_dropped(self):
        cache = self._write()
        entry = cache.map_art("/Game/Maps/Ascent/Ascent")
        assert [c.name for c in entry.callouts] == ["A Site"]

    def test_a_map_with_no_transform_is_not_plottable(self):
        """Riot ships the deathmatch arenas with null scalars."""
        cache = self._write()
        assert not cache.map_art("/Game/Maps/Rig/Rig").plottable

    def test_png_size_reads_the_ihdr(self):
        path = self.root / "probe.png"
        path.write_bytes(_png_bytes(456, 100))
        assert art_mod.png_size(path) == (456, 100)

    def test_png_size_rejects_a_file_that_is_not_a_png(self):
        path = self.root / "not.png"
        path.write_bytes(b"GIF89a" + b"\0" * 32)
        with pytest.raises(ValueError, match="is not a PNG"):
            art_mod.png_size(path)

    def test_subsample_never_upscales_and_never_returns_zero(self):
        assert art_mod.subsample_for((1024, 1024), 64) == 16
        assert art_mod.subsample_for((512, 512), 64) == 8
        assert art_mod.subsample_for((256, 128), 128) == 2
        assert art_mod.subsample_for((456, 100), 456) == 1
        # Smaller than the target: Tk rejects 0, and there is no upscaling.
        assert art_mod.subsample_for((32, 32), 64) == 1
        assert art_mod.subsample_for((0, 0), 64) == 1

    def test_coverage_reports_an_empty_cache_in_one_line(self):
        lines = art_mod.coverage(art_mod.ArtCache(), "/Game/Maps/Ascent/Ascent", [])
        assert len(lines) == 1
        assert "fetch-assets" in lines[0]

    def test_coverage_counts_the_slots_that_resolved(self):
        cache = self._write(files=["agents/KAY_O/icon.png"])
        lines = art_mod.coverage(
            cache,
            "/Game/Maps/Ascent/Ascent",
            [
                "601dbbe7-43ce-be57-2a40-4abd24953621",
                "add6443a-41bd-e414-f6ad-e58d267f4e95",
            ],
        )
        assert any("1/2 loadout slots" in line for line in lines)


class TestRealArtCache(unittest.TestCase):
    """
    The cache on this machine, when there is one.

    assets/ is gitignored and may be present but partial, so this skips at
    runtime rather than by decorator -- the same idiom the catalogue tests use.
    """

    def setUp(self):
        self.cache = art_mod.load()
        if self.cache.empty:
            raise unittest.SkipTest("no art cache fetched")

    def test_every_ascent_callout_lands_inside_the_image(self):
        """346/346 was the measurement; per-map it must be all of them."""
        entry = self.cache.map_art("/Game/Maps/Ascent/Ascent")
        if entry is None or not entry.callouts:
            raise unittest.SkipTest("Ascent not in the cache")
        for callout in entry.callouts:
            x, y = entry.to_pixels(callout, 1024, 1024)
            assert 0 <= x <= 1024, callout.name
            assert 0 <= y <= 1024, callout.name

    def test_the_documented_ascent_pixels_still_hold(self):
        entry = self.cache.map_art("/Game/Maps/Ascent/Ascent")
        if entry is None:
            raise unittest.SkipTest("Ascent not in the cache")
        found = {c.name: entry.to_pixels(c, 1024, 1024) for c in entry.callouts}
        if "A Site" not in found:
            raise unittest.SkipTest("callout set changed upstream")
        x, y = found["A Site"]
        assert (round(x), round(y)) == ASCENT_A_SITE_PX

    def test_a_cached_icon_subsamples_to_the_roster_tile_size(self):
        entry = self.cache.agent_art("add6443a-41bd-e414-f6ad-e58d267f4e95")
        if entry is None or entry.icon is None:
            raise unittest.SkipTest("Jett icon not fetched")
        size = art_mod.png_size(entry.icon)
        factor = art_mod.subsample_for(size, 64)
        assert max(size) // factor <= 64


def _png_bytes(width: int, height: int) -> bytes:
    """
    The first 24 bytes of a PNG: signature, IHDR length and type, w, h.

    art.png_size reads no further, so the rest of a real file would be waste.
    """
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


class TestHeadless(unittest.TestCase):
    """The model must stay usable with no display and no Tk build.

    Read statically rather than by importing in a subprocess: a source walk
    also catches an import that hides behind a function body or a branch, and
    it follows first-party imports so a model module cannot reach tkinter
    through a sibling either.
    """

    MODEL_MODULES = (
        "model",
        "infer",
        "loader",
        "names",
        "state",
        "layout",
        "clock",
        "theme",
        # art resolves file paths and coordinates, never pixels; keeping it on
        # this list is what lets `dump` report art coverage with no Tk present.
        "art",
    )

    @staticmethod
    def _imported_modules(module: str) -> set[str]:
        """Every module name `vrfview.<module>` imports, however deeply nested."""
        source = REPO / "libraries" / "vrfview" / f"{module}.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
                names.update(f"{node.module}.{a.name}" for a in node.names)
        return names

    def test_model_layers_never_import_tkinter(self):
        pending = list(self.MODEL_MODULES)
        walked: set[str] = set()
        while pending:
            module = pending.pop()
            if module in walked:
                continue
            walked.add(module)
            for name in self._imported_modules(module):
                assert name.split(".")[0] != "tkinter", (
                    f"vrfview.{module} imports {name}"
                )
                if name.startswith("vrfview.") and name.count(".") == 1:
                    pending.append(name.split(".", 1)[1])
        assert walked >= set(self.MODEL_MODULES)


@unittest.skipUnless(JSON.exists(), "reference JSON not present")
class TestReferenceCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from vrfview.loader import load

        cls.replay = annotate(load(JSON))

    def test_the_match_id_is_read_from_the_header(self):
        """The container names its own match; the filename merely agrees."""
        assert self.replay.match_id == "039f3991-5472-4119-bed2-838da0935f60"

    def test_the_roster_is_ten_agent_uuids(self):
        assert len(self.replay.loadouts) == 10
        assert all(x.character_id for x in self.replay.loadouts)
        assert len(self.replay.subjects) == 10

    def test_the_roster_resolves_to_the_verified_multiset(self):
        """The exact composition val-content-v1 confirmed on 2026-08-21."""
        expected = [
            "Astra",
            "Killjoy",
            "Waylay",
            "Sova",
            "Reyna",
            "Sova",
            "Reyna",
            "Brimstone",
            "Chamber",
            "Raze",
        ]
        from vrfview.loader import load

        catalog = valcatalog.load()
        if catalog.empty:
            raise unittest.SkipTest("no content catalogue cached")
        # A fresh load: resolve mutates, and the shared replay is read as
        # unresolved by the .vrf/JSON comparison below.
        assert resolve(annotate(load(JSON)), catalog).roster == expected

    def test_counts_match_the_capture(self):
        assert len(self.replay.rounds) == 15
        assert len(self.replay.players) == 10
        assert len(self.replay.kills) == 108
        assert len(self.replay.ultimates) == 9
        assert self.replay.length_ms == 1571721
        assert self.replay.side_swap_ms == 1235236

    def test_teams_match_the_verified_split(self):
        assert {p.actor_id for p in self.replay.team(TEAM_A)} == {
            546,
            852,
            958,
            1258,
            1362,
        }
        assert {p.actor_id for p in self.replay.team(TEAM_B)} == {
            646,
            744,
            1058,
            1160,
            1462,
        }

    def test_no_same_team_kills(self):
        for kill in self.replay.kills:
            if kill.is_suicide:
                continue
            assert (
                self.replay.player(kill.killer).team
                != self.replay.player(kill.victim).team
            )

    def test_killer_victim_order_is_not_reversed(self):
        """No player may die twice in one round -- the ordering regression."""
        for rnd in self.replay.rounds:
            victims = [k.victim for k in self.replay.kills if rnd.contains(k.t_ms)]
            assert len(victims) == len(
                set(victims),
            ), f"round {rnd.number} has a repeat victim"

    def test_outcome_breakdown_matches_the_measurement(self):
        reasons = [r.reason for r in self.replay.rounds]
        assert reasons.count(WIN_WIPE) == 11
        assert reasons.count(WIN_UNDETERMINED) == 2
        assert self.replay.score == (9, 2)

    @unittest.skipUnless(DEMO.exists(), "reference .vrf not present")
    def test_vrf_and_json_agree(self):
        """The two input paths must produce the same model."""
        from vrfview.loader import load

        from_vrf = annotate(load(DEMO))
        assert from_vrf.kills == self.replay.kills
        assert from_vrf.rounds == self.replay.rounds
        assert from_vrf.players == self.replay.players
        assert from_vrf.length_ms == self.replay.length_ms
        assert from_vrf.match_id == self.replay.match_id
        assert from_vrf.loadouts == self.replay.loadouts

    @unittest.skipUnless(DEMO.exists(), "reference .vrf not present")
    def test_vrf_loads_without_oodle(self):
        """The viewer reads uncompressed chunks only, so no DLL is required."""
        import vrf_reader
        from vrfview.loader import load

        original = vrf_reader.Oodle.discover

        def refuse(*_a, **_k):
            raise AssertionError("Oodle must not be needed to view a replay")

        vrf_reader.Oodle.discover = staticmethod(refuse)
        try:
            assert len(load(DEMO).kills) == 108
        finally:
            vrf_reader.Oodle.discover = original


if __name__ == "__main__":
    unittest.main()
