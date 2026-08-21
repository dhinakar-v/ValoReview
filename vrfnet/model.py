"""
Records emitted by the replication-stream decoder.

Deliberately plain: these are the shapes that get counted, cross-checked and
serialised to JSON, not a live object graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NetFieldExport:
    """One replicated property (or RPC parameter block) within a group.

    `name` is whatever the stream carries -- an inline string, or "#<n>" for a
    hardcoded UE EName index.  There is deliberately no type: modern builds do
    not put one on the wire (see docs/vrf-decoding-research.md Part 1).
    """

    handle: int
    checksum: int
    name: str


@dataclass
class NetFieldExportGroup:
    """A class's property table, keyed by 1-based wire handle."""

    path_name: str
    path_name_index: int
    num_exports: int = 0
    exports: dict[int, NetFieldExport] = field(default_factory=dict)

    def lookup(self, handle: int) -> NetFieldExport | None:
        return self.exports.get(handle)

    @property
    def is_class_net_cache(self) -> bool:
        """ClassNetCache groups carry RPC/function signatures, not properties."""
        return "_ClassNetCache" in self.path_name


@dataclass
class NetGuidEntry:
    """A NetGUID and the path it exported, plus its outer in the object chain."""

    guid: int
    path: str = ""
    outer_guid: int = 0
    checksum: int | None = None
    flags: int = 0


@dataclass
class PlaybackPacket:
    """One BufferSize-prefixed blob; its interior is bit-addressed."""

    level_index: int
    offset: int
    size: int
    data: bytes


@dataclass
class ExternalDataEntry:
    net_guid: int
    num_bits: int
    payload: bytes


@dataclass
class DemoFrame:
    """One demo frame: a prologue of exports/levels, then playback packets."""

    level_index: int
    time_seconds: float
    offset: int
    end: int
    packets: list[PlaybackPacket] = field(default_factory=list)
    new_groups: list[str] = field(default_factory=list)
    num_field_exports: int = 0
    num_guid_blobs: int = 0
    streaming_levels: list[str] = field(default_factory=list)
    external_data: list[ExternalDataEntry] = field(default_factory=list)

    @property
    def size(self) -> int:
        return self.end - self.offset

    @property
    def packet_bytes(self) -> int:
        return sum(p.size for p in self.packets)
