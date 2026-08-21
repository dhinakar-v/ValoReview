# Valorant Replay - Key/Value Summary

`039f3991-5472-4119-bed2-838da0935f60.vrf`

Extracted from `out/039f3991.json` (parser output for the VRF container).

## 1. Source File

| Key | Value |
|---|---|
| File name | `039f3991-5472-4119-bed2-838da0935f60.vrf` |
| Path | `E:\Personal\val-replay-analyzer\Demos\039f3991-5472-4119-bed2-838da0935f60.vrf` |
| Size | 47,509,693 bytes (45.3 MiB) |
| SHA-256 | `941d1281ff51aac2fd24f0e730511e5c73ccc93ee1b721a2d491766fc39ee527` |
| Oodle DLL used | True - `oo2core_8_win64.dll` |

## 2. Match Identity

| Key | Value |
|---|---|
| Match / replay ID | `039f3991-5472-4119-bed2-838da0935f60` |
| Container GUID | `95A4F03E7E0B49E4BA43D35694FF87D9` |
| Recorded (UTC) | 2025-12-28T11:27:46.235000+00:00 |
| Duration | 26:11.721 (1,571,721 ms) |
| Map (internal) | `/Game/Maps/Infinity/Infinity` |
| Map (public name) | Abyss *(inferred: internal codename `Infinity`)* |
| Game build | `++Ares-Core+release-11.11` |
| Network version | 480767974 |
| Changelist | 4,091,853 |
| Live recording | no (VOD) |
| Players | 10 |
| Rounds recorded | 15 |

## 3. Container / Format

| Key | Value |
|---|---|
| Container magic | `0x43F4EFDD` |
| Container file version | 7 |
| Demo magic | `0x2CF5A13D` |
| Demo version | 19 |
| Header chunk | offset 594, 223,192 bytes |
| Chunk table start | 586 |
| Chunk table reaches EOF | True |
| Encrypted | False |
| Compressed | True (codec: Mermaid) |
| Compressed payload | 47,260,106 bytes |
| Decompressed payload | 127,871,988 bytes |
| Compression ratio | 2.706x |
| Timestamp ticks | 639025180662350000 |

## 4. Chunk Inventory

Total chunks: **175**

| Type | Count | Bytes |
|---|---:|---:|
| CHECKPOINT | 15 | 3,422,578 |
| EVENT | 143 | 23,159 |
| HEADER | 1 | 223,192 |
| REPLAYDATA | 16 | 43,838,778 |
| **Total** | **175** | **47,507,707** |

## 5. Players (from header `playerLoadouts`)

The file stores anonymised `subject` UUIDs and `characterId` only - no display names, ranks, or teams.

| # | Subject UUID | Character UUID | Agent* |
|---:|---|---|---|
| 0 | `19c14046-bb7d-5c30-84e6-b09b4910cbce` | `41fb69c1-4189-7b37-f117-bcaf1e96f1bf` | Astra |
| 1 | `3e8d64f5-f985-5ba4-8ad7-cb65dcdca1c5` | `1e58de9c-4950-5125-93e9-a0aee9f98746` | Killjoy |
| 2 | `9ada8cec-e510-5699-a02f-a8e4c53b98f6` | `df1cb487-4902-002e-5c17-d28e83e78588` | Waylay |
| 3 | `8db3a734-f946-5786-bc83-70ab5a8d6bbf` | `320b2a48-4d9b-a075-30f1-1f93a9b638fa` | Sova |
| 4 | `f3a66293-1b80-5b78-8537-2c1281bdaf7f` | `a3bfb853-43b2-7238-a4f1-ad90e9e46bcc` | Reyna |
| 5 | `989e9bfd-7296-56a0-ab06-278ad5a25ce3` | `320b2a48-4d9b-a075-30f1-1f93a9b638fa` | Sova |
| 6 | `f44c3db5-4981-5c84-8cb6-888755d9827e` | `a3bfb853-43b2-7238-a4f1-ad90e9e46bcc` | Reyna |
| 7 | `dd6341a6-1666-5c28-931c-28cd7687185d` | `9f0d8ba9-4140-b941-57d3-a7ad57c6b417` | Brimstone |
| 8 | `b01c5727-f95e-5cd6-85df-f01e0bc4fddc` | `22697a3d-45bf-8dd7-4fec-84a9e28c69d7` | Chamber |
| 9 | `4169c636-70af-5d50-a6e3-ef7d78f4729b` | `f94c3b30-42be-e959-889c-5aa313dba261` | Raze |

