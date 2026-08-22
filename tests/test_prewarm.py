"""
The background decode queue: order, skipping, stopping, and never dying.

No `.vrf` is opened here.  `Prewarmer` is given fake cards and its one
expensive call is patched out, because what needs testing is the scheduling --
that it decodes the right captures in the right order, that it leaves alone the
ones already cached, that `stop()` is prompt, and that a capture which explodes
costs itself and not the queue.
"""

from __future__ import annotations

import threading
import unittest
from dataclasses import dataclass
from pathlib import Path

from vrfhome import prewarm

# How long a test waits for the worker before calling it hung.  Generous: the
# work is mocked, so anything approaching this is a real deadlock.
TIMEOUT = 10.0


@dataclass(frozen=True)
class FakeCard:
    """Only the two attributes `Prewarmer` reads off a scan card."""

    path: Path
    playable: bool = True


def cards(*names, playable=True):
    return [FakeCard(Path(f"{n}.vrf"), playable) for n in names]


class Harness:
    """
    A `Prewarmer` with its decode replaced and its cache answers scripted.

    Patching the three module-level names it calls is enough: the queue's own
    logic never touches the filesystem, which is the property that makes it
    testable without a library of 47 MB captures.
    """

    def __init__(self, test, *, cached=(), fails=(), on_decode=None):
        self.decoded: list[Path] = []
        self.cached = {Path(c) for c in cached}
        self.fails = {Path(f) for f in fails}
        self.on_decode = on_decode
        self.events: list[tuple[Path, str]] = []
        self.lock = threading.Lock()

        test.enterContext(Patch(prewarm.positioncache, "has", self._has))
        test.enterContext(Patch(prewarm.loader, "load", self._load))
        test.enterContext(Patch(prewarm.infer_mod, "annotate", lambda r: r))
        test.enterContext(Patch(prewarm.tracks, "attach", self._attach))

    # -- the patched world ----------------------------------------------
    def _has(self, path, root=None):  # noqa: ARG002 - matches positioncache.has
        return Path(path) in self.cached

    def _load(self, path):  # noqa: ARG002 - matches loader.load
        return _Replay()

    def _attach(self, replay, path, options=None):
        with self.lock:
            self.decoded.append(Path(path))
        if self.on_decode is not None:
            self.on_decode(Path(path), options)
        if Path(path) in self.fails:
            msg = "pretend this file is truncated"
            raise OSError(msg)
        replay.positions = {1: object()}
        replay.position_source = "decoded in a test"
        return replay

    # -- the callback ----------------------------------------------------
    def record(self, path, status):
        with self.lock:
            self.events.append((path, status.state))

    def states_for(self, path):
        with self.lock:
            return [s for p, s in self.events if p == Path(path)]


class _Replay:
    """The three attributes `_prepare` reads back off a decode."""

    def __init__(self):
        self.positions = {}
        self.position_source = ""

    @property
    def has_positions(self):
        return bool(self.positions)


class Patch:
    """A context manager, so `enterContext` unwinds these however a test ends."""

    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.was = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)
        return self.value

    def __exit__(self, *_exc):
        setattr(self.obj, self.name, self.was)
        return False


class TestQueue(unittest.TestCase):
    def test_only_playable_captures_are_queued(self):
        """
        An unsupported build and an unreadable file are refusals `scan` made.

        Re-deciding them here would be a second opinion on a question that
        already has one answer.
        """
        Harness(self)
        warmer = prewarm.Prewarmer(
            [*cards("a", "b"), *cards("old", playable=False)],
        )
        assert [c.path.stem for c in warmer.queue] == ["a", "b"]

    def test_captures_are_decoded_in_the_order_the_list_shows_them(self):
        harness = Harness(self)
        warmer = prewarm.Prewarmer(cards("a", "b", "c"))
        warmer.start()
        warmer.join(TIMEOUT)
        assert [p.stem for p in harness.decoded] == ["a", "b", "c"]

    def test_an_already_cached_capture_is_ready_without_being_decoded(self):
        harness = Harness(self, cached=["b.vrf"])
        warmer = prewarm.Prewarmer(cards("a", "b", "c"))
        assert warmer.status("b.vrf").ready
        assert warmer.status("b.vrf").note == prewarm.CACHED_NOTE
        warmer.start()
        warmer.join(TIMEOUT)
        assert [p.stem for p in harness.decoded] == ["a", "c"]

    def test_a_fully_cached_library_never_starts_a_thread(self):
        Harness(self, cached=["a.vrf", "b.vrf"])
        warmer = prewarm.Prewarmer(cards("a", "b"))
        warmer.start()
        assert not warmer.running
        assert warmer.outstanding == []

    def test_progress_moves_from_queued_through_preparing_to_ready(self):
        harness = Harness(self)
        warmer = prewarm.Prewarmer(cards("a"), on_change=harness.record)
        warmer.start()
        warmer.join(TIMEOUT)
        assert harness.states_for("a.vrf") == [prewarm.PREPARING, prewarm.READY]
        assert warmer.status("a.vrf").ready

    def test_the_summary_counts_what_is_prepared(self):
        Harness(self, cached=["a.vrf"])
        warmer = prewarm.Prewarmer(cards("a", "b"))
        assert warmer.described == "1/2 replays prepared"


