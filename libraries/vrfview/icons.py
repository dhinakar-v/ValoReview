"""
Where the transport glyphs live, and what to show when they do not.

`scripts/make_icons.py` draws them; this says where they land and what each
control falls back to without one.  The split exists because `scripts/` is not
installed -- the viewer cannot import the generator -- and because the names
have to agree at both ends or a button silently loses its picture.

`assets/` is gitignored, so absent icons are the ordinary state of a fresh
checkout, not a fault.  Every caller asks `path_for` and passes the answer
straight to `ImageCache.ctk`, which returns None for a file that is not there;
the button then draws `FALLBACK[name]` and works exactly as well.
"""

from __future__ import annotations

from pathlib import Path

from vrfview.art import ASSETS_DIR

ICON_DIRNAME = "icons"

# Drawn at 48 px; the bar shows them at 20, which Pillow resamples cleanly.
ICON_PX = 20

# Every glyph the app asks for, and the text that stands in for it.
#
# `death` is the odd one out: it is drawn on the map canvas rather than on a
# button, so its fallback is never rendered as text -- `minimap` falls back to
# the two crossed lines it drew before there was an icon.  It lives here
# anyway because the generator and the viewer have to agree on the name, and
# this table plus `tests/test_app_ui.py::IconNames` is what makes them.
FALLBACK = {
    "play": ">",
    "pause": "||",
    "step_back": "<",
    "step_forward": ">",
    "round_back": "|<",
    "round_forward": ">|",
    "back": "<-",
    "map": "MAP",
    "info": "i",
    "death": "x",
    "sight": "SIGHT",
    "ability": "ABIL",
}

NAMES = tuple(FALLBACK)


def icon_dir(root: Path | None = None) -> Path:
    return (root or ASSETS_DIR) / ICON_DIRNAME


def path_for(name: str, root: Path | None = None) -> Path | None:
    """The glyph's file, or None if it has not been generated."""
    path = icon_dir(root) / f"{name}.png"
    return path if path.is_file() else None
