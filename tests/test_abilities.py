"""
The ability path parser, against paths that were actually observed.

Every archetype string below was read out of a real 12.10 capture
(`Demos/03fcbb4a-...vrf`, three REPLAYDATA blocks) rather than invented, which
is what makes these tests worth anything: the parser's whole job is to survive
Riot's naming, and Riot's naming is not consistent enough to guess at.  The
awkward cases are the point -- `Ability_4` for the C slot, agent and slot
swapped round in half the leaves, a slot that only exists in the folder, and a
passive that has no `Ability_*` folder at all.
"""

from __future__ import annotations

import unittest

from vrfview import abilities
from vrfview.model import Player, Position, Round, Track

# --- observed, verbatim ----------------------------------------------------
TURRET_PAWN = (
    "/Game/Characters/Killjoy/S0/Ability_E/Pawn_Killjoy_E_Turret"
    ".Default__Pawn_Killjoy_E_Turret_C"
)
TURRET_CAST = (
    "/Game/Characters/Killjoy/S0/Ability_E/Ability_Killjoy_E_Turret"
    ".Default__Ability_Killjoy_E_Turret_C"
)
TURRET_ATTACK = (
    "/Game/Characters/Killjoy/S0/Ability_E/Ability_Killjoy_E_TurretAttack"
    ".Default__Ability_Killjoy_E_TurretAttack_C"
)
DRONE_PAWN = (
    "/Game/Characters/Hunter/S0/Ability_E/Drone/Pawn_Hunter_E_Drone"
    ".Default__Pawn_Hunter_E_Drone_C"
)
JETT_SMOKE_CAST = (
    "/Game/Characters/Wushu/S0/Ability_4/Ability_Wushu_4_Smoke"
    ".Default__Ability_Wushu_4_Smoke_C"
)
JETT_SMOKE_PROJECTILE = (
    "/Game/Characters/Wushu/S0/Ability_4/Projectile_Wushu_4_Smoke"
    ".Default__Projectile_Wushu_4_Smoke_C"
)
JETT_SMOKE_ZONE = (
    "/Game/Characters/Wushu/S0/Ability_4/GameObject_Wushu_4_SmokeZone"
    ".Default__GameObject_Wushu_4_SmokeZone_C"
)
# Slot before the codename, not after.
CLOVE_KNIFE = (
    "/Game/Characters/Smonk/S0/Ability_Q/DebuffKnife/DecayLauncher"
    "/Ability_Q_Smonk_DebuffKnife.Default__Ability_Q_Smonk_DebuffKnife_C"
)
# No slot token in the leaf at all; only the folder says E.
CLOVE_SMOKE_OBJECT = (
    "/Game/Characters/Smonk/S0/Ability_E/MapTargetSmoke/GameObject_Smonk_NewSmoke"
    ".Default__GameObject_Smonk_NewSmoke_C"
)
# No `Ability_*` folder; the slot is a token in the leaf.
JETT_GLIDE = (
    "/Game/Characters/Wushu/S0/Glide/Ability_Wushu_Passive_Glide"
    ".Default__Ability_Wushu_Passive_Glide_C"
)
KILLJOY_ULT = (
    "/Game/Characters/Killjoy/S0/Ability_X/Ability_Killjoy_X_Bomb"
    ".Default__Ability_Killjoy_X_Bomb_C"
)

# Things that must NOT parse as abilities.
PLAYER_PAWN = "/Game/Characters/Hunter/Hunter_PC.Default__Hunter_PC_C"
CORPSE = "/Game/Characters/Smonk/Smonk_PostDeath_PC.Default__Smonk_PostDeath_PC_C"
MELEE = "/Game/Equippables/Melee/Ability_Melee_Base.Default__Ability_Melee_Base_C"
PISTOL = "/Game/Equippables/Guns/Sidearms/Luger/LugerPistol.Default__LugerPistol_C"


