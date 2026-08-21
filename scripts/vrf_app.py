"""
The CustomTkinter app: the match list over DEMO_PATH.

    python scripts/vrf_app.py                 scan DEMO_PATH and list it
    python scripts/vrf_app.py --demo-path DIR scan DIR instead
    python scripts/vrf_app.py --list          the same scan, as text

`--list` exists because the scan is the interesting half and it is headless:
it says what the library holds, which builds decode positions and which files
it could not read, on a machine with no display at all.

Opening a card currently prints the replay it would open.  The viewer route is
Phase 6 of the rebuild; the router lands with it rather than being stubbed in
two places.
"""

from __future__ import annotations

import argparse
import sys

from vrfhome import scan

WINDOW_TITLE = "Valorant replay analyzer"
WINDOW_SIZE = "1180x760"


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
        "--no-cache",
        action="store_true",
        help="re-read every file rather than trusting out/match-scan.json",
    )
    return ap.parse_args(argv)


def run_scan(args: argparse.Namespace) -> scan.ScanResult:
    cache = scan.Cache(path=None) if args.no_cache else scan.Cache()
    return scan.scan(root=args.demo_path, cache=cache)


def print_scan(result: scan.ScanResult) -> int:
    """The whole library as text, newest first."""
    print(result.described)
    for card in scan.sort_cards(result.cards, descending=True):
        if not card.readable:
            print(f"  {card.file_name}  UNREADABLE  {card.error}")
            continue
        print(
            f"  {card.recorded}  {card.map_name:<9} {card.duration}  "
            f"{card.rounds:>2} rounds  "
            f"{'minimap  ' if card.positions_available else 'schematic'}  "
            f"{card.file_name}",
        )
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    result = run_scan(args)
    if args.list:
        return print_scan(result)

    # Imported here, not at module scope, so --list stays runnable with no
    # display and no customtkinter import.
    import customtkinter as ctk  # noqa: PLC0415

    from vrfhome import cards  # noqa: PLC0415
    from vrfview import theme  # noqa: PLC0415

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.title(WINDOW_TITLE)
    root.geometry(WINDOW_SIZE)
    root.configure(fg_color=theme.APP_BG)

    def open_card(card: scan.MatchCard) -> None:
        print(f"open {card.path}", file=sys.stderr)

    page = cards.MatchListPage(root, result, on_open=open_card)
    page.pack(fill="both", expand=True)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
