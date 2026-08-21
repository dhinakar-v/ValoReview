"""
The map reference window: Riot's radar image and Riot's own callouts.

This is the one place in the viewer where a coordinate is drawn at a real map
position, and it is safe precisely because none of those coordinates come from
the replay.  The callouts are Riot's, cached in assets/manifest.json, and they
describe the map rather than the match: the same picture for every replay on
Bind, whatever happened in it.  Nothing here reads Replay.kills, and the footer
says so on screen.

It is a separate Toplevel and not a layer under the scene for that reason.  The
replay contains no positions -- the property payloads are undecoded -- so
players cannot be placed on this image, and drawing the schematic's nodes on top
of it would suggest they had been.  docs/replay-viewer-*-handoff.md records the
decision to keep the scene schematic; this window does not reopen it.

The transform is vrfview.art's, including the axis swap, which is measured and
not assumed.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from vrfview import theme

if TYPE_CHECKING:
    from vrfview.art import MapArt
    from vrfview.images import ImageCache

IMAGE_PX = 512
PAD = 16
DOT = 3
FOOTER_HEIGHT = 46

# Within this many pixels of an edge, a centred label would be clipped.
_EDGE_PX = 60

FONT_CALLOUT = ("Segoe UI", 8)
FONT_FOOTER = ("Segoe UI", 8)
FONT_TITLE = ("Segoe UI Semibold", 11)

FOOTER = (
    "Riot's own callout coordinates, from assets/manifest.json.\n"
    "No replay data is plotted here - the replay contains no positions."
)


def show(
    master: tk.Misc,
    map_art: MapArt | None,
    images: ImageCache,
) -> tk.Toplevel | None:
    """
    Open the reference window, or do nothing if there is no art to show.

    Takes no Replay, and that is the point rather than an oversight: this
    window cannot draw match data because it is never given any.  Returns the
    window so the app can raise an existing one instead of stacking duplicates,
    and None when the cache has no minimap for this map.
    """
    if map_art is None or not map_art.plottable:
        return None
    image = images.get(map_art.minimap, IMAGE_PX)
    if image is None:
        return None

    top = tk.Toplevel(master)
    top.title(f"Map reference - {map_art.name}")
    top.configure(bg=theme.BACKGROUND)

    width, height = image.width(), image.height()
    canvas = tk.Canvas(
        top,
        width=width + PAD * 2,
        height=height + PAD * 2 + FOOTER_HEIGHT,
        bg=theme.BACKGROUND,
        highlightthickness=0,
        bd=0,
    )
    canvas.pack()
    # The cache owns the PhotoImage, but this window may outlive the call, so
    # the canvas keeps its own reference too.
    canvas.image = image

    canvas.create_image(PAD, PAD, image=image, anchor="nw")
    _draw_callouts(canvas, map_art, width, height)
    canvas.create_text(
        PAD,
        PAD + height + 10,
        text=FOOTER,
        fill=theme.MUTED,
        font=FONT_FOOTER,
        anchor="nw",
    )
    top.resizable(width=False, height=False)
    top.bind("<Escape>", lambda _e: top.destroy())
    return top


def _anchor_for(x: float, width: int) -> str:
    """
    Which side of the dot a label hangs from, so edge names stay readable.

    Riot puts the spawn callouts hard against the left and right of the radar,
    and a centred label there runs off the canvas.  The dot never moves -- only
    the text does -- so this changes legibility and not position.
    """
    if x < _EDGE_PX:
        return "sw"
    if x > width - _EDGE_PX:
        return "se"
    return "s"


def _draw_callouts(
    canvas: tk.Canvas,
    map_art: MapArt,
    width: int,
    height: int,
) -> None:
    """A dot and a label per region, in image pixels."""
    for callout in map_art.callouts:
        x, y = map_art.to_pixels(callout, width, height)
        # Riot ships regions outside the rendered radar on some maps; clipping
        # them is honest, moving them onto the edge would not be.
        if not (0 <= x <= width and 0 <= y <= height):
            continue
        cx, cy = PAD + x, PAD + y
        canvas.create_oval(
            cx - DOT,
            cy - DOT,
            cx + DOT,
            cy + DOT,
            fill=theme.ACCENT,
            outline=theme.BACKGROUND,
        )
        canvas.create_text(
            cx,
            cy - DOT - 2,
            text=callout.name,
            fill=theme.TEXT,
            font=FONT_CALLOUT,
            anchor=_anchor_for(x, width),
        )
