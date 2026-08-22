"""
Find an Oodle runtime (oo2core_*_win64.dll) on this machine.

Valorant cannot supply one, which is worth stating plainly because the install
looks like it should.  Its shipping exe links Oodle statically -- the symbol
oo2::OodleLZ_Decompress and the whole set of "OODLE ERROR :" strings are
compiled into VALORANT-Win64-Shipping.exe -- and none of the 131 DLLs beside it
is an oo2core.  The exe does export 659 symbols, but they are all Wwise audio
(AK::SoundEngine::...), so there is no Oodle entry point to bind to either.  A
DLL has to come from somewhere else.

Search order, most explicit and cheapest first:

  1. --oodle-dll PATH          an argument beats everything
  2. VRF_OODLE_DLL             real environment, then the nearest .env
  3. vendor/                   drop-in directory beside pyproject.toml
  4. cache                     whatever a previous scan resolved
  5. Steam and Epic libraries  any installed UE4/UE5 game ships one

Steps 1 and 2 are configured on purpose, so a path that does not exist raises
instead of quietly falling through to a scan -- a typo in .env should not look
like a missing DLL.  Only step 5 touches the disk in bulk, and it writes its
answer to the project's own `.cache/` so it runs at most once per checkout --
which is the right scope, because the answer is only meaningful while this
tree's `vendor/` and `.env` say what they currently say.  It globs a handful of
known layouts under each game rather than walking installs, because an rglob
over a Fortnite directory is tens of thousands of files.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import envfile
import vrfcache

if TYPE_CHECKING:
    from collections.abc import Iterable

try:
    import winreg
except ImportError:  # not Windows; the registry lookups then find nothing
    winreg = None

ENV_VAR = "VRF_OODLE_DLL"
VENDOR_DIRNAME = "vendor"

DLL_RE = re.compile(r"^oo2core_\d+_win64\.dll$", re.IGNORECASE)

# Where a game keeps its Oodle runtime, relative to its install root.  Unreal
# puts it under Engine/Binaries/ThirdParty/Oodle; some titles drop it beside
# the exe or at the root instead.  Globs, not rglob, to keep the scan bounded.
_DLL_GLOBS = (
    "oo2core_*_win64.dll",
    "Binaries/Win64/oo2core_*_win64.dll",
    "Engine/Binaries/Win64/oo2core_*_win64.dll",
    "Engine/Binaries/ThirdParty/Oodle/Win64/oo2core_*_win64.dll",
    "Engine/Binaries/ThirdParty/Oodle/*/Win64/oo2core_*_win64.dll",
    "*/Binaries/Win64/oo2core_*_win64.dll",
)

# libraryfolders.vdf lists libraries as "path" in current Steam builds and as a
# bare numeric key in older ones; match either.
_VDF_PATH_RE = re.compile(r'"(?:path|\d+)"\s*"([^"]+)"', re.IGNORECASE)


class OodleNotFoundError(Exception):
    """No usable oo2core runtime; the message says how to supply one."""


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def locate(explicit: str | Path | None = None, *, use_cache: bool = True) -> Path:
    """Path to an oo2core runtime, or raise OodleNotFoundError explaining the fix."""
    if explicit:
        return _require(Path(str(explicit).strip('"')), f"--oodle-dll {explicit}")

    configured, origin = _from_env()
    if configured is not None:
        return _require(configured, origin)

    found = _from_vendor()
    if found is not None:
        return found

    if use_cache:
        cached = _read_cache()
        if cached is not None and cached.is_file():
            return cached

    roots = game_roots()
    for root in roots:
        found = _match_in(root)
        if found is not None:
            _write_cache(found)
            return found

    raise OodleNotFoundError(not_found_message(len(roots)))


def not_found_message(searched: int = 0) -> str:
    """The actionable half of the error: every way to supply a DLL."""
    vendor = vendor_dir() or Path.cwd() / VENDOR_DIRNAME
    plural = "y" if searched == 1 else "ies"
    return (
        "no Oodle runtime found (oo2core_*_win64.dll).\n"
        "Valorant cannot provide one: it links Oodle statically and exports no "
        "Oodle symbols.\n"
        "Supply a DLL in any of these ways:\n"
        f"  - drop it in {vendor}\\ (gitignored)\n"
        f"  - set {ENV_VAR}=C:\\path\\to\\oo2core_9_win64.dll in .env\n"
        "  - pass --oodle-dll C:\\path\\to\\oo2core_9_win64.dll\n"
        "Any UE4/UE5 game install has one, usually under\n"
        "Engine\\Binaries\\ThirdParty\\Oodle\\Win64\\.\n"
        f"Searched {searched} game director{plural} in the Steam and Epic libraries."
    )


def _require(path: Path, origin: str) -> Path:
    """A path someone set on purpose: a miss is an error, not a fallback."""
    if path.is_file():
        return path
    msg = f"{origin} points at {path}, which is not a file"
    raise OodleNotFoundError(msg)


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


def _from_env() -> tuple[Path | None, str]:
    """The configured path and where it came from, for a precise error."""
    from_environ = os.environ.get(ENV_VAR)
    if from_environ:
        return Path(from_environ.strip('"')), f"{ENV_VAR} (environment)"
    env_path = envfile.find_upwards(envfile.ENV_FILENAME)
    if env_path is not None and env_path.is_file():
        value = envfile.read(env_path).get(ENV_VAR)
        if value:
            return Path(value), f"{ENV_VAR} in {env_path}"
    return None, ""


def vendor_dir() -> Path | None:
    """The drop-in directory, wherever the project root turns out to be."""
    return envfile.find_upwards(VENDOR_DIRNAME)


def _from_vendor() -> Path | None:
    directory = vendor_dir()
    if directory is None or not directory.is_dir():
        return None
    return _best_dll(directory.glob("oo2core_*_win64.dll"))


def _best_dll(candidates: Iterable[Path]) -> Path | None:
    """Highest version number wins: Oodle 2.5+ decodes these blocks."""
    hits = [p for p in candidates if DLL_RE.match(p.name) and p.is_file()]
    hits.sort(key=_version_of, reverse=True)
    return hits[0] if hits else None


def _version_of(path: Path) -> int:
    match = re.search(r"\d+", path.name)
    return int(match.group()) if match else 0


def _match_in(root: Path) -> Path | None:
    for pattern in _DLL_GLOBS:
        try:
            found = _best_dll(root.glob(pattern))
        except OSError:
            continue
        if found is not None:
            return found
    return None


# --------------------------------------------------------------------------
# Game libraries
# --------------------------------------------------------------------------


def game_roots() -> list[Path]:
    """Every installed game directory Steam and Epic know about."""
    roots: list[Path] = []
    for library in steam_libraries():
        common = library / "steamapps" / "common"
        try:
            roots.extend(d for d in common.iterdir() if d.is_dir())
        except OSError:
            continue
    roots.extend(epic_installs())
    return roots


def steam_libraries() -> list[Path]:
    """The Steam install plus every extra library folder it has registered."""
    root = _steam_root()
    if root is None:
        return []
    libraries = [root]
    try:
        text = (root / "steamapps" / "libraryfolders.vdf").read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return libraries
    for raw in _VDF_PATH_RE.findall(text):
        path = Path(raw.replace("\\\\", "\\"))
        if path.is_dir() and path not in libraries:
            libraries.append(path)
    return libraries


def _steam_root() -> Path | None:
    for hive, key, value in (
        ("HKCU", r"Software\Valve\Steam", "SteamPath"),
        ("HKLM", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    ):
        got = _reg_read(hive, key, value)
        if got and Path(got).is_dir():
            return Path(got)
    return None


def epic_installs() -> list[Path]:
    """Install locations from the Epic launcher's per-app manifests."""
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    manifests = program_data / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if not manifests.is_dir():
        return []
    out: list[Path] = []
    for item in manifests.glob("*.item"):
        try:
            doc = json.loads(item.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        location = doc.get("InstallLocation") if isinstance(doc, dict) else None
        if location and Path(location).is_dir():
            out.append(Path(location))
    return out


def _reg_read(hive: str, key: str, value: str) -> str | None:
    if winreg is None:
        return None
    roots = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    try:
        with winreg.OpenKey(roots[hive], key) as handle:
            return str(winreg.QueryValueEx(handle, value)[0])
    except OSError:
        return None


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------


def cache_file() -> Path:
    """
    Where a resolved path is remembered, so the scan runs once per checkout.

    In the project's own `.cache/` rather than %LOCALAPPDATA%, beside the
    decoded positions: one directory a user can find and delete.  Raises
    `NoProjectRootError` when there is no project root, which both callers
    below treat as "no cache" -- costing a rescan and nothing else.
    """
    return vrfcache.root() / "oodle.json"


def _read_cache() -> Path | None:
    try:
        doc = json.loads(cache_file().read_text(encoding="utf-8"))
    except (OSError, ValueError, vrfcache.NoProjectRootError):
        return None
    path = doc.get("path") if isinstance(doc, dict) else None
    return Path(path) if path else None


def _write_cache(path: Path) -> None:
    # A cache that cannot be written costs a rescan next run, nothing more --
    # and with no project root there is nowhere to write one at all.
    with contextlib.suppress(OSError, vrfcache.NoProjectRootError):
        target = cache_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"path": str(path)}), encoding="utf-8")
