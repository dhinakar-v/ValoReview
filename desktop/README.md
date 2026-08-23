# desktop/

ValoReview as a Windows application: one installer, one icon, no `uv`, no .NET
SDK and no checkout.

The shell is Tauri. It does almost nothing on purpose — the SPA, the API, the
art and the decoder are the existing project unchanged, and this starts them and
points a window at them.

```
desktop/
  splash/index.html      the startup window, hand-written and served by Tauri
  src-tauri/             the Rust shell, its config, its icons
  packaging/             how the Python sidecar and the app icon are made
  licences/              what ships beside the decoder (see "Licensing")
```

## What runs where

| Piece | Ships as | Started by |
|---|---|---|
| Python backend (`scripts/vrf_desktop.py`) | PyInstaller onedir, `backend/` | the shell, per launch |
| Position decoder (`csharp/VrfPositions`) | self-contained publish, `decoder/` | the backend, per capture |
| Web interface (`web/dist`) | static files, `web/` | served by the backend |
| Riot's art (~86 MB) | **not bundled** | downloaded on first run |

The window loads `http://127.0.0.1:<port>/` rather than bundling the SPA into
Tauri, and that is what makes the frontend need no change at all:
`web/src/api/client.ts` fetches same-origin relative paths with no base-URL
seam, and the server already mounts the built page and Riot's art and answers
`/replay/<id>` with `index.html`. Bundling would mean a configurable API base, a
CSP allowance for it, and reimplementing both mounts against a `tauri://`
origin. It also means the page the user looks at is a *remote* page named in no
capability, so it has no IPC surface. There is no `capabilities/` file at all:
Tauri v2 reaches a remote origin's IPC only where a capability names that URL
under `remote.urls`, nothing here does, and the shell uses no plugins, so there
is no permission to grant either. The three commands are the splash's alone.

Both payloads are `bundle.resources` rather than `bundle.externalBin`.
`externalBin` resolves single files with a target-triple suffix, and a
PyInstaller onedir tree and a `dotnet publish --self-contained` tree are both
directories. So they are spawned with `std::process::Command`, and
`tauri-plugin-shell` is not a dependency.

## What a fresh machine needs to run the installer

Almost nothing, and that is the point of the bundle: **no Python, no .NET, no
uv, no Node, no checkout, no Oodle DLL, no Visual C++ redistributable.** All of
those are either inside the installer or not on this app's path at all.

| Requirement | Why, and what happens without it |
|---|---|
| **Windows 10 (1803+) or 11, 64-bit** | The only build target. There is no x86 or ARM64 bundle. |
| **WebView2 Runtime** | The window *is* WebView2. Windows 11 ships it; most Windows 10 machines have it because Edge installs it. Where it is missing, the NSIS installer fetches it — `webviewInstallMode` is `downloadBootstrapper`, so **that one case needs internet during installation**. `embedBootstrapper` or `offlineInstaller` in `tauri.conf.json` removes even that, at 150 KB and ~130 MB of installer size respectively. |
| **~130 MB free disk for the install** | 44 MB frozen backend, 78 MB self-contained decoder, 1.6 MB web bundle. Installs per-user under `%LOCALAPPDATA%`, so **no administrator and no UAC prompt**. |
| **Internet on first launch, once** | The splash downloads Riot's maps, agents, roles and weapons (~86 MB) into `%LOCALAPPDATA%\com.valoreview.desktop\assets`. Refusing it is an ordinary state — the app runs and states everything it always states, without pictures — and every launch after that is fully offline. |
| **Room for the decode cache** | A decoded capture's sidecar is 10–15 MB and the prewarmer works through the whole library, so a hundred captures is one to one and a half gigabytes under `%LOCALAPPDATA%\com.valoreview.desktop\cache`. Deleting that directory costs time and nothing else. |
| **Valorant, to have produced the captures** | The app reads `%LOCALAPPDATA%\VALORANT\Saved\Demos` and asks nobody. An empty or absent folder is the match list's empty state, not an error, so the app installs and runs on a machine that has never had the game. |

What it does **not** need is worth being explicit about, because each one was a
prerequisite at some point in this project's life. Python 3.11 travels inside the
frozen backend (`python311.dll`, `VCRUNTIME140.dll`, `ucrtbase.dll` and the
api-ms-win stubs are all in `backend/_internal`). The .NET 10 runtime travels
inside the decoder (`dotnet publish --self-contained`, `includedFrameworks` in
its `runtimeconfig.json`). Oodle is not on the app's path at all — the decoder
decompresses for itself and the server never imports `oodlefind` — so the
`oo2core_*_win64.dll` a checkout hunts for is simply not part of this. And the
server binds loopback only, which on this machine raised no firewall prompt,
though that is unverified on a profile that has never run it.

Two things a fresh machine *will* show, both cosmetic and both expected: the
installer is unsigned, so SmartScreen says "Windows protected your PC" and the
user clicks *More info → Run anyway*; and a cold first launch reads every
capture in the folder before the window opens, which is why readiness allows
180 seconds and why the splash shows the backend's own lines while it waits.

## Building it

Needs everything a checkout needs, plus Rust with the **MSVC** toolchain
(`link.exe` — Visual Studio Build Tools with the C++ workload; `rustup` alone is
not enough) and the .NET 10 SDK. On a machine with nothing, that is:

