# Decoding the VRF Replication Stream — Measured Results

**Date:** 2026-08-21
**Sample:** `039f3991-5472-4119-bed2-838da0935f60.vrf` — build `++Ares-Core+release-11.11`,
network version `480767974`
**Code:** `libraries/vrfnet/`, driven by `scripts/vrf_net.py`; tests in `tests/`

Companion to `vrf-decoding-research.md`, which is a literature review. This file records what
was *measured* against the capture. Everything below is reproducible from the decompressed
blocks in `out/039f3991_blocks/` with no Oodle DLL and no network access.

---

## Headline

The replication stream is decoded structurally from the demo frame down to the content block.
Verified end to end by an independent cross-check: **the bit stream yields 10 agent pawns with
8 distinct codenames, two of them appearing twice** — the same multiset as the header's
`playerLoadouts` (10 players, 8 agents, Sova ×2, Reyna ×2). The two paths share no code.

| Layer | Status | Evidence |
|---|---|---|
| Demo frames | **decoded** | 100.0000% byte accounting over all 16 REPLAYDATA blocks (117 MB) |
| Net field export groups | **decoded** | 456 groups, handle → property name |
| NetGUID cache + outer chain | **decoded** | 17,811 GUIDs; every export blob consumes its exact length |
| Playback packets → bunches | **decoded** | 99.96% of packets consume to exactly zero leftover bits |
| Actor identity | **decoded** | ChIndex → actor GUID → archetype path |
| Content-block framing | **decoded** | 88% of blocks framed exactly to the bunch boundary |
| Property payload interior | **not decoded on this capture** | obfuscated; 11.11 has no known transform — see "The premise that did not hold" |

Run it:

```
runners\vrf-net.bat decode out/039f3991_blocks/block000_replaydata.bin
runners\vrf-net.bat actors out/039f3991_blocks/block00*_replaydata.bin
```

---

## Corrections to the research document

### The demo frame prologue carries the export table (§2.4 understated this)

The research doc places export groups "inline in a bunch" or "in bulk inside a checkpoint". In
this capture they arrive in a third place, which is the dominant one: the **demo frame prologue**,
via `ReadExportData` → `ReadNetFieldExports` + `ReadNetExportGUIDs`, before any packet.

This matters a lot. It means the schema table and the GUID cache are recoverable **without
decoding a single bit of the bunch stream** — they are plain byte-archive structures. It also
explains why no bunch in the capture sets `bHasPackageMapExports`: there is nothing left to send.

Exact per-entry layout, confirmed byte by byte:

```
packed  NumLayoutCmdExports
per entry:
  packed  PathNameIndex
  packed  WasExported            true encodes as 0x02  (packed 1)
  if WasExported:
    FString PathName
    packed  NumExports
  uint8   bExported              true encodes as 0x01  (raw byte, NOT packed)
  packed  Handle
  uint32  CompatibleChecksum
  FName   Name                   uint8 hardcoded-flag, then packed EName index
                                 or FString + int32
```

Three fields that all read as "a bool" use three different encodings, and the capture
disambiguates them: `WasExported` is a packed int (true → `0x02`), while `bExported` and the
FName hardcoded flag are raw bytes (true → `0x01`).

### `NetworkGUID::IsDefault()` is `Value == 1`, not "even"

Easy to get wrong, and it decides whether an export-flags byte is on the wire at all. `IsDynamic()`
is the even test; `IsStatic()` is odd; `IsDefault()` is the literal value 1. Only default GUIDs
and exporting bunches carry the flags byte.

### Packets carry a `SeenLevelIndex` prefix

`ReadPacket` in the research doc starts at `int32 BufferSize`. In this build every packet —
**including the zero-size terminator** — is preceded by a packed `SeenLevelIndex`. Missing it
desyncs the packet loop immediately.

### Packet bit length comes from a terminator bit, not the byte count

Not mentioned in the research doc and essential. A packet has no bunch count and no sentinel; UE
writes a single 1 bit after the last bunch and zero-pads to the byte. The true bit length is
found by scanning the last non-zero byte for its highest set bit and excluding it. Using
`len(data) * 8` makes the loop parse padding as a bunch and collapses the clean rate.

---

## Version gates, resolved empirically

The `EEngineNetworkVersionHistory` integer thresholds for this build are not public, so they were
not guessed. `vrf-net.bat calibrate` sweeps 192 candidate layouts and scores each by the fraction
of packets whose bunch loop lands exactly on `at_end()`. A wrong bit layout does not degrade
gracefully — it collapses within a bunch or two — so the correct one separates by a wide margin.

**Result: 99.80% clean vs 17.68% for the next structurally different layout — a margin of 82
percentage points.**

| Gate | Resolved to |
|---|---|
| `HISTORY_ACKS_INCLUDED_IN_HEADER` | modern — no leading ack-dummy bit |
| `HISTORY_MAX_ACTOR_CHANNELS_CUSTOMIZATION` | modern — `ChIndex` is a packed int |
| `HISTORY_CHANNEL_NAMES` | modern — `ChName` is an FName, read only when `bReliable \|\| bOpen` |
| `MaxPacketSizeInBits` | 16384 |
| post-`ChIndex` flag bits | **four**, where UE documents three |
| `HISTORY_CHANNEL_CLOSE_REASON` | **not determined** — see below |

### One gate this capture cannot settle

`legacy_close_reason` ties. Every `bClose` bunch in the replay closes with reason `Destroyed`
(value 0), which encodes identically under both branches. The calibration reports this as
undetermined rather than picking one and calling it measured — a gate guarding a branch the data
never takes is an open question, not a result.

### The fourth flag bit

