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
 * One ray, to the first thing that blocks it or to `radius`, whichever is
 * nearer.  Exported so the parity test can march the directions Python marched.
 *
 * **The stopping distance is exact, not a whole number of cells.**  This used
 * to step a fixed `1/size` at a time and return `(i - 1) * cell`, so every ray
 * ended on a multiple of one cell whatever it had actually hit.  Two
 * neighbouring rays glancing a near-parallel wall then stopped one whole cell
 * apart, and the cone's rim came out as a sawtooth whose teeth were spaced at
 * `ray_step_degrees` and one cell deep -- a drawing artefact of the sampling,
 * not a fact about the map.
 *
 * So a wall is found by grid traversal (`wallEntry`), which visits cell
 * boundaries in order and returns the distance to the face of the first
 * blocked cell, and a smoke by solving the ray-circle quadratic
 * (`smokeEntry`).  Both answers are the real intersection, so the rim traces
 * the silhouette at the mask's own resolution instead of at the sampling's.
 *
 * Everything here is multiply, divide, add, compare, `floor` and `sqrt`, all
 * of which IEEE-754 specifies exactly, so this agrees with Python by
 * construction the way the old stepping did.  No `hypot` -- approximate by
 * specification in both languages.
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
  const seedT = seedCells / mask.size;
  const limit = smokeEntry(occluders, origin, direction, radius, seedT);
  const travelled = wallEntry(mask, origin, direction, limit, seedT);
  return [u0 + du * travelled, v0 + dv * travelled];
}

/**
 * How far the ray travels before it enters a blocked cell, capped at `limit`.
 *
 * Amanatides-Woo traversal: hold the distance to the next boundary on each
 * axis, always cross the nearer one, and the cell index steps by one.  The
 * cell is then an *integer* pair rather than a `Math.floor` of a sampled
 * point, which is what makes landing exactly on a boundary well defined
 * instead of a rounding question -- and the returned distance is the boundary
 * itself, so the polygon meets the wall's face.
 *
 * `seedT` is `seed_cells` cells' worth of distance, ignored the way the
 * stepped version ignored its first few samples: a player against a wall or in
 * a doorway sits on a transparent cell often enough that refusing there would
 * blink the cone off exactly when it matters.  As a distance rather than a
 * count of crossings, because a diagonal ray crosses two boundaries per cell
 * and the seed must not shrink with the angle.
 */
function wallEntry(
  mask: SightMask,
  origin: [number, number],
  direction: [number, number],
  limit: number,
  seedT: number,
): number {
  const [u0, v0] = origin;
  const [du, dv] = direction;
  const size = mask.size;
  const cell = 1 / size;

  let col = Math.floor(u0 * size);
  let row = Math.floor(v0 * size);
  const stepCol = du > 0 ? 1 : du < 0 ? -1 : 0;
  const stepRow = dv > 0 ? 1 : dv < 0 ? -1 : 0;
  if (stepCol === 0 && stepRow === 0) {
    return limit;
  }

  const nextU = stepCol > 0 ? (col + 1) * cell : col * cell;
  const nextV = stepRow > 0 ? (row + 1) * cell : row * cell;
  let tU = stepCol === 0 ? Infinity : (nextU - u0) / du;
  let tV = stepRow === 0 ? Infinity : (nextV - v0) / dv;
  const deltaU = stepCol === 0 ? Infinity : cell / Math.abs(du);
  const deltaV = stepRow === 0 ? Infinity : cell / Math.abs(dv);

  for (;;) {
    let travelled: number;
    if (tU < tV) {
      travelled = tU;
      col += stepCol;
      tU += deltaU;
    } else {
      travelled = tV;
      row += stepRow;
      tV += deltaV;
    }
    if (travelled >= limit) {
      return limit;
    }
    if (travelled <= seedT) {
      continue;
    }
    if (!(col >= 0 && col < size && row >= 0 && row < size)) {
      return travelled;
    }
    if (!mask.cells[row * size + col]) {
      return travelled;
    }
  }
}

/**
 * How far the ray travels before it enters a smoke, capped at `radius`.
 *
 * The ray-circle quadratic, with `a` taken as 1 because the directions are
 * `cos`/`sin` of one angle and are unit by construction -- and taken as 1 in
 * both languages, which is what the parity fixture checks.  A ray that starts
 * *inside* a smoke has a negative entry root and is stopped at `seedT`, which
 * is what the stepped version did by walking into the circle on its first
 * unseeded sample.
 *
 * `sqrt` is exactly specified by IEEE-754, so this is as portable as the
 * squared-distance test it replaces; what it buys is a smoke rim that is a
 * circle rather than a staircase at the sampling interval.
 */
function smokeEntry(
  occluders: readonly Occluder[],
  origin: [number, number],
  direction: [number, number],
  radius: number,
  seedT: number,
): number {
  const [u0, v0] = origin;
  const [du, dv] = direction;
  let nearest = radius;
  for (const smoke of occluders) {
    const fu = u0 - smoke.u;
    const fv = v0 - smoke.v;
    const halfB = fu * du + fv * dv;
    const c = fu * fu + fv * fv - smoke.radius * smoke.radius;
    const discriminant = halfB * halfB - c;
    if (discriminant < 0) {
      continue;
    }
    const root = Math.sqrt(discriminant);
    if (-halfB + root < seedT) {
      continue;
    }
    const entry = -halfB - root;
    const travelled = entry > seedT ? entry : seedT;
    if (travelled < nearest) {
      nearest = travelled;
    }
  }
  return nearest;
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