class TestFailures(unittest.TestCase):
    def test_one_bad_capture_does_not_stop_the_queue(self):
        """
        `attach` is documented never to raise for want of positions.

        Anything that gets here is a genuine surprise -- a truncated file, a
        full disk -- and it must cost that capture and nothing else, because a
        background queue that dies silently is worse than one that never ran.
        """
        harness = Harness(self, fails=["b.vrf"])
        warmer = prewarm.Prewarmer(cards("a", "b", "c"))
        warmer.start()
        warmer.join(TIMEOUT)
        assert [p.stem for p in harness.decoded] == ["a", "b", "c"]
        assert warmer.status("b.vrf").state == prewarm.FAILED
        assert "truncated" in warmer.status("b.vrf").note
        assert warmer.status("c.vrf").ready

    def test_a_decode_that_finds_nothing_is_a_failure_with_the_reason(self):
        harness = Harness(self)

        def empty(replay, path, options=None):
            harness.decoded.append(Path(path))
            replay.position_source = "no positions: no payload transform"
            return replay

        with Patch(prewarm.tracks, "attach", empty):
            warmer = prewarm.Prewarmer(cards("a"))
            warmer.start()
            warmer.join(TIMEOUT)
        found = warmer.status("a.vrf")
        assert found.state == prewarm.FAILED
        assert "no payload transform" in found.note


class TestStopping(unittest.TestCase):
    def test_stop_is_seen_inside_a_decode_not_after_it(self):
        """
        The flag is checked in the per-block progress callback.

        Checking it between captures instead would mean up to four minutes
        between asking the window to close and it closing.
        """
        started = threading.Event()
        released = threading.Event()

        def slow(path, options):
            # Stand in for the block loop: the real decode calls this once per
            # REPLAYDATA block, and raising out of it is how one is cut short.
            # The gate makes the race deterministic -- the worker is parked
            # inside the first capture's decode until the test has stopped it.
            options.progress(0, 100)
            started.set()
            released.wait(TIMEOUT)
            for i in range(1, 100):
                options.progress(i, 100)

        harness = Harness(self, on_decode=slow)
        warmer = prewarm.Prewarmer(cards("a", "b", "c"), on_change=harness.record)
        warmer.start()
        assert started.wait(TIMEOUT)
        warmer.stop()
        released.set()
        warmer.join(TIMEOUT)
        assert not warmer.running
        # Only the capture it was already inside; b and c were never reached.
        assert [p.stem for p in harness.decoded] == ["a"]

    def test_an_abandoned_capture_goes_back_to_queued_not_failed(self):
        """Stopping is not a fault, and the chip must not accuse the file."""
        started = threading.Event()
        released = threading.Event()

        def slow(path, options):
            options.progress(0, 100)
            started.set()
            released.wait(TIMEOUT)
            options.progress(1, 100)

        harness = Harness(self, on_decode=slow)
        warmer = prewarm.Prewarmer(cards("a"), on_change=harness.record)
        warmer.start()
        assert started.wait(TIMEOUT)
        warmer.stop()
        released.set()
        warmer.join(TIMEOUT)
        assert warmer.status("a.vrf").state == prewarm.QUEUED
        assert prewarm.FAILED not in harness.states_for("a.vrf")

    def test_a_paused_worker_still_stops(self):
        """
        A pause parks the worker on an event it would never leave.

        `stop` releases it as well as setting the flag, or closing the window
        while a viewer was open would hang on the join.
        """
        harness = Harness(self)
        warmer = prewarm.Prewarmer(cards("a", "b"), on_change=harness.record)
        warmer.pause()
        warmer.start()
        warmer.stop()
        warmer.join(TIMEOUT)
        assert not warmer.running

    def test_resume_picks_up_what_is_left(self):
        harness = Harness(self, cached=["a.vrf"])
        warmer = prewarm.Prewarmer(cards("a", "b"))
        warmer.pause()
        warmer.resume()
        warmer.join(TIMEOUT)
        assert [p.stem for p in harness.decoded] == ["b"]
