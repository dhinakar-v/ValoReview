/**
 * Which cones exist, and how much ink each one gets.
 *
 * Both halves are silent failures, which is why they are pinned here rather
 * than left to the pixel suite.  A cone drawn for a dead player, or for a side
 * whose markers are hidden, is an extra wedge on a busy canvas that nobody
 * counts; a denominator that drifts is a wash that is merely a bit darker than
 * it was.  Neither throws, and neither shows up in a screenshot as a fault.
 *
 * The compositing itself is deliberately *not* tested here: jsdom has no 2D
 * context, so `paintCones` cannot run at all.  That is what
 * `e2e/minimap.spec.ts` and `e2e/scene.spec.ts` are for -- each samples the
 * cones the model predicts and compares them against the same cones turned.
 */

import { describe, expect, it } from "vitest";

import type { MapArt, Replay } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { SightMask, SightSettings } from "../model/sight";
import type { Snapshot } from "../model/state";
import { SIGHT_MIN_DENOM, coneAlpha, sightCones } from "./sightlayer";

/** Wide open: every ray runs to its full radius and every cone is a full fan. */
const OPEN: SightMask = { size: 8, cells: new Uint8Array(8 * 8).fill(1) };

const SETTINGS: SightSettings = {
  max_range_uu: 2000,
  fov_degrees: 103,
  ray_step_degrees: 2,
  seed_cells: 2,
  probe_uu: 100,
};

const ART = {
  transform: {
    x_multiplier: 0.0001,
    y_multiplier: -0.0001,
    x_scalar: 0.5,
    y_scalar: 0.5,
    vertical_scale: 0.0001,
    usable: true,
  },
} as unknown as MapArt;

/** Five a side, so a full team is exactly `SIGHT_MIN_DENOM` cones. */
function model(): ReplayModel {
  const players = [];
  for (let i = 0; i < 10; i += 1) {
    players.push({ actor_id: i, team: i < 5 ? "A" : "B" });
  }
  return {
    replay: { players, side_swap_ms: null } as unknown as Replay,
  } as unknown as ReplayModel;
}

/** Everyone alive and spread out, unless `only` names who lives. */
function snapshot(only?: number[]): Snapshot {
  const ids = only ?? [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
  const positions = new Map<number, { x: number; y: number; z: number; yaw: number }>();
  for (const id of ids) {
    positions.set(id, { x: id * 100, y: id * 100, z: 0, yaw: 45 });
  }
  return {
    t_ms: 1000,
    alive: new Set(ids),
    positions,
    roundCasts: [],
  } as unknown as Snapshot;
}

const all = () => true;

function cones(snap: Snapshot, shown: (team: string) => boolean = all) {
  return sightCones({
    model: model(),
    art: ART,
    snap,
    silhouette: OPEN,
    settings: SETTINGS,
    shown,
    smokes: [],
  });
}

describe("which players get a cone", () => {
  it("draws one for every living player, with nobody selected", () => {
    // The whole point of the layer: no click, no hover, ten cones.
    expect(cones(snapshot())).toHaveLength(10);
  });

  it("draws none for the dead", () => {
    // `snap.positions`, not `positionOf` -- a cone at a corpse would be a claim
    // about a dead player's vision, and `positionOf` falls back to where they
    // fell precisely so the death mark can be drawn there.
    expect(cones(snapshot([0, 1, 2]))).toHaveLength(3);
  });

  it("draws none for a player the snapshot cannot place", () => {
    const snap = snapshot();
    snap.positions.delete(4);
    expect(cones(snap)).toHaveLength(9);
  });

  it("obeys the same hidden-team gate the markers do", () => {
    // A side drawing a cone but no marker would be a new way for the two to
    // disagree, and it is exactly what `Scene3D` used to do.
    const drawn = cones(snapshot(), (team) => team === "A");
    expect(drawn).toHaveLength(5);
    expect(new Set(drawn.map((entry) => entry.side))).toEqual(new Set(["ATK"]));
  });

  it("colours by side rather than by team", () => {
    const drawn = cones(snapshot());
    const sides = drawn.map((entry) => entry.side);
    expect(sides.filter((side) => side === "ATK")).toHaveLength(5);
    expect(sides.filter((side) => side === "DEF")).toHaveLength(5);
  });

  it("returns a polygon that is a fan about the player, apex first", () => {
    const [first] = cones(snapshot([0]));
    // One apex plus one point per ray, so a canvas can fill it directly.
    expect(first!.polygon.length).toBeGreaterThan(3);
  });
});

describe("how much ink one cone gets", () => {
  it("splits a full side's opacity evenly, so five overlapping reach 100%", () => {
    expect(coneAlpha(5)).toBeCloseTo(0.2, 10);
    expect(coneAlpha(5) * 5).toBeCloseTo(1, 10);
  });

  it("never lets a thinning side darken, so a lone survivor is not opaque", () => {
    /*
      Without the floor N is the live count, so the last player alive would be
      1/1 -- a solid wedge with the radar gone underneath it, arriving exactly
      when somebody is watching a clutch most closely.
    */
    for (const alive of [1, 2, 3, 4, 5]) {
      expect(coneAlpha(alive)).toBeCloseTo(1 / SIGHT_MIN_DENOM, 10);
    }
  });

  it("keeps thinning past a full side, so overlap can still reach 100%", () => {
    // Above the floor the denominator is the real count again: N cones over
    // one point is always full opacity, whatever N is.
    expect(coneAlpha(8)).toBeCloseTo(0.125, 10);
    expect(coneAlpha(8) * 8).toBeCloseTo(1, 10);
  });

  it("never exceeds full opacity, however many cones overlap", () => {
    for (const count of [1, 2, 5, 10, 20]) {
      expect(coneAlpha(count) * count).toBeLessThanOrEqual(1);
    }
  });
});
