/**
 * The 3D scene's ground reference, and the coordinate that is not a place.
 *
 * `floorZ` is the one piece of the model with no Python counterpart -- the
 * desktop viewer never drew a height -- so `tests/golden/` cannot pin it and
 * this does instead.
 *
 * It is here because taking the raw minimum shipped, and the consequence was
 * that four of the twenty-one playable captures drew **no players at all** in
 * the 3D scene: the replication stream parks an out-of-play actor about 50,000
 * uu below the map, so every marker was lifted three and a half map-widths out
 * of frame while the ground rendered perfectly underneath.  It looked like a
 * quiet map, not like a fault.  `web/e2e/scene.spec.ts` catches it in a real
 * browser; this catches it in a millisecond.
 */

import { describe, expect, it } from "vitest";

import type { Replay } from "../../api/types";
import { OFF_WORLD_DROP_UU, buildModel, floorZ } from "../replay";
import type { Columns, PositionsDoc } from "../replay";

/** The only two fields of a replay this reads. */
const REPLAY = { players: [], length_ms: 0, position_source: "" } as unknown as Replay;

function columns(zs: number[]): Columns {
  return {
    t: zs.map((_, i) => i * 100),
    x: zs.map(() => 0),
    y: zs.map(() => 0),
    z: zs,
    yaw: zs.map(() => 0),
    pitch: zs.map(() => 0),
  };
}

function model(tracks: Record<string, number[]>) {
  const doc = {
    tracks: Object.fromEntries(
      Object.entries(tracks).map(([id, zs]) => [id, columns(zs)]),
    ),
    ability_tracks: {},
    position_source: "",
  } as unknown as PositionsDoc;
  return buildModel(REPLAY, doc);
}

describe("floorZ", () => {
  it("is the lowest sample when every sample is a place", () => {
    expect(floorZ(model({ "1": [400, 200, 650], "2": [-25, 300] }))).toBe(-25);
  });

  it("ignores the coordinate an out-of-play actor is parked at", () => {
    // The shape of a real capture: a match lived between -4.5 and 1083, and
    // 310 of its 148,482 samples -- about a fifth of one percent -- sat at
    // -49,919.64. The proportion matters, because the median is what the
    // threshold is measured from.
    const played: number[] = [];
    for (let i = 0; i < 200; i += 1) {
      played.push([400.3, 200.1, -4.5, 1082.93, 500.5][i % 5]!);
    }
    const parked = new Array(2).fill(-49919.64);
    expect(floorZ(model({ "1": [...played, ...parked], "2": played }))).toBe(-4.5);
  });

  it("keeps a sample that is merely low, which the deepest real one is", () => {
    // The deepest legitimate sample measured across the library is 1,025.7 uu
    // below its capture's median, so the threshold has to leave that alone.
    const zs = [650.3, 650.3, 650.3, 650.3, 650.3, -375.4];
    expect(floorZ(model({ "1": zs }))).toBe(-375.4);
    expect(650.3 - -375.4).toBeLessThan(OFF_WORLD_DROP_UU);
  });

  it("is zero when there is nothing decoded, rather than infinite", () => {
    expect(floorZ(model({}))).toBe(0);
    expect(floorZ(buildModel(REPLAY, null))).toBe(0);
  });
});
