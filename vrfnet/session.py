"""
Cross-block decoder state and the health metrics that judge it.

A replay is a sequence of decompressed blocks, but the GUID cache, the export
table and the channel table all persist across them: an actor opened in block 2
keeps its identity until a bunch closes it, and a path exported once is never
re-exported.  ReplaySession owns that state so blocks can be fed in order.

The numbers this produces are not decoration.  clean_packet_rate is the health
metric for the whole decoder: bit-level desync does not degrade gracefully, so
anything below ~99% means a layout is wrong somewhere, not that the data is
noisy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vrfnet.actors import ChannelTable, read_content_block, read_new_actor
from vrfnet.bitreader import NetError
from vrfnet.datachannel import read_packet_bunches
from vrfnet.demodriver import read_demo_frames
from vrfnet.packagemap import ExportTable, GuidCache
from vrfnet.versions import Features


@dataclass
class Stats:
    """Counters accumulated while decoding, and the rates derived from them."""

    blocks: int = 0
    bytes_in: int = 0
    bytes_accounted: int = 0
    frames: int = 0
    packets: int = 0
    packets_clean: int = 0
    bunches: int = 0
    bunches_open: int = 0
    bunches_close: int = 0
    actors_resolved: int = 0
    actors_unresolved: int = 0
    content_blocks: int = 0
    content_blocks_exact: int = 0
    failures: dict = field(default_factory=dict)

    def fail(self, stage: str, exc: Exception) -> None:
        key = f"{stage}: {type(exc).__name__}"
        self.failures[key] = self.failures.get(key, 0) + 1

    @property
    def byte_accounting(self) -> float:
        return self.bytes_accounted / self.bytes_in if self.bytes_in else 0.0

    @property
    def clean_packet_rate(self) -> float:
        return self.packets_clean / self.packets if self.packets else 0.0

    @property
    def content_block_exact_rate(self) -> float:
        return (
            self.content_blocks_exact / self.content_blocks
            if self.content_blocks
            else 0.0
        )

    def report(self) -> str:
        lines = [
            f"blocks            {self.blocks}",
            f"byte accounting   {self.byte_accounting:.4%} "
            f"({self.bytes_accounted:,}/{self.bytes_in:,})",
            f"frames            {self.frames:,}",
            f"packets           {self.packets:,}",
            f"clean packets     {self.clean_packet_rate:.4%} "
            f"({self.packets_clean:,})",
            f"bunches           {self.bunches:,} "
            f"({self.bunches_open:,} open, {self.bunches_close:,} close)",
            f"archetypes        {self.actors_resolved:,} resolved, "
            f"{self.actors_unresolved:,} unresolved",
            f"content blocks    {self.content_blocks:,} "
            f"({self.content_block_exact_rate:.2%} exactly framed)",
        ]
        if self.failures:
            lines.append("failures:")
            for key, count in sorted(self.failures.items(), key=lambda kv: -kv[1]):
                lines.append(f"  {count:>7,}  {key}")
        return "\n".join(lines)


@dataclass
class ReplaySession:
    """Decoder state that outlives any single block."""

    features: Features = field(default_factory=Features)
    guids: GuidCache = field(default_factory=GuidCache)
    exports: ExportTable = field(default_factory=ExportTable)
    channels: ChannelTable = field(default_factory=ChannelTable)
    stats: Stats = field(default_factory=Stats)

    def feed_block(self, buf: bytes, decode_bunches: bool = True) -> None:
        """Decode one decompressed REPLAYDATA block."""
        self.stats.blocks += 1
        self.stats.bytes_in += len(buf)
        frames = read_demo_frames(buf, self.guids, self.exports)
        self.stats.frames += len(frames)
        self.stats.bytes_accounted += sum(f.size for f in frames)
        if not decode_bunches:
            self.stats.packets += sum(len(f.packets) for f in frames)
            return
        for frame in frames:
            for packet in frame.packets:
                self._feed_packet(packet, frame.time_seconds)

    def _feed_packet(self, packet, time_seconds: float) -> None:
        self.stats.packets += 1
        try:
            bunches = read_packet_bunches(packet.data, self.features)
        except NetError as exc:
            self.stats.fail("packet", exc)
            return
        self.stats.packets_clean += 1
        for bunch in bunches:
            self._feed_bunch(bunch, time_seconds)

    def _feed_bunch(self, bunch, time_seconds: float) -> None:
        self.stats.bunches += 1
        reader = bunch.reader()
        if bunch.b_open:
            self.stats.bunches_open += 1
            try:
                actor = read_new_actor(reader, self.guids)
            except NetError as exc:
                self.stats.fail("new actor", exc)
                return
            self.channels.open(bunch, actor, time_seconds)
            if actor.resolved:
                self.stats.actors_resolved += 1
            else:
                self.stats.actors_unresolved += 1
            # The spawn transform after the archetype is not decoded, so the
            # cursor cannot be trusted past here on an opening bunch.
            return

        channel = self.channels.get(bunch.ch_index)
        if channel is not None:
            channel.bunches += 1
        try:
            block = read_content_block(reader)
        except NetError as exc:
            self.stats.fail("content block", exc)
        else:
            self.stats.content_blocks += 1
            if block.exact:
                self.stats.content_blocks_exact += 1
            if channel is not None:
                channel.content_blocks += 1
                channel.payload_bits += block.num_bits

        # A close applies whether or not the payload parsed -- the flag is in
        # the header, which we trust, not in the body, which we do not.
        if bunch.b_close:
            self.stats.bunches_close += 1
            self.channels.close(bunch.ch_index)
