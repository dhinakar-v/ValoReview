/**
 * The round as the unit of playback.
 *
 * The one thing worth pinning here is what the clock counts down *from*. A real
 * VALORANT round is a fixed timer plus a spike timer; what a capture holds is
 * when `roundStarted` fired and when the next one did, and those differ. Showing
 * a fixed 1:40 would be inventing a clock the file does not carry, so the
 * countdown is `duration_ms` and this asserts it hits 0:00 at `end_ms`.
 */

import { describe, expect, it } from "vitest";

import type { Replay, Round } from "../../api/types";
import {
  activeRound,
  clampToRound,
  clockText,
  elapsedMs,
  eventTimesIn,
  remainingMs,
  roundByNumber,
  roundOf,
} from "../roundclock";

function round(number: number, startMs: number, durationMs: number): Round {
  return {
    number,
    index: number - 1,
    start_ms: startMs,
    end_ms: startMs + durationMs,
    duration_ms: durationMs,
    winner: "A",
    reason: "wipe",
    decided: true,
  };
}

const ROUNDS = [round(1, 0, 100_000), round(2, 100_000, 85_000), round(3, 185_000, 92_000)];

const REPLAY = {
  rounds: ROUNDS,
  event_times: [5_000, 40_000, 120_000, 190_000, 260_000],
  length_ms: 277_000,
} as unknown as Replay;

describe("which round an instant is in", () => {
  it("finds it", () => {
    expect(roundOf(REPLAY, 0)?.number).toBe(1);
    expect(roundOf(REPLAY, 99_999)?.number).toBe(1);
    expect(roundOf(REPLAY, 100_000)?.number).toBe(2);
    expect(roundOf(REPLAY, 200_000)?.number).toBe(3);
  });

  it("says nothing rather than guessing past the end", () => {
    expect(roundOf(REPLAY, 400_000)).toBeNull();
    expect(roundByNumber(REPLAY, 9)).toBeNull();
    expect(roundByNumber(REPLAY, null)).toBeNull();
  });

  it("prefers an explicit choice over the playhead", () => {
    // Picking round 3 and then scrubbing does not silently rescope the
    // transport: the chip stays chosen until another one is pressed.
    expect(activeRound(REPLAY, 3, 0)?.number).toBe(3);
    expect(activeRound(REPLAY, null, 120_000)?.number).toBe(2);
  });

  it("falls back to the first round rather than to nothing", () => {
    // A transport has to be scoped to something, and the gap before
    // `roundStarted` fires is a real instant a capture can be at.
    expect(activeRound(REPLAY, null, 400_000)?.number).toBe(1);
  });
});

describe("the countdown", () => {
  it("is the round's own recorded length, not a fixed timer", () => {
    expect(remainingMs(ROUNDS[1]!, ROUNDS[1]!.start_ms)).toBe(85_000);
    expect(clockText(remainingMs(ROUNDS[1]!, ROUNDS[1]!.start_ms))).toBe("1:25");
  });

  it("reaches zero exactly at the end of the round", () => {
    expect(remainingMs(ROUNDS[0]!, ROUNDS[0]!.end_ms)).toBe(0);
    expect(clockText(remainingMs(ROUNDS[0]!, ROUNDS[0]!.end_ms))).toBe("0:00");
  });

  it("does not run past either edge", () => {
    expect(remainingMs(ROUNDS[0]!, -50_000)).toBe(100_000);
    expect(remainingMs(ROUNDS[0]!, 500_000)).toBe(0);
    expect(elapsedMs(ROUNDS[0]!, -50_000)).toBe(0);
    expect(elapsedMs(ROUNDS[0]!, 500_000)).toBe(100_000);
  });

  it("truncates rather than rounds", () => {
    // A clock showing 1:40 for the first half-second of 1:39.6 has already lied
    // about a whole second.
    expect(clockText(99_900)).toBe("1:39");
    expect(clockText(0)).toBe("0:00");
    expect(clockText(-5)).toBe("0:00");
  });

  it("clamps a seek to the round it is scoped to", () => {
    expect(clampToRound(ROUNDS[1]!, 0)).toBe(100_000);
    expect(clampToRound(ROUNDS[1]!, 999_999)).toBe(185_000);
  });
});

describe("stepping to an event", () => {
  it("walks only the events inside the round", () => {
    expect(eventTimesIn(REPLAY, ROUNDS[0]!)).toEqual([5_000, 40_000]);
    expect(eventTimesIn(REPLAY, ROUNDS[1]!)).toEqual([120_000]);
  });

  it("walks the whole capture where nothing is scoped", () => {
    expect(eventTimesIn(REPLAY, null)).toEqual(REPLAY.event_times);
  });
});
