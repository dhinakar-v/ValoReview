"""
The one place external knowledge is joined onto a replay.

vrfview.infer derives facts from the file's own contents.  This module does
something different and keeps it separate on purpose: it takes the codename a
player's pawn states and turns it into the name a person would use.  Nothing
here decides anything; a codename with no entry keeps whatever the loader put
there and a note says so, and the notes go in `Replay.catalog_notes` rather
than `Replay.notes`, because a looked-up fact and a derived one are different
claims.

There was a live catalogue behind this, and it has been removed
---------------------------------------------------------------
`valcatalog` reduced a `val-content-v1` response to two more joins -- map asset
path to name, and agent UUID to name -- and `valapi` fetched one.  Nothing ever
passed a catalogue in: `vrf_serve` constructed its settings without one, so
every call arrived with `None` and took the fallback path below.  A parameter
that is always `None` is not a feature, so both modules went, and with them the
only thing in the project that opened a socket.

What that costs is honest and small.  Map names come from `loader.MAP_NAMES`,
which the loader has already applied.  `Loadout.agent` -- the UUID join -- is
now never filled, so `Replay.roster` is always empty; it was already empty in
every response the server has ever sent.  The cross-check that compared the
pawn agents against the loadout roster went with it, for the same reason: with
one side permanently empty it could never fire.

The join that is left, and its one gap
--------------------------------------
    Player.codename                     == AgentDto.developerName     (agents)

`developerName` is published by valorant-api.com and has no equivalent in
val-content-v1.  AGENT_CODENAMES below is the table, sourced from it on
2026-08-21 -- the exact counterpart of `loader.MAP_NAMES`, and reported as such.

Why the roster is still not attached to players
-----------------------------------------------
The loadout list and the actor net IDs in the event stream remain two disjoint
namespaces: no field anywhere links them, and nothing decoded since has changed
that.  So the loadouts are still reported in the file's own order, and "loadout
slot 3 is actor 646" is still an invention.

What did change, long before this, is that a player no longer needs the roster
to have an agent.  Its pawn states its own archetype --
`/Game/Characters/Hunter/Hunter_PC` -- and vrfview.tracks reads the codename
out of it.  That is a fact about the actor, from the actor, so naming it here
is a lookup and not a guess.
"""

from __future__ import annotations

from dataclasses import replace

from vrfview.abilities import GRENADE, ULTIMATE
from vrfview.model import Player, Replay

CODENAME_SOURCE_TABLE = "built-in codename table"

# What `Replay.catalog_source` says now that there is no catalogue to consult.
# A sentence rather than an empty string: the field is on the wire and a reader
# is owed the reason it is not naming a published source.
CATALOG_SOURCE = (
    "built-in tables (map names and agent codenames); no content catalogue is consulted"
)

# Riot's internal agent names, as valorant-api.com published them on
# 2026-08-21.  Keyed lowercase because the archetype path capitalises and the
# catalogue need not.  This is the keyless fallback only: a manifest that
# carries developer names is preferred and says so.
AGENT_CODENAMES = {
    "aggrobot": "Gekko",
    "bountyhunter": "Fade",
    "breach": "Breach",
    "cable": "Deadlock",
    "cashew": "Tejo",
    "clay": "Raze",
    "deadeye": "Chamber",
    "grenadier": "KAY/O",
    "guide": "Skye",
    "gumshoe": "Cypher",
    "hunter": "Sova",
    "iris": "Miks",
    "killjoy": "Killjoy",
    "mage": "Harbor",
    "nox": "Vyse",
    "pandemic": "Viper",
    "phoenix": "Phoenix",
    "pine": "Veto",
    "rift": "Astra",
    "sarge": "Brimstone",
    "sequoia": "Iso",
    "smonk": "Clove",
    "sprinter": "Neon",
    "stealth": "Yoru",
    "terra": "Waylay",
    "thorne": "Sage",
    "vampire": "Reyna",
    "wraith": "Omen",
    "wushu": "Jett",
}


def resolve(replay: Replay) -> Replay:
    """Name each player from the codename its pawn archetype stated."""
    replay.catalog_source = CATALOG_SOURCE
    _resolve_codenames(replay)
    _resolve_casts(replay)
    return replay


def _resolve_casts(replay: Replay) -> None:
    """
    Name the agent behind each ability cast, and say what could not be named.

    An ability actor's path states its agent's codename, so the caster is a
    lookup of the same kind `_resolve_codenames` makes for a pawn -- and it is
    made here, in the module that owns lookups, rather than in `tracks`, which
    reads the stream and is not allowed to consult a table.

    The ability's own name is a different matter and is *not* resolved for two
    of the four slots.  X is always `Ultimate` and C always `Grenade` in Riot's
    published data, so those join exactly.  Q and E are published as `Ability1`
    and `Ability2` **in an order that varies by agent**, so no join exists;
    those keep the internal name read out of the archetype path, which is a
    fact from the file rather than a guess dressed as a lookup.
    """
    if not replay.ability_casts:
        return

    # `replace`, not a fresh `AbilityCast` listing every field.  This is a
    # lookup filling in one field, and rebuilding the record by hand made it
    # silently drop any field added since -- which is exactly what happened
    # when casts learnt where they landed: the coordinates were decoded,
    # stored and read back correctly, and then dropped here on the way past.
    # A test pins it now, but the shape is what stops it recurring.
    replay.ability_casts = [
        replace(c, agent=_agent_for(c.codename)[0]) for c in replay.ability_casts
    ]

    slots = {c.slot for c in replay.ability_casts}
    joinable = sorted(slots & {ULTIMATE, GRENADE})
    unjoinable = sorted(slots - {ULTIMATE, GRENADE})
    replay.catalog_notes.append(
        f"{len(replay.ability_casts)} ability casts read from the archetype "
        f"paths of the actors each one spawned; there is no ability event in "
        f"the file",
    )
    if unjoinable:
        replay.catalog_notes.append(
            f"ability names for slots {', '.join(unjoinable)} are the internal "
            f"names read from those paths, not published names: Riot publishes "
            f"Q and E as Ability1/Ability2 in an order that varies by agent, so "
            f"there is no join"
            + (
                f"; slots {', '.join(joinable)} are named from the table"
                if joinable
                else ""
            ),
        )


def _resolve_codenames(replay: Replay) -> None:
    """Name each player from the codename its pawn archetype stated."""
    if not any(p.codename for p in replay.players):
        return

    named: list[Player] = []
    for p in replay.players:
        named.append(
            Player(
                actor_id=p.actor_id,
                team=p.team,
                label=p.label,
                merged_from=p.merged_from,
                codename=p.codename,
                agent=_agent_for(p.codename)[0],
            ),
        )
    replay.players = named

    resolved = [p for p in replay.players if p.agent]
    coded = [p for p in replay.players if p.codename]
    roster = ", ".join(f"{p.label or p.actor_id} {p.agent}" for p in resolved)
    replay.catalog_notes.append(
        f"{len(resolved)}/{len(coded)} player pawns named from their archetype "
        f"codename against the {CODENAME_SOURCE_TABLE}: {roster or 'none'}",
    )
    unresolved = sorted({p.codename for p in coded if not p.agent})
    if unresolved:
        replay.catalog_notes.append(
            f"{len(unresolved)} codenames are in no built-in table "
            f"({', '.join(unresolved)}); they are shown as they are read",
        )


def _agent_for(codename: str) -> tuple[str, str]:
    """The public name for a codename, and which source produced it."""
    if not codename:
        return "", ""
    name = AGENT_CODENAMES.get(codename.lower())
    return (name, CODENAME_SOURCE_TABLE) if name else ("", "")
