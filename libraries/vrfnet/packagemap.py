"""
NetGUID resolution and net field export groups.

Mirrors UPackageMapClient.  Two structures live here, both of which persist for
the whole replay rather than per block:

  GuidCache    NetGUID -> exported path, plus the outer chain that turns a
               leaf GUID into a full object path.
  ExportTable  PathNameIndex -> a class's property table, keyed by wire handle.

Wire notes settled against block000 of the reference capture
------------------------------------------------------------
On the byte archive that carries the demo frame prologue, three flags that all
look like "a bool" are encoded three different ways, and the capture
disambiguates them:

  WasExported (per export-group entry)  SerializeIntPacked   true -> 0x02
  bExported   (per FNetFieldExport)     raw uint8            true -> 0x01
  FName hardcoded flag                  raw uint8            true -> 0x01

Inside a bunch the same fields are single bits instead; see
read_net_field_exports_compat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vrfnet.bitreader import NetError
from vrfnet.bytereader import ByteReader
from vrfnet.model import NetFieldExport, NetFieldExportGroup, NetGuidEntry

# FExportFlags, from UPackageMapClient.
EXPORT_HAS_PATH = 0x01
EXPORT_NO_LOAD = 0x02
EXPORT_HAS_NETWORK_CHECKSUM = 0x04

# UE guards the outer chain at 16 levels.
MAX_OUTER_RECURSION = 16

# UPackageMapClient::ReceiveNetGUIDBunch caps a single bunch's GUID count.
MAX_GUID_COUNT = 2048


@dataclass
class GuidCache:
    """NetGUID -> path, accumulated across the whole replay."""

    entries: dict[int, NetGuidEntry] = field(default_factory=dict)

    def __contains__(self, guid: int) -> bool:
        return guid in self.entries

    def __len__(self) -> int:
        return len(self.entries)

    def record(self, entry: NetGuidEntry) -> NetGuidEntry:
        # A GUID may be re-exported; keep the first path we saw for stability.
        existing = self.entries.get(entry.guid)
        if existing is not None and existing.path:
            return existing
        self.entries[entry.guid] = entry
        return entry

    def path(self, guid: int) -> str:
        entry = self.entries.get(guid)
        return entry.path if entry else ""

    def full_path(self, guid: int) -> str:
        """Walk the outer chain leaf-last, e.g. Package.Class -> full path."""
        parts: list[str] = []
        seen: set[int] = set()
        current = guid
        while current and current not in seen:
            seen.add(current)
            entry = self.entries.get(current)
            if entry is None:
                break
            if entry.path:
                parts.append(entry.path)
            current = entry.outer_guid
        return ".".join(reversed(parts))

    def paths(self) -> set[str]:
        return {e.path for e in self.entries.values() if e.path}


def internal_load_object(
    reader,
    cache: GuidCache,
    *,
    is_exporting: bool,
    depth: int = 0,
) -> int:
    """
    UPackageMapClient::InternalLoadObject -- one GUID, maybe with an export.

    Layout
    ------
      packed  NetGUID                      0 = invalid, terminates the chain
      if (default GUID or exporting):
        uint8   ExportFlags
        if bHasPath:
          -> recurse for the OUTER guid first
          FString PathName
          if bHasNetworkChecksum: uint32

    Works over either ByteReader or BitReader; both expose the same surface.
    """
    if depth > MAX_OUTER_RECURSION:
        msg = f"outer chain deeper than {MAX_OUTER_RECURSION}"
        raise NetError(msg)

    guid = reader.read_int_packed()
    if guid == 0:
        return 0

    # Only the default GUID and exporting bunches carry the export payload.
    # NetworkGUID::IsDefault() is Value == 1 specifically -- not "even", which
    # is IsDynamic().  Inside a bunch (is_exporting False) that difference
    # decides whether a flags byte is on the wire at all.
    if guid == 1 or is_exporting:
        flags = reader.read_u8()
        if flags & EXPORT_HAS_PATH:
            outer = internal_load_object(
                reader,
                cache,
                is_exporting=is_exporting,
                depth=depth + 1,
            )
            path = reader.read_fstring()
            checksum = None
            if flags & EXPORT_HAS_NETWORK_CHECKSUM:
                checksum = reader.read_u32()
            cache.record(
                NetGuidEntry(
                    guid=guid,
                    path=path,
                    outer_guid=outer,
                    checksum=checksum,
                    flags=flags,
                ),
            )
        elif guid not in cache:
            cache.record(NetGuidEntry(guid=guid, flags=flags))
    return guid


def read_net_export_guids(reader, cache: GuidCache) -> int:
    """
    UDemoNetDriver::ReadNetExportGUIDs -- packed count, then sized blobs.

    Each blob is an independent archive holding exactly one outer chain, so its
    length doubles as a per-GUID checksum: a chain that does not consume its
    blob exactly means the export layout is wrong.
    """
    count = reader.read_int_packed()
    for _ in range(count):
        length = reader.read_i32()
        if length < 0 or length > reader.bits_left // 8:
            msg = f"bad GUID blob length {length}"
            raise NetError(msg)
        blob = reader.read_bytes(length)
        _load_guid_blob(blob, cache)
    return count


def _load_guid_blob(blob: bytes, cache: GuidCache) -> None:
    sub = ByteReader(blob)
    internal_load_object(sub, cache, is_exporting=True)
    if sub.pos != len(blob):
        msg = f"GUID blob consumed {sub.pos} of {len(blob)} bytes"
        raise NetError(msg)


@dataclass
class ExportTable:
    """PathNameIndex -> NetFieldExportGroup, accumulated across the replay."""

    by_index: dict[int, NetFieldExportGroup] = field(default_factory=dict)
    by_path: dict[str, NetFieldExportGroup] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.by_index)

    def declare(self, index: int, path: str, num_exports: int) -> NetFieldExportGroup:
        group = self.by_path.get(path)
        if group is None:
            group = NetFieldExportGroup(path_name=path, path_name_index=index)
            self.by_path[path] = group
        group.path_name_index = index
        group.num_exports = max(group.num_exports, num_exports)
        self.by_index[index] = group
        return group

    def get(self, index: int) -> NetFieldExportGroup | None:
        return self.by_index.get(index)

    def replace_all(self, groups: list[NetFieldExportGroup]) -> None:
        """Checkpoints ship the whole table and supersede what came before."""
        self.by_index = {g.path_name_index: g for g in groups}
        self.by_path = {g.path_name: g for g in groups}

    def paths(self) -> set[str]:
        return set(self.by_path)


def read_net_field_export(
    reader,
    group: NetFieldExportGroup | None,
    *,
    hardcoded_packed: bool = True,
) -> NetFieldExport | None:
    """
    One FNetFieldExport: bExported, then handle / checksum / name.

    The stream carries no type for the property -- that is the whole reason a
    schema is needed to decode values, and the whole reason skipping works
    without one.
    """
    if not reader.read_u8():
        return None
    handle = reader.read_int_packed()
    checksum = reader.read_u32()
    name = reader.read_fname(hardcoded_packed=hardcoded_packed)
    export = NetFieldExport(handle=handle, checksum=checksum, name=name)
    if group is not None:
        group.exports[handle] = export
    return export


def read_net_field_exports(reader, table: ExportTable) -> tuple[int, list[str]]:
    """
    UDemoNetDriver::ReadNetFieldExports -- the demo-frame prologue form.

    Layout
    ------
      packed  NumLayoutCmdExports
      per entry:
        packed  PathNameIndex
        packed  WasExported
        if WasExported:  FString PathName, packed NumExports
        FNetFieldExport                        (one per entry, not per group)

    Returns (entry count, paths of groups newly declared in this frame).
    """
    count = reader.read_int_packed()
    new_paths: list[str] = []
    for _ in range(count):
        index = reader.read_int_packed()
        if reader.read_int_packed():
            path = reader.read_fstring()
            num_exports = reader.read_int_packed()
            if path not in table.by_path:
                new_paths.append(path)
            group = table.declare(index, path, num_exports)
        else:
            group = table.get(index)
            if group is None:
                msg = f"export references unknown PathNameIndex {index}"
                raise NetError(msg)
        read_net_field_export(reader, group)
    return count, new_paths


def read_export_data(
    reader,
    cache: GuidCache,
    table: ExportTable,
) -> tuple[int, list[str], int]:
    """UDemoNetDriver::ReadExportData -- field exports, then GUID exports."""
    num_exports, new_paths = read_net_field_exports(reader, table)
    num_guids = read_net_export_guids(reader, cache)
    return num_exports, new_paths, num_guids
