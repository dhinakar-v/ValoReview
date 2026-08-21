# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Requires [uv](https://docs.astral.sh/uv/). Runners are `.bat` wrappers that `pushd` to the repo root, forward all arguments and propagate the exit code — they work from any directory.

```
uv sync                                    # create .venv, install project + dev tools
runners\test.bat                           # uv run pytest
runners\test.bat tests/test_vrfview.py     # one file
runners\test.bat tests/test_vrfview.py -k killer_victim   # one test
runners\lint.bat                           # ruff check .   (config: ruff.toml)
runners\format.bat                         # ruff format .
```

Pipeline CLIs: `runners\vrf-reader.bat`, `vrf-to-json.bat`, `vrf-net.bat`, `vrf-view.bat`, `fetch-assets.bat` — see README for their subcommands.

## Import layout

`libraries/` is the **source root, not a package**. `pyproject.toml` maps its contents onto the install root (`sources = ["libraries"]`), so `import vrf_reader`, `import vrfnet`, `import vrfview` resolve after `uv sync` — never `libraries.vrfnet`. `scripts/` is *not* installed; pytest reaches it via `pythonpath = ["scripts"]`. Adding a new CLI means a file in `scripts/` plus a runner in `runners/`; adding importable code means `libraries/`.

Note the deliberate name pairing: `scripts/vrf_net.py` drives `libraries/vrfnet/`, `scripts/vrf_view.py` drives `libraries/vrfview/`. They must not sit in the same directory or the package shadows the script on import.

## Architecture

Four layers, bottom up:

**Container — `libraries/vrf_reader.py`, `vrf_to_json.py`.** A `.vrf` is a UE local-file replay container with Riot additions: fixed header then `[uint32 type][uint32 size][payload]` chunks of type HEADER / REPLAYDATA / CHECKPOINT / EVENT. Nothing is encrypted. Only REPLAYDATA and CHECKPOINT are Oodle-compressed (Mermaid); everything the viewer and the event timeline need lives in plain chunks, which is why the viewer needs no DLL.

**Replication stream — `libraries/vrfnet/`.** A port of the UE net stack, one module per engine concept, each mirroring a named UE class: `demodriver` (byte-addressed demo frames, `UDemoNetDriver`) → `datachannel` (bit-addressed packets → bunches, `UNetConnection`/`FInBunch`) → `actors` (`UActorChannel`, spawn identity and content-block framing), with `packagemap` (`UPackageMapClient` — NetGUID cache and net field export groups) and `session` (state that persists across blocks: GUID cache, export table, channel table) spanning all of them. `bitreader` is LSB-first and backed by a Python int, so construct one per playback packet (≤2048 bytes), never per decompressed block.

Everything down to the content block is decoded; the **property payload interior is not** — the documented `[handle][NumBits][payload]` loop does not parse this title. `actors.py` reports the payload rather than guessing. See `docs/vrf-decoding-findings.md` § "The premise that did not hold" before attempting it.

**Names — `libraries/valapi.py`, `valcatalog.py`.** `valapi` is a stdlib client for Riot's official API (`docs/valorant-api.md` is its reference); `valcatalog` reduces a `val-content-v1` response — or the `fetch-assets` manifest, which needs no key — to the only two joins a replay needs: map asset path → name, agent UUID → name. `vrfview/names.py` applies them and nothing else consumes them.

**Viewer — `libraries/vrfview/`.** `loader` converges a `.vrf` and a `vrf_to_json` JSON onto one `Replay` (tests assert the two produce equal models); `infer` derives everything the file does not state; `state.state_at(t)` recomputes a snapshot from scratch per frame (no accumulation, so seeking backwards is as correct as playing forward); `layout`/`scene`/`controls`/`clock`/`theme` are the Tk UI. `model`, `infer`, `state` and `layout` import no tkinter and must stay runnable headlessly.

## Conventions that matter here

**No positions exist.** The replication stream's property payloads are undecoded, so there is no player position, rotation or map geometry anywhere in this pipeline. The scene is an explicit schematic and captions itself as one — do not let anything imply a minimap.

The one thing drawn at real map coordinates is the **map reference window** (`vrfview/mapref.py`, the *Map* button): Riot's own callouts, from the `assets/manifest.json` transforms, via `vrfview/art.py`. It is safe because it describes the map and not the match — it is the same picture for every replay on Bind — and it is structurally unable to do otherwise, because `mapref.show` is handed no `Replay`. Keep it that way; the day positions land they belong in the scene, not smuggled in here.

