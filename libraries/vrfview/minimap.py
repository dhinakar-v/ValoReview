"""
The centre canvas when positions decoded: agents on Riot's own minimap.

This is the view the whole decode exists for.  It draws `minimap.png` from the
art cache and puts every player where the replication stream said they were,
through `art.Transform.apply` -- the same transform `mapref` uses for callouts,
measured against all 346 of them rather than assumed, x/y swap included.

What it will and will not draw
------------------------------
* A player with a live position is a filled dot in its team's colour, with a
  facing line from the decoded yaw.
* A player who has died is pinned at the coordinate they died on, drawn hollow
  and dimmed.  `Snapshot.position_of` does that fallback; this module only has
  to draw the two differently, because a corpse shown as a live dot is a lie
  about where five people are.
* A player with **no** position at this instant -- no sample within
  `Track`'s hold window -- is not drawn at all.  There is no last-known-place
  guess here: `Track.at` already refused, and inventing a dot downstream of a
  refusal is exactly what that refusal exists to prevent.

Interchangeable with the schematic
----------------------------------
`SceneView` and `MinimapView` present the same three things -- `widget`,
`render(snapshot)` and `on_hover` -- so the viewer swaps one for the other on
`replay.has_positions` and nothing else changes.  Each says what it is in its
own corner: the schematic keeps its SCHEMATIC watermark, and this one names
the map and the fact that positions were decoded.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import TYPE_CHECKING

from vrfview import theme
from vrfview.model import Position

if TYPE_CHECKING:
    from vrfview.art import MapArt
    from vrfview.images import ImageCache
    from vrfview.model import Player, Replay
    from vrfview.state import Snapshot

DOT_RADIUS = 7
DEAD_RADIUS = 5
FACING_LENGTH = 16

# How far ahead the facing probe is placed, in Unreal units.  Any distance
# works -- the line is renormalised to FACING_LENGTH pixels -- so this is only
# large enough to survive the transform's float precision.
FACING_PROBE_UU = 100.0

# The minimap is square; this is the largest square the canvas can hold, less a
# margin so a dot on the very edge of the map is not clipped by the border.
MARGIN = 10

LABEL_FONT = ("Arial", 8, "bold")
NOTE_FONT = ("Arial", 9)


class MinimapView:
    """Riot's minimap, with the decoded positions drawn on it."""

    def __init__(
        self,
        master: tk.Misc,
        replay: Replay,
        map_art: MapArt,
        images: ImageCache,
    ) -> None:
        self.replay = replay
        self.map_art = map_art
        self.images = images
        self.canvas = tk.Canvas(
            master,
            bg=theme.APP_BG,
            highlightthickness=0,
            bd=0,
        )
        self.on_hover = None

        self._size = (0, 0)
        self._image = None
        self._image_item: int | None = None
        self._box = (0.0, 0.0, 0.0, 0.0)
        self._items: list[int] = []
        self._hit: list[tuple[float, float, Player]] = []
        self._hovered: int | None = None
        self._last: Snapshot | None = None

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(None))

    @property
    def widget(self) -> tk.Canvas:
        return self.canvas

    def set_layer(self, name: str, *, on: bool) -> None:
        """Accepted and ignored: the map has no optional layers yet."""

    # -- geometry --------------------------------------------------------
    def _on_configure(self, event: tk.Event) -> None:
        size = (event.width, event.height)
        if size == self._size:
            return
        self._size = size
        self._place_image()
        if self._last is not None:
            self.render(self._last)

    def _place_image(self) -> None:
        """Fit the square minimap into the canvas and remember where it went."""
        width, height = self._size
        side = max(64, min(width, height) - 2 * MARGIN)
        left = (width - side) / 2
        top = (height - side) / 2
        self._box = (left, top, side, side)

        self.canvas.delete("background")
        self._image = self.images.photo(self.map_art.minimap, (side, side))
        if self._image is not None:
            self._image_item = self.canvas.create_image(
                left,
                top,
                image=self._image,
                anchor="nw",
                tags="background",
            )
        self.canvas.create_rectangle(
            left,
            top,
            left + side,
            top + side,
            outline=theme.BORDER,
            tags="background",
        )
        self.canvas.create_text(
            left + 8,
            top + 8,
            anchor="nw",
            text=f"{self.replay.map_name.upper()}  ·  POSITIONS DECODED",
            fill=theme.TEXT_MUTED,
            font=NOTE_FONT,
            tags="background",
        )

    def to_pixels(self, position: Position) -> tuple[float, float]:
        """One world coordinate as a canvas point, through the map transform."""
        left, top, width, height = self._box
        u, v = self.map_art.transform.apply(position.x, position.y)
        return left + u * width, top + v * height

    # -- drawing ---------------------------------------------------------
    def render(self, snap: Snapshot) -> None:
        """Redraw every player from scratch.  Ten dots; diffing would be noise."""
        self._last = snap
        for item in self._items:
            self.canvas.delete(item)
        self._items.clear()
        self._hit.clear()
        if self._box[2] <= 0:
            return

        for player in self.replay.players:
            position = snap.position_of(player.actor_id)
            if position is None:
                continue
            alive = snap.is_alive(player.actor_id)
            self._draw_player(player, position, alive=alive)

    def _draw_player(self, player: Player, position: Position, *, alive: bool) -> None:
        x, y = self.to_pixels(position)
        colour = theme.team_colour(player.team)
        hovered = self._hovered == player.actor_id

        if alive:
            radius = DOT_RADIUS
            self._items.append(
                self.canvas.create_oval(
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                    fill=colour,
                    outline=theme.APP_BG if not hovered else theme.TEXT_PRIMARY,
                    width=2,
                ),
            )
            self._draw_facing(x, y, position, colour)
        else:
            radius = DEAD_RADIUS
            faded = theme.blend(colour, theme.APP_BG, 0.55)
            self._items.append(
                self.canvas.create_oval(
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                    outline=faded,
                    width=2,
                ),
            )
            # A cross, so a corpse is legible as one at a glance and not just
            # as a slightly different dot.
            for dx, dy in ((-1, -1), (-1, 1)):
                self._items.append(
                    self.canvas.create_line(
                        x + dx * radius,
                        y + dy * radius,
                        x - dx * radius,
                        y - dy * radius,
                        fill=faded,
                    ),
                )

        self._items.append(
            self.canvas.create_text(
                x,
                y - DOT_RADIUS - 8,
                text=player.label,
                fill=theme.TEXT_PRIMARY if alive else theme.TEXT_MUTED,
                font=LABEL_FONT,
            ),
        )
        self._hit.append((x, y, player))

    def _draw_facing(self, x: float, y: float, position: Position, colour: str) -> None:
        """
        A short line the way the player was looking.

        The direction is not computed from the yaw in screen space -- it is a
        second world point, one metre ahead along the yaw, pushed through the
        same `Transform.apply` and subtracted.  That is the only form immune to
        the transform's axis swap and to the sign of either multiplier: get
        those wrong by hand and every player faces ninety degrees off, which
        looks plausible enough to ship.
        """
        radians = math.radians(position.yaw)
        ahead = Position(
            t_ms=position.t_ms,
            actor_id=position.actor_id,
            x=position.x + FACING_PROBE_UU * math.cos(radians),
            y=position.y + FACING_PROBE_UU * math.sin(radians),
            z=position.z,
        )
        tip_x, tip_y = self.to_pixels(ahead)
        dx, dy = tip_x - x, tip_y - y
        length = math.hypot(dx, dy)
        if length <= 0:
            return
        scale = FACING_LENGTH / length
        self._items.append(
            self.canvas.create_line(
                x,
                y,
                x + dx * scale,
                y + dy * scale,
                fill=colour,
                width=2,
            ),
        )

    # -- hover -----------------------------------------------------------
    def _on_motion(self, event: tk.Event) -> None:
        found = None
        for x, y, player in self._hit:
            if (event.x - x) ** 2 + (event.y - y) ** 2 <= (DOT_RADIUS + 4) ** 2:
                found = player
                break
        self._set_hover(found)

    def _set_hover(self, player: Player | None) -> None:
        actor_id = player.actor_id if player is not None else None
        if actor_id == self._hovered:
            return
        self._hovered = actor_id
        if self.on_hover is not None:
            self.on_hover(player)
        if self._last is not None:
            self.render(self._last)
