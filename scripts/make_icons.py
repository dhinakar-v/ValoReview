"""
Draw the transport glyphs the app uses, as PNGs.

    python scripts/make_icons.py            write assets/icons/*.png
    python scripts/make_icons.py --list     name them without writing

The brief asks for a custom icon on every interactive control and none exist:
the art cache is Riot's, and Riot ships no transport glyphs.  Rather than
depend on an icon font or vendor a set with its own licence, the nine shapes
are drawn here -- triangles, bars and an arrow head -- at 4x and downsampled,
which is what makes their edges smooth at 20 px.

They are generated, not committed: `assets/` is gitignored, and the viewer
falls back to a text label for any glyph that is missing, so a checkout that
never runs this still has a working control bar with `>` where the play
triangle would be.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from vrfview.icons import FALLBACK, icon_dir

ICON_DIR = icon_dir()
SIZE = 48
SUPERSAMPLE = 4
COLOUR = (236, 232, 225, 255)

def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    side = SIZE * SUPERSAMPLE
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def _finish(image: Image.Image) -> Image.Image:
    return image.resize((SIZE, SIZE), Image.LANCZOS)


def _triangle(draw, left: float, right: float, *, pointing: int = 1) -> None:
    """A play head pointing right (1) or left (-1), spanning the full height."""
    top, bottom = SIZE * SUPERSAMPLE * 0.22, SIZE * SUPERSAMPLE * 0.78
    middle = SIZE * SUPERSAMPLE * 0.5
    if pointing > 0:
        draw.polygon([(left, top), (left, bottom), (right, middle)], fill=COLOUR)
    else:
        draw.polygon([(right, top), (right, bottom), (left, middle)], fill=COLOUR)


def _bar(draw, x: float, width: float) -> None:
    side = SIZE * SUPERSAMPLE
    draw.rectangle([x, side * 0.22, x + width, side * 0.78], fill=COLOUR)


def draw_play() -> Image.Image:
    image, draw = _canvas()
    side = SIZE * SUPERSAMPLE
    _triangle(draw, side * 0.3, side * 0.76)
    return _finish(image)


def draw_pause() -> Image.Image:
    image, draw = _canvas()
    side = SIZE * SUPERSAMPLE
    _bar(draw, side * 0.3, side * 0.13)
    _bar(draw, side * 0.57, side * 0.13)
    return _finish(image)


def _step(pointing: int) -> Image.Image:
    image, draw = _canvas()
    side = SIZE * SUPERSAMPLE
    _triangle(draw, side * 0.32, side * 0.68, pointing=pointing)
    return _finish(image)


def _to_end(pointing: int) -> Image.Image:
    """A step triangle with the bar it stops against, as a track-skip does."""
    image, draw = _canvas()
    side = SIZE * SUPERSAMPLE
    if pointing > 0:
        _triangle(draw, side * 0.24, side * 0.62, pointing=1)
        _bar(draw, side * 0.66, side * 0.1)
    else:
        _bar(draw, side * 0.24, side * 0.1)
        _triangle(draw, side * 0.38, side * 0.76, pointing=-1)
    return _finish(image)


def draw_back() -> Image.Image:
    """The back arrow: a shaft and a head, not a triangle."""
    image, draw = _canvas()
    side = SIZE * SUPERSAMPLE
    middle = side * 0.5
    draw.line(
        [(side * 0.28, middle), (side * 0.76, middle)],
        fill=COLOUR,
        width=int(side * 0.07),
    )
    draw.polygon(
        [
            (side * 0.2, middle),
            (side * 0.44, middle - side * 0.17),
            (side * 0.44, middle + side * 0.17),
        ],
        fill=COLOUR,
    )
    return _finish(image)


def draw_map() -> Image.Image:
    """A folded map: three panels, so it is not mistaken for a document."""
    image, draw = _canvas()
    side = SIZE * SUPERSAMPLE
    width = int(side * 0.05)
    draw.polygon(
        [
            (side * 0.18, side * 0.3),
            (side * 0.4, side * 0.22),
            (side * 0.6, side * 0.34),
            (side * 0.82, side * 0.24),
            (side * 0.82, side * 0.7),
            (side * 0.6, side * 0.8),
            (side * 0.4, side * 0.68),
            (side * 0.18, side * 0.78),
        ],
        outline=COLOUR,
        width=width,
    )
    draw.line(
        [(side * 0.4, side * 0.22), (side * 0.4, side * 0.68)],
        fill=COLOUR,
        width=width,
    )
    draw.line(
        [(side * 0.6, side * 0.34), (side * 0.6, side * 0.8)],
        fill=COLOUR,
        width=width,
    )
    return _finish(image)


def draw_info() -> Image.Image:
    """A dot and a stem inside a ring: provenance, the panel that explains."""
    image, draw = _canvas()
    side = SIZE * SUPERSAMPLE
    draw.ellipse(
        [side * 0.16, side * 0.16, side * 0.84, side * 0.84],
        outline=COLOUR,
        width=int(side * 0.06),
    )
    draw.ellipse(
        [side * 0.45, side * 0.26, side * 0.55, side * 0.36],
        fill=COLOUR,
    )
    draw.rectangle(
        [side * 0.45, side * 0.43, side * 0.55, side * 0.72],
        fill=COLOUR,
    )
    return _finish(image)


GLYPHS = {
    "play": draw_play,
    "pause": draw_pause,
    "step_back": lambda: _step(-1),
    "step_forward": lambda: _step(1),
    "round_back": lambda: _to_end(-1),
    "round_forward": lambda: _to_end(1),
    "back": draw_back,
    "map": draw_map,
    "info": draw_info,
}


def icon_path(name: str, root: Path = ICON_DIR) -> Path:
    return root / f"{name}.png"


def write_all(root: Path = ICON_DIR) -> list[Path]:
    """Draw every glyph, returning what was written."""
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for name, draw in GLYPHS.items():
        path = icon_path(name, root)
        draw().save(path)
        written.append(path)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Draw the app's transport icons.")
    ap.add_argument("--out", default=str(ICON_DIR), metavar="DIR")
    ap.add_argument("--list", action="store_true", help="name them, write nothing")
    args = ap.parse_args(argv)

    if args.list:
        for name, fallback in FALLBACK.items():
            print(f"{name:<15} fallback {fallback!r}")
        return 0

    for path in write_all(Path(args.out)):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
