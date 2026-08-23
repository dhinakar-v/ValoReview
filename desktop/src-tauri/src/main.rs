// The desktop shell.
//
// It decides almost nothing, which is the point: the SPA, the API, the art and
// the decoder are all the existing project, unchanged, and this starts them and
// points a window at them. The one thing it owns is the answer to "where is the
// replay folder", because a packaged app has no checkout to default to.
//
// The window loads `http://127.0.0.1:<port>/` rather than bundling the SPA.
// `web/src/api/client.ts` fetches same-origin relative paths with no base-URL
// seam, and the server already mounts the built page and Riot's art and answers
// `/replay/<id>` with `index.html`; bundling the page into Tauri would mean a
// configurable API base, a CSP allowance for it, and reimplementing both mounts
// against the `tauri://` origin. So the frontend needs no change at all, and
// the served page -- being remote, and named in no capability -- has no IPC
// surface either.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar;

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder};

/// What the shell remembers between launches. One key today, and the file
/// exists because `vrfconfig` deliberately has no runtime setter: `DEMO_PATH`
/// is read from the environment or a `.env`, never written by the server, and
/// this keeps that true by passing `--demo-path` on every launch instead.
///
/// Nothing writes it any more -- the folder is `demo_dir` below -- and it is
/// read rather than deleted because it is the only way to point an install at
/// captures kept somewhere other than where the game puts them.
#[derive(Default, Deserialize)]
struct Config {
    demo_path: Option<String>,
}

/// What the splash page is told before it draws anything.
#[derive(Serialize)]
struct FirstLook {
    demo_path: String,
    art_present: bool,
}

struct Running(Mutex<Option<std::process::Child>>);

fn config_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| format!("no config directory: {e}"))?;
    fs::create_dir_all(&dir).map_err(|e| format!("could not create {}: {e}", dir.display()))?;
    Ok(dir.join("config.json"))
}

fn read_config(app: &AppHandle) -> Config {
    config_path(app)
        .ok()
        .and_then(|p| fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

/// Where the captures are.
///
/// Valorant writes them to `%LOCALAPPDATA%\VALORANT\Saved\Demos` and writes
/// them nowhere else, so there is nothing to ask a person and no picker: the
/// answer is a property of the game's installation rather than of this app.
/// A `demo_path` in `config.json` still wins where somebody keeps captures
/// elsewhere, and a folder that does not exist is not an error -- `vrfconfig`
/// resolves it, reports `exists = false`, and the match list draws its own
/// empty state, which is the right thing to show somebody who has not recorded
/// a game yet.
fn demo_dir(app: &AppHandle) -> Result<PathBuf, String> {
    if let Some(chosen) = read_config(app).demo_path {
        return Ok(PathBuf::from(chosen));
    }
    let base = app
        .path()
        .local_data_dir()
        .map_err(|e| format!("no local data directory: {e}"))?;
    Ok(base.join("VALORANT").join("Saved").join("Demos"))
}

/// The two writable directories, under the per-user app data dir.
///
/// This is where `vrfcache`'s docstring stops applying and says so: it argues
/// against `%LOCALAPPDATA%` because "the data belongs to a checkout, not a
/// machine", and an installed app has no checkout. `VRF_CACHE_ROOT` is the
/// branch added for exactly this, above the search rather than below it, so the
/// refusal a checkout relies on is untouched.
fn data_dirs(app: &AppHandle) -> Result<(PathBuf, PathBuf), String> {
    let base = app
        .path()
        .app_local_data_dir()
        .map_err(|e| format!("no data directory: {e}"))?;
    let cache = base.join("cache");
    let assets = base.join("assets");
    for dir in [&cache, &assets] {
        fs::create_dir_all(dir).map_err(|e| format!("could not create {}: {e}", dir.display()))?;
    }
    Ok((cache, assets))
}

fn resource(app: &AppHandle, relative: &str) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("no resource directory: {e}"))?;
    let path = dir.join(relative);
    if path.exists() {
        Ok(path)
    } else {
        Err(format!("this install is missing {relative}"))
    }
}

/// An art directory counts as present once it holds the manifest, which is the
/// file `art.load` actually reads. A half-finished download leaves pictures
/// without one, and that is correctly "no art" rather than "some art".
fn art_present(assets: &Path) -> bool {
    assets.join("manifest.json").is_file()
}

fn say(app: &AppHandle, line: &str) {
    let _ = app.emit("progress", line);
}

#[tauri::command]
fn first_look(app: AppHandle) -> Result<FirstLook, String> {
    let (_, assets) = data_dirs(&app)?;
    Ok(FirstLook {
        demo_path: demo_dir(&app)?.to_string_lossy().to_string(),
        art_present: art_present(&assets),
    })
}

/// Download Riot's art into the app data directory.
///
/// It has to finish before the backend is spawned, and that is forced rather
/// than preferred: `build_settings` calls `art.load()` once, `create_app`
/// captures the result, and `_mount_static` decides at startup whether to serve
/// pictures or install the 404 handler. Art that lands afterwards is not picked
/// up, so a route or an in-page download would need a restart anyway.
#[tauri::command]
fn fetch_art(app: AppHandle) -> Result<(), String> {
    let (_, assets) = data_dirs(&app)?;
    let exe = resource(&app, "backend/valoreview-backend.exe")?;
    let handle = app.clone();
    sidecar::fetch_assets(&exe, &assets, move |line| say(&handle, &line))
}

/// Start the backend, wait for it, and show the real window.
/// `async` is not a style choice. A synchronous command runs on the main
/// thread, and `WebviewWindowBuilder::build` deadlocks there on Windows
/// (wry#583) -- the window appears with the right title and never paints, so
/// the symptom is a white client area rather than an error. An `async` command
/// runs off the main thread, which is what the builder's own docs prescribe.
#[tauri::command]
async fn launch(app: AppHandle, running: State<'_, Running>) -> Result<(), String> {
    let demo_path = demo_dir(&app)?;
    let (cache_root, assets) = data_dirs(&app)?;
    let layout = sidecar::Layout {
        exe: resource(&app, "backend/valoreview-backend.exe")?,
        demo_path,
        assets,
        web_dir: resource(&app, "web")?,
        cache_root,
        parser_exe: resource(&app, "decoder/vrf-positions.exe")?,
    };

    let handle = app.clone();
    let backend = sidecar::start(&layout, move |line| say(&handle, &line))?;
    sidecar::kill_on_exit(&backend.child)?;
    let port = backend.port;
    *running.0.lock().unwrap() = Some(backend.child);

    let url = format!("http://127.0.0.1:{port}/")
        .parse()
        .map_err(|e| format!("bad url: {e}"))?;
    WebviewWindowBuilder::new(&app, "main", WebviewUrl::External(url))
        .title("ValoReview")
        .inner_size(1440.0, 900.0)
        .min_inner_size(900.0, 600.0)
        .center()
        .build()
        .map_err(|e| format!("could not open the window: {e}"))?;

    if let Some(splash) = app.get_webview_window("splash") {
        let _ = splash.close();
    }
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .manage(Running(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![first_look, fetch_art, launch])
        .build(tauri::generate_context!())
        .expect("could not start ValoReview")
        .run(|app, event| {
            // The job object already guarantees this on a hard kill; the
            // ordinary path asks first, so the backend gets to exit rather than
            // being torn down mid-write.
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(child) = app.state::<Running>().0.lock().unwrap().as_mut() {
                    let _ = child.kill();
                }
            }
        });
}
