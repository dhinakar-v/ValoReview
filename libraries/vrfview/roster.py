"""
The roster band: which map, and which agents were in the match.

Static for the whole replay, so it is built once and never touched again.  It
takes no Snapshot and does no work in the 30 fps loop -- the loadout list does
not change with the playhead, and pretending otherwise would put a redraw in
the frame budget for nothing.

Why the agents are a row and not labels on the nodes
----------------------------------------------------
The file states ten loadouts and ten actor net IDs and links them nowhere.  The
property payloads that might are undecoded.  So the agents are shown in the
file's own order, captioned as unattributable, and the scene's player nodes stay
as vrfview.infer labels them -- A1..A5, B1..B5.  Putting Jett's icon on a node
would be an invention with a picture on it, which is worse than one without.
vrfview.names says the same thing at greater length and is the authority.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from vrfview import theme

if TYPE_CHECKING:
    from vrfview.art import ArtCache
    from vrfview.images import ImageCache
    from vrfview.model import Replay

BAND_HEIGHT = 92
PAD_X = 12
PAD_Y = 8

ICON_PX = 64
ROLE_PX = 18
TILE_GAP = 8
TILE_WIDTH = ICON_PX + TILE_GAP

# The map strip is 456x100 natively, which is taller than the band; drawn at
# half size it sits beside the tiles instead of dwarfing them.
MAP_STRIP_PX = 228
MAP_GAP = 16

FONT_MAP = ("Segoe UI Semibold", 13)
FONT_AGENT = ("Segoe UI", 9)
FONT_CAPTION = ("Segoe UI", 8)

CAPTION = "roster order from the file - not attributable to any player"


class RosterBand:
    """Map identity on the left, agent tiles across, caption on the right."""

    def __init__(
        self,
        master: tk.Misc,
        replay: Replay,
        art: ArtCache,
        images: ImageCache,
    ) -> None:
        self.replay = replay
        self.images = images
        self.map_art = art.map_art(replay.map_path)
        self.canvas = tk.Canvas(
            master,
            bg=theme.PANEL,
            height=BAND_HEIGHT,
            highlightthickness=0,
            bd=0,
        )
        self._tiles = [(x, art.agent_art(x.character_id)) for x in replay.loadouts]
        self._build()

    @property
    def widget(self) -> tk.Canvas:
        return self.canvas

    @property
    def useful(self) -> bool:
        """
        Whether this band has anything the rest of the window does not.

        False on a checkout with no art cache, and the app then never grids it,
        so the viewer keeps exactly its previous layout rather than growing an
        empty stripe.
        """
        if self.map_art is not None and self.map_art.listview is not None:
            return True
        return any(entry is not None and entry.icon for _, entry in self._tiles)

    def _build(self) -> None:
        x = PAD_X
        x = self._draw_map(x)
        for loadout, entry in self._tiles:
            x = self._draw_tile(x, loadout, entry)
        self.canvas.create_text(
            x + MAP_GAP,
            BAND_HEIGHT // 2,
            text=CAPTION,
            fill=theme.FAINT,
            font=FONT_CAPTION,
            anchor="w",
            width=190,
        )

    def _draw_map(self, x: int) -> int:
        """The map's menu strip and its name.  Returns the next free x."""
        strip = None if self.map_art is None else self.map_art.listview
        image = self.images.get(strip, MAP_STRIP_PX)
        if image is not None:
            self.canvas.create_image(x, PAD_Y, image=image, anchor="nw")
            self.canvas.create_text(
                x + image.width() // 2,
                BAND_HEIGHT - PAD_Y,
                text=self.replay.map_name.upper(),
                fill=theme.TEXT,
                font=FONT_MAP,
                anchor="s",
            )
            return x + image.width() + MAP_GAP

        self.canvas.create_text(
            x,
            BAND_HEIGHT // 2,
            text=self.replay.map_name.upper(),
            fill=theme.TEXT,
            font=FONT_MAP,
            anchor="w",
        )
        return x + MAP_GAP * 8

    def _draw_tile(self, x: int, loadout, entry) -> int:
        """One loadout slot: icon if there is one, name either way."""
        image = None if entry is None else self.images.get(entry.icon, ICON_PX)
        centre = x + ICON_PX // 2

        if image is None:
            self.canvas.create_text(
                centre,
                BAND_HEIGHT // 2,
                text=loadout.display,
                fill=theme.MUTED,
                font=FONT_AGENT,
                anchor="c",
                width=ICON_PX,
            )
            return x + TILE_WIDTH

        self.canvas.create_image(x, PAD_Y, image=image, anchor="nw")
        role = None if entry is None else self.images.get(entry.role_icon, ROLE_PX)
        if role is not None:
            self.canvas.create_image(
                x + ICON_PX - role.width(),
                PAD_Y,
                image=role,
                anchor="nw",
            )
        self.canvas.create_text(
            centre,
            PAD_Y + ICON_PX + 2,
            text=entry.name,
            fill=theme.TEXT,
            font=FONT_AGENT,
            anchor="n",
            width=ICON_PX + TILE_GAP,
        )
        return x + TILE_WIDTH
