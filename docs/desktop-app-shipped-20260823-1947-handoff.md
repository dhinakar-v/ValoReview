# The desktop app — vendored parser, sidecars, Tauri shell

23 August 2026 · branch `vd-develop` · `E:\Personal\ValoReview`

This session took the Tauri packaging plan from "Phase 1 done" to **an installer that builds,
installs and runs**. It also answered the previous session's blocking question by removing it:
the sibling parser clone is gone, vendored into this repository.

**One thing does not work and it is the last thing standing: the app window renders white.**
Everything behind it is verified good. See *Open questions* — that is where the next session
starts.

---

## Read these first

| # | Artifact | What it is / why it matters |
|---|---|---|
| 1 | `docs/tauri-packaging-20260823-1810-handoff.md` | The session before this one. Its Phase 1 is committed; its Phase 2 blocker is **resolved** (see *Decisions*), and its "uncommitted work from another session" warning is **stale** — the tree was clean at `d3a5078` when this session started. |
| 2 | `C:\Users\Dhina\.claude\plans\create-a-plan-for-dreamy-raven.md` | The approved five-phase plan. Still outside the repo, still not version-controlled. Phases 2–5 are now implemented; read it for the reasoning behind each choice rather than for status. |
| 3 | `desktop/README.md` | Written this session. The build order, what runs where, and the three things that would break quietly. Start here for anything about the app itself. |
| 4 | `csharp/parser/README.md` | Written this session. Provenance of the vendored parser and the four ways it differs from upstream. |
| 5 | `CLAUDE.md`, the new **Shell — `desktop/`** paragraph | The durable record of the packaging decisions, in the file that carries every other one. |

---

## State

### Everything is uncommitted

`git status --short` lists 22 entries and **all of them are this session's**. Unlike the previous
handoff, nothing here belongs to a concurrent session — the tree was clean at `d3a5078` when this
started. Committing is the next agent's first action.

Modified: `.gitignore`, `CLAUDE.md`, `README.md`, `THIRD_PARTY.md`, `pyproject.toml`, `uv.lock`,
`vendor/README.md`, `runners/build-decoder.bat`, `libraries/vrfview/csharpdecode.py`,
`csharp/VrfPositions/VrfPositions.csproj`, `csharp/TransformSearch/{README.md,TransformSearch.csproj}`,
`csharp/patches/{README.md,0001-payload-capture.patch}`. Deleted: `csharp/patches/0002-transform-13-04.patch`.
New: `csharp/parser/`, `desktop/`, `.github/workflows/`, `scripts/vrf_desktop.py`,
`runners/{publish-decoder,vrf-desktop}.bat`, `tests/test_vrf_desktop.py`.

`csharp/parser/` alone is **317 files**. `git add -A` is safe this time, but review the count so it
is not a surprise.

### Done and verified

- **The parser is vendored** at `csharp/parser/` (four projects, 312 source files, ~15k lines).
  `VrfPositions.csproj` references it directly; `$(VrpRoot)` is gone. Builds clean, 0 warnings.
- **Ground truth passes on the vendored decoder.** `tests/test_positions.py` with
  `VRF_CACHE_ROOT` pointed at an empty directory — so the 12.10 and 13.04 classes really decoded,
  they use `decode=True, cache=False` — 27 passed.
- **Ground truth passes on the *published* decoder too**, via `VRF_PARSER_EXE` pointed at
  `vendor/parser/vrf-positions.exe`. That is the plan's Phase 2 acceptance criterion.
- **Full suite green**: 551 passed, 9 skipped, 451 subtests. `ruff check` and `ruff format --check`
  clean. (`tests/test_prewarm.py`'s 12 failures from the last handoff are gone — that was the
  concurrent work, since committed.)
- **The backend freezes and runs outside a checkout.** 43.6 MB / 86 files. Run from a directory
  with no `pyproject.toml` above it, `/api/config` reports `demo_root.exists`, `decoder.found` and
  `web_built` all true, and the scan cache lands in `VRF_CACHE_ROOT`.
- **The installer builds**: `ValoReview_0.1.0_x64-setup.exe`, 43.5 MB, from 122.7 MB of resources
  (backend 43.6, decoder 77.5, web 1.5, licences 0.1). All four trees verified present in
  `target/release/`.
- **The app launches and the backend works.** Window titled ValoReview opens, backend binds a
  dynamic port, `/api/config` is all-true, `/api/library` returns 15 pages of 103 captures, and the
  prewarmer is decoding (a `vrf-positions` process was live).
