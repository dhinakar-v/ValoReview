"""
Tests for the match-list scanner.

Everything here except the two capture-backed cases runs on synthetic cards:
sorting, filtering, paging and the cache are arithmetic over a list, and
pinning them against a real library would make the suite depend on which
replays happen to sit in Demos/.

`vrfhome.scan` must stay importable with no display, which is what the import
test asserts -- the page that draws these cards imports customtkinter, and if
that ever leaked into the scanner the whole suite would need a screen.
"""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

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
    return scan.MatchCard(
        path=Path(f"Demos/{name}.vrf"),
        match_id=name,
        map_path=f"/Game/Maps/Codename/{map_name}",
        map_name=map_name,
        recorded_utc=START + timedelta(days=day),
        length_ms=125_000,
        rounds=24,
        players=10,
        build=build,
    ) if not error else scan.MatchCard(path=Path(f"Demos/{name}.vrf"), error=error)


class CardFacts(unittest.TestCase):
    def test_duration_is_mm_ss(self):
        assert card("a").duration == "02:05"

    def test_a_dateless_card_says_so_rather_than_showing_an_epoch(self):
        dateless = scan.MatchCard(path=Path("x.vrf"))
        assert dateless.recorded == "date not in file"

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

    def test_paging_is_ten_a_page_and_clamps(self):
        cards = [card(f"m{i}", day=i) for i in range(25)]
        assert scan.page_count(cards) == 3
        assert len(scan.page(cards, 1)) == 10
        assert len(scan.page(cards, 3)) == 5
        # Past the end shows the last page rather than nothing.
        assert scan.page(cards, 99) == scan.page(cards, 3)
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

    def test_no_cache_file_is_written_when_the_path_is_none(self):
        scan.scan(root=str(self.tmp), cache=scan.Cache(path=None))
        assert not self.cache_path.exists()


class HeadlessImport(unittest.TestCase):
    def test_the_scanner_pulls_in_no_toolkit(self):
        """
        The page imports customtkinter; the scanner must not.

        Asserted against sys.modules after importing scan on its own, because
        an accidental `from vrfhome.cards import ...` inside scan.py would be
        invisible until the first machine with no display ran the suite.
        """
        assert "vrfhome.scan" in sys.modules
        assert "vrfhome.cards" not in sys.modules
        source = Path("libraries/vrfhome/scan.py").read_text(encoding="utf-8")
        for forbidden in ("import tkinter", "import customtkinter", "from PIL"):
            assert forbidden not in source


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
        assert got.duration.count(":") == 1

    @unittest.skipUnless(DEMO_11_11.exists(), "needs the 11.11 reference capture")
    def test_the_11_11_capture_reads_but_refuses_positions(self):
        got = scan.read_card(DEMO_11_11)
        assert got.readable
        assert got.build == BUILD_UNSUPPORTED
        assert not got.positions_available
        assert "schematic" in got.positions_note
