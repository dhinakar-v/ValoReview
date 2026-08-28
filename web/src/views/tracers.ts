/**
 * The fatal shot, as a bullet crossing a line between two decoded positions.
 *
 * **Nothing in a `.vrf` is a shot.**  `loader` reads `characterDeath` and gets
 * three arguments -- a millisecond, a killer and a victim -- with no weapon, no
 * hit location and no projectile; and only `Pawn_` actors ever emit movement,
 * which is why `abilities` cannot draw an arc either.  So what is read here is
 * that two named players were in two known places at one known instant, and
 * what is *generated* is the straight line joining them, the speed anything
 * travels along it, and the fact that anything travels at all.  That is the
 * same kind of claim `model/synthetic.ts` makes about a health bar, and it is
 * drawn the way this canvas already marks a generated geometry: dashed, under a
 * layer whose label carries the word.
 *
 * **The flight ends at the kill, which means it begins before it.**
 * `FLIGHT_MS` of it is drawn while the victim is still alive and still moving,
 * so this layer shows a bullet heading for somebody who has not died yet.  That
 * is the page knowing the future, and nothing else in this interface does it:
 * `stateAt` answers about one instant and refuses to look past it.  It is a
 * deliberate exception, taken because the whole value of animating a shot is
 * the physical reading -- a bullet lands, a player falls -- and running the
 * flight the other way lands the impact on a body that is already down, which
 * reads as a mistake rather than as a shot.  The disclaimer covers it:
 * `SIMULATED_NOTE` says the flight is an animation and says it is drawn early.
 *
 * Storeless, and that is load-bearing rather than tidy.  `LayersMenu.test.tsx`
 * scrapes `layers.<key>` out of the raw source of `MinimapCanvas.tsx` and
 * `Scene3D.tsx` to check that a layer is drawn by exactly the canvases it
 * claims; a gate moved in here would vanish from both files and fail that guard
 * twice.  Each canvas reads its own switch and calls this for the geometry --
 * the arrangement `sightlayer.ts` already has.
 *
 * Nothing is added to `Snapshot` either.  It is serialised field for field
 * against `tests/golden/` by `parity.test.ts`, so a member here would mean a
 * Python counterpart, a regenerated golden and a `make-golden --check` pass, in
 * two languages, for a mark that lives just over a second.
 */

import type { ReplayModel } from "../model/replay";
import type { Snapshot } from "../model/state";
import type { Position } from "../model/track";
import { trackAt } from "../model/track";
import type { Side } from "../model/synthetic";
import { sideOf } from "../model/synthetic";

/**
 * How long the bullet is in the air, ending at the kill.
 *
 * A presentation speed and not a muzzle velocity: a rifle round crosses a site
 * in a few milliseconds, so a bullet slow enough to watch is one this project
 * invented outright.  What the number has to buy is that the eye can follow it
 * from one end of the line to the other, and half a second does that at any
 * zoom while keeping the whole mark inside the second either side of the kill
 * that a reader is actually looking at.
 */
export const FLIGHT_MS = 500;

/** The whole line, at full strength, once the bullet has landed. */
export const HOLD_MS = 200;

/** And then it goes, leaving the map to the round again. */
export const FADE_MS = 500;

/** How long a tracer is on screen in total, on both sides of its kill. */
export const TRACER_LIFE_MS = FLIGHT_MS + HOLD_MS + FADE_MS;

export interface Tracer {
  /** Where the killer stood at the kill instant. */
  from: Position;
  /** Where the victim stood at the same instant. */
  to: Position;
  /**
   * The **killer's** side, which is what colours the line.
   *
   * Null where the killer is in no roster, which is the same refusal
   * `roundevents` makes: a side is a claim, and an unattributable mark gets
   * `--team-unknown` rather than a guess.
   */
  side: Side | null;
  /** How far along the line the bullet is: 0 at the muzzle, 1 landed. */
  progress: number;
  /** Ink. 1 until the hold is over, then down to 0 across the fade. */
  alpha: number;
}

/**
 * Every tracer that should be on screen at `snap.t_ms`.
 *
 * The window straddles the kill -- `FLIGHT_MS` before it and `HOLD_MS +
 * FADE_MS` after -- so this reads `model.replay.kills` directly rather than
 * `Snapshot.recentKills`, which holds only kills the playhead has already
 * passed.  That also drops an incidental coupling: the two layers no longer
 * have to agree about `KILL_FADE_MS`, which is a fact about how long a reader
 * needs to read a kill-feed row and was never about this.
 *
 * Four refusals, each of them one this tree has already made somewhere else:
 *
 *   * a **suicide** draws nothing, because there is no shooter;
 *   * both ends are `trackAt(..., kill.t_ms)` and never `positionOf`, which
 *     answers about *now*.  They stay pinned there for the whole flight, while
 *     neither player is standing on them yet: the line is *the shot*, anchored
 *     to the moment it mattered, and an end that tracked a live position would
 *     drag the geometry under the bullet and draw a path nobody took;
 *   * where `trackAt` returns null at either end, nothing is drawn at all.  Its
 *     own docstring is the rule: "Where this returns null, draw nothing.  There
 *     is no last-known-place fallback anywhere downstream.";
 *   * a killer in no roster gets no side rather than a guessed one.
 */
export function tracersAt(model: ReplayModel, snap: Snapshot): Tracer[] {
  const out: Tracer[] = [];
  for (const kill of model.replay.kills) {
    // In time order, so the first kill whose muzzle is still ahead of the
    // playhead ends the walk.
    if (kill.t_ms - FLIGHT_MS > snap.t_ms) {
      break;
    }
    const sinceKill = snap.t_ms - kill.t_ms;
    if (kill.is_suicide || sinceKill >= HOLD_MS + FADE_MS) {
      continue;
    }
    const from = trackAt(model.positions.get(kill.killer), kill.t_ms);
    const to = trackAt(model.positions.get(kill.victim), kill.t_ms);
    if (from === null || to === null) {
      continue;
    }
    const killer = model.replay.players.find((player) => player.actor_id === kill.killer);
    out.push({
      from,
      to,
      side: killer ? sideOf(model.replay, killer.team, kill.t_ms) : null,
      progress: flightProgress(sinceKill),
      alpha: flightAlpha(sinceKill),
    });
  }
  return out;
}

/**
 * How far the bullet has flown, `sinceKill` ms after the kill.
 *
 * Negative before it, which is where the flight is: `-FLIGHT_MS` is the muzzle
 * and 0 is the impact.  Clamped at both ends so the hold draws the whole line
 * rather than one that keeps growing past the victim.
 */
export function flightProgress(sinceKill: number): number {
  return Math.max(0, Math.min(1, (sinceKill + FLIGHT_MS) / FLIGHT_MS));
}

/**
 * How opaque a tracer is, `sinceKill` ms after the kill.
 *
 * Full through the flight and the hold, then `1 - f * f` across the fade --
 * the same curve `KillToast` fades a chip with, so the shot and the row naming
 * it die together.
 */
export function flightAlpha(sinceKill: number): number {
  if (sinceKill <= HOLD_MS) {
    return 1;
  }
  const fading = Math.min(1, (sinceKill - HOLD_MS) / FADE_MS);
  return 1 - fading * fading;
}