Between `ChIndex` and the partial flags this build carries four bits where UE documents three
(`bHasPackageMapExports`, `bHasMustBeMappedGUIDs`, `bPartial`). All four are zero across all
28,483 bunches sampled — there are no partial bunches and no inline package-map exports, because
the exports ship in the frame prologue instead. **Which of the four is `bPartial` is therefore
not determined by this capture**, and `libraries/vrfnet/datachannel.py` says so at the point of use. It only
matters on a replay that actually sets one.

---

## Actor identity

An opening bunch's payload begins with exactly two packed NetGUIDs: the actor, then its archetype.
Validated by *resolution* rather than bit accounting — 261 of 286 opening bunches produce an
archetype GUID already in the cache with a real path, and those paths are UE class default objects
(`Default__Foo_C`), which is what an archetype is. The 25 that miss reference exports from blocks
not yet read. Actor GUIDs are dynamic and correctly have no exported path.

Decoded from blocks 0 and 2, agent pawn channels:

```
1 x Clay      1 x Deadeye   2 x Hunter    1 x Killjoy
1 x Rift      1 x Sarge     1 x Terra     2 x Vampire     -> 10 pawns, 8 codenames
```

Cross-referencing the header's agent list gives the internal codename mapping:

| Codename | Agent | | Codename | Agent |
|---|---|---|---|---|
| `Hunter` | Sova (×2) | | `Sarge` | Brimstone |
| `Vampire` | Reyna (×2) | | `Deadeye` | Chamber |
| `Rift` | Astra | | `Clay` | Raze |
| `Terra` | Waylay | | `Killjoy` | Killjoy |

Also recovered: exactly 10 `BombPlayerState_C` channels, 10 `Equippable_Unarmed`, 10
`Ability_Melee_Base` — one per player, as expected.

---

## The premise that did not hold

> **Superseded, 2026-08-22.** The premise held. Everything measured below is correct and the
> conclusion drawn from it was not: the payload is **obfuscated**, not encoded differently. Riot
> whitens every content-block payload with a keystream seeded `payload_bits ^ actor_net_guid`, and
> "leading packed integers decode to implausible values (billions)" is precisely what a *correct*
> packed-int reader returns when pointed at a keystream. Undo the transform and the documented
> `[handle][NumBits][payload]` loop parses at 99.75%.
>
> `libraries/vrfnet/payload_transform.py` does that for 12.10, 12.11 and 13.00–13.02. **It cannot
> do it for this capture:** the transforms rotate every patch and are derived per build with
> Ghidra against the shipped binary, and 11.11 is long gone from the live client. So the row in
> the table above stays "not decoded" for `039f3991…` — but for a reason about this *build*, not
> about this title. See `docs/archive/payload-decryption-20260821-2338-handoff.md`.
>
> Both hypotheses at the end of this section are dead. The encoding was never the problem, so
> neither `ReceiveProperties_r` nor a variable preamble was ever going to explain it. The one
> useful thing they cost was time: every probe ran against scrambled bytes, where no bit layout
> could have matched. Do not re-run them.

`vrf-decoding-research.md` Part 1 is built on this claim:

> Because every property announces its own bit length, **you never need a type to safely skip a
> property — only to decode its value.**

The predicted encoding is a flat loop of `[packed handle][packed NumBits][payload]` terminated by
handle 0. **That loop does not parse this capture.** Measured, on 8,000 non-opening bunches:

- Content-block *framing* is confirmed: two flag bits then a packed `NumPayloadBits` that lands
  exactly on the bunch boundary in 6,517 of 8,000 cases (81.4%). A length field cannot hit the
  boundary that often by chance.
- Inside that payload, the handle/`NumBits` loop yields **zero** clean parses under every variant
  tried: at bit offsets 0–4, with and without a leading rep-layout flag, split by all four
  combinations of the two header bits.
- The leading packed integers decode to implausible values (billions, not small handles),
  which is what happens when a packed-int reader is pointed at data that is not packed ints.

So for this title the property payload is **not** self-delimiting in the documented way, and a
structural-only property timeline — the plan's M5 deliverable — is not reachable by that route.
`libraries/vrfnet/actors.py` reports the payload rather than guessing at it.

Two hypotheses worth testing next, in order:

1. **`FRepLayout::ReceiveProperties_r` rather than `..._BackwardsCompatible`.** The non-backwards-
   compatible path sends handles *without* bit lengths, because a receiver that knows the layout
   does not need them. That would make a schema mandatory rather than optional, and would fully
   explain the observations. Against it: the frame prologue ships `NetFieldExportGroup`s with
   `CompatibleChecksum`, which exist *only* to serve the backwards-compatible path — so something
   consumes them.
2. **A per-payload preamble** before the handle loop, e.g. a checksum or a rep-layout selector,
   that shifts the first handle off bit 0 by a non-constant amount.

The four-versus-three flag-bit discrepancy suggests Riot has modified this area of the engine, so
neither hypothesis should be assumed to match stock UE.

---

## Reproducing

```
runners\test.bat                                  # 28 bit-reader vectors
runners\vrf-net.bat calibrate out/039f3991_blocks/block002_replaydata.bin --limit 4000 --save
runners\vrf-net.bat decode    out/039f3991_blocks/block00{0,2}_replaydata.bin
runners\vrf-net.bat actors    out/039f3991_blocks/block00{0,2}_replaydata.bin
runners\vrf-net.bat exports   out/039f3991_blocks/block000_replaydata.bin --filter PlayerState
```

`clean packets` in the `decode` report is the health metric for the whole decoder. Bit-level
desync is not subtle; anything below ~99% means a layout is wrong, not that the data is noisy.

Note the calibration guard: on a small sample it reports **INCONCLUSIVE** even while picking the
correct winner (89 packets → 97.75%, below the 99% bar). Feed it a few thousand packets.
