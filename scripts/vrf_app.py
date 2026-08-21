"""
The CustomTkinter app: the match list over DEMO_PATH.

    python scripts/vrf_app.py                 scan DEMO_PATH and list it
    python scripts/vrf_app.py --demo-path DIR scan DIR instead
    python scripts/vrf_app.py --list          the same scan, as text

`--list` exists because the scan is the interesting half and it is headless:
it says what the library holds, which builds decode positions and which files
it could not read, on a machine with no display at all.

Opening a card loads that replay and switches to the viewer; `vrfview.app` is
the router and owns both pages.
"""

from __future__ import annotations

import argparse

from vrfhome import scan
from vrfview import positioncache


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Browse a library of .vrf replays.")
    ap.add_argument(
        "--demo-path",
        metavar="DIR",
        help="replay directory to scan (default: DEMO_PATH, else Demos/)",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="print the scan as text and exit; needs no display",
    )
    ap.add_argument(
        "--no-art",
        action="store_true",
        help="ignore the art cache; no thumbnails, portraits or minimap",
    )
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="re-read every file rather than trusting out/match-scan.json",
    )
    return ap.parse_args(argv)


def run_scan(args: argparse.Namespace) -> scan.ScanResult:
    cache = scan.Cache(path=None) if args.no_cache else scan.Cache()
    return scan.scan(root=args.demo_path, cache=cache)


def print_scan(result: scan.ScanResult) -> int:
    """
    The whole library as text, newest first.

    Every card, including the ones the window holds back: a listing is what a
    user reaches for precisely when they want to know why a capture is not on
    screen, so this is the one place the filter does not apply.
    """
    print(result.described)
    for card in scan.sort_cards(result.cards, descending=True):
        if not card.readable:
            print(f"  {card.file_name}  UNREADABLE  {card.error}")
            continue
        state = "playable " if card.playable else "no decode"
        cached = "  cached" if positioncache.has(card.path) else ""
        print(
            f"  {card.recorded}  {card.map_name:<9} {card.duration}  "
            f"{card.rounds:>2} rounds  {state}{cached}  {card.file_name}",
        )
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    result = run_scan(args)
    if args.list:
        return print_scan(result)

    # Imported here, not at module scope, so --list stays runnable with no
    # display and no customtkinter import.
    from vrfview import app  # noqa: PLC0415
    from vrfview import art as art_mod  # noqa: PLC0415

    art = art_mod.ArtCache() if args.no_art else art_mod.load()
    return app.run(result, art)


if __name__ == "__main__":
    raise SystemExit(main())