- **The job object works.** `Stop-Process -Force` on the shell — a hard kill, the strongest case —
  left **no** `valoreview-backend` and no `vrf-positions` behind.
- **CI exists** where there was none: `.github/workflows/ci.yml` (python / web / decoder jobs) and
  `release.yml` (tag-triggered installer build). Neither has run; they are unverified.

### Broken

**The webview renders white.** Captured twice — `PrintWindow` and a real `CopyFromScreen` of the
composited desktop — both blank. The title bar and icon are correct. Everything the page needs is
served correctly over the same port at the same moment: `/` is 200/1554 bytes,
`/static/index-*.js` is 200/524762 bytes with `application/javascript`, the CSS and the favicon
likewise. So this is the webview or its configuration, not the server and not the bundle.

The probe that would have separated "page is broken" from "webview is broken" — loading the same
URL in Playwright's Chromium and reading its console — was interrupted before it ran. **Run it
first.**

### Untouched

Signing (deliberately: ship unsigned). A clean-VM install test — the plan's Phase 5 verification,
and the only real test of the packaging. Threading `Settings.parser_exe` into `prewarm.Prewarmer`,
which the plan notes as the real fix behind the env-var-and-flag workaround.

---

## Decisions made

**The parser is vendored, and that resolved the previous session's open question by removing it.**
The user's instruction was "create the application without valorantreplayparser, everything should
be in this repo". The previous handoff's blocker was that the sibling clone held 130 lines existing
nowhere else — a PUUID-stripping descriptor and two new economy descriptors — so a release built
from a clean clone plus the committed patches would have silently re-enabled account-identifier
decoding. Vendoring carries all of it into the tree, where a commit can see it. `csharp/patches/`
now holds one patch, not two.

**`0002-transform-13-04.patch` was deleted; `0001-payload-capture.patch` was rebased and kept.**
The 13.04 transform is a source file now, so a patch for it would be a second copy. The capture
tool is a passthrough transform that must never ship in a decoder, so it stays outside the source
tree; it was regenerated against the vendored tree (so it no longer conflicts on the registry hunk)
and applies with `git apply --directory=csharp/parser`. Verified with `--check`.

**Upstream's `Directory.Build.props` was not copied.** It sets `TreatWarningsAsErrors`, and
vendored third-party source should not fail this repository's build on a warning a future SDK
invents. The tree compiles with zero warnings as it stands.

**The vendored directory is `csharp/parser/`, not `csharp/vendor/`.** `.gitignore` has a bare
`vendor/*`, which matches at every depth — a `csharp/vendor/` would have been silently ignored.

**The window loads `http://127.0.0.1:<port>/`; the SPA is not bundled into Tauri.** Carried over
from the plan and still right: the frontend needed zero changes, and the page is a remote page
named in no capability, so it has no IPC surface.

**Both payloads are `bundle.resources`, spawned with `std::process::Command`.** `externalBin` takes
single files and both of these are directory trees. `tauri-plugin-shell` is not a dependency.

**The folder picker is the `rfd` crate, not `tauri-plugin-dialog`.** The only dialog this app opens
is opened from Rust, so a plugin would add an IPC surface and a capability grant for nothing.

**The app icon is rendered from `web/public/favicon.svg` by Playwright**
(`desktop/packaging/make-icon.mjs`), then expanded by `tauri icon`. The mark already has two
committed drawings and a hand-drawn third would drift. The generated `src-tauri/icons/` **are**
committed so a build needs neither Playwright nor the icon step; `packaging/appicon.png` is not.

**PyInstaller onedir, console subsystem.** Onedir because onefile re-extracts ~44 MB to `%TEMP%`
every launch. Console because the backend's startup lines are the only progress the splash has, and
`CREATE_NO_WINDOW` from Rust means nothing is shown anyway.

**`scripts/vrf_desktop.py` is an argv switch over `vrf_serve.main` and `fetch_assets.main`.** One
frozen executable, two entry points, no logic moved. `serve` is the default so running the exe by
hand does something sensible. `fetch-assets` always passes `fetch` and never `list`, which prints a
catalogue to a console a packaged app does not have.

**GPLv3 is settled in the bundle, not only on paper.** `desktop/licences/` holds `GPLv3.txt` and a
written offer of source naming this repository, the vendored parser's revision and the exact
`runners\publish-decoder.bat` command. `THIRD_PARTY.md` gained a **Distribution** section, and
`vendor/README.md`'s open warning now points at it instead of trailing off.

---

## What did not work

**`git apply` of the old `0001` onto the vendored tree.** Its registry hunk was written against
upstream's five-transform array and the vendored one has six. Regenerating the patch from a
three-file diff between the vendored tree and the clone's working tree was the fix.

