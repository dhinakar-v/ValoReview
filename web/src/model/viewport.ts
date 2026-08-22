/**
 * Zoom and pan over the radar, as a transform on the placed square.
 *
 * `model/transform.ts` is not touched by any of this, and that is the point.
 * `applyTransform`, `placeSquare` and `uvToPixels` are compared against
 * `tests/golden/transform.json` in two languages; a viewport that reached into
 * them would put a camera inside a contract about coordinates.  So the camera
 * lives here instead and produces a `Box` -- the same shape `placeSquare`
 * returns -- which everything downstream consumes without knowing it moved.
 *
 * Pan is held in **uv**, not in pixels.  A pan measured in pixels changes
 * meaning when the window resizes: the same drag would move the map further on
 * a small canvas than on a large one, and a zoomed view would jump on every
 * layout change.  In uv it is a fraction of the map, which is what the user
 * actually chose.
 *
 * `FIT` is the identity, and every default in the interface is `FIT` -- which
 * is what keeps `e2e/minimap.spec.ts`'s pixel arithmetic valid: at rest, the
 * geometry is bit-identical to a build with no viewport at all.
 */

import type { Box } from "./transform";

export interface Viewport {
  /** 1 fits the map to the box; 8 is the closest this allows. */
  scale: number;
  /** Where the centre of the view sits, in uv. 0.5, 0.5 is the map's middle. */
  panU: number;
  panV: number;
}

export const MIN_SCALE = 1;
export const MAX_SCALE = 8;

export const FIT: Viewport = { scale: 1, panU: 0.5, panV: 0.5 };

/** Whether a viewport is the untouched one, which is worth saying in the UI. */
export function isFit(vp: Viewport): boolean {
  return vp.scale === FIT.scale && vp.panU === FIT.panU && vp.panV === FIT.panV;
}

/**
 * Keep the view over the map.
 *
 * The centre is held inside the half-window the current scale leaves, so the
 * map's edge can reach the middle of the canvas but not cross it.  At scale 1
 * that collapses to exactly 0.5 on both axes, which is why `FIT` survives a
 * clamp unchanged and why a wheel-out always lands back on the identity rather
 * than near it.
 */
export function clamp(vp: Viewport): Viewport {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, vp.scale));
  const half = 0.5 / scale;
  const fix = (value: number) => Math.min(1 - half, Math.max(half, value));
  return { scale, panU: fix(vp.panU), panV: fix(vp.panV) };
}

/**
 * The square to draw into, given the square the canvas would otherwise use.
 *
 * The box grows by `scale` and is offset so that `panU, panV` lands in the
 * middle of the original box.  Everything that was drawn through `uvToPixels`
 * keeps working, because a uv fraction of a larger, shifted square is exactly
 * what a zoomed map is.
 */
export function viewBox(box: Box, vp: Viewport): Box {
  const side = box.side * vp.scale;
  const centreX = box.left + box.side / 2;
  const centreY = box.top + box.side / 2;
  return {
    left: centreX - vp.panU * side,
    top: centreY - vp.panV * side,
    side,
  };
}

/** The uv coordinate under a point in canvas pixels, for the current view. */
export function uvAt(box: Box, vp: Viewport, x: number, y: number): [number, number] {
  const view = viewBox(box, vp);
  return [(x - view.left) / view.side, (y - view.top) / view.side];
}

/**
 * Zoom by `factor` about a point in canvas pixels, holding that point still.
 *
 * Holding the cursor's own uv fixed is the whole reason this is arithmetic
 * rather than a scale multiply: zooming about the centre while the pointer is
 * near an edge walks the thing under the pointer off the screen, which reads
 * as the map fighting the mouse.
 */
export function zoomAt(
  box: Box,
  vp: Viewport,
  x: number,
  y: number,
  factor: number,
): Viewport {
  const [u, v] = uvAt(box, vp, x, y);
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, vp.scale * factor));
  // Where the pointer sits inside the box, 0..1 -- the fraction that has to
  // keep resolving to the same uv after the scale changes.
  const fx = (x - box.left) / box.side;
  const fy = (y - box.top) / box.side;
  return clamp({
    scale,
    panU: u - (fx - 0.5) / scale,
    panV: v - (fy - 0.5) / scale,
  });
}

/** Drag by a pixel delta, which is a uv delta once divided by the view side. */
export function panBy(box: Box, vp: Viewport, dx: number, dy: number): Viewport {
  const side = box.side * vp.scale;
  return clamp({ scale: vp.scale, panU: vp.panU - dx / side, panV: vp.panV - dy / side });
}

/**
 * How much larger to draw a marker at this zoom.
 *
 * Markers scale with the map -- the reference frames show a 26px marker at fit
 * and roughly 40px at 2.5x -- but not without bound: at 8x an unbounded marker
 * is a portrait the size of a site, and the point of zooming in is to separate
 * players standing on top of each other.
 */
export const MAX_MARKER_SCALE = 2.2;

export function markerScale(vp: Viewport): number {
  return Math.min(MAX_MARKER_SCALE, Math.sqrt(vp.scale));
}
