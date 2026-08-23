# Tauri Windows packaging — session handoff

23 August 2026 · branch `vd-develop` · `E:\Personal\ValoReview`

The session answered "can this Python + C# + React local web app become a Tauri Windows app?"
(yes), produced a five-phase plan, and **implemented and verified Phase 1** — the Python-side
seams that let the server run outside a checkout. Phases 2–5 are unstarted.

---

## Read these first

| # | Artifact | What it is / why it matters |
|---|---|---|
| 1 | `C:\Users\Dhina\.claude\plans\create-a-plan-for-dreamy-raven.md` | **The plan.** Five phases, decisions table, per-phase verification. Approved by the user. Lives outside the repo — see *Cautions*. |
| 2 | `THIRD_PARTY.md`, the OozSharp section | The GPLv3/MIT conflict in `vrf-positions.exe`. States outright that nobody should ship that binary without settling it. The decision taken is in *Decisions* below. |
| 3 | `csharp/patches/README.md` | The manual `git apply` contract against the sibling parser clone. Phase 2 is entirely about the gap between what this file claims and what is actually on disk. |
| 4 | `CLAUDE.md`, "Conventions that matter here" | Why `vrfcache` refuses rather than falling back, why `vrfserve` decides nothing, why the route list is closed. Every Phase 1 change was shaped to not violate these. |
| 5 | `<scratchpad>/uncaptured-clone-changes.diff` | The 130 lines living only in the sibling clone's working tree. Session-scoped temp file — regenerate with the command in *Next steps* if gone. |

Not required reading: `docs/payload-lanes-1304-*-handoff.md` and the two other 13.04 handoffs
from earlier today. Different subject; this session did not touch the transform work.

---

## State

### Done and verified — Phase 1

All four changes are **new branches on existing seams**. None alters checkout behaviour, which
is what kept the suite green.

- `libraries/vrfcache.py` — `VRF_CACHE_ROOT`, read via `envfile.get`. Names the cache directory
  itself, not a project root to append `.cache/` to. New `root_or_none()`; `vrfhome/scan.py`
  and `csharpdecode._scratch_for` rerouted onto it from `project_root()`.
- `scripts/vrf_serve.py` — `--web-dir` flag, applied only when passed.
- `libraries/vrfview/art.py` — `FETCH_HINT` constant → `fetch_hint()` function, overridable by
  `VRF_FETCH_HINT`. One call site updated in `libraries/vrfserve/app.py`.
- `libraries/vrfview/csharpdecode.py` — `creationflags=_quiet_flags()` (`CREATE_NO_WINDOW` on
  Windows, `0` elsewhere; `subprocess` rejects non-zero off Windows).

Tests added: `tests/test_vrfcache.py` (a `WhenAnInstallerNamesTheRoot` class, plus a
`_unset_configured_root` guard so a developer with the variable exported does not see the
search tests fail for an unrelated reason) and one case in `tests/test_csharpdecode.py`.

Verified by running the resolution with and without the variable — all five consumers
(positions, scan cache, decoder scratch, oodle cache, art hint) move together, asking creates
nothing, and the unset case still resolves to `E:\Personal\ValoReview\.cache`. `--web-dir`
confirmed to reach `Settings.web_built`. `ruff check` clean.

### Untouched

Phases 2–5: the decoder pin, the PyInstaller/dotnet-publish sidecars, the Rust shell, the
installer, CI, and the licence paperwork.

### ⚠ Uncommitted work, and it is not all this session's

`git status --short` lists ~50 modified files. **Only eight are from this session:**

```
libraries/vrfcache.py  libraries/vrfview/art.py  libraries/vrfview/csharpdecode.py
scripts/vrf_serve.py   tests/test_vrfcache.py    tests/test_csharpdecode.py
libraries/vrfhome/scan.py     (~6 of its 131 changed lines)
libraries/vrfserve/app.py     (1 line: art_mod.FETCH_HINT -> art_mod.fetch_hint())
```

Everything else — `vrfserve/wire.py`, `schema.py`, `vrfhome/prewarm.py`, the new untracked
`libraries/vrfhome/teamorder.py`, and roughly twenty `web/src/` files including new
`views/skeleton.tsx` — is **concurrent in-flight work from another session**. Several files
changed on disk *during* this session. Do not assume a clean baseline and do not commit
wholesale.

