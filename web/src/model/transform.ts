/**
 * World coordinates onto the radar image.  A port of `art.Transform.apply`.
 *
 * **The x and y inputs are swapped, and that is measured rather than assumed.**
 * Running all 346 callouts in `assets/manifest.json` through the unswapped form
 * lands 200 of them inside the image; through this form, 346 of 346.  The
 * unswapped version does not crash and does not look obviously broken -- it
 * produces a plausible wrong answer -- so it is pinned by a test on both sides
 * of the wire: `tests/golden/transform.json` and `tests/test_vrfview.py`.
 *
 * Everything downstream works in uv, because uv is the one space where the
 * picture and the positions already agree.  Angles, however, are never computed
 * in it: see `forwardUv` in `./sight`.
 */

import type { Transform } from "../api/types";

/** One world coordinate as a (u, v) fraction of minimap.png, both 0..1. */
export function applyTransform(
  transform: Transform,
  worldX: number,
  worldY: number,
): [u: number, v: number] {
  return [
    worldY * transform.x_multiplier + transform.x_scalar_to_add,
    worldX * transform.y_multiplier + transform.y_scalar_to_add,
  ];
}

/**
 * The largest square a box of this size can hold, less a margin, centred.
 *
 * A port of `minimap._place_image`.  The radar is square and the panel is not,
 * so everything drawn on it is placed relative to this box rather than to the
 * canvas -- and the margin is there so a player standing on the very edge of
 * the map is not clipped by the border.
 */
export interface Box {
  left: number;
  top: number;
  side: number;
}

export const MARGIN = 10;

export function placeSquare(width: number, height: number, margin = MARGIN): Box {
  const side = Math.max(64, Math.min(width, height) - 2 * margin);
  return { left: (width - side) / 2, top: (height - side) / 2, side };
}

/** A uv fraction as a point inside a placed square. */
export function uvToPixels(box: Box, u: number, v: number): [x: number, y: number] {
  return [box.left + u * box.side, box.top + v * box.side];
}