class TestParse(unittest.TestCase):
    def test_a_pawn_names_its_agent_slot_kind_and_ability(self):
        ref = abilities.parse(TURRET_PAWN)
        assert ref.codename == "Killjoy"
        assert ref.slot == "E"
        assert ref.kind == abilities.KIND_PAWN
        assert ref.name == "Turret"

    def test_ability_4_is_the_c_slot(self):
        """Riot numbers the C slot rather than lettering it.  See the module doc."""
        assert abilities.parse(JETT_SMOKE_CAST).slot == "C"
        assert abilities.parse(JETT_SMOKE_PROJECTILE).slot == "C"

    def test_slot_before_codename_parses_the_same(self):
        """`Ability_Q_Smonk_DebuffKnife` -- the leaf token order is not fixed."""
        ref = abilities.parse(CLOVE_KNIFE)
        assert ref.codename == "Smonk"
        assert ref.slot == "Q"
        assert ref.name == "DebuffKnife"

    def test_the_folder_supplies_a_slot_the_leaf_omits(self):
        ref = abilities.parse(CLOVE_SMOKE_OBJECT)
        assert ref.slot == "E"
        assert ref.kind == abilities.KIND_GAMEOBJECT
        assert ref.name == "NewSmoke"

    def test_a_passive_has_no_ability_folder_and_still_resolves(self):
        ref = abilities.parse(JETT_GLIDE)
        assert ref.slot == abilities.PASSIVE
        assert ref.name == "Glide"

    def test_only_pawns_are_reported_as_moving(self):
        """The measured fact the whole feature is bounded by."""
        assert abilities.parse(TURRET_PAWN).moves
        assert abilities.parse(DRONE_PAWN).moves
        assert not abilities.parse(JETT_SMOKE_PROJECTILE).moves
        assert not abilities.parse(JETT_SMOKE_ZONE).moves
        assert not abilities.parse(JETT_SMOKE_CAST).moves

    def test_non_abilities_are_refused(self):
        for path in (PLAYER_PAWN, CORPSE, MELEE, PISTOL, "", "/Game", "///"):
            assert abilities.parse(path) is None, path

    def test_the_melee_is_called_ability_and_is_not_one(self):
        """It lives under /Game/Equippables, which is what rejects it."""
        assert abilities.parse(MELEE) is None

    def test_internal_names_become_words(self):
        assert abilities.humanise("RemoteBees_MultiDetonate") == (
            "Remote Bees Multi Detonate"
        )
        assert abilities.humanise("OwlDrone") == "Owl Drone"
        assert abilities.humanise("MapTargetSmokeV2") == "Map Target Smoke V2"


def spawns(*pairs):
    """(archetype, t_ms) pairs as the two history tables `spawns_from` reads."""
    archetypes = {i: path for i, (path, _t) in enumerate(pairs, start=100)}
    first_seen = {i: t / 1000 for i, (_p, t) in enumerate(pairs, start=100)}
    return abilities.spawns_from(archetypes, first_seen)


ROUNDS = [
    Round(number=1, index=0, start_ms=0, end_ms=60_000),
    Round(number=2, index=1, start_ms=60_000, end_ms=120_000),
]


def round_of(t_ms):
    for rnd in ROUNDS:
        if rnd.contains(t_ms):
            return rnd.number
    return 0


class TestSpawns(unittest.TestCase):
    def test_an_actor_with_no_recorded_time_is_skipped(self):
        """A cast at the wrong instant lands in the wrong round; absence does not."""
        found = abilities.spawns_from({1: TURRET_CAST, 2: DRONE_PAWN}, {1: 4.0})
        assert [s.actor_id for s in found] == [1]

    def test_spawns_come_back_in_time_order(self):
        found = spawns((DRONE_PAWN, 9000), (TURRET_CAST, 1000))
        assert [s.t_ms for s in found] == [1000, 9000]

    def test_non_ability_actors_never_appear(self):
        assert spawns((PISTOL, 1000), (PLAYER_PAWN, 2000)) == []


class TestCasts(unittest.TestCase):
    def test_one_cast_per_agent_slot_and_round(self):
        """
        Jett's smoke spawns three actors and is one decision.

        Counting actors would report it three times, which is the difference
        between describing the match and describing the wire.
        """
        found = abilities.casts(
            spawns(
                (JETT_SMOKE_CAST, 5000),
                (JETT_SMOKE_PROJECTILE, 5100),
                (JETT_SMOKE_ZONE, 5300),
            ),
            round_of=round_of,
        )
        assert len(found) == 1
        assert found[0].slot == "C"
        assert found[0].spawns == 3
        assert found[0].t_ms == 5000
        assert found[0].round_no == 1

    def test_a_turret_firing_repeatedly_is_still_one_cast(self):
        found = abilities.casts(
            spawns(
                (TURRET_CAST, 3000),
                (TURRET_PAWN, 3200),
                (TURRET_ATTACK, 20_000),
                (TURRET_ATTACK, 31_000),
            ),
            round_of=round_of,
        )
        assert len(found) == 1
        assert found[0].t_ms == 3000
        assert found[0].spawns == 4

    def test_the_same_slot_in_two_rounds_is_two_casts(self):
        found = abilities.casts(
            spawns((TURRET_CAST, 3000), (TURRET_CAST, 70_000)),
            round_of=round_of,
        )
        assert [c.round_no for c in found] == [1, 2]

    def test_pawn_actor_ids_travel_with_the_cast(self):
        found = abilities.casts(
            spawns((TURRET_CAST, 3000), (TURRET_PAWN, 3200)),
            round_of=round_of,
        )
        assert len(found[0].pawns) == 1
        assert found[0].has_track

    def test_effects_with_no_cast_are_dropped(self):
        """
        A smoke still standing when the round rolled over is not a new cast.

        Its `GameObject_` reopens in the next round's window with no
        `Ability_` beside it, and reporting that would put a decision in a
        round nobody made it in.
        """
        assert (
            abilities.casts(spawns((JETT_SMOKE_ZONE, 70_000)), round_of=round_of) == []
        )

    def test_a_catalogue_name_is_applied_where_it_is_given(self):
        found = abilities.casts(
            spawns((TURRET_CAST, 3000)),
            round_of=round_of,
            codenames={"Killjoy": "Killjoy"},
        )
        assert found[0].agent == "Killjoy"
        assert found[0].identity == "Killjoy"

    def test_a_cast_falls_back_to_its_codename(self):
        found = abilities.casts(spawns((CLOVE_KNIFE, 3000)), round_of=round_of)
        assert found[0].agent == ""
        assert found[0].identity == "Smonk"
        assert found[0].display_name == "Debuff Knife"


