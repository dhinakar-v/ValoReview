"""
Ability radii and charge counts, looked up rather than read.

**Nothing in this project's inputs carries these numbers.**  Not the `.vrf`, not
val-content-v1, not `assets/manifest.json` -- `docs/valorant-replay-parser-
features.md` lists ability range, radius and damage among the things that are
out of reach.  What a decode gives is *where* a placed ability came to rest and
nothing about how far it reaches, which is why an ability marker was a dot with
a name beside it and no extent.

So this is external knowledge, in the shape `names.AGENT_CODENAMES` already
establishes for external knowledge: a hand-written table, offline, consulted at
runtime and never fetched.  The research happened while authoring it; the table
ships as source.  Every figure carries the page it came from.

The unit is the Unreal unit and the conversion is **exact rather than assumed**:
Riot's own patch notes for Sky Smoke read "Radius increased 410 >>> 415" for an
ability the wiki gives as 4.15 m, so the game's internal number is centimetres
and `UU_PER_METRE` is 100 on Riot's own arithmetic rather than on a convention.

Why this is still drawn as **simulated**
----------------------------------------
Two reasons, and both are on the page.  These are community measurements of a
game that rebalances every few weeks, so a radius here is right for some patch
and this capture may not be that patch -- the replay states its build and this
table does not.  And a radius is an *area of effect*, which is a claim about the
world, where everything else this canvas draws is a coordinate that was decoded.
Drawing it solid beside decoded geometry would make it indistinguishable from
one, so the ring is dashed and its layer is labelled `RANGE (SIM)`.

Why the key is (agent, internal name)
-------------------------------------
Not the keybind, which looks like the obvious key and is a trap.  `abilities`
reads the slot out of the archetype path -- `Ability_Q`, `Ability_E`,
`Ability_4` -- so those letters are Riot's own, but they are Riot's *internal*
letters and they do not track the keybinds the game currently displays.
Measured across the reference library: the decode calls Sova's Recon Bolt `Q`
where the game binds it to E, and Brimstone's Stim Beacon `E` where the game
binds it to C.  Matching the decoded internal names against the manifest's
display names does not rescue it either -- over the 40 (agent, slot) pairs the
library actually produces, a similarity match agrees on 3, and one of those 3
is wrong.

That is also why there is **no Q/E slot map here**.  It was the obvious thing to
add while researching, and the measurement above is the reason it would have
been a guess wearing a citation: `art.AgentArt.ability` goes on refusing Q and E,
and it is right to.

An agent or an ability that is not in this table returns `None`.  There is no
default radius: a ring drawn at a made-up size is worse than no ring, because
the absent one is visibly absent.

The smoke table below is a second table on purpose
--------------------------------------------------
`_SMOKES` answers a different question -- *does this thing block sight, how
wide, and for how long* -- and it is keyed on **(codename, slot)** rather than
on the internal name the table above uses.  That is not a preference; the
internal name is not stable enough to key an occluder on.  Measured over the
reference library, Clove's smoke arrives under **two** names for the same
ability: 257 casts named `Post Death` and 55 named `New Smoke`, because
`abilities._namer` prefers an `Ability_` spawn and then the shortest name, and
`PostDeath` beats `MapTargetSmokeV2`.  Astra's splits the same way between
`Transform Rift Smoke World Targeting` and `Smoke Zone`.  A codename and a slot
are what the archetype path states outright and cannot split.

**The durations here are the weakest figures in this file and are marked so.**
A radius has a published number on a page.  A smoke's lifetime does too, but no
source could be reached from inside this tree to check it against, so each one
carries what standing it actually has in its own `source` string rather than a
citation it has not earned.  `tests/test_abilityfacts.py` pins the radii
against the entries above, so the two tables cannot drift apart; nothing can
pin the durations except somebody reading the page.

The measured route was considered and is not available: a smoke is a
`GameObject_`/`Zone_` placement and **not one of the 2,704 in the library has a
track**, `abilities.spawns_from` records a first-seen and nothing records a
channel close, so there is no lifetime on disk to read.  Getting one means new
C# decoder work, a decode-format bump, a sidecar version bump and a full
re-decode -- and then a validation pass, because a channel close can be
dormancy, a checkpoint reseed or a round rollover.
"""

