"""
Where this project keeps disposable data: one directory, inside the checkout.

Everything regenerable lands under `<project root>/.cache/` -- the decoded
position sidecars, the resolved Oodle path, the match-list scan, and the
decoder's own scratch.  One directory means a user can find the cache, and
deleting it is a complete reset rather than a hunt through four conventions.

Why not %LOCALAPPDATA%
----------------------
That is where the position cache and the Oodle cache used to live, and it is
defensible for a machine-scoped tool: it survives a reinstall and it is
per-user.  It is the wrong answer here for one reason -- the data belongs to a
*checkout*, not to a machine.  A cached decode is keyed by a capture in this
repository's `DEMO_PATH`, and the Oodle answer is only meaningful while this
tree's `vendor/` and `.env` say what they currently say.  Putting it outside
the tree also put it outside the user's reach: two caches accumulating tens of
megabytes per capture in a directory nothing in the project ever mentions.

Why not `out/`, which is what `vrfhome.scan` used to do
-------------------------------------------------------
`Path("out")` is relative to the *working directory*, so running the app from
anywhere but the repository root silently addressed a different cache and
rescanned.  This is not that.  The root here is **searched for**, not assumed:
`envfile.find_upwards` walks up until it finds the marker, so every entry point
-- a runner, a test, an editor, a CLI invoked from a subdirectory -- resolves
the same directory.  The complaint about `out/` was never "it is in the tree",
it was "it is a bare relative path".

There is no fallback, on purpose
--------------------------------
`root()` raises when there is no project root above the code, which is what an
installed wheel in site-packages looks like.  Falling back to the working
directory would recreate the `out/` bug; falling back to %LOCALAPPDATA% would
recreate the directory this module exists to retire.  So callers catch the
refusal and degrade: every cache in this project is an optimisation whose
absence costs time and nothing else, and each one already had that path.
`root_or_none()` is the non-raising half, for the two callers that would rather
have no cache than an exception -- `vrfhome.scan`, which simply rescans, and
`vrfview.csharpdecode`, whose scratch file is deleted the moment it is read and
must not fail a decode for want of a home.

A *configured* root is not a fallback
-------------------------------------
`VRF_CACHE_ROOT` names the cache directory outright, and is read before the
search runs.  That is the opposite of a fallback: a fallback guesses when it
was not told, and this is being told.  It exists for the packaged desktop app,
where there is no checkout for the argument above to be about -- the data still
belongs to one installation rather than to a machine, and the installer is what
knows where that installation keeps things.  With the variable unset nothing
changes, the refusal included: an installed copy that was never told where to
cache still caches nothing and simply redoes the work.

Note what it names.  `VRF_CACHE_ROOT` is the cache directory *itself*, not a
project root to append `.cache/` to, because the thing an installer has to hand
is somewhere to put files rather than somewhere a `pyproject.toml` pretends to
be.

A note on which root is found
-----------------------------
`find_upwards` tries the working directory's chain first and the chain above
`envfile` itself second.  In a checkout the second chain always reaches this
repository, so the answer does not depend on where you ran from.  The first
chain wins only when the working directory sits inside a *different* Python
project -- which is exactly how the tests get an isolated root
(`tests/test_oodlefind.py` chdirs into a temp directory holding a
`pyproject.toml`) instead of writing into the real repository's cache.

Nothing here touches the disk beyond the search.  No directory is created:
each writer already makes its own parent, and a `cache_root()` with a side
effect would mean merely *asking* where the cache is created one.
"""

from __future__ import annotations

from pathlib import Path

import envfile

# The file that says "a project starts here".  pyproject.toml rather than .git
# (a worktree or an exported tree has none) or vendor/ (optional, gitignored,
# and absent on a fresh checkout).  It is also the file that names this
# project, so finding it is finding the thing the cache belongs to.
MARKER = "pyproject.toml"

CACHE_DIRNAME = ".cache"

# The one way to name the cache directory from outside.  Read through envfile,
# so it obeys the same "real environment first, nearest .env second" order as
# DEMO_PATH, VRF_OODLE_DLL and VRF_PARSER_EXE.
ROOT_ENV = "VRF_CACHE_ROOT"

NO_ROOT = (
    f"no {MARKER} above this code and no {ROOT_ENV}, so there is nowhere to "
    "cache (an installed copy caches nothing and simply redoes the work)"
)


class NoProjectRootError(Exception):
    """Nowhere to cache: no configured root and no project root."""


def project_root() -> Path | None:
    """The directory holding the marker, or None if there is not one."""
    found = envfile.find_upwards(MARKER)
    return None if found is None else found.parent


def configured_root() -> Path | None:
    """The cache directory `VRF_CACHE_ROOT` names, or None if none does."""
    value = envfile.get(ROOT_ENV)
    return None if not value else Path(value.strip('"')).expanduser()


def root() -> Path:
    """The cache directory, or raise saying why there is not one."""
    named = configured_root()
    if named is not None:
        return named
    base = project_root()
    if base is None:
        raise NoProjectRootError(NO_ROOT)
    return base / CACHE_DIRNAME


def root_or_none() -> Path | None:
    """The cache directory, or None -- for a caller that must not raise."""
    try:
        return root()
    except NoProjectRootError:
        return None


def subdir(*parts: str) -> Path:
    """One named area of the cache, e.g. `subdir("positions")`."""
    return root().joinpath(*parts)
