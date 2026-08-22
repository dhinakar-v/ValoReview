/**
 * One actor's decoded trajectory, and the three answers it can give.
 *
 * A port of `vrfview.model.Track`, field for field and branch for branch.
 * Sampling is not uniform -- the game emits movement in bursts and stops
 * emitting for an actor with nothing to say -- so `trackAt` has to choose
 * between interpolating across a short gap, holding a lone sample briefly, and
 * reporting no position at all.  The third is the one that matters: a straight
 * line across a long gap draws a player through a wall, and a stale sample
 * dressed as current puts somebody on the map who is not there.
 *
 * **Where this returns null, draw nothing.**  There is no last-known-place
 * fallback anywhere downstream, and adding one would undo the refusal this
 * exists to make.
 */

import { lerp, lerpAngle } from "./angles";

/**
 * Where one actor was at one instant, in the map's own Unreal units.
 *
 * Snake_case because this *is* the wire shape: the same object arrives from
 * `/api/replays/{id}/positions`, goes into `tests/golden/`, and is compared
 * against Python's, so renaming the fields here would mean a translation layer
 * in the one place a translation layer could hide a mismatch.
 *
 * There is no interpolation flag.  A held Position carries the millisecond it
 * was actually measured at and an interpolated one carries the requested time,
 * so `t_ms` already says how fresh it is.
 */
export interface Position {
  t_ms: number;
  actor_id: number;
  x: number;
  y: number;
  z: number;
  yaw: number;
  pitch: number;
}

export interface Track {
  actor_id: number;
  /** In time order, which is how both the sidecar and the decoder write them. */
  samples: Position[];
}

/**
 * Two samples further apart than this are a gap in the record rather than a
 * straight line worth drawing.
 */
export const MAX_INTERPOLATE_MS = 1000;

/** Past this a lone sample stops standing in for the present altogether. */
export const MAX_HOLD_MS = 2000;

/** `bisect_left` over the samples, keyed by millisecond. */
function bisectLeft(samples: Position[], tMs: number): number {
  let low = 0;
  let high = samples.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (samples[middle]!.t_ms < tMs) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }
  return low;
}

/** Where this actor was at `tMs`, or null if that is not known. */
export function trackAt(track: Track | undefined, tMs: number): Position | null {
  const samples = track?.samples;
  if (!samples || samples.length === 0) {
    return null;
  }
  const i = bisectLeft(samples, tMs);
  const before = i > 0 ? samples[i - 1]! : null;
  const after = i < samples.length ? samples[i]! : null;

  if (after !== null && after.t_ms === tMs) {
    return after;
  }
  if (before !== null && after !== null && after.t_ms - before.t_ms <= MAX_INTERPOLATE_MS) {
    const f = (tMs - before.t_ms) / (after.t_ms - before.t_ms);
    return {
      t_ms: tMs,
      actor_id: track!.actor_id,
      x: lerp(before.x, after.x, f),
      y: lerp(before.y, after.y, f),
      z: lerp(before.z, after.z, f),
      yaw: lerpAngle(before.yaw, after.yaw, f),
      // An angle, like the yaw beside it, and interpolated as one.
      pitch: lerpAngle(before.pitch, after.pitch, f),
    };
  }
  const candidates = [before, after].filter((p): p is Position => p !== null);
  let nearest = candidates[0]!;
  for (const candidate of candidates) {
    if (Math.abs(candidate.t_ms - tMs) < Math.abs(nearest.t_ms - tMs)) {
      nearest = candidate;
    }
  }
  return Math.abs(nearest.t_ms - tMs) <= MAX_HOLD_MS ? nearest : null;
}

/** The first and last millisecond this track says anything about. */
export function span(track: Track): [number, number] {
  if (track.samples.length === 0) {
    return [0, 0];
  }
  return [track.samples[0]!.t_ms, track.samples[track.samples.length - 1]!.t_ms];
}

/**
 * The samples inside a window, in time order, split where the record goes quiet.
 *
 * Every trail in the interface goes through this rather than joining whatever
 * samples happen to be in range.  `trackAt` refuses to interpolate across a gap
 * longer than `MAX_INTERPOLATE_MS` precisely because the straight line would
 * cross whatever is between the two points -- and a trail that then draws that
 * same line has thrown the refusal away.  The desktop viewer's
 * `minimap._draw_pawn_trail` did exactly that; both ports split instead.
 */
export function segments(track: Track, fromMs: number, toMs: number): Position[][] {
  const out: Position[][] = [];
  let run: Position[] = [];
  for (const sample of track.samples) {
    if (sample.t_ms < fromMs || sample.t_ms > toMs) {
      continue;
    }
    const previous = run[run.length - 1];
    if (previous !== undefined && sample.t_ms - previous.t_ms > MAX_INTERPOLATE_MS) {
      out.push(run);
      run = [];
    }
    run.push(sample);
  }
  if (run.length > 0) {
    out.push(run);
  }
  return out.filter((piece) => piece.length >= 2);
}
