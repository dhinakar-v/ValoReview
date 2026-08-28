"""
The looked-up ability table, and the things that make it safe.

Not a check that the numbers are *right* -- nothing in this repository can
know that, which is the whole reason the drawing built on them is labelled
simulated.  These pin the properties that would make the table unsafe: a
figure with no source, a figure whose unit has slipped, a lookup that answers
where it does not know, and -- the one that only a real decode can catch -- a
key that will never match anything the file states.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import ClassVar

from vrfview import abilities, abilityfacts

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "positions"

# Where a figure in this table is allowed to have come from.
#
# An allow-list of hosts rather than the substring "wiki" the earlier version
# of this file checked for.  That check passed for the wrong reason and would
# have failed for the right one: `liquipedia.net/valorant/Sage` carries Sage's
# and Cypher's figures and contains no "wiki" anywhere, so the old assertion
# would have pushed an author into writing "Liquipedia Wiki" into a URL to get
# past it.  Naming the hosts says what is actually meant.
SOURCE_HOSTS = (
    "valorant.fandom.com",
    "liquipedia.net",
    # The Weird Gloop wiki, which is the one that is actually reachable and is
    # also the better source: it tags each row of its stats tables with how the
    # value was established, so a figure taken from it can say whether it came
    # out of the game files, out of a patch note, or out of somebody's testing.
    "wiki.playvalorant.com",
    "Riot patch note",
    "docs/Valorant Agent Ability Details.md",
)

# Every figure, with the band a real one falls in.  A band is a unit check
# rather than a correctness check: 100 uu is a metre, so a radius under one
# metre or over sixty is a slipped unit and not a rebalance.
BANDS: dict[str, tuple[float, float]] = {
    "radius_uu": (100.0, 6000.0),
    "detection_radius_uu": (100.0, 6000.0),
    # Killjoy's Lockdown counts down for thirteen seconds and is the ceiling.
    "windup_ms": (100.0, 15_000.0),
    "activation_delay_ms": (100.0, 5_000.0),
    # Sage's Barrier stands for forty seconds and is the ceiling.
    "duration_ms": (100.0, 60_000.0),
    "cooldown_ms": (1_000.0, 120_000.0),
    "charges": (1.0, 10.0),
    "deployable_hp": (1.0, 500.0),
}


def figures(facts: abilityfacts.AbilityMechanics):
    """Every figure on one record, with the field it was written in."""
    for field in BANDS:
        found = getattr(facts, field)
        if found is not None:
            yield field, found


class EveryFigureCarriesItsSource(unittest.TestCase):
    """
    One source per figure, not one per ability.

    A citation covering a row of ten numbers stands behind numbers it never
    backed, and the next reader cannot tell which ones.
    """

    def test_every_figure_names_where_it_came_from(self):
        for key, facts in abilityfacts._MECHANICS.items():
            for field, figure in figures(facts):
                assert figure.source, f"{key}.{field} has no source"
                assert any(host in figure.source for host in SOURCE_HOSTS), (
                    f"{key}.{field} names no known source: {figure.source}"
                )

    def test_every_figure_is_inside_its_own_band(self):
        for key, facts in abilityfacts._MECHANICS.items():
            for field, figure in figures(facts):
                low, high = BANDS[field]
                assert low <= figure.value <= high, (
                    f"{key}.{field} is {figure.value}, outside {low}..{high}"
                )

    def test_every_entry_names_the_ability_and_the_key_the_game_binds(self):
        for key, facts in abilityfacts._MECHANICS.items():
            assert facts.ability, f"{key} has no published name"
            assert facts.keybind in {"C", "Q", "E", "X"}, f"{key} binds {facts.keybind}"


class TheSlotIsNotTheKeybind(unittest.TestCase):
    """
    The one mistake this table exists to prevent.

    The research the figures come from is written in the keys the *game*
    binds.  The archetype path states Riot's own internal letter, and the two
    disagree.  If they always agreed the distinction would be harmless; these
    are the cases proving they do not, so an author who "simplifies" the table
    by dropping `keybind` and reusing the slot fails here.
    """

    SHUFFLED: ClassVar[dict] = {
        ("Hunter", "C"): ("Shock Bolt", "Q"),
        ("Hunter", "Q"): ("Recon Bolt", "E"),
        ("Hunter", "E"): ("Owl Drone", "C"),
        ("Sarge", "C"): ("Sky Smoke", "E"),
        ("Sarge", "E"): ("Stim Beacon", "C"),
        ("Wraith", "C"): ("Dark Cover", "E"),
        ("Wraith", "E"): ("Shrouded Step", "C"),
        ("Clay", "C"): ("Paint Shells", "E"),
        ("Clay", "E"): ("Boom Bot", "C"),
        ("Thorne", "C"): ("Slow Orb", "Q"),
        ("Thorne", "E"): ("Barrier Orb", "C"),
        ("Phoenix", "C"): ("Hot Hands", "E"),
        ("Gumshoe", "C"): ("Cyber Cage", "Q"),
        ("Gumshoe", "E"): ("Trapwire", "C"),
    }

    def test_the_internal_slot_and_the_bound_key_really_do_differ(self):
        for (codename, slot), (ability, keybind) in self.SHUFFLED.items():
            found = abilityfacts.mechanics_for(codename, slot)
            assert found is not None, (codename, slot)
            assert found.ability == ability, f"{codename} {slot} is {found.ability}"
            assert found.keybind == keybind
            assert found.keybind != slot, (
                f"{codename} {slot} is bound to {keybind}; if this ever passes "
                "trivially the shuffle has stopped being a real hazard"
            )


class AnUnknownAbilityIsRefusedRatherThanDefaulted(unittest.TestCase):
    """
    The rule the rest of this codebase keeps: no nearest match, no fallback.

    A default radius would put a ring on every ability at a size nobody
    published, which is exactly the plausible-looking wrong answer the ability
    placement work exists to avoid.
    """

    def test_an_unknown_codename_returns_nothing(self):
        assert abilityfacts.mechanics_for("Nobody", "C") is None

    def test_an_unknown_slot_on_a_known_agent_returns_nothing(self):
        # Astra has no `Passive` entry, and a passive is not an ability.
        assert abilityfacts.mechanics_for("Rift", "Passive") is None

    def test_empty_input_returns_nothing_rather_than_raising(self):
        assert abilityfacts.mechanics_for("", "") is None
        assert abilityfacts.mechanics_for("Rift", "") is None
        assert abilityfacts.smoke_for("", "") is None

    def test_a_known_ability_answers(self):
        found = abilityfacts.mechanics_for("Gumshoe", "C")
        assert found is not None
        assert found.ability == "Cyber Cage"
        assert found.radius_uu is not None
        assert found.radius_uu.value == 372.0

    def test_viper_is_absent_on_purpose(self):
        """
        Not an oversight: the reference library holds no Viper cast at all, so
        nothing says which internal slot letter each of her abilities occupies
        -- and `TheSlotIsNotTheKeybind` above is why that cannot be inferred
        from the key the game binds.
        """
        for slot in ("C", "Q", "E", "X"):
            assert abilityfacts.mechanics_for("Pandemic", slot) is None


class TheConversionIsRiotsOwn(unittest.TestCase):
    def test_a_metre_is_a_hundred_unreal_units(self):
        """
        Anchored on Riot's own patch note rather than on a convention: Sky
        Smoke's radius is published as 4.15 m and its patch note reads
        "Radius increased 410 >>> 415".
        """
        assert abilityfacts.UU_PER_METRE == 100.0

    def test_the_unit_is_the_one_the_module_argues_for(self):
        brimstone = abilityfacts.smoke_for("Sarge", "C")
        assert brimstone is not None
        assert brimstone.radius_m == 4.15
        assert brimstone.duration_s == 19.25


class WhatOccludesSight(unittest.TestCase):
    """
    `smoke_for` is a reading over the table rather than a second table.

    It used to be one: `_SMOKES` carried its own copy of each radius, and the
    test here was that the two copies agreed with each other.  One table
    cannot disagree with itself, so that check is gone rather than weakened.
    """

    ROUND_SMOKES: ClassVar[set] = {
        ("Sarge", "C"),
        ("Wraith", "C"),
        ("Wushu", "C"),
        ("Rift", "E"),
        ("Mage", "E"),
        # Clove's Ruse, and it is here because a source arrived rather than
        # because the rule softened.  It was the largest gap in this table --
        # 365 casts, the most-used ability in the library, occluding nothing --
        # and it was refused for as long as its radius was unpublished.
        ("Smonk", "E"),
    }

    def test_exactly_the_round_smokes_occlude(self):
        found = {key for key in abilityfacts._MECHANICS if abilityfacts.smoke_for(*key)}
        assert found == self.ROUND_SMOKES

    def test_a_smoke_takes_its_radius_and_life_from_the_one_record(self):
        for key in self.ROUND_SMOKES:
            smoke = abilityfacts.smoke_for(*key)
            facts = abilityfacts.mechanics_for(*key)
            assert smoke is not None
            assert facts is not None
            assert facts.radius_uu is not None
            assert facts.duration_ms is not None
            assert smoke.radius_uu == facts.radius_uu.value
            assert smoke.duration_ms == int(facts.duration_ms.value)
            # Both halves of the answer name their own page.
            assert facts.radius_uu.source in smoke.source
            assert facts.duration_ms.source in smoke.source

    def test_a_smoke_with_no_published_radius_occludes_nothing(self):
        """
        Half a smoke is not a smoke, and this is what keeps that true.

        It used to be Clove's Ruse: a round smoke whose duration was published
        and whose radius was not, refused outright rather than drawn at a
        made-up width.  A source arrived -- the Weird Gloop wiki gives 4.0 m
        tagged *Game files* -- so it occludes now, and the refusal moves to the
        next ability in the same position rather than being retired with it.

        Miks' Waveform is that ability: 187 casts, visibly a smoke, and no
        published radius or duration anywhere.  It deliberately does not even
        set `blocks_sight`, because a flag standing over two missing figures
        reads as a smoke that failed to draw rather than as one nobody
        measured.
        """
        facts = abilityfacts.mechanics_for("Iris", "E")
        assert facts is not None
        assert facts.radius_uu is None
        assert facts.duration_ms is None
        assert abilityfacts.smoke_for("Iris", "E") is None

    def test_a_smoke_occludes_only_once_both_halves_are_published(self):
        """The rule itself, independent of which ability is currently short."""
        for key, facts in abilityfacts._MECHANICS.items():
            if abilityfacts.smoke_for(*key) is not None:
                assert facts.radius_uu is not None, key
                assert facts.duration_ms is not None, key

    def test_a_wall_is_never_an_occluder(self):
        """A wall is a line, and a circle drawn for one would block behind the
        caster and leave the far ends of the wall open.

        Unchanged by the wall geometry landing.  A wall is now *drawn* -- from
        its own segment coordinates where it has them, and along the caster's
        facing where it does not -- and none of that makes it a circle, which
        is the only shape `sight.Occluder` has in either language.
        """
        for key in (("Thorne", "E"), ("Phoenix", "Q"), ("Mage", "Q"), ("Nox", "Q")):
            facts = abilityfacts.mechanics_for(*key)
            assert facts is not None
            assert facts.blocks_sight is False, f"{key} is a wall"
            assert abilityfacts.smoke_for(*key) is None

    def test_an_ability_with_no_figures_blocks_nothing(self):
        """No default: a made-up smoke is the plausible wrong answer."""
        # A slot with an ability nobody publishes numbers for, and one that is
        # not a smoke at all.
        assert abilityfacts.smoke_for("Iris", "C") is None
        assert abilityfacts.smoke_for("Hunter", "Q") is None


class TwoFiguresThisResearchCorrected(unittest.TestCase):
    """
    The table that came before this one carried two durations that the
    research file contradicts.  Pinned so a later edit that quietly restores
    either has to argue with a test rather than with nobody.
    """

    def test_astras_nebula_lasts_fourteen_and_a_quarter_seconds(self):
        smoke = abilityfacts.smoke_for("Rift", "E")
        assert smoke is not None
        assert smoke.duration_ms == 14_250, "was 15,000 before the research file"

    def test_jetts_cloudburst_lasts_two_and_a_half_seconds(self):
        smoke = abilityfacts.smoke_for("Wushu", "C")
        assert smoke is not None
        assert smoke.duration_ms == 2_500, "was 4,500 before the research file"

    def test_where_the_research_contradicts_itself_the_entry_says_so(self):
        """
        Clove's Ruse is 14.25 s in the research file's summary table and 14.0 s
        in its own Clove section.  A silent pick between two figures is the
        failure this project names; the source string carries the disagreement.
        """
        facts = abilityfacts.mechanics_for("Smonk", "E")
        assert facts is not None
        assert facts.duration_ms is not None
        assert facts.duration_ms.value == 14_000.0
        assert "14.25" in facts.duration_ms.source


class EveryKeyIsOneTheDecodeProduces(unittest.TestCase):
    """
    The only check that can catch a key which will never match anything.

    A hand-typed `(codename, slot)` that the file never states is not an
    error, it is *silence*: the lookup returns None for ever and the ability
    simply never draws its ring.  Nothing else here would notice, because
    "returns None" is also the correct answer for every ability the table does
    not cover.

    Needs a decoded library, so it is skipped where there is none -- the same
    treatment `tests/test_positions.py` gives its measurements.
    """

    @classmethod
    def setUpClass(cls):
        cls.seen: set[tuple[str, str]] = set()
        for path in sorted(CACHE.glob("*.json")):
            stored = json.loads(path.read_text(encoding="utf-8"))
            for record in stored.get("ability_spawns", {}).values():
                ref = abilities.parse(record[0])
                if ref is not None:
                    cls.seen.add((ref.codename, ref.slot))

    def setUp(self):
        if not self.seen:
            self.skipTest("no decoded captures in .cache/positions")

    def test_every_entry_is_an_ability_the_library_actually_states(self):
        unseen = sorted(key for key in abilityfacts._MECHANICS if key not in self.seen)
        assert not unseen, f"these keys never match a decoded ability: {unseen}"

    def test_the_table_covers_most_of_what_the_library_casts(self):
        """
        A coverage floor rather than a ceiling.  It is allowed to be
        incomplete -- sixteen agents of twenty-nine -- but a table that had
        quietly stopped matching would show up here as a collapse rather than
        as a map with no rings on it.
        """
        named = sum(1 for key in self.seen if key in abilityfacts._MECHANICS)
        # A hundred of the library's 114 decoded slots are named now, and the
        # floor moved with it: at 40 this had stopped being able to see a
        # collapse, since more than half the table could go before it fired.
        assert named >= 95, f"only {named} of {len(self.seen)} decoded slots are named"


class EveryAbilityNameJoinsRiotsCatalogue(unittest.TestCase):
    """
    That the table's published names are Riot's, and that they pick the icon.

    This is what retired a refusal rather than merely restating it.  The map
    used to draw a keybind letter for every Q and E cast because no arrangement
    of *letters* joins the decode to Riot's catalogue: the archetype path's
    slot is Riot's internal letter and does not track the keybind -- Sova's
    Recon Bolt decodes as `Q` and the game binds it to E -- and Riot's own
    `Ability1`/`Ability2`/`Grenade` names do not track the keybind either, with
    Phoenix's `Ability1` being Hot Hands, which the game binds to E.  Two
    namespaces, each shuffled against the keybind, and shuffled differently.

    A **name** is not a letter.  `abilityfacts` says which ability sits in each
    internal slot and the manifest says what Riot calls each one, so matching
    them is an identity.  Measured here over every entry, and it is also what
    caught the join that was shipping: `Grenade` was taken to be the C slot on
    every agent and is the C slot on eight of these sixteen, so half the C-slot
    casts on the map carried the wrong ability's picture -- Stim Beacon's on
    Brimstone's Sky Smoke, Shrouded Step's on Omen's Dark Cover.  Nothing
    failed and nothing looked wrong, because one white glyph at fourteen pixels
    looks much like another.

    Needs a fetched `assets/`, so it skips without one.
    """

    @classmethod
    def setUpClass(cls):
        from vrfview import art

        cls.cache = art.load(Path("assets"))

    def setUp(self):
        if self.cache.empty:
            self.skipTest(self.cache.reason)

    def _art_for(self, codename: str):
        from vrfview import names

        agent, _source = names._agent_for(codename)
        return self.cache.agent_art_by_name(agent)

    def test_every_entry_names_exactly_one_published_ability(self):
        missed = []
        for (codename, slot), facts in abilityfacts._MECHANICS.items():
            found = self._art_for(codename)
            if found is None:
                self.skipTest(f"no art for {codename}")
            if found.ability_named(facts.ability) is None:
                missed.append((codename, slot, facts.ability))
        assert not missed, f"named no published ability: {missed}"

    def test_every_entry_therefore_has_a_picture(self):
        """Including Q and E, which is the whole point of joining by name."""
        for (codename, slot), facts in abilityfacts._MECHANICS.items():
            found = self._art_for(codename)
            if found is None:
                self.skipTest(f"no art for {codename}")
            joined = found.ability_named(facts.ability)
            assert joined is not None, (codename, slot)
            assert joined.icon is not None, f"{codename} {slot} has no icon file"

    def test_the_slot_join_alone_would_get_the_c_slot_wrong(self):
        """
        The measurement that removed `C` from `art.SLOT_TO_MANIFEST`.

        Kept as an assertion rather than a comment because it is the evidence:
        if Riot ever renames these so that `Grenade` *is* the internal C slot
        everywhere, this fails and the fallback can be widened again on
        purpose. Under-claiming is the safe direction and has to stay visible.
        """
        from vrfview import art

        assert "C" not in art.SLOT_TO_MANIFEST
        wrong = 0
        for (codename, slot), facts in abilityfacts._MECHANICS.items():
            if slot != "C":
                continue
            found = self._art_for(codename)
            if found is None:
                self.skipTest(f"no art for {codename}")
            grenade = found.abilities.get("Grenade")
            if (
                grenade is not None
                and found.ability_named(facts.ability) is not grenade
            ):
                wrong += 1
        assert wrong >= 5, f"only {wrong} disagree; the C join may be safe again"

    def test_each_named_agent_is_a_bijection_onto_its_four_abilities(self):
        """
        Four slots, four different pictures, and every one of Riot's four used.

        This is the check that would catch the *next* version of the join that
        was shipping.  Every entry naming exactly one published ability is not
        enough on its own: two slots of one agent could name the same ability
        and both would join, and the map would then draw one icon twice and
        another never.  So for an agent whose four internal slots are all in
        the table, the four names must be distinct, the four `AbilityArt`
        objects must be distinct, and together they must be exactly Riot's
        `Ability1`, `Ability2`, `Grenade` and `Ultimate` for that agent.
        """
        by_codename: dict[str, dict[str, str]] = {}
        for (codename, slot), facts in abilityfacts._MECHANICS.items():
            by_codename.setdefault(codename, {})[slot] = facts.ability
        checked = 0
        for codename, slots in sorted(by_codename.items()):
            if set(slots) != {"C", "Q", "E", "X"}:
                continue
            found = self._art_for(codename)
            if found is None:
                continue
            checked += 1
            names_used = list(slots.values())
            assert len(set(names_used)) == len(names_used), (
                f"{codename} names one ability twice: {names_used}"
            )
            joined = [found.ability_named(name) for name in names_used]
            assert all(entry is not None for entry in joined), codename
            slots_used = {entry.slot for entry in joined if entry is not None}
            assert slots_used == {"Ability1", "Ability2", "Grenade", "Ultimate"}, (
                f"{codename} covers {sorted(slots_used)}"
            )
        assert checked >= 20, f"only {checked} agents had all four slots"

    def test_the_ultimate_slot_still_joins_by_letter(self):
        """X is exact on every agent measured, which is why it survives."""
        from vrfview import art

        assert art.SLOT_TO_MANIFEST["X"] == "Ultimate"
        for (codename, slot), facts in abilityfacts._MECHANICS.items():
            if slot != "X":
                continue
            found = self._art_for(codename)
            if found is None:
                self.skipTest(f"no art for {codename}")
            assert found.ability("X") is found.ability_named(facts.ability), codename


class AWallIsDrawnFromItsOwnGeometryOrNotAtAll(unittest.TestCase):
    """
    The three wall kinds, and what each of them is allowed to claim.

    `"segments"` and nothing else: the cast opens a channel per segment and the
    whole line is decoded, so it needs no length and must not carry one.

    There were going to be two more, for a wall drawn along the caster's yaw at
    a looked-up length, and the premise failed twice: Phoenix's Blaze and
    Harbor's High Tide follow a steerable missile and are a different length
    every cast, and Vyse's Shear is placed on vertical terrain rather than
    along the way the caster faced.  The single value here is what stops that
    idea coming back without the measurement that would justify it.
    """

    KINDS = ("segments",)

    def test_every_wall_names_one_of_the_three_shapes(self):
        for key, facts in abilityfacts._MECHANICS.items():
            if facts.wall is not None:
                assert facts.wall in self.KINDS, f"{key} claims shape {facts.wall!r}"

    def test_every_wall_says_where_its_shape_came_from(self):
        for key, facts in abilityfacts._MECHANICS.items():
            if facts.wall is not None:
                assert facts.wall_source, f"{key} claims a wall with no source"

    def test_a_wall_is_never_also_a_circle(self):
        for key, facts in abilityfacts._MECHANICS.items():
            if facts.wall == "segments":
                assert facts.radius_uu is None, f"{key} is a wall and not a circle"

    def test_no_wall_carries_a_looked_up_length(self):
        """
        There is no `wall_length_uu` field at all, and this is the check that
        it does not come back quietly: the only wall here is measured from its
        own coordinates, and a figure beside it would be a second answer to a
        question already settled by the capture.
        """
        assert not hasattr(abilityfacts.AbilityMechanics, "wall_length_uu")

    def test_sages_barrier_is_the_decoded_one(self):
        facts = abilityfacts.mechanics_for("Thorne", "E")
        assert facts is not None
        assert facts.wall == "segments"


class WhatDiesWithItsCaster(unittest.TestCase):
    """
    Exactly four abilities, listed rather than derived.

    A published rule of the game -- Chamber's Trademark and Rendezvous and
    Cypher's Trapwire and Spycam are removed the moment their owner dies -- and
    the *absence* is the load-bearing half: Killjoy's utility is disabled at
    range and destroyed only by damage, so it stands when she falls.  Reading
    `persists` as this flag would have swept three of her four abilities off
    the map every time she traded.
    """

    DIES: ClassVar[set[tuple[str, str]]] = {
        ("Deadeye", "C"),
        ("Deadeye", "E"),
        ("Gumshoe", "E"),
        ("Gumshoe", "Q"),
    }

    def test_exactly_these_four_die_with_their_caster(self):
        found = {
            key
            for key, facts in abilityfacts._MECHANICS.items()
            if facts.destroyed_on_caster_death
        }
        assert found == self.DIES

    def test_killjoys_utility_survives_her(self):
        for slot in ("C", "Q", "E", "X"):
            facts = abilityfacts.mechanics_for("Killjoy", slot)
            assert facts is not None
            assert facts.destroyed_on_caster_death is False, slot

    def test_nothing_dies_with_a_caster_without_standing_first(self):
        """The flag is a narrowing of `persists` and is meaningless alone."""
        for key, facts in abilityfacts._MECHANICS.items():
            if facts.destroyed_on_caster_death:
                assert facts.persists, f"{key} dies with its caster but never stood"


class WhatSees(unittest.TestCase):
    """
    Which ability pawns get a view cone, and why it is a lookup.

    A Boom Bot and a Blast Pack are pawns too and neither looks at anything, so
    the kind cannot answer this.  Both entries here are cameras somebody steers.
    """

    SEES: ClassVar[set[tuple[str, str]]] = {("Hunter", "E"), ("Cashew", "C")}

    def test_exactly_the_cameras_see(self):
        found = {key for key, facts in abilityfacts._MECHANICS.items() if facts.sees}
        assert found == self.SEES
