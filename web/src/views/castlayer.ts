/**
 * What an ability is doing right now: in the air, arming, standing, or gone.
 *
 * The canvas used to draw a cast as one static mark at one coordinate -- a
 * square for a pawn, a hollow diamond for a placed thing -- which answers
 * *something happened here* and nothing else.  It never said when the thing
 * arrived, how far it reaches, how long it stood or when it stopped mattering,
 * so a reader watching a round could not tell a smoke that had just landed
 * from one about to expire.
 *
 * Two different kinds of number make that answerable and they must not be
 * confused, which is most of what this module is for:
 *
 *   * **decoded** -- where the throw began, where it ended, and the instant of
 *     each.  A `Projectile_` channel opens where the caster is standing and a
 *     placed channel opens where the thing came to rest, and since
 *     `Placement.t_ms` exists both instants are read out of the capture.  The
 *     only invented part of a throw is the straight line between its two ends,
 *     which is exactly the claim `tracers.ts` makes about a fatal shot.
 *   * **looked up** -- the radius, the arm time, how long it lasts.  Nothing
 *     in a `.vrf` states any of these; they come from `vrfview.abilityfacts`,
 *     which is community research about a game that rebalances every few
 *     weeks.  Every one of them is drawn dashed and lives under a layer whose
 *     label carries `(SIM)`.
 *
 * There is **no arc**.  Only `Pawn_` actors emit movement, so nothing in the
 * file says where a thrown thing was halfway between its two ends, and a curve
 * through the middle would be a path nobody took drawn in the same ink as one
 * that was decoded.
 *
 * There is **no claim about any player**.  This module returns geometry and
 * phases; it never takes a radius and a set of positions and reports who was
 * inside.  Position is 10 Hz and interpolated, the sight approximation already
 * wrongly closes a third of real sightlines, and whether somebody was looking
 * at a flash is not in the file at all -- so "these three were blinded" would
 * be a confident sentence about named people built on none of the evidence it
 * would appear to rest on.  A published debuff is a property of the *ability*
 * and is shown as one.
 *
 * **This module reads no store.**  `LayersMenu.test.tsx` scrapes `layers.<key>`
 * out of the raw source of `MinimapCanvas.tsx` and `Scene3D.tsx` and checks it
 * against each layer's declared `drawnIn`, so a gate moved in here would
 * vanish from both files and fail that guard twice.  The canvas reads the
 * switch and calls in with the answer, the way it already does for tracers and
 * for sight.
 */

import type { AbilityCast, Placement, Flight } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { Snapshot } from "../model/state";
import type { Side } from "../model/synthetic";
import { sideOf } from "../model/synthetic";

/**
 * How long a mark fades once its published lifetime is over.
 *
 * A presentation figure and the only invented duration in this module: the
 * ability stops at its published lifetime and this is how long the *drawing*
 * takes to admit it. It exists because a mark that vanishes between two frames
 * reads as a rendering fault rather than as an expiry, and somebody scrubbing
 * a round needs to see which of two smokes went out first.
 */
export const EXPIRE_MS = 600;

/**
 * How long a *moment* stays on screen.
 *
 * The one invented duration in this module, and it is invented the way
 * `tracers.FLIGHT_MS` is -- a presentation figure, not a measurement, and it
 * has to be admitted as one.
 *
 * It exists because the alternative was worse in a way a reader could see. An
 * ability that publishes no lifetime and leaves nothing standing -- a flash, a
 * shock dart, a concussion -- was drawn from the instant it went off until the
 * round ended, so a flash that popped forty seconds ago sat on the map beside
 * one going off now. That is a claim, and a false one: the file says a thing
 * happened *there, then*, and nothing at all about it still being there.
 *
 * Neither reading is decoded. Nothing records a channel closing, so there is
 * no measured lifetime on disk for any of these. Between "it happened here for
 * a moment" and "it is still here a minute later", the first is much closer to
 * what a flash is, and the second is the plausible-looking wrong answer.
 *
 * A thing that genuinely does stand is not affected: see `persists`.
 */
export const EVENT_MS = 2000;

