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

Pipeline CLIs: `runners\vrf-reader.bat`, `vrf-to-json.bat`, `vrf-net.bat`, `vrf-view.bat`, `vrf-app.bat`, `make-icons.bat`, `fetch-assets.bat` — see README for their subcommands.

## Import layout

`libraries/` is the **source root, not a package**. `pyproject.toml` maps its contents onto the install root (`sources = ["libraries"]`), so `import vrf_reader`, `import vrfnet`, `import vrfview` resolve after `uv sync` — never `libraries.vrfnet`. `scripts/` is *not* installed; pytest reaches it via `pythonpath = ["scripts"]`. Adding a new CLI means a file in `scripts/` plus a runner in `runners/`; adding importable code means `libraries/`.

Note the deliberate name pairing: `scripts/vrf_net.py` drives `libraries/vrfnet/`, `scripts/vrf_view.py` drives `libraries/vrfview/`. They must not sit in the same directory or the package shadows the script on import.

## Architecture

Four layers, bottom up:

**Container — `libraries/vrf_reader.py`, `vrf_to_json.py`.** A `.vrf` is a UE local-file replay container with Riot additions: fixed header then `[uint32 type][uint32 size][payload]` chunks of type HEADER / REPLAYDATA / CHECKPOINT / EVENT. Nothing is encrypted. Only REPLAYDATA and CHECKPOINT are Oodle-compressed (Mermaid); everything the viewer and the event timeline need lives in plain chunks, which is why the viewer needs no DLL.

**Replication stream — `libraries/vrfnet/`.** A port of the UE net stack, one module per engine concept, each mirroring a named UE class: `demodriver` (byte-addressed demo frames, `UDemoNetDriver`) → `datachannel` (bit-addressed packets → bunches, `UNetConnection`/`FInBunch`) → `actors` (`UActorChannel`, spawn identity and content-block framing), with `packagemap` (`UPackageMapClient` — NetGUID cache and net field export groups) and `session` (state that persists across blocks: GUID cache, export table, channel table) spanning all of them. `bitreader` is LSB-first and backed by a Python int, so construct one per playback packet (≤2048 bytes), never per decompressed block.

**The property payload is obfuscated, not unparsed.** Riot whitens every content-block payload with a keystream seeded `payload_bits ^ actor_net_guid`; underneath it is stock UE. `payload_transform` undoes it (one class per build, ported from `michel-giehl/ValorantReplayParser`, MIT — see `THIRD_PARTY.md`), `properties` runs the property loop, and `movement` decodes the RPC that carries player positions. **Never add a nearest-version fallback to `payload_transform`** — an unsupported build must raise, or a porting bug becomes indistinguishable from a version mismatch. Only 12.10, 12.11 and 13.00–13.02 have transforms; 11.11 is permanently out of reach, including the canonical `039f3991…` capture.

`clean_packet_rate` is computed from bunch *headers* and never enters a payload, so it is blind to this layer — it sat at 99.98% while 100% of payloads were undecodable. Score property work with `PropertyStats.rep_layout_rate`, and position work against ground truth: killer and victim within weapon range at every `characterDeath`.

**Names — `libraries/valapi.py`, `valcatalog.py`.** `valapi` is a stdlib client for Riot's official API (`docs/valorant-api.md` is its reference); `valcatalog` reduces a `val-content-v1` response — or the `fetch-assets` manifest, which needs no key — to the only two joins a replay needs: map asset path → name, agent UUID → name. `vrfview/names.py` applies them and nothing else consumes them.

**Viewer — `libraries/vrfview/`.** `loader` converges a `.vrf` and a `vrf_to_json` JSON onto one `Replay` (tests assert the two produce equal models); `tracks` decodes positions and codenames out of the replication stream; `infer` derives everything the file does not state; `names` looks up what is external; `state.state_at(t)` recomputes a snapshot from scratch per frame (no accumulation, so seeking backwards is as correct as playing forward). The UI is CustomTkinter: `app` is the two-page router, `viewer` assembles the viewer page, `panels` draws the two mirrored team columns, `minimap` and `scene` are the two possible centre canvases, `controls` holds the timeline strip and the transport bar, `images`/`icons`/`theme`/`clock`/`layout` support them. `minimap`, `scene` and the strip are `tk.Canvas` inside CTk frames, because a themed widget owns its geometry and cannot be drawn into. The order is read → decode → infer → name, and it matters: `infer` cross-checks its team split against the codenames, and `names` needs them to name anybody. `model`, `infer`, `state` and `layout` import no tkinter *and no vrfnet* — `tracks` is the only module that bridges the two — and must stay runnable headlessly.

