"""
Reader for Valorant replay files (.vrf).

A .vrf is an Unreal Engine "local file" replay container with Riot-specific
additions.  Nothing in it is encrypted, but the REPLAYDATA and CHECKPOINT
payloads are Oodle-compressed (Mermaid) and need an oo2core runtime to read;
see Oodle.discover() and check_obfuscation().

Layout
------
  [container header]                       fixed prefix + UTF-16 friendly name
  [chunk][chunk]...                        each: uint32 type, uint32 size, payload

  chunk type 0 HEADER      -> FNetworkDemoHeader: build string, map list,
                              and two JSON blobs (GameSpecificData)
  chunk type 1 REPLAYDATA  -> Oodle-compressed UE net stream
  chunk type 2 CHECKPOINT  -> Oodle-compressed periodic world snapshot
  chunk type 3 EVENT       -> game events (roundStarted, characterDeath, ...)

Usage
-----
  python vrf_reader.py <file.vrf>                 summary
  python vrf_reader.py <file.vrf> --events        event timeline
  python vrf_reader.py <file.vrf> --players       players / agents from metadata
  python vrf_reader.py <file.vrf> --dump-json OUT write embedded JSON blobs
  python vrf_reader.py <file.vrf> --chunks        chunk table
  python vrf_reader.py <file.vrf> --decode N      decompress+decode block N
  python vrf_reader.py <file.vrf> --blocks        compressed block table
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as _dt
import json
import os
import re
import struct
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field

CONTAINER_MAGIC = 0x43F4EFDD  # Riot .vrf container
DEMO_MAGIC = 0x2CF5A13D  # UE FNetworkDemoHeader

HEADER, REPLAYDATA, CHECKPOINT, EVENT = 0, 1, 2, 3
CHUNK_NAMES = {
    HEADER: "HEADER",
    REPLAYDATA: "REPLAYDATA",
    CHECKPOINT: "CHECKPOINT",
    EVENT: "EVENT",
}

# .NET DateTime ticks -> unix epoch
_TICKS_AT_EPOCH = 621_355_968_000_000_000


class VrfError(Exception):
    pass


# --------------------------------------------------------------------------
# UE FArchive primitives
# --------------------------------------------------------------------------
class Reader:
    """Little-endian cursor over a bytes buffer, with UE FString support."""

    def __init__(self, buf: bytes, pos: int = 0):
        self.buf = buf
        self.pos = pos

    @property
    def remaining(self) -> int:
        return len(self.buf) - self.pos

    def _unpack(self, fmt: str, size: int):
        if self.pos + size > len(self.buf):
            raise VrfError(f"read past end at {self.pos}")
        value = struct.unpack_from(fmt, self.buf, self.pos)[0]
        self.pos += size
        return value

    def u32(self) -> int:
        return self._unpack("<I", 4)

    def i32(self) -> int:
        return self._unpack("<i", 4)

    def i64(self) -> int:
        return self._unpack("<q", 8)

    def f32(self) -> float:
        return self._unpack("<f", 4)

    def bytes(self, n: int) -> bytes:
        if self.pos + n > len(self.buf):
            raise VrfError(f"read past end at {self.pos}")
        b = self.buf[self.pos : self.pos + n]
        self.pos += n
        return b

    def guid(self) -> str:
        a, b, c, d = struct.unpack_from("<4I", self.buf, self.pos)
        self.pos += 16
        return f"{a:08X}{b:08X}{c:08X}{d:08X}"

    def fstring(self) -> str:
        """UE FString: positive length = ANSI/UTF-8, negative = UTF-16LE.

        The stored length includes the trailing NUL.
        """
        n = self.i32()
        if n == 0:
            return ""
        if n < 0:
            raw = self.bytes(-n * 2)
            return raw[:-2].decode("utf-16-le", "replace")
        raw = self.bytes(n)
        return raw[:-1].decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass
class Chunk:
    type: int
    offset: int  # offset of the payload, after the 8-byte chunk header
    size: int

    @property
    def name(self) -> str:
        return CHUNK_NAMES.get(self.type, f"UNKNOWN({self.type})")


@dataclass
class Event:
    group: str  # "characterDeath", "roundStarted", ...
    id: str  # replayId_eventGuid
    meta: str
    time_ms: int
    enum_name: str  # "EReplayEventGroup::CharacterDeath"
    args: list  # event-specific uint32 arguments
    time_s: float  # float seconds stored in the payload (None if absent)
    offset: int


@dataclass
class ContainerHeader:
    magic: int
    file_version: int
    unknown_08: int
    guid: str
    unknown_1c: int
    length_ms: int
    network_version: int
    changelist: int
    friendly_name: str
    is_live: int
    timestamp_ticks: int
    flag_a: int  # compression-style flag, see check_obfuscation()
    flag_b: int
    trailing_len: int  # UE stores the encryption key array here; 0 == absent
    chunks_start: int

    @property
    def recorded_utc(self):
        if self.timestamp_ticks <= _TICKS_AT_EPOCH:
            return None
        secs = (self.timestamp_ticks - _TICKS_AT_EPOCH) / 1e7
        return _dt.datetime.fromtimestamp(secs, _dt.timezone.utc)


@dataclass
class DemoHeader:
    magic: int
    version: int
    build: str = ""
    changelist: str = ""
    maps: list = field(default_factory=list)
    json_blobs: list = field(default_factory=list)
    raw_json: list = field(default_factory=list)


@dataclass
class DataBlock:
    """One Oodle-compressed payload block (REPLAYDATA or CHECKPOINT)."""

    chunk: Chunk
    label: str
    time1: int
    time2: int
    size: int
    memory_size: int
    decompressed_size: int
    compressed_size: int
    blob_offset: int

    def blob(self, data: bytes) -> bytes:
        return data[self.blob_offset : self.blob_offset + self.compressed_size]

    def oodle_codec(self, data: bytes) -> str:
        """Identify the Oodle codec from the 2-byte block header."""
        b0, b1 = data[self.blob_offset], data[self.blob_offset + 1]
        if b0 & 0x0F != 0x0C:
            return f"unknown(0x{b0:02X}{b1:02X})"
        return OODLE_CODECS.get(b1 & 0x7F, f"OodleType{b1 & 0x7F}")

    @property
    def ratio(self) -> float:
        return self.decompressed_size / self.compressed_size


# Oodle decoder-type byte -> codec name
OODLE_CODECS = {5: "LZNA", 6: "Kraken", 10: "Mermaid", 11: "Selkie", 12: "Hydra"}

# Games that ship a redistributable Oodle runtime; any recent one can decode.
_OODLE_DLL_HINTS = (
    r"C:\Program Files\Epic Games",
    r"C:\Program Files (x86)\Steam\steamapps\common",
    r"D:\Games",
    r"E:\Games",
    r"E:\SteamLibrary\steamapps\common",
)


class Oodle:
    """ctypes binding for OodleLZ_Decompress from an oo2core_*_win64.dll.

    Valorant statically links Oodle into its shipping exe, so there is no DLL
    to borrow from the game itself; point --oodle-dll at any oo2core runtime
    (Oodle 2.5+ decodes these blocks) or set the VRF_OODLE_DLL env var.
    """

    def __init__(self, dll_path: str):
        self.path = dll_path
        lib = ctypes.CDLL(dll_path)
        fn = lib.OodleLZ_Decompress
        fn.restype = ctypes.c_ssize_t
        fn.argtypes = [
            ctypes.c_char_p, ctypes.c_ssize_t,   # compressed buffer + size
            ctypes.c_char_p, ctypes.c_ssize_t,   # output buffer + size
            ctypes.c_int, ctypes.c_int, ctypes.c_int,   # fuzzSafe, checkCRC, verbosity
            ctypes.c_void_p, ctypes.c_ssize_t,   # decBufBase, decBufSize
            ctypes.c_void_p, ctypes.c_void_p,    # callback, callback userdata
            ctypes.c_void_p, ctypes.c_ssize_t,   # scratch, scratch size
            ctypes.c_int,                        # thread phase
        ]
        self._fn = fn

    def decompress(self, blob: bytes, out_size: int) -> bytes:
        out = ctypes.create_string_buffer(out_size + 64)
        n = self._fn(blob, len(blob), out, out_size,
                     1, 0, 0, None, 0, None, None, None, 0, 3)
        if n != out_size:
            raise VrfError(
                f"OodleLZ_Decompress returned {n}, expected {out_size}")
        return out.raw[:n]

    @classmethod
    def discover(cls, explicit: str | None = None) -> "Oodle":
        candidates = []
        if explicit:
            candidates.append(explicit)
        env = os.environ.get("VRF_OODLE_DLL")
        if env:
            candidates.append(env)
        for path in candidates:
            if os.path.isfile(path):
                return cls(path)
        for root in _OODLE_DLL_HINTS:
            if not os.path.isdir(root):
                continue
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    if _OODLE_RE.match(name):
                        return cls(os.path.join(dirpath, name))
        raise VrfError(
            "no oo2core_*_win64.dll found; pass --oodle-dll PATH or set VRF_OODLE_DLL")


_OODLE_RE = re.compile(r"^oo2core_\d+_win64\.dll$", re.I)


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------
class VrfFile:
    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as fh:
            self.data = fh.read()
        self.header = self._parse_container_header()
        self.chunks = list(self._walk_chunks())
        self.demo = self._parse_demo_header()

    # ---- container ------------------------------------------------------
    def _parse_container_header(self) -> ContainerHeader:
        r = Reader(self.data)
        magic = r.u32()
        if magic != CONTAINER_MAGIC:
            raise VrfError(
                f"not a .vrf: magic 0x{magic:08X}, expected 0x{CONTAINER_MAGIC:08X}"
            )
        file_version = r.u32()
        unknown_08 = r.u32()
        guid = r.guid()
        unknown_1c = r.u32()
        length_ms = r.u32()
        network_version = r.u32()
        changelist = r.u32()
        friendly_name = r.fstring().rstrip(" \0")
        is_live = r.u32()
        timestamp = r.i64()
        flag_a = r.u32()
        flag_b = r.u32()
        trailing_len = r.u32()
        return ContainerHeader(
            magic,
            file_version,
            unknown_08,
            guid,
            unknown_1c,
            length_ms,
            network_version,
            changelist,
            friendly_name,
            is_live,
            timestamp,
            flag_a,
            flag_b,
            trailing_len,
            r.pos,
        )

    def _walk_chunks(self) -> Iterator[Chunk]:
        off = self.header.chunks_start
        end = len(self.data)
        while off + 8 <= end:
            ctype, size = struct.unpack_from("<II", self.data, off)
            if off + 8 + size > end:
                raise VrfError(
                    f"truncated chunk at 0x{off:X}: type={ctype} size={size}"
                )
            yield Chunk(ctype, off + 8, size)
            off += 8 + size
        if off != end:
            raise VrfError(f"trailing {end - off} bytes after last chunk")

    # ---- header chunk ---------------------------------------------------
    def _parse_demo_header(self) -> DemoHeader:
        hdr = next((c for c in self.chunks if c.type == HEADER), None)
        if hdr is None:
            raise VrfError("no HEADER chunk")
        buf = self.data[hdr.offset : hdr.offset + hdr.size]
        r = Reader(buf)
        magic = r.u32()
        if magic != DEMO_MAGIC:
            raise VrfError(f"bad demo header magic 0x{magic:08X}")
        demo = DemoHeader(magic=magic, version=r.u32())

        # The middle of this header is Riot-specific and undocumented, so the
        # fields worth having are recovered by scanning for length-prefixed
        # strings rather than by fixed offsets.
        for text in _iter_ansi_strings(buf):
            if text.startswith("++") and not demo.build:
                demo.build = text
            elif text.startswith("/Game/Maps/"):
                demo.maps.append(text)
            elif text.startswith("{"):
                demo.raw_json.append(text)
                try:
                    demo.json_blobs.append(json.loads(text))
                except json.JSONDecodeError:
                    demo.json_blobs.append(None)
            elif text.isdigit() and demo.build and not demo.changelist:
                demo.changelist = text
        return demo

    # ---- events ---------------------------------------------------------
    def events(self) -> list:
        out = []
        for c in self.chunks:
            if c.type != EVENT:
                continue
            r = Reader(self.data, c.offset)
            ev_id = r.fstring()
            group = r.fstring()
            meta = r.fstring()
            r.u32()  # time1, duplicates time2
            time_ms = r.u32()
            payload = r.bytes(r.u32())
            enum_name, args, time_s = _parse_event_payload(payload)
            out.append(
                Event(group, ev_id, meta, time_ms, enum_name, args, time_s, c.offset)
            )
        out.sort(key=lambda e: e.time_ms)
        return out

    # ---- metadata -------------------------------------------------------
    def match_metadata(self):
        """The large GameSpecificData JSON blob (playerLoadouts etc.)."""
        for blob in self.demo.json_blobs:
            if isinstance(blob, dict) and "playerLoadouts" in blob:
                return blob
        return None

    def players(self) -> list:
        meta = self.match_metadata()
        if not meta:
            return []
        return [
            {"subject": e.get("subject"), "characterId": e.get("characterId")}
            for e in meta.get("playerLoadouts", [])
        ]

    # ---- payload blocks --------------------------------------------------
    def data_blocks(self, kinds=(REPLAYDATA, CHECKPOINT)) -> list:
        """Parse the compressed payload framing of REPLAYDATA/CHECKPOINT chunks.

        Both carry, after their chunk-specific preamble:
            uint32 time1, uint32 time2, uint32 size, uint32 memory_size
            uint32 decompressed_size, uint32 compressed_size   <- block header
            byte   blob[compressed_size]                       <- Oodle stream
        """
        out = []
        for c in self.chunks:
            if c.type not in kinds:
                continue
            r = Reader(self.data, c.offset)
            label = ""
            if c.type == CHECKPOINT:
                label = r.fstring()  # "checkpoint7"
                r.fstring()  # group
                r.fstring()  # metadata
            time1, time2 = r.u32(), r.u32()
            size = r.u32()
            memory_size = r.u32() if c.type == REPLAYDATA else size
            head = r.pos
            dec_size, comp_size = r.u32(), r.u32()
            out.append(
                DataBlock(
                    chunk=c,
                    label=label,
                    time1=time1,
                    time2=time2,
                    size=size,
                    memory_size=memory_size,
                    decompressed_size=dec_size,
                    compressed_size=comp_size,
                    blob_offset=head + 8,
                )
            )
        return out

    # ---- the "is it encrypted / compressed?" question --------------------
    def check_obfuscation(self) -> dict:
        """Report how the payload is protected, from the chunk framing itself.

        Note: a plaintext-string probe over the raw file is *not* a valid test
        here.  Oodle is an LZ scheme, so literal runs survive compression and
        readable asset paths still show up in the compressed bytes (subtly
        mangled, e.g. "Charcters", where a match reference replaced a run).
        The framing below is authoritative instead.
        """
        blocks = self.data_blocks()
        raw = sum(b.decompressed_size for b in blocks)
        packed = sum(b.compressed_size for b in blocks)
        codecs = sorted({b.oodle_codec(self.data) for b in blocks})
        return {
            "header_flag_a": self.header.flag_a,  # 1 == bCompressed
            "header_flag_b": self.header.flag_b,  # 0 == bEncrypted
            "trailing_array_len": self.header.trailing_len,  # 0 == no key stored
            "encrypted": bool(self.header.flag_b) or self.header.trailing_len > 0,
            "compressed": bool(self.header.flag_a),
            "codecs": codecs,
            "blocks": len(blocks),
            "compressed_bytes": packed,
            "decompressed_bytes": raw,
            "ratio": (raw / packed) if packed else 0.0,
            # _walk_chunks() already validated the table lands exactly on EOF
            "chunk_table_reaches_eof": True,
        }


def _iter_ansi_strings(buf: bytes) -> Iterator[str]:
    """Yield UE length-prefixed ANSI strings found in a buffer.

    Scans for a plausible (int32 length, NUL-terminated text) pair.  Used only
    for the undocumented middle of the demo header.
    """
    end = len(buf)
    i = 0
    while i + 4 <= end:
        ln = struct.unpack_from("<i", buf, i)[0]
        if 2 <= ln <= end - i - 4:
            stop = i + 4 + ln
            text = buf[i + 4 : stop]
            if text.endswith(b"\x00") and _is_text(text[:-1]):
                yield text[:-1].decode("utf-8", "replace")
                i = stop
                continue
        i += 1


def _iter_fstrings(buf: bytes, start: int = 0) -> Iterator[str]:
    """Yield UE length-prefixed FStrings, ANSI *or* UTF-16, found in a buffer.

    REPLAYDATA frames name objects in ANSI; CHECKPOINT snapshots use UTF-16.
    """
    end = len(buf)
    i = start
    while i + 4 <= end:
        n = struct.unpack_from("<i", buf, i)[0]
        if 2 <= n <= end - i - 4:  # ANSI
            stop = i + 4 + n
            text = buf[i + 4 : stop]
            if text.endswith(b"\x00") and _is_text(text[:-1]):
                yield text[:-1].decode("utf-8", "replace")
                i = stop
                continue
        elif -4096 <= n <= -2:  # UTF-16
            width = -n * 2
            stop = i + 4 + width
            if stop <= end:
                text = buf[i + 4 : stop]
                if text.endswith(b"\x00\x00") and _is_text(text[:-2:2]) and all(
                    c == 0 for c in text[1::2]
                ):
                    yield text[:-2].decode("utf-16-le", "replace")
                    i = stop
                    continue
        i += 1


def _is_text(b: bytes) -> bool:
    return bool(b) and all(c in (9, 10, 13) or 32 <= c < 127 for c in b)


def _parse_event_payload(payload: bytes):
    """Payload: uint32 type id, N uint32 args, FString enum name, float seconds."""
    marker = payload.find(b"EReplayEventGroup::")
    if marker < 4:
        return "", [], None
    args = [struct.unpack_from("<I", payload, o)[0] for o in range(0, marker - 4, 4)]
    nul = payload.find(b"\x00", marker)
    enum_name = payload[marker:nul].decode("ascii", "replace")
    time_s = None
    if nul + 5 <= len(payload):
        time_s = struct.unpack_from("<f", payload, nul + 1)[0]
    return enum_name, args, time_s


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _fmt_ms(ms: int) -> str:
    return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def cmd_info(vrf: VrfFile) -> None:
    h, d = vrf.header, vrf.demo
    print(f"File            {vrf.path}")
    print(f"Size            {len(vrf.data):,} bytes")
    print(f"Container       magic=0x{h.magic:08X} version={h.file_version}")
    print(f"Replay id       {h.friendly_name}")
    print(f"GUID            {h.guid}")
    print(f"Duration        {_fmt_ms(h.length_ms)}  ({h.length_ms:,} ms)")
    ts = h.recorded_utc
    print(f"Recorded (UTC)  {ts:%Y-%m-%d %H:%M:%S}" if ts else "Recorded (UTC)  -")
    print(f"Build           {d.build or '-'}  changelist={d.changelist or '-'}")
    print(f"Map             {', '.join(d.maps) or '-'}")
    print(f"Demo header     magic=0x{d.magic:08X} version={d.version}")

    counts, sizes = {}, {}
    for c in vrf.chunks:
        counts[c.type] = counts.get(c.type, 0) + 1
        sizes[c.type] = sizes.get(c.type, 0) + c.size
    print(f"\nChunks          {len(vrf.chunks)}")
    for t in sorted(counts):
        print(f"  {CHUNK_NAMES.get(t, t):<12} {counts[t]:>5}   {sizes[t]:>12,} bytes")

    evs = vrf.events()
    groups = {}
    for e in evs:
        groups[e.group] = groups.get(e.group, 0) + 1
    print(f"\nEvents          {len(evs)}")
    for g in sorted(groups, key=lambda k: -groups[k]):
        print(f"  {g:<24} {groups[g]:>4}")

    ob = vrf.check_obfuscation()
    print("\nObfuscation check")
    print(f"  encrypted            {ob['encrypted']}")
    print(f"  compressed           {ob['compressed']}  ({', '.join(ob['codecs'])})")
    print(
        f"  header flags         a={ob['header_flag_a']} b={ob['header_flag_b']} "
        f"trailing_array_len={ob['trailing_array_len']}"
    )
    print(
        f"  payload blocks       {ob['blocks']}  "
        f"{ob['compressed_bytes']:,} -> {ob['decompressed_bytes']:,} bytes "
        f"({ob['ratio']:.2f}x)"
    )
    print(f"  chunk table to EOF   {ob['chunk_table_reaches_eof']}")

    md = vrf.match_metadata()
    if md:
        print(
            f"\nMetadata JSON   {len(d.raw_json)} blob(s), "
            f"top-level keys: {', '.join(sorted(md))}"
        )
        print(f"Players         {len(md.get('playerLoadouts', []))}")


def cmd_events(vrf: VrfFile) -> None:
    print(f"{'time':>10}  {'group':<24} args")
    for e in vrf.events():
        print(f"{_fmt_ms(e.time_ms):>10}  {e.group:<24} {e.args}")


def cmd_players(vrf: VrfFile) -> None:
    md = vrf.match_metadata()
    if not md:
        print("no player metadata found")
        return
    for i, p in enumerate(md.get("playerLoadouts", []), 1):
        print(f"{i:>2}. subject={p.get('subject')} character={p.get('characterId')}")


def cmd_chunks(vrf: VrfFile) -> None:
    print(f"{'offset':>12}  {'type':<12} {'size':>12}")
    for c in vrf.chunks:
        print(f"0x{c.offset:010X}  {c.name:<12} {c.size:>12,}")


def cmd_blocks(vrf: VrfFile) -> None:
    print(
        f"{'#':>4}  {'kind':<11} {'label':<13} {'t1':>9} {'t2':>9} "
        f"{'packed':>10} {'raw':>11}  ratio  codec"
    )
    for i, b in enumerate(vrf.data_blocks()):
        print(
            f"{i:>4}  {b.chunk.name:<11} {b.label:<13} {b.time1:>9} {b.time2:>9} "
            f"{b.compressed_size:>10,} {b.decompressed_size:>11,}  "
            f"{b.ratio:>4.2f}x  {b.oodle_codec(vrf.data)}"
        )


def cmd_decode(vrf: VrfFile, index: int, dll: str | None, outfile: str | None) -> None:
    blocks = vrf.data_blocks()
    if not 0 <= index < len(blocks):
        raise VrfError(f"block {index} out of range (0..{len(blocks) - 1})")
    b = blocks[index]
    oodle = Oodle.discover(dll)
    raw = oodle.decompress(b.blob(vrf.data), b.decompressed_size)

    print(f"Oodle DLL       {oodle.path}")
    print(f"Block {index:<9} {b.chunk.name} {b.label} at 0x{b.chunk.offset:X}")
    print(f"Times           t1={b.time1} t2={b.time2} ms")
    print(
        f"Sizes           {b.compressed_size:,} -> {b.decompressed_size:,} bytes "
        f"({b.ratio:.2f}x, {b.oodle_codec(vrf.data)})"
    )

    if b.chunk.type == REPLAYDATA:
        # A replay-data block opens with one demo frame header.
        r = Reader(raw)
        print(f"\nDemo frame      level_index={r.u32()} time={r.f32():.4f}s")
        names = list(_iter_fstrings(raw, 8))
    else:
        # Checkpoints are full world snapshots with a different preamble that
        # is not decoded here; the name table is still recoverable.
        print(f"\nSnapshot        preamble {raw[:4].hex()} (layout not decoded)")
        names = list(_iter_fstrings(raw))

    paths = [n for n in names if n.startswith("/")]
    print(f"NetGUID table   {len(names)} entries "
          f"({len(paths)} asset paths, {len(names) - len(paths)} property names)")
    for n in names[:15]:
        print(f"  {n}")
    if len(names) > 15:
        print(f"  ... {len(names) - 15} more")

    if outfile:
        with open(outfile, "wb") as fh:
            fh.write(raw)
        print(f"\nwrote {outfile}  ({len(raw):,} bytes)")


def cmd_dump_json(vrf: VrfFile, outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(vrf.path))[0]
    for i, raw in enumerate(vrf.demo.raw_json):
        dest = os.path.join(outdir, f"{base}.meta{i}.json")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(raw)
        print(f"wrote {dest}  ({len(raw):,} bytes)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read a Valorant .vrf replay file.")
    ap.add_argument("path")
    ap.add_argument("--events", action="store_true", help="print the event timeline")
    ap.add_argument(
        "--players", action="store_true", help="print players from metadata"
    )
    ap.add_argument("--chunks", action="store_true", help="print the chunk table")
    ap.add_argument("--dump-json", metavar="OUTDIR", help="write embedded JSON blobs")
    ap.add_argument(
        "--blocks", action="store_true", help="print the compressed block table"
    )
    ap.add_argument(
        "--decode", type=int, metavar="N", help="decompress and decode block N"
    )
    ap.add_argument("--oodle-dll", metavar="PATH", help="path to oo2core_*_win64.dll")
    ap.add_argument("--out", metavar="FILE", help="with --decode, write raw block here")
    args = ap.parse_args(argv)

    try:
        vrf = VrfFile(args.path)
        if args.events:
            cmd_events(vrf)
        elif args.players:
            cmd_players(vrf)
        elif args.chunks:
            cmd_chunks(vrf)
        elif args.blocks:
            cmd_blocks(vrf)
        elif args.decode is not None:
            cmd_decode(vrf, args.decode, args.oodle_dll, args.out)
        elif args.dump_json:
            cmd_dump_json(vrf, args.dump_json)
        else:
            cmd_info(vrf)
    except (VrfError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