There are also untracked scratch files in `web/`: `.jump.mjs`, `.m.mjs`, `.m2.mjs`, `.m3.mjs`,
`.probe.mjs`, `.shots.mjs`. Not this session's; leave them.

### Failing tests that are not this session's

`tests/test_prewarm.py` — 12 failures, all `AttributeError: 'FakeCard' object has no attribute
'agent_ids'` at `prewarm.py:130`. `agent_ids` does not exist in `HEAD`; it is part of the
concurrent work above. Everything else passes (501 passed, 9 skipped).

---

## Decisions made

**The Tauri window loads `http://127.0.0.1:<port>/` — the SPA is *not* bundled into the Tauri
app.** The Python server keeps serving it. This is the whole reason the frontend needs zero
changes: `web/src/api/client.ts` uses relative same-origin `fetch` with no base-URL seam, and
`/assets` plus the `/replay/<id>` SPA fallback keep working as they are. Bundling the SPA into
Tauri would mean a configurable API base, a CSP `connect-src`, and reimplementing both mounts.

**Both payloads ship via `bundle.resources`, not `bundle.externalBin`.** `externalBin` takes
single files; PyInstaller onedir and `dotnet publish --self-contained` are both directory
trees. Consequence: spawn from Rust with `std::process::Command`, and `tauri-plugin-shell` is
not used at all — which also means the main window can be left out of every capability and so
gets no IPC surface.

**Riot art (86 MB) is fetched on first launch, not bundled** — the repo deliberately does not
redistribute it, and `scripts/fetch_assets.py` is already idempotent and resumable. The fetch
must complete **before the sidecar is spawned**: `build_settings` calls `art_mod.load()` once,
`create_app` captures the `ArtCache`, and `_mount_static` decides at startup whether to mount
`StaticFiles` or install the 404 handler. Art appearing later is never picked up.

**.NET ships self-contained**, untrimmed. The parser reflects over descriptor types; trimming
is exactly the failure that shows up on one capture in twenty.

**Cache goes to a per-install app-data dir via `VRF_CACHE_ROOT`.** `vrfcache`'s docstring
argues against `%LOCALAPPDATA%` on the grounds that "the data belongs to a checkout, not a
machine" — that argument does not reach an installed app, which has no checkout. The refusal
is kept for the case it was written for.

**The decoder is wired by env var *and* flag, from one resolved path.** `prewarm.py:215` calls
`tracks.attach(replay, path, Options(progress=progress))` with no `parser_exe`, so
`--parser-exe` alone never reaches the background prewarmer — it would fall through to
`_from_vendor()`/`_from_build()`, both gated on `find_upwards("vendor")`, which finds nothing
in an install directory. Every capture would fail to prepare while the DECODE button worked.
So set `VRF_PARSER_EXE` for reach and `--parser-exe` for the loud error on a wrong path.

**`vrf-positions.exe` will be conveyed under GPLv3 at the process boundary.** It ships in its
own resource folder with GPLv3 text and a written offer of source; ValoReview stays Apache-2.0;
the `subprocess`-over-argv boundary is the licence boundary. User chose this over shipping a
decoder-less installer.

**Ship unsigned.** Azure Trusted Signing is US/Canada-only for individuals and needs three
years of verifiable org history; OV is reputation-based and does not clear SmartScreen on day
one; only EV (~$325–600/yr plus a token) gives an immediate bypass. NSIS `installMode:
currentUser` installs to `%LOCALAPPDATA%` with no UAC prompt, removing one of the two dialogs.
Retrofitting later is a config change plus a CI secret, not a redesign.

---

## What did not work / was ruled out

**Reverting the sibling clone's uncaptured changes.** The plan originally said "if inert,
revert." That was wrong and reading the diff proved it — see *Open questions*.

**Having uvicorn take `--port 0` and parsing its chosen port back.** It couples the shell to
uvicorn's log format, and `vrf_serve.main` prints its own `serving http://host:port/` line
from the *pre-bind* args, so the two would disagree. Shell picks a free port and passes
`--port` instead, with a 3-attempt retry for the bind race.

**A 30-second readiness timeout.** `create_app` runs `library.rescan()` synchronously *before*
`uvicorn.run()`, so the port does not open until the whole library is scanned, and on first
launch the cache is always cold. Use 180 s and stream the sidecar's stdout to the splash.

