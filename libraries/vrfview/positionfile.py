"""
The positions sidecar: decoded tracks, on disk, next to a JSON dump.

Decoding positions costs an Oodle DLL and about four minutes on a full match.
The JSON path exists so that neither is needed twice, so `vrf-to-json` can
write what it decoded and `vrfview.tracks` can read it back on a machine with
no DLL at all.

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
One JSON object.  Samples are stored columnar -- six equal-length arrays per
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
VERSION = 1
SUFFIX = ".positions.json"

# The order the columns are written in, and the order Position takes them.
COLUMNS = ("t", "x", "y", "z", "yaw", "pitch")


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

    @property
    def samples(self) -> int:
        return sum(len(t) for t in self.positions.values())


def sidecar_path(dump_path: str | Path) -> Path:
    """The sidecar that belongs to a dump: `out.json` -> `out.positions.json`."""
    path = Path(dump_path)
    return path.with_name(path.stem + SUFFIX)


def write(path: str | Path, sidecar: Sidecar) -> Path:
    """Write one sidecar, and return where it went."""
    out = Path(path)
    doc = {
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
            str(actor_id): _columns(track)
            for actor_id, track in sorted(sidecar.positions.items())
        },
    }
    with out.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)
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
    if doc.get("version") != VERSION:
        msg = f"{src}: sidecar version {doc.get('version')!r}, expected {VERSION}"
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
    return Sidecar(
        positions=positions,
        codenames=codenames,
        description=str(doc.get("position_source") or ""),
        match_id=str(doc.get("match_id") or ""),
        build=str(doc.get("build") or ""),
        hz=int(doc.get("hz") or POSITION_HZ),
    )


def _columns(track: Track) -> dict[str, list]:
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
