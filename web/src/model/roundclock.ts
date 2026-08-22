/**
 * The round as the unit of playback.
 *
 * The desktop viewer and the first web port both treated a capture as one
 * twenty-six minute timeline with a round band drawn across it.  That is the
 * right model of the *file* and the wrong model of the *task*: nobody watches a
 * replay end to end, they watch round four, and a scrubber spanning twenty-six
 * minutes gives round four about forty pixels.
 *
 * So the transport is scoped to a round and the clock counts down inside it.
 * Nothing here changes the model underneath -- `stateAt` still takes an absolute
 * millisecond and still recomputes from scratch, so seeking backwards across a
 * round boundary is exactly as correct as it was.  This is arithmetic over
 * `Replay.rounds`, which `infer` already numbered.
 *
 * **The countdown is the round's own recorded length, not 1:40.** A real
 * VALORANT round is a fixed timer plus a spike timer, but what a capture holds
 * is when `roundStarted` fired and when the next one did, and those differ --
 * an eight-second round-one buy phase is inside the first, a long overtime
 * pause inside another.  Showing a fixed 1:40 would be inventing a clock the
 * file does not carry; showing `duration_ms` is reading one it does.
 */

import type { Replay, Round } from "../api/types";

/** The round containing an instant, or null before the first / after the last. */
export function roundOf(replay: Replay, tMs: number): Round | null {
  for (const round of replay.rounds) {
    if (tMs >= round.start_ms && tMs < round.end_ms) {
      return round;
    }
  }
  return null;
}

export function roundByNumber(replay: Replay, number: number | null): Round | null {
  if (number === null) {
    return null;
  }
  return replay.rounds.find((round) => round.number === number) ?? null;
}

/**
 * Which round the transport is working in.
 *
 * An explicit choice wins; otherwise it is wherever the playhead is; and if the
 * playhead is in no round at all -- the gap before `roundStarted` fires -- it is
 * the first, because a transport has to be scoped to something.
 */
export function activeRound(
  replay: Replay,
  roundNo: number | null,
  tMs: number,
): Round | null {
  return (
    roundByNumber(replay, roundNo) ?? roundOf(replay, tMs) ?? replay.rounds[0] ?? null
  );
}

/** Milliseconds left in the round, floored at zero and clamped to its length. */
export function remainingMs(round: Round, tMs: number): number {
  return Math.max(0, Math.min(round.duration_ms, round.end_ms - tMs));
}

/** Milliseconds since the round started, which is what a scrubber spans. */
export function elapsedMs(round: Round, tMs: number): number {
  return Math.max(0, Math.min(round.duration_ms, tMs - round.start_ms));
}

export function clampToRound(round: Round, tMs: number): number {
  return Math.max(round.start_ms, Math.min(round.end_ms, tMs));
}

/**
 * `M:SS`, floor-truncated.
 *
 * Truncation and not rounding: a countdown that shows 1:40 for the first half
 * second of a 1:39.6 round has already lied about a whole second, and every
 * other clock in this interface truncates for the same reason.
 */
export function clockText(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Every event time inside a round, which is what step-to-event walks. */
export function eventTimesIn(replay: Replay, round: Round | null): number[] {
  if (round === null) {
    return replay.event_times;
  }
  return replay.event_times.filter((t) => t >= round.start_ms && t < round.end_ms);
}
