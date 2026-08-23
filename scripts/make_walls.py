r"""
Write out the wall lines Riot draws on each radar, as one PNG per map.

    runners\make-walls.bat                     every map in assets/manifest.json
    runners\make-walls.bat --only Icebox       one map; repeatable
    runners\make-walls.bat --overlay           also write a composite for eyes

`libraries/vrfview/walls.py` is the one place that decides what a wall is and
this generates from it, so the threshold, the downsample and the reasoning all
have one home.

**Nothing in the app reads these files back**, and that is the finding rather
than an oversight.  The reason to extract the walls was to hand them to
`sight.SightMap` so a cone would stop at the interior walls the alpha
silhouette misses; measured against 3,128 real kill sightlines that made line
of sight roughly twenty times worse, because Riot already encodes opaque
geometry as the silhouette and the white ink marks what you can see *past*.
`walls.py` carries the table and `tests/test_positions.py` is the standing
check.  So these PNGs are a picture of what the radar draws, for a person to
look at and for whatever comes next to build on -- not an occluder.

That also means there is no `--check` mode here the way `make_theme` and
`make_golden` have one: those guard a committed file against going stale, and
`assets/` is gitignored in full and holds no contract.

The per-map line it prints is worth reading.  `new` counts the working-grid
cells the ink closes that the alpha silhouette had left open -- 10.3% to 21.6%
of the open map, which is how much detail the silhouette does not carry, and
equally how much of it turned out not to block anything.
"""

from __future__ import annotations

import argparse
import sys

from vrfview import art, sight, walls

WALLS_NAME = "walls.png"
OVERLAY_NAME = "walls-overlay.png"

# Below this share of the open cells, the walls are telling us nothing the
# silhouette did not already say and the run should mention the map by name.
# Not a threshold anything branches on -- it only decides whether a sentence is
# printed -- so a round number is honest here where it would not be in `walls`.
QUIET_SHARE = 1.0

# What `--overlay` paints the selected ink in.  See `overlay_image`.
OVERLAY_INK = (255, 0, 255, 255)


def wall_image(source, ink):
    """
    The mask itself: opaque white where wall, fully transparent everywhere else.

    Transparent rather than black so the file is a mask a compositor can use
    directly, at the radar's own size and in its own alignment.  `wall_ink`
    returns an `"L"` and it goes in as the alpha channel of a solid white
    frame, which keeps the antialiased rim as a soft edge rather than
    quantising it away.  Look at it with `--overlay`, not on its own: white on
    transparent is white on white in most viewers.
    """
    from PIL import Image  # noqa: PLC0415  (see vrfview/walls.wall_ink)

    out = Image.new("RGBA", source.size, (255, 255, 255, 0))
    out.putalpha(ink)
    return out


def overlay_image(source, ink):
    """
    The radar with the selected ink painted over it in a colour it never uses.

    Magenta, and that is the whole design of this file.  Compositing the mask
    back in white produces a picture pixel-identical to the radar -- the ink is
    already white -- so it would look perfect whatever the threshold did, which
    is the one thing a QA image must not do.  Nothing on any published radar is
    magenta, so every pixel this picks reads as picked, and anything it took
    that is not a wall is immediately visible.

    The radar underneath is composited on black rather than left transparent,
    so the void reads as void instead of as whatever the viewer paints behind
    the page.
    """
    from PIL import Image  # noqa: PLC0415  (see vrfview/walls.wall_ink)

    base = Image.new("RGBA", source.size, (0, 0, 0, 255))
    base.alpha_composite(source.convert("RGBA"))
    paint = Image.new("RGBA", source.size, OVERLAY_INK)
    paint.putalpha(ink)
    base.alpha_composite(paint)
    return base


def measure(source, size: int = sight.GRID) -> tuple[int, int, int]:
    """
    Ink pixels, open cells under alpha alone, and cells the walls newly close.

    The third number is the point of the exercise and is computed here rather
    than inferred from the other two: a wall line drawn along the rim of the
    silhouette closes a cell that was already closed, and only the ones drawn
    on open floor are new.
    """
    rgba = source.convert("RGBA")
    ink = walls.wall_ink(rgba, alpha_floor=sight.ALPHA_FLOOR)
    ink_pixels = sum(1 for value in ink.tobytes() if value)

    alpha = rgba.resize((size, size)).getchannel("A").tobytes()
    wall = walls.wall_cells(rgba, size, alpha_floor=sight.ALPHA_FLOOR)
    was_open = [1 if a >= sight.ALPHA_FLOOR else 0 for a in alpha]
    newly = sum(1 for o, w in zip(was_open, wall, strict=True) if o and w)
    return ink_pixels, sum(was_open), newly


def entries(cache: art.ArtCache, only: tuple[str, ...]) -> list[art.MapArt]:
    """
    The maps to write, in name order, skipping any with no radar on disk.

    Taken from the manifest rather than by listing `assets/maps/` for the
    reason `art._resolve` exists: a path is read out of the manifest's `files`
    dict and never built from a display name, or `KAY/O` breaks.
    """
    found = sorted(cache.maps.values(), key=lambda entry: entry.name)
    if only:
        wanted = {name.casefold() for name in only}
        found = [entry for entry in found if entry.name.casefold() in wanted]
    return [entry for entry in found if entry.minimap is not None]


def write_one(entry: art.MapArt, *, overlay: bool) -> tuple[str, int, int, int]:
    """One map: read the radar, write the mask beside it, return its numbers."""
    from PIL import Image  # noqa: PLC0415  (see vrfview/walls.wall_ink)

    with Image.open(entry.minimap) as source:
        source.load()
        ink = walls.wall_ink(source, alpha_floor=sight.ALPHA_FLOOR)
        wall_image(source, ink).save(entry.minimap.with_name(WALLS_NAME))
        if overlay:
            overlay_image(source, ink).save(entry.minimap.with_name(OVERLAY_NAME))
        return (entry.name, *measure(source))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="make-walls",
        description="Write each map's wall lines out as a PNG beside its radar.",
    )
    parser.add_argument("--assets", default="assets", help="the art cache to read")
    parser.add_argument(
        "--only",
        action="append",
        metavar="MAP",
        help="limit to one map by display name; repeatable (default: all)",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help=f"also write {OVERLAY_NAME}: the mask laid back over the radar",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cache = art.load(args.assets)
    if cache.empty:
        print(f"error: {cache.reason}", file=sys.stderr)
        return 1

    wanted = entries(cache, tuple(args.only or ()))
    if not wanted:
        named = ", ".join(args.only) if args.only else "any map"
        print(f"error: no radar on disk for {named}", file=sys.stderr)
        return 1

    print(f"{'map':10} {'ink px':>9} {'open cells':>11} {'new':>7} {'% open':>7}")
    quiet: list[str] = []
    for entry in wanted:
        name, ink_pixels, open_cells, newly = write_one(entry, overlay=args.overlay)
        share = 100 * newly / open_cells if open_cells else 0.0
        print(f"{name:10} {ink_pixels:9d} {open_cells:11d} {newly:7d} {share:7.1f}")
        if share < QUIET_SHARE:
            quiet.append(name)

    also = f" and {OVERLAY_NAME}" if args.overlay else ""
    print(f"wrote {len(wanted)} {WALLS_NAME}{also}")
    if quiet:
        print(
            "note: the walls close almost nothing the silhouette did not on "
            f"{', '.join(quiet)} -- no interior wall is drawn there",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
