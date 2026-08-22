"""
The one decoder: run `csharp/VrfPositions` and read what it wrote.

Why this replaced a pure-Python decode
--------------------------------------
A Python port of the same net stack decoded this stream *correctly* -- the two agreed on
every one of 10,544 compared samples, to the last bit of yaw and pitch -- but it
takes about four minutes on a full match, because `bitreader` is backed by a
Python int and the movement loop runs three million times.  The same work in C#
takes four seconds.  Nothing about the format changed; only the language did.

What this module is not
-----------------------
It is not a port of the decompressor.  `OozSharpOodleDecompressor` is a wrapper
over OozSharp, which is a partial Mermaid decoder and slower than the native
`oo2core` this project used to bind; decompression was never the cost.  It is
about one second of the four minutes, and the emitter that replaced them both
still runs it -- in C#, where it is free enough not to matter.

Why a subprocess and a file
---------------------------
Because the alternative is worse.  ValorantReplayParser's own `CliReader export`
would work, but it has no category flag: a full match is 5.3 GB of NDJSON, of
which this module needs 15 MB.  `csharp/VrfPositions` references the same
libraries and writes only the facts `tracks` consumes.

What comes back is facts, never readings.  Which actor is a player, which spawn
is an ability, how casts group: all of that stays in `tracks` and `abilities`,
where the tests are, and none of it crossed the process boundary.  That is the
same rule the sidecar follows, for the same reason -- the readings have already
changed once.

Imports nothing that needs a display, so it stays headless.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import envfile
import vrfcache
from vrfview.model import POSITION_HZ, Position

# An argument beats the environment, which beats a published drop-in, which
# beats whatever the repository happens to have built.  Same order, and the
# same reasoning, as libraries/oodlefind.py.
ENV_VAR = "VRF_PARSER_EXE"
VENDOR_DIRNAME = "vendor"
VENDOR_SUBDIR = "parser"
EXE_NAME = "vrf-positions.exe"
DLL_NAME = "vrf-positions.dll"
BUILT = Path("csharp") / "VrfPositions" / "bin" / "Release" / "net10.0" / DLL_NAME

FORMAT = "vrf-csharp-decode"
READABLE = (1,)

NOT_FOUND = (
    "the position decoder is not built; run "
    "runners\\build-decoder.bat (it needs the .NET 10 SDK and a clone of "
    "michel-giehl/ValorantReplayParser beside this repository)"
)


class DecodeError(Exception):
    """The decoder is missing, refused the capture, or wrote something odd."""


@dataclass(frozen=True)
class Decoded:
    """
    One decode, exactly as the emitter stated it.

    `first_seen` is in **seconds** even though the file stores milliseconds,
    because that is what `abilities.spawns_from` takes and converting once here
    is cheaper than remembering to convert at every call site.
    """

    samples: dict[int, list[Position]] = field(default_factory=dict)
    archetypes: dict[int, str] = field(default_factory=dict)
    first_seen: dict[int, float] = field(default_factory=dict)
    spawn_locations: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    moves: int = 0
    hz: int = POSITION_HZ


# --------------------------------------------------------------------------
# Finding the decoder
# --------------------------------------------------------------------------


def locate(explicit: str | Path | None = None) -> Path:
    """The decoder to run, or raise saying every place that was looked."""
    if explicit:
        return _require(Path(explicit), "--parser-exe")

    configured, origin = _from_env()
    if configured is not None:
        return _require(configured, origin)

    found = _from_vendor() or _from_build()
    if found is not None:
        return found
    raise DecodeError(NOT_FOUND)


def _require(path: Path, origin: str) -> Path:
    """A deliberately configured path that is wrong is an error, not a hint."""
    if path.is_file():
        return path
    msg = f"{origin} points at {path}, which is not a file"
    raise DecodeError(msg)


def _from_env() -> tuple[Path | None, str]:
    from_environ = os.environ.get(ENV_VAR)
    if from_environ:
        return Path(from_environ.strip('"')), f"{ENV_VAR} (environment)"
    env_path = envfile.find_upwards(envfile.ENV_FILENAME)
    if env_path is not None and env_path.is_file():
        value = envfile.read(env_path).get(ENV_VAR)
        if value:
            return Path(value), f"{ENV_VAR} in {env_path}"
    return None, ""


def _from_vendor() -> Path | None:
    """A published, self-contained drop-in: no .NET runtime needed to run it."""
    root = envfile.find_upwards(VENDOR_DIRNAME)
    if root is None:
        return None
    candidate = root / VENDOR_SUBDIR / EXE_NAME
    return candidate if candidate.is_file() else None


def _from_build() -> Path | None:
    """Whatever `dotnet build` last produced in this working tree."""
    root = envfile.find_upwards(VENDOR_DIRNAME)
    if root is None:
        return None
    candidate = root.parent / BUILT
    return candidate if candidate.is_file() else None


def _command(decoder: Path, vrf: Path, out: Path, hz: int) -> list[str]:
    """
    How to invoke whichever of the two shapes was found.

    A published `.exe` runs itself; a `.dll` from a plain build is
    framework-dependent and needs the runtime launcher in front of it.
    """
    args = [str(vrf), str(out), "--hz", str(hz)]
    if decoder.suffix.lower() == ".dll":
        return ["dotnet", str(decoder), *args]
    return [str(decoder), *args]


# --------------------------------------------------------------------------
# Running it
# --------------------------------------------------------------------------


def run(
    vrf_path: str | Path,
    *,
    hz: int = POSITION_HZ,
    explicit: str | Path | None = None,
    out_path: str | Path | None = None,
) -> Decoded:
    """
    Decode one capture, and return the facts.

    Raises `DecodeError` for everything: a missing decoder, an unsupported
    build, a capture that will not parse.  `tracks.attach` turns each of those
    into a sentence, because positions never raise for want of positions.
    """
    decoder = locate(explicit)
    vrf = Path(vrf_path)
    out = Path(out_path) if out_path else _scratch_for(vrf)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        done = subprocess.run(  # noqa: S603
            _command(decoder, vrf, out, hz),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        msg = f"could not run {decoder}: {exc}"
        raise DecodeError(msg) from exc

    if done.returncode != 0:
        # The emitter prints one sentence and nothing else, which is exactly
        # what Replay.position_source wants to carry.
        detail = (done.stderr or done.stdout or "").strip().splitlines()
        reason = detail[-1] if detail else f"exit {done.returncode}"
        raise DecodeError(reason)

    try:
        return read(out)
    finally:
        if out_path is None:
            out.unlink(missing_ok=True)


SCRATCH_DIRNAME = "decode"


def _scratch_for(vrf: Path) -> Path:
    """
    Somewhere of our own to let the decoder write.

    Never beside the capture: `Demos/` is the user's directory, and the game
    deletes from it.

    The project's `.cache/decode/` when there is a project root, and the system
    temp directory when there is not.  This is the one place in the project
    that keeps that fallback, and it is not a cache: `run` unlinks the file the
    moment it has read it.  A decode failing for want of somewhere to put a
    scratch file would be a worse answer than putting it where every other
    program puts one.
    """
    root = vrfcache.project_root()
    base = (
        root / vrfcache.CACHE_DIRNAME / SCRATCH_DIRNAME
        if root is not None
        else Path(tempfile.gettempdir())
    )
    return base / f"{vrf.stem}.vrf-decode.json"


def read(path: str | Path) -> Decoded:
    """Read one emitter file, refusing anything that is not one."""
    src = Path(path)
    try:
        with src.open(encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        msg = f"{src}: unreadable decode: {exc}"
        raise DecodeError(msg) from exc

    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        msg = f"{src}: not a {FORMAT} file"
        raise DecodeError(msg)
    if doc.get("version") not in READABLE:
        msg = (
            f"{src}: decode version {doc.get('version')!r}, expected one of {READABLE}"
        )
        raise DecodeError(msg)

    samples = {
        int(raw_id): _samples(src, int(raw_id), columns)
        for raw_id, columns in (doc.get("samples") or {}).items()
    }
    return Decoded(
        samples=samples,
        archetypes={
            int(raw_id): str(path_)
            for raw_id, path_ in (doc.get("archetypes") or {}).items()
        },
        # Milliseconds on disk, seconds in hand: see Decoded.
        first_seen={
            int(raw_id): float(t_ms) / 1000.0
            for raw_id, t_ms in (doc.get("first_seen") or {}).items()
        },
        spawn_locations={
            int(raw_id): (float(xyz[0]), float(xyz[1]), float(xyz[2]))
            for raw_id, xyz in (doc.get("spawn_locations") or {}).items()
            if isinstance(xyz, list) and len(xyz) == 3  # noqa: PLR2004
        },
        moves=int(doc.get("moves") or 0),
        hz=int(doc.get("hz") or POSITION_HZ),
    )


_COLUMNS = ("t", "x", "y", "z", "yaw", "pitch")


def _samples(src: Path, actor_id: int, columns) -> list[Position]:
    """Six equal-length columns into Positions, or refuse the file."""
    if not isinstance(columns, dict) or any(c not in columns for c in _COLUMNS):
        msg = f"{src}: actor {actor_id} is missing one of the {len(_COLUMNS)} columns"
        raise DecodeError(msg)
    lengths = {len(columns[c]) for c in _COLUMNS}
    if len(lengths) != 1:
        msg = f"{src}: actor {actor_id} has ragged columns {sorted(lengths)}"
        raise DecodeError(msg)
    return [
        Position(
            t_ms=int(t),
            actor_id=actor_id,
            x=float(x),
            y=float(y),
            z=float(z),
            yaw=float(yaw),
            pitch=float(pitch),
        )
        for t, x, y, z, yaw, pitch in zip(
            columns["t"],
            columns["x"],
            columns["y"],
            columns["z"],
            columns["yaw"],
            columns["pitch"],
            strict=True,
        )
    ]
