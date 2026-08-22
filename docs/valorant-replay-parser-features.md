# ValorantReplayParser: what it extracts, and what that means for this project

A capability inventory of [`michel-giehl/ValorantReplayParser`](https://github.com/michel-giehl/ValorantReplayParser),
cross-referenced against this repository. It doubles as the backlog for
`docs/039f3991_summary.md` §8, which lists what a `.vrf` was thought not to
carry -- most of §8 turns out to be reachable, and this document says where.

Read at commit `99d9646` ("feat: Add harbor ultimate", 2026-08-01) from a
reference clone. MIT, C#, .NET 10. Its own README grades itself: Player
Movement ✔, Agents ✔, Abilities 🚧, Gunplay ✔, Game State ❌, World State ❌,
Stable public API ❌.

Claims marked **(verified here)** were checked against the clone or against a
real capture on this machine. Everything else is read off the source and is
reported as the source states it.

---

## 1. Container level

`ReplayChunkDispatcher` reads `ReplayInfo`, then the first `Header` chunk, then
walks the rest.

`ReplayChunkType`: `Header = 0`, `ReplayData = 1`, `Checkpoint = 2`,
`Event = 3`.

**It skips CHECKPOINT and EVENT chunks entirely** -- both are logged and
dropped (`"Skipping checkpoint chunk"` / `"Skipping event chunk"`), though
their offsets stay in `ReplayInfo.Chunks`. That is a capability *this* project
has and it does not: the whole `vrfview` event timeline, and every fact
`vrfhome/scan.py` puts on a match card, comes out of chunks it never reads.

| Type | Fields |
|---|---|
| `ReplayInfo` | `LengthInMs`, `NetworkVersion`, `Changelist`, `FriendlyName`, `Timestamp`, `TotalDataSizeInBytes`, `IsLive`, `IsValid`, `Compressed`, `Encrypted`, `EncryptionKey`, `HeaderChunkIndex`, `Chunks`, `DataChunks` |
| `ReplayHeader` | `NetworkVersion`, `NetworkChecksum`, `EngineNetworkProtocolVersion`, `GameNetworkProtocolVersion`, `Guid`, `MinRecordHz`, `MaxRecordHz`, `FrameLimitInMs`, `CheckpointLimitInMs`, `LevelNamesAndTimes` (the map), `Flags`, `GameSpecificData`, `Platform`, `BuildConfig`, `BuildTargetType` |
| `ReplayVersion` | `Major`, `Minor`, `Patch`, `Changelist`, `Branch` |
| `UEVersion` | `UE4Version`, `UE5Version`, `PackageVersionLicense` |

`ValorantReplayReader.ReadMetadata` returns all of the above without consuming
the archive, and reports `FullParseSupportStatus` for unsupported builds --
the same cheap-refusal idea as `vrfhome/scan.py`'s `positions_available`.

## 2. Replication stream

Events arrive through `IReplayEventSink.Emit(ReplayEvent)`, every one carrying
`TimeSeconds` and `PacketId`:

- **`ActorSpawned`** -- `ActorNetGuid`, `ChannelIndex`, `IsDynamic`, `ActorPath`,
  `ArchetypeNetGuid`, `ArchetypePath`, `ReplicationClassPath`, `LevelNetGuid`,
  and **`Location`, `Rotation`, `Scale`, `Velocity`**.
- **`ActorClosed`** -- `Reason` ∈ `{Destroyed, Dormancy}`.
- **`ExportGroupReceived`** / **`RpcReceived`** -- paths, categories, decoded
  field counts, `PayloadBits` vs `ParsedBits`, and the decoded payload.
- **`DecodedReplayField`** -- values typed `Bool, Byte, Int32, UInt32, Float,
  Double, String, NetGuid, Vector, Rotator, RepMovement, Object`.
- **`ValorantShotReceived`**, **`RemoteCharacterMovementReceived`** -- below.

`ParseProfile` gates the work by `ExportCategory` (`Movement, Ability, Gunplay,
Agent, GameState, Inventory, Economy, Effects, Visibility, Debug`), plus path
and field include/exclude sets. **(verified here)** That gate is worth a great
deal: restricting to `Movement` is most of why `csharp/VrfPositions` decodes a
full match in about four seconds.

## 3. VALORANT extraction

### 3.1 Movement and positions

`ReplaysClientReceiveRemoteCharacterUpdatesSingleArrayNoAutonomous` on
`BaseReplayController_C_ClassNetCache`, decoded by
`RemoteCharacterUpdatesRpcDecoder` (max 256 updates per batch), with the
bitstream in `ComponentDataStream` (magic `0x52`, `FixedVectorScale = 1/65536`,
`AngleScale = 360/65536`).

`MovementMove` carries `Position`, `Velocity`, `Yaw`, `Pitch`, `RotationInput`,
`Timestamp`, `ModeFlags`, `MovementState`, `PackedAngles`, `RawYaw`, `RawPitch`
and a dozen variant flags.

**Documented limitation:** `EmitMovementEvents` emits only the *latest* move
per update (`componentDataStream.LatestMove`), which the export manifest
records under `limitations`.

**(verified here)** That limitation costs nothing at this project's sample
rate. On the 12.10 Haven capture it yields **3,069,141 movement records over
154 actors** -- matching, to the record, what `vrfnet` produces -- and the two
decoders agree on all **10,544** samples of the stored decode, exactly, in
x, y, z, yaw and pitch. A full-match decode is **199,180 positions for 11
player actors**, which is the number `vrfview/positionfile.py` already cites
from a Python decode.

This is the part of the project that now runs through `csharp/VrfPositions`;
see `libraries/vrfview/csharpdecode.py`.

### 3.2 Gunplay

`ValorantShotReceived`, projected from `ReplayPlayContinuousEffectAtLocation`
on `ReplayEffectComponent_ClassNetCache`. `ValorantShot` carries `Location`,
`Rotation`, `AmmoRemaining`, `NumProjectiles`, `RandomSeed`, `TracerOption`,
`BurstShotNumber`, `YawSwitch`, `FiringPlayerState`, `Equippable`, `FireMode`
and `AttackVectors` (gameplay tags `FiringState.AttackVector.1` … `.15`).

`ValorantShotFireMode` ∈ `{Unknown, Primary, Alternate}`, resolved by matching
`SourceId` or the firing-state outer chain against markers `altfire`,
`zoomedfire`, `firingstateburst`, `burstmode` …, and recorded with the evidence
that decided it.

**(verified here)** 4,523 shot events on the 12.10 Haven capture.

**Weapons.** `ValorantEquippableResolver` maps class paths to 24 named
equippables in `{Unarmed, Melee, Bomb, Sidearm, Smg, Shotgun, Rifle,
SniperRifle, MachineGun, Ability}`: Classic, Shorty, Frenzy, Ghost, Compact
Pistol, Sheriff, Stinger, Spectre, Bucky, Judge, Bulldog, Guardian (filed as
`Rifle`), Phantom, Vandal, Marshal, Operator, Outlaw, Ares, Odin, Spike, Melee,
Unarmed, plus the two ability guns Headhunter and Tour de Force.

### 3.3 Damage and kills

`MulticastNotifyDamage_Base` / `_Point` on `DamageableComponent_ClassNetCache`,
with a fully mapped handle table:

`DamageTaken`, `DamageDealt`, `DamageKilledTarget`, `AliveAfterDamage`,
`EventInstigator`, `DamageCauser`, `EquippableUsed` (decoded to a named
weapon), `DamageType`, `DeltaLife`, `EventInstigatorPawn`,
`DamagerPlayerState`, `KillCreditPlayerState`, `RegionalDamage`, `Character`,
`NetTimestamp`, `RespawnNumber`, `EquippableUsedZoomed`. `_Point` adds
`DamagedBone`, `IsWallPenetration`, `FalloffMultiplier`, `Assister`,
`AssistingEquippableClass`, `KillsForKiller`, `KillsForVictim`.

`EAresRegionalDamage`: `Normal, Headshot, Legshot, …` -- so headshot rate is
derivable.

**Kills:** `MulticastNotifyKilledEnemy(KillerCharacter, KilledCharacter,
MultikillLevel)`, synthesised onto *every* agent's ClassNetCache, so kills are
decodable for all 29 agents.

Caveat: impact location/direction/normal and the assist list stay **raw bit
payloads**, not decoded structs.

### 3.4 Rounds, phases, economy

`BombGameStateDescriptor` exposes `MatchState`, `WinningTeam`,
`CompletionState`, `TeamEconomy`, `DisplayRemainingTime`, `GamePhaseElapsedTime`,
`MatchID`, `RoundResults`, `Phase`, `RoundNumber`, `BombState`.

`RoundResults` **is** decoded, into `AresRoundResult(RoundNumber, WinningTeam,
WinningTeamRole, RoundResult)` with `AresTeamRole ∈ {Attacker, Defender, …}`
and `AresRoundOutcome ∈ {Elimination, Defuse, Detonate, TimeExpired, Cheat,
Surrendered}`. Field handles are hard-coded to the release-13.01 layout, with a
raw-payload fallback otherwise.

`EAresGamePhase`: `NotStarted, GameStarted, BetweenRounds, RoundStarting,
InRound, RoundEnding, SwitchingTeams, GameEnded`. Lifecycle RPCs:
`ClientRoundStart`, `ClientBuyPhaseEnd`, `MulticastEndRound`,
`MulticastSetPhase`, `ClientResetRound`, side-switch.

**Economy is written but not switched on. (verified here)**
`AresTeamEconomyDecoder` / `CompatibleAresTeamEconomyDecoder` exist and are
unit-tested, but `grep -rn` over `src/` finds **no reference to either outside
their own file**; `BombGameStateDescriptor` wires `TeamEconomy` to a raw
payload. The same is true of `CombatRoundReportsDecoder` (the full per-round
damage matrix: `DamageDealt`, `HitsDealt`, `DamageReceived`, `DidKill`,
`DestroyedArmor`, per region, per participant) against
`BombCombatReportComponentDescriptor`. By contrast `AresRoundResultsDecoder`
*is* wired, which is what makes the comparison conclusive rather than a guess.

**Also defined but not registered in `ValorantDescriptors.CreateCatalog()`
(verified here):** `LightArmorItemDescriptor`, `HeavyArmorItemDescriptor`,
`PlasmaArmorItemDescriptor`, `AbilityCooldownComponentDescriptor`,
`AbilityRechargeComponentDescriptor`, `AbilityResourceComponentDescriptor`,
`SignatureAbilityResourceComponentDescriptor`,
`EquipmentChargeComponentDescriptor`, `SmokeAbilityDescriptor`. Registered and
live: `AmmoComponentDescriptor`, `AresInventoryDescriptor`,
`BombPlayerStateDescriptor`.

So armor state and ability charges/cooldowns are one `catalog.Add(...)` line
away each, not a decoding problem.

### 3.5 Player and team state

`BombPlayerStateDescriptor`: `PlayerId`, `CompetitiveTier`, **`Subject`** (the
Riot player UUID, as `FString`), `SpectatedPlayer`, `PlayerInfo`,
`SpawnedCharacter`, **`PossessedCharacter`**, `UltimateActive`,
`NumUltimatePoints`, `TotalAcquiredUltimatePoints`.

`BaseReplayPlayerState`: `IsAfk`, `ConnectionStatus`,
`AllPlayersObfuscatedPlayerInformation` (raw), `SubjectUniqueId` (raw).

`AresAttributeSet`: `Health`, `MaxHealth`, `Shield`, `MaxShield`, `Healing`,
`Damage`.

`Subject` beside `PossessedCharacter` is the single most valuable thing in this
document -- see §6.

### 3.6 Inventory

`AresInventoryDescriptor` (`CurrentEquippable`, `NewCurrentEquippable`,
`Character`, `ItemSlots` raw), `AmmoComponentDescriptor`
(`AuthResourceAmount`), `EquippableStateMachineComponentDescriptor`.

### 3.7 Agents and abilities

29 agent descriptors, each at
`/Game/Characters/<Codename>/<Codename>_PC.<Codename>_PC_C`:

| Codename | Agent | Codename | Agent | Codename | Agent |
|---|---|---|---|---|---|
| Aggrobot | Gekko | Iris | Miks | Sarge | Brimstone |
| BountyHunter | Fade | Killjoy | Killjoy | Sequoia | Iso |
| Breach | Breach | Mage | Harbor | Smonk | Clove |
| Cable | Deadlock | Nox | Vyse | Sprinter | Neon |
| Cashew | Tejo | Pandemic | Viper | Stealth | Yoru |
| Clay | Raze | Phoenix | Phoenix | Terra | Waylay |
| Deadeye | Chamber | Pine | Veto | Thorne | Sage |
| Grenadier | KAY/O | Rift | Astra | Vampire | Reyna |
| Guide | Skye | | | Wraith | Omen |
| Gumshoe | Cypher | | | Wushu | Jett |
| Hunter | Sova | | | | |

That table is the same `codename -> agent` join `vrfview/names.py` performs
through `developerName`, and it agrees everywhere the two overlap.

**Ability coverage is sparse: only 6 of 29 agents** have descriptors beyond the
generic actor -- Cypher (trapwire, cage), Harbor (wall, cove, and the whole
Tidal Wave ult with `MulticastInitialize` chunk geometry), Viper
(`MulticastAddSmokeScreenPoint`, so wall segment geometry is extractable),
Phoenix (flame wall), Neon (tunnel), Omen (dark cover).

`ClientActivateAbility` is declared with **no parameter descriptor**, so
ability *casts* are not decoded as such. Both projects therefore infer casts
from the actors they spawn -- which is exactly what
`libraries/vrfview/abilities.py` already does.

## 4. Version matrix

Two independent gates. Structural: `ReplayVersion 5.3.2`, `UE4Version 522`,
`UE5Version 1009`, `GameNetworkProtocolVersion 0`. And a registered payload
transform for the branch:

`++Ares-Core+release-` **12.10, 12.11, 13.00, 13.01, 13.02**

**These are the identical five** `libraries/vrfnet/payload_transform.py`
supports, which is why `vrfhome/scan.py`'s `SUPPORTED_BRANCHES` remains the
authority for this project and did not have to change. 11.11 is out of reach
for both, including the canonical `039f3991…` capture.

## 5. CLI

    dotnet run --project src\CliReader -- log <replay.vrf>
    dotnet run --project src\CliReader -- export <replay.vrf> --output <dir> [--profile default|viewer]

`export` writes `events.ndjson`, `movement.ndjson` and `manifest.json`
(schema 4; source SHA-256, build, duration, packet stats, per-type counts, a
full dump of the net-field export groups, and a `filtered_export_group_summary`
sorted by frequency -- a ready-made "what is not modelled yet" report).

`--profile viewer` adds `CaptureDiagnosticFields`.

**(verified here)** The export is complete but very large, because there is no
category flag on the CLI. One 40-minute match:

| Profile | Time | Output |
|---|---|---|
| `viewer` | 86 s | 7.8 GB (5.4 GB events + 2.5 GB movement) |
| `default` | 60 s | 5.3 GB (2.8 GB events + 2.5 GB movement) |
| `csharp/VrfPositions` (this repo, Movement only) | **4 s** | **15 MB** |

That gap is the entire reason this project has its own emitter rather than
shelling out to `CliReader`: it needs ~3,245 `actor_spawned` lines and thinned
movement, and `default` would write 2.8 GB of `export_group_received` and
`rpc_received` to deliver them.

`NetGuidCacheReader <replay> <out>` dumps the export groups as text -- the tool
to reach for when reverse-engineering a new handle layout.

## 6. Gap analysis

### Now within reach that was not

Each of these is listed in `docs/039f3991_summary.md` §8 as absent, and each is
decoded by this parser on a supported build:

- **The actor → `subject` join.** §8 calls out "any mapping from event actor
  net IDs back to `subject` UUIDs", and `CLAUDE.md` still states the loadout
  roster is not attributable to actor net IDs. `BombPlayerStateDescriptor`
  carries `Subject` (the Riot UUID) *and* `PossessedCharacter` on the same
  actor. This is the join, and it would let `Loadout` and `Player` be filled
  from one another instead of being kept deliberately apart.
- **Weapon used per kill** -- `EquippableUsed`, resolved to a named weapon.
- **Damage numbers** -- `DamageDealt`/`DamageTaken`, with region, wall-pen and
  falloff, plus `Health`/`Shield` from `AresAttributeSet`.
- **Round win/loss results** -- `AresRoundResult`, with the outcome reason.
  Note this still does **not** produce the brief's `WIN`/`LOSS` card badge:
  that needs a *local player*, and nothing in the file names one, so
  `scan.RESULT_NOT_IN_FILE` stays correct.
- **Economy** -- decoder written, one registration line from working.
- **Ability spawn coordinates.** `CLAUDE.md` states "the spawn transform is not
  decoded at all, so a smoke has a time and no coordinate". `ActorSpawned`
  carries `Location`. `csharp/VrfPositions` already emits it as
  `spawn_locations`; nothing consumes it yet.

### Still out of reach, for both projects

- **Player display names / Riot IDs.** `Subject` is a UUID; the name is not in
  the file, and `val-match-v1` is 403 without a production key.
- **Spike plant/defuse position, planter, or timer.** Only an opaque
  `BombState` int and `AresRoundOutcome.{Defuse, Detonate}`.
- **Ability range, radius or damage figures** -- not in the replay and not in
  `val-content-v1`.
- **Projectile arcs.** Confirmed from the other direction here: only `Pawn_`
  actors emit movement records.
- **Map geometry / collision.** README: World State ❌. `vrfview/sight.py`'s
  radar-alpha raycast remains an approximation of a silhouette, and says so.

### Where this project is ahead

- **CHECKPOINT and EVENT chunks**, which it skips entirely -- the whole event
  timeline and every match-card fact.
- **`vrfhome`**: a cached, headless scan of a 101-file library in 4.3 s cold.
- **Names and art**: `valapi`/`valcatalog`/`names` join map and agent names
  offline; there is no equivalent.
- **A viewer at all.**
- **The honesty conventions**: read-vs-inferred kept apart, every derivation
  noted, `RESULT_NOT_IN_FILE` rather than a guessed badge, and a sentence
  wherever a drawing would overclaim.

### What was *not* worth taking

Its **decompressor**. `OozSharpOodleDecompressor` wraps the NuGet package
`OozSharp 3.0.1`, which lives in `Shiqan/FortniteReplayDecompressor` and is a
922-line `unsafe` C# transliteration of `powzix/ooz`. **(verified here)** it
implements **Mermaid only, and within Mermaid only the raw/memcpy chunk path**:
`Huff` occurs 0 times in `Kraken.cs` and `Tans` 0 times, and seven paths throw
`NotImplementedException`, including `DecodeBytes` itself. `Kraken.cs` also
carries a **GPLv3** header while the package ships an MIT `LICENSE`.

It is slower than the native `oo2core` this project used to bind, and
decompression was never the cost: a full match is 31 blocks, 47.2 MB → 127.9 MB,
about one second of a four-minute decode. The four minutes were Python
bit-parsing. See `libraries/vrfview/csharpdecode.py`.

It does work, though, and that matters: **(verified here)** all **21** supported
captures in the reference library decode through it with **0 failures**, across
12.10, 12.11 and 13.00.