from __future__ import annotations

from dataclasses import dataclass

# Riot's own arithmetic: see the module docstring.
UU_PER_METRE = 100.0


@dataclass(frozen=True)
class AbilityFacts:
    """What is published about one ability, and where it was published."""

    radius_uu: float | None
    charges: int | None
    source: str

    @property
    def radius_m(self) -> float | None:
        return None if self.radius_uu is None else self.radius_uu / UU_PER_METRE


_WIKI = "wiki.playvalorant.com"

# What a duration figure is worth here.  Spelled out once and referenced by
# every entry, so no `source` string implies a page that was never opened.
_UNCHECKED = (
    "duration is a community figure and was NOT verified against a published "
    "source from this tree"
)

# Keyed by (agent display name, the internal name `abilities.humanise` produces).
#
# Only abilities that **occupy an area a person could point at** are here.  A
# camera, a drone, a decoy and a flash have no radius worth drawing on a radar:
# either they have no extent at all or their extent is a direction rather than a
# circle, and a circle drawn for a cone is a wrong answer that looks right.
_FACTS: dict[tuple[str, str], AbilityFacts] = {
    ("Astra", "Transform Rift Smoke World Targeting"): AbilityFacts(
        475.0,
        2,
        f"{_WIKI}/Nebula_/_Dissipate: smoke radius 4.75 m",
    ),
    ("Brimstone", "Molotov Production"): AbilityFacts(
        450.0,
        1,
        f"{_WIKI}/Incendiary: fire zone radius 4.5 m",
    ),
    ("Chamber", "Trap Dart"): AbilityFacts(
        1000.0,
        1,
        f"{_WIKI}/Trademark: search radius 10 m (slow radius 6 m)",
    ),
    ("Cypher", "Cage Trap"): AbilityFacts(
        372.0,
        2,
        f"{_WIKI}/Cyber_Cage: cylinder radius 3.72 m",
    ),
    ("Deadlock", "Net Toss"): AbilityFacts(
        650.0,
        1,
        f"{_WIKI}/GravNet: radius 6.5 m",
    ),
    ("Deadlock", "Net Toss Underhand"): AbilityFacts(
        650.0,
        1,
        f"{_WIKI}/GravNet: radius 6.5 m",
    ),
    ("Gekko", "Aggrobot C Explodey Patch"): AbilityFacts(
        620.0,
        1,
        f"{_WIKI}/Mosh_Pit: outer radius 6.2 m (inner 5.5 m)",
    ),
    ("Harbor", "World Smoke"): AbilityFacts(
        460.0,
        1,
        f"{_WIKI}/Cove: radius 4.6 m",
    ),
    ("Jett", "Smoke"): AbilityFacts(
        335.0,
        2,
        f"{_WIKI}/Cloudburst: smoke radius 3.35 m",
    ),
    ("Killjoy", "Remote Bees Multi Detonate"): AbilityFacts(
        450.0,
        2,
        f"{_WIKI}/Nanoswarm: damage radius 4.5 m",
    ),
    ("Killjoy", "Stealth Alarmbot"): AbilityFacts(
        550.0,
        1,
        f"{_WIKI}/Alarmbot: bot detects enemies at 5.5 m",
    ),
    ("Omen", "Smoke"): AbilityFacts(
        410.0,
        2,
        f"{_WIKI}/Dark_Cover: smoke radius 4.1 m",
    ),
    ("Phoenix", "Molotov Production"): AbilityFacts(
        450.0,
        1,
        f"{_WIKI}/Hot_Hands: fire zone radius 4.5 m",
    ),
    ("Sova", "Reveal Bolt"): AbilityFacts(
        3000.0,
        1,
        f"{_WIKI}/Recon_Bolt: reveal radius 30 m",
    ),
    ("Vyse", "Barbed Wire"): AbilityFacts(
        625.0,
        2,
        f"{_WIKI}/Razorvine: radius 6.25 m",
    ),
}


