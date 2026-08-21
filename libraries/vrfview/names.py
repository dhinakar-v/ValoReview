"""
The one place external knowledge is joined onto a replay.

vrfview.infer derives facts from the file's own contents.  This module does
something different and keeps it separate on purpose: it takes UUIDs and asset
paths the file states, looks them up in Riot's published content catalogue, and
records which source answered.  Nothing here decides anything; if the catalogue
has no entry the field keeps whatever the loader put there and a note says so.

Three joins, all verified live on 2026-08-21 (docs/valorant-api.md):

    demo_header.maps[0]                 == ContentItemDto.assetPath   (maps)
    playerLoadouts[].characterId        == ContentItemDto.id          (characters)
    Player.codename                     == AgentDto.developerName     (agents)

Why the roster is still not attached to players
-----------------------------------------------
The loadout list and the actor net IDs in the event stream remain two disjoint
namespaces: no field anywhere links them, and nothing decoded since has changed
that.  So the loadouts are still reported as a roster in the file's own order,
and "loadout slot 3 is actor 646" is still an invention.

What did change is that a player no longer needs the roster to have an agent.
Its pawn states its own archetype -- `/Game/Characters/Hunter/Hunter_PC` --
and vrfview.tracks reads the codename out of it.  That is a fact about the
actor, from the actor, so naming it here is a lookup and not a guess.  The two
paths never cross: `Loadout.agent` comes from a UUID and `Player.agent` from a
codename, and neither is ever filled from the other.

The codename join, and its one gap
----------------------------------
`developerName` is published by valorant-api.com and has no equivalent in
val-content-v1, so only a fetch_assets manifest carries it, and only one
written since fetch_assets began recording it.  AGENT_CODENAMES below is the
keyless fallback for every other case -- the exact counterpart of
loader.MAP_NAMES, sourced the same way, and reported as such.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vrfview.model import Loadout, Player, Replay

if TYPE_CHECKING:
    from valcatalog import Catalog

MAP_NAME_SOURCE_CATALOG = "Riot content catalogue"
CODENAME_SOURCE_TABLE = "built-in codename table"

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


def resolve(replay: Replay, catalog: Catalog | None) -> Replay:
    """Apply a catalogue to a replay's map path, agent UUIDs and codenames."""
    usable = _describe(replay, catalog)
    if usable is not None:
        _resolve_map(replay, usable)
        _resolve_agents(replay, usable)
    # Codenames are resolved either way: the built-in table needs no catalogue
    # and is the only thing a player pawn can fall back on.
    _resolve_codenames(replay, usable)
    return replay


def _describe(replay: Replay, catalog: Catalog | None) -> Catalog | None:
    """Record where names come from; None means fall back to the tables."""
    if catalog is None:
        replay.catalog_source = "no catalogue consulted (--no-catalog)"
        return None

    replay.catalog_source = catalog.described
    if catalog.empty:
        if replay.loadouts:
            replay.catalog_notes.append(
                f"{len(replay.loadouts)} agent UUIDs are in the file but no content "
                "catalogue is cached to name them; "
                "runners\\vrf-view.bat catalog says where one is looked for",
            )
        return None
    return catalog


def _resolve_map(replay: Replay, catalog: Catalog) -> None:
    name = catalog.map_name(replay.map_path)
    if not name:
        if replay.map_path:
            replay.catalog_notes.append(
                f"map path {replay.map_path!r} is in no catalogue entry; "
                f"the name shown comes from the {replay.map_name_source}",
            )
        return

    was = replay.map_name
    replay.map_name = name
    replay.map_name_source = f"{MAP_NAME_SOURCE_CATALOG} ({catalog.source})"
    changed = "" if was == name else f", where the built-in table said {was!r}"
    version = f" {catalog.version}" if catalog.version else ""
    replay.catalog_notes.append(
        f"map name {name!r} resolved from {replay.map_path!r} by asset path against "
        f"{catalog.source}{version}{changed}",
    )