**Match list — `libraries/vrfhome/`.** `scan` describes a whole library of `.vrf` files from plain chunks only — map, date, duration, round count, player count, build — caching by `(path, mtime, size)`, and is headless: 4.3 s cold for 101 captures, 0.03 s warm, no Oodle and no display. `cards` is the CustomTkinter page over it. A file that fails to parse becomes a card carrying its error, never a silent omission. Two card facts are load-bearing: the `WIN`/`LOSS` badge the brief demands **cannot be built** (no local player, teams are A/B by inference) so every card shows `scan.RESULT_NOT_IN_FILE`; and `positions_available` is a membership test against `payload_transform.SUPPORTED_BRANCHES`, the decoder's own table, so the MINIMAP/SCHEMATIC chip cannot drift from what the decode will do. On the reference library that is 21 of 101 captures. `scan` must keep importing no tkinter — `tests/test_vrfhome.py` asserts it.

## Conventions that matter here

**Positions exist for supported builds, and nowhere else.** `vrfview/tracks.py` is the only bridge from `vrfnet` into the model: it decodes movement into `Replay.positions` (per-actor `Track`s, thinned to 10 Hz) and reads each pawn's agent codename off its archetype path. It is opt-in (`vrf-view.bat dump --positions`) because it needs Oodle and about four minutes on a full match, and it *never raises for want of positions* — an unsupported build, a missing DLL or a JSON dump all end as a sentence in `Replay.position_source`. So every consumer must handle both cases: `viewer._make_view` picks `MinimapView` when the replay has positions *and* the art cache holds a radar image, and `SceneView` otherwise, and the caption under the canvas says which is showing and why. Never let the schematic imply a minimap, and never let a missing track become a plausible coordinate — `MinimapView` draws nothing for an actor whose `Track.at` refused. The viewer decodes on a worker thread behind the DECODE POSITIONS button, never at load; after a decode it re-runs `names.resolve` and rebuilds the body, because the codenames that name the agents only exist once the stream has been read.

The one thing drawn at real map coordinates *without* positions is the **map reference window** (`vrfview/mapref.py`, the *Map* button): Riot's own callouts, from the `assets/manifest.json` transforms, via `vrfview/art.py`. It is safe because it describes the map and not the match — it is the same picture for every replay on Bind — and it is structurally unable to do otherwise, because `mapref.show` is handed no `Replay`. Keep it that way: positions belong in the scene, not smuggled in here.

**Art is a picture, never a claim.** `vrfview/art.py` is a second reader over `assets/manifest.json` — `valcatalog` takes names from it, `art` takes file paths, the transform and the callouts. Art resolution is deliberately not part of the model: it never touches `Replay`, has its own `ART CACHE` block in the provenance panel, and a missing or partial `assets/` costs thumbnails, portraits and the minimap image and changes nothing the viewer states (`--no-art` forces that path). Read every PNG path out of the manifest's `files` dict — never build one from a display name, or `KAY/O` breaks. Sizing is Pillow's since Phase 6: `images.ImageCache` resamples to any size and masks a portrait to a circle, and it hands a `PhotoImage` to a canvas but a `CTkImage` to a widget — the two are not interchangeable. `art.png_size`/`art.subsample_for` are gone; they only existed to pick an integer factor for Tk's `subsample`. Transport glyphs come from `scripts/make_icons.py` via `vrfview/icons.py`, which lists the names and the text each control falls back to when `assets/icons/` has not been generated.

**Names are looked up, never invented, and the lookup is offline by default.** Map and agent names are external knowledge, so they live in `vrfview/names.py` rather than `infer`, and they append to `Replay.catalog_notes` rather than `Replay.notes` — a looked-up fact and a derived one are different claims. The search order is `--catalog` → `assets/content-<locale>.json` → `assets/manifest.json` → the built-in table (`loader.MAP_NAMES` for maps, `names.AGENT_CODENAMES` for agents), and whichever answered is always reported. Only `vrf-view.bat catalog --refresh` opens a socket: no command needs `RIOT_API` to view or dump a replay.

There are three joins, and the third has a caveat: map asset path → name, agent UUID → name, and **codename → name** (`Hunter` → Sova) via `developerName`, which only valorant-api.com publishes, so only a `fetch-assets` manifest carries it. The **loadout roster is still not attributable to actor net IDs** — nothing links a loadout slot to an actor and nothing decoded since has changed that. What changed is that a player no longer needs the roster: its pawn states its own archetype, so `Player.codename` is *read* and `Player.agent` is *looked up*, while `Loadout.agent` still comes from a UUID. The two are never filled from each other; when both resolve, `names` notes that they agree. `val-match-v1` (player names, ranks, economy, positions) is 403 without a production key, so it is implemented and diagnosed but never depended on.

