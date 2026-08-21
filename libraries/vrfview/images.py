"""
Decoded, resized, shaped images -- and the reference-keeping Tk still requires.

Its own module for two reasons, both of them toolkit facts rather than taste.

A `PhotoImage` is destroyed when the last Python reference to it goes, and a
canvas item holding one does *not* count as a reference: an image made in a
local variable renders blank as soon as the function returns.  Something has to
own them for the window's lifetime, and that something is this cache.

The second reason used to be that scaling was integer-only.  It is not any
more.  Tk 8.6's `subsample` divides by whole numbers, so a 1024x1024 portrait
could reach 64x64 and nothing in between, and `art.subsample_for` existed to
pick that factor from each file's real IHDR.  Pillow resamples to any size, so
that whole apparatus is gone: ask for 46x46 and you get 46x46, and a circular
portrait is a mask rather than a square tile with the corners showing.

Two flavours, and the difference matters
----------------------------------------
`photo` returns a Tk `PhotoImage` for a **canvas** -- the minimap, the map
reference window, the ability window.  `ctk` returns a `CTkImage` for a
**widget** --
a label, a button.  They are not interchangeable: a canvas cannot draw a
CTkImage, and a CTkImage is what lets a widget rescale itself when the display
scaling changes.  Callers pick by where the image is going.

Every failure returns None rather than raising.  A corrupt or truncated PNG
should cost a tile, not the window, and every caller has a text-only path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

if TYPE_CHECKING:
    from vrfview.art import ArtCache

# How a shaped image is masked.  SQUARE is no mask at all.
SQUARE = "square"
CIRCLE = "circle"
ROUNDED = "rounded"

# The corner radius of ROUNDED, as a fraction of the shorter side.
ROUNDED_FRACTION = 0.22

# Supersampling factor for the mask, so a circle's edge is not a staircase.
_MASK_SCALE = 4


def _fit(size: tuple[int, int], target: int) -> tuple[int, int]:
    """`size` scaled so its longest side is `target`, aspect kept."""
    width, height = size
    if width <= 0 or height <= 0:
        return (target, target)
    longest = max(width, height)
    scale = target / longest
    return (max(1, round(width * scale)), max(1, round(height * scale)))


def _mask(size: tuple[int, int], shape: str) -> Image.Image:
    """An L-mode mask, drawn large and shrunk so the edge is smooth."""
    big = (size[0] * _MASK_SCALE, size[1] * _MASK_SCALE)
    mask = Image.new("L", big, 0)
    draw = ImageDraw.Draw(mask)
    if shape == CIRCLE:
        draw.ellipse((0, 0, big[0] - 1, big[1] - 1), fill=255)
    else:
        radius = round(min(big) * ROUNDED_FRACTION)
        draw.rounded_rectangle((0, 0, big[0] - 1, big[1] - 1), radius, fill=255)
    return mask.resize(size, Image.LANCZOS)


def shape(image: Image.Image, kind: str) -> Image.Image:
    """`image` masked to a circle or a rounded rectangle, with alpha."""
    if kind == SQUARE:
        return image
    out = image.convert("RGBA")
    out.putalpha(_mask(out.size, kind))
    return out


class ImageCache:
    """
    Decoded images, sized and shaped once and kept.

    Keyed by `(path, size, shape, flavour)`, so an agent icon drawn in ten
    player rows is decoded once, and the same file at two sizes is two entries
    rather than a re-decode on every draw.
    """

    def __init__(self) -> None:
        self._sources: dict[str, Image.Image] = {}
        self._photos: dict[tuple, ImageTk.PhotoImage] = {}
        self._ctk: dict[tuple, ctk.CTkImage] = {}
        self._failed: set[str] = set()

    # -- loading ---------------------------------------------------------
    def source(self, path: Path | None) -> Image.Image | None:
        """
        The decoded file, cached.

        `path` may be None so a caller can pass an unresolved art field
        straight through: a missing entry and a missing file are the same
        outcome here, and both mean "draw the text instead".
        """
        if path is None:
            return None
        key = str(path)
        if key in self._failed:
            return None
        if key in self._sources:
            return self._sources[key]
        try:
            image = Image.open(path)
            image.load()
        except (OSError, ValueError):
            self._failed.add(key)
            return None
        self._sources[key] = image
        return image

    # -- flavours --------------------------------------------------------
    def photo(
        self,
        path: Path | None,
        size: tuple[int, int] | int,
        kind: str = SQUARE,
    ) -> ImageTk.PhotoImage | None:
        """A canvas image at exactly `size` (an int means longest side)."""
        key = self._key(path, size, kind)
        if key is None:
            return None
        if key not in self._photos:
            self._photos[key] = ImageTk.PhotoImage(self._render(path, key))
        return self._photos[key]

    def ctk(
        self,
        path: Path | None,
        size: tuple[int, int] | int,
        kind: str = SQUARE,
    ) -> ctk.CTkImage | None:
        """A widget image at exactly `size` (an int means longest side)."""
        key = self._key(path, size, kind)
        if key is None:
            return None
        if key not in self._ctk:
            image = self._render(path, key)
            self._ctk[key] = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=image.size,
            )
        return self._ctk[key]

    def get(self, path: Path | None, target: int) -> ImageTk.PhotoImage | None:
        """Longest side at most `target`, aspect kept -- the canvas callers."""
        return self.photo(path, target)

    def size_of(self, image) -> tuple[int, int]:
        """The drawn size of an already-sized image."""
        if isinstance(image, ctk.CTkImage):
            return image.cget("size")
        return image.width(), image.height()

    def clear(self) -> None:
        """Drop every reference.  The images go with them."""
        self._sources.clear()
        self._photos.clear()
        self._ctk.clear()
        self._failed.clear()

    # -- internals -------------------------------------------------------
    def _key(
        self,
        path: Path | None,
        size: tuple[int, int] | int,
        kind: str,
    ) -> tuple | None:
        """
        The cache key, which needs the file only to resolve an int size.

        Decoding happens here, but only once per file: an already-cached
        (size, shape) is answered without touching Pillow again, which is what
        keeps a ten-row panel redraw free.
        """
        source = self.source(path)
        if source is None:
            return None
        wanted = _fit(source.size, size) if isinstance(size, int) else size
        return (str(path), wanted, kind)

    def _render(self, path: Path | None, key: tuple) -> Image.Image:
        source = self.source(path)
        image = source.convert("RGBA").resize(key[1], Image.LANCZOS)
        return shape(image, key[2])


@dataclass(frozen=True)
class Visuals:
    """
    An art cache and the image cache that draws from it, as one argument.

    Every widget that shows a picture needs both -- one to resolve a path, the
    other to decode and size it -- and passing them separately down four levels
    of constructor is how a signature grows past what anyone reads.  The
    annotations stay strings (`from __future__ import annotations`, and nothing
    calls `get_type_hints`), so this costs no import of the art layer.
    """

    art: ArtCache
    images: ImageCache

    @classmethod
    def make(cls, art: ArtCache, images: ImageCache | None = None) -> Visuals:
        return cls(art=art, images=images if images is not None else ImageCache())
