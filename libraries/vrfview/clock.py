"""
The playback clock.

It never reads the wall clock itself.  `tick` is handed the elapsed
milliseconds by whoever is driving the frame loop, which is what keeps the
clock unit-testable without sleeping and makes the speed multiplier exact:
speed scales the delta, never the frame rate.

Pausing is exact for the same reason.  The driver refreshes its wall-time
reference every frame whether or not the clock is running, so no time
accumulates across a pause and resuming does not jump.
"""

from __future__ import annotations

SPEEDS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)


class PlaybackClock:
    """Replay position in milliseconds, advanced by explicit deltas."""

    def __init__(self, length_ms: int, speed: float = 1.0) -> None:
        self.length_ms = max(0, int(length_ms))
        self.speed = speed
        self.playing = False
        self._t = 0.0

    @property
    def t_ms(self) -> int:
        return int(self._t)

    @property
    def at_end(self) -> bool:
        return self._t >= self.length_ms

    def tick(self, wall_delta_ms: float) -> float:
        """Advance by `wall_delta_ms` of real time; return ms actually moved."""
        if not self.playing or wall_delta_ms <= 0:
            return 0.0
        before = self._t
        self._t = min(self._t + wall_delta_ms * self.speed, float(self.length_ms))
        if self.at_end:
            self.playing = False
        return self._t - before

    def seek(self, ms: float) -> None:
        self._t = max(0.0, min(float(ms), float(self.length_ms)))

    def nudge(self, delta_ms: float) -> None:
        self.seek(self._t + delta_ms)

    def play(self) -> None:
        if self.at_end:
            self._t = 0.0
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.01, float(speed))