**Read vs. inferred is never blurred.** `loader` fills in only what the file states; `infer` derives teams (bipartite two-colouring of the kill graph), round outcomes, sides and reconnect merges, appends a line to `Replay.notes` for each derivation, and leaves an explicit unknown where it cannot decide. The UI surfaces those notes. Keep new derivations in `infer` and keep them noted.

**`characterDeath` args: `args[1]` is the killer, `args[2]` the victim.** The summary doc originally had this reversed; the symptom is not a crash but players dying twice in a round. `test_killer_victim_order_is_not_reversed` pins it.

**`clean_packet_rate` is the *bunch layer's* health metric.** Bit-level desync does not degrade gracefully, so anything below ~99% means a layout is wrong, not that the data is noisy. It doubles as the calibration score. It says nothing about anything inside a payload — see the replication-stream section above.

**Version gates are calibrated, not guessed.** The `EEngineNetworkVersionHistory` thresholds for `++Ares-Core+release-11.11` are not public, so `vrfnet/versions.Features` is a plain policy object and `vrfnet/calibrate.py` sweeps every candidate against real packets, scoring by how many bunch loops consume to exactly zero leftover bits. The answer is committed at `libraries/vrfnet/calibrated.json`. Never hard-code a gate; re-run `vrf-net.bat calibrate ... --save` with a few thousand packets (small samples report INCONCLUSIVE even when the winner is right).

**Oodle is never vendored.** `libraries/oodlefind.py` resolves `oo2core_*_win64.dll` in order: `--oodle-dll` → `VRF_OODLE_DLL` (real env, then nearest `.env` via `libraries/envfile.py`) → `vendor/` → cache → Steam/Epic library scan. The first two are configured deliberately, so a nonexistent path raises rather than falling through to a scan. Valorant itself cannot supply one (statically linked, exports no Oodle symbols).

**Two runtime dependencies, and a declined third.** The decoding pipeline (`vrf_reader`, `vrf_to_json`, `vrfnet`, `valapi`) is stdlib-only and stays that way; the desktop app adds `customtkinter` (the widget set the brief specifies) and `Pillow` (circular portraits and fractional scaling -- Tk's own `subsample` divides by whole numbers only). Dev group is pytest + ruff. `requirements.txt` mirrors `pyproject.toml` for pip installs. **`python-dotenv` was deliberately not adopted**: `envfile.py` already implements the same contract -- real environment first, nearest `.env` second, no `os.environ` mutation -- so `vrfconfig.py` calls it rather than putting two readers of one `.env` in one process. Add a dependency only when the standard library genuinely lacks the thing.

**Configuration is one key, and it reports where it came from.** `libraries/vrfconfig.py` resolves `DEMO_PATH` (the directory the match list scans) through `envfile`, defaulting to `Demos/`, and returns a `DemoRoot` carrying the provenance sentence alongside the path. A `DEMO_PATH` that does not exist resolves normally and reports `exists = False` -- an empty library is the match list's empty state, not a startup error.

**Positions travel beside a JSON dump, never inside it.** `vrf-to-json ... --positions` decodes tracks once, on the machine that has the Oodle DLL, and writes `<out>.positions.json` (`libraries/vrfview/positionfile.py`); `tracks.attach` reads that sidecar when it is handed a `.json`, so the JSON path stays DLL-free without weakening the test that asserts the two input paths build equal `Replay`s -- `loader.load` still reads only what the container states. A sidecar whose `match_id` disagrees with the replay's is refused with a sentence, because a track drawn for the wrong match looks entirely plausible.

## Tests

`unittest`-style classes run under pytest. Everything runs headlessly with no `.vrf`, no display and no network: `Demos/`, `out/` and `assets/` are gitignored, so tests needing the reference capture (`Demos/039f3991-5472-4119-bed2-838da0935f60.vrf`) are `skipUnless(...exists())`. Network and DLL-loading tests use small inline fixtures.

Ruff runs with nearly every rule family enabled (see `ruff.toml`); test files get a per-file exemption list. Expect lint feedback on error-message style, pathlib usage, boolean traps and complexity.

## Docs

`docs/vrf-decoding-findings.md` is measured truth about this capture and supersedes `docs/vrf-decoding-research.md`, which is a literature review that is **partly wrong for this title**. `docs/039f3991_summary.md` §8 lists what is not in the file and is the target backlog. Handoff docs (`*-handoff.md`) are point-in-time session summaries.
