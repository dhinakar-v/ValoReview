"""
Where a decoded replay is kept so it is never decoded twice.

`positionfile` defines the sidecar; this decides where one lives when nobody
asked for a particular path.  The two are separate because a sidecar written by
`vrf-to-json --positions` belongs *beside its dump* -- it is an output the user
asked for and can copy around -- whereas the one the app writes after a decode
is a cache: regenerable, disposable, and safe to delete without losing a fact.

Why not next to the `.vrf`
--------------------------
`DEMO_PATH` points at the folder VALORANT itself writes captures into.  Writing
into it means writing into the game's directory, on a path the game will
happily delete a capture from, and it makes a read-only or network library fail
for a reason that has nothing to do with the replay.

Why the project's own `.cache/`, and why that is not `out/`
-----------------------------------------------------------
`vrfhome.scan` used to cache in `out/`, and it was wrong about it: `Path("out")`
is relative to the working directory, so running the app from anywhere but the
repo root silently addressed a different cache and rescanned.  The fix was
never to leave the tree -- it was to stop assuming the path.  `vrfcache` walks
up for the project marker, so every entry point resolves the same directory
whatever the working directory is, and a user who wants the decodes gone can
delete one folder they can actually find.

Everything here degrades to a slower run
----------------------------------------
An unwritable cache directory, a corrupt entry, a full disk and *no project
root at all* -- an installed copy in site-packages -- all end as "no cache
entry", never as an exception: the fallback is to decode, which is what would
have happened anyway.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import vrfcache
from vrfview import positionfile

CACHE_DIRNAME = "positions"


def cache_root() -> Path:
    """
    The cache directory, under the project's own `.cache/`.

    Deliberately the same base as the Oodle cache rather than a second
    convention: two caches for one application in two different places is how
    a user ends up unable to clear either.  Raises `NoProjectRootError` when
    there is no project root; every caller below turns that into "no entry".
    """
    return vrfcache.subdir(CACHE_DIRNAME)


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


def entry(replay_path: str | Path, root: Path | None = None) -> Path | None:
    """
    The cache file for a capture if there is one on disk, else None.

    The non-raising face of `cache_path`, and the one `tracks.attach` uses: a
    caller that wants to read a cached decode should not have to know that
    "there is no project root" is a thing that can happen, and it certainly
    should not turn into a traceback in the middle of opening a replay.
    """
    try:
        path = cache_path(replay_path, root)
    except vrfcache.NoProjectRootError:
        return None
    return path if path.is_file() else None


def read(replay_path: str | Path, root: Path | None = None):
    """The cached sidecar for a capture, or None if there is not a usable one."""
    path = entry(replay_path, root)
    if path is None:
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
    try:
        path = cache_path(replay_path, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        return positionfile.write(path, sidecar)
    except (OSError, vrfcache.NoProjectRootError):
        return None


def has(replay_path: str | Path, root: Path | None = None) -> bool:
    """Whether a capture is already decoded, without parsing the entry."""
    return entry(replay_path, root) is not None
