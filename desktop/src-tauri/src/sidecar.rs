//! Starting the Python backend, and making sure it dies with us.
//!
//! Everything here is about a child process that is not the end of the tree:
//! the backend spawns `vrf-positions.exe` per capture while it prewarms, so a
//! shell that kills only its direct child leaves decoders running, and a shell
//! that is itself killed leaves the whole branch orphaned.

use std::io::{BufRead, BufReader};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// Windows' "do not give this child a console". The backend is a console
/// subsystem binary -- it has to be, because its startup lines are the only
/// progress there is -- so without this every launch flashes a black window.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// How long the port may take to open.
///
/// Not thirty seconds: `create_app` runs the whole library rescan
/// *synchronously* before `uvicorn.run`, so nothing is listening until every
/// capture in the folder has been read, and on a first launch that cache is
/// always cold.
const READY_TIMEOUT: Duration = Duration::from_secs(180);
const POLL_EVERY: Duration = Duration::from_millis(250);

/// Ask the OS for a free port by binding one and letting go.
///
/// The alternative -- `uvicorn --port 0` and reading the chosen port back out
/// of its log -- couples this to a log format, and `vrf_serve` prints its own
/// `serving http://host:port/` line from the *pre-bind* arguments, so the two
/// would disagree about the answer. There is a race between the drop and the
/// backend's bind; `start` retries.
pub fn free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

/// Where every path the backend needs has been resolved to.
pub struct Layout {
    pub exe: PathBuf,
    pub demo_path: PathBuf,
    pub assets: PathBuf,
    pub web_dir: PathBuf,
    pub cache_root: PathBuf,
    pub parser_exe: PathBuf,
}

impl Layout {
    fn command(&self, port: u16) -> Command {
        let mut command = Command::new(&self.exe);
        command
            .arg("serve")
            .arg("--port")
            .arg(port.to_string())
            .arg("--demo-path")
            .arg(&self.demo_path)
            .arg("--assets")
            .arg(&self.assets)
            .arg("--web-dir")
            .arg(&self.web_dir)
            // Both, from one value, and that is deliberate. `--parser-exe`
            // reaches only the on-demand decode route; the background
            // prewarmer calls `tracks.attach` without it and would fall
            // through to a `vendor/` search that finds nothing in an install
            // directory. The environment variable is what reaches the
            // prewarmer, and the flag is what turns a wrong path into a loud
            // error instead of a silent fallthrough.
            .arg("--parser-exe")
            .arg(&self.parser_exe)
            .env("VRF_PARSER_EXE", &self.parser_exe)
            .env("VRF_CACHE_ROOT", &self.cache_root)
            // `art.fetch_hint()` is printed in /api/config and in every 404
            // from the no-art route. Its default names a .bat file in a
            // checkout, which a packaged user does not have.
            .env(
                "VRF_FETCH_HINT",
                "reinstalling downloads the pictures again",
            )
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW);
        command
    }
}

/// A running backend, and the port it was told to listen on.
pub struct Backend {
    pub child: Child,
    pub port: u16,
}

