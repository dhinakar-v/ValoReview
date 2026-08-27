/**
 * What a tracer refuses to draw, which is the whole of what makes it honest.
 *
 * The line itself is generated -- a `.vrf` holds no shot -- so the only thing
 * keeping it from being a plausible invention is that both of its ends are
 * real.  Each assertion below is one of the ways that could quietly stop being
 * true: the wrong instant, a track that never answered, a shooter who is not
 * there, or a colour claiming a side nothing established.
 *
 * Every one of them fails *silently*.  A tracer drawn from the killer's current
 * position instead of the kill instant is still a line between two players and
 * still looks like a shot; it is simply about a moment that never happened.
 */

import { describe, expect, it } from "vitest";

import type { Replay } from "../api/types";
import type { ReplayModel } from "../model/replay";
import { stateAt } from "../model/state";
import type { Position, Track } from "../model/track";
import { FADE_MS, FLIGHT_MS, HOLD_MS, flightAlpha, flightProgress, tracersAt } from "./tracers";

const KILL_MS = 15_000;

function sample(tMs: number, actorId: number, x: number): Position {
  return { t_ms: tMs, actor_id: actorId, x, y: x * 2, z: 0, yaw: 0, pitch: 0 };
}

/**
 * Two samples, half a second apart.
 *
 * Close enough that `trackAt` interpolates between them rather than refusing,
 * which is what makes "the kill instant, not the playhead" an assertion with
 * two different answers rather than one answer twice.
 */
function track(actorId: number, atKill: number, later: number): Track {
  return {
    actor_id: actorId,
    samples: [sample(KILL_MS, actorId, atKill), sample(KILL_MS + 500, actorId, later)],
  };
}

function player(actorId: number, team: string) {
  return {
    actor_id: actorId,
    team,
    known_team: true,
    label: `${team}1`,
    merged_from: [],
    codename: "Hunter",
    agent: "Sova",
    identity: "Sova",
    display: "Sova",
    icon_url: null,
    portrait_url: null,
    role_icon_url: null,
    role: "",
    abilities: [],
  };
}

const REPLAY: Replay = {
  id: "abc123",
  source: "Demos/match.vrf",
  match_id: "m-1",
  build: "++Ares-Core+release-12.10",
  recorded_utc: "2026-08-21T18:02:00Z",
  length_ms: 60_000,
  side_swap_ms: null,
  map_path: "/Game/Maps/Triad/Triad",
  map_name: "Haven",
  map_name_source: "built-in table",
  map_key: "Haven",
  players: [player(1, "A"), player(2, "B")],
  rounds: [
    {
      number: 1,
      index: 0,
      start_ms: 0,
      end_ms: 60_000,
      duration_ms: 60_000,
      buy_phase_ms: 45_000,
      action_start_ms: 45_000,
      winner: "A",
      reason: "wipe",
      decided: true,
    },
  ],
  kills: [{ t_ms: KILL_MS, killer: 1, victim: 2, round_no: 1, is_suicide: false }],
  ultimates: [],
  spike: [],
  loadouts: [],
  ability_casts: [],
  event_times: [KILL_MS],
  score: [1, 0],
  has_positions: true,
  has_abilities: false,
  positions_available: true,
  positions_note: "positions decode on this build",
  position_source: "decoded",
  catalog_source: "",
  notes: [],
  catalog_notes: [],
};

function modelWith(replay: Replay, tracks: Track[]): ReplayModel {
  return {
    replay,
    positions: new Map(tracks.map((one) => [one.actor_id, one])),
    abilityTracks: new Map(),
  };
}

/** Both players moving between the kill and the instant being watched. */
function shotModel(replay: Replay = REPLAY): ReplayModel {
  return modelWith(replay, [track(1, 100, 900), track(2, 200, 1000)]);
}

