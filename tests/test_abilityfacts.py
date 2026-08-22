"""
The looked-up ability table, and the two things that make it safe.

Not a check that the numbers are *right* -- nothing in this repository can
know that, which is the whole reason the drawing built on them is labelled
simulated.  These pin the two properties that would make it unsafe: a figure
with no source, and a lookup that answers where it does not know.
"""

from __future__ import annotations

import unittest

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
