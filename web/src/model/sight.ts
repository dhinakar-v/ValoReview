/**
 * The approximate sight cone, raycast against the radar's own silhouette.
 *
 * A port of `vrfview.sight`.  This project has
 * no collision data, no navmesh and no height information anywhere: a map is a
 * radar PNG, four transform scalars and a list of point callouts, and that is
 * the entire spatial model.  What it does have is a measurement -- the area
 * outside the playable space in every published `minimap.png` is fully
 * transparent, 57% of Abyss and 72% of Bind -- so marching a ray until it
 * leaves that silhouette gives an occluder that is measured rather than
 * invented.
 *
 * The contract is narrow, and everything drawn from it is an approximation:
 * transparent means outside the rendered radar, which is usually wall or void
 * and is not the same claim as "opaque geometry blocks vision"; it is
 * two-dimensional, so Bind's teleporters read as solid and Split's heaven reads
 * as the floor beneath it; and a doorway narrower than the grid closes.
 *
 * The mask is thresholded in Python
 * ---------------------------------
 * `GRID` and `ALPHA_FLOOR` stay authoritative there, and a browser downscale is
 * not Pillow's, so a mask rebuilt here would differ in its rim by a few cells
 * on every map -- exactly the kind of difference no test could then pin.  This
 * module takes the bytes and does the arithmetic on top of them.
 */

import type { Transform } from "../api/types";
import { radians } from "./angles";
import { applyTransform } from "./transform";

/** One map's playable silhouette: row-major, one byte per cell, 1 open. */
export interface SightMask {
  size: number;
  cells: Uint8Array;
}

/**
 * A round smoke standing in the world, in uv space.
 *
 * In uv rather than world units because that is the space a ray is already
 * marched in, so a smoke is converted once per frame instead of once per step.
 * `radius` is `uvRadius(transform, smoke_radius_uu)`.
 *
 * It carries no time: whether a smoke is still standing is decided by whoever
 * builds the list, so the raycaster stays a pure function of geometry the way
 * the mask is. Mirrors `sight.Occluder`.
 */
export interface Occluder {
  u: number;
  v: number;
  radius: number;
}

/** The constants the server sends beside the cells; `sight.py` decides them. */
export interface SightSettings {
  max_range_uu: number;
  fov_degrees: number;
  ray_step_degrees: number;
  seed_cells: number;
  probe_uu: number;
}

export function decodeMask(size: number, base64Cells: string): SightMask {
  const binary = atob(base64Cells);
  const cells = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    cells[i] = binary.charCodeAt(i);
  }
  return { size, cells };
}

/**
 * Whether the cell at this uv fraction is outside the playable area.
 *
 * **`Math.floor`, not `| 0` and not `Math.trunc`.**  Truncation goes toward
 * zero, so `(-0.8 * size) | 0` is 0 and a ray leaving the left or top edge
 * would silently reappear in column or row zero instead of stopping -- a cone
 * wrapping onto the far side of the image, on any map whose spawn sits near an
 * edge.
 */
export function blocked(mask: SightMask, u: number, v: number): boolean {
  const col = Math.floor(u * mask.size);
  const row = Math.floor(v * mask.size);
  if (!(col >= 0 && col < mask.size && row >= 0 && row < mask.size)) {
    return true;
  }
  return !mask.cells[row * mask.size + col];
}

/**
 * A unit heading in uv space, via a probe point rather than trigonometry.
 *
 * The transform swaps x and y and either multiplier may be negative, so the
 * only form immune to both is to move in world space and transform the result.
 * Doing the trigonometry in uv space directly puts every cone ninety degrees
 * out, which looks entirely plausible on screen -- and is the same trap the
 * facing line on the minimap avoids the same way.
 */
export function forwardUv(
  transform: Transform,
  x: number,
  y: number,
  yaw: number,
  probeUu: number,
): [du: number, dv: number] {
  const angle = radians(yaw);
  const [u0, v0] = applyTransform(transform, x, y);
  const [u1, v1] = applyTransform(
    transform,
    x + probeUu * Math.cos(angle),
    y + probeUu * Math.sin(angle),
  );
  const du = u1 - u0;
  const dv = v1 - v0;
  // `Math.sqrt` on both sides, never `hypot`. Both languages have one, and
  // both specify it as approximate -- CPython's is a correctly-rounded
  // algorithm and V8's is not the same one -- so two implementations of this
  // that both used it would be free to disagree in the last bit. `sqrt` is
  // exactly specified in IEEE-754 and agrees by construction.
  const length = Math.sqrt(du * du + dv * dv);
  if (length <= 0) {
    return [0, 0];
  }
  return [du / length, dv / length];
}

