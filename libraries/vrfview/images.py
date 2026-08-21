"""
PhotoImage loading and the reference-keeping that Tk requires.

Its own module for two reasons, both of them Tk facts rather than taste.

A PhotoImage is destroyed when the last Python reference to it goes, and a
canvas item holding one does *not* count as a reference: an image created in a
local variable renders blank as soon as the function returns.  So something must
own them for the window's lifetime, and that something is this cache.

The scaling is integer-only.  Tk 8.6's `subsample` takes whole-number factors
and the project has no Pillow to resample with (pyproject.toml keeps runtime
dependencies at zero), so a 1024x1024 icon reaches 64x64 exactly and a 456x100
strip is drawn at its native size.  vrfview.art.subsample_for picks the factor
from the file's real IHDR, because the cache is not uniformly sized.

Every failure here returns None rather than raising.  A corrupt or truncated PNG
should cost a tile, not the window -- the callers all have a text-only path.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

from vrfview import art


class ImageCache:
    """
    Sized PhotoImages, kept alive and reused.

    Keyed by (path, factor), so the roster's 29 possible icons and the map
    reference's minimap are each decoded once even if drawn repeatedly.
    """

    def __init__(self) -> None:
        self._images: dict[tuple[str, int], tk.PhotoImage] = {}
        self._failed: set[str] = set()

    def get(self, path: Path | None, target: int) -> tk.PhotoImage | None:
        """
        One image, scaled so its longest side is at most `target` pixels.

        `path` is allowed to be None so callers can pass an unresolved art field
        straight through: a missing file and a missing entry are the same
        outcome here, and both mean "draw the text instead".
        """
        if path is None:
            return None
        key = str(path)
        if key in self._failed:
            return None
        try:
            factor = art.subsample_for(art.png_size(path), target)
        except (OSError, ValueError):
            self._failed.add(key)
            return None

        cached = self._images.get((key, factor))
        if cached is not None:
            return cached
        try:
            image = tk.PhotoImage(file=str(path))
            if factor > 1:
                image = image.subsample(factor, factor)
        except tk.TclError:
            self._failed.add(key)
            return None
        self._images[(key, factor)] = image
        return image

    def size_of(self, image: tk.PhotoImage) -> tuple[int, int]:
        """The drawn size of an already-scaled image."""
        return image.width(), image.height()

    def clear(self) -> None:
        """Drop every reference. The images go with them."""
        self._images.clear()
        self._failed.clear()
