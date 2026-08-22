"""
The model as plain data, ready for JSON.

Kept apart from the server so it can be tested without one, and so the rule it
follows is visible: this module imports no web framework, no image library and
no decoder.  It turns dataclasses into dicts and does nothing else.  Anything
here that needed a request or a PNG would be a sign that a claim was being
invented at the edge rather than carried from the model.

Two conventions run through all of it.

**No integer keys.**  `Replay.positions`, `Replay.ability_tracks` and several
`Snapshot` fields are keyed by actor net ID, and a JSON object key is a string.
Rather than stringify and force the far end to parse back, every one of those
becomes a list of records carrying an explicit `actor_id`.  The one exception is
the positions document, which keeps its string keys because it is already an
on-disk format with readers -- `vrfview.positionfile` owns that shape and this
module does not second-guess it.

**Two name fields for an ability, never one.**  `internal_name` is read out of
the archetype path; `published_name` is Riot's, and resolves for X and C only,
because Q and E vary by agent and `art.AgentArt.ability` refuses to guess.
Collapsing them into one field would let a client silently prefer the wrong one,
which is the coin flip that method exists to avoid.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vrfview import provenance as provenance_mod
from vrfview.abilities import NO_POSITION, travel

if TYPE_CHECKING:
    from pathlib import Path

    from vrfview.art import ArtCache, MapArt
    from vrfview.model import Replay

ASSET_PREFIX = "/assets"


def asset_url(path: Path | None, root: Path) -> str | None:
    """
    One resolved art file as a URL the browser can ask for, or None.

    The path handed in has already come out of the manifest's own `files` dict
    via `art._resolve`, and this only re-roots it.  That ordering is the whole
    point: a URL assembled from a display name breaks on KAY/O, so nothing here
    ever builds a filename -- it only rewrites one the manifest chose.

    A path outside `root` is None rather than an escape: a mistyped --assets
    should cost pictures, not serve the filesystem.
    """
    if path is None:
        return None
    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return f"{ASSET_PREFIX}/{relative.as_posix()}"


def transform_of(art: MapArt) -> dict:
    """
    The four scalars, plus the vertical scale derived from them.

    `vertical_scale` is the same average `sight.uv_radius` takes, published as a
    number rather than left to be rediscovered: it converts an Unreal unit into
    a fraction of the radar, which is what a 3D scene needs to place a player's
    z at the same scale as the map's own footprint.  A figure derived from a
    measured transform, not one chosen because it looked right.
    """
    t = art.transform
    return {
        "x_multiplier": t.x_multiplier,
        "y_multiplier": t.y_multiplier,
        "x_scalar_to_add": t.x_scalar_to_add,
        "y_scalar_to_add": t.y_scalar_to_add,
        "usable": t.usable,
        "vertical_scale": (abs(t.x_multiplier) + abs(t.y_multiplier)) / 2,
    }


def map_art(art: MapArt, root: Path) -> dict:
    """One map's pictures and coordinates.  Never handed a replay."""
    return {
        "name": art.name,
        "codename": art.codename,
        "map_url": art.map_url,
        "plottable": art.plottable,
        "minimap_url": asset_url(art.minimap, root),
        "listview_url": asset_url(art.listview, root),
        "splash_url": asset_url(art.splash, root),
        "transform": transform_of(art),
        "callouts": [
            {"name": c.name, "world_x": c.world_x, "world_y": c.world_y}
            for c in art.callouts
        ],
    }


def _agent_urls(cache: ArtCache | None, name: str) -> dict:
    if cache is None or not name:
        return {"icon_url": None, "portrait_url": None, "role_icon_url": None}
    found = cache.agent_art_by_name(name)
    if found is None:
        return {"icon_url": None, "portrait_url": None, "role_icon_url": None}
    return {
        "icon_url": asset_url(found.icon, cache.root),
        "portrait_url": asset_url(found.portrait, cache.root),
        "role_icon_url": asset_url(found.role_icon, cache.root),
        "role": found.role,
    }


def player(entry, cache: ArtCache | None) -> dict:
    return {
        "actor_id": entry.actor_id,
        "team": entry.team,
        "known_team": entry.known_team,
        "label": entry.label,
        "merged_from": list(entry.merged_from),
        # Read from the pawn's own archetype.
        "codename": entry.codename,
        # Looked up from that codename.  The two are never filled from each
        # other; see vrfview.names.
        "agent": entry.agent,
        "identity": entry.identity,
        "display": entry.display,
        **_agent_urls(cache, entry.agent),
    }


def loadout(entry, cache: ArtCache | None) -> dict:
    """
    One roster slot.  Nothing links it to an actor, and nothing pretends to.

    `character_id` is a UUID from the file and `agent` is what the catalogue
    made of it.  A Player's agent arrives by a different route entirely, which
    is why these are separate lists rather than one joined table.
    """
    art = cache.agent_art(entry.character_id) if cache else None
    return {
        "index": entry.index,
        "subject": entry.subject,
        "character_id": entry.character_id,
        "agent": entry.agent,
        "display": entry.display,
        "icon_url": asset_url(art.icon, cache.root) if art and cache else None,
    }


