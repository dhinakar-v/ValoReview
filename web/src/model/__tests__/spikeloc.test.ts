/**
 * Where the planted spike is, and the three ways there is no answer.
 *
 * `spikeLocation` is the whole of what puts a spike on either canvas, and every
 * one of its refusals looks from the outside like a round in which nobody
 * planted.  That is the failure this project keeps naming: a marker that is
 * computed, laid out and then drawn nowhere is indistinguishable from a marker
 * that was never wanted.  So each refusal is pinned by name here --
 *
 *   * the spike is not down (`spikeState` is anything else),
 *   * the plant is in a round that has ended, because nothing carries over, and
 *   * the plant has no coordinate at all, which is every capture whose sidecar
 *     predates version 4 and is a real state rather than a corrupt one.
 *
 * `web/e2e/minimap.spec.ts` checks that the coordinate reaches the pixels; this
 * checks the arithmetic that hands it over, in a millisecond and with no server.
 */

import { describe, expect, it } from "vitest";

import type { Replay } from "../../api/types";
import type { ReplayModel } from "../replay";
import { spikeLocation, stateAt } from "../state";

/**
 * Two rounds and two plants: one located, one not.
 *
 * Round 2's plant carries `x`/`y`/`z` of null the way a version 1 to 3 sidecar
 * leaves them -- `positionfile` stores a spawn whose transform is unknown as
 * fewer fields rather than as three zeros, because defaulting it would put the
 * spike on the map's origin.
 */
const REPLAY = {
  id: "id",
  source: "x.vrf",
  match_id: "m",
  build: "b",
  recorded_utc: "",
  length_ms: 300_000,
  side_swap_ms: null,
  map_path: "/Game/Maps/Triad/Triad",
  map_name: "Haven",
  map_name_source: "",
  map_key: "Haven",
  players: [],
  rounds: [
    {
      number: 1,
      index: 0,
      start_ms: 0,
      end_ms: 100_000,
      duration_ms: 100_000,
      winner: "A",
      reason: "wipe",
      decided: true,
    },
    {
      number: 2,
      index: 1,
      start_ms: 100_000,
      end_ms: 200_000,
      duration_ms: 100_000,
      winner: "B",
      reason: "wipe",
      decided: true,
    },
  ],
  kills: [],
  ultimates: [],
  spike: [
    { t_ms: 50_000, kind: "planted", round_no: 1, x: 1000, y: 2000, z: 300 },
    { t_ms: 150_000, kind: "planted", round_no: 2, x: null, y: null, z: null },
  ],
  loadouts: [],
  ability_casts: [],
  event_times: [50_000, 150_000],
  score: [1, 1],
  has_positions: false,
  has_abilities: false,
  positions_available: true,
  positions_note: "",
  position_source: "",
  catalog_source: "",
  notes: [],
  catalog_notes: [],
} as unknown as Replay;

const MODEL: ReplayModel = {
  replay: REPLAY,
  positions: new Map(),
  abilityTracks: new Map(),
};

describe("spikeLocation", () => {
  it("is null before the plant", () => {
    expect(spikeLocation(MODEL, stateAt(MODEL, 49_000))).toBeNull();
  });

  it("is the plant coordinate at the plant instant", () => {
    const snap = stateAt(MODEL, 50_000);
    expect(snap.spikeState).toBe("planted");
    expect(snap.spikeSinceMs).toBe(50_000);
    expect(spikeLocation(MODEL, snap)).toEqual({ x: 1000, y: 2000, z: 300 });
  });

  it("is still the plant coordinate later in the round", () => {
    expect(spikeLocation(MODEL, stateAt(MODEL, 70_000))).toEqual({
      x: 1000,
      y: 2000,
      z: 300,
    });
  });

  it("does not carry the plant into the next round", () => {
    expect(spikeLocation(MODEL, stateAt(MODEL, 120_000))).toBeNull();
  });

  it("refuses a plant that has no coordinate rather than inventing one", () => {
    const snap = stateAt(MODEL, 150_000);
    expect(snap.spikeState, "the round still knows the spike is down").toBe("planted");
    expect(spikeLocation(MODEL, snap)).toBeNull();
  });
});
