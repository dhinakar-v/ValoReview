"""
Decode the UE replication stream inside a .vrf.

Works on decompressed blocks written by `vrf_reader.py --decode N`, or straight
from a .vrf (decompressing via Oodle as it goes).

Usage
-----
  python vrf_net.py calibrate BLOCK...        resolve the engine version gates
  python vrf_net.py decode    BLOCK...        decode and report health metrics
  python vrf_net.py actors    BLOCK...        channel -> archetype table
  python vrf_net.py exports   BLOCK...        class property tables by handle
  python vrf_net.py replay    FILE.vrf        all REPLAYDATA blocks in order
  python vrf_net.py positions FILE.vrf        per-character movement, decoded

The number that matters is `clean packets`: the fraction of playback packets
whose bunch loop lands exactly on the end of the packet.  A bit-level desync
collapses it immediately, so it doubles as the calibration score and the
regression check.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vrf_reader import REPLAYDATA, Oodle, VrfError, VrfFile
from vrfnet.calibrate import CALIBRATION_FILE, calibrate, load, save
from vrfnet.demodriver import read_demo_frames
from vrfnet.packagemap import ExportTable, GuidCache
from vrfnet.payload_transform import UnsupportedBuildError
from vrfnet.session import ReplaySession


def _blocks_from_args(
    paths: list[str],
    oodle_dll: str | None = None,
    limit: int | None = None,
):
    """Yield (label, decompressed bytes) from block dumps or a .vrf."""
    for path in paths:
        if path.lower().endswith(".vrf"):
            vrf = VrfFile(path)
            oodle = Oodle.discover(oodle_dll)
            for i, block in enumerate(vrf.data_blocks(kinds=(REPLAYDATA,))):
                if limit is not None and i >= limit:
                    break
                raw = oodle.decompress(block.blob(vrf.data), block.decompressed_size)
                yield f"block{i:03d}", raw
        else:
            dump = Path(path)
            yield dump.name, dump.read_bytes()


def _session(
    paths: list[str],
    oodle_dll: str | None,
    *,
    decode_bunches: bool = True,
) -> ReplaySession:
    session = ReplaySession(features=load())
    for label, raw in _blocks_from_args(paths, oodle_dll):
        print(f"  {label}: {len(raw):,} bytes", file=sys.stderr)
        session.feed_block(raw, decode_bunches=decode_bunches)
    return session


def cmd_calibrate(args) -> int:
    session = ReplaySession()
    packets = []
    for _label, raw in _blocks_from_args(args.paths, args.oodle_dll):
        session.feed_block(raw, decode_bunches=False)
        # Re-walk for packet bodies; the session pass primed the export table.
        for frame in read_demo_frames(raw, GuidCache(), ExportTable()):
            packets.extend(frame.packets)
        if len(packets) >= args.limit:
            break
    packets = packets[: args.limit]
    print(f"scoring {len(packets):,} packets", file=sys.stderr)
    result, _ = calibrate(packets)
    print(result.summary())
    if args.save:
        save(result)
        print(f"\nsaved -> {args.out}")
    return 0 if result.is_decisive else 1


def cmd_decode(args) -> int:
    session = _session(args.paths, args.oodle_dll)
    print(session.stats.report())
    return 0


def cmd_actors(args) -> int:
    session = _session(args.paths, args.oodle_dll)
    table = session.channels.by_archetype()
    print(
        f"{len(session.channels):,} open channels, "
        f"{len(table):,} distinct archetypes\n",
    )
    for path, channels in sorted(table.items(), key=lambda kv: -len(kv[1])):
        idxs = ", ".join(
            str(c.ch_index) for c in sorted(channels, key=lambda c: c.ch_index)[:12]
        )
        print(f"{len(channels):>4}  {path}")
        print(f"      channels: {idxs}")
    return 0


def cmd_exports(args) -> int:
    session = _session(args.paths, args.oodle_dll, decode_bunches=False)
    groups = sorted(session.exports.by_path.items())
    print(f"{len(groups):,} export groups\n")
    for path, group in groups:
        if args.filter and args.filter.lower() not in path.lower():
            continue
        print(f"{path}  ({len(group.exports)}/{group.num_exports} seen)")
        for handle, export in sorted(group.exports.items())[: args.max_props]:
            print(f"    {handle:>4}  {export.name}")
    return 0


def cmd_positions(args) -> int:
    """
    Decode player movement and report each character's trajectory.

    The check that matters is not the move count but the shape: at the first
    frame the ten players must sit in two tight clusters, one per spawn, which
    is a fact about the map that no decoding bug could invent.
    """
    branch = args.branch or _branch_from(args.paths)
    if not branch:
        print(
            "error: no build branch; pass --branch for block dumps",
            file=sys.stderr,
        )
        return 1

    session = ReplaySession(features=load(), branch=branch, collect_movement=True)
    for label, raw in _blocks_from_args(args.paths, args.oodle_dll, limit=args.blocks):
        print(f"  {label}: {len(raw):,} bytes", file=sys.stderr)
        session.feed_block(raw)

    print(f"branch            {branch}")
    print(session.props.report())
    print(session.movement.report())

    log = session.movement
    if not log.samples:
        print("\nNo movement decoded.")
        return 1

    print("\ncharacters  [net guid is the same id characterDeath events carry]")
    print(f"  {'guid':>7}{'moves':>9}   {'x range':>19}   {'y range':>19}   first seen")
    ranked = sorted(log.samples.items(), key=lambda kv: -len(kv[1]))
    for guid, samples in ranked:
        x0, x1, y0, y1 = log.bounds(guid)
        first = samples[0][1]
        print(
            f"  {guid:>7}{len(samples):>9,}   "
            f"[{x0:8.0f},{x1:8.0f}]   [{y0:8.0f},{y1:8.0f}]   "
            f"({first.position.x:.0f}, {first.position.y:.0f}) yaw {first.yaw:.0f}",
        )
    return 0


def _branch_from(paths: list[str]) -> str:
    """The build branch, read from the first .vrf among the inputs."""
    for path in paths:
        if path.lower().endswith(".vrf"):
            return VrfFile(path).demo.build
    return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "command",
        choices=("calibrate", "decode", "actors", "exports", "replay", "positions"),
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="decompressed block dumps, or a .vrf file",
    )
    parser.add_argument(
        "--oodle-dll",
        help="oo2core_*_win64.dll for .vrf input (else vendor/, .env or a game)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8000,
        help="packets to score during calibration",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="persist the calibration result",
    )
    parser.add_argument("--out", default=str(CALIBRATION_FILE))
    parser.add_argument("--filter", help="substring filter for exports")
    parser.add_argument(
        "--branch",
        help="build branch for block dumps; read from the header for a .vrf",
    )
    parser.add_argument(
        "--blocks",
        type=int,
        default=2,
        help="REPLAYDATA blocks to decode for positions (default 2)",
    )
    parser.add_argument("--max-props", type=int, default=20)
    args = parser.parse_args(argv)

    commands = {
        "calibrate": cmd_calibrate,
        "decode": cmd_decode,
        "replay": cmd_decode,
        "actors": cmd_actors,
        "exports": cmd_exports,
        "positions": cmd_positions,
    }
    try:
        return commands[args.command](args)
    except UnsupportedBuildError as exc:
        # Deliberately fatal: guessing a transform yields plausible rubbish.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (VrfError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
