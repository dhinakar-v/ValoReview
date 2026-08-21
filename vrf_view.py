"""
Play a .vrf replay back in 2D.

Two commands: `view` opens the window, `dump` prints the same model as text so
the model and inference layers can be checked on a machine with no display.
The command may be omitted, so `vrf_view.py some.vrf` opens the viewer.

The name mirrors vrf_net.py against vrfnet/: a root script cannot share a name
with a package beside it, because the package wins the import and `import
vrfview` would then never reach this module.
"""

from __future__ import annotations

import argparse
import sys

from vrf_reader import VrfError, _fmt_ms
from vrfview.infer import annotate
from vrfview.loader import load
from vrfview.model import TEAM_A, TEAM_B
from vrfview.state import state_at

COMMANDS = ("view", "dump")


def cmd_dump(args: argparse.Namespace) -> int:
    """Print the whole derived model, without needing a display."""
    replay = annotate(load(args.path))

    print(f"source          {replay.source}")
    print(f"map             {replay.map_name}  ({replay.map_path})  [name inferred]")
    print(f"recorded        {replay.recorded_utc}")
    print(f"build           {replay.build}")
    print(f"length          {_fmt_ms(replay.length_ms)}  ({replay.length_ms:,} ms)")
    print(
        f"content         {len(replay.rounds)} rounds, {len(replay.players)} players, "
        f"{len(replay.kills)} kills, {len(replay.ultimates)} ults, "
        f"{len(replay.spike)} spike events"
    )
    if replay.side_swap_ms is not None:
        print(f"side swap       {_fmt_ms(replay.side_swap_ms)}")
    a, b = replay.score
    print(f"score           A {a} - {b} B   [inferred; undecided rounds excluded]")

    final = state_at(replay, replay.length_ms)
    print("\nplayers  [teams inferred from the kill graph]")
    print(f"  {'label':<6}{'actor':>7}{'K':>5}{'D':>5}   merged from")
    for team in (TEAM_A, TEAM_B):
        for p in replay.team(team):
            k, d = final.kd.get(p.actor_id, (0, 0))
            merged = ", ".join(str(m) for m in p.merged_from) or "-"
            print(f"  {p.label:<6}{p.actor_id:>7}{k:>5}{d:>5}   {merged}")

    print("\nrounds  [winner inferred]")
    for r in replay.rounds:
        print(
            f"  R{r.number:<3}{_fmt_ms(r.start_ms):>11} - {_fmt_ms(r.end_ms):<11}"
            f"{r.winner:>3}  {r.reason}"
        )

    if args.at is not None:
        _print_snapshot(replay, args.at)

    print("\nprovenance")
    for note in replay.notes:
        print(f"  - {note}")
    print(
        "  - no positions exist in this file; the 2D scene is schematic, "
        "not a map"
    )
    return 0


def _print_snapshot(replay, at_ms: int) -> None:
    snap = state_at(replay, at_ms)
    rnd = snap.round.number if snap.round else "-"
    print(f"\nsnapshot at {_fmt_ms(snap.t_ms)}  round {rnd}")
    print(f"  spike         {snap.spike_state}")
    print(f"  score         A {snap.score[0]} - {snap.score[1]} B")
    alive = [p.label for p in replay.players if snap.is_alive(p.actor_id)]
    dead = [p.label for p in replay.players if not snap.is_alive(p.actor_id)]
    print(f"  alive         {', '.join(alive) or '-'}")
    print(f"  dead          {', '.join(dead) or '-'}")
    for kill, age in snap.recent_kills:
        killer = replay.player(kill.killer)
        victim = replay.player(kill.victim)
        print(
            f"  recent kill   {killer.label if killer else kill.killer} -> "
            f"{victim.label if victim else kill.victim}  (age {age:.2f})"
        )


def cmd_view(args: argparse.Namespace) -> int:
    """Open the playback window."""
    from vrfview.app import run

    return run(annotate(load(args.path)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", default="view", help="view or dump")
    parser.add_argument("path", nargs="?", help=".vrf file, or a vrf_to_json.py dump")
    parser.add_argument(
        "--at", type=int, default=None, metavar="MS", help="dump: snapshot at this time"
    )
    args = parser.parse_args(argv)

    if args.command not in COMMANDS:
        args.command, args.path = "view", args.command
    if not args.path:
        parser.error("a .vrf or .json path is required")

    try:
        return cmd_dump(args) if args.command == "dump" else cmd_view(args)
    except (VrfError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
