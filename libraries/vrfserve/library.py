"""
What the server holds between requests: a scan, and a few open replays.

Two caches with different lifetimes.  The scan is the match list and is cheap
to keep -- `vrfhome.scan` already caches by `(path, mtime, size)` on disk, so
rescanning a hundred captures is hundredths of a second warm.  An open `Replay`
is not cheap: a fully decoded one is 199,180 `Position` objects, and holding
several is how a local app quietly takes a gigabyte.

`Replay` is the one mutable dataclass in the model, and `infer`, `names` and
`tracks` all annotate it in place.  That is fine in a single-threaded window and
is a hazard here, so two rules hold:

  * every read of an entry takes its lock for as long as it takes to serialise;
  * a decode never mutates the cached object.  It builds its own `Replay` from
    the file and replaces the entry when it finishes, so a request that arrives
    mid-decode sees the old replay whole rather than a new one half-written.

`revision` is what a browser watches.  A decode does not only add positions --
it also gives every pawn its codename and every cast its agent -- so the page
that was open before it is stale afterwards in more places than the map, which
is why the counter is on the whole entry and not on the tracks.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from vrfhome import scan
from vrfserve import ids
from vrfview import pipeline

if TYPE_CHECKING:
    from vrfview.model import Replay

# How many decoded replays to keep. Two is enough to flick between a pair
# without re-reading, and small enough that the footprint stays explainable.
MAX_OPEN = 2


@dataclass
class Entry:
    """One open replay, and the lock that keeps a decode off a serialiser."""

    replay: Replay
    path: Path
    replay_id: str
    revision: int = 1
    lock: threading.Lock = field(default_factory=threading.Lock)
    # The serialised positions document, kept because re-encoding twelve
    # megabytes per request is pointless. Dropped whenever revision moves.
    positions_json: bytes | None = None


class Library:
    """The scan, the id registry, and the open replays."""

    def __init__(
        self,
        result: scan.ScanResult | None = None,
        root: str | None = None,
    ) -> None:
        # Overrides DEMO_PATH the way a command-line flag does; None lets
        # vrfconfig resolve it and report which of the three sources answered.
        self.root = root
        self.registry = ids.Registry()
        self._entries: OrderedDict[str, Entry] = OrderedDict()
        self._guard = threading.Lock()
        self.result = result if result is not None else scan.ScanResult()
        self._register()

    def _register(self) -> None:
        self.registry.replace([c.path for c in self.result.cards])

    # -- the match list ---------------------------------------------------
    def rescan(self, *, cache: bool = True) -> scan.ScanResult:
        """Read the library again, optionally ignoring the on-disk cache."""
        self.result = scan.scan(
            root=self.root,
            cache=scan.Cache() if cache else scan.Cache(path=None),
        )
        self._register()
        return self.result

    def card(self, replay_id: str) -> scan.MatchCard | None:
        path = self.registry.path(replay_id)
        if path is None:
            return None
        for entry in self.result.cards:
            if entry.path == path:
                return entry
        return None

    def id_of(self, path: str | Path) -> str:
        return ids.id_for(path)

    # -- open replays -----------------------------------------------------
    def entry(self, replay_id: str) -> Entry | None:
        """An already-open replay, without opening one."""
        with self._guard:
            found = self._entries.get(replay_id)
            if found is not None:
                self._entries.move_to_end(replay_id)
            return found

    def open(self, replay_id: str) -> Entry | None:
        """
        Read a capture and keep it, or return the copy already held.

        The four steps are `vrfview.pipeline`'s and are not repeated here: an
        interface that reorders them shows ten players called `Hunter` rather
        than failing, so there is exactly one place they are written down.
        """
        held = self.entry(replay_id)
        if held is not None:
            return held
        path = self.registry.path(replay_id)
        if path is None:
            return None
        replay = pipeline.open_replay(path)
        entry = Entry(replay=replay, path=Path(path), replay_id=replay_id)
        with self._guard:
            self._entries[replay_id] = entry
            self._entries.move_to_end(replay_id)
            while len(self._entries) > MAX_OPEN:
                self._entries.popitem(last=False)
        return entry

    def close(self, replay_id: str) -> bool:
        with self._guard:
            return self._entries.pop(replay_id, None) is not None

    def replace(self, replay_id: str, replay: Replay) -> Entry | None:
        """
        Swap in a freshly decoded replay and move the revision on.

        Whole-object replacement rather than mutation: a request that arrives
        while a decode is finishing gets one replay or the other, never a
        replay whose positions have landed but whose codenames have not.
        """
        with self._guard:
            found = self._entries.get(replay_id)
            if found is None:
                return None
            found.replay = replay
            found.revision += 1
            found.positions_json = None
            return found

    @property
    def open_ids(self) -> list[str]:
        with self._guard:
            return list(self._entries)
