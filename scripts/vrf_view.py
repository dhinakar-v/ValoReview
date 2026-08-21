"""
Play a .vrf replay back in 2D.

Three commands: `view` opens the window, `dump` prints the same model as text so
the model and inference layers can be checked on a machine with no display, and
`catalog` reports (or refreshes) the Riot content catalogue that turns the map
path and the agent UUIDs in a replay into names.  The command may be omitted, so
`vrf_view.py some.vrf` opens the viewer.

Names come from a cache, never from a live call, unless --refresh is passed.
`view` and `dump` therefore work offline, with no RIOT_API key, on a checkout
that has never talked to Riot -- they simply fall back to the built-in codename
table and say so.  See docs/valorant-api.md.

The name mirrors vrf_net.py against vrfnet/.  The script lives in scripts/ and
the package in libraries/vrfview/, so the two no longer sit side by side and the
old collision -- where a same-named package wins the import and `import vrfview`
never reaches this module -- cannot happen; the names are kept for continuity.
"""

from __future__ import annotations

import argparse
import importlib
import sys

import valapi
import valcatalog
from vrf_reader import VrfError, _fmt_ms
from vrfview import art as art_mod
from vrfview import tracks
from vrfview.infer import annotate
from vrfview.loader import load
from vrfview.model import TEAM_A, TEAM_B
from vrfview.names import resolve
from vrfview.state import state_at

COMMANDS = ("view", "dump", "catalog")

# Every val-match-v1 endpoint 403s on a personal development key, so a match id
# read from a replay cannot yet be turned into a MatchDto.  Said once, here.
MATCH_GATE = "val-match-v1 lookup needs a production key"


def build_catalog(args: argparse.Namespace) -> valcatalog.Catalog | None:
    """
    The catalogue for this run.  --refresh is the only path that opens a socket.

    A failed refresh is a warning, not a stop: the cached catalogue, or the
    built-in table, still names the map.  The diagnosis printed with it is the
    one docs/valorant-api.md prescribes -- val-status-v1 takes no identifier, so
    a 200 from it proves the key and User-Agent are fine and the other failure
    is an access grant.
    """
    if args.no_catalog:
        return None
    if args.refresh:
        try:
            return valcatalog.refresh(args.shard, args.locale)
        except (valapi.RiotApiError, OSError) as exc:
            live, why = valapi.key_state(args.shard)
            print(f"warning: catalogue refresh failed: {exc}", file=sys.stderr)
            print(f"  val-status-v1 says: {why}", file=sys.stderr)
            if live:
                print(
                    "  so the key works and this is an access or network problem",
                    file=sys.stderr,
                )
    return valcatalog.load(args.catalog, args.locale)


def build_art(args: argparse.Namespace) -> art_mod.ArtCache:
    """
    The art cache for this run.  Never networked, and never fatal.

    Separate from build_catalog because the two answer different questions: a
    catalogue says what the map and the agents are *called*, this says which
    PNGs happen to be on disk.  A missing or mistyped --assets yields an empty
    cache that reports the path it tried, rather than an error, because art
    changes nothing the viewer claims.
    """
    if args.no_art:
        return art_mod.ArtCache(reason="art disabled (--no-art)")
    return art_mod.load(args.assets)


def read_replay(args: argparse.Namespace):
    """
    Read, decode, infer, then name -- in that order, for both commands.

    Positions come second because they are read facts and everything after
    them derives or looks up: infer needs the codenames to cross-check its
    team split, and names needs them to say who anybody is.  They are also
    the only step that can take minutes, which is why nothing asks for them
    unless --positions did.
    """
    replay = load(args.path)
    if args.positions:
        tracks.attach(replay, args.path, _decode_options(args))
    else:
        replay.position_source = tracks.NOT_REQUESTED
    return resolve(annotate(replay), build_catalog(args))


def _decode_options(args: argparse.Namespace) -> tracks.Options:
    """Decode knobs, with progress on stderr because this is the slow part."""

    def progress(done: int, total: int) -> None:
        print(f"  decoding block {done}/{total}", end="\r", file=sys.stderr)
        if done == total:
            print(file=sys.stderr)

    return tracks.Options(
        oodle_dll=args.oodle_dll,
        blocks=args.blocks,
        progress=progress,
    )


