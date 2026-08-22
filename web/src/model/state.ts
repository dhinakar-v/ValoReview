/**
 * What the match looks like at one instant.  A port of `vrfview.state`.
 *
 * Recomputed from scratch on every frame; there is no incremental cache and no
 * notion of "playing forward".  That is affordable -- a match is about 150
 * events and ten binary searches -- and it buys the property that makes replay
 * interfaces hard otherwise: seeking backwards, dragging the scrubber and
 * jumping between rounds are all exactly as correct as playing forward, because
 * nothing accumulates.  Measured in Python at 0.127 ms on a 199,180-sample
 * replay, against 16.7 ms of budget at 60 fps; this does the same arithmetic.
 *
 * Alive state is scoped to the round.  Everyone is alive at a round boundary,
 * which is what the file implies: there is no respawn event, and no player dies
 * twice inside a single round window once `characterDeath`'s arguments are read
 * in the right order -- `args[1]` is the killer and `args[2]` the victim.
 *
 * Where a player has stopped emitting movement, which is what dying looks like
 * on the wire, `deathPositions` holds the last place they were seen this round,
 * so the scene can leave a body rather than have somebody vanish or, worse,
 * appear to keep walking.
 */

import type { AbilityCast, Kill, Round } from "../api/types";
import type { ReplayModel } from "./replay";
import type { Position } from "./track";
import { trackAt } from "./track";

/** How long a kill arrow and an ultimate pulse stay on screen, in playback ms. */
export const KILL_FADE_MS = 2500;
export const ULT_FADE_MS = 1500;

export const SPIKE_NONE = "none";
export const SPIKE_PLANTED = "planted";
export const SPIKE_DEFUSED = "defused";
export const SPIKE_EXPLODED = "exploded";

const SPIKE_STATE: Record<string, string> = {
  planted: SPIKE_PLANTED,
  defused: SPIKE_DEFUSED,
  exploded: SPIKE_EXPLODED,
};

export interface Snapshot {
  t_ms: number;
  round: Round | null;
  alive: Set<number>;
  deadSince: Map<number, number>;
  /** Each kill still inside the fade window, with its age as 0..1. */
  recentKills: Array<[Kill, number]>;
  recentUlts: Array<[number, number]>;
  roundKills: Kill[];
  ultedThisRound: Set<number>;
  spikeState: string;
  spikeSinceMs: number | null;
  /** Running (kills, deaths) per actor over the whole match up to `t_ms`. */
  kd: Map<number, [number, number]>;
  score: [number, number];
  positions: Map<number, Position>;
  deathPositions: Map<number, Position>;
  roundCasts: AbilityCast[];
  abilityPositions: Map<number, Position>;
}

/** Where an actor is now, or where they fell if they have stopped moving. */
export function positionOf(snap: Snapshot, actorId: number): Position | null {
  return snap.positions.get(actorId) ?? snap.deathPositions.get(actorId) ?? null;
}

export function roundAt(model: ReplayModel, tMs: number): Round | null {
  for (const round of model.replay.rounds) {
    if (round.start_ms <= tMs && tMs < round.end_ms) {
      return round;
    }
  }
  const rounds = model.replay.rounds;
  if (rounds.length > 0 && tMs >= model.replay.length_ms) {
    return rounds[rounds.length - 1]!;
  }
  return null;
}

function containsRound(round: Round | null, tMs: number): boolean {
  return round !== null && round.start_ms <= tMs && tMs < round.end_ms;
}

function kdAt(model: ReplayModel, tMs: number): Map<number, [number, number]> {
  const kd = new Map<number, [number, number]>();
  for (const player of model.replay.players) {
    kd.set(player.actor_id, [0, 0]);
  }
  for (const kill of model.replay.kills) {
    if (kill.t_ms > tMs) {
      break;
    }
    if (!kill.is_suicide) {
      const killer = kd.get(kill.killer);
      if (killer) {
        kd.set(kill.killer, [killer[0] + 1, killer[1]]);
      }
    }
    const victim = kd.get(kill.victim);
    if (victim) {
      kd.set(kill.victim, [victim[0], victim[1] + 1]);
    }
  }
  return kd;
}

function deathsThisRound(
  model: ReplayModel,
  round: Round | null,
  tMs: number,
): { deadSince: Map<number, number>; roundKills: Kill[] } {
  const deadSince = new Map<number, number>();
  const roundKills: Kill[] = [];
  if (round === null) {
    return { deadSince, roundKills };
  }
  for (const kill of model.replay.kills) {
    if (kill.t_ms > tMs) {
      break;
    }
    if (containsRound(round, kill.t_ms)) {
      if (!deadSince.has(kill.victim)) {
        deadSince.set(kill.victim, kill.t_ms);
      }
      roundKills.push(kill);
    }
  }
  return { deadSince, roundKills };
}

/**
 * Where the spike is lying right now, or null.
 *
 * A free function rather than a `Snapshot` field on purpose.  `Snapshot` is
 * serialised field-for-field against `tests/golden/` by `parity.test.ts`, so a
 * new member needs a Python counterpart, a regenerated golden and a
 * `make-golden --check` pass -- in two languages, for one marker.  Nothing
 * here needs the snapshot's own work, only the round and the clock.
 *
 * Only while **planted**: on a defuse the spike is picked up and on an explode
 * it is gone, so drawing it after either would put an object on the map that
 * is not there.  A plant whose capture was never decoded has no coordinate and
 * returns null, which is the same "draw nothing" as no plant at all.
 */
