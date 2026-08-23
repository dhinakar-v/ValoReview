"""
Where each map's round-start spawn barriers stand, looked up rather than read.

A `.vrf` does not state this.  Nothing decoded here does: the barriers are
level geometry that the engine raises during the buy phase and drops at round
start, they replicate no actor this project has ever seen, and
`docs/039f3991_summary.md` §6 lists all seven event groups with nothing among
them that fires when one appears.  So a barrier is external knowledge, in the
shape `abilityfacts` and `names.AGENT_CODENAMES` already set for external
knowledge: a table, offline, consulted rather than fetched.

Unlike those two, though, this table was **measured rather than transcribed**,
and `barrierdecode.py` is the measurement.  Nobody publishes barrier
coordinates, so the figures come off nine screenshots of another replay viewer
that draws them -- `features/map-barriers/` -- aligned onto Riot's own radar by
maximising silhouette overlap.  `docs/map-barriers.md` is that derivation and
carries every number.  **`features/` is gitignored**, which is exactly why this
file is JSON in `libraries/` and not a note beside the pictures: the config is
the only durable record of the reading, and the evidence for it is not in the
tree.

This module holds no image code at all -- no Pillow, no drawing, no rectangles
in pixels until somebody asks for them at a size.  That is deliberate and it is
what lets the server or the browser read the table one day without either of
them growing an image dependency.  `scripts/make_barriers.py` does the drawing
and `barrierdecode` does the reading; both import this and this imports
neither.

The space is uv, and the sides are two
--------------------------------------
A barrier is stored as an axis-aligned rectangle in **uv** -- 0..1 across the
radar image, the same space `sight` marches its rays in and the same space
`art`'s map transform lands in -- so the table says nothing about a resolution
and a 512px render is the same fact as a 1024px one.

`Side` is `attack` or `defence` and never a team.  Which team is attacking
swaps at half time and the barrier does not move, so keying this on A/B would
be wrong for half of every match.  The colours below come from
`theme.TEAM_COLOURS` regardless, because that palette's A and B *are* Valorant's
attacker red and defender blue and a second pair of hex values here would be a
second place the same claim could drift from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vrfview import theme

# The two sides a barrier belongs to.  See the module docstring for why this is
# not a team.
Side = Literal["attack", "defence"]
SIDES: tuple[Side, ...] = ("attack", "defence")

# What each side's barriers are painted in.  Read off `theme` rather than
# written out, so the generated picture agrees with every marker the browser
# draws and there is one palette rather than two.
INK: dict[Side, str] = {
    "attack": theme.TEAM_COLOURS["A"],
    "defence": theme.TEAM_COLOURS["B"],
}

# The committed table.  A sibling of this module rather than a file under
# `assets/` or `features/`, both of which are gitignored in full -- see the
# module docstring.
CONFIG_PATH = Path(__file__).with_name("barriers.json")

# The format the file on disk carries.  Bumped when the shape changes, and read
# back so a future reader refuses an older file rather than silently
# misreading one -- the sidecar rule in `positionfile`, for the same reason.
VERSION = 1


class ConfigError(Exception):
    """The table on disk is missing, unreadable, or not this version."""


@dataclass(frozen=True, slots=True)
class Barrier:
    """
    One barrier: which side it belongs to, and the box it occupies in uv.

    Axis-aligned, because every barrier in the reference frames is: they are
    drawn as flat bars across a doorway and the viewer they came from draws
    them screen-aligned.  A barrier that ran diagonally would need a polygon
    and this would be the wrong shape for it -- so if one ever turns up, the
    honest move is to widen this record rather than to fit a box around it and
    let the box read as measured.
    """

    side: Side
    u0: float
    v0: float
    u1: float
    v1: float

    def rect(self, size: int) -> tuple[int, int, int, int]:
        """
        The box in pixels at a given square render size, as `(x0, y0, x1, y1)`.

        Inclusive of both corners, and **floored to at least one pixel each
        way**.  A barrier is six screenshot pixels thick and lands near five on
        the radar; render one at 256 and the thin axis rounds to nothing, which
        would drop the bar from the picture rather than draw it thin.
        """
        x0, x1 = sorted((self.u0 * size, self.u1 * size))
        y0, y1 = sorted((self.v0 * size, self.v1 * size))
        left, top = int(x0), int(y0)
        return (left, top, max(int(x1), left + 1), max(int(y1), top + 1))


@dataclass(frozen=True, slots=True)
class Fit:
    """
    How the reference frame was placed onto the radar, and how well.

    Kept in the table rather than thrown away with the tool that produced it,
    because it is the only thing that says whether a row is worth believing.
    `iou` is the overlap the winning placement reached and `runner_up` is the
    best of the other seven orientations: the gap between them is the argument
    that the orientation was *found* rather than assumed, and a row where the
    two came out close is a row to re-derive rather than to draw.
    """

    orient: str
    scale: float
    tx: float
    ty: float
    iou: float
    runner_up: str
    runner_up_iou: float

    @property
    def margin(self) -> float:
        """How far the winning orientation beat the next best, as a ratio."""
        return self.iou / self.runner_up_iou if self.runner_up_iou else float("inf")


@dataclass(frozen=True, slots=True)
class MapBarriers:
    """Every barrier on one map, with the placement they were read through."""

    name: str
    reference: str
    fit: Fit
    barriers: tuple[Barrier, ...]

    def side(self, side: Side) -> tuple[Barrier, ...]:
        return tuple(b for b in self.barriers if b.side == side)


def load(path: Path | None = None) -> dict[str, MapBarriers]:
    """
    The table, keyed by the map's display name -- `Ascent`, not `map_url`.

    Display name because that is what a caller has: `/api/maps/Ascent` is
    addressed that way for the reason CLAUDE.md gives, and
    `/Game/Maps/Ascent/Ascent` cannot be a URL segment.  `art.MapArt.name` is
    the same string, so the join is exact rather than fuzzy.

    Raises `ConfigError` rather than returning an empty table when the file is
    missing or the wrong version.  An empty table and an unreadable one would
    render identically -- no barriers anywhere -- and the caller has to be able
    to tell "this map has none recorded" from "the table did not load".
    """
    path = path or CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        message = f"no barrier table at {path}"
        raise ConfigError(message) from exc
    except json.JSONDecodeError as exc:
        message = f"{path} is not readable JSON: {exc}"
        raise ConfigError(message) from exc

    version = raw.get("version")
    if version != VERSION:
        message = f"{path} is version {version!r}, this reads {VERSION}"
        raise ConfigError(message)

    out: dict[str, MapBarriers] = {}
    for name, entry in sorted(raw.get("maps", {}).items()):
        out[name] = MapBarriers(
            name=name,
            reference=entry["reference"],
            fit=Fit(**entry["fit"]),
            barriers=tuple(_barrier(row) for row in entry["barriers"]),
        )
    return out


def _barrier(row: dict) -> Barrier:
    side = row["side"]
    if side not in SIDES:
        message = f"unknown side {side!r}: expected one of {SIDES}"
        raise ConfigError(message)
    u0, v0, u1, v1 = row["rect"]
    return Barrier(side=side, u0=u0, v0=v0, u1=u1, v1=v1)


def dumps(maps: dict[str, MapBarriers]) -> str:
    """
    The table as the file on disk, ready to write.

    One barrier per line rather than pretty-printed over five, because the
    file is read by people as a list of bars and a diff of it should be one
    line per bar that moved.  `json.dumps` cannot do that, so the rows are
    assembled here and the surrounding document is indented normally.
    """
    blocks = []
    for name in sorted(maps):
        entry = maps[name]
        rows = ",\n".join(
            "        "
            + json.dumps(
                {
                    "side": b.side,
                    "rect": [round(v, 6) for v in (b.u0, b.v0, b.u1, b.v1)],
                },
            )
            for b in entry.barriers
        )
        fit = json.dumps(
            {
                "orient": entry.fit.orient,
                "scale": round(entry.fit.scale, 6),
                "tx": round(entry.fit.tx, 3),
                "ty": round(entry.fit.ty, 3),
                "iou": round(entry.fit.iou, 4),
                "runner_up": entry.fit.runner_up,
                "runner_up_iou": round(entry.fit.runner_up_iou, 4),
            },
        )
        blocks.append(
            f"    {json.dumps(name)}: {{\n"
            f'      "reference": {json.dumps(entry.reference)},\n'
            f'      "fit": {fit},\n'
            f'      "barriers": [\n{rows}\n      ]\n'
            f"    }}",
        )
    body = ",\n".join(blocks)
    return f'{{\n  "version": {VERSION},\n  "maps": {{\n{body}\n  }}\n}}\n'
