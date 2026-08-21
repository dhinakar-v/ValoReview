"""
The one place external knowledge is joined onto a replay.

vrfview.infer derives facts from the file's own contents.  This module does
something different and keeps it separate on purpose: it takes UUIDs and asset
paths the file states, looks them up in Riot's published content catalogue, and
records which source answered.  Nothing here decides anything; if the catalogue
has no entry the field keeps whatever the loader put there and a note says so.

Two joins, both verified live on 2026-08-21 (docs/valorant-api.md):

    demo_header.maps[0]                 == ContentItemDto.assetPath   (maps)
    playerLoadouts[].characterId        == ContentItemDto.id          (characters)

Why the roster is not attached to players
-----------------------------------------
The loadout list and the actor net IDs in the event stream are two disjoint
namespaces: no field anywhere in the container links them, and the replication
stream's property payloads -- which might -- are undecoded.  So the agents are
reported as a roster in the file's own order and never as "actor 646 is Astra",
which would be an invention dressed as a lookup.  infer._label_players makes
the same choice for the same reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vrfview.model import Loadout, Replay

if TYPE_CHECKING:
    from valcatalog import Catalog

MAP_NAME_SOURCE_CATALOG = "Riot content catalogue"


def resolve(replay: Replay, catalog: Catalog | None) -> Replay:
    """Apply a catalogue to a replay's map path and agent UUIDs, in place."""
    if catalog is None:
        replay.catalog_source = "no catalogue consulted (--no-catalog)"
        return replay

    replay.catalog_source = catalog.described
    if catalog.empty:
        if replay.loadouts:
            replay.catalog_notes.append(
                f"{len(replay.loadouts)} agent UUIDs are in the file but no content "
                "catalogue is cached to name them; "
                "runners\\vrf-view.bat catalog says where one is looked for",
            )
        return replay

    _resolve_map(replay, catalog)
    _resolve_agents(replay, catalog)
    return replay


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
        "the agent roster is not attributable to actor net IDs: the file links "
        "loadouts to no actor, so no player node carries an agent",
    )