/**
 * The kinds of placement that are a thing left standing.
 *
 * The same set `sightlayer` uses, and deliberately the same three: a
 * `Projectile_` is a throw origin sitting inside the caster's own capsule and
 * an `Ability_` is the record of the decision, so neither is somewhere a ring
 * belongs. Mirrors `abilities.PLACED_KINDS` in Python.
 */
export const PLACED_KINDS = new Set(["GameObject", "Zone", "Patch"]);

export interface Point {
  x: number;
  y: number;
}

/**
 * What one placement is doing at one instant.
 *
 * `flight` is the only one whose clock is entirely decoded. `arming` and
 * `active` run on looked-up figures, and `placed` is the old static mark --
 * what an ability with no published lifetime gets, for ever, because there is
 * nothing to count down.
 */
export type CastPhase =
  | { kind: "flight"; from: Point; to: Point; at: Point; progress: number }
  | { kind: "wall"; from: Point; to: Point }
  | { kind: "arming"; at: Point; progress: number }
  | { kind: "active"; at: Point; progress: number }
  | { kind: "expiring"; at: Point; alpha: number }
  | { kind: "placed"; at: Point };

export interface DrawnCast {
  /** Stable across frames: one cast can leave several things standing. */
  key: string;
  cast: AbilityCast;
  /** The placement this phase is about, or null during a flight. */
  place: Placement | null;
  phase: CastPhase;
  /**
   * The caster's side, or null where two players share the agent.
   *
   * By side and never by team, like every other mark on this canvas: a team
   * changes side at half time and the ability does not move.
   */
  side: Side | null;
  /** The published area of effect, or null. Never defaulted. */
  radiusUu: number | null;
  /** The published trigger range, or null. A different claim from the above. */
  detectionUu: number | null;
}

/** When a placement's own clock starts: the instant its channel opened. */
export function startOf(place: Placement): number {
  return place.t_ms;
}

/**
 * How long this ability's effect lasts once armed, or null if nobody says.
 *
 * Not how long the *thing* is there -- see `standsOf`. A Trademark publishes a
 * four-second slow and waits on the floor all round, so reading this as a
 * lifetime would sweep the trap off the map four seconds after it was placed.
 */
export function lifeOf(cast: AbilityCast): number | null {
  return cast.mechanics?.duration_ms ?? null;
}

/**
 * Whether the thing itself stands until destroyed, triggered or the round ends.
 *
 * A turret, a camera, a trapwire, an anchor. These publish no lifetime because
 * they have none: what ends them is somebody shooting them or walking into
 * them, and nothing in the capture records either.
 */
export function persistsOf(cast: AbilityCast): boolean {
  return cast.mechanics?.persists ?? false;
}

/** The arm time between landing and doing anything, or 0 where none is published. */
export function armingOf(cast: AbilityCast): number {
  return cast.mechanics?.activation_delay_ms ?? 0;
}

/**
 * The flight that ends at this placement, or null.
 *
 * Joined on the landing actor's own id rather than by position in a list: a
 * cast can hold several throws and `flights` refuses to pair at all unless the
 * counts match, so the ids are the only thing that survives a partial answer.
 */
export function flightTo(cast: AbilityCast, place: Placement): Flight | null {
  return cast.flights.find((entry) => entry.to_actor_id === place.actor_id) ?? null;
}

/**
 * Where one placement is on its own timeline at `tMs`, or null if not on screen.
 *
 * The order of the branches is the order the thing actually happens in, and
 * each boundary is half-open so no instant belongs to two phases at once.
 */
