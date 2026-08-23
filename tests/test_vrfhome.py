"""
Tests for the match-list scanner.

Everything here except the two capture-backed cases runs on synthetic cards:
sorting, filtering, paging and the cache are arithmetic over a list, and
pinning them against a real library would make the suite depend on which
replays happen to sit in Demos/.

That `scan` reaches for no widget set is asserted in `tests/test_layering.py`
now, over the whole of `libraries/` rather than over this one module.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import vrfcache
from vrfhome import scan

DEMO_12_10 = Path("Demos/03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf")
DEMO_11_11 = Path("Demos/039f3991-5472-4119-bed2-838da0935f60.vrf")

BUILD_SUPPORTED = "++Ares-Core+release-12.10"
BUILD_UNSUPPORTED = "++Ares-Core+release-11.11"

START = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def card(
    name: str,
    day: int = 0,
    map_name: str = "Haven",
    build: str = BUILD_SUPPORTED,
    error: str = "",
) -> scan.MatchCard:
    return (
        scan.MatchCard(
            path=Path(f"Demos/{name}.vrf"),
            match_id=name,
            map_path=f"/Game/Maps/Codename/{map_name}",
            map_name=map_name,
            recorded_utc=START + timedelta(days=day),
            length_ms=125_000,
            rounds=24,
            players=10,
            build=build,
        )
        if not error
        else scan.MatchCard(path=Path(f"Demos/{name}.vrf"), error=error)
    )


class CardFacts(unittest.TestCase):
    def test_a_card_carries_the_instant_and_the_length_not_a_rendering(self):
        """
        A scan describes a capture; it does not decide how a date is written.

        There were `duration` and `recorded` properties here that formatted
        these two into strings for a card to print.  Removing them is what
        stopped the match list and the viewer header writing the same instant
        two different ways -- see `web/src/model/format.ts`.
        """
        one = card("a")
        assert one.length_ms == 125_000
        assert one.recorded_utc is not None
        assert not hasattr(one, "duration")
        assert not hasattr(one, "recorded")

    def test_a_dateless_card_says_so_rather_than_showing_an_epoch(self):
        dateless = scan.MatchCard(path=Path("x.vrf"))
        assert dateless.recorded_utc is None

    def test_the_result_badge_is_always_the_refusal(self):
        assert card("a").result == scan.RESULT_NOT_IN_FILE

    def test_positions_follow_the_transform_table_not_a_guess(self):
        assert card("a", build=BUILD_SUPPORTED).positions_available
        assert not card("b", build=BUILD_UNSUPPORTED).positions_available
        assert not card("c", build="").positions_available


class Arranging(unittest.TestCase):
    def setUp(self):
        self.cards = [card("c", day=2), card("a", day=0), card("b", day=1)]

    def test_default_sort_is_oldest_first(self):
        got = [c.match_id for c in scan.sort_cards(self.cards)]
        assert got == ["a", "b", "c"]

    def test_descending_reverses_it(self):
        got = [c.match_id for c in scan.sort_cards(self.cards, descending=True)]
        assert got == ["c", "b", "a"]

    def test_a_dateless_card_sorts_last_in_both_directions(self):
        cards = [*self.cards, scan.MatchCard(path=Path("z.vrf"), match_id="z")]
        for descending in (False, True):
            got = [c.match_id for c in scan.sort_cards(cards, descending=descending)]
            assert got[-1] == "z"

    def test_filter_by_map_is_a_case_insensitive_substring(self):
        cards = [card("a", map_name="Haven"), card("b", map_name="Breeze")]
        got = scan.filter_cards(cards, map_name="hav")
        assert [c.match_id for c in got] == ["a"]

    def test_filter_by_date_matches_a_month_or_a_day(self):
        cards = [card("a", day=0), card("b", day=40)]
        assert len(scan.filter_cards(cards, date="2026-06")) == 1
        assert len(scan.filter_cards(cards, date="2026-06-01")) == 1
        assert len(scan.filter_cards(cards, date="2027")) == 0

    def test_paging_is_seven_a_page_and_clamps(self):
        cards = [card(f"m{i}", day=i) for i in range(12)]
        assert scan.page_count(cards) == 2
        assert len(scan.page(cards, 1)) == scan.PER_PAGE
        assert len(scan.page(cards, 2)) == 12 - scan.PER_PAGE
        # Past the end shows the last page rather than nothing.
        assert scan.page(cards, 99) == scan.page(cards, 2)
        assert scan.page(cards, 0) == scan.page(cards, 1)

    def test_an_empty_library_still_has_one_page(self):
        assert scan.page_count([]) == 1
        assert scan.page([], 1) == []

    def test_maps_present_is_sorted_and_unique(self):
        cards = [card("a", map_name="Split"), card("b", map_name="Bind"), card("c")]
        assert scan.maps_present(cards) == ["Bind", "Haven", "Split"]


class UnreadableFiles(unittest.TestCase):
    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def test_a_non_vrf_becomes_a_card_carrying_its_error(self):
        junk = self.tmp / "junk.vrf"
        junk.write_bytes(b"not a replay at all")
        got = scan.read_card(junk)
        assert not got.readable
        assert got.error
        assert got.result == scan.RESULT_NOT_IN_FILE

    def test_a_missing_file_is_a_card_too(self):
        got = scan.read_card(self.tmp / "gone.vrf")
        assert not got.readable

    def test_the_scan_reports_how_many_failed(self):
        (self.tmp / "junk.vrf").write_bytes(b"nope")
        result = scan.scan(root=str(self.tmp), cache=scan.Cache(path=None))
        assert len(result.cards) == 1
        assert len(result.failed) == 1
        assert "1 unreadable" in result.described

    def test_an_empty_library_says_where_it_looked(self):
        result = scan.scan(root=str(self.tmp), cache=scan.Cache(path=None))
        assert result.cards == []
        assert str(self.tmp) in result.described


class Caching(unittest.TestCase):
    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.file = self.tmp / "junk.vrf"
        self.file.write_bytes(b"nope")
        self.cache_path = self.tmp / "cache.json"

    def tearDown(self):
        self._dir.cleanup()

    def test_a_second_scan_reads_nothing(self):
        first = scan.scan(root=str(self.tmp), cache=scan.Cache(self.cache_path))
        assert (first.read, first.cached) == (1, 0)
        second = scan.scan(root=str(self.tmp), cache=scan.Cache(self.cache_path))
        assert (second.read, second.cached) == (0, 1)
        assert second.cards[0].error == first.cards[0].error

    def test_touching_the_file_invalidates_its_entry(self):
        scan.scan(root=str(self.tmp), cache=scan.Cache(self.cache_path))
        self.file.write_bytes(b"nope, longer this time")
        again = scan.scan(root=str(self.tmp), cache=scan.Cache(self.cache_path))
        assert (again.read, again.cached) == (1, 0)

    def test_a_corrupt_cache_costs_a_rescan_and_nothing_else(self):
        self.cache_path.write_text("{not json", encoding="utf-8")
        result = scan.scan(root=str(self.tmp), cache=scan.Cache(self.cache_path))
        assert len(result.cards) == 1
        assert result.read == 1

    def test_a_cache_of_the_wrong_version_is_ignored(self):
        self.cache_path.write_text('{"version": 0, "entries": {}}', encoding="utf-8")
        cache = scan.Cache(self.cache_path)
        assert cache.entries == {}

    def test_the_default_cache_lives_under_the_projects_dot_cache(self):
        """
        Not `out/`, which was relative to the working directory: running the
        app from anywhere but the repo root addressed a different cache and
        rescanned the whole library.
        """
        found = scan.default_cache_path()
        assert found == vrfcache.root() / scan.CACHE_FILENAME
        assert found.parent.name == vrfcache.CACHE_DIRNAME

    def test_with_no_project_root_the_scan_simply_does_not_cache(self):
        """An installed copy rescans; it does not fail to list the library."""
        with mock.patch.object(vrfcache.envfile, "find_upwards", return_value=None):
            assert scan.default_cache_path() is None
            assert scan.Cache().path is None

    def test_an_explicit_none_still_disables_the_cache(self):
        """`--no-cache` and "resolve the default" must stay distinguishable."""
        assert scan.Cache(path=None).path is None
        assert scan.Cache().path is not None

    def test_no_cache_file_is_written_when_the_path_is_none(self):
        scan.scan(root=str(self.tmp), cache=scan.Cache(path=None))
        assert not self.cache_path.exists()


@unittest.skipUnless(DEMO_12_10.exists(), "needs the 12.10 reference capture")
class AgainstARealCapture(unittest.TestCase):
    def test_a_supported_build_reads_and_offers_positions(self):
        got = scan.read_card(DEMO_12_10)
        assert got.readable
        assert got.map_name == "Haven"
        assert got.build == BUILD_SUPPORTED
        assert got.positions_available
        assert got.rounds > 0
        assert got.players == 10
        assert got.recorded_utc is not None
        assert got.length_ms > 0

    @unittest.skipUnless(DEMO_11_11.exists(), "needs the 11.11 reference capture")
    def test_the_11_11_capture_reads_but_refuses_positions(self):
        got = scan.read_card(DEMO_11_11)
        assert got.readable
        assert got.build == BUILD_UNSUPPORTED
        assert not got.positions_available
        assert "no payload transform" in got.positions_note
        assert not got.playable


def loadout(character_id: str) -> dict:
    """One roster slot as `vrf_reader.players()` reports it."""
    return {"subject": f"player-{character_id}", "characterId": character_id}


def roster(*ids: str) -> list[dict]:
    return [loadout(i) for i in ids]


TEN = tuple("abcdefghij")


class TheTeamSplit(unittest.TestCase):
    """
    The rule behind the two rows of agents on a card.

    `team_ids` claims that the loadout roster's first five slots are one team
    and the last five the other.  Nothing in the metadata says so, so the claim
    rests on the measurement in its docstring -- and on the refusal below,
    which is what keeps it from being applied to a capture that disagrees with
    it.  `LoadoutSplitIsTheRealTeamSplit` re-runs the measurement itself.
    """

    def test_ten_distinct_agents_split_five_and_five(self):
        first, second = scan.team_ids(roster(*TEN))
        assert first == TEN[:5]
        assert second == TEN[5:]

    def test_an_agent_on_both_teams_is_ordinary_and_still_splits(self):
        # The common case by far: 95 of the 103 reference captures carry at
        # least one agent picked by both teams.  It is a duplicate *within* one
        # team that would mean the order is not what this claims.
        first, second = scan.team_ids(
            roster("a", "b", "c", "d", "e", "a", "b", "f", "g", "h"),
        )
        assert first == ("a", "b", "c", "d", "e")
        assert second == ("a", "b", "f", "g", "h")

    def test_a_repeated_agent_inside_one_half_refuses_the_split(self):
        # Two of the same agent on one team is not a thing that happens, so
        # this file's order is not the order this rule assumes. Refuse it
        # rather than draw five portraits of a team that never existed.
        assert scan.team_ids(
            roster("a", "a", "b", "c", "d", "e", "f", "g", "h", "i"),
        ) == ((), ())

    def test_a_roster_that_is_not_ten_is_refused(self):
        assert scan.team_ids(roster("a", "b", "c", "d")) == ((), ())
        assert scan.team_ids(roster(*TEN, "k", "l")) == ((), ())
        assert scan.team_ids([]) == ((), ())

    def test_a_blank_character_id_is_refused_rather_than_drawn_as_a_gap(self):
        assert scan.team_ids(
            roster("a", "b", "c", "d", "", "f", "g", "h", "i", "j"),
        ) == ((), ())


class TheCacheCarriesTheNewFields(unittest.TestCase):
    """
    A card's teams and score survive a round trip, and `None` stays `None`.

    The score is the one that matters: `(0, 0)` is a real answer -- a capture
    where the kill graph two-coloured but nothing was ever attributed -- and
    `None` means the teams are unknown.  A rehydration that collapsed the
    second into the first would print `0 - 0` over a match nobody can score.
    """

    def test_a_full_card_round_trips(self):
        original = scan.MatchCard(
            path=Path("m.vrf"),
            match_id="m-1",
            agent_ids=(TEN[:5], TEN[5:]),
            score=(13, 9),
            rounds_undecided=2,
        )
        back = scan._from_entry(original.path, scan._to_entry(original))
        assert back.agent_ids == original.agent_ids
        assert back.score == (13, 9)
        assert back.rounds_undecided == 2

    def test_an_unscored_card_comes_back_unscored(self):
        original = scan.MatchCard(path=Path("m.vrf"), score=None)
        back = scan._from_entry(original.path, scan._to_entry(original))
        assert back.score is None

    def test_a_zero_score_is_not_confused_with_no_score(self):
        original = scan.MatchCard(path=Path("m.vrf"), score=(0, 0))
        back = scan._from_entry(original.path, scan._to_entry(original))
        assert back.score == (0, 0)

    def test_a_half_written_split_is_refused_rather_than_padded(self):
        entry = scan._to_entry(scan.MatchCard(path=Path("m.vrf")))
        entry["agent_ids"] = [["a", "b"], ["c", "d", "e", "f", "g"]]
        assert scan._from_entry(Path("m.vrf"), entry).agent_ids == ((), ())


class TheTeamOrder(unittest.TestCase):
    """
    Which loadout half is `infer`'s team A, and the refusals around it.

    This is the join that cannot be made from plain chunks, so every path that
    is not a clean, complete, unambiguous match has to end in `""` -- an
    unattributed scoreline costs a card two numbers, and a wrongly attributed
    one is a fabricated result printed beside the right five faces.
    """

    HALVES = (("a", "b", "c", "d", "e"), ("f", "g", "h", "i", "j"))
    # The catalogue names an agent UUID; here a UUID names itself.
    NAMES = staticmethod(lambda uuid: uuid.upper())

    def replay(self, team_a, team_b):
        from vrfview.model import Player, Replay

        found = Replay()
        found.players = [
            *[Player(actor_id=i, team="A", agent=n) for i, n in enumerate(team_a)],
            *[
                Player(actor_id=100 + i, team="B", agent=n)
                for i, n in enumerate(team_b)
            ],
        ]
        return found

    def order(self, replay):
        from vrfhome import teamorder

        return teamorder.first_half_team(replay, self.HALVES, self.NAMES)

    def test_the_first_half_is_named_when_it_is_team_a(self):
        found = self.replay(list("ABCDE"), list("FGHIJ"))
        assert self.order(found) == "A"

    def test_the_first_half_is_named_when_it_is_team_b(self):
        found = self.replay(list("FGHIJ"), list("ABCDE"))
        assert self.order(found) == "B"

    def test_a_disagreement_is_refused_rather_than_resolved(self):
        # One agent in the wrong place is not a near-match to be rounded off:
        # it means the two sources are describing different things.
        found = self.replay(list("ABCDF"), list("EGHIJ"))
        assert self.order(found) == ""

    def test_an_incomplete_decode_is_refused(self):
        found = self.replay(list("ABCD"), list("FGHIJ"))
        assert self.order(found) == ""

    def test_a_capture_with_no_split_is_refused(self):
        from vrfhome import teamorder

        found = self.replay(list("ABCDE"), list("FGHIJ"))
        assert teamorder.first_half_team(found, ((), ()), self.NAMES) == ""

    def test_an_unnamed_uuid_is_refused_rather_than_matched_as_blank(self):
        # Two UUIDs the catalogue cannot name would collapse to one empty
        # string and make a four-agent set look like a five-agent one.
        found = self.replay(list("ABCDE"), list("FGHIJ"))
        from vrfhome import teamorder

        assert teamorder.first_half_team(found, self.HALVES, lambda _u: "") == ""


class TheTeamOrderCache(unittest.TestCase):
    """Letters survive a restart, and anything unreadable is simply absent."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        patched = mock.patch.object(vrfcache, "project_root", return_value=root)
        patched.start()
        self.addCleanup(patched.stop)

    def test_a_recorded_letter_reads_back(self):
        from vrfhome import teamorder

        teamorder.record("m-1", "B")
        assert teamorder.load() == {"m-1": "B"}

    def test_recording_does_not_lose_what_was_already_there(self):
        from vrfhome import teamorder

        teamorder.record("m-1", "A")
        teamorder.record("m-2", "B")
        assert teamorder.load() == {"m-1": "A", "m-2": "B"}

    def test_a_refusal_is_never_written(self):
        from vrfhome import teamorder

        teamorder.record("m-1", "")
        assert teamorder.load() == {}

    def test_a_corrupt_file_reads_as_nothing_known(self):
        from vrfhome import teamorder

        path = teamorder.cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert teamorder.load() == {}

    def test_a_file_from_an_older_version_is_discarded(self):
        import json

        from vrfhome import teamorder

        path = teamorder.cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 0, "entries": {"m-1": "A"}}),
            encoding="utf-8",
        )
        assert teamorder.load() == {}