| Tool | Version built with | Notes |
|---|---|---|
| Visual Studio 2022 Build Tools | VCTools + Windows SDK 10.0.26100 | Supplies `link.exe`. `cargo` did not find it unaided here; every build in this tree ran through `vcvars64.bat` first. **Let the installer finish before diagnosing a missing `.lib`** — a half-written install reports as a link error. |
| Rust | 1.98.0, `stable-x86_64-pc-windows-msvc` | `~\.cargo\bin` is not always on a fresh shell's PATH. |
| .NET SDK | 10.0.400 | Builds and publishes the vendored parser. |
| Node.js | 25.9.0 (20+ is enough) | The web bundle, and `npx tauri` — `tauri-cli` 2.11.4 installs into `desktop/node_modules`. |
| uv | 0.9.17 | Creates the venv and runs PyInstaller 6.22.2, which is in the dev group. |

NSIS is downloaded by `tauri build` itself. Playwright is needed only to
regenerate the icon, and `src-tauri/icons/` is committed, so a build does not
install it.

```
runners\publish-decoder.bat                 # -> vendor\parser\ (self-contained)
cd web && npm run build && cd ..            # -> web\dist
uv run pyinstaller desktop\packaging\vrf-desktop.spec --noconfirm ^
    --distpath desktop\packaging\dist --workpath desktop\packaging\build
cd desktop && npm install && npx tauri build
```

The installer lands in `src-tauri/target/release/bundle/nsis/`.

`npx tauri dev` runs the same shell against the same three resource trees, so
everything above except the last line still has to have been done first.

The app icon is rendered from `web/public/favicon.svg` by
`packaging/make-icon.mjs` (using the Chromium the e2e suite installs) and turned
into `src-tauri/icons/` by `npx tauri icon packaging/appicon.png`. The mark has
two committed drawings already, in `web/src/views/icons.tsx` and that SVG; a
third hand-drawn one is exactly what this avoids. The generated icons **are**
committed, so a build needs neither Playwright nor the icon step.

## First run

The shell owns it, not the SPA and not a new API route — and that is forced
rather than preferred. `build_settings` calls `art.load()` **once**,
`create_app` captures the resulting `ArtCache`, and `_mount_static` decides
there and then whether to serve pictures or install the 404 handler. Art that
lands after the server is up is never picked up, so the download has to finish
*before* the backend is spawned. A route could not arrange that for itself, and
`vrfserve`'s route list is deliberately closed anyway.

So: `valoreview-backend fetch-assets`, whose per-file lines the splash shows as
progress; then the backend, then the window. The download is idempotent and
resumable, and a refused one is an ordinary state — a missing `assets/` costs
pictures and changes nothing the interface states, which `--no-art` already
exercises.

**Nobody is asked where the captures are.** Valorant writes them to
`%LOCALAPPDATA%\VALORANT\Saved\Demos` and writes them nowhere else, so the
answer is a property of the game's installation rather than a question for a
person, and `main.rs:demo_dir` names that directory. There is no folder picker
and therefore no dialog crate; the splash has no buttons at all and starts on
its own. A `demo_path` in `%APPDATA%\com.valoreview.desktop\config.json` still
wins, which is the escape hatch for captures kept elsewhere, and nothing writes
that file. A directory that does not exist is not a startup error either:
`vrfconfig` resolves it and reports `exists = false`, and the match list draws
its empty state — which is the right thing to show somebody who has not recorded
a game yet.

## Three things that would break quietly

**Nothing may outlive the window.** The backend spawns `vrf-positions.exe` per
capture while it prewarms, so killing the direct child is not enough, and a
crash of the shell would orphan the whole branch. The backend is put in a
Windows **job object** with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so the kernel
tears the tree down when this process's last handle closes — including on a hard
kill. `ExitRequested` asks nicely first.

**No console may flash.** Two places, and only one of them is the shell's: the
backend gets `CREATE_NO_WINDOW` from Rust, and the decoder gets it from
`csharpdecode.run` in Python, because the shell cannot reach a grandchild's
creation flags and the prewarmer launches those back to back.

**The window is built from an `async` command, and that is a correctness
requirement rather than a style.** A synchronous `#[tauri::command]` runs on the
main thread, and `WebviewWindowBuilder::build` deadlocks there on Windows
([wry#583](https://github.com/tauri-apps/wry/issues/583)) — the failure is not an
error: the window appears, titled correctly, and never paints, so what a person
sees is a white client area and what a screenshot shows is a blank rectangle. It
shipped that way once and the first suspicion fell on the CSP, which was
innocent. `launch` is therefore `async fn`. The probe that separates the two
cases is loading the served page in the Chromium the e2e suite already installs:
if that page renders — it does — the fault is the shell's and not the SPA's.

## Licensing

`vrf-positions.exe` links OozSharp, whose `Kraken.cs` carries a GPLv3 header
under an MIT package file. Taking the stricter reading, it ships in **its own
folder** under GPLv3, with `licences/GPLv3.txt` and
`licences/DECODER-SOURCE-OFFER.txt` beside it; ValoReview itself stays
Apache-2.0, and the `subprocess`-over-argv boundary is the licence boundary. See
the "Distribution" section of `THIRD_PARTY.md`, which the installer also ships.

## Not signed

The installer is unsigned, so SmartScreen shows "Windows protected your PC" and
the user clicks *More info → Run anyway*. It does not block installation. An OV
certificate would remove the *unknown publisher* wording but not the reputation
warning; only EV clears it on day one. NSIS `installMode: currentUser` installs
under `%LOCALAPPDATA%` with no UAC prompt, which removes the other dialog.
Retrofitting a certificate later is a config change plus a CI secret.
