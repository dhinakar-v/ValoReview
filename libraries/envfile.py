"""
Minimal .env reader, standing in for python-dotenv.

pyproject.toml declares no runtime dependencies and the project is stdlib +
tkinter, so a whole package would be a poor trade for the parsing below.

Nothing here mutates os.environ.  Callers read the real environment first and
fall back to the file, which keeps that precedence visible at the call site
rather than hiding it in an import-time side effect -- and means a shell export
or a CI secret always beats a checked-out .env without anyone editing a file.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILENAME = ".env"

# A value is quoted only if it has an opening and a closing quote, so the
# shortest quoted value -- an empty one -- is two characters long.
_QUOTED_MIN_LEN = 2

# Parsed files, keyed by resolved path.  A .env does not change under a running
# process often enough to be worth re-reading on every lookup; clear_cache()
# exists for the tests that write one.
_cache: dict[Path, dict[str, str]] = {}


def find_upwards(name: str, start: Path | None = None) -> Path | None:
    """
    Nearest `name` at or above `start`, then at or above this module.

    Two chains, because the working directory is where a user's .env and
    vendor/ live, while an installed wheel puts this module in site-packages
    with neither anywhere above it.  Trying both means a checkout run from any
    subdirectory and an installed copy run from a project both resolve.
    """
    bases = [start or Path.cwd(), Path(__file__).resolve().parent]
    for base in bases:
        for directory in (base, *base.parents):
            candidate = directory / name
            if candidate.exists():
                return candidate
    return None


def parse(text: str) -> dict[str, str]:
    """
    KEY=VALUE lines into a dict.

    Blank lines, # comments and lines with no = are skipped, an `export `
    prefix is tolerated, and a quoted value keeps everything inside the quotes.
    An unquoted value loses any trailing ` #` comment, so a path containing a
    literal # has to be quoted.  Later duplicates win, as a shell would do.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if key:
            out[key] = _unquote(value.strip())
    return out


def _unquote(value: str) -> str:
    if len(value) >= _QUOTED_MIN_LEN and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value.partition(" #")[0].strip()


def read(path: Path | str) -> dict[str, str]:
    """Parsed contents of one .env, or {} if it is absent or unreadable."""
    resolved = Path(path).resolve()
    if resolved not in _cache:
        try:
            _cache[resolved] = parse(resolved.read_text(encoding="utf-8"))
        except OSError:
            _cache[resolved] = {}
    return _cache[resolved]


def get(key: str, default: str | None = None) -> str | None:
    """Value for `key` from the real environment, else from the nearest .env."""
    from_environ = os.environ.get(key)
    if from_environ:
        return from_environ
    path = find_upwards(ENV_FILENAME)
    if path is not None and path.is_file():
        value = read(path).get(key)
        if value:
            return value
    return default


def clear_cache() -> None:
    """Forget every parsed file; a test that rewrites a .env needs this."""
    _cache.clear()