describe("tracersAt", () => {
  it("reads both ends at the kill instant, not at the playhead", () => {
    const model = shotModel();
    // 200ms after the shot, by which point `trackAt` has both players 40% of
    // the way to their next sample.
    const [tracer] = tracersAt(model, stateAt(model, KILL_MS + 200));

    expect(tracer).toBeDefined();
    expect(tracer!.from.x).toBe(100);
    expect(tracer!.to.x).toBe(200);
  });

  it("colours by the killer's side, and follows the swap", () => {
    const before = shotModel();
    expect(tracersAt(before, stateAt(before, KILL_MS))[0]!.side).toBe("ATK");

    // The same kill by the same team, after the sides have changed hands.
    const after = shotModel({ ...REPLAY, side_swap_ms: 1_000 });
    expect(tracersAt(after, stateAt(after, KILL_MS))[0]!.side).toBe("DEF");
  });

  it("claims no side for a killer in no roster", () => {
    const orphan: Replay = { ...REPLAY, players: [player(2, "B")] };
    const model = shotModel(orphan);

    expect(tracersAt(model, stateAt(model, KILL_MS))[0]!.side).toBeNull();
  });

  it("draws nothing for a suicide, because there is no shooter", () => {
    const replay: Replay = {
      ...REPLAY,
      kills: [{ t_ms: KILL_MS, killer: 2, victim: 2, round_no: 1, is_suicide: true }],
    };
    const model = shotModel(replay);

    expect(tracersAt(model, stateAt(model, KILL_MS))).toEqual([]);
  });

  it("draws nothing where either track refused", () => {
    const noKiller = modelWith(REPLAY, [track(2, 200, 1000)]);
    expect(tracersAt(noKiller, stateAt(noKiller, KILL_MS))).toEqual([]);

    const noVictim = modelWith(REPLAY, [track(1, 100, 900)]);
    expect(tracersAt(noVictim, stateAt(noVictim, KILL_MS))).toEqual([]);
  });

  it("is on screen before its own kill, and lands exactly on it", () => {
    const model = shotModel();

    // The muzzle. This is the deliberate exception in this layer: the victim
    // is alive here and the bullet is already on its way to them.
    const muzzle = tracersAt(model, stateAt(model, KILL_MS - FLIGHT_MS));
    expect(muzzle).toHaveLength(1);
    expect(muzzle[0]!.progress).toBe(0);

    // Halfway.
    expect(
      tracersAt(model, stateAt(model, KILL_MS - FLIGHT_MS / 2))[0]!.progress,
    ).toBeCloseTo(0.5);

    // And the impact is exact rather than nearly: the pixel suite steps to an
    // `event_times` entry, which is this millisecond, and photographs the
    // whole line.
    expect(tracersAt(model, stateAt(model, KILL_MS))[0]!.progress).toBe(1);
  });

  it("draws nothing outside its window, on either side", () => {
    const model = shotModel();

    expect(tracersAt(model, stateAt(model, KILL_MS - FLIGHT_MS - 1))).toEqual([]);
    expect(tracersAt(model, stateAt(model, KILL_MS + HOLD_MS + FADE_MS))).toEqual([]);
    expect(tracersAt(model, stateAt(model, KILL_MS + HOLD_MS + FADE_MS - 1))).toHaveLength(1);
  });

  it("holds the whole line before it fades", () => {
    const model = shotModel();
    // Landed, and still growing no further: `progress` is clamped, so the hold
    // draws the line to the victim rather than past them.
    const held = tracersAt(model, stateAt(model, KILL_MS + HOLD_MS))[0]!;
    expect(held.progress).toBe(1);
    expect(held.alpha).toBe(1);
  });
});

describe("the flight", () => {
  it("runs from the muzzle to the impact, and stops at both", () => {
    expect(flightProgress(-FLIGHT_MS)).toBe(0);
    expect(flightProgress(0)).toBe(1);
    // Before the muzzle and after the impact are both clamped rather than
    // extrapolated -- a bullet past the victim is a path nobody took.
    expect(flightProgress(-FLIGHT_MS - 500)).toBe(0);
    expect(flightProgress(500)).toBe(1);
  });

  it("is at full ink until the hold is over, then fades to nothing", () => {
    expect(flightAlpha(-FLIGHT_MS)).toBe(1);
    expect(flightAlpha(0)).toBe(1);
    expect(flightAlpha(HOLD_MS)).toBe(1);
    expect(flightAlpha(HOLD_MS + FADE_MS)).toBe(0);
    // Faster at the end than at the start, which is what keeps the shot
    // reading as a flash rather than as a line being wiped off.
    expect(flightAlpha(HOLD_MS + FADE_MS / 2)).toBeGreaterThan(0.5);
  });
});