**Heredocs containing Windows paths, through the Bash tool.** Backslash sequences (`runners\\build`)
arrive collapsed, so `assert old in s` fails on text that is visibly identical. Cost several
retries. Use the Write tool, or `re.search` an anchor and mutate the match, or `sed` by line
number. This will bite the next agent too.

**`cargo build` with `rustup` alone.** No linker: this machine had no Visual Studio at all. Then,
with Build Tools half-installed, `kernel32.lib` was missing; then `dbghelp.lib`; both because the
installer was still writing. **Wait for the install to finish before diagnosing a link error.**

**`windows-sys` features by intuition.** `CreateJobObjectW` needs `Win32_Security` (it takes a
`SECURITY_ATTRIBUTES*`, always null here) and `JOBOBJECT_EXTENDED_LIMIT_INFORMATION` needs
`Win32_System_Threading` (it embeds `IO_COUNTERS`). Neither is named in the code. Both are now
commented in `Cargo.toml`.

**Mapping a single file to a directory target in `bundle.resources`.** `"../../LICENSE": "licences/"`
failed the build with `Access is denied. (os error 5)`. Give single files an explicit target
filename: `"licences/LICENSE.txt"`.

**`PrintWindow` on a WebView2 window.** Returns white whether or not the page rendered, so it
cannot distinguish the two. `Graphics.CopyFromScreen` on the foreground window can — that is what
confirmed the white is real.

**`Invoke-WebRequest` without `-UseBasicParsing`** dies with "PowerShell is in NonInteractive mode"
on PS 5.1. `Invoke-RestMethod` is fine.

---

## Environment facts

- **Rust 1.98.0 / cargo 1.98.0**, installed this session via winget. `~\.cargo\bin` is **not** on
  this shell's PATH — prepend it.
- **MSVC Build Tools 2022** with the VCTools workload and Windows SDK 10.0.26100, installed this
  session. `cargo` still cannot find `link.exe` on its own here. Every Rust build in this session
  used:
  `cmd /c "call \"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat\" >nul && set PATH=%USERPROFILE%\.cargo\bin;%PATH% && cd /d ... && cargo build --release"`.
  vcvars prints `'vswhere.exe' is not recognized` every time and works anyway — ignore it.
- `tauri-cli` **2.11.4**, installed under `desktop/node_modules` (`npx tauri`). tauri crate 2.11.5.
- pyinstaller **6.22.2**, added to `pyproject.toml`'s dev group.
- Also present: dotnet 10.0.400, node v25.9.0, uv 0.9.17, python 3.11.14, WebView2 142.0.3595.65.
- Sizes: backend bundle 43.6 MB / 86 files; published decoder 77.5 MB / 203 files; installer 43.5 MB.
- Timings: decoder build ~4 s cold; PyInstaller freeze ~30 s; `cargo build --release` ~50 s warm,
  several minutes cold; full pytest ~85 s; `test_positions.py` with a cold cache ~65 s.
