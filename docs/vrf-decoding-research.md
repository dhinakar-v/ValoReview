# Decoding the Valorant `.vrf` Replication Stream — Research Findings

**Date:** 2026-08-21
**Context:** `vrf_reader.py` / `vrf_to_json.py` successfully parse the VRF container (chunk table, Oodle Mermaid decompression, frame headers, name/export table) but stop at the bit-packed UE replication stream. This document collects research into how to decode that stream.

**Reference sample:** `039f3991-5472-4119-bed2-838da0935f60.vrf` — container magic `0x43F4EFDD` (v7), demo magic `0x2CF5A13D` (v19), build `++Ares-Core+release-11.11`, network version `480767974`, changelist `4091853`.

> **Provenance warning.** Epic's `github.com/EpicGames/UnrealEngine` requires an Epic-linked GitHub account and could not be read directly during this research. Field *names* and *struct shapes* below are taken from Epic's auto-generated public API docs (authoritative, generated from real headers) and from a mature working re-implementation ([Shiqan/FortniteReplayDecompressor](https://github.com/Shiqan/FortniteReplayDecompressor)). Field *orderings* and *bit widths* come from that re-implementation, not from first-party source. Verify against real captures before hard-coding. Items that could not be verified at all are explicitly flagged **[UNVERIFIED]**.

---

## Part 1 — The Headline Answer

### Is the replication stream self-describing?

**Partially — and the part that is self-describing is enough to walk the entire stream without knowing anything about Valorant.**

| What the stream carries | Present? |
|---|---|
| Property **handle** (stable numeric ID) | Yes |
| Property **name** (as an `FName` into the name table you already parse) | Yes |
| `CompatibleChecksum` (schema-drift fingerprint) | Yes |
| Property **wire type** / bit shape (bool vs float vs vector vs object ref) | **No** |
| Explicit **bit length** of each property's payload | **Yes — this is the unlock** |

Epic's [`FNetFieldExport`](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/FNetFieldExport) struct fields are `Handle`, `CompatibleChecksum`, `ExportName`, `bExported`, `bExportBlob`, `bIncompatible`, `bDirtyForReplay`, `Blob`. Note the absence of any type/`RepLayoutCmdType`/bit-width field.

Historically this was different. From `ReadNetFieldExport`:

```csharp
var isExported = archive.ReadBoolean();
if (isExported) {
    Handle = archive.ReadIntPacked();
    CompatibleChecksum = archive.ReadUInt32();
    if (EngineNetworkVersion < HISTORY_NETEXPORT_SERIALIZATION)      { Name = ReadFString(); Type = ReadFString(); }  // OLD: type string included
    else if (EngineNetworkVersion < HISTORY_NETEXPORT_SERIALIZE_FIX) { Name = ReadFString(); }
    else                                                             { Name = archive.ReadFName(); }                 // MODERN: name only
}
```

Early UE4 replays genuinely were self-describing for types. Modern builds — which `release-11.11` certainly is — dropped the type string. You must supply an external `(ClassPath, PropertyName) → wire shape` table yourself.

Independent confirmation from [xNocken/replay-reader docs](https://github.com/xNocken/replay-reader/blob/master/docs/addOwnExports.md): *"Replays use so called netFieldExports to parse their packets. The replays provide the information about which part of the replay has which property, and **we** provide the information about how to parse them."*

### Why this is still very good news

The property receive loop is length-prefixed:

```csharp
while (true) {
    var handle = archive.ReadIntPacked();
    if (handle == 0) break;                 // 0 = terminator
    handle--;                                // handles are 1-based on the wire
    if (!group.IsValidIndex(handle)) return false;   // out-of-range = desync
    var export = group.NetFieldExports[handle];
    var numBits = archive.ReadIntPacked();   // exact bit-length of this property's payload
    if (numBits == 0) continue;
    if (export is null) { archive.SkipBits(numBits); continue; }   // safely skippable without any schema
    // bits = archive.ReadBits(numBits) → your own type-specific decoder
}
```

Because every property announces its own bit length, **you never need a type to safely skip a property — only to decode its value.** A complete *structural* parser (actor spawns, channel open/close, which named property changed on which actor at which frame, and its size) is achievable before reverse-engineering a single type.

---

## Part 2 — Wire Format Specification

### 2.1 Demo frame layout

`UDemoNetDriver::ReadDemoFrameIntoPlaybackPackets`:

```
if (NetworkVersion >= HISTORY_MULTIPLE_LEVELS)   int32  CurrentLevelIndex
                                                 float  TimeSeconds
if (NetworkVersion >= HISTORY_LEVEL_STREAMING_FIXES)  → ReadExportData()   // the name/export table already parsed
if (HasLevelStreamingFixes())
    packed  NumStreamingLevels
    for each:  FString LevelName
else
    packed  NumStreamingLevels
    for each:  FString PackageName, FString PackageNameToLoad, FTransform LevelTransform
if (HasLevelStreamingFixes())        uint64  ExternalOffset
→ ReadExternalData()
if (HasGameSpecificFrameData())      uint64  SkipExternalOffset  (skip that many bytes if > 0)

loop:
    if (HasLevelStreamingFixes())    packed  SeenLevelIndex
    ReadPacket()  → until PacketState.End / Error
```

This matches the `level_index` + `time_seconds` frame header the parser already extracts.

**`ReadExternalData`** — per-frame side-channel data keyed by NetGUID (RPCs targeting unresolved GUIDs, voice, etc.):

```
loop:
    packed  ExternalDataNumBits
    if 0: break                              // sentinel
    packed  NetGUID
    bytes   (ExternalDataNumBits + 7) >> 3   // raw payload, consumed when that GUID's object becomes available
```

**`ReadPacket`** — one playback packet:

```
int32  BufferSize
if BufferSize == 0: PacketState.End          // sentinel terminating the packet loop
if BufferSize < 0 or > 2048: PacketState.Error
bytes  BufferSize                            // bit-parsed as a sequence of bunches
```

**Important:** there is **no packet-level header** inside a demo `REPLAYDATA` chunk — no sequence numbers, no `bHasPacketInfo`, no ack/NAK bits. `UDemoNetConnection` runs in "InternalAck" mode, bypassing the live `PacketHandler`/packet-notify machinery used on real UDP connections. A packet is just a byte blob parsed directly as bunches.

### 2.2 Packet → bunch (`FInBunch` header)

From the working `ReceivedPacket` loop:

```csharp
while (!bitReader.AtEnd())
{
    if (bitReader.EngineNetworkVersion < HISTORY_ACKS_INCLUDED_IN_HEADER)
        bitReader.ReadBit();                       // legacy "isAckDummy" — absent in modern builds

    var bControl = bitReader.ReadBit();
    bunch.bOpen  = bControl && bitReader.ReadBit();
    bunch.bClose = bControl && bitReader.ReadBit();

    if (EngineNetworkVersion < HISTORY_CHANNEL_CLOSE_REASON) {
        bunch.bDormant = bunch.bClose && bitReader.ReadBit();
        bunch.CloseReason = bunch.bDormant ? Dormancy : Destroyed;
    } else {
        bunch.CloseReason = bunch.bClose
            ? (ChannelCloseReason)bitReader.ReadSerializedInt((int)ChannelCloseReason.MAX)
            : Destroyed;
        bunch.bDormant = bunch.CloseReason == Dormancy;
    }

    bunch.bIsReplicationPaused = bitReader.ReadBit();
    bunch.bReliable            = bitReader.ReadBit();

    if (EngineNetworkVersion < HISTORY_MAX_ACTOR_CHANNELS_CUSTOMIZATION)
        bunch.ChIndex = bitReader.ReadSerializedInt(OLD_MAX_ACTOR_CHANNELS);   // fixed max, e.g. 10240
    else
        bunch.ChIndex = bitReader.ReadIntPacked();                             // packed int, modern

    bunch.bHasPackageMapExports  = bitReader.ReadBit();
    bunch.bHasMustBeMappedGUIDs  = bitReader.ReadBit();
    bunch.bPartial               = bitReader.ReadBit();

    // ChSequence is derived, not read: InReliable+1 if reliable, InPacketId if partial, else 0
    bunch.bPartialInitial = bunch.bPartial && bitReader.ReadBit();
    bunch.bPartialFinal   = bunch.bPartial && bitReader.ReadBit();

    if (EngineNetworkVersion < HISTORY_CHANNEL_NAMES)
        var type = bitReader.ReadSerializedInt((int)ChannelType.MAX);   // legacy int channel type
    else if (bunch.bReliable || bunch.bOpen)
        bitReader.ReadFName();                                          // ChName — only for reliable or opening bunches

    var bunchDataBits = (int)bitReader.ReadSerializedInt(MaxPacketSizeInBits);  // range-bounded packed int, cap 16384

    if (bunch.bHasPackageMapExports) ReceiveNetGUIDBunch(bunch.Archive);   // §2.3 / §2.4
    // → dispatch to channel by ChIndex
}
```

Structural notes:

- **Loop sentinel is bit exhaustion** (`!AtEnd()`), not a magic value. Multiple bunches per packet.
- Given `release-11.11`, assume all `HISTORY_*` gates are satisfied: packed `ChIndex`, range-int `CloseReason`, `FName` channel names (not int `ChType`), no legacy ack-dummy bit.
- `bunchDataBits` is a **range-bounded** `ReadSerializedInt` (bounded by `MaxPacketSizeInBits`), *not* a plain `SerializeIntPacked`. Consume exactly that many bits — no terminator. The next bunch header starts wherever those bits end; mid-byte is fine, everything is bit-addressed.
- If `bHasMustBeMappedGUIDs`: inside the bunch's own data span, before the property stream, read `uint16 NumMustBeMappedGUIDs` then that many `ReadIntPacked()` NetGUIDs. A live-play optimization; safe to skip offline provided the bit count is consumed.

`EEngineNetworkVersionHistory` runs from `HISTORY_INITIAL = 1` to `HISTORY_CustomExports = 36` in current builds. The gate *names* above are reliable; the exact enum *integer values* are **[UNVERIFIED]**.

### 2.3 Net GUID export & the outer chain

`UPackageMapClient::InternalLoadObject`:

```csharp
NetworkGUID InternalLoadObject(archive, isExportingNetGUIDBunch, recursionCount = 0)
{
    if (recursionCount > 16) return default;          // outer-chain recursion guard

    var netGuid = new NetworkGUID { Value = archive.ReadIntPacked() };
    if (!netGuid.IsValid()) return netGuid;

    if (netGuid.IsDefault() || isExportingNetGUIDBunch)
    {
        var flags = archive.ReadByteAsEnum<ExportFlags>();   // bHasPath | bNetStartup | bHasNetworkChecksum
        if (flags.HasFlag(bHasPath))
        {
            InternalLoadObject(archive, true, recursionCount + 1);   // recurse: OuterGuid FIRST
            var pathName = archive.ReadFString();
            if (flags.HasFlag(bHasNetworkChecksum)) archive.ReadUInt32();
            if (isExportingNetGUIDBunch)
                NetGuidCache.NetGuidToPathName[netGuid.Value] = pathName.RemoveAllPathPrefixes();
        }
    }
    return netGuid;
}
```

A NetGUID on the wire is either:

- **Already known** — just the packed value. Look it up in the session cache.
- **A fresh export** — packed value, a byte of export flags, then (if `bHasPath`) a *recursive* export of the GUID's **outer** first, then its own path string, then optionally a checksum. Paths are reconstructed as an outer chain (`Package → Class → Object`), terminated by an already-known/default GUID at the top.

Bunch-level entry, `ReceiveNetGUIDBunch` (only when `bHasPackageMapExports`):

```csharp
var bHasRepLayoutExport = bitArchive.ReadBit();
if (bHasRepLayoutExport) { ReceiveNetFieldExportsCompat(bitArchive); return; }   // carries export groups, not GUIDs
var numGUIDsInBunch = bitArchive.ReadInt32();     // capped at MAX_GUID_COUNT (2048)
for numGUIDsInBunch times: InternalLoadObject(bitArchive, isExportingNetGUIDBunch: true);
```

### 2.4 Where export groups appear

`FNetFieldExportGroup` fields ([Epic docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/FNetFieldExportGroup)): `PathName` (FString), `PathNameIndex` (uint32), `NetFieldExports` (TArray), `bDirtyForReplay`.

They arrive in two places:

1. **Inline in a bunch** with `bHasPackageMapExports` set → `ReceiveNetFieldExportsCompat` reads `NumLayoutCmdExports`, then per entry a `PathNameIndex` (packed int into a growing per-session table) plus a bit selecting "new group → also read PathName + NumExports" vs "existing group → look up by index", then one `ReadNetFieldExport` per new/changed handle.
2. **In bulk inside a checkpoint** (§2.6) → `ReadNetFieldExportGroupMap` reads `PathName`, `PathNameIndex`, `NetFieldExportsLength`, then that many entries contiguously. Cleaner encoding; **replaces the entire running table**.

### 2.5 Actor identity — `SerializeNewActor`

This is the mechanism that maps an actor net GUID to a concrete character/player. On a `bOpen` bunch for a freshly-assigned `ChIndex`:

1. `InternalLoadObject` → the actor's own NetGUID.
2. `InternalLoadObject` → the actor's **Archetype**. The exported path (e.g. `/Game/Characters/.../BP_Sova_C`) identifies the class/kit being spawned. **This is the payoff.**
3. Initial transform: `Location`, `Rotation`, `Scale`, optionally `Velocity` — each gated by a presence bit (serialized only if non-default).

After this, `ChIndex ↔ ActorNetGUID ↔ ArchetypePath` is fixed for the channel's lifetime (until a `bClose` bunch on the same `ChIndex`). Every subsequent bunch on that channel carries that actor's property deltas or RPCs.

**Practical recipe:** watch `bOpen` bunches → decode the archetype via the outer-chain export → record `(ChIndex → GUID → ArchetypePath)`. Player identity (name, team, agent) is then whatever replicates as properties on that channel afterwards — a PlayerState-equivalent actor. This should resolve the actor IDs seen in the already-decoded event args (`546, 646, 744, 852, 958, 1058, 1160, 1258, 1362, 1462`).

Field order confirmed structurally from [Epic docs on `SerializeNewActor`](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/UPackageMapClient/SerializeNewActor); exact bit-presence-flag ordering is **[UNVERIFIED]** and should be checked against captures.

### 2.6 Checkpoints — the best entry point

`ReadCheckpoint`:

```
FString Id, Group, Metadata
uint32  StartTime, EndTime
int32   SizeInBytes
→ decrypt/decompress payload (existing Oodle path), giving binaryArchive

if HasDeltaCheckpoints():          uint32 CheckPointSize
if HasLevelStreamingFixes():       int64  PacketOffset
if NetworkVersion >= HISTORY_MULTIPLE_LEVELS:        int32 LevelForCheckpoint
if NetworkVersion >= HISTORY_DELETED_STARTUP_ACTORS: array<FString> DeletedNetStartupActors

int32  GuidCacheCount
for each:
    packed  GUID
    packed  OuterGUID
    if NetworkVersion < HISTORY_GUID_NAMETABLE:  FString PathName
    else:
        bool  isExported
        if isExported: FString PathName
        else:          packed  PathNameIndex        // reuse previously-exported path
    if NetworkVersion < HISTORY_GUIDCACHE_CHECKSUMS: uint32 NetworkChecksum
    byte    Flags                                    // bNetStartup / bDynamic / bNoLoad

uint32  NumNetFieldExportGroups
for each:  ReadNetFieldExportGroupMap()   // full bulk form — REPLACES the entire export table

// reset all channel→actor associations
for each channel: channel.Actor = null

→ ReadDemoFrameIntoPlaybackPackets(binaryArchive)   // the checkpoint body IS a demo frame
```

A checkpoint is therefore: **full GUID cache dump → full schema dump → a normal demo frame containing `bOpen` bunches for every live actor.** The same code path handles it as a regular REPLAYDATA chunk; only the preamble differs. This makes it the ideal validation target — it exercises the entire `SerializeNewActor` + property pipeline for every actor at once with no dependency on incremental history from earlier frames.

The sample file has **15 checkpoints**, one per round, each a complete world snapshot.

> **Gap:** the reference implementation throws `NotImplementedException` on delta checkpoints (`FDeltaCheckpointData`, added ~UE 4.24+ for large-scale titles). If Valorant uses them, no public reference implementation exists. Expect something like a "destroyed actors this checkpoint" list plus subsets of the guid-cache/export loops instead of full dumps, controlled by a bit or count near the top of the decompressed body. **[UNVERIFIED / unresolved]**

### 2.7 RPCs

RPCs are **not structurally different** from property replication — same handle/`numBits` loop, different export group:

```csharp
bool ReceivedRPC(FBitArchive reader, NetFieldExportGroup functionGroup, uint channelIndex)
{
    if (functionGroup is null) return false;
    ReceiveProperties(reader, functionGroup, channelIndex, out _);   // RPC params use the SAME loop
    if (reader.IsError) return false;
    if (!IsIgnoringGroup && WillReadType && !reader.AtEnd()) return false;  // all bits must be consumed
    return true;
}

// dispatch:
if (classNetProperty.IsFunction) {
    var functionGroup = NetGuidCache.GetNetFieldExportGroup(classNetProperty.PathName);
    ReceivedRPC(archive, functionGroup, bunch.ChIndex);
}
```

There are **two kinds** of `NetFieldExportGroup`: plain replicated properties, and the **`ClassNetCache`**, which holds function/RPC signatures and delta-array metadata. Function export group paths typically use a colon separator (`ClassName:FunctionName`). Kill/damage events arriving as RPCs will appear as ordinary handle/`numBits` entries on the relevant actor's `ChIndex`, distinguishable only by export group.

### 2.8 Bit-level gotchas

- **No universal trailing terminator bit.** Every variable-length construct is either length-prefixed (`numBits`, `NumGUIDsInBunch`, `BufferSize`) or explicitly zero-terminated (`handle == 0`, `externalDataNumBits == 0`, `BufferSize == 0`). Trust the counts; do not expect an implicit sentinel bit.
- **`SerializeIntPacked` encoding:** groups of **7 payload bits + 1 continuation bit**, LSB-first within each byte, up to 5 groups (35 bits payload). Continuation bit is the LSB of each read byte (`(readByte & 1) == 0` stops the loop). It reads from the *current bit position* — a true bitstream packed int, **not** a byte-aligned varint. Do not align before reading one.
- **Bit order:** `FBitReader` treats bit 0 (LSB) of a byte as the first bit read; bytes are consumed in stream order. Standard UE networking convention.
- **Alignment:** nothing is byte-aligned except the outer playback-packet boundary (the `BufferSize`-prefixed blob, extracted as whole bytes before bit parsing). A bunch's start need not be aligned to the previous bunch's end.
- **Version gating is pervasive.** `ChIndex` width, `CloseReason` encoding, `ChType` vs `ChName`, `NetFieldExport` type-string presence, GUID-cache `PathName` vs `PathNameIndex`, `NetworkChecksum` presence — all gated on `EEngineNetworkVersionHistory` thresholds against the header's network version (`480767974`). Implement each as a real `if (NetworkVersion >= HISTORY_X)` branch even where only one branch is currently reachable; it documents intent and survives a Riot engine bump.
- **`CompatibleChecksum`** is an opaque compatibility fingerprint, likely derived from property name + type category + array dim (**[UNVERIFIED]** formula). It cannot be decoded into a type, but consistent decode across many actors of the same class is a good correctness signal. Some community tools brute-force a dictionary of known checksums for common primitives to auto-classify simple scalars — heuristic, not guaranteed.
- **`NET_CHECKSUM` / `bDoChecksum` debug bits** are a compile-time (`DO_GUARD_SLOW`-style) feature, very unlikely in a shipped title's capture. Treat as absent. **[UNVERIFIED]**
- **Array/struct nesting** inside `ReceiveProperties` is **[UNVERIFIED]**. Community understanding: an element-count packed int followed by a nested handle/`numBits` loop per element, mirroring the top-level loop one level down. Test: an array property's `numBits` payload should itself parse as `[count][handle, numBits, data]* [0 terminator]`.

---

## Part 3 — Prior Art

### 3.1 Valorant-specific parsers

**No open-source project gets past the name table into actor replication data.** This appears genuinely unsolved in public.

Commercial tools that clearly *do* solve it, all closed source:

| Tool | URL | Notes |
|---|---|---|
| valab | https://www.valab.gg/ · [format explainer](https://www.valab.gg/guides/vrf-file) | Reads "positions, health, shields, weapons, abilities and credits, all read straight from the replay file." States the format is undocumented and was "worked out field by field against real matches." |
| offangle | https://offangle.pro/ | Replay-derived positions + vision raycasting for aim metrics. |
| ValoPlant | https://valoplant.gg/matches | 2D replay import from `.vrf`. |
| Vextra / Calculated.gg | https://github.com/Xylot | The public repo is only a desktop *uploader*; parsing happens server-side. |

**Ruled out (not VRF parsers):**
- `rahinroy/Valorant-Replay-System` — template-matching/OCR on screen captures.
- `tam0w/valorant-data-extraction` (Practistics) — OCR on scoreboard screenshots.

**Community context:** a Riot dev-relations request for a documented binary event-history format ([developer-relations#312](https://github.com/RiotGames/developer-relations/issues/312)) has no Riot response and remains open, confirming Riot has never published VRF internals. No Reddit or blog write-up with concrete VRF technical detail was found.

### 3.2 Adaptable UE replay parsers

The Fortnite ecosystem is the same UE replay architecture and cleanly separates a **game-agnostic engine layer** from a **game-specific schema layer**.

| Project | Language | Key files | Coverage |
|---|---|---|---|
| [Shiqan/FortniteReplayDecompressor](https://github.com/Shiqan/FortniteReplayDecompressor) | C# | [`src/Unreal.Core/ReplayReader.cs`](https://github.com/Shiqan/FortniteReplayDecompressor/blob/master/src/Unreal.Core/ReplayReader.cs) | **Everything in Part 2 (§2.1–2.7)**, with explicit version gating. The single best reference. Does **not** implement delta checkpoints. |
| | | [`BitReader.cs`](https://github.com/Shiqan/FortniteReplayDecompressor/blob/master/src/Unreal.Core/BitReader.cs) | `ReadIntPacked`, `ReadFName`, `AtEnd` — the bit primitives (§2.8). |
| | | [`NetBitReader.cs`](https://github.com/Shiqan/FortniteReplayDecompressor/blob/master/src/Unreal.Core/NetBitReader.cs) | Type-specific decoders (vectors, rotators, compressed floats, `RepMovement`) for once a handle's type is known. |
| | | [`NetFieldParser.cs`](https://github.com/Shiqan/FortniteReplayDecompressor/blob/master/src/Unreal.Core/NetFieldParser.cs) | Shows how manual the handle→type dispatch is (attribute-based, per-game, per-class hardcoding) — direct proof types are not in the stream. |
| [xNocken/replay-reader](https://github.com/xNocken/replay-reader) | JS | [`docs/addOwnExports.md`](https://github.com/xNocken/replay-reader/blob/master/docs/addOwnExports.md), `NetFieldExports/` | Independent confirmation of the "names yes, shapes no" split and the plain-vs-`ClassNetCache` group distinction. Documents the workflow for adding a new class. Claims 99%+ Fortnite replay coverage. |
| [EpicKitten/PUBG-Resources wiki](https://github.com/EpicKitten/PUBG-Resources/wiki/Replay-Files-Documentation) | — | — | High-level checkpoint confirmation only. Secondary source. |
| [exception/UnrealReplayReader](https://github.com/exception/UnrealReplayReader) | Java | — | Archived since Nov 2021, minimal docs, coverage unverified. |
| Rocket League (boxcars, rattletrap) | — | — | **Not applicable.** Psyonix's format is only loosely UE-inspired and does not use `UDemoNetDriver`/`FRepLayout` at the wire level. Do not use as reference. |

The game-specific layer, for reference, looks like per-class models annotated `[NetFieldExportGroup("/Game/.../SomeClass.SomeClass_C")]` with per-property `[NetFieldExport("PropName", RepLayoutCmdType.PropertyFloat)]` (name-based) or `[NetFieldExportHandle(1, RepLayoutCmdType.PropertyFloat)]` (handle-only, when the name is absent). The Fortnite docs note that handle-only cases "required significant reverse-engineering effort to identify" — even with names available, the type is always hand-supplied.

### 3.3 Schema sources — what does and doesn't help

**`.usmap` mapping files are a different system.** They describe cooked *asset* property tags for unversioned property serialization, consumed by [CUE4Parse](https://github.com/FabianFG/CUE4Parse)/FModel — see [UnrealMappingsDumper](https://github.com/TheNaeem/UnrealMappingsDumper), [Unreal-Mappings-Archive](https://github.com/TheNaeem/Unreal-Mappings-Archive). No evidence anyone uses usmap to drive replay bitstream decoding.

The connection is indirect but real: `FRepLayout` assigns handles server-side by walking a UClass's replicated `FProperty`s **in declaration order**, flattening structs/arrays. So *any* source of accurate property lists in declaration order with types — a usmap-derived dump, an SDK dump — lets you reconstruct the same handle→type mapping. **No public Valorant usmap or SDK dump was found.**

**Do not dump the live client.** [Dumper-7](https://github.com/Encryqed/Dumper-7), UE4SS, and UnrealFinderTool work by injecting into a running process and walking live reflection data. Vanguard is kernel-level, has demonstrably blocked unrelated third-party drivers ([OpenRGB#316](https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/316)), and Riot bans for third-party tools touching the live client. This is both likely to fail and a ban risk.

By contrast, **parsing an already-saved `.vrf` offline touches nothing in the running game and carries no such risk.** This is presumably how the commercial tools operate.

---

## Part 4 — The Shortcut Worth Taking First

### Riot's unofficial local client API

The **match-details endpoint** ([docs](https://valapidocs.techchrism.me/endpoint/match-details), from [techchrism/valorant-api-docs](https://github.com/techchrism/valorant-api-docs)) is the same endpoint the Valorant client itself calls (`pd.{region}.a.pvp.net`), authenticated with a token derived from your own local client's lockfile ([common components](https://github.com/techchrism/valorant-api-docs/blob/trunk/docs/common-components.md), [entitlements token](https://valapidocs.techchrism.me/endpoint/entitlements-token)).

Its response already contains, keyed by match ID:

- Player UUID, `gameName`, `tagLine`
- Team assignment (Blue/Red)
- Per-round score, economy (`loadoutValue`, weapon, armor, spent/remaining)
- Per-kill finishing weapon, headshot/bodyshot/legshot damage breakdown
- Round win/loss, bomb plant/defuse outcomes
- **Event-anchored positions** — `plantPlayerLocations`, `defusePlayerLocations`, killer/victim locations with view angles

That is essentially the entire "not in this JSON" list, for free.

**What it does not give:** continuous tick-rate 3D positions and movement paths throughout a round. Only the replication stream has that (valab describes "position and view angle, sampled many times a second").

**The strategic value beyond convenience:** for any match where both the `.vrf` and the API response are available, the API provides **ground truth** — known player ↔ team ↔ round outcome — to correlate against actor net GUIDs and property handle values while reverse-engineering the bitstream. This cross-validation is exactly the technique the Fortnite parser authors describe using to identify undocumented handles.

A hosted wrapper exists ([Henrik-3/unofficial-valorant-api](https://github.com/Henrik-3/unofficial-valorant-api), [docs](https://docs.henrikdev.xyz)) if managing the local lockfile auth flow is undesirable, subject to Riot's match-history retention window.

**The official API is not a substitute.** [developer.riotgames.com/docs/valorant](https://developer.riotgames.com/docs/valorant) requires production-key approval and mandates per-player RSO opt-in, explicitly excluding use cases like "scouting... seeing an opponent's stats before a match."

---

## Part 5 — Recommended Implementation Order

1. **Checkpoint reader** (§2.6). GUID cache dump → export-group bulk dump → embedded demo frame with `bOpen` bunches. Richest, most self-contained validation target; proves the bit primitives (packed int, `FName`, bit-count-prefixed extraction) end to end.
2. **Playback packet / bunch splitting** (§2.1–2.2). `BufferSize`-prefixed blobs, each a `while (!AtEnd())` bunch loop. No packet header to contend with.
3. **NetGUID outer-chain decode** (§2.3, §2.5) → build the `ChIndex → GUID → ArchetypePath` table. Correlate against the ten actor IDs already extracted from `characterDeath` / `characterUltimateUsed` event args.
4. **Structural-only property pass** (§2.4 / Part 1). Walk `handle`/`numBits` pairs and skip every payload. **Success criterion: every bunch consumes to exactly zero leftover bits** — `AtEnd()` true after the last bunch in a packet, and after each `handle == 0` terminator. This alone yields per-actor, per-frame "which named property changed" timelines.
5. **Per-class type reverse engineering.** Use `numBits` as the primary tell — 1 bit = bool; a handful = byte/small enum; 32 = raw float; compressed floats via `ReadFixedCompressedFloat`/`ReadPackedVector`; object refs are always `ReadIntPacked` GUIDs. Cross-check decoded values against ground truth from the local client API (Part 4). This is unavoidable per-title manual work; no amount of format knowledge substitutes for it.

**Highest-value follow-up if available:** an Epic-linked GitHub account would give direct access to `Engine/Source/Runtime/Engine/` — `DataChannel.cpp`, `DemoNetDriver.cpp`, `NetConnection.cpp`, `RepLayout.cpp`, `PackageMapClient.cpp` — replacing every re-implementation-derived claim above with byte-exact primary-source citations.

---

## Open Questions

| Question | Status |
|---|---|
| Does Valorant use delta checkpoints (`FDeltaCheckpointData`)? | Unknown. No public reference implementation if so. |
| Exact array/struct nesting recursion in `ReceiveProperties` | Unverified; testable hypothesis in §2.8. |
| Exact `EEngineNetworkVersionHistory` integer values for build `release-11.11` | Unverified. |
| Exact `CompatibleChecksum` hash formula | Unverified; treat as opaque. |
| Exact bit-presence-flag ordering in `SerializeNewActor` | Unverified; check against captures. |
| Does a public Valorant `.usmap` or SDK dump exist anywhere? | None found. |

---

## Source Index

**Epic (authoritative for struct field lists):**
- [`FNetFieldExport`](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/FNetFieldExport)
- [`FNetFieldExportGroup`](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/FNetFieldExportGroup)
- [`UPackageMapClient::SerializeNewActor`](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/UPackageMapClient/SerializeNewActor)
- [`FNetworkVersion::GetLocalNetworkVersion`](https://docs.unrealengine.com/4.26/en-US/API/Runtime/Core/Misc/FNetworkVersion/GetLocalNetworkVersion/)
- [Network Version and Determining Network Compatibility](https://dev.epicgames.com/community/learning/knowledge-base/7yB9/unreal-engine-network-version-and-determining-network-compatibility)

**Working implementations (authoritative for field order):**
- [Shiqan/FortniteReplayDecompressor](https://github.com/Shiqan/FortniteReplayDecompressor) · [docs](https://fortnitereplaydecompressor.readthedocs.io/en/latest/receiving-properties/)
- [xNocken/replay-reader](https://github.com/xNocken/replay-reader) · [addOwnExports.md](https://github.com/xNocken/replay-reader/blob/master/docs/addOwnExports.md)

**Secondary write-ups:**
- [ikrima — detailed replication flow](https://ikrima.dev/ue4guide/networking/network-replication/detailed-replication-flow/)
- [ikrima — detailed network serialization](https://ikrima.dev/ue4guide/networking/network-replication/detailed-network-serialization/)
- [PUBG Replay Files Documentation](https://github.com/EpicKitten/PUBG-Resources/wiki/Replay-Files-Documentation)

**Riot APIs:**
- [Unofficial match-details endpoint](https://valapidocs.techchrism.me/endpoint/match-details) · [techchrism/valorant-api-docs](https://github.com/techchrism/valorant-api-docs)
- [Henrik-3/unofficial-valorant-api](https://github.com/Henrik-3/unofficial-valorant-api)
- [Official Riot Valorant API](https://developer.riotgames.com/docs/valorant)