export function spikeLocation(
  model: ReplayModel,
  snap: Snapshot,
): { x: number; y: number; z: number } | null {
  if (snap.spikeState !== SPIKE_PLANTED || snap.round === null) {
    return null;
  }
  for (const event of model.replay.spike) {
    if (
      event.kind === "planted" &&
      event.t_ms === snap.spikeSinceMs &&
      event.x !== null &&
      event.y !== null &&
      event.z !== null
    ) {
      return { x: event.x, y: event.y, z: event.z };
    }
  }
  return null;
}


/** The last spike event inside the current round wins; nothing carries over. */
function spikeAt(
  model: ReplayModel,
  round: Round | null,
  tMs: number,
): [string, number | null] {
  if (round === null) {
    return [SPIKE_NONE, null];
  }
  let state = SPIKE_NONE;
  let since: number | null = null;
  for (const event of model.replay.spike) {
    if (event.t_ms > tMs) {
      break;
    }
    if (containsRound(round, event.t_ms)) {
      state = SPIKE_STATE[event.kind] ?? SPIKE_NONE;
      since = event.t_ms;
    }
  }
  return [state, since];
}

/**
 * Where everyone is now, and where the dead were last seen this round.
 *
 * A player who has died has no live position for long: their pawn stops sending
 * movement and `trackAt` goes quiet a couple of seconds later.  Asking the
 * track for the death instant instead is exact, so the two maps never disagree
 * about somebody -- and a death position outranks a live one, because the pawn
 * may still be replicating a ragdoll and it is the moment of the kill the
 * viewer means to mark.
 */
function positionsAt(
  model: ReplayModel,
  deadSince: Map<number, number>,
  tMs: number,
): { live: Map<number, Position>; fallen: Map<number, Position> } {
  const live = new Map<number, Position>();
  const fallen = new Map<number, Position>();
  for (const [actorId, track] of model.positions) {
    const here = trackAt(track, tMs);
    if (here !== null) {
      live.set(actorId, here);
    }
    const diedAt = deadSince.get(actorId);
    if (diedAt !== undefined) {
      const there = trackAt(track, diedAt);
      if (there !== null) {
        fallen.set(actorId, there);
      }
    }
  }
  for (const actorId of fallen.keys()) {
    live.delete(actorId);
  }
  return { live, fallen };
}

/**
 * The casts made so far this round, and where their pawns are now.
 *
 * A cast is kept once the playhead reaches it and never removed before the
 * round ends.  Unlike a kill arrow it is not an animation but the record of a
 * decision, and a list that empties as you scrub forward would be unable to
 * answer what utility has already been spent.
 *
 * Pawn positions go through the same `trackAt` as a player's, so an ability
 * pawn that has stopped replicating disappears rather than freezing in place.
 * There is deliberately no death-position fallback: a drone is shot down and
 * gone, and pinning its last coordinate would leave a marker on the map for
 * something that is no longer on it.
 */
function abilitiesAt(
  model: ReplayModel,
  round: Round | null,
  tMs: number,
): { casts: AbilityCast[]; live: Map<number, Position> } {
  if (round === null) {
    return { casts: [], live: new Map() };
  }
  const casts = model.replay.ability_casts.filter(
    (cast) => containsRound(round, cast.t_ms) && cast.t_ms <= tMs,
  );
  const live = new Map<number, Position>();
  for (const cast of casts) {
    for (const actorId of cast.pawns) {
      const here = trackAt(model.abilityTracks.get(actorId), tMs);
      if (here !== null) {
        live.set(actorId, here);
      }
    }
  }
  return { casts, live };
}

/** Everything drawable at `tMs`, computed from scratch. */
export function stateAt(
  model: ReplayModel,
  rawMs: number,
  killFadeMs = KILL_FADE_MS,
  ultFadeMs = ULT_FADE_MS,
): Snapshot {
  const tMs = Math.max(0, Math.min(Math.trunc(rawMs), model.replay.length_ms));
  const round = roundAt(model, tMs);

  const kd = kdAt(model, tMs);
  const { deadSince, roundKills } = deathsThisRound(model, round, tMs);
  const alive = new Set(
    model.replay.players
      .filter((player) => !deadSince.has(player.actor_id))
      .map((player) => player.actor_id),
  );

  const recentKills: Array<[Kill, number]> = model.replay.kills
    .filter((kill) => tMs - kill.t_ms >= 0 && tMs - kill.t_ms < killFadeMs)
    .map((kill) => [kill, (tMs - kill.t_ms) / killFadeMs]);
  const recentUlts: Array<[number, number]> = model.replay.ultimates
    .filter((ult) => tMs - ult.t_ms >= 0 && tMs - ult.t_ms < ultFadeMs)
    .map((ult) => [ult.actor_id, (tMs - ult.t_ms) / ultFadeMs]);

  const ultedThisRound = new Set(
    model.replay.ultimates
      .filter((ult) => ult.t_ms <= tMs && containsRound(round, ult.t_ms))
      .map((ult) => ult.actor_id),
  );

  const [spikeState, spikeSinceMs] = spikeAt(model, round, tMs);

  const scoreA = model.replay.rounds.filter(
    (r) => r.winner === "A" && r.end_ms <= tMs,
  ).length;
  const scoreB = model.replay.rounds.filter(
    (r) => r.winner === "B" && r.end_ms <= tMs,
  ).length;

  const { live, fallen } = positionsAt(model, deadSince, tMs);
  const { casts, live: abilityPositions } = abilitiesAt(model, round, tMs);

  return {
    t_ms: tMs,
    round,
    alive,
    deadSince,
    recentKills,
    recentUlts,
    roundKills,
    ultedThisRound,
    spikeState,
    spikeSinceMs,
    kd,
    score: [scoreA, scoreB],
    positions: live,
    deathPositions: fallen,
    roundCasts: casts,
    abilityPositions,
  };
}
