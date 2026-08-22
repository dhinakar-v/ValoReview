/**
 * The two documents the browser is handed, joined into one thing to draw from.
 *
 * `/api/replays/{id}` sends everything the file states, everything inferred and
 * everything looked up; `/api/replays/{id}/positions` sends the decoded tracks,
 * separately, because they are three orders of magnitude larger and because a
 * replay is worth showing before they arrive.  Nothing here decides anything --
 * it decodes six parallel arrays into records and puts them in a Map.
 *
 * The columnar shape is `vrfview.positionfile`'s own, unchanged: six
 * equal-length arrays per actor rather than a record per sample, about a third
 * of the bytes and the shape a typed array wants at this end.  One builder
 * feeds the sidecar, the machine cache and this response, so there is one
 * description of what a track looks like rather than three.
 */

import type { Replay } from "../api/types";
import type { Position, Track } from "./track";

/** `vrfview.positionfile`'s document, as it arrives. */
export interface Columns {
  t: number[];
  x: number[];
  y: number[];
  z: number[];
  yaw: number[];
  pitch: number[];
}

export interface PositionsDoc {
  format: string;
  version: number;
  match_id: string;
  build: string;
  hz: number;
  position_source: string;
  codenames: Record<string, string>;
  tracks: Record<string, Columns>;
  /**
   * Empty over HTTP, and deliberately: `tracks.sidecar_of` cannot rebuild the
   * raw spawns from a loaded replay, and says so rather than inventing them.
   * The grouped casts arrive on the replay document instead.
   */
  ability_spawns: Record<string, unknown[]>;
  ability_tracks: Record<string, Columns>;
}

/** Everything `stateAt` reads: the wire replay, plus the tracks beside it. */
export interface ReplayModel {
  replay: Replay;
  positions: Map<number, Track>;
  abilityTracks: Map<number, Track>;
}

function toTrack(actorId: number, columns: Columns): Track {
  const samples: Position[] = new Array(columns.t.length);
  for (let i = 0; i < columns.t.length; i += 1) {
    samples[i] = {
      t_ms: columns.t[i]!,
      actor_id: actorId,
      x: columns.x[i]!,
      y: columns.y[i]!,
      z: columns.z[i]!,
      yaw: columns.yaw[i]!,
      pitch: columns.pitch[i]!,
    };
  }
  return { actor_id: actorId, samples };
}

function toTracks(entries: Record<string, Columns>): Map<number, Track> {
  const out = new Map<number, Track>();
  for (const [rawId, columns] of Object.entries(entries)) {
    const actorId = Number(rawId);
    out.set(actorId, toTrack(actorId, columns));
  }
  return out;
}

export function buildModel(replay: Replay, positions: PositionsDoc | null): ReplayModel {
  return {
    replay,
    positions: positions ? toTracks(positions.tracks) : new Map(),
    abilityTracks: positions ? toTracks(positions.ability_tracks) : new Map(),
  };
}

/**
 * How far below the match's own median z a sample stops being a place.
 *
 * The replication stream parks an out-of-play actor far off the world, and the
 * samples say so plainly: across the 21 playable captures the deepest sample a
 * player ever legitimately reaches is 1,025.7 uu below that capture's median,
 * while four captures additionally carry 182 to 684 samples sitting 49,899 to
 * 49,920 uu below it -- with x out at about -50,000 as well, off the map
 * horizontally too.  The two populations are two orders of magnitude apart, so
 * this threshold is ten times the deepest real sample and a fifth of the
 * shallowest parked one.  It is a gap, not a tuned number.
 *
 * The median is the reference for that comparison, which assumes the parked
 * samples are a minority.  They are, by a wide margin: 0.10% to 0.33% of a
 * capture's samples in the four that have any.  A capture where most samples
 * were parked would have nobody on the map to measure a floor for.
 */
export const OFF_WORLD_DROP_UU = 10000;

/**
 * The lowest z any player *stands* at, which is the 3D scene's ground reference.
 *
 * Computed once on load rather than per frame, and over the players only: an
 * ability pawn can sit on a ledge or under the floor, and the plane a scene is
 * measured from should be the one people stand on.
 *
 * Which is why the raw minimum is not it.  A parked actor is 50,000 uu down,
 * and taking it made `sceneY` about 3.5 -- three and a half times the width of
 * the whole map -- for **every player in the capture**, so the scene drew ten
 * stems disappearing off the top of the frame and not one marker.  The ground
 * rendered perfectly underneath, which is exactly why nobody caught it by eye:
 * the view looked like a map with nobody on it rather than like a bug.
 *
 * Nothing is dropped from the model here.  This is the scene's reference height
 * and only that; a parked sample is still in the track, and what should happen
 * to it there is a separate question about the decode, not about a camera.
 */
export function floorZ(model: ReplayModel): number {
  const zs: number[] = [];
  for (const track of model.positions.values()) {
    for (const sample of track.samples) {
      zs.push(sample.z);
    }
  }
  if (zs.length === 0) {
    return 0;
  }
  zs.sort((a, b) => a - b);
  const median = zs[Math.trunc(zs.length / 2)]!;
  for (const z of zs) {
    if (z >= median - OFF_WORLD_DROP_UU) {
      return z;
    }
  }
  // Every sample is below the median by more than the threshold, which cannot
  // happen -- the median is one of them. Kept so the function has no way to
  // return `undefined` rather than because it can be reached.
  return median;
}
