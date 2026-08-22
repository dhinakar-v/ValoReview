"""
Tests for the provenance account, now that it is structured rather than prose.

The panel is the page that states what is known and how, so a claim that has
stopped being true there is worse than having no panel at all.  It used to say
positions do not exist.

Two things are pinned here and they are different kinds of promise.  The
sections are the contract an interface reads -- headings, labels, which section
a fact is filed under -- and they are what a web page or a CLI actually
consumes.  `describe` is the older promise: the plain-text block the viewer has
always shown, which must keep rendering with its values in one column, because
that alignment is the only thing separating a label from a claim in a
monospaced box.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from vrfview import provenance
from vrfview.model import Loadout, Player, Replay, Round

REPO = Path(__file__).resolve().parents[1]


def _replay() -> Replay:
    replay = Replay(
        source="capture.vrf",
        match_id="m-1",
        map_path="/Game/Maps/Triad/Triad",
        map_name="Haven",
        map_name_source="built-in table",
        length_ms=60_000,
        build="++Ares-Core+release-12.10",
        recorded_utc="2026-08-21T19:04:00Z",
        catalog_source="built-in table",
    )
    replay.rounds = [Round(number=1, index=0, start_ms=0, end_ms=60_000)]
    replay.players = [
        Player(actor_id=1, team="A", label="A1", codename="Hunter", agent="Sova"),
        Player(actor_id=2, team="B", label="B1"),
    ]
    replay.loadouts = [Loadout(index=0, subject="s-1", character_id="c-1")]
    replay.notes = ["teams split by two-colouring the kill graph"]
    replay.catalog_notes = ["the pawn's agent and the loadout's agree"]
    return replay


class Sections(unittest.TestCase):
    def test_every_heading_is_present_and_in_order(self):
        titles = [s.title for s in provenance.sections(_replay()).sections]
        assert titles == [
            provenance.READ,
            provenance.DECODED,
            provenance.CATALOGUE,
            provenance.ART,
            provenance.INFERRED,
            provenance.NOT_IN_FILE,
        ]

    def test_a_read_fact_and_an_inferred_one_are_in_different_sections(self):
        """The distinction the whole module exists for."""
        account = provenance.sections(_replay())
        read = account.section(provenance.READ)
        inferred = account.section(provenance.INFERRED)
        assert any(e.label == "build" for e in read.entries)
        assert any("two-colouring" in e.value for e in inferred.entries)
        assert not any("two-colouring" in e.value for e in read.entries)

    def test_a_looked_up_fact_is_filed_apart_from_a_derived_one(self):
        account = provenance.sections(_replay())
        catalogue = account.section(provenance.CATALOGUE)
        inferred = account.section(provenance.INFERRED)
        assert any("loadout's agree" in e.value for e in catalogue.entries)
        assert not any("loadout's agree" in e.value for e in inferred.entries)

    def test_a_note_is_a_bare_line_and_a_fact_is_labelled(self):
        account = provenance.sections(_replay())
        notes = account.section(provenance.INFERRED).entries
        assert all(e.bare for e in notes)
        assert not any(e.bare for e in account.section(provenance.READ).entries)

    def test_the_absent_section_does_not_depend_on_the_replay(self):
        """
        Every entry there is a fact about the format, not about a capture.

        A replay that happened to resolve nothing would otherwise read exactly
        like one whose format never carried the thing.
        """
        bare = provenance.sections(Replay()).section(provenance.NOT_IN_FILE)
        full = provenance.sections(_replay()).section(provenance.NOT_IN_FILE)
        assert bare.entries == full.entries == provenance.ABSENT

    def test_the_map_reference_promise_is_stated(self):
        art = provenance.sections(_replay()).section(provenance.ART)
        assert any("never players" in e.value for e in art.entries)

    def test_an_unknown_heading_is_none_rather_than_an_empty_section(self):
        assert provenance.sections(_replay()).section("NO SUCH THING") is None


class Claims(unittest.TestCase):
    def test_it_reports_the_position_source_verbatim(self):
        replay = _replay()
        replay.position_source = "12.10: 199,180 positions for 10 player actors"
        assert replay.position_source in provenance.describe(replay)

    def test_it_says_which_actors_stated_their_own_agent(self):
        text = provenance.describe(_replay())
        assert "1 of 2 actors state their own agent" in text
        assert "Sova" in text

    def test_an_undecoded_replay_says_so_without_claiming_positions_are_absent(self):
        text = provenance.describe(_replay())
        assert "not requested" in text
        # The line this panel used to carry, and which the decode falsified.
        assert "the 2D scene is schematic, not a map" not in text

    def test_the_three_absent_numbers_are_named(self):
        text = provenance.describe(_replay())
        assert "health, armour, credits" in text
        assert "player names / Riot IDs" in text

    def test_an_ability_free_replay_does_not_imply_the_match_had_none(self):
        text = provenance.describe(_replay())
        assert "no ability actor was read" in text


class PlainText(unittest.TestCase):
    """The rendering, which a monospaced box depends on."""

    def test_values_line_up_in_one_column(self):
        section = provenance.sections(_replay()).section(provenance.READ)
        column = provenance.INDENT + provenance.LABEL_WIDTH
        for entry, line in zip(section.entries, section.lines[1:], strict=True):
            assert line.startswith(f"{' ' * provenance.INDENT}{entry.label}")
            assert line[column:] == entry.value.splitlines()[0]

    def test_a_continuation_sits_under_its_value_not_its_label(self):
        section = provenance.sections(Replay()).section(provenance.NOT_IN_FILE)
        wrapped = [line for line in section.lines if line.startswith(" " * 10)]
        indent = provenance.INDENT + provenance.ABSENT_LABEL_WIDTH
        assert all(len(line) - len(line.lstrip()) == indent for line in wrapped)

    def test_sections_are_separated_by_a_blank_line(self):
        text = provenance.describe(_replay())
        assert f"\n\n{provenance.INFERRED}" in text


class Headless(unittest.TestCase):
    """
    The account is data about the model, so it must not need a toolkit.

    `pipeline` gets the same check for a different reason: it opens files and
    reaches the decoder, so it is not a model-layer module, but it is the one
    thing a server has to call and it must not drag a window in behind it.
    """

    MODULES = ("provenance", "pipeline")

    def test_neither_reaches_a_toolkit(self):
        for module in self.MODULES:
            source = REPO / "libraries" / "vrfview" / f"{module}.py"
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    root = name.split(".")[0]
                    assert root not in {"tkinter", "customtkinter"}, (
                        f"vrfview.{module} imports {name}"
                    )
