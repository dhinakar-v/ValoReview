"""
Where a decoded replay is kept so it is never decoded twice.

`positionfile` defines the sidecar; this decides where one lives when nobody
asked for a particular path.  The two are separate because a sidecar written by
`vrf-to-json --positions` belongs *beside its dump* -- it is an output the user
asked for and can copy around -- whereas the one the app writes after a decode
is a cache: machine-scoped, disposable, and none of the user's business.

Why not next to the `.vrf`
--------------------------
`DEMO_PATH` points at the folder VALORANT itself writes captures into.  Writing
into it means writing into the game's directory, on a path the game will
happily delete a capture from, and it makes a read-only or network library fail
for a reason that has nothing to do with the replay.

Why not `out/`
--------------
`vrfhome.scan` caches there, and it is wrong about it: `Path("out")` is
relative to the working directory, so running the app from anywhere but the
repo root silently loses the whole cache and rescans.  For a four-second rescan
that is a wart; for a four-*minute* decode per capture it would be a serious
bug, so this follows `oodlefind.cache_file` instead, which is the one place in
the project that already resolves a real per-machine cache directory.

Everything here degrades to a slower run
----------------------------------------
An unwritable cache directory, a corrupt entry and a full disk all end as "no
cache entry", never as an exception: the fallback is to decode, which is what
would have happened anyway.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from vrfview import positionfile

APP_DIRNAME = "val-replay-analyzer"
CACHE_DIRNAME = "positions"


def cache_root() -> Path:
    """
    The per-machine cache directory, the way `oodlefind.cache_file` picks one.

    Deliberately the same base as the Oodle cache rather than a second
    convention: two caches for one application in two different places is how
    a user ends up unable to clear either.
    """
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".cache"
    return base / APP_DIRNAME / CACHE_DIRNAME


def cache_path(replay_path: str | Path, root: Path | None = None) -> Path:
    """
    The cache entry belonging to one capture.

    Named from the file's stem, which for a Valorant capture is the match ID
    and therefore already unique.  It is not *only* trusted to be: the sidecar
    records its own `match_id` and `tracks` refuses one that disagrees, so two
    unrelated files sharing a stem cost a re-decode rather than a wrong map.
    """
    stem = Path(replay_path).stem
    return (
        cache_root() if root is None else Path(root)
    ) / f"{stem}{positionfile.SUFFIX}"


def read(replay_path: str | Path, root: Path | None = None):
    """The cached sidecar for a capture, or None if there is not a usable one."""
    path = cache_path(replay_path, root)
    if not path.is_file():
        return None
    try:
        return positionfile.read(path)
    except positionfile.PositionFileError:
        # A cache entry we cannot read is one we should not keep. Dropping it
        # here is what stops a format change from costing a decode every run
        # forever, rather than only the once.
        with contextlib.suppress(OSError):
            path.unlink()
        return None


def write(replay_path: str | Path, sidecar, root: Path | None = None) -> Path | None:
    """Store one decode, returning where it went or None if it could not."""
    path = cache_path(replay_path, root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return positionfile.write(path, sidecar)
    except OSError:
        return None


def has(replay_path: str | Path, root: Path | None = None) -> bool:
    """Whether a capture is already decoded, without parsing the entry."""
    return cache_path(replay_path, root).is_file()