def cmd_dump(args: argparse.Namespace) -> int:
    """Print the whole derived model, without needing a display."""
    replay = read_replay(args)

    print(f"source          {replay.source}")
    if replay.match_id:
        print(f"match id        {replay.match_id}  [{MATCH_GATE}]")
    print(
        f"map             {replay.map_name}  ({replay.map_path})  "
        f"[{replay.map_name_source}]",
    )
    print(f"recorded        {replay.recorded_utc}")
    print(f"build           {replay.build}")
    print(f"length          {_fmt_ms(replay.length_ms)}  ({replay.length_ms:,} ms)")
    print(
        f"content         {len(replay.rounds)} rounds, {len(replay.players)} players, "
        f"{len(replay.kills)} kills, {len(replay.ultimates)} ults, "
        f"{len(replay.spike)} spike events",
    )
    if replay.side_swap_ms is not None:
        print(f"side swap       {_fmt_ms(replay.side_swap_ms)}")
    a, b = replay.score
    print(f"score           A {a} - {b} B   [inferred; undecided rounds excluded]")

    _print_players(replay)
    _print_roster(replay, build_art(args))

    print("\nrounds  [winner inferred]")
    for r in replay.rounds:
        print(
            f"  R{r.number:<3}{_fmt_ms(r.start_ms):>11} - {_fmt_ms(r.end_ms):<11}"
            f"{r.winner:>3}  {r.reason}",
        )

    if args.at is not None:
        _print_snapshot(replay, args.at)

    print("\nprovenance")
    print(f"  - catalogue: {replay.catalog_source}")
    for line in art_mod.coverage(
        build_art(args),
        replay.map_path,
        [x.character_id for x in replay.loadouts],
    ):
        print(f"  - art: {line}")
    for note in replay.catalog_notes:
        print(f"  - looked up: {note}")
    for note in replay.notes:
        print(f"  - {note}")
    print(f"  - positions: {replay.position_source}")
    if not replay.has_positions:
        print("  - with no positions the 2D scene is schematic, not a map")
    return 0


def _print_players(replay) -> None:
    """
    The player table: read identity, inferred team, decoded track length.

    `agent` and `codename` sit here rather than on the roster table below
    because these come from the actor itself, and the roster still comes from
    a loadout list that names no actor.
    """
    final = state_at(replay, replay.length_ms)
    print("\nplayers  [teams inferred from the kill graph; agents read from the wire]")
    print(
        f"  {'label':<6}{'actor':>7}{'K':>5}{'D':>5}  {'agent':<10}{'codename':<12}"
        f"{'samples':>9}   merged from",
    )
    for team in (TEAM_A, TEAM_B):
        for p in replay.team(team):
            k, d = final.kd.get(p.actor_id, (0, 0))
            merged = ", ".join(str(m) for m in p.merged_from) or "-"
            track = replay.track(p.actor_id)
            samples = f"{len(track):,}" if track else "-"
            print(
                f"  {p.label:<6}{p.actor_id:>7}{k:>5}{d:>5}  {p.agent or '-':<10}"
                f"{p.codename or '-':<12}{samples:>9}   {merged}",
            )


def _print_roster(replay, art: art_mod.ArtCache) -> None:
    """
    The loadout list, agent names filled in where a catalogue answered.

    Deliberately its own section rather than a column on the player table: the
    file links loadouts to no actor net ID, so lining the two up would imply a
    correspondence that does not exist.  The art column is the icon the viewer
    would draw, so resolution can be checked on a machine with no display.
    """
    if not replay.loadouts:
        return
    print("\nagents  [roster order from the file; not attributable to actor ids]")
    print(f"  {'#':<3}{'agent':<12}{'characterId':<38}{'subject':<38}icon")
    for x in replay.loadouts:
        entry = art.agent_art(x.character_id)
        icon = "-" if entry is None or entry.icon is None else str(entry.icon)
        print(
            f"  {x.index:<3}{x.display:<12}{x.character_id:<38}{x.subject:<38}{icon}",
        )


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
            f"{victim.label if victim else kill.victim}  (age {age:.2f})",
        )


def cmd_catalog(args: argparse.Namespace) -> int:
    """Report the local content catalogue, and refresh it when asked."""
    catalog = build_catalog(args) or valcatalog.Catalog()

    print("cache search order  [first readable one wins]")
    for path in valcatalog.candidates(args.catalog, args.locale):
        print(f"  {'found  ' if path.exists() else 'missing'}  {path}")

    art = build_art(args)
    print(f"\ncatalogue       {catalog.described}")
    print(f"art cache       {art.described}")
    print(f"key             {_key_presence()}")
    print(f"routing         shard {args.shard}, locale {args.locale}")

    _print_art(art)

    if catalog.empty:
        print(
            "\nNo catalogue is cached, so map and agent names fall back to the\n"
            "built-in codename table and agent UUIDs stay unresolved.  Either:\n"
            "  runners\\vrf-view.bat catalog --refresh   val-content-v1, needs "
            f"{valapi.KEY_VAR}\n"
            "  runners\\fetch-assets.bat fetch --only agents --only maps\n"
            "                                          valorant-api.com, needs no key",
        )
        return 1

    print("\nsample joins  [what a replay actually looks up]")
    for path, name in sorted(catalog.maps.items())[:3]:
        print(f"  map    {path:<42} {name}")
    for uuid, name in sorted(catalog.agents.items())[:3]:
        print(f"  agent  {uuid:<42} {name}")
    print(
        f"\nval-match-v1 is not used: {MATCH_GATE}, so a replay's match id is\n"
        "reported and never looked up.  See docs/valorant-api.md.",
    )
    return 0