/// Start the backend and wait until `/api/config` answers.
///
/// `on_line` receives every line the child writes to stdout, which is what the
/// splash turns into progress: the backend prints `replays`, `art`, `decoder`
/// and `serving` before it binds, so a long cold scan reads as work rather
/// than as a hang.
pub fn start(
    layout: &Layout,
    on_line: impl Fn(String) + Send + Sync + 'static,
) -> Result<Backend, String> {
    if !layout.exe.is_file() {
        return Err(format!("the backend is missing at {}", layout.exe.display()));
    }

    let on_line = Arc::new(on_line);
    // Three attempts, because the port was free when we asked for it and
    // something else on the machine may have taken it in between.
    let mut last = String::new();
    for _ in 0..3 {
        let port = free_port().map_err(|e| format!("no free port: {e}"))?;
        let mut child = layout
            .command(port)
            .spawn()
            .map_err(|e| format!("could not start the backend: {e}"))?;

        if let Some(stdout) = child.stdout.take() {
            let on_line = on_line.clone();
            std::thread::spawn(move || {
                for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                    on_line(line);
                }
            });
        }
        // stderr is drained into a buffer rather than dropped: a backend that
        // exits immediately says why there, and a pipe nobody reads eventually
        // fills and blocks the writer.
        let errors = Arc::new(Mutex::new(String::new()));
        if let Some(stderr) = child.stderr.take() {
            let errors = errors.clone();
            std::thread::spawn(move || {
                for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                    let mut held = errors.lock().unwrap();
                    held.push_str(&line);
                    held.push('\n');
                }
            });
        }

        match wait_ready(&mut child, port) {
            Ok(()) => return Ok(Backend { child, port }),
            Err(reason) => {
                let _ = child.kill();
                let tail = errors.lock().unwrap().clone();
                last = if tail.trim().is_empty() {
                    reason
                } else {
                    format!("{reason}\n{}", tail.trim())
                };
            }
        }
    }
    Err(last)
}

fn wait_ready(child: &mut Child, port: u16) -> Result<(), String> {
    let url = format!("http://127.0.0.1:{port}/api/config");
    let deadline = Instant::now() + READY_TIMEOUT;
    while Instant::now() < deadline {
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!(
                "the backend exited with {status} before it listened"
            ));
        }
        // A 200 from /api/config proves rather more than that the socket is
        // open: the library has been scanned, the art resolved and the decoder
        // located, because all three happen before the bind.
        if ureq::get(&url).timeout(Duration::from_secs(2)).call().is_ok() {
            return Ok(());
        }
        std::thread::sleep(POLL_EVERY);
    }
    Err(format!(
        "nothing answered on port {port} within three minutes"
    ))
}

/// Run the one-shot art download, streaming its progress.
///
/// `fetch_assets` prints one line per file to **stderr**, so the progress bar
/// is a read of lines the script already writes and needs no change on the
/// Python side. It is idempotent and resumable, so an interrupted run costs
/// the next launch nothing but the files it did not reach.
pub fn fetch_assets(exe: &Path, out: &Path, mut on_line: impl FnMut(String)) -> Result<(), String> {
    let mut command = Command::new(exe);
    command
        .arg("fetch-assets")
        .arg("--out")
        .arg(out)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    let mut child = command
        .spawn()
        .map_err(|e| format!("could not start the art download: {e}"))?;
    if let Some(stderr) = child.stderr.take() {
        for line in BufReader::new(stderr).lines().map_while(Result::ok) {
            on_line(line);
        }
    }
    let status = child
        .wait()
        .map_err(|e| format!("the art download did not finish: {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("the art download exited with {status}"))
    }
}

/// Tie a process tree's lifetime to this one's.
///
/// The backend's own children are the decoders, so killing the backend is not
/// enough, and killing *this* process would leave everything below it running.
/// A job object with `KILL_ON_JOB_CLOSE` makes the kernel do it: when the last
/// handle to the job closes -- including when this process is terminated
/// outright -- every process in the job is terminated with it.
#[cfg(windows)]
pub fn kill_on_exit(child: &Child) -> Result<(), String> {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    // The job handle is deliberately never closed: the job has to outlive this
    // call and die with the process, which is exactly what leaking it does.
    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return Err("could not create the job object".into());
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        let size = std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32;
        if SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            std::ptr::addr_of!(info).cast(),
            size,
        ) == 0
        {
            return Err("could not configure the job object".into());
        }
        if AssignProcessToJobObject(job, child.as_raw_handle() as _) == 0 {
            return Err("could not put the backend in the job object".into());
        }
    }
    Ok(())
}

#[cfg(not(windows))]
pub fn kill_on_exit(_child: &Child) -> Result<(), String> {
    Ok(())
}
