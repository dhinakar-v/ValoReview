"""
Where the nodes go.

Pure geometry, no tkinter, so the arrangement can be tested without a display.

There are no real coordinates to honour -- the replication stream's property
payloads are undecoded, so no player position, rotation or map geometry exists
anywhere in this pipeline.  The arrangement here is therefore chosen to be
readable rather than faithful: two arcs facing each other across the field, one
per inferred team, bulging inward so that a kill arrow between them crosses the
middle and reads as a trade rather than as a horizontal line in a list.

Nothing in this module should ever be mistaken for a minimap.  The scene draws
an explicit "schematic - not map positions" caption for that reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vrfview.model import TEAM_A, TEAM_B, Replay

MIN_RADIUS = 12
MAX_RADIUS = 34


@dataclass
class Layout:
    """Node centres by actor ID, plus the field box they were placed in."""

    positions: dict[int, tuple[float, float]] = field(default_factory=dict)
    radius: float = MIN_RADIUS
    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    def of(self, actor_id: int) -> tuple[float, float] | None:
        return self.positions.get(actor_id)


@dataclass(frozen=True)
class Framing:
    """
    How much of the canvas the field keeps clear, and how far it bulges.

    All three are fractions of the canvas, so a layout looks the same at any
    window size.  They travel together because changing one without the others
    is never what you want.
    """

    pad_x: float = 0.16
    pad_y: float = 0.14
    arc: float = 0.10


DEFAULT_FRAMING = Framing()


def compute(
    replay: Replay,
    width: float,
    height: float,
    framing: Framing = DEFAULT_FRAMING,
) -> Layout:
    """Place each team on an inward-bulging arc inside the given box."""
    left = width * framing.pad_x
    right = width * (1 - framing.pad_x)
    top = height * framing.pad_y
    bottom = height * (1 - framing.pad_y)

    team_a = [p.actor_id for p in replay.team(TEAM_A)]
    team_b = [p.actor_id for p in replay.team(TEAM_B)]
    rest = [
        p.actor_id
        for p in replay.players
        if p.actor_id not in team_a and p.actor_id not in team_b
    ]
    # With no team split at all, show one column rather than an empty field.
    if not team_a and not team_b:
        team_a, rest = rest, []

    biggest = max(len(team_a), len(team_b), len(rest), 1)
    span = max(bottom - top, 1.0)
    radius = max(MIN_RADIUS, min(MAX_RADIUS, span / (biggest * 2.6)))

    layout = Layout(radius=radius, left=left, top=top, right=right, bottom=bottom)
    depth = width * framing.arc
    _place(layout, team_a, left, depth, +1)
    _place(layout, team_b, right, depth, -1)
    if rest:
        _place(layout, rest, (left + right) / 2, 0.0, +1)
    return layout


def _place(
    layout: Layout,
    actors: list[int],
    x: float,
    depth: float,
    direction: int,
) -> None:
    """
    Spread actors down an arc at `x`, bulging by `depth` toward `direction`.

    The vertical span comes from the layout itself, which already holds the
    padded box every column is drawn inside.
    """
    if not actors:
        return
    n = len(actors)
    for i, actor_id in enumerate(actors):
        frac = (i + 0.5) / n
        y = layout.top + frac * (layout.bottom - layout.top)
        bulge = math.sin(frac * math.pi) * depth
        layout.positions[actor_id] = (x + direction * bulge, y)