/**
 * A world distance as a fraction of the radar's side.
 *
 * The two multipliers differ slightly on some maps because the radar is not
 * exactly square in world terms, so this averages them: the cone's reach is a
 * bound on an approximation, not a measurement anybody reads off.
 */
export function uvRadius(transform: Transform, distanceUu: number): number {
  const scale = (Math.abs(transform.x_multiplier) + Math.abs(transform.y_multiplier)) / 2;
  return Math.abs(distanceUu) * scale;
}

/**
 * One ray, to the first blocked cell or to `radius`, whichever comes first.
 *
 * Exported so the parity test can march the directions Python marched.  Every
 * step of this is plain IEEE arithmetic -- multiply, add, floor, compare -- so
 * it is comparable across the two languages to the bit, which the directions
 * themselves are not.
 */
export function march(
  mask: SightMask,
  origin: [number, number],
  direction: [number, number],
  radius: number,
  seedCells: number,
  occluders: readonly Occluder[] = [],
): [number, number] {
  const [u0, v0] = origin;
  const [du, dv] = direction;
  const cell = 1 / mask.size;
  const steps = Math.max(1, Math.trunc(radius / cell));
  for (let i = 1; i <= steps; i += 1) {
    const travelled = i * cell;
    const u = u0 + du * travelled;
    const v = v0 + dv * travelled;
    if (i > seedCells && (blocked(mask, u, v) || inside(occluders, u, v))) {
      // Stop on the last open cell, not inside the wall, so the polygon traces
      // the silhouette rather than overlapping it.
      const back = (i - 1) * cell;
      return [u0 + du * back, v0 + dv * back];
    }
  }
  return [u0 + du * radius, v0 + dv * radius];
}

/**
 * Whether this step has walked into a smoke.
 *
 * Squared distance, and that is about parity rather than about speed. `hypot`
 * is approximate by specification in both languages and `sqrt` would be a
 * needless rounding besides; multiply, subtract and compare are exactly
 * specified in IEEE-754, so this agrees with Python by construction and
 * `tests/golden/cone.json` compares the two to the bit.
 */
function inside(occluders: readonly Occluder[], u: number, v: number): boolean {
  for (const smoke of occluders) {
    const du = u - smoke.u;
    const dv = v - smoke.v;
    if (du * du + dv * dv <= smoke.radius * smoke.radius) {
      return true;
    }
  }
  return false;
}

/**
 * The unit direction of every ray in a cone, before any of them is marched.
 *
 * Split out for the reason the Python side is: these are the only values in the
 * whole model that come out of `atan2`, `cos` and `sin`, and **both languages
 * specify those as approximate** -- CPython takes the platform's libm and V8
 * ships its own.  So this is the one place the golden fixtures compare within a
 * bound rather than to the bit, and everything downstream of it is plain
 * arithmetic and compared exactly.
 */
export function rayDirections(
  forward: [number, number],
  settings: SightSettings,
): Array<[number, number]> {
  const [du, dv] = forward;
  if (du === 0 && dv === 0) {
    return [];
  }
  const base = Math.atan2(dv, du);
  const half = radians(settings.fov_degrees) / 2;
  const step = radians(settings.ray_step_degrees);
  const count = Math.max(2, Math.trunc(radians(settings.fov_degrees) / step) + 1);

  const out: Array<[number, number]> = [];
  for (let i = 0; i < count; i += 1) {
    const angle = base - half + 2 * half * (i / (count - 1));
    out.push([Math.cos(angle), Math.sin(angle)]);
  }
  return out;
}

/**
 * The visible wedge as a uv polygon, apex first.
 *
 * **An empty result means draw nothing** -- no heading, or no radius.  Never a
 * fallback circle: a circle where a cone belongs claims the player can see in
 * every direction, which is the one thing a sight approximation must not say.
 */
export function cone(
  mask: SightMask,
  origin: [number, number],
  forward: [number, number],
  radius: number,
  settings: SightSettings,
  occluders: readonly Occluder[] = [],
): Array<[number, number]> {
  if (radius <= 0) {
    return [];
  }
  const rays = rayDirections(forward, settings);
  if (rays.length === 0) {
    return [];
  }
  return [
    origin,
    ...rays.map((ray) =>
      march(mask, origin, ray, radius, settings.seed_cells, occluders),
    ),
  ];
}
