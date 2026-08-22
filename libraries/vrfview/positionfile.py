"""
The positions sidecar: decoded tracks, on disk, next to a JSON dump.

Decoding positions costs a built decoder and a few seconds on a full match.
The JSON path exists so that neither is needed twice, so `vrf-to-json` can
write what it decoded and `vrfview.tracks` can read it back on a machine with
no .NET SDK and no clone at all.

Why a sidecar and not the dump itself
-------------------------------------
199,180 samples is roughly 12 MB against the dump's ~5 MB, and the dump is
already the thing a human opens to look at a chunk table.  More importantly,
`tests/test_vrfview.py` asserts that the `.vrf` and JSON paths build *equal*
Replays -- that equality is what makes the two inputs interchangeable, and it
holds precisely because `loader` reads only what the container states.  Putting
positions inside the dump would have made the JSON path carry something the
`.vrf` path does not, and the honest fix would have been to weaken the test.
A separate file keeps both: `loader.load` is unchanged, and positions stay what
they have always been -- opt-in, attached by `tracks.attach`, and described in
`Replay.position_source` whether they arrived by decode or by sidecar.

The format
----------
One JSON object.  Version 2 added the ability actors and version 3 the
coordinate each one spawned at; version 1 and 2 files are still read, and
simply have less.  Samples are stored columnar -- six equal-length arrays per
actor rather than a dict per sample -- which is about a third of the bytes and
costs nothing in clarity, since a sample is six numbers and always the same
six.  Floats are written at full precision: json round-trips a double exactly,
so a Replay built from a sidecar equals one built by decoding, and a test can
assert that rather than an approximation of it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from vrfview.model import POSITION_HZ, Position, Track

FORMAT = "vrf-positions"
VERSION = 4
# Every version this module can still read.  A v1 file is a real sidecar
# written by `vrf-to-json --positions` before abilities were decoded, and it is
# not wrong -- it simply says nothing about them.  A v2 file predates the spawn
# transform being measured, so its casts have a time and no coordinate, which
# is exactly the state the whole project was in when it was written.  A v3 file
# predates the spike plant being measured, so its plants have a time and no
# coordinate -- again exactly the state the project was in.  Refusing any of
# them would throw away a whole decode over a field it was never asked to
# carry.
READABLE = (1, 2, 3, 4)
SUFFIX = ".positions.json"

# The order the columns are written in, and the order Position takes them.
COLUMNS = ("t", "x", "y", "z", "yaw", "pitch")

# An ability spawn is stored as [archetype path, milliseconds], and since
# version 3 as [archetype path, milliseconds, x, y, z] where the decoder read
# a spawn transform for it.  Both lengths are read; the short one is a spawn
# whose coordinate is genuinely unknown, not a defaulted zero.
_SPAWN_FIELDS = 2
_SPAWN_FIELDS_LOCATED = 5

# A plant is [t_ms, x, y, z] or it is not stored at all.
_PLANT_FIELDS = 4


class PositionFileError(Exception):
    """A sidecar that is absent, unreadable, or not a sidecar at all."""


@dataclass(frozen=True)
class Sidecar:
    """What one sidecar states, in the shape `tracks.attach` needs it."""

    positions: dict[int, Track] = field(default_factory=dict)
    codenames: dict[int, str] = field(default_factory=dict)
    description: str = ""
    match_id: str = ""
    build: str = ""
    hz: int = POSITION_HZ
    # Ability actors as they were seen: actor net ID -> (archetype path,
    # spawn time, spawn coordinate or None).  Stored raw rather than as
    # grouped casts on purpose -- a spawn is a fact off the wire, a cast is a
    # reading of several of them, and the reading has already changed twice.
    # Keeping the facts means an improvement to `abilities.casts` takes effect
    # on the next load instead of needing every cached decode thrown away,
    # which is exactly what happened when casts learnt where they landed.
    ability_spawns: dict[int, tuple[str, int, tuple[float, float, float] | None]] = (
        field(default_factory=dict)
    )
    ability_tracks: dict[int, Track] = field(default_factory=dict)
    # Where each spike was planted: (t_ms, x, y, z), one per plant, since
    # version 4.  Stored as coordinates rather than as placed events for the
    # same reason `ability_spawns` is stored raw -- pairing a plant to an event
    # is a reading, and `tracks._place_spike` should get to redo it on every
    # load rather than have an old reading baked into the cache.
    plants: list[tuple[int, float, float, float]] = field(default_factory=list)

    @property
    def samples(self) -> int:
        return sum(len(t) for t in self.positions.values())


def sidecar_path(dump_path: str | Path) -> Path:
    """The sidecar that belongs to a dump: `out.json` -> `out.positions.json`."""
    path = Path(dump_path)
    return path.with_name(path.stem + SUFFIX)


def to_document(sidecar: Sidecar) -> dict:
    """
    One sidecar as the JSON document that represents it.

    Separate from `write` because this document is not only a file any more.
    It is the format positions travel in: to a sidecar beside a dump, to the
    machine cache, and over HTTP to whatever is drawing them.  Having one
    builder means those three can never disagree about what a track looks
    like, and a test can assert an HTTP body is byte-identical to what `write`
    would have produced for the same replay.

    Six parallel arrays per actor rather than a record per sample: about a
    third of the bytes, and the shape a typed array wants at the far end.
    """
    return {
        "format": FORMAT,
        "version": VERSION,
        "match_id": sidecar.match_id,
        "build": sidecar.build,
        "hz": sidecar.hz,
        # The line the decoder wrote about itself.  Kept verbatim so a replay
        # loaded from a sidecar can say what was decoded and by what, months
        # after the machine that had the DLL.
        "position_source": sidecar.description,
        "codenames": {str(k): v for k, v in sorted(sidecar.codenames.items())},
        "tracks": {
            str(actor_id): to_columns(track)
            for actor_id, track in sorted(sidecar.positions.items())
        },
        # Two fields where the spawn transform is unknown and five where it is
        # read.  A short entry is a coordinate nobody has, and writing three
        # zeros for it would put every such actor on the map's origin.
        "ability_spawns": {
            str(actor_id): [path, t_ms, *(location or ())]
            for actor_id, (path, t_ms, location) in sorted(
                sidecar.ability_spawns.items(),
            )
        },
        "ability_tracks": {
            str(actor_id): to_columns(track)
            for actor_id, track in sorted(sidecar.ability_tracks.items())
        },
        # [t_ms, x, y, z] per plant.  A capture whose plants were never located
        # writes an empty list, which is what every v1..v3 file reads back as.
        "spike_plants": [list(plant) for plant in sorted(sidecar.plants)],
    }


def write(path: str | Path, sidecar: Sidecar) -> Path:
    """Write one sidecar, and return where it went."""
    out = Path(path)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(to_document(sidecar), fh, ensure_ascii=False)
    return out


def read(path: str | Path) -> Sidecar:
    """Read one sidecar back, raising PositionFileError on anything malformed."""
    src = Path(path)
    try:
        with src.open(encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        msg = f"{src}: unreadable positions sidecar: {exc}"
        raise PositionFileError(msg) from exc

    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        msg = f"{src}: not a {FORMAT} file"
        raise PositionFileError(msg)
    if doc.get("version") not in READABLE:
        msg = (
            f"{src}: sidecar version {doc.get('version')!r}, expected one of {READABLE}"
        )
        raise PositionFileError(msg)

    positions = {}
    for raw_id, columns in (doc.get("tracks") or {}).items():
        actor_id = _actor_id(src, raw_id)
        positions[actor_id] = Track(
            actor_id=actor_id,
            samples=_samples(src, actor_id, columns),
        )
    codenames = {
        _actor_id(src, raw_id): str(name)
        for raw_id, name in (doc.get("codenames") or {}).items()
    }
    ability_tracks = {}
    for raw_id, columns in (doc.get("ability_tracks") or {}).items():
        actor_id = _actor_id(src, raw_id)
        ability_tracks[actor_id] = Track(
            actor_id=actor_id,
            samples=_samples(src, actor_id, columns),
        )
    return Sidecar(
        positions=positions,
        codenames=codenames,
        description=str(doc.get("position_source") or ""),
        match_id=str(doc.get("match_id") or ""),
        build=str(doc.get("build") or ""),
        hz=int(doc.get("hz") or POSITION_HZ),
        ability_spawns={
            _actor_id(src, raw_id): _spawn(src, raw_id, entry)
            for raw_id, entry in (doc.get("ability_spawns") or {}).items()
        },
        ability_tracks=ability_tracks,
        plants=[
            _plant(src, entry) for entry in (doc.get("spike_plants") or [])
        ],
    )


def _plant(src: Path, entry) -> tuple[int, float, float, float]:
    """
    One stored plant back, or refuse the file.

    Four fields or nothing: unlike an ability spawn there is no short form,
    because a plant with no coordinate is simply absent from the list.
    """
    if not isinstance(entry, (list, tuple)) or len(entry) != _PLANT_FIELDS:
        msg = f"{src}: spike plant {entry!r} is not [t_ms, x, y, z]"
        raise PositionFileError(msg)
    return (int(entry[0]), float(entry[1]), float(entry[2]), float(entry[3]))


def _spawn(
    src: Path,
    raw_id,
    entry,
) -> tuple[str, int, tuple[float, float, float] | None]:
    """One stored ability spawn back, at either length, or refuse the file."""
    if not isinstance(entry, (list, tuple)) or len(entry) not in (
        _SPAWN_FIELDS,
        _SPAWN_FIELDS_LOCATED,
    ):
        msg = f"{src}: ability spawn {raw_id!r} is not [path, t] or [path, t, x, y, z]"
        raise PositionFileError(msg)
    located = len(entry) == _SPAWN_FIELDS_LOCATED
    location = (float(entry[2]), float(entry[3]), float(entry[4])) if located else None
    return (str(entry[0]), int(entry[1]), location)


def to_columns(track: Track) -> dict[str, list]:
    return {
        "t": [p.t_ms for p in track.samples],
        "x": [p.x for p in track.samples],
        "y": [p.y for p in track.samples],
        "z": [p.z for p in track.samples],
        "yaw": [p.yaw for p in track.samples],
        "pitch": [p.pitch for p in track.samples],
    }


def _samples(src: Path, actor_id: int, columns) -> tuple[Position, ...]:
    """Six equal-length columns back into Positions, or refuse the file."""
    if not isinstance(columns, dict) or any(c not in columns for c in COLUMNS):
        msg = f"{src}: actor {actor_id} is missing one of the {len(COLUMNS)} columns"
        raise PositionFileError(msg)
    lengths = {len(columns[c]) for c in COLUMNS}
    if len(lengths) != 1:
        msg = f"{src}: actor {actor_id} has ragged columns {sorted(lengths)}"
        raise PositionFileError(msg)
    return tuple(
        Position(
            t_ms=int(t),
            actor_id=actor_id,
            x=float(x),
            y=float(y),
            z=float(z),
            yaw=float(yaw),
            pitch=float(pitch),
        )
        for t, x, y, z, yaw, pitch in zip(
            *(columns[c] for c in COLUMNS),
            strict=True,
        )
    )


def _actor_id(src: Path, raw: object) -> int:
    try:
        return int(str(raw))
    except ValueError as exc:
        msg = f"{src}: {raw!r} is not an actor net ID"
        raise PositionFileError(msg) from exc