\* Agent names come from the public Valorant agent-UUID list, **not** from the file itself. Two Sovas and two Reynas appear - i.e. one of each per team.

Each loadout entry carries `sprays` (0 selections for player 0), `expressions.aESSelections` (4), `items` (19 weapon/skin entries with nested `sockets`), and `options`. All values are cosmetic asset GUIDs.

## 6. Events

Total events: **143**

| Group | Count | Enum | Type ID |
|---|---:|---|---:|
| characterDeath | 108 | `EReplayEventGroup::CharacterDeath` | 8 |
| roundStarted | 15 | `EReplayEventGroup::RoundStart` | 2 |
| characterUltimateUsed | 9 | `EReplayEventGroup::CharacterUltimateUsed` | 11 |
| spikePlanted | 7 | `EReplayEventGroup::SpikePlanted` | 4 |
| spikeDefused | 2 | `EReplayEventGroup::SpikeDefused` | 5 |
| switchTeams | 1 | `EReplayEventGroup::SwitchTeams` | 3 |
| spikeExploded | 1 | `EReplayEventGroup::SpikeExploded` | 6 |

Event record shape: `id`, `group`, `metadata`, `time1_ms`/`time2_ms`, `enum_name`, `type_id`, `args`, `payload_bytes`, `payload_hex`. `args[0]` repeats the type ID; the remaining args are actor net IDs. `metadata` holds the round number on `roundStarted` (and `11` on `switchTeams`), and is empty otherwise.

### Round timeline

| Round | `metadata` | Start | Deaths | Ults | Spike planted | Defused | Exploded |
|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | 0 | 00:00.063 | 8 | 0 | 0 | 0 | 0 |
| 2 | 1 | 02:01.108 | 6 | 0 | 0 | 0 | 0 |
| 3 | 2 | 03:22.830 | 8 | 0 | 1 | 0 | 0 |
| 4 | 3 | 05:00.759 | 8 | 1 | 1 | 1 | 0 |
| 5 | 4 | 07:01.581 | 7 | 1 | 0 | 0 | 0 |
| 6 | 5 | 08:23.961 | 6 | 1 | 0 | 0 | 0 |
| 7 | 6 | 09:42.930 | 6 | 0 | 0 | 0 | 0 |
| 8 | 7 | 11:30.852 | 6 | 0 | 0 | 0 | 0 |
| 9 | 8 | 12:36.288 | 7 | 5 | 1 | 0 | 0 |
| 10 | 9 | 14:09.337 | 8 | 0 | 0 | 0 | 0 |
| 11 | 10 | 16:20.205 | 8 | 0 | 1 | 1 | 0 |
| 12 | 11 | 18:43.337 | 8 | 1 | 0 | 0 | 0 |
| 13 | 12 | 20:35.391 | 7 | 0 | 1 | 0 | 1 |
| 14 | 13 | 22:40.309 | 7 | 0 | 1 | 0 | 0 |
| 15 | 14 | 24:06.463 | 8 | 0 | 1 | 0 | 0 |

Side switch (`switchTeams`) fires at **20:35.236**, inside round 12 - consistent with a 12-round first half followed by a second segment in this 15-round recording.

### Per-actor kills & deaths

Actor net IDs come from `characterDeath.args`: **`args[1]` is the killer, `args[2]` the victim.** Ten distinct IDs match the ten players, but the file gives no link from an actor ID back to a `subject`.

> **Corrected 2026-08-21.** This was previously documented the other way round. Under the
> old reading every one of the 15 rounds contains a player who dies twice - in round 1,
> actor 646 dies at 87.3s, dies again at 105.3s, then scores a kill at 114.0s. Under the
> reading above, **0 of 15** rounds have a repeat victim, 13 of 15 rounds terminate on an
> exact five-player wipe, and the team that wins 9-2 has all five players at positive K/D
> while the losing five are all negative. The table below was inverted by the same error
> and has been recomputed.

Team A / Team B below are **inferred**, not read from the file: the kill graph is bipartite
(0 same-team kills in 108) and admits exactly one 5v5 split. Actor 852 has one self-kill,
counted as a death but not as a kill, which is why kills total 107 against 108 deaths.