def facts_for(agent: str, internal_name: str) -> AbilityFacts | None:
    """
    What is published about one ability, or None.

    None is the ordinary answer and must stay drawable as nothing: most
    abilities have no area, this table does not pretend to be complete, and an
    agent released after it was written is a miss rather than an error.
    """
    if not agent or not internal_name:
        return None
    return _FACTS.get((agent, internal_name))


def radius_uu(agent: str, internal_name: str) -> float | None:
    """The published radius in Unreal units, or None where none is published."""
    found = facts_for(agent, internal_name)
    return None if found is None else found.radius_uu


@dataclass(frozen=True)
class SmokeFacts:
    """A placement that blocks sight: how wide, how long, and on whose word."""

    radius_uu: float
    duration_ms: int
    source: str

    @property
    def radius_m(self) -> float:
        return self.radius_uu / UU_PER_METRE

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000.0


# Keyed by (codename, slot) -- what the archetype path states outright.  See
# the module docstring for why the internal name is not usable here.
#
# **Round smokes only.**  Sage's Barrier, Viper's Toxic Screen, Phoenix's Blaze
# and Harbor's Cascade block sight too and are deliberately absent: they are
# *lines*, and a cast gives one point and no orientation or length, so a circle
# drawn for them would block behind the caster and leave the far ends of a long
# wall open.  That is the same refusal `_FACTS` makes for a cone.
#
# Miks (`Iris`) has 187 smoke casts in the library and is **not** here, because
# no figure for them was available to write down.  An agent this table does not
# name blocks nothing, which is the visibly-absent failure rather than the
# plausible one.
_SMOKES: dict[tuple[str, str], SmokeFacts] = {
    # Brimstone, Sky Smoke.  The radius is the one figure in this table with a
    # first-party source: Riot's patch note reads "Radius increased 410 >>> 415".
    ("Sarge", "C"): SmokeFacts(
        415.0,
        19_250,
        f"Riot patch note, Sky Smoke radius 410 >>> 415; {_UNCHECKED}",
    ),
    # Omen, Dark Cover.  Radius agrees with ("Omen", "Smoke") above.
    ("Wraith", "C"): SmokeFacts(
        410.0,
        15_000,
        f"{_WIKI}/Dark_Cover: smoke radius 4.1 m; {_UNCHECKED}",
    ),
    # Jett, Cloudburst.  Radius agrees with ("Jett", "Smoke") above.
    ("Wushu", "C"): SmokeFacts(
        335.0,
        4_500,
        f"{_WIKI}/Cloudburst: smoke radius 3.35 m; {_UNCHECKED}",
    ),
    # Astra, Nebula.  Radius agrees with the Astra entry above.
    ("Rift", "E"): SmokeFacts(
        475.0,
        15_000,
        f"{_WIKI}/Nebula_/_Dissipate: smoke radius 4.75 m; {_UNCHECKED}",
    ),
    # Harbor, Cove.  Radius agrees with ("Harbor", "World Smoke") above.
    ("Mage", "E"): SmokeFacts(
        460.0,
        15_000,
        f"{_WIKI}/Cove: radius 4.6 m; {_UNCHECKED}",
    ),
}


def smoke_for(codename: str, slot: str) -> SmokeFacts | None:
    """
    What blocks sight for this agent's slot, or None if nothing is known.

    None is the answer for every ability that is not a round smoke, and for a
    round smoke nobody has written a figure down for.  A caller must draw and
    occlude nothing rather than reach for a default: a smoke of a made-up size
    standing for a made-up length of time is the plausible wrong answer, and
    the whole of `tests/test_positions.py` exists because of those.
    """
    return _SMOKES.get((codename, slot))
