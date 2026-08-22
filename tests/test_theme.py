"""
The palette has one home, and the stylesheet is generated from it.

`libraries/vrfview/theme.py` decides the colours; `scripts/make_theme.py`
writes them out as custom properties.  The generated file is committed so a
checkout builds without running the generator, which means it can go stale --
this is the test that says so.

It matters more than a duplicated hex string usually would.  The palette
carries an argument: the brief names its red ATK and its blue DEF, and this
project does not adopt those meanings, because which team attacked is not
recoverable from a replay.  That reasoning lives beside the constants, and a
hand-copied stylesheet would leave the values in one place and the reason in
another.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import make_theme
from vrfview import theme

REPO = Path(__file__).resolve().parents[1]
GENERATED = REPO / "web" / "src" / "theme.generated.css"


class Generated(unittest.TestCase):
    def test_the_committed_stylesheet_is_current(self):
        assert GENERATED.is_file(), f"{GENERATED} is missing"
        current = GENERATED.read_text(encoding="utf-8")
        assert current == make_theme.render(), (
            "web/src/theme.generated.css is out of date; run runners\\make-theme.bat"
        )

    def test_every_listed_colour_exists_in_the_palette(self):
        for name, _ in make_theme.COLOURS:
            assert hasattr(theme, name), f"theme.{name} is gone"

    def test_it_writes_a_property_for_each_colour(self):
        css = make_theme.render()
        for name, prop in make_theme.COLOURS:
            assert f"{prop}: {getattr(theme, name)};" in css

    def test_the_two_teams_are_written_as_a_and_b(self):
        """
        Never as attacker and defender.

        Spike events carry no actor ID, so which side planted is unrecoverable.
        The hues are the brief's; the meaning is what the data supports.
        """
        css = make_theme.render()
        assert f"--team-a: {theme.TEAM_COLOURS['A']};" in css
        assert f"--team-b: {theme.TEAM_COLOURS['B']};" in css
        assert "atk" not in css.lower()
        assert "--team-def" not in css.lower()

    def test_the_reason_travels_with_the_values(self):
        css = make_theme.render()
        assert "not recoverable" in css

    def test_check_agrees_with_the_committed_file(self):
        assert make_theme.main(["--check"]) == 0