def _resolve_agents(replay: Replay, catalog: Catalog) -> None:
    if not replay.loadouts:
        return

    replay.loadouts = [
        Loadout(
            index=x.index,
            subject=x.subject,
            character_id=x.character_id,
            agent=catalog.agent_name(x.character_id) or "",
        )
        for x in replay.loadouts
    ]

    named = replay.roster
    total = len(replay.loadouts)
    replay.catalog_notes.append(
        f"{len(named)}/{total} agent UUIDs resolved against {catalog.source}: "
        f"{', '.join(named) or 'none'}",
    )
    unresolved = [x.character_id for x in replay.loadouts if not x.agent]
    if unresolved:
        replay.catalog_notes.append(
            f"{len(unresolved)} agent UUIDs are in no catalogue entry "
            f"({', '.join(unresolved)}); the catalogue may predate the agent",
        )
    replay.catalog_notes.append(
        "the loadout roster is still not attributable to actor net IDs: the file "
        "links loadouts to no actor, so a player's agent comes from its own pawn "
        "archetype or not at all",
    )


def _resolve_codenames(replay: Replay, catalog: Catalog | None) -> None:
    """Name each player from the codename its pawn archetype stated."""
    if not any(p.codename for p in replay.players):
        return

    sources: set[str] = set()
    named: list[Player] = []
    for p in replay.players:
        agent, source = _agent_for(p.codename, catalog)
        if source:
            sources.add(source)
        named.append(
            Player(
                actor_id=p.actor_id,
                team=p.team,
                label=p.label,
                merged_from=p.merged_from,
                codename=p.codename,
                agent=agent,
            ),
        )
    replay.players = named

    resolved = [p for p in replay.players if p.agent]
    coded = [p for p in replay.players if p.codename]
    roster = ", ".join(f"{p.label or p.actor_id} {p.agent}" for p in resolved)
    replay.catalog_notes.append(
        f"{len(resolved)}/{len(coded)} player pawns named from their archetype "
        f"codename against {', '.join(sorted(sources)) or 'nothing'}: "
        f"{roster or 'none'}",
    )
    unresolved = sorted({p.codename for p in coded if not p.agent})
    if unresolved:
        replay.catalog_notes.append(
            f"{len(unresolved)} codenames are in no catalogue and no built-in "
            f"table ({', '.join(unresolved)}); they are shown as they are read",
        )
    _cross_check_roster(replay, resolved)


def _cross_check_roster(replay: Replay, resolved: list[Player]) -> None:
    """
    Compare the pawn agents against the loadout roster.

    The two are arrived at along completely separate routes -- one from an
    archetype path in the replication stream through `developerName`, the
    other from a loadout UUID through the content catalogue -- and they have
    no term in common.  So when they name the same ten agents, each is
    evidence for the other; when they do not, something is wrong and the note
    says so rather than picking a winner.
    """
    roster = replay.roster
    if not roster or len(roster) != len(replay.loadouts) or not resolved:
        return
    if len(resolved) != len(roster):
        return

    from_pawns = sorted(p.agent for p in resolved)
    if from_pawns == sorted(roster):
        replay.catalog_notes.append(
            f"the {len(roster)} agents read from the pawns and the {len(roster)} "
            "read from the loadout roster are the same agents, by two joins "
            "that share no term",
        )
        return
    replay.catalog_notes.append(
        f"the agents read from the pawns ({', '.join(from_pawns)}) and from the "
        f"loadout roster ({', '.join(sorted(roster))}) do not agree; one of the "
        "two joins is wrong",
    )


def _agent_for(codename: str, catalog: Catalog | None) -> tuple[str, str]:
    """The public name for a codename, and which source produced it."""
    if not codename:
        return "", ""
    if catalog is not None:
        name = catalog.agent_for_codename(codename)
        if name:
            return name, f"{MAP_NAME_SOURCE_CATALOG} ({catalog.source})"
    name = AGENT_CODENAMES.get(codename.lower())
    return (name, CODENAME_SOURCE_TABLE) if name else ("", "")