class TestWorldSnapshots(unittest.TestCase):
    """
    A burst of spawns across many agents on one millisecond is the engine.

    Measured on a 19-round capture: two instants carry 33 ability actors each
    -- four slots for every one of five agents -- while the busiest genuine
    millisecond in the whole match carries two, both from the same agent.  So
    the signature is *distinct agents*, not actor count.
    """

    def test_many_agents_on_one_instant_is_a_snapshot(self):
        found = abilities.snapshot_instants(
            spawns(
                (TURRET_CAST, 63),
                (JETT_SMOKE_CAST, 63),
                (CLOVE_KNIFE, 63),
                (DRONE_PAWN, 5000),
            ),
        )
        assert found == {63}

    def test_two_agents_together_is_a_coordinated_play_not_a_snapshot(self):
        """A pair of agents using utility on the same frame is a real execute."""
        assert (
            abilities.snapshot_instants(
                spawns((TURRET_CAST, 4000), (JETT_SMOKE_CAST, 4000)),
            )
            == set()
        )

    def test_one_agent_spawning_several_at_once_is_not_a_snapshot(self):
        """Clove dying sets off her own post-death pair on one millisecond."""
        assert (
            abilities.snapshot_instants(
                spawns((CLOVE_KNIFE, 900), (CLOVE_SMOKE_OBJECT, 900)),
            )
            == set()
        )

    def test_snapshot_spawns_never_become_casts(self):
        found = abilities.casts(
            spawns(
                (TURRET_CAST, 63),
                (JETT_SMOKE_CAST, 63),
                (CLOVE_KNIFE, 63),
                (TURRET_CAST, 40_000),
            ),
            round_of=round_of,
        )
        assert [c.t_ms for c in found] == [40_000]


class TestAttribution(unittest.TestCase):
    def test_a_codename_one_player_holds_attributes(self):
        found = abilities.attribute(
            [
                Player(actor_id=7, codename="Hunter"),
                Player(actor_id=8, codename="Wushu"),
            ],
        )
        assert found.by_codename == {"Hunter": 7, "Wushu": 8}
        assert found.ambiguous == ()
        assert found.note == ""

    def test_a_shared_codename_is_refused_and_said_out_loud(self):
        """
        Two players on one agent cannot be told apart by an archetype path.

        Picking the first would attribute half of somebody's utility to
        somebody else, which is exactly the kind of plausible wrong answer
        this project refuses to produce.
        """
        found = abilities.attribute(
            [
                Player(actor_id=7, codename="Hunter"),
                Player(actor_id=8, codename="Hunter"),
            ],
        )
        assert found.by_codename == {}
        assert found.ambiguous == ("Hunter",)
        assert "unattributed" in found.note

    def test_players_with_no_codename_are_ignored(self):
        assert abilities.attribute([Player(actor_id=1)]).by_codename == {}


class TestTravel(unittest.TestCase):
    @staticmethod
    def track(*points):
        return Track(
            actor_id=1,
            samples=tuple(
                Position(t_ms=i * 100, actor_id=1, x=x, y=y, z=0.0)
                for i, (x, y) in enumerate(points)
            ),
        )

    def test_distance_is_the_path_and_not_the_displacement(self):
        """A drone that flies out and back travelled twice the distance."""
        there_and_back = self.track((0, 0), (300, 0), (0, 0))
        assert abilities.travel(there_and_back) == 600

    def test_a_turret_that_never_moved_travelled_nothing(self):
        """Zero is a real answer here, not a missing one."""
        assert abilities.travel(self.track((10, 10), (10, 10))) == 0.0

    def test_an_empty_track_is_zero_rather_than_an_error(self):
        assert abilities.travel(Track(actor_id=1)) == 0.0
