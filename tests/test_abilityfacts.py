"""
The looked-up ability table, and the two things that make it safe.

Not a check that the numbers are *right* -- nothing in this repository can
know that, which is the whole reason the drawing built on them is labelled
simulated.  These pin the two properties that would make it unsafe: a figure
with no source, and a lookup that answers where it does not know.
"""

from __future__ import annotations

import unittest
from typing import ClassVar

from vrfview import abilityfacts


class EveryFigureCarriesItsSource(unittest.TestCase):
    def test_no_entry_is_unsourced(self):
        for key, facts in abilityfacts._FACTS.items():
            assert facts.source, f"{key} has no source"
            assert "wiki" in facts.source, f"{key} does not name where it came from"

    def test_a_radius_is_a_real_distance(self):
        for key, facts in abilityfacts._FACTS.items():
            assert facts.radius_uu is not None, f"{key} has no radius"
            # A metre is 100 uu, so anything under a metre or over sixty is a
            # unit slip rather than an ability.
            assert 100.0 <= facts.radius_uu <= 6000.0, f"{key} is {facts.radius_uu} uu"

    def test_charges_are_at_least_one_where_they_are_stated(self):
        for key, facts in abilityfacts._FACTS.items():
            if facts.charges is not None:
                assert facts.charges >= 1, f"{key} has {facts.charges} charges"


class AnUnknownAbilityIsRefusedRatherThanDefaulted(unittest.TestCase):
    """
    The rule the rest of this codebase keeps: no nearest match, no fallback.

    A default radius would put a ring on every ability at a size nobody
    published, which is exactly the plausible-looking wrong answer the ability
    placement work exists to avoid.
    """

    def test_an_unknown_agent_returns_nothing(self):
        assert abilityfacts.facts_for("Nobody", "Cage Trap") is None
        assert abilityfacts.radius_uu("Nobody", "Cage Trap") is None

    def test_an_unknown_ability_on_a_known_agent_returns_nothing(self):
        assert abilityfacts.facts_for("Cypher", "Possessable Camera") is None

    def test_empty_input_returns_nothing_rather_than_raising(self):
        assert abilityfacts.facts_for("", "") is None
        assert abilityfacts.radius_uu("Cypher", "") is None

    def test_a_known_ability_answers(self):
        found = abilityfacts.facts_for("Cypher", "Cage Trap")
        assert found is not None
        assert found.radius_uu == 372.0
        assert found.radius_m == 3.72


class TheConversionIsRiotsOwn(unittest.TestCase):
    def test_a_metre_is_a_hundred_unreal_units(self):
        """
        Anchored on Riot's own patch note rather than on a convention: Sky
        Smoke's radius is published as 4.15 m and its patch note reads
        "Radius increased 410 >>> 415".
        """
        assert abilityfacts.UU_PER_METRE == 100.0


class SmokeTable(unittest.TestCase):
    """
    The second table, and the one thing that can be checked without a browser.

    `_SMOKES` is keyed on (codename, slot) because the internal name splits --
    Clove's smoke arrives as both `Post Death` and `New Smoke` for the same
    ability.  That means the radius is written twice, here and in `_FACTS`, and
    two copies of a number are two chances to change one of them.
    """

    # (codename, slot) -> the (agent, internal name) entry for the same ability.
    SAME_ABILITY: ClassVar[dict] = {
        ("Wraith", "C"): ("Omen", "Smoke"),
        ("Wushu", "C"): ("Jett", "Smoke"),
        ("Rift", "E"): ("Astra", "Transform Rift Smoke World Targeting"),
        ("Mage", "E"): ("Harbor", "World Smoke"),
    }

    def test_a_radius_written_in_both_tables_agrees_with_itself(self):
        for key, twin in self.SAME_ABILITY.items():
            smoke = abilityfacts.smoke_for(*key)
            facts = abilityfacts.facts_for(*twin)
            assert smoke is not None, key
            assert facts is not None, twin
            assert smoke.radius_uu == facts.radius_uu, f"{key} disagrees with {twin}"

    def test_an_agent_the_table_does_not_name_blocks_nothing(self):
        """No default: a made-up smoke is the plausible wrong answer."""
        assert abilityfacts.smoke_for("Iris", "E") is None
        assert abilityfacts.smoke_for("Hunter", "Q") is None

    def test_every_duration_says_it_was_not_verified(self):
        """
        The figures are the weakest in the file and the source strings say so.

        A citation that implies a page somebody opened is worse than an
        admission, because the next reader cannot tell them apart.
        """
        for key, smoke in abilityfacts._SMOKES.items():
            assert "NOT verified" in smoke.source, key
            assert smoke.duration_ms > 0, key

    def test_the_unit_is_the_one_the_module_argues_for(self):
        brimstone = abilityfacts.smoke_for("Sarge", "C")
        assert brimstone is not None
        assert brimstone.radius_m == 4.15
        assert brimstone.duration_s == 19.25
