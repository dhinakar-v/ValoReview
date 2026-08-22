"""
One adapter from either input form to a single Replay.

A .vrf and a JSON dumped by vrf_to_json.py converge here, because both go
through the same vrf_to_json.dump_* functions -- the JSON path just reads back
what the .vrf path computes.  That is what makes the two inputs comparable
field for field, and tests/test_vrfview.py asserts they produce equal Replays.

Why the .vrf path is the fast one
---------------------------------
It needs no Oodle DLL.  Oodle is only required to decompress data blocks, and
the viewer reads none of them: events, both headers and the loadout metadata
all live in plain chunks.  Measured at 0.04s to load the 47 MB reference
capture, against ~5 MB of JSON to parse on the other path.

This module fills in only what the file states.  Teams, round outcomes and the
map's public name are left at their unknown defaults for vrfview.infer to
derive, so that "read from the file" and "inferred by us" never get mixed up in
one place.
"""

from __future__ import annotations

import json
from pathlib import Path

from vrf_reader import VrfError, VrfFile
from vrf_to_json import (
    dump_container_header,
    dump_demo_header,
    dump_events,
    dump_match_metadata,
)
from vrfview.model import (
    Kill,
    Loadout,
    Player,
    Replay,
    Round,
    SpikeEvent,
    Ultimate,
)

# Internal map paths are codenames; the public names are external knowledge and
# are shown as inferred.  This table is the keyless fallback: when a Riot
# content catalogue is available, vrfview.names resolves the same path against
# it instead and says so.  Unknown paths fall back to the leaf of the path.
MAP_NAMES = {
    "Ascent": "Ascent",
    "Bonsai": "Split",
    "Canyon": "Fracture",
    "Duality": "Bind",
    "Foxtrot": "Breeze",
    "Infinity": "Abyss",
    "Jam": "Lotus",
    "Juliett": "Sunset",
    "Pitt": "Pearl",
    "Port": "Icebox",
    "Rook": "Corrode",
    "Triad": "Haven",
}

# characterDeath is (?, killer, victim) and characterUltimateUsed is (?, actor),
# so an event carrying fewer args than this is truncated and cannot be read.
_KILL_ARGS = 3
_ULTIMATE_ARGS = 2

_GROUP_SPIKE = {
    "spikePlanted": "planted",
    "spikeDefused": "defused",
    "spikeExploded": "exploded",
}


# How Replay.map_name was arrived at.  vrfview.names adds its own value when a
# catalogue answers, so the interface never has to guess which one is showing.
MAP_NAME_SOURCE_TABLE = "built-in codename table"
MAP_NAME_SOURCE_LEAF = "raw path leaf (codename not in the built-in table)"


def map_name_for(map_path: str) -> tuple[str, bool]:
    """Public map name for an internal path, and whether it was recognised."""
    leaf = map_path.rstrip("/").rsplit("/", 1)[-1] if map_path else ""
    if leaf in MAP_NAMES:
        return MAP_NAMES[leaf], True
    return leaf or "unknown", False


def load(path: str | Path) -> Replay:
    """Build a Replay from a .vrf or from a vrf_to_json.py JSON dump."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as fh:
            doc = json.load(fh)
        return _from_document(
            source=path,
            container=doc["container_header"],
            demo=doc["demo_header"],
            events=doc["events"],
            metadata=doc.get("match_metadata") or {},
        )
    vrf = VrfFile(path)
    return _from_document(
        source=path,
        container=dump_container_header(vrf),
        demo=dump_demo_header(vrf),
        events=dump_events(vrf),
        metadata=dump_match_metadata(vrf) or {},
    )


def _from_document(
    source: Path,
    container: dict,
    demo: dict,
    events: list,
    metadata: dict,
) -> Replay:
    """Assemble a Replay from the four pieces both input paths produce."""
    maps = demo.get("maps") or []
    map_path = maps[0] if maps else ""
    name, recognised = map_name_for(map_path)

    replay = Replay(
        source=source.name,
        # friendly_name is the match UUID: it equals the file's own stem on all
        # 101 captures surveyed, and is read from the header rather than from
        # the filename so a renamed copy still reports the right match.
        match_id=str(container.get("friendly_name") or ""),
        map_path=map_path,
        map_name=name,
        map_name_source=MAP_NAME_SOURCE_TABLE if recognised else MAP_NAME_SOURCE_LEAF,
        length_ms=int(container.get("length_ms") or 0),
        recorded_utc=str(container.get("recorded_utc") or ""),
        build=str(demo.get("build") or ""),
        loadouts=_loadouts(metadata),
    )
    if not recognised and map_path:
        replay.notes.append(
            f"map codename {map_path!r} is not in the public-name table; "
            "showing the raw path leaf",
        )

    for ev in sorted(events, key=lambda e: e["time2_ms"]):
        group = ev.get("group") or ""
        t = int(ev["time2_ms"])
        args = ev.get("args") or []
        if group == "characterDeath" and len(args) >= _KILL_ARGS:
            replay.kills.append(Kill(t_ms=t, killer=int(args[1]), victim=int(args[2])))
        elif group == "characterUltimateUsed" and len(args) >= _ULTIMATE_ARGS:
            replay.ultimates.append(Ultimate(t_ms=t, actor_id=int(args[1])))
        elif group in _GROUP_SPIKE:
            replay.spike.append(SpikeEvent(t_ms=t, kind=_GROUP_SPIKE[group]))
        elif group == "switchTeams":
            replay.side_swap_ms = t

    replay.players = [
        Player(actor_id=a) for a in sorted(_actor_ids(replay.kills, replay.ultimates))
    ]
    replay.rounds = _rounds(events, replay.length_ms)
    if not replay.rounds:
        msg = f"{source}: no roundStarted events, nothing to play back"
        raise VrfError(msg)
    return replay


def _loadouts(metadata: dict) -> list[Loadout]:
    """
    The roster as the file states it: a subject and an agent UUID per slot.

    Both stay UUIDs here.  Turning `characterId` into an agent name needs Riot's
    catalogue, which is external knowledge and therefore vrfview.names' job.
    """
    return [
        Loadout(
            index=int(p.get("index", i)),
            subject=str(p.get("subject") or ""),
            character_id=str(p.get("characterId") or ""),
        )
        for i, p in enumerate(metadata.get("players") or [])
    ]


def _actor_ids(kills: list, ultimates: list) -> set[int]:
    ids = {k.killer for k in kills} | {k.victim for k in kills}
    return ids | {u.actor_id for u in ultimates}


def _rounds(events: list, length_ms: int) -> list:
    """
    RoundStarted times bound the rounds; the last one closes at the end.

    Round numbers come from `metadata`, not from position, because the
    recording need not start at round 1.
    """
    starts = []
    for ev in events:
        if ev.get("group") != "roundStarted":
            continue
        raw = ev.get("metadata")
        try:
            index = int(raw)
        except (TypeError, ValueError):
            index = len(starts)
        starts.append((int(ev["time2_ms"]), index))
    starts.sort()

    rounds = []
    for i, (start, index) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else max(length_ms, start)
        rounds.append(Round(number=index + 1, index=index, start_ms=start, end_ms=end))
    return rounds
