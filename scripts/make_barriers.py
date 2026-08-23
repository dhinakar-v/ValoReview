r"""
Write each map's round-start spawn barriers out as a PNG beside its radar.

    runners\make-barriers.bat                  every map the table names
    runners\make-barriers.bat --only Ascent    one map; repeatable
    runners\make-barriers.bat --overlay        also write a composite for eyes
    runners\make-barriers.bat --decode         re-read features/map-barriers/

Two modes and they are not the same job.  The default reads
`libraries/vrfview/barriers.json` -- the committed table -- and draws it.
`--decode` rebuilds that table from the reference screenshots in
`features/map-barriers/`, which is a measurement, takes about five seconds a
map, and is the only thing here that needs those pictures to exist.  They are
gitignored, so on a fresh checkout the default mode works and `--decode` says
what is missing.

`libraries/vrfview/barriers.py` is the one place that decides what a barrier is
and what colour each side gets, and `barrierdecode.py` the one place that
decides how a screenshot becomes a coordinate, so the palette, the shape filter
and the alignment all have one home apiece.

Like `make_walls`, there is no `--check` here: `assets/` is gitignored in full
and the PNGs hold no contract.  The **table** does, and it is committed --
`--decode` rewrites it and `git diff` is the review.

The per-map line is worth reading in both modes.  `on floor` is the ground
truth this rests on: a barrier closes a doorway and a doorway is floor, so a
bar that came out of a bad fit lands in the void.  In decode mode `IoU` and
`2nd` say how far the winning orientation beat the best of the other seven --
under about 1.5x apart and the placement is a coin toss rather than a reading.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vrfview import art, barrierdecode, barriers

BARRIERS_NAME = "barriers.png"
OVERLAY_NAME = "barriers-overlay.png"

# Where `--decode` looks for the reference frames, and what it calls a map.
# `<display name>.png`, case-folded, resolved against the manifest rather than
# title-cased back -- the join `art.WeaponArt` already uses, for the reason
# `art._resolve` exists: a name is matched against the catalogue, never rebuilt
# from a string.
REFERENCES = Path("features/map-barriers")

# Below this ratio between the winning orientation's overlap and the runner-up's,
# the placement is not a reading and the run should say the map's name.  The
# nine frames measured span 1.72x to 2.24x, so this sits clear below all of
# them; it decides whether a sentence is printed and nothing branches on it.
MARGIN_FLOOR = 1.4

# And below this share of its centreline on playable floor, a single bar is
# suspect however well its map scored.  The worst of the 76 measured is 0.90.
FLOOR_SHARE = 0.75


def barrier_image(size: tuple[int, int], entry: barriers.MapBarriers):
    """
    The barriers alone: each bar in its side's colour, transparent elsewhere.

    Transparent rather than black for the reason `make_walls.wall_image` gives
    -- the file is a mask a compositor can use directly, at the radar's own
    size and in its own alignment.  Unlike the walls it is *coloured*, because
    there are two classes of barrier and a one-channel mask cannot say which is
    which; `--overlay` is still the way to look at it.
    """
    from PIL import Image, ImageDraw  # noqa: PLC0415  (see vrfview/walls.wall_ink)

    out = Image.new("RGBA", size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(out)
    for barrier in entry.barriers:
        draw.rectangle(barrier.rect(min(size)), fill=barriers.INK[barrier.side])
    return out


def overlay_image(source, entry: barriers.MapBarriers):
    """
    The radar with the barriers painted over it, composited on black.

    In the sides' own colours rather than in a colour nothing else uses, which
    is where this parts company with `make_walls.overlay_image` and for a
    reason: that file paints magenta because it is checking a *threshold*, and
    white ink composited in white would look perfect whatever the threshold
    did.  Here the extraction is not in doubt -- a bar is a flat rectangle in
    one of two colours -- and what wants checking is the **placement**, which
    reads best when the bars look the way the source frame drew them.
    """
    from PIL import Image  # noqa: PLC0415  (see above)

    base = Image.new("RGBA", source.size, (0, 0, 0, 255))
    base.alpha_composite(source.convert("RGBA"))
    base.alpha_composite(barrier_image(source.size, entry))
    return base


def entries(cache: art.ArtCache, only: tuple[str, ...]) -> list[art.MapArt]:
    """The maps with a radar on disk, in name order, filtered by `--only`."""
    found = sorted(cache.maps.values(), key=lambda entry: entry.name)
    if only:
        wanted = {name.casefold() for name in only}
        found = [entry for entry in found if entry.name.casefold() in wanted]
    return [entry for entry in found if entry.minimap is not None]


def write_one(
    entry: art.MapArt,
    row: barriers.MapBarriers,
    *,
    overlay: bool,
) -> tuple[int, int, int]:
    """One map: draw the table's bars beside its radar, return its numbers."""
    from PIL import Image  # noqa: PLC0415  (see above)

    with Image.open(entry.minimap) as source:
        source.load()
        barrier_image(source.size, row).save(entry.minimap.with_name(BARRIERS_NAME))
        if overlay:
            overlay_image(source, row).save(entry.minimap.with_name(OVERLAY_NAME))
        silhouette = barrierdecode.radar_silhouette(entry.minimap)

    grounded = sum(
        1
        for barrier in row.barriers
        if barrierdecode.on_floor(barrier, silhouette) >= FLOOR_SHARE
    )
    return len(row.side("attack")), len(row.side("defence")), grounded


