"""
The centre canvas: agents on Riot's own minimap, where they actually were.

This is the view the whole decode exists for, and since the schematic was
removed it is the only one.  It draws `minimap.png` from the art cache and puts
every player where the replication stream said they were, through
`art.Transform.apply` -- the same transform `mapref` uses for callouts,
measured against all 346 of them rather than assumed, x/y swap included.

What it will and will not draw
------------------------------
* A player with a live position is their **agent's own portrait**, masked to a
  circle inside a ring in their team's colour, with a facing line from the
  decoded yaw.  Where the art cache has no icon for that agent -- a fresh
  checkout, `--no-art`, an agent the manifest predates -- it is a filled dot in
  the team colour instead, which is what this drew before and is visibly a
  marker rather than a portrait that failed.
* A player who has died is pinned at the coordinate they died on and marked
  with the `death` glyph.  `Snapshot.position_of` does that fallback; this
  module only has to draw the two differently, because a corpse shown as a live
  agent is a lie about where five people are.
* A player with **no** position at this instant -- no sample within `Track`'s
  hold window -- is not drawn at all.  There is no last-known-place guess here:
  `Track.at` already refused, and inventing a dot downstream of a refusal is
  exactly what that refusal exists to prevent.

Two optional layers, both off unless asked for
----------------------------------------------
`sight` draws the approximate view cone of the selected player, raycast against
the radar's own silhouette by `vrfview.sight`.  It is **not** a line-of-sight
computation -- this project has no collision data at all -- and the caption
under the canvas says so in those words.  It is drawn for one player at a time
because ten overlapping wedges say nothing, and because the claim is weak
enough that it should be asked for deliberately.

`abilities` draws the ability pawns a cast spawned, and the path each one
travelled.  Only `Pawn_` actors appear, because they are the only ability
actors that emit a movement record; a smoke or a thrown projectile has a time
and an identity and no coordinate anywhere in the file, so nothing is drawn for
it here and the abilities window says as much in words.

Selection
---------
Hovering a player previews their cone; clicking pins them, so the cone stays
while the mouse goes elsewhere.  Clicking the same player again unpins.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import TYPE_CHECKING

from vrfview import abilities as ability_paths
from vrfview import icons, sight, theme
from vrfview.images import CIRCLE
from vrfview.model import Position

if TYPE_CHECKING:
    from vrfview.art import MapArt
    from vrfview.images import Visuals
    from vrfview.model import Player, Replay
    from vrfview.state import Snapshot

DOT_RADIUS = 7
DEAD_RADIUS = 5
AVATAR_PX = 26
DEATH_PX = 18
FACING_LENGTH = 16

# How far ahead the facing probe is placed, in Unreal units.  Any distance
# works -- the line is renormalised to FACING_LENGTH pixels -- so this is only
# large enough to survive the transform's float precision.
FACING_PROBE_UU = 100.0

# The minimap is square; this is the largest square the canvas can hold, less a
# margin so a dot on the very edge of the map is not clipped by the border.
MARGIN = 10

# An ability pawn's marker, and how far back along its path is drawn.
PAWN_HALF = 5
PAWN_TRAIL_MS = 20000

LAYER_SIGHT = "sight"
LAYER_ABILITIES = "abilities"

# A polygon needs three corners, and a polyline two points -- four floats,
# because both are flattened into (x, y) pairs for the canvas.
MIN_POLYGON_POINTS = 3
MIN_LINE_FLOATS = 4
# Two samples is the fewest that can describe having gone anywhere.
MIN_TRAIL_SAMPLES = 2

LABEL_FONT = ("Arial", 8, "bold")
NOTE_FONT = ("Arial", 9)
MISSING_FONT = ("Arial", 11)

SIGHT_CAPTION = (
    "SIGHT (approx) — the radar silhouette, not collision. 2D only: it ignores "
    "heaven, tunnels and anything you can see over."
)

NO_ART = "No radar image for {name}."


class MissingArtView:
    """
    What the centre shows when there is no radar image to draw on.

    Deliberately not a fallback picture of any kind.  The schematic used to
    stand here and was removed because a diagram in the place a map goes reads
    as a map; a sentence naming the missing file cannot be misread as one.
    """

    def __init__(self, master: tk.Misc, replay: Replay, hint: str = "") -> None:
        self.replay = replay
        self.hint = hint
        self.canvas = tk.Canvas(master, bg=theme.APP_BG, highlightthickness=0, bd=0)
        self.on_hover = None
        self.canvas.bind("<Configure>", lambda _e: self._draw())

    @property
    def widget(self) -> tk.Canvas:
        return self.canvas

    def set_layer(self, name: str, *, on: bool) -> None:
        """Accepted and ignored: there is no canvas here to put a layer on."""

    def render(self, snap: Snapshot) -> None:
        """Nothing here changes with time."""

    def _draw(self) -> None:
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self.canvas.create_text(
            width / 2,
            height / 2,
            width=max(200, width - 80),
            justify="center",
            text=NO_ART.format(name=self.replay.map_name or self.replay.map_path)
            + ("\n\n" + self.hint if self.hint else ""),
            fill=theme.TEXT_MUTED,
            font=MISSING_FONT,
        )


class MinimapView:
    """Riot's minimap, with the decoded positions drawn on it."""

    def __init__(
        self,
        master: tk.Misc,
        replay: Replay,
        map_art: MapArt,
        visuals: Visuals,
    ) -> None:
        self.replay = replay
        self.map_art = map_art
        self.visuals = visuals
        self.images = visuals.images
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
        self._pinned: int | None = None
        self._last: Snapshot | None = None
        self._layers = {LAYER_SIGHT: False, LAYER_ABILITIES: True}
        self._sight = sight.SightCache(visuals.images)
        # Codename -> the player who is that agent, for attributing a cast to a
        # team.  `abilities.attribute` refuses a codename two players share
        # rather than picking one, so an ambiguous cast simply has no colour.
        self._by_codename = ability_paths.attribute(replay.players).by_codename

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(None))

    @property
    def widget(self) -> tk.Canvas:
        return self.canvas

    @property
    def selected(self) -> int | None:
        """The pinned player, else whichever one the mouse is over."""
        return self._pinned if self._pinned is not None else self._hovered

    def set_layer(self, name: str, *, on: bool) -> None:
        """Turn one optional layer on or off and redraw at once."""
        if name not in self._layers:
            return
        self._layers[name] = on
        if self._last is not None:
            self.render(self._last)

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

    def uv_to_pixels(self, u: float, v: float) -> tuple[float, float]:
        """A uv fraction of the radar as a canvas point.  The sight layer's unit."""
        left, top, width, height = self._box
        return left + u * width, top + v * height

    # -- drawing ---------------------------------------------------------
    def render(self, snap: Snapshot) -> None:
        """
        Redraw everything from scratch.

        Ten dots and a handful of pawns; diffing would be noise.  The order is
        the z-order: the cone is a wash under everything, then ability paths,
        then the players on top, because a player hidden behind their own
        utility is the one thing on this canvas nobody can afford to lose.
        """
        self._last = snap
        for item in self._items:
            self.canvas.delete(item)
        self._items.clear()
        self._hit.clear()
        if self._box[2] <= 0:
            return

        if self._layers[LAYER_SIGHT]:
            self._draw_sight(snap)
        if self._layers[LAYER_ABILITIES]:
            self._draw_abilities(snap)

        for player in self.replay.players:
            position = snap.position_of(player.actor_id)
            if position is None:
                continue
            alive = snap.is_alive(player.actor_id)
            self._draw_player(player, position, alive=alive)

    # -- the sight layer -------------------------------------------------
    def _draw_sight(self, snap: Snapshot) -> None:
        """
        The selected player's approximate view cone.

        Everything about this is an approximation and the caption says so; what
        it must not be is *wrong about which way they are looking*, so the
        heading goes through `sight.forward_uv`, which probes a world point and
        transforms it rather than doing trigonometry in image space.
        """
        actor_id = self.selected
        if actor_id is None or not snap.is_alive(actor_id):
            return
        position = snap.positions.get(actor_id)
        if position is None:
            return
        silhouette = self._sight.get(self.map_art.minimap)
        if silhouette is None:
            return

        transform = self.map_art.transform
        polygon = sight.cone(
            silhouette,
            transform.apply(position.x, position.y),
            sight.forward_uv(transform, position.x, position.y, position.yaw),
            sight.uv_radius(transform, sight.MAX_RANGE_UU),
        )
        if len(polygon) < MIN_POLYGON_POINTS:
            return

        player = self.replay.player(actor_id)
        colour = theme.team_colour(player.team if player else "?")
        points = [c for u, v in polygon for c in self.uv_to_pixels(u, v)]
        # A Tk canvas has no alpha fill, so a stipple is how a wash is drawn.
        self._items.append(
            self.canvas.create_polygon(
                *points,
                fill=colour,
                outline=theme.blend(colour, theme.APP_BG, 0.35),
                stipple="gray25",
            ),
        )

    # -- the abilities layer ---------------------------------------------
    def _draw_abilities(self, snap: Snapshot) -> None:
        """Ability pawns, and the path each one has travelled so far."""
        for cast in snap.round_casts:
            colour = self._cast_colour(cast)
            for actor_id in cast.pawns:
                here = snap.ability_positions.get(actor_id)
                if here is None:
                    continue
                self._draw_pawn_trail(actor_id, snap.t_ms, colour)
                self._draw_pawn(here, cast, colour)

    def _cast_colour(self, cast) -> str:
        """The casting team's colour, or the neutral one where it is unknown."""
        actor_id = self._by_codename.get(cast.codename)
        player = self.replay.player(actor_id) if actor_id is not None else None
        return theme.team_colour(player.team if player else "?")

    def _draw_pawn_trail(self, actor_id: int, t_ms: int, colour: str) -> None:
        """
        Where this pawn has been, over the last few seconds.

        Only the samples the track actually holds are joined, and only ones
        already in the past: drawing the whole track would show a drone
        arriving somewhere before it got there.
        """
        track = self.replay.ability_tracks.get(actor_id)
        if track is None or len(track) < MIN_TRAIL_SAMPLES:
            return
        points: list[float] = []
        for sample in track.samples:
            if sample.t_ms > t_ms or sample.t_ms < t_ms - PAWN_TRAIL_MS:
                continue
            points.extend(self.to_pixels(sample))
        if len(points) < MIN_LINE_FLOATS:
            return
        self._items.append(
            self.canvas.create_line(
                *points,
                fill=theme.blend(colour, theme.APP_BG, 0.5),
                width=2,
            ),
        )

    def _draw_pawn(self, position: Position, cast, colour: str) -> None:
        """
        One ability pawn, as a square so it is never mistaken for a player.

        The shape carries the meaning here: circles are people, squares are
        utility, and at this size that difference has to survive being glanced
        at rather than read.
        """
        x, y = self.to_pixels(position)
        self._items.append(
            self.canvas.create_rectangle(
                x - PAWN_HALF,
                y - PAWN_HALF,
                x + PAWN_HALF,
                y + PAWN_HALF,
                fill=colour,
                outline=theme.APP_BG,
            ),
        )
        self._items.append(
            self.canvas.create_text(
                x,
                y + PAWN_HALF + 7,
                text=f"{cast.slot} {cast.name}",
                fill=theme.TEXT_MUTED,
                font=LABEL_FONT,
            ),
        )

    # -- players ---------------------------------------------------------
    def _draw_player(self, player: Player, position: Position, *, alive: bool) -> None:
        x, y = self.to_pixels(position)
        colour = theme.team_colour(player.team)
        selected = self.selected == player.actor_id

        if alive:
            self._draw_alive(player, position, (x, y), colour, selected=selected)
        else:
            self._draw_dead(x, y, colour)

        self._items.append(
            self.canvas.create_text(
                x,
                y - AVATAR_PX / 2 - 7,
                text=player.label,
                fill=theme.TEXT_PRIMARY if alive else theme.TEXT_MUTED,
                font=LABEL_FONT,
            ),
        )
        self._hit.append((x, y, player))

    def _draw_alive(
        self,
        player: Player,
        position: Position,
        point: tuple[float, float],
        colour: str,
        *,
        selected: bool,
    ) -> None:
        """The agent's face in a team-coloured ring, or a plain dot without art."""
        x, y = point
        self._draw_facing(x, y, position, colour)
        entry = self.visuals.art.agent_art_by_name(player.agent)
        avatar = self.images.photo(
            entry.icon if entry is not None else None,
            (AVATAR_PX, AVATAR_PX),
            CIRCLE,
        )
        radius = AVATAR_PX / 2 if avatar is not None else DOT_RADIUS
        ring = theme.TEXT_PRIMARY if selected else colour
        if avatar is not None:
            # The ring is drawn first and slightly proud of the portrait, so
            # the team colour survives an agent icon with a pale border.
            self._items.append(
                self.canvas.create_oval(
                    x - radius - 2,
                    y - radius - 2,
                    x + radius + 2,
                    y + radius + 2,
                    fill=colour,
                    outline=ring,
                    width=2,
                ),
            )
            self._items.append(self.canvas.create_image(x, y, image=avatar))
            return
        self._items.append(
            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=colour,
                outline=theme.APP_BG if not selected else theme.TEXT_PRIMARY,
                width=2,
            ),
        )

    def _draw_dead(self, x: float, y: float, colour: str) -> None:
        """The death glyph, or the crossed lines it replaced."""
        faded = theme.blend(colour, theme.APP_BG, 0.55)
        glyph = self.images.photo(icons.path_for("death"), (DEATH_PX, DEATH_PX))
        if glyph is not None:
            self._items.append(self.canvas.create_image(x, y, image=glyph))
            return
        self._items.append(
            self.canvas.create_oval(
                x - DEAD_RADIUS,
                y - DEAD_RADIUS,
                x + DEAD_RADIUS,
                y + DEAD_RADIUS,
                outline=faded,
                width=2,
            ),
        )
        for dx, dy in ((-1, -1), (-1, 1)):
            self._items.append(
                self.canvas.create_line(
                    x + dx * DEAD_RADIUS,
                    y + dy * DEAD_RADIUS,
                    x - dx * DEAD_RADIUS,
                    y - dy * DEAD_RADIUS,
                    fill=faded,
                ),
            )

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
        scale = (AVATAR_PX / 2 + FACING_LENGTH) / length
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

    # -- hover and selection ---------------------------------------------
    def _at(self, event: tk.Event) -> Player | None:
        reach = (AVATAR_PX / 2 + 4) ** 2
        for x, y, player in self._hit:
            if (event.x - x) ** 2 + (event.y - y) ** 2 <= reach:
                return player
        return None

    def _on_motion(self, event: tk.Event) -> None:
        self._set_hover(self._at(event))

    def _on_click(self, event: tk.Event) -> None:
        """Pin a player so their cone survives the mouse moving away."""
        player = self._at(event)
        actor_id = player.actor_id if player is not None else None
        self._pinned = None if actor_id == self._pinned else actor_id
        if self._last is not None:
            self.render(self._last)

    def _set_hover(self, player: Player | None) -> None:
        actor_id = player.actor_id if player is not None else None
        if actor_id == self._hovered:
            return
        self._hovered = actor_id
        if self.on_hover is not None:
            self.on_hover(player)
        if self._last is not None:
            self.render(self._last)