**A `POST /api/assets/fetch` route, or an SPA first-run page.** Both need a server restart
anyway because of the one-shot art resolution above, and a route would violate the closed
route list and `vrfserve`'s "decides nothing" rule.

**PyInstaller `--onefile`.** Self-extracts ~60 MB to `%TEMP%` on every launch and attracts AV
heuristics. Onedir.

**`STARTUPINFO.wShowWindow = SW_HIDE` for the decoder console**, and making `vrf-positions` a
`WinExe`. The first allocates a console then hides it — still flashes. The second kills the
CLI's one-sentence-on-stderr contract that `tracks.attach` turns into `position_source`.

**"Improving" `uvicorn.run(app, ...)` into the `"module:app"` string form.** The string form is
the single most common PyInstaller/uvicorn failure — uvicorn re-imports by name in a frozen
process and cannot find the module. The current object form is correct. Leave it.

---

## Environment facts

- **Rust is not installed.** `cargo` and `rustc` both absent. Phase 4 is blocked on this.
- Present: `dotnet 10.0.400`, `node v25.9.0`, `npm 11.13.0`, `uv 0.9.17`, `python 3.11.14`,
  WebView2 `142.0.3595.65`.
- The parser clone is at `E:\Personal\ValorantReplayParser`, `origin` =
  `github.com/michel-giehl/ValorantReplayParser`, on `main` at `99d9646` ("feat: Add harbor
  ultimate", 2026-08-01). Matches the csproj's `$(VrpRoot)` default of `../../../`.
- `git diff` on that clone warns `CRLF will be replaced by LF` on every file. Patch
  application on a CI runner will hit this; use `git apply --3way`.
- The decoder build output is framework-dependent and 1.1 MB
  (`csharp/VrfPositions/bin/Release/net10.0/`), containing both `vrf-positions.dll` and an
  apphost `vrf-positions.exe`. `csharpdecode.BUILT` points at the `.dll` and prepends `dotnet`.
- `.venv/Lib/site-packages` is 44 MB total; ~30 MB excluding dev tools, of which `PIL` is 16 MB
  and `pydantic_core` 5.4 MB. Estimated onedir bundle 45–70 MB.
- `assets/` is 86 MB / 304 files. `web/dist` is 1.6 MB.
- `/api/config` is the right readiness probe — cheapest route, no path params, and a 200 proves
  the scan finished, art resolved and the decoder was located.
- `scripts/fetch_assets.py` already prints `  [ 12/1204] get  maps/Ascent/minimap.png` per file
  to **stderr**, so a determinate progress bar is a regex with no Python change.
- `csharpdecode.py` holds the **only** `subprocess` call in the Python tree.
- The server path never imports `oodlefind` — only the `vrf_reader`/`vrf_to_json` CLIs do. The
  desktop app therefore has no Oodle dependency and nothing unshippable.
- Test commands: `runners\test.bat`, `runners\lint.bat`, `cd web && npm test`. Full Python
  suite is ~54 s.

---

## Open questions

**1. The sibling clone holds 130 lines that exist nowhere else, and they are load-bearing.**
Six files are locally modified; `csharp/patches/` covers only two of them. The four uncovered:

- `GameState/BombPlayerStateDescriptor.cs` — **deletes** `Subject` (a player UUID),
  `CompetitiveTier` and `UniqueId`, with a docstring saying this parser "feeds a local review
  tool that has no business writing an account identifier into a cache file or a web response."
- `GameState/AresPlayerRoundInfoDescriptor.cs` (new) and
  `GameState/OwnerExclusivePlayerInfoDescriptor.cs` (new) — decode **real per-round credits and
  loadout value**, measured, with the reasoning written into the docstrings. This is what
  `web/src/model/synthetic.ts` currently generates.
- `Descriptors/ValorantDescriptors.cs` — registers those plus three armour-item descriptors.

A release built from a clean clone plus the two committed patches would silently **re-enable
player-UUID decoding** and **drop the economy work**. Cost of guessing wrong: a privacy
decision reversed by a build, with nothing saying so.

The user was asked whether to capture these as patches now or whether the work is still
moving, and **has not answered**. Do not snapshot mid-edit without asking again.

**2. Nothing in this repo names where Valorant writes `.vrf` captures.** The first-run folder
picker has no candidate list to probe. Needs confirming on a machine with the game installed.

**3. `bundle.resources` directory semantics and the NSIS *upgrade* path.** The array form with
a trailing slash is documented to copy recursively, but tauri#15134 reports reinstalls not
replacing `externalBin`. Verify by installing v1, installing v2 over it, and listing what
actually landed.

**4. Windows Firewall on a loopback-only bind.** Believed not to prompt; unverified on a clean
install with a default profile. If it does prompt, first-run gets much worse and an
install-time rule would need `perMachine` + UAC, which changes the signing calculus.

---

## Next steps

The user's last unanswered questions gate Phase 2 and Phase 4, so **start with Phase 3**, which
needs neither Rust nor a decision about the clone.

1. Ask the two open questions again (clone patches; Rust toolchain).
2. Write `scripts/vrf_desktop.py` — an argv dispatcher with `serve` and `fetch-assets`
   subcommands over `vrf_serve.main` and `fetch_assets.main`. This is the cheapest way to get
   two entry points out of one PyInstaller tree, and moves no logic.
3. Write `desktop/packaging/vrf-desktop.spec`. Two things are essential and easy to miss:
   `pathex` must include `libraries/` (it is a *source root*, not a package — `pyproject.toml`
   maps it onto the install root), and `excludes` must list `tkinter` or Pillow's hook drags
   ~10 MB of Tcl/Tk into a project that renders no widgets.
4. Freeze, then run the smoke check from the plan's Phase 3 verification: launch the frozen exe
   from a directory with no `pyproject.toml` above it and assert `/api/config` reports
   `demo_root.exists`, `decoder.found` and `web_built` all true.

First command to regenerate the clone evidence if the scratchpad file is gone:

```bash
cd /e/Personal/ValorantReplayParser && git status --porcelain && git diff -- src/Replay.Valorant/
```

---

## Cautions

- **The plan file lives outside the repo** (`~/.claude/plans/`) and is not version-controlled.
  If it needs to survive, copy it into `docs/` — this handoff deliberately does not duplicate
  its phase-by-phase detail.
- **Do not `git add -A`.** Most of the working tree is another session's in-flight work.
  Commit only the eight files listed under *State*, and note that two of them (`scan.py`,
  `app.py`) contain other people's lines as well — those two need a hunk-level commit.
- **Do not revert anything in `E:\Personal\ValorantReplayParser`.** It is a different repo and
  its working tree is the only copy of the descriptor work.
- **Do not "fix" `tests/test_prewarm.py`.** Its 12 failures belong to the concurrent work.
- Do not enable `PublishTrimmed` on the C# publish without a real decode test in CI.
- Do not apply `csharp/patches/0001-payload-capture.patch` in a release build — it is a
  derivation tool, it conflicts with `0002` on the transform registry, and its passthrough
  transform must never ship.

---

## Suggested skills

- **`commit`** — first, before anything else. There is uncommitted verified work and it is
  tangled with another session's; the skill's conventional-commit discipline plus a
  hunk-level review is exactly what this tree needs. Scope it to the eight files above.
- **`code-review`** — after the Phase 3 bundle exists. The PyInstaller spec and the dispatcher
  will be new, lightly-tested code whose failure mode (a missing hidden import) only appears
  in a frozen process.
- **`handoff`** — again at the end of the next session; this work spans more phases than one
  context will hold.

Not useful here: `init` (there is a thorough `CLAUDE.md`), `web-design-guidelines` and
`high-end-visual-design` (no UI work — the entire point of the chosen architecture is that the
frontend does not change), and `dataviz` (nothing being charted).

---

## Sensitive material

- The `BombPlayerStateDescriptor.cs` discussion concerns **player UUIDs (PUUIDs)** and
  competitive tiers. No actual identifier values were seen or recorded this session, and none
  appear in this document. Treat any capture-derived PUUID as do-not-copy.
- `.env` in the repo root may hold `DEMO_PATH`, `VRF_OODLE_DLL` and `VRF_PARSER_EXE` values.
  Read them through `envfile.get` at runtime; never quote them into a document.
- The Oodle DLL (`vendor/oo2core_*_win64.dll`) is Epic IP and must never be redistributed or
  committed. It is not on the desktop app's path at all.