def decode_all(wanted: list[art.MapArt], references: Path):
    """
    Rebuild the table from the reference frames, for every map that has one.

    A map with no frame is not an error and not an empty row -- it is simply
    absent from the table, and `load` will report it as "not recorded" rather
    than as "has no barriers".  The two are different claims and the second one
    would be a lie about nine of the eighteen maps.
    """
    found: dict[str, barriers.MapBarriers] = {}
    missing: list[str] = []
    frames = {path.stem.casefold(): path for path in sorted(references.glob("*.png"))}
    for entry in wanted:
        frame = frames.get(entry.name.casefold())
        if frame is None:
            missing.append(entry.name)
            continue
        found[entry.name] = barrierdecode.decode(entry.name, frame, entry.minimap)
    return found, missing


def report(name: str, row: barriers.MapBarriers, counts: tuple[int, int, int]) -> str:
    attack, defence, grounded = counts
    fit = row.fit
    return (
        f"{name:10} {attack:6d} {defence:7d} {grounded:3d}/{attack + defence:<3d} "
        f"{fit.orient:9} {fit.iou:7.4f} {fit.runner_up_iou:7.4f} {fit.margin:6.2f}x"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="make-barriers",
        description="Write each map's spawn barriers out as a PNG beside its radar.",
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
        help=f"also write {OVERLAY_NAME}: the bars laid back over the radar",
    )
    parser.add_argument(
        "--decode",
        action="store_true",
        help=f"re-read {REFERENCES} and rewrite the committed table first",
    )
    parser.add_argument(
        "--references",
        default=str(REFERENCES),
        help="where the reference screenshots live (with --decode)",
    )
    parser.add_argument(
        "--config",
        default=str(barriers.CONFIG_PATH),
        help="the barrier table to read, or to write with --decode",
    )
    return parser.parse_args(argv)


def rebuild(args: argparse.Namespace, wanted: list[art.MapArt], config: Path) -> int:
    """`--decode`: re-read the reference frames and rewrite the committed table."""
    references = Path(args.references)
    if not references.is_dir():
        print(f"error: no reference frames at {references}", file=sys.stderr)
        return 1
    table, without = decode_all(wanted, references)
    if not table:
        print(f"error: no frame in {references} names a map", file=sys.stderr)
        return 1
    read = len(table)
    if args.only:
        table = {**_existing(config), **table}
    config.write_text(barriers.dumps(table), encoding="utf-8")
    kept = len(table) - read
    also = f", keeping {kept} row(s) already there" if kept else ""
    print(f"wrote {config} from {read} reference frame(s){also}")
    if without:
        print(f"note: no reference frame for {', '.join(without)} -- not recorded")
    return 0


def notes(skipped: list[str], thin: list[str], ungrounded: list[str]) -> None:
    """
    Everything the run wants to say after the table, by name and never by count.

    A map that was asked for and drew nothing has to be named, or a library of
    unrecorded maps reads as a clean run -- the same argument `vrfhome.scan`
    makes for listing a capture it cannot decode rather than omitting it.
    """
    if skipped:
        print(f"note: no barriers recorded for {', '.join(skipped)} -- nothing drawn")
    if thin:
        print(
            "note: the winning orientation barely beat the next best on "
            f"{', '.join(thin)} -- re-derive before trusting the placement",
        )
    if ungrounded:
        print(
            f"note: a bar lands off the playable floor on {', '.join(ungrounded)} -- "
            "the fit put it somewhere the map is not",
        )


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

    config = Path(args.config)
    if args.decode and rebuild(args, wanted, config):
        return 1

    try:
        table = barriers.load(config)
    except barriers.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    drawn = [entry for entry in wanted if entry.name in table]
    if not drawn:
        print(f"error: {config} records none of the maps asked for", file=sys.stderr)
        return 1

    header = f"{'map':10} {'attack':>6} {'defence':>7} {'on floor':>7} "
    print(header + f"{'orient':9} {'IoU':>7} {'2nd':>7} {'margin':>7}")
    thin: list[str] = []
    ungrounded: list[str] = []
    for entry in drawn:
        row = table[entry.name]
        counts = write_one(entry, row, overlay=args.overlay)
        print(report(entry.name, row, counts))
        if row.fit.margin < MARGIN_FLOOR:
            thin.append(entry.name)
        if counts[2] < counts[0] + counts[1]:
            ungrounded.append(entry.name)

    also = f" and {OVERLAY_NAME}" if args.overlay else ""
    print(f"wrote {len(drawn)} {BARRIERS_NAME}{also}")
    notes([e.name for e in wanted if e.name not in table], thin, ungrounded)
    return 0


def _existing(config: Path) -> dict[str, barriers.MapBarriers]:
    """The table already on disk, so `--decode --only` edits one row of it."""
    try:
        return barriers.load(config)
    except barriers.ConfigError:
        return {}


if __name__ == "__main__":
    sys.exit(main())