| Actor ID | Team | Kills | Deaths | K/D | Ults used |
|---:|:---:|---:|---:|---:|---:|
| 958 | A | 15 | 10 | 1.50 | 1 |
| 852 | A | 14 | 4 | 3.50 | 1 |
| 546 | A | 14 | 6 | 2.33 | 1 |
| 1258 | A | 14 | 12 | 1.17 | 2 |
| 1362 | A | 11 | 8 | 1.38 | 0 |
| 1160 | B | 10 | 13 | 0.77 | 0 |
| 1058 | B | 9 | 11 | 0.82 | 1 |
| 646 | B | 7 | 15 | 0.47 | 1 |
| 744 | B | 7 | 15 | 0.47 | 1 |
| 1462 | B | 6 | 14 | 0.43 | 1 |
| **Total** | | **107** | **108** | | **9** |

## 7. Data Blocks (decompressed payload)

31 blocks - 16 REPLAYDATA + 15 CHECKPOINT, all Oodle **Mermaid**-compressed. Raw block dumps were written to `out/039f3991_blocks/`.

| # | Kind | Label | From | To | Compressed | Decompressed | Ratio | Name-table entries |
|---:|---|---|---|---|---:|---:|---:|---:|
| 0 | REPLAYDATA | - | 00:00.000 | 00:00.046 | 68,683 | 144,034 | 2.0971 | 1,701 |
| 1 | CHECKPOINT | checkpoint0 | 00:00.046 | 00:00.046 | 72,764 | 219,867 | 3.0216 | 1,589 |
| 2 | REPLAYDATA | - | 00:00.046 | 02:00.960 | 3,010,263 | 8,704,714 | 2.8917 | 4,416 |
| 3 | CHECKPOINT | checkpoint1 | 02:00.960 | 02:00.960 | 167,982 | 509,666 | 3.0341 | 4,407 |
| 4 | REPLAYDATA | - | 02:00.960 | 03:22.686 | 2,499,355 | 6,306,685 | 2.5233 | 1,108 |
| 5 | CHECKPOINT | checkpoint2 | 03:22.686 | 03:22.686 | 181,801 | 553,477 | 3.0444 | 4,954 |
| 6 | REPLAYDATA | - | 03:22.686 | 05:00.618 | 2,739,921 | 7,081,014 | 2.5844 | 1,194 |
| 7 | CHECKPOINT | checkpoint3 | 05:00.618 | 05:00.618 | 199,369 | 603,714 | 3.0281 | 5,428 |
| 8 | REPLAYDATA | - | 05:00.618 | 07:01.420 | 3,154,166 | 8,334,996 | 2.6425 | 937 |
| 9 | CHECKPOINT | checkpoint4 | 07:01.420 | 07:01.420 | 209,732 | 636,816 | 3.0363 | 5,680 |
| 10 | REPLAYDATA | - | 07:01.420 | 08:23.816 | 2,593,976 | 6,536,642 | 2.5199 | 1,031 |
| 11 | CHECKPOINT | checkpoint5 | 08:23.816 | 08:23.816 | 221,477 | 661,477 | 2.9867 | 5,832 |
| 12 | REPLAYDATA | - | 08:23.816 | 09:42.781 | 2,675,744 | 6,481,014 | 2.4221 | 819 |
| 13 | CHECKPOINT | checkpoint6 | 09:42.781 | 09:42.781 | 231,471 | 680,923 | 2.9417 | 5,940 |
| 14 | REPLAYDATA | - | 09:42.781 | 11:30.682 | 3,357,319 | 8,713,094 | 2.5953 | 690 |
| 15 | CHECKPOINT | checkpoint7 | 11:30.682 | 11:30.682 | 237,896 | 692,142 | 2.9094 | 6,001 |
| 16 | REPLAYDATA | - | 11:30.682 | 12:36.144 | 2,117,676 | 5,688,058 | 2.686 | 760 |
| 17 | CHECKPOINT | checkpoint8 | 12:36.144 | 12:36.144 | 245,206 | 707,229 | 2.8842 | 6,130 |
| 18 | REPLAYDATA | - | 12:36.144 | 14:09.166 | 3,019,613 | 7,358,076 | 2.4368 | 1,080 |
| 19 | CHECKPOINT | checkpoint9 | 14:09.166 | 14:09.166 | 263,490 | 748,376 | 2.8402 | 6,421 |
| 20 | REPLAYDATA | - | 14:09.166 | 16:19.991 | 3,233,585 | 9,184,900 | 2.8405 | 745 |
| 21 | CHECKPOINT | checkpoint10 | 16:19.991 | 16:19.991 | 265,811 | 754,403 | 2.8381 | 6,463 |
| 22 | REPLAYDATA | - | 16:19.991 | 18:43.146 | 3,737,732 | 10,448,529 | 2.7954 | 757 |
| 23 | CHECKPOINT | checkpoint11 | 18:43.146 | 18:43.146 | 274,268 | 768,831 | 2.8032 | 6,558 |
| 24 | REPLAYDATA | - | 18:43.146 | 20:35.244 | 2,885,242 | 9,007,767 | 3.122 | 1,006 |
| 25 | CHECKPOINT | checkpoint12 | 20:35.244 | 20:35.244 | 261,073 | 756,390 | 2.8972 | 6,519 |
| 26 | REPLAYDATA | - | 20:35.244 | 22:40.145 | 3,389,559 | 9,389,683 | 2.7702 | 1,529 |
| 27 | CHECKPOINT | checkpoint13 | 22:40.145 | 22:40.145 | 290,759 | 798,799 | 2.7473 | 6,727 |
| 28 | REPLAYDATA | - | 22:40.145 | 24:06.286 | 2,390,624 | 6,468,819 | 2.7059 | 807 |
| 29 | CHECKPOINT | checkpoint14 | 24:06.286 | 24:06.286 | 298,613 | 811,126 | 2.7163 | 6,799 |
| 30 | REPLAYDATA | - | 24:06.286 | 26:11.721 | 2,964,936 | 8,120,727 | 2.7389 | 910 |
| | | | | | **47,260,106** | **127,871,988** | **2.706** | **104,938** |