def ability_cast(cast, replay: Replay, cache: ArtCache | None) -> dict:
    """
    One cast, with both names and a measured distance or none at all.

    `travel_uu` is null rather than zero where no pawn moved: zero is a real
    answer for a turret, and a range this project could publish does not exist
    -- no ability carries one in the replay or in Riot's catalogue.
    """
    published = None
    icon = None
    if cache is not None and cast.agent:
        art = cache.agent_art_by_name(cast.agent)
        slot = art.ability(cast.slot) if art else None
        if slot is not None:
            published = slot.name
            icon = asset_url(slot.icon, cache.root)
    distance = None
    for actor_id in cast.pawns:
        track = replay.ability_track(actor_id)
        if track is not None and track.samples:
            measured = travel(track)
            distance = measured if distance is None else max(distance, measured)
    return {
        "t_ms": cast.t_ms,
        "round_no": cast.round_no,
        "actor_id": cast.actor_id,
        "codename": cast.codename,
        "agent": cast.agent,
        "identity": cast.identity,
        "slot": cast.slot,
        "internal_name": cast.display_name,
        "published_name": published,
        "icon_url": icon,
        "spawns": cast.spawns,
        "kinds": list(cast.kinds),
        "pawns": list(cast.pawns),
        "has_track": cast.has_track,
        "travel_uu": distance,
        "travel_note": None if distance is not None else NO_POSITION,
    }


def sections(replay: Replay, cache: ArtCache | None) -> list[dict]:
    """The provenance account, heading by heading."""
    return [
        {
            "title": section.title,
            "label_width": section.label_width,
            "entries": [
                {"label": e.label, "value": e.value, "bare": e.bare}
                for e in section.entries
            ],
        }
        for section in provenance_mod.sections(replay, cache).sections
    ]


def replay_doc(replay: Replay, replay_id: str, cache: ArtCache | None) -> dict:
    """
    Everything about one replay except the position samples.

    The samples are a separate request because they are three orders of
    magnitude larger and because a replay is worth showing before they arrive.
    What stays here is `position_source`: whether a decode happened, and what
    it found, is a fact about this replay and not about a download.
    """
    art = cache.map_art(replay.map_path) if cache else None
    return {
        "id": replay_id,
        "source": replay.source,
        "match_id": replay.match_id,
        "build": replay.build,
        "recorded_utc": replay.recorded_utc,
        "length_ms": replay.length_ms,
        "side_swap_ms": replay.side_swap_ms,
        "map_path": replay.map_path,
        "map_name": replay.map_name,
        "map_name_source": replay.map_name_source,
        "map_key": art.name if art else "",
        "players": [player(p, cache) for p in replay.players],
        "rounds": [
            {
                "number": r.number,
                "index": r.index,
                "start_ms": r.start_ms,
                "end_ms": r.end_ms,
                "duration_ms": r.duration_ms,
                "winner": r.winner,
                "reason": r.reason,
                "decided": r.decided,
            }
            for r in replay.rounds
        ],
        "kills": [
            {
                "t_ms": k.t_ms,
                "killer": k.killer,
                "victim": k.victim,
                "round_no": k.round_no,
                "is_suicide": k.is_suicide,
            }
            for k in replay.kills
        ],
        "ultimates": [
            {"t_ms": u.t_ms, "actor_id": u.actor_id, "round_no": u.round_no}
            for u in replay.ultimates
        ],
        "spike": [
            {"t_ms": s.t_ms, "kind": s.kind, "round_no": s.round_no}
            for s in replay.spike
        ],
        "loadouts": [loadout(x, cache) for x in replay.loadouts],
        "ability_casts": [ability_cast(c, replay, cache) for c in replay.ability_casts],
        "event_times": list(replay.event_times),
        "score": list(replay.score),
        "has_positions": replay.has_positions,
        "has_abilities": replay.has_abilities,
        # Prose, and shown verbatim.  `attach` never raises for want of
        # positions; it says what happened here instead.
        "position_source": replay.position_source,
        "catalog_source": replay.catalog_source,
        "notes": list(replay.notes),
        "catalog_notes": list(replay.catalog_notes),
        "provenance": sections(replay, cache),
    }


def card(entry, replay_id: str, cache: ArtCache | None, prewarm: dict | None) -> dict:
    """
    One row of the match list, as the scanner describes it.

    `result` is `scan.RESULT_NOT_IN_FILE` for every capture and always will be:
    the WIN/LOSS badge needs a local player, and a replay has none.  It is sent
    rather than omitted so the interface shows the sentence instead of quietly
    leaving a gap where a verdict should be.
    """
    art = cache.map_art(entry.map_path) if cache else None
    return {
        "id": replay_id,
        "file_name": entry.file_name,
        "match_id": entry.match_id,
        "map_path": entry.map_path,
        "map_name": entry.map_name,
        "map_key": art.name if art else "",
        "listview_url": asset_url(art.listview, cache.root) if art and cache else None,
        "recorded_utc": entry.recorded_utc.isoformat() if entry.recorded_utc else None,
        "recorded": entry.recorded,
        "length_ms": entry.length_ms,
        "duration": entry.duration,
        "rounds": entry.rounds,
        "players": entry.players,
        "build": entry.build,
        "size_bytes": entry.size_bytes,
        "error": entry.error,
        "readable": entry.readable,
        "positions_available": entry.positions_available,
        "positions_note": entry.positions_note,
        "playable": entry.playable,
        "result": entry.result,
        "prewarm": prewarm,
    }
