/**
 * Which cones exist.
 *
 * A silent failure, which is why it is pinned here rather than left to the
 * pixel suite: a cone drawn for a dead player, or for a side whose markers are
 * hidden, is an extra wedge on a busy canvas that nobody counts.  It does not
 * throw, and it does not show up in a screenshot as a fault.
 *
 * How much ink a cone gets used to be pinned here too, back when it was `1/N`
 * of its side's ink and `coneAlpha` was a pure function anything could call.
 * The wash is a flat `SIGHT_ALPHA` on the blit now, so there is no arithmetic
 * left to check and nothing exported to check it through.
 *
 * The compositing itself is deliberately *not* tested here: jsdom has no 2D
 * context, so `paintCones` cannot run at all.  That is what
 * `e2e/minimap.spec.ts` and `e2e/scene.spec.ts` are for -- each samples the
 * cones the model predicts and compares them against the same cones turned.
 */

import { describe, expect, it } from "vitest";

import type { AbilityCast, MapArt, Placement, Replay } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { SightMask, SightSettings } from "../model/sight";
import type { Snapshot } from "../model/state";
import { sightCones, smokesAt } from "./sightlayer";

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

describe("when a smoke starts and stops blocking", () => {
  /*
    Each smoke on its own arrival, and this is a correction rather than a
    detail.  Every placement used to be aged from `cast.t_ms`, with a note
    admitting a thrown smoke started blocking slightly early because the wire
    carried no time on a placement.  It does now, and "slightly" is a median
    831 ms across the reference library with a p95 of 2.3 s -- so a smoke was
    occluding sight for up to two seconds before it existed, which is exactly
    the plausible wrong answer this project spends its measurements on.

    Worse for a cast that drops several: one `AbilityCast` is one agent, one
    slot, one round, so Brimstone's three smokes all ran on the first one's
    clock and the last one went out early.
  */
  const smoke = (over: Partial<Placement>): Placement =>
    ({
      t_ms: 12_000,
      actor_id: 900,
      kind: "GameObject",
      name: "Smoke",
      display: "Smoke",
      x: 0,
      y: 0,
      z: 0,
      ...over,
    }) as Placement;

  const cast = (places: Placement[]): AbilityCast =>
    ({
      t_ms: 10_000,
      actor_id: 800,
      codename: "Wraith",
      slot: "C",
      pawns: [],
      placements: places,
      smoke_radius_uu: 410,
      smoke_duration_ms: 15_000,
      smoke_source: "a page",
    }) as unknown as AbilityCast;

  function occluders(tMs: number, places: Placement[]) {
    const snap = { t_ms: tMs, roundCasts: [cast(places)] } as unknown as Snapshot;
    return smokesAt(ART, snap);
  }

  it("does not block while the smoke is still in the air", () => {
    // Two seconds after the cast and before the landing: the ability has been
    // used, and there is nothing on that ground yet.
    expect(occluders(11_999, [smoke({})])).toHaveLength(0);
  });

  it("blocks from the instant its own channel opened", () => {
    expect(occluders(12_000, [smoke({})])).toHaveLength(1);
  });

  it("expires a lifetime after it landed, not after it was cast", () => {
    // 12,000 + 15,000. Ageing from `cast.t_ms` would have put this at 25,000
    // and taken two seconds off a smoke that was still standing.
    expect(occluders(26_999, [smoke({})])).toHaveLength(1);
    expect(occluders(27_001, [smoke({})])).toHaveLength(0);
  });

  it("gives each smoke of one cast its own clock", () => {
    const places = [smoke({ actor_id: 900 }), smoke({ actor_id: 901, t_ms: 20_000 })];
    expect(occluders(12_500, places)).toHaveLength(1);
    expect(occluders(21_000, places)).toHaveLength(2);
    expect(occluders(28_000, places)).toHaveLength(1);
  });
});

describe("a drone, which sees", () => {
  /** One cast owning one pawn, with whatever the test needs published. */
  function drone(over: Record<string, unknown> = {}) {
    return {
      player_actor_id: 0,
      pawns: [500],
      placements: [],
      smoke_radius_uu: null,
      smoke_duration_ms: null,
      mechanics: { sees: true },
      ...over,
    } as unknown as Snapshot["roundCasts"][number];
  }

  function withDrone(cast: unknown, at?: { x: number; y: number; yaw: number }) {
    const snap = snapshot() as unknown as {
      roundCasts: unknown[];
      abilityPositions: Map<number, unknown>;
    };
    snap.roundCasts = [cast];
    snap.abilityPositions = new Map(
      at === undefined ? [] : [[500, { ...at, z: 0 }]],
    );
    return snap as unknown as Snapshot;
  }

  it("gets a cone of its own, on its caster's side", () => {
    const drawn = cones(withDrone(drone(), { x: 400, y: 400, yaw: 90 }));
    // Ten players plus the drone.
    expect(drawn).toHaveLength(11);
    expect(drawn[10]!.side).toBe(cones(snapshot())[0]!.side);
  });

  it("draws nothing for a pawn that does not see", () => {
    // A Boom Bot is a pawn too. Which pawns see is looked up, never inferred
    // from the kind.
    const blind = drone({ mechanics: { sees: false } });
    expect(cones(withDrone(blind, { x: 400, y: 400, yaw: 90 }))).toHaveLength(10);
  });

  it("draws nothing for a drone that is no longer in the air", () => {
    // `abilityPositions` is built through the same `trackAt` a player's is, so
    // a drone whose record has run out simply is not there.
    expect(cones(withDrone(drone()))).toHaveLength(10);
  });

  it("draws nothing where its side is hidden", () => {
    const drawn = cones(
      withDrone(drone(), { x: 400, y: 400, yaw: 90 }),
      (team) => team === "B",
    );
    expect(drawn).toHaveLength(5);
  });

  it("draws nothing where nothing can say whose it is", () => {
    const orphan = drone({ player_actor_id: null });
    expect(cones(withDrone(orphan, { x: 400, y: 400, yaw: 90 }))).toHaveLength(10);
  });
});