export function phaseOf(cast: AbilityCast, place: Placement, tMs: number): CastPhase | null {
  const at: Point = { x: place.x, y: place.y };
  const flight = flightTo(cast, place);
  if (flight !== null) {
    if (tMs < flight.start_ms) {
      // Nothing yet. The thing has not left the caster's hand, and the mark on
      // the map may not appear before it: a smoke drawn at its landing point
      // while it is still in the air is a place nobody has been.
      return null;
    }
    if (tMs < flight.end_ms) {
      const from: Point = { x: flight.from_x, y: flight.from_y };
      const progress = (tMs - flight.start_ms) / flight.duration_ms;
      return {
        kind: "flight",
        from,
        to: at,
        // Straight, and that is the whole invention here. See the module note.
        at: {
          x: from.x + (at.x - from.x) * progress,
          y: from.y + (at.y - from.y) * progress,
        },
        progress,
      };
    }
  }
  const start = startOf(place);
  if (tMs < start) {
    return null;
  }
  const arming = armingOf(cast);
  if (tMs < start + arming) {
    return { kind: "arming", at, progress: (tMs - start) / arming };
  }
  const armed = start + arming;
  const age = tMs - armed;
  if (persistsOf(cast)) {
    /*
      A thing that stands: a turret, a camera, a trapwire, an anchor. What
      ends it is somebody shooting it or walking into it, and the capture
      records neither, so it stays for the rest of the round -- which is what
      `abilitiesAt` guarantees anyway. Its `duration_ms`, where it has one, is
      how long its *effect* lasts and is deliberately not read here.
    */
    return { kind: "placed", at };
  }
  const life = lifeOf(cast);
  if (life === null) {
    /*
      Nothing published a lifetime. What happens next depends on whether the
      table has anything to say about this ability at all, and the difference
      matters:

        * it names the ability and publishes neither a lifetime nor
          persistence -- that is positive knowledge that this leaves nothing
          standing. A flash, a dart, a concussion. Shown for `EVENT_MS`.
        * it does not name the ability -- thirteen agents of twenty-nine, and
          anything released since. Then nothing is known in either direction,
          and a mark swept off the map after two seconds would be a claim made
          from an absence. It keeps the old behaviour and stands for the round.

      The second is the rule the whole table keeps: no figure, change nothing.
    */
    if (cast.mechanics === null) {
      return { kind: "placed", at };
    }
    if (age >= EVENT_MS) {
      return null;
    }
    const leftOver = EVENT_MS - age;
    if (leftOver <= EXPIRE_MS) {
      return { kind: "expiring", at, alpha: leftOver / EXPIRE_MS };
    }
    return { kind: "active", at, progress: age / EVENT_MS };
  }
  if (age >= life) {
    return null;
  }
  const left = life - age;
  if (left <= EXPIRE_MS) {
    return { kind: "expiring", at, alpha: left / EXPIRE_MS };
  }
  return { kind: "active", at, progress: age / life };
}

/**
 * Whether a thing that landed at `startMs` is still there at `tMs`.
 *
 * The same three outcomes `phaseOf` uses, without the phase: something that
 * persists stands, a published lifetime runs out, and an ability the table does
 * not name changes nothing.  Walls go through this rather than through
 * `phaseOf` because a wall is not a point and has no ring to arm, expire or
 * count down -- what it has is two ends and a lifetime.
 */
function standing(cast: AbilityCast, startMs: number, tMs: number): boolean {
  const age = tMs - startMs;
  if (age < 0) {
    return false;
  }
  if (persistsOf(cast)) {
    return true;
  }
  const life = lifeOf(cast);
  if (life === null) {
    // Unnamed ability: nothing is known in either direction, so nothing
    // changes. A named one with no lifetime is a moment, and a moment is not a
    // wall -- no ability in the table is both.
    return cast.mechanics === null;
  }
  return age < life;
}