- The app's runtime state on this machine: config at `%APPDATA%\com.valoreview.desktop\config.json`
  (seeded with a `demo_path` this session), data at `%LOCALAPPDATA%\com.valoreview.desktop\`, whose
  `assets` is a **directory junction** to the repo's `assets/` so the 86 MB fetch was skipped.
- Finding the running app's port: `Get-NetTCPConnection -State Listen | Where-Object { $_.OwningProcess -in (Get-Process -Name valoreview-backend).Id }`.

---

## Open questions

**1. Why is the webview white?** The whole session's remaining work. Ranked suspects:

- **The CSP in `desktop/src-tauri/tauri.conf.json`.** `default-src 'self'` is the only thing
  configured that could break a page that otherwise serves perfectly. Tauri applies it to the
  webviews it creates; whether it reaches a webview on a remote origin was not established.
  **Cheapest test: delete `app.security.csp` entirely and rebuild.**
- The SPA failing at runtime inside WebView2 specifically (a WebGL or module issue Chromium would
  not show).
- The window being created before the page is reachable, and never retrying.

Cost of guessing wrong: rebuilding the shell is ~50 s, so guessing is cheap — but do the Playwright
probe first, because "the page is fine in Chromium" and "the page is broken everywhere" lead to
completely different investigations.

**2. Nothing in this repo names where Valorant writes `.vrf` captures.** Unchanged from the last
handoff. The first-run picker has no candidate directory to suggest. Needs a machine with the game.

**3. The NSIS *upgrade* path is unverified.** Install v1, install v2 over it, list what actually
landed — `bundle.resources` directory semantics on reinstall are reported as unreliable
(tauri#15134).

**4. Windows Firewall on a loopback-only bind.** Did not prompt on this machine, but this machine
has already run the server many times. Unverified on a clean profile.

---

## Next steps

1. **Commit.** Everything is this session's; use the `commit` skill. Consider two commits — the
   vendoring, then the desktop app — since they are separable stories.
2. **Diagnose the white window.** First command, with the app running (it prints its own port; find
   it with the `Get-NetTCPConnection` line above):

   ```bash
   node desktop/packaging/make-icon.mjs   # no — that is the icon; see below
   ```

   The actual probe, which was written but interrupted, loads the served page in the Chromium the
   e2e suite already installs and prints console errors, page errors and failed requests:

   ```js
   // node <scratch>/probe.mjs
   import { createRequire } from "node:module";
   const { chromium } = createRequire("E:/Personal/ValoReview/web/package.json")("@playwright/test");
   const page = await (await chromium.launch()).newPage();
   page.on("pageerror", (e) => console.log("pageerror:", e.message));
   page.on("console", (m) => m.type() === "error" && console.log("console:", m.text()));
   page.on("requestfailed", (r) => console.log("failed:", r.url()));
   await page.goto("http://127.0.0.1:<PORT>/", { waitUntil: "networkidle" });
   console.log((await page.innerText("body")).slice(0, 300));
   ```

   If Chromium renders it, the page is fine and the fault is Tauri's — drop the CSP and rebuild.
3. **Then re-verify the plan's Phase 4 list**: the match list draws, a playable capture draws
   markers on the radar, the 3D view renders, no console flashes during prewarm. The last two are
   already covered by the job-object and `CREATE_NO_WINDOW` work but have not been *seen*.
4. **Phase 5's real test**: install on a clean VM with no dotnet, no Python, no uv, and walk first
   run end to end — folder picker, art fetch, match list, a decoded capture. That is the only
   machine that does not already have what the checkout assumes.

---

## Cautions

- **Do not delete or revert `E:\Personal\ValorantReplayParser`.** Its working tree is still the
  only place some of that history lives, and nothing here reads it any more. Leave it alone.
- **Do not apply `csharp/patches/0001-payload-capture.patch` in a release build.** It is a
  derivation instrument; its passthrough transform must never ship. Apply, capture, revert.
- **Do not enable `PublishTrimmed`** on the decoder publish without running `tests/test_positions.py`
  against the result. The parser reflects over its descriptor catalogue.
- **Do not "fix" the vendored parser by re-copying from upstream** without re-applying the four
  changes `csharp/parser/README.md` lists — one of them is the decision not to decode a player UUID.
- The plan file still lives outside the repo and is not version-controlled. If it should survive,
  copy it into `docs/`.
- `%LOCALAPPDATA%\com.valoreview.desktop\assets` is a **junction into the repo's `assets/`**.
  Deleting it recursively from the app-data side would delete the repo's art. Remove the link, not
  the contents.

---

## Suggested skills

- **`commit`** — first, before anything else. 22 entries, all this session's, and two clean stories
  in them. The skill's conventional-commit discipline is what keeps the vendoring legible in the
  log a year from now.
- **`code-review`** — after the white-window fix lands. `desktop/src-tauri/src/` is ~450 lines of
  new Rust that no test touches, and its failure modes (an orphaned process tree, a console flash,
  a readiness poll that gives up early) are all invisible in a screenshot.
- **`handoff`** — again at the end of the next session if the clean-VM test has not happened yet.

Not useful here: `init` (`CLAUDE.md` is thorough and was updated this session), `web-design-guidelines`
and `high-end-visual-design` (the frontend is deliberately unchanged — that is the architecture's
whole point), `dataviz` (nothing charted).

---

## Sensitive material

- `csharp/parser/src/Replay.Valorant/GameState/BombPlayerStateDescriptor.cs` is the file that
  **stops** player UUIDs, competitive tiers and unique IDs being decoded. No identifier values were
  seen or recorded this session. Treat any capture-derived PUUID as do-not-copy, and do not "restore"
  those fields to match upstream.
- `.env` in the repo root may hold `DEMO_PATH`, `VRF_OODLE_DLL` and `VRF_PARSER_EXE`. Read them
  through `envfile.get` at runtime; never quote them into a document.
- `vendor/oo2core_*_win64.dll` is Epic IP and is never redistributed or committed. It is not on the
  desktop app's path at all — the server never imports `oodlefind`.
