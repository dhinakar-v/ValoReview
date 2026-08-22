/**
 * The camera over the radar.
 *
 * Two of these are about a promise made to another test suite rather than about
 * the arithmetic itself.  `e2e/minimap.spec.ts` computes where every marker
 * should be from `placeSquare` alone and then looks there; that stays valid
 * only because the default viewport is the exact identity, not something very
 * close to it.  So `FIT` is asserted to leave a box untouched, and a clamp is
 * asserted to leave `FIT` alone -- a clamp that nudged it by a float would move
 * every marker by a fraction of a pixel and fail a suite two directories away.
 */

import { describe, expect, it } from "vitest";

import type { Box } from "../transform";
import {
  FIT,
  MAX_SCALE,
  MIN_SCALE,
  clamp,
  isFit,
  markerScale,
  panBy,
  uvAt,
  viewBox,
  zoomAt,
} from "../viewport";

const BOX: Box = { left: 30, top: 10, side: 400 };

describe("the untouched view", () => {
  it("is the identity, exactly", () => {
    const view = viewBox(BOX, FIT);
    expect(view.left).toBe(BOX.left);
    expect(view.top).toBe(BOX.top);
    expect(view.side).toBe(BOX.side);
  });

  it("survives a clamp unchanged", () => {
    expect(clamp(FIT)).toEqual(FIT);
    expect(isFit(clamp(FIT))).toBe(true);
  });

  it("puts the middle of the map in the middle of the box", () => {
    expect(uvAt(BOX, FIT, BOX.left + BOX.side / 2, BOX.top + BOX.side / 2)).toEqual([
      0.5, 0.5,
    ]);
  });
});

describe("zooming", () => {
  it("holds the point under the cursor still", () => {
    const x = BOX.left + 90;
    const y = BOX.top + 320;
    const before = uvAt(BOX, FIT, x, y);
    const after = uvAt(BOX, zoomAt(BOX, FIT, x, y, 2.5), x, y);
    expect(after[0]).toBeCloseTo(before[0], 10);
    expect(after[1]).toBeCloseTo(before[1], 10);
  });

  it("holds it still again from an already-zoomed view", () => {
    const start = zoomAt(BOX, FIT, BOX.left + 120, BOX.top + 120, 3);
    const x = BOX.left + 260;
    const y = BOX.top + 80;
    const before = uvAt(BOX, start, x, y);
    const after = uvAt(BOX, zoomAt(BOX, start, x, y, 1.6), x, y);
    expect(after[0]).toBeCloseTo(before[0], 10);
    expect(after[1]).toBeCloseTo(before[1], 10);
  });

  it("stops at both ends of the range", () => {
    const centre = BOX.left + BOX.side / 2;
    let vp = FIT;
    for (let i = 0; i < 40; i += 1) {
      vp = zoomAt(BOX, vp, centre, centre, 2);
    }
    expect(vp.scale).toBe(MAX_SCALE);
    for (let i = 0; i < 40; i += 1) {
      vp = zoomAt(BOX, vp, centre, centre, 0.5);
    }
    expect(vp.scale).toBe(MIN_SCALE);
  });

  it("comes all the way back to the identity, not near it", () => {
    const centre = BOX.left + BOX.side / 2;
    let vp = zoomAt(BOX, FIT, centre, centre, 4);
    vp = zoomAt(BOX, vp, centre, centre, 0.25);
    expect(isFit(vp)).toBe(true);
  });
});

describe("panning", () => {
  it("does nothing at fit, because there is nowhere to go", () => {
    expect(panBy(BOX, FIT, 120, -80)).toEqual(FIT);
  });

  it("moves the map with the drag", () => {
    const zoomed = { scale: 4, panU: 0.5, panV: 0.5 };
    // Dragging right shows what was to the left, so the centre moves left.
    expect(panBy(BOX, zoomed, 40, 0).panU).toBeLessThan(zoomed.panU);
    expect(panBy(BOX, zoomed, 0, 40).panV).toBeLessThan(zoomed.panV);
  });

  it("keeps the view over the map", () => {
    const vp = panBy(BOX, { scale: 2, panU: 0.5, panV: 0.5 }, 10_000, 10_000);
    expect(vp.panU).toBeGreaterThanOrEqual(0.25);
    expect(vp.panU).toBeLessThanOrEqual(0.75);
    expect(vp.panV).toBeGreaterThanOrEqual(0.25);
    expect(vp.panV).toBeLessThanOrEqual(0.75);
  });
});

describe("marker sizes", () => {
  it("are unchanged at rest", () => {
    expect(markerScale(FIT)).toBe(1);
  });

  it("grow with the map but not without bound", () => {
    expect(markerScale({ ...FIT, scale: 4 })).toBeGreaterThan(1);
    // The point of zooming in is to separate people standing on each other, so
    // a marker the size of a site would defeat the exercise.
    expect(markerScale({ ...FIT, scale: MAX_SCALE })).toBeLessThanOrEqual(2.2);
  });
});