/**
 * The wall this cast left, or none.
 *
 * **Entirely decoded, and that is the only kind there is.** Sage's Barrier Orb
 * opens one channel per segment at one instant, each carrying its own spawn
 * transform, so the line, its length and its orientation were all read out of
 * the capture -- measured over 125 casts the four segments are exactly
 * collinear and 260 uu apart. `abilities.AbilityCast.walls` does that grouping
 * in Python, because the rule for it should not exist in two languages, and
 * this reads the answer.
 *
 * There was going to be a second kind, drawn along the caster's decoded yaw at
 * a looked-up length, for the three walls that place a single actor. Two
 * findings retired it before it drew anything:
 *
 *   * **Phoenix's Blaze and Harbor's High Tide have no length.** Each casts a
 *     steerable missile that leaves a path on the ground, and the wall rises
 *     from the caster and spreads along that path until it runs out or meets
 *     geometry -- so every cast is a polyline of a different length, and there
 *     is no figure to look up because there is no number.
 *   * **Vyse's Shear is placed on vertical terrain**, perpendicular to the
 *     ground, so its axis is a property of the surface she was aiming at
 *     rather than of the direction her body faced.
 *
 * The yaw was a weak predictor even where the idea held: on Sage's wall, the
 * one whose axis *is* decoded, the caster's yaw is within 15 degrees of
 * parallel for 66.4% of casts and within 15 degrees of *perpendicular* for
 * 28.8%, because a player can turn that one as they place it. So a wall here
 * is drawn solid, like every other stroke on this canvas around something that
 * was decoded, and there is nothing dashed to distinguish it from.
 */
function wallsOf(cast: AbilityCast, snap: Snapshot): CastPhase[] {
  if (cast.mechanics?.wall !== "segments") {
    return [];
  }
  const out: CastPhase[] = [];
  for (const built of cast.walls) {
    if (!standing(cast, built.t_ms, snap.t_ms)) {
      continue;
    }
    out.push({
      kind: "wall",
      from: { x: built.x1, y: built.y1 },
      to: { x: built.x2, y: built.y2 },
    });
  }
  return out;
}

/**
 * Everything this layer draws at `snap.t_ms`.
 *
 * Pure, storeless, and computed from scratch like everything else here -- so
 * scrubbing backwards is as correct as playing forwards.
 *
 * A cast with a pawn is deliberately absent: a drone and a Boom Bot have real
 * decoded tracks, `MinimapCanvas` already draws those as trails, and a spawn
 * point beside a track is a second, staler answer to the same question.
 */
export function castsAt(model: ReplayModel, snap: Snapshot): DrawnCast[] {
  const sideByActor = new Map<number, string>();
  for (const player of model.replay.players) {
    sideByActor.set(player.actor_id, player.team);
  }
  const out: DrawnCast[] = [];
  for (const cast of snap.roundCasts) {
    if (cast.pawns.length > 0) {
      continue;
    }
    const team = cast.player_actor_id === null ? undefined : sideByActor.get(cast.player_actor_id);
    const side = team === undefined ? null : sideOf(model.replay, team, snap.t_ms);
    const radiusUu = cast.mechanics?.radius_uu ?? null;
    const detectionUu = cast.mechanics?.detection_radius_uu ?? null;
    /*
      A thing that goes when its owner does.

      `persists` says the capture records nothing that ends this, which was
      read as "so it stands to the end of the round" -- and for a Trademark or
      a Spycam that is wrong in a way a reader spots at once: Chamber dies and
      his trap is still sat on the map. What ends it is published (the game
      removes it) and *when* is decoded (`snap.alive` is built from the kill
      feed), so the two together are a fact rather than a guess.

      Refused where the caster is unknown, like every other claim about a
      caster here: two players on the same agent means no attribution, and an
      unattributed trap is left standing rather than removed on somebody's
      death who may not own it.
    */
    if (
      cast.mechanics?.destroyed_on_caster_death === true &&
      cast.player_actor_id !== null &&
      !snap.alive.has(cast.player_actor_id)
    ) {
      continue;
    }
    for (const [index, phase] of wallsOf(cast, snap).entries()) {
      out.push({
        key: `${cast.actor_id}-wall-${index}`,
        cast,
        place: null,
        phase,
        side,
        radiusUu: null,
        detectionUu: null,
      });
    }
    for (const place of cast.placements) {
      if (!PLACED_KINDS.has(place.kind)) {
        continue;
      }
      const phase = phaseOf(cast, place, snap.t_ms);
      if (phase === null) {
        continue;
      }
      out.push({
        key: `${cast.actor_id}-${place.actor_id}`,
        cast,
        place: phase.kind === "flight" ? null : place,
        phase,
        side,
        radiusUu,
        detectionUu,
      });
    }
  }
  return out;
}
