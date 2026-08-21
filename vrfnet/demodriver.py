"""
Demo frames and playback packets.

Mirrors UDemoNetDriver::ReadDemoFrameIntoPlaybackPackets.  Everything here is
byte-addressed; the bit-addressed world starts inside a playback packet.

Frame layout (settled against block000 of the reference capture)
----------------------------------------------------------------
  uint32  LevelIndex
  float   TimeSeconds
  -> ReadExportData          net field exports, then NetGUID export blobs
  packed  NumStreamingLevels
    per level: FString LevelName
  uint64  ExternalOffset     byte size of the external-data section
  -> ReadExternalData        packed NumBits (0 terminates), packed NetGUID, payload
  loop:
    packed  SeenLevelIndex   <- easy to miss; precedes every packet, terminator
    int32   BufferSize       0 terminates the frame
    bytes   BufferSize       one playback packet, parsed as bunches

A decompressed REPLAYDATA block holds one or more of these back to back.
"""

from __future__ import annotations

from vrfnet.bitreader import NetError
from vrfnet.bytereader import ByteReader
from vrfnet.model import DemoFrame, ExternalDataEntry, PlaybackPacket
from vrfnet.packagemap import ExportTable, GuidCache, read_export_data

# UDemoNetDriver rejects anything outside this; it is the sanity check that
# tells us immediately whether the frame prologue was consumed correctly.
MAX_PACKET_SIZE = 2048

# Loose upper bounds, purely to fail fast on a desync instead of allocating.
MAX_STREAMING_LEVELS = 4096
MAX_EXTERNAL_ENTRIES = 65536


def read_external_data(reader: ByteReader) -> list[ExternalDataEntry]:
    """Per-frame side channel keyed by NetGUID; zero NumBits terminates."""
    entries: list[ExternalDataEntry] = []
    while True:
        num_bits = reader.read_int_packed()
        if num_bits == 0:
            return entries
        if len(entries) >= MAX_EXTERNAL_ENTRIES:
            raise NetError("runaway external-data list")
        guid = reader.read_int_packed()
        payload = reader.read_bytes((num_bits + 7) >> 3)
        entries.append(
            ExternalDataEntry(net_guid=guid, num_bits=num_bits, payload=payload)
        )


def read_demo_frame(reader: ByteReader, cache: GuidCache,
                    table: ExportTable) -> DemoFrame:
    """Read exactly one demo frame, leaving the cursor on the next one."""
    start = reader.pos
    level_index = reader.read_u32()
    time_seconds = reader.read_f32()

    num_exports, new_paths, num_guids = read_export_data(reader, cache, table)

    num_levels = reader.read_int_packed()
    if num_levels > MAX_STREAMING_LEVELS:
        raise NetError(f"implausible NumStreamingLevels {num_levels}")
    levels = [reader.read_fstring() for _ in range(num_levels)]

    external_offset = reader.read_u64()
    external_start = reader.pos
    external = read_external_data(reader)
    consumed = reader.pos - external_start
    if external_offset and consumed != external_offset:
        raise NetError(
            f"external data consumed {consumed} bytes, "
            f"ExternalOffset said {external_offset}"
        )

    frame = DemoFrame(
        level_index=level_index,
        time_seconds=time_seconds,
        offset=start,
        end=start,
        new_groups=new_paths,
        num_field_exports=num_exports,
        num_guid_blobs=num_guids,
        streaming_levels=levels,
        external_data=external,
    )

    while True:
        seen_level = reader.read_int_packed()
        size = reader.read_i32()
        if size == 0:
            break
        if size < 0 or size > MAX_PACKET_SIZE:
            raise NetError(
                f"BufferSize {size} out of range at byte {reader.pos - 4}"
            )
        offset = reader.pos
        frame.packets.append(
            PlaybackPacket(
                level_index=seen_level,
                offset=offset,
                size=size,
                data=reader.read_bytes(size),
            )
        )

    frame.end = reader.pos
    return frame


def read_demo_frames(buf: bytes, cache: GuidCache, table: ExportTable,
                     start: int = 0, limit: int | None = None
                     ) -> list[DemoFrame]:
    """Read frames until the buffer is exhausted.

    A well-formed block ends exactly on the last frame's terminator; any
    leftover bytes mean the walk desynced somewhere and should be reported
    rather than swallowed.
    """
    reader = ByteReader(buf, start)
    frames: list[DemoFrame] = []
    while reader.remaining > 0:
        if limit is not None and len(frames) >= limit:
            break
        frames.append(read_demo_frame(reader, cache, table))
    return frames
