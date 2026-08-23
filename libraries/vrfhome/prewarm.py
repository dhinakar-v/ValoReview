"""
Decode the library in the background, so no capture is ever decoded twice.

`vrfhome.scan` describes a library from plain chunks in about four seconds.
Actually *drawing* one needs the replication stream, which needs Oodle and
about four seconds, and until now that was paid every single time a capture was
opened -- `tracks.attach` wrote a sidecar only when `vrf-to-json` asked it to,
and never read one back for a `.vrf` at all.  With `vrfview.positioncache` in
place a decode is permanent, and the only question left is when it happens.
This is the answer: while the user is reading the match list.

One capture at a time, and why
------------------------------
A decode is CPU-bound, allocates a whole block of movement records at a time,
and holds the Oodle DLL.  Running four at once finishes the library sooner and
makes the window it is running in unusable, which is the wrong trade for work
nobody asked to wait for.  So there is one worker, it takes the captures in the
order the list shows them, and it yields the moment anything else needs it --
`pause()` is called when a viewer opens, because the viewer's own DECODE
POSITIONS button is a request the user *did* make and it should not queue
behind twenty they did not.

Stopping is prompt
------------------
The stop flag is checked in the per-block progress callback, not between
captures.  Between captures would mean a whole capture between asking the
window to close and it closing.

No tkinter here
---------------
Same rule as `scan`, and `tests/test_vrfhome.py` asserts it for both: this
schedules work and reports strings, and a caller marshals those onto the Tk
thread itself.  That is what lets the queue be tested with no display.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vrfhome import teamorder
from vrfview import infer as infer_mod
from vrfview import loader, names, positioncache, tracks

# What a capture's preparation is currently doing.
QUEUED = "QUEUED"
PREPARING = "PREPARING"
READY = "READY"
FAILED = "FAILED"

# A capture that was already decoded before the app started.
CACHED_NOTE = "already decoded"


@dataclass(frozen=True)
class Status:
    """One capture's place in the queue, and whatever it has to say."""

    state: str = QUEUED
    note: str = ""
    done: int = 0
    total: int = 0

    @property
    def ready(self) -> bool:
        return self.state == READY

    @property
    def label(self) -> str:
        """The short form a card chip shows."""
        if self.state == PREPARING and self.total:
            return f"{PREPARING} {self.done}/{self.total}"
        return self.state

    @property
    def described(self) -> str:
        return f"{self.label}: {self.note}" if self.note else self.label


