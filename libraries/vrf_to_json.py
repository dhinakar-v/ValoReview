"""
Dump one Valorant .vrf replay to a single JSON document.

Everything the container exposes structurally is emitted: the container
header, the UE demo header and its embedded GameSpecificData blobs, the full
chunk table, every EVENT record, and the framing of every Oodle-compressed
REPLAYDATA / CHECKPOINT block.

Compressed blocks are decompressed (Oodle Mermaid) and mined for the parts
that are byte-addressable: the demo frame header and the NetGUID/property
name table.  The replication payload after that table is a bit-packed UE net
stream whose meaning depends on the game's class layouts, so it is reported
as size + digest rather than invented structure.  Use --payload-dir to keep
the decompressed bytes, or --inline-payloads to base64 them into the JSON.

Usage
-----
  python vrf_to_json.py <file.vrf> -o out.json
  python vrf_to_json.py <file.vrf> -o out.json --payload-dir blocks/
  python vrf_to_json.py <file.vrf> -o out.json --no-decompress
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
import sys
from pathlib import Path

from vrf_reader import (
    EVENT,
    EVENT_TYPE_ID_SIZE,
    HEADER,
    REPLAYDATA,
    Oodle,
    Reader,
    VrfError,
    VrfFile,
    _iter_fstrings,
    _parse_event_payload,
)


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _ms(ms: int) -> str:
    return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------
def dump_container_header(vrf: VrfFile) -> dict:
    h = vrf.header
    ts = h.recorded_utc
    return {
        "magic": f"0x{h.magic:08X}",
        "file_version": h.file_version,
        "unknown_08": h.unknown_08,
        "guid": h.guid,
        "unknown_1c": h.unknown_1c,
        "length_ms": h.length_ms,
        "length_formatted": _ms(h.length_ms),
        "network_version": h.network_version,
        "changelist": h.changelist,
        "friendly_name": h.friendly_name,
        "is_live": h.is_live,
        "timestamp_ticks": h.timestamp_ticks,
        "recorded_utc": ts.isoformat() if ts else None,
        "flag_a_compressed": h.flag_a,
        "flag_b_encrypted": h.flag_b,
        "trailing_array_len": h.trailing_len,
        "chunks_start": h.chunks_start,
    }


def dump_demo_header(vrf: VrfFile) -> dict:
    d = vrf.demo
    hdr = next(c for c in vrf.chunks if c.type == HEADER)
    return {
        "magic": f"0x{d.magic:08X}",
        "version": d.version,
        "build": d.build,
        "changelist": d.changelist,
        "maps": d.maps,
        "chunk_offset": hdr.offset,
        "chunk_size": hdr.size,
        "game_specific_data": [
            {
                "index": i,
                "bytes": len(raw),
                "parse_error": parsed is None,
                "parsed": parsed,
            }
            for i, (raw, parsed) in enumerate(
                zip(d.raw_json, d.json_blobs, strict=True),
            )
        ],
    }


def dump_chunks(vrf: VrfFile) -> list:
    return [
        {
            "index": i,
            "type": c.type,
            "name": c.name,
            "header_offset": c.offset - 8,
            "payload_offset": c.offset,
            "size": c.size,
        }
        for i, c in enumerate(vrf.chunks)
    ]


def dump_events(vrf: VrfFile) -> list:
    """Re-read EVENT chunks so the raw payload travels with each record."""
    out = []
    for c in vrf.chunks:
        if c.type != EVENT:
            continue
        r = Reader(vrf.data, c.offset)
        ev_id = r.fstring()
        group = r.fstring()
        meta = r.fstring()
        time1 = r.u32()
        time2 = r.u32()
        payload = r.bytes(r.u32())
        enum_name, args, time_s = _parse_event_payload(payload)
        out.append(
            {
                "chunk_offset": c.offset,
                "id": ev_id,
                "group": group,
                "metadata": meta,
                "time1_ms": time1,
                "time2_ms": time2,
                "time_formatted": _ms(time2),
                "enum_name": enum_name,
                "type_id": (
                    struct.unpack_from("<I", payload, 0)[0]
                    if len(payload) >= EVENT_TYPE_ID_SIZE
                    else None
                ),
                "args": args,
                "time_seconds": time_s,
                "payload_bytes": len(payload),
                "payload_hex": payload.hex(),
            },
        )
    out.sort(key=lambda e: e["time2_ms"])
    return out


def dump_match_metadata(vrf: VrfFile):
    md = vrf.match_metadata()
    if not md:
        return None
    loadouts = md.get("playerLoadouts", [])
    return {
        "top_level_keys": sorted(md),
        "player_count": len(loadouts),
        "players": [
            {
                "index": i,
                "subject": p.get("subject"),
                "characterId": p.get("characterId"),
            }
            for i, p in enumerate(loadouts)
        ],
        "raw": md,
    }


def decode_block(vrf: VrfFile, index: int, b, oodle, opts) -> dict:
    """Framing for one compressed block, plus what its plaintext gives up."""
    rec = {
        "index": index,
        "kind": b.chunk.name,
        "label": b.label,
        "chunk_offset": b.chunk.offset,
        "blob_offset": b.blob_offset,
        "time1_ms": b.time1,
        "time2_ms": b.time2,
        "time1_formatted": _ms(b.time1),
        "time2_formatted": _ms(b.time2),
        "size": b.size,
        "memory_size": b.memory_size,
        "compressed_size": b.compressed_size,
        "decompressed_size": b.decompressed_size,
        "ratio": round(b.ratio, 4),
        "codec": b.oodle_codec(vrf.data),
        "compressed_sha256": _sha256(b.blob(vrf.data)),
    }
    if oodle is None:
        rec["decompressed"] = None
        return rec

    raw = oodle.decompress(b.blob(vrf.data), b.decompressed_size)
    dec = {"sha256": _sha256(raw), "bytes": len(raw)}

    if b.chunk.type == REPLAYDATA:
        r = Reader(raw)
        dec["frame_header"] = {"level_index": r.u32(), "time_seconds": r.f32()}
        names = list(_iter_fstrings(raw, 8))
    else:
        dec["frame_header"] = None
        dec["preamble_hex"] = raw[:16].hex()
        names = list(_iter_fstrings(raw))

    paths = [n for n in names if n.startswith("/")]
    dec["name_table"] = {
        "total": len(names),
        "asset_paths": len(paths),
        "property_names": len(names) - len(paths),
        "unique_asset_paths": sorted(set(paths)),
        "unique_property_names": sorted({n for n in names if not n.startswith("/")}),
    }
    if opts.name_sequence:
        dec["name_table"]["sequence"] = names
    dec["replication_stream"] = {
        "decoded": False,
        "note": "bit-packed UE net stream; decoding needs the game's class layouts",
    }
    if opts.inline_payloads:
        dec["raw_base64"] = base64.b64encode(raw).decode("ascii")
    if opts.payload_dir:
        payload_dir = Path(opts.payload_dir)
        payload_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"_{b.label}" if b.label else ""
        dest = payload_dir / f"block{index:03d}_{b.chunk.name.lower()}{suffix}.bin"
        dest.write_bytes(raw)
        dec["raw_file"] = str(dest)

    rec["decompressed"] = dec
    return rec


# --------------------------------------------------------------------------
def build(vrf: VrfFile, oodle, opts) -> dict:
    counts, sizes = {}, {}
    for c in vrf.chunks:
        counts[c.name] = counts.get(c.name, 0) + 1
        sizes[c.name] = sizes.get(c.name, 0) + c.size

    events = dump_events(vrf)
    groups = {}
    for e in events:
        groups[e["group"]] = groups.get(e["group"], 0) + 1

    doc = {
        "source": {
            "path": str(vrf.path.resolve()),
            "file_name": vrf.path.name,
            "size_bytes": len(vrf.data),
            "sha256": _sha256(vrf.data),
        },
        "oodle": {
            "dll": str(oodle.path) if oodle else None,
            "used": oodle is not None,
        },
        "container_header": dump_container_header(vrf),
        "demo_header": dump_demo_header(vrf),
        "obfuscation": vrf.check_obfuscation(),
        "chunk_summary": {
            "total": len(vrf.chunks),
            "by_type": {
                k: {"count": counts[k], "bytes": sizes[k]} for k in sorted(counts)
            },
        },
        "chunks": dump_chunks(vrf),
        "match_metadata": dump_match_metadata(vrf),
        "event_summary": {
            "total": len(events),
            "by_group": dict(sorted(groups.items(), key=lambda kv: -kv[1])),
        },
        "events": events,
        "data_blocks": [],
    }

    blocks = vrf.data_blocks()
    for i, b in enumerate(blocks):
        if oodle is not None:
            print(
                f"  block {i + 1}/{len(blocks)}  {b.chunk.name:<10} "
                f"{b.compressed_size:>10,} -> {b.decompressed_size:>11,}",
                file=sys.stderr,
            )
        doc["data_blocks"].append(decode_block(vrf, i, b, oodle, opts))
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dump a .vrf replay to JSON.")
    ap.add_argument("path")
    ap.add_argument("-o", "--out", required=True, help="output .json path")
    ap.add_argument(
        "--oodle-dll",
        metavar="PATH",
        help="path to oo2core_*_win64.dll (else vendor/, .env or an installed game)",
    )
    ap.add_argument(
        "--no-decompress",
        action="store_true",
        help="skip Oodle; emit compressed-block framing only",
    )
    ap.add_argument(
        "--payload-dir",
        metavar="DIR",
        help="write each decompressed block as .bin",
    )
    ap.add_argument(
        "--inline-payloads",
        action="store_true",
        help="base64 every decompressed block into the JSON (very large)",
    )
    ap.add_argument(
        "--name-sequence",
        action="store_true",
        help="keep each block's full ordered name table, not just the unique sets",
    )
    ap.add_argument(
        "--positions",
        action="store_true",
        help="also decode player positions into a <out>.positions.json sidecar "
        "(slow: needs Oodle, minutes on a full match, supported builds only)",
    )
    ap.add_argument(
        "--positions-hz",
        type=int,
        default=None,
        metavar="HZ",
        help="sample rate for the positions sidecar (default: the model's 10 Hz)",
    )
    ap.add_argument(
        "--positions-blocks",
        type=int,
        default=None,
        metavar="N",
        help="stop the position decode after N REPLAYDATA blocks",
    )
    ap.add_argument("--indent", type=int, default=2)
    args = ap.parse_args(argv)

    try:
        vrf = VrfFile(args.path)
        oodle = None if args.no_decompress else Oodle.discover(args.oodle_dll)
        doc = build(vrf, oodle, args)
        out = Path(args.out)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=args.indent, ensure_ascii=False)
    except (VrfError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {out}  ({out.stat().st_size:,} bytes)", file=sys.stderr)
    if args.positions:
        return dump_positions(args.path, out, args)
    return 0


def dump_positions(vrf_path: str, out: Path, args) -> int:
    """
    Decode positions for `vrf_path` and write the sidecar belonging to `out`.

    The imports are local, and deliberately so.  This module is the container
    layer: it reads chunks and knows nothing about the viewer.  Positions come
    out of the replication stream through `vrfview.tracks`, which sits two
    layers up and pulls in the whole vrfnet decoder, so importing it at module
    scope would make every `vrf-to-json` run pay for a decoder it almost never
    uses -- and would invert the layering the rest of the file keeps.

    Failing here is not fatal to the dump, which is already written, but it is
    reported as a failure: positions were asked for by name, and a silent exit
    0 with no sidecar is how a scripted pipeline ends up drawing nothing.
    """
    from vrfview import loader, tracks  # noqa: PLC0415  (layering; see above)

    options = tracks.Options(
        oodle_dll=args.oodle_dll,
        blocks=args.positions_blocks,
        hz=args.positions_hz or tracks.POSITION_HZ,
        progress=lambda done, total: print(
            f"  positions: block {done}/{total}",
            file=sys.stderr,
        ),
    )
    try:
        replay = loader.load(vrf_path)
        found = tracks.extract(
            vrf_path,
            {p.actor_id for p in replay.players},
            options,
        )
    except (tracks.UnsupportedBuildError, VrfError, OSError) as exc:
        print(f"error: no positions written: {exc}", file=sys.stderr)
        return 1

    side = tracks.save(out, replay, found)
    print(
        f"wrote {side}  ({side.stat().st_size:,} bytes)\n  {found.described}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
