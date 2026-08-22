"""
Stable, opaque ids for the captures a scan found.

A URL never carries a filesystem path.  The server is local and single-user, so
the threat is not an attacker so much as the shape of the mistake: the moment a
handler joins a client string onto a directory, `..` works, Windows backslashes
and URL escaping start mattering, and a bug there reads files rather than
returning a wrong answer.  A registry closes that off structurally -- an id the
scan did not produce resolves to nothing, and there is no code path that turns
a request into a path any other way.

The id is a digest of the resolved path rather than the file stem.  A stem is
usually the match UUID and would be prettier, but `positioncache` already
documents that it is not trusted to be unique, and two captures colliding would
silently serve one for the other.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Long enough that a library of a few thousand captures will not collide, short
# enough to read in a URL.
ID_LENGTH = 16


def id_for(path: str | Path) -> str:
    """The id of one capture, from its resolved path."""
    resolved = str(Path(path).resolve())
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()
    return digest[:ID_LENGTH]


class Registry:
    """Every capture a scan described, addressable by id."""

    def __init__(self) -> None:
        self._paths: dict[str, Path] = {}

    def add(self, path: str | Path) -> str:
        found = id_for(path)
        self._paths[found] = Path(path)
        return found

    def replace(self, paths) -> None:
        """Rebuild from a fresh scan, forgetting captures that have gone."""
        self._paths = {id_for(p): Path(p) for p in paths}

    def id_for_path(self, path: str | Path) -> str:
        """The id a capture would have, whether or not it is registered."""
        return id_for(path)

    def path(self, replay_id: str) -> Path | None:
        """The capture with this id, or None.  Never derived from the string."""
        return self._paths.get(replay_id)

    def __contains__(self, replay_id: object) -> bool:
        return replay_id in self._paths

    def __len__(self) -> int:
        return len(self._paths)