class Prewarmer:
    """
    A single worker that fills the position cache from a scanned library.

    `on_change(path, status)` is called from the worker thread every time a
    capture's state moves.  It is the caller's job to marshal that onto its own
    UI thread; this class deliberately knows nothing about one.
    """

    def __init__(
        self,
        cards,
        on_change: Callable[[Path, Status], None] | None = None,
        agent_name: Callable[[str], str] | None = None,
    ) -> None:
        """
        `agent_name` turns an agent UUID into its published display name.

        It is how a finished decode answers the one question the plain chunks
        cannot -- which of the loadout roster's two halves is `infer`'s team A
        -- so that the match list can put a scoreline beside the right five
        agents.  Without it (no art on disk, or a caller that has none) the
        decode still happens and the letter is simply never recorded, which
        costs the card its numbers and nothing else.
        """
        # Only what is worth decoding, in the order the list shows it.  An
        # unreadable file and an unsupported build are both refusals `scan`
        # already made; repeating them here would be a second opinion on a
        # question that has one answer.
        self.queue = [c for c in cards if c.playable]
        self.on_change = on_change
        self._status: dict[Path, Status] = {}
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._thread: threading.Thread | None = None

        self.agent_name = agent_name
        # A capture already in the position cache is ready and needs no decode
        # -- unless nothing has yet worked out which half of its roster is team
        # A.  That answer only exists where codenames do, so such a capture is
        # queued anyway: `tracks.attach` will find the cache and return in
        # milliseconds without decoding a thing, and the letter gets recorded
        # on the way past.  Skipping them would mean a library decoded before
        # this existed never showed a scoreline again.
        known = teamorder.load() if agent_name is not None else {}
        for card in self.queue:
            cached = positioncache.has(card.path)
            lettered = not card.agent_ids[0] or card.match_id in known
            state = READY if cached and lettered else QUEUED
            note = CACHED_NOTE if state == READY else ""
            self._status[Path(card.path)] = Status(state=state, note=note)

    # -- state -----------------------------------------------------------
    def status(self, path: str | Path) -> Status:
        """One capture's status.  Anything not queued reports as not ready."""
        return self._status.get(Path(path), Status(state=QUEUED))

    @property
    def outstanding(self) -> list:
        return [c for c in self.queue if not self.status(c.path).ready]

    @property
    def described(self) -> str:
        ready = sum(1 for c in self.queue if self.status(c.path).ready)
        return f"{ready}/{len(self.queue)} replays prepared"

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        """Begin, unless there is nothing to do or it is already going."""
        if self.running or not self.outstanding:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._work,
            daemon=True,
            name="prewarm-positions",
        )
        self._thread.start()

    def stop(self) -> None:
        """Ask the worker to give up.  It checks between blocks, not captures."""
        self._stop.set()
        # A paused worker is parked on the resume event and would never reach
        # the stop check; releasing it lets it wake up and see it.
        self._resume.set()

    def pause(self) -> None:
        """Stand aside for work the user actually asked for."""
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()
        self.start()

    def join(self, timeout: float | None = None) -> None:
        """Wait for the worker, for a caller that needs it finished."""
        if self._thread is not None:
            self._thread.join(timeout)

    # -- the work --------------------------------------------------------
    def _work(self) -> None:
        for card in self.queue:
            if self._stop.is_set():
                return
            # Blocks here rather than in the loop below, so a pause takes
            # effect at a capture boundary and never mid-decode.
            self._resume.wait()
            if self._stop.is_set():
                return
            if self.status(card.path).ready:
                continue
            self._prepare(card)

    def _prepare(self, card) -> None:
        path = Path(card.path)
        self._set(path, Status(state=PREPARING))

        def progress(done: int, total: int) -> None:
            if self._stop.is_set():
                # `attach` has no cancel, so raising out of its own progress
                # callback is the one way to leave a decode early.  It is
                # caught below and reported as a stop, not as a failure.
                raise _StoppedError
            self._set(path, Status(state=PREPARING, done=done, total=total))

        try:
            replay = loader.load(path)
            infer_mod.annotate(replay)
            tracks.attach(replay, path, tracks.Options(progress=progress))
        except _StoppedError:
            self._set(path, Status(state=QUEUED))
            return
        except Exception as exc:  # noqa: BLE001 - a background queue may not die
            # `attach` is documented never to raise for want of positions, so
            # anything arriving here is a genuine surprise -- a corrupt file, a
            # full disk.  It costs this capture and not the queue.
            self._set(path, Status(state=FAILED, note=str(exc)))
            return

        if replay.has_positions:
            self._remember_team_order(replay, card)
            self._set(path, Status(state=READY, note=replay.position_source))
        else:
            self._set(path, Status(state=FAILED, note=replay.position_source))

    def _remember_team_order(self, replay, card) -> None:
        """
        Record which loadout half is team A, now that the pawns have names.

        `names.resolve` is what turns a decoded codename into the display name
        the catalogue publishes, which is the only form comparable with what an
        agent UUID resolves to.  Best-effort throughout: a capture that cannot
        be matched keeps its agents and loses only its numbers.
        """
        if self.agent_name is None or not card.agent_ids[0]:
            return
        try:
            names.resolve(replay)
            letter = teamorder.first_half_team(
                replay,
                card.agent_ids,
                self.agent_name,
            )
        except Exception:  # noqa: BLE001 - a background queue may not die
            return
        teamorder.record(replay.match_id, letter)

    def _set(self, path: Path, status: Status) -> None:
        self._status[path] = status
        if self.on_change is not None:
            self.on_change(path, status)


class _StoppedError(Exception):
    """Raised inside a progress callback to abandon a decode in progress."""