**Art is a picture, never a claim.** `vrfview/art.py` is a second reader over `assets/manifest.json` — `valcatalog` takes names from it, `art` takes file paths, the transform and the callouts. Art resolution is deliberately not part of the model: it never touches `Replay`, has its own `ART CACHE` block in the provenance panel, and a missing or partial `assets/` costs a roster band and a button and changes nothing the viewer states (`--no-art` forces that path). Read every PNG path out of the manifest's `files` dict — never build one from a display name, or `KAY/O` breaks. Tk scales by whole factors only, so `art.subsample_for` sizes tiles from each file's real IHDR.

**Names are looked up, never invented, and the lookup is offline by default.** Map and agent names are external knowledge, so they live in `vrfview/names.py` rather than `infer`, and they append to `Replay.catalog_notes` rather than `Replay.notes` — a looked-up fact and a derived one are different claims. The search order is `--catalog` → `assets/content-<locale>.json` → `assets/manifest.json` → the built-in `loader.MAP_NAMES` table, and whichever answered is always reported. Only `vrf-view.bat catalog --refresh` opens a socket: no command needs `RIOT_API` to view or dump a replay. Agent names stay a **roster** — nothing in the file links a loadout to an actor net ID, so no player node carries an agent. `val-match-v1` (player names, ranks, economy, positions) is 403 without a production key, so it is implemented and diagnosed but never depended on.

**Read vs. inferred is never blurred.** `loader` fills in only what the file states; `infer` derives teams (bipartite two-colouring of the kill graph), round outcomes, sides and reconnect merges, appends a line to `Replay.notes` for each derivation, and leaves an explicit unknown where it cannot decide. The UI surfaces those notes. Keep new derivations in `infer` and keep them noted.

**`characterDeath` args: `args[1]` is the killer, `args[2]` the victim.** The summary doc originally had this reversed; the symptom is not a crash but players dying twice in a round. `test_killer_victim_order_is_not_reversed` pins it.

**`clean_packet_rate` is the decoder's health metric.** Bit-level desync does not degrade gracefully, so anything below ~99% means a layout is wrong, not that the data is noisy. It doubles as the calibration score.

**Version gates are calibrated, not guessed.** The `EEngineNetworkVersionHistory` thresholds for `++Ares-Core+release-11.11` are not public, so `vrfnet/versions.Features` is a plain policy object and `vrfnet/calibrate.py` sweeps every candidate against real packets, scoring by how many bunch loops consume to exactly zero leftover bits. The answer is committed at `libraries/vrfnet/calibrated.json`. Never hard-code a gate; re-run `vrf-net.bat calibrate ... --save` with a few thousand packets (small samples report INCONCLUSIVE even when the winner is right).

**Oodle is never vendored.** `libraries/oodlefind.py` resolves `oo2core_*_win64.dll` in order: `--oodle-dll` → `VRF_OODLE_DLL` (real env, then nearest `.env` via `libraries/envfile.py`) → `vendor/` → cache → Steam/Epic library scan. The first two are configured deliberately, so a nonexistent path raises rather than falling through to a scan. Valorant itself cannot supply one (statically linked, exports no Oodle symbols).

**No runtime dependencies.** stdlib + tkinter only; dev group is pytest + ruff. `envfile.py` exists instead of python-dotenv for this reason. Keep it that way unless asked.

## Tests

`unittest`-style classes run under pytest. Everything runs headlessly with no `.vrf`, no display and no network: `Demos/`, `out/` and `assets/` are gitignored, so tests needing the reference capture (`Demos/039f3991-5472-4119-bed2-838da0935f60.vrf`) are `skipUnless(...exists())`. Network and DLL-loading tests use small inline fixtures.

Ruff runs with nearly every rule family enabled (see `ruff.toml`); test files get a per-file exemption list. Expect lint feedback on error-message style, pathlib usage, boolean traps and complexity.

## Docs

`docs/vrf-decoding-findings.md` is measured truth about this capture and supersedes `docs/vrf-decoding-research.md`, which is a literature review that is **partly wrong for this title**. `docs/039f3991_summary.md` §8 lists what is not in the file and is the target backlog. Handoff docs (`*-handoff.md`) are point-in-time session summaries.