def _print_art(art: art_mod.ArtCache) -> None:
    """
    What the art cache holds, and what the viewer will therefore draw.

    Reported beside the name cache because both live under assets/ and get
    conflated; they are different files answering different questions, and only
    the catalogue affects what the viewer claims.
    """
    print(f"\nart manifest    {art_mod.manifest_path(art.root)}")
    if art.empty:
        print(
            "  No art is cached, so the viewer shows no roster band and no\n"
            "  map reference window.  Names and inference are unaffected.\n"
            "    runners\\fetch-assets.bat fetch      263 files, needs no key",
        )
        return
    plottable = sum(1 for m in art.maps.values() if m.plottable)
    icons = sum(1 for a in art.agents.values() if a.icon is not None)
    print(f"  {plottable}/{len(art.maps)} maps have a radar image and a transform")
    print(f"  {icons}/{len(art.agents)} agents have an icon on disk")


def _key_presence() -> str:
    """Whether a key is configured. The key itself is never printed."""
    try:
        valapi.api_key()
    except valapi.MissingKeyError:
        return f"no {valapi.KEY_VAR} configured (only --refresh needs one)"
    return f"{valapi.KEY_VAR} is set"


def cmd_view(args: argparse.Namespace) -> int:
    """
    Open the playback window.

    vrfview.app is loaded here rather than at the top of the module because it
    imports tkinter, and `dump` has to keep working on a Python with no Tk at
    all.  importlib says that is deliberate; a plain import inside a function
    reads like an oversight.
    """
    app = importlib.import_module("vrfview.app")

    return app.run(read_replay(args), build_art(args))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", default="view", help=", ".join(COMMANDS))
    parser.add_argument("path", nargs="?", help=".vrf file, or a vrf_to_json.py dump")
    parser.add_argument(
        "--at",
        type=int,
        default=None,
        metavar="MS",
        help="dump: snapshot at this time",
    )
    parser.add_argument(
        "--catalog",
        metavar="PATH",
        help="content catalogue cache to use instead of the default search",
    )
    parser.add_argument(
        "--locale",
        default=valapi.DEFAULT_LOCALE,
        help=f"catalogue locale (default {valapi.DEFAULT_LOCALE})",
    )
    parser.add_argument(
        "--shard",
        default=valapi.DEFAULT_SHARD,
        choices=valapi.SHARDS,
        help=f"val-* shard host for --refresh (default {valapi.DEFAULT_SHARD})",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help=f"fetch val-content-v1 and rewrite the cache; needs {valapi.KEY_VAR}",
    )
    parser.add_argument(
        "--no-catalog",
        action="store_true",
        help="ignore any catalogue and use the built-in codename table",
    )
    parser.add_argument(
        "--assets",
        metavar="DIR",
        default=None,
        help=f"art cache directory (default {art_mod.ASSETS_DIR})",
    )
    parser.add_argument(
        "--no-art",
        action="store_true",
        help="ignore the art cache; the viewer draws no icons or map image",
    )
    parser.add_argument(
        "--positions",
        action="store_true",
        help="decode player positions and agents from the replication stream; "
        "needs Oodle and takes minutes on a full match",
    )
    parser.add_argument(
        "--blocks",
        type=int,
        default=None,
        metavar="N",
        help="stop after N REPLAYDATA blocks when decoding positions",
    )
    parser.add_argument(
        "--oodle-dll",
        metavar="PATH",
        help="oo2core_*_win64.dll to use when decoding positions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.command not in COMMANDS:
        args.command, args.path = "view", args.command
    if args.command != "catalog" and not args.path:
        parser.error("a .vrf or .json path is required")

    try:
        if args.command == "catalog":
            return cmd_catalog(args)
        return cmd_dump(args) if args.command == "dump" else cmd_view(args)
    except (VrfError, valapi.RiotApiError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