### Block internals

| Key | Value |
|---|---|
| REPLAYDATA frame header | `level_index`, `time_seconds` (block 0: level 0 @ 0.007811s) |
| CHECKPOINT header | no frame header; 16-byte `preamble_hex` (block 1: `bbc30200000000000000000000000000`) |
| Name table (block 0) | 1,701 entries = 609 asset paths + 1,092 property names |
| Largest name table | block 29 (checkpoint14): 6,799 entries |
| Replication stream | **not decoded on this capture** - the payloads are obfuscated and no transform exists for 11.11; see the note under section 8 |

Sample asset paths: `/Game/Characters/_Core/BaseJanusController`, `/Game/Equippables/Buddies/...`, `/Game/CloserCeremony`, `/Game/ClutchCeremony`.

Sample property names: `AresAbilitySystem`, `AresAttributeSet`, `BombGameMode_C`, `Bomb_CombatReportComponent_C`, `BasicCombatStatsComponent`, `AFKDetectionComponent`, `BlueTeam`, `AverageLoadoutValue`.

## 8. What Is Not in This JSON

- Player display names / Riot IDs, team assignment, round win-loss results
- Scoreline, economy, weapon used per kill, damage numbers, positions
- Any mapping from event actor net IDs back to `subject` UUIDs

All of that lives inside the bit-packed UE replication stream, which the parser decompresses but does not decode on this capture.

> **Partly superseded, 2026-08-22.** "Decoding needs the game's class layouts" was the wrong
> diagnosis. The property payloads are *obfuscated* -- whitened with a keystream seeded
> `payload_bits ^ actor_net_guid` -- and underneath they are stock UE. `libraries/vrfnet/
> payload_transform.py` undoes that for 12.10, 12.11 and 13.00-13.02, and on those builds
> **player positions and the agent each actor is playing are decoded** and drawn on a real map
> (`vrf-view.bat dump <file>.vrf --positions`, or the viewer's DECODE POSITIONS button).
>
> **Abilities too, on those builds.** Every ability opens actor channels whose archetype paths name
> the agent and the keybind -- `/Game/Characters/Killjoy/S0/Ability_E/Pawn_Killjoy_E_Turret` -- so
> `libraries/vrfview/abilities.py` reads casts out of them even though section 6 above shows there
> is no ability event of any kind. What that still cannot give is *where*: the spawn transform is
> not decoded, and of every ability archetype seen in a full capture only the `Pawn_` ones emit a
> movement record, so a drone and a turret have paths and a thrown smoke has a time and nothing
> else. No ability range, radius or damage figure exists in the replay or in Riot's catalogue.
>
> None of it applies to `039f3991...`: the transforms are derived per build against the shipped
> binary and 11.11 is long gone from the live client, so this capture correctly refuses. The list
> above therefore still holds *for this file*. Player names, economy, damage and the actor-to-
> `subject` join remain out of reach on every build.

