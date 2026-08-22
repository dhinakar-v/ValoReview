/**
 * The playback clock.  A port of `vrfview.clock.PlaybackClock`.
 *
 * It never reads the wall clock itself.  `tick` is handed the elapsed
 * milliseconds by whoever is driving the frame loop, which is what makes the
 * speed multiplier exact -- speed scales the delta, never the frame rate -- and
 * what makes `tests/golden/clock.json` reproducible in two languages without
 * either of them sleeping.
 *
 * Pausing is exact for the same reason: the driver refreshes its wall-time
 * reference every frame whether or not the clock is running, so no time
 * accumulates across a pause and resuming does not jump.
 */

export const SPEEDS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0] as const;

export class PlaybackClock {
  readonly lengthMs: number;
  speed: number;
  playing = false;
  /** The playhead at full precision; `tMs` is what anything else should read. */
  private t = 0;

  constructor(lengthMs: number, speed = 1.0) {
    this.lengthMs = Math.max(0, Math.trunc(lengthMs));
    this.speed = speed;
  }

  /** `int()`, not `floor()`: the same truncation Python's `int` does. */
  get tMs(): number {
    return Math.trunc(this.t);
  }

  get atEnd(): boolean {
    return this.t >= this.lengthMs;
  }

  /** Advance by `wallDeltaMs` of real time; return the ms actually moved. */
  tick(wallDeltaMs: number): number {
    if (!this.playing || wallDeltaMs <= 0) {
      return 0;
    }
    const before = this.t;
    this.t = Math.min(this.t + wallDeltaMs * this.speed, this.lengthMs);
    if (this.atEnd) {
      this.playing = false;
    }
    return this.t - before;
  }

  seek(ms: number): void {
    this.t = Math.max(0, Math.min(ms, this.lengthMs));
  }

  nudge(deltaMs: number): void {
    this.seek(this.t + deltaMs);
  }

  play(): void {
    if (this.atEnd) {
      this.t = 0;
    }
    this.playing = true;
  }

  pause(): void {
    this.playing = false;
  }

  toggle(): void {
    if (this.playing) {
      this.pause();
    } else {
      this.play();
    }
  }

  /**
   * A floor of 0.01, because a stopped clock is what `pause` is for.
   *
   * A speed of zero looks like playback and never advances, which is a bug
   * report rather than a feature.
   */
  setSpeed(speed: number): void {
    this.speed = Math.max(0.01, speed);
  }
}
