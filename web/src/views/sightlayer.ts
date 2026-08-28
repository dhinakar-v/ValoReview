/**
 * The ink a sight cone is drawn in, shared by both views.
 *
 * `model/sight.ts` is the geometry and is parity-pinned against Python to the
 * bit; this is everything downstream of it that is a *drawing* decision, and it
 * lives in one module because the 2D canvas and the 3D scene used to make those
 * decisions separately and did not agree.  The minimap drew a wedge for every
 * living player and the scene drew exactly one, for whoever happened to be
 * picked, with no hidden-team gate and no smoke occluders at all -- so the same
 * switch meant two different things, and switching to 3D silently dropped nine
 * cones.
 *
 * **This module reads no store.**  It is a pure function of its arguments, and
 * that is load-bearing rather than tidy: `LayersMenu.test.tsx` scrapes
 * `layers.<key>` out of the raw source of `MinimapCanvas.tsx` and `Scene3D.tsx`
 * to check each layer is drawn by exactly the canvases it claims, so a gate
 * moved in here would vanish from both files and fail that guard twice.  Each
 * canvas keeps its own `state.layers.sight` check and calls this with the
 * answer.
 *
 * The wash is flat, and overlap says nothing
 * ------------------------------------------
 * A side's cones are unioned into one shape and that shape is painted at
 * `SIGHT_ALPHA`.  One cone and five overlapping cones read identically, so what
 * the layer states is simply *where that side can see* -- a silhouette of
 * vision, not a count of it.
 *
 * It used to weigh the count: each cone took `1/N` of its side's ink and the
 * overlaps accumulated additively, so k cones over a point read as exactly
 * `k/N` and a full side covering one lane painted it solid.  That answered a
 * second question -- which parts of the map nobody can see -- and it is gone
 * along with `coneAlpha` and its floored denominator.  A flat wash asks the
 * reader to judge nothing, and the overlap gradient it replaces was the reason
 * a lone survivor's cone and a five-man stack's could not be compared by eye.
 *
 * The offscreen buffer survives the change and is still mandatory; see
 * `paintCones` for why, because the reason is no longer the one it was.
 */

import type { MapArt } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { Occluder, SightMask, SightSettings } from "../model/sight";
import { cone, forwardUv, uvRadius } from "../model/sight";
import type { Snapshot } from "../model/state";
import { sideOf } from "../model/synthetic";
import { applyTransform } from "../model/transform";
import { sideColour } from "./images";

/*
  Which placements are the thing an ability left standing, mirroring
  `abilities.PLACING_KINDS`. A smoke is a `GameObject_`, and Omen's is a
  `Zone_`; a `Projectile_` is the throw origin, a median 42 uu from the caster,
  so occluding on one would put the smoke on top of the person who threw it.
*/
const PLACED_KINDS = new Set(["GameObject", "Zone", "Patch"]);

/**
 * The side of the square the 3D overlay is rasterised into.
 *
 * The 2D canvas rasterises in screen space and stays crisp at any zoom; the
 * scene cannot, because what it hands the GPU is a texture on a ground quad.
 * 1024 is the radar's own resolution, which is the line worth holding -- a cone
 * edge is then never coarser than the map it is drawn on.  The cone's *shape*
 * is quantised at `sight.GRID` (256) long before it reaches here, so this is
 * four times finer than the geometry it draws and all the extra resolution buys
 * is a clean antialiased rim.
 */
export const SIGHT_RASTER = 1024;

/**
 * How much ink one side's whole wash gets.
 *
 * One value and not a function of anything: the count of cones, who is alive
 * and how many overlap all stop mattering here.  Deliberately not exported --
 * it is a drawing constant with one call site, and `paintCones` needs a 2D
 * context that jsdom does not provide, so there is nothing that could pin it
 * below the Playwright tier anyway.
 *
 * A quarter and not a half.  At 0.5 a full team's wash took the radar with it:
 * the callouts, the ramps and the site outlines under the shape were all but
 * gone, and this layer is a claim *about* the map that has to be read against
 * it.  What the number has to buy is only that the shape is unmistakable, and
 * a quarter does that over Riot's greys while leaving the map underneath
 * legible.  The pixel suite measures it as a *changed* pixel rather than as a
 * strong one, so its detector moved with this -- see `minimap.spec.ts` and
 * `scene.spec.ts`.
 */
const SIGHT_ALPHA = 0.25;

/**
 * The order the side layers are composited in.
 *
 * Fixed rather than incidental, so the picture is deterministic for the pixel
 * suite: where both sides reach full coverage, whichever blits second wins
 * outright.  Compositing the two layers additively instead would give magenta
 * -- a third colour nothing on this canvas means -- so one of them has to be on
 * top.
 */
const SIDE_ORDER = ["ATK", "DEF"];

/** One cone to draw: the polygon in uv, and the side that owns its colour. */
export interface DrawnCone {
  side: string;
  polygon: Array<[number, number]>;
}

/**
 * The round smokes standing at this instant, as uv circles.
 *
 * Two things about a smoke are looked up rather than decoded -- the radius, and
 * how long it lasts.  A cast with neither is not a smoke and occludes nothing:
 * there is no default size and no default lifetime, because a smoke of a
 * made-up width standing for a made-up time is exactly the plausible wrong
 * answer this project refuses.
 *
 * **Each smoke runs from its own arrival, not from the cast.**  This used to
 * age every placement from `cast.t_ms`, with a note that the wire carried no
 * time on a placement so a thrown smoke started blocking slightly early.  It
 * does now, and "slightly" was worth measuring: across the reference library a
 * thrown thing lands a median 831 ms after the projectile leaves the hand and
 * a p95 of 2.3 s, so a smoke was blocking sight for up to two seconds before
 * it existed -- and a cast that drops several smokes started all of them on
 * the first one's clock.  `place.t_ms` is the instant that channel opened,
 * which is when the smoke is actually there.
 *
 * Expiry is computed here rather than in `abilitiesAt`, which keeps a cast
 * until the round ends on purpose and is parity-tested in both languages.
 */
export function smokesAt(art: MapArt, snap: Snapshot): Occluder[] {
  const out: Occluder[] = [];
  for (const cast of snap.roundCasts) {
    const { smoke_radius_uu: radiusUu, smoke_duration_ms: life } = cast;
    if (radiusUu === null || life === null) {
      continue;
    }
    const radius = uvRadius(art.transform, radiusUu);
    // Every placement, not just `landed`: two smokes from one agent in one
    // round are a single `AbilityCast`, and `landed` names only the first.
    for (const place of cast.placements) {
      if (!PLACED_KINDS.has(place.kind)) {
        continue;
      }
      const age = snap.t_ms - place.t_ms;
      if (age < 0 || age > life) {
        continue;
      }
      const [u, v] = applyTransform(art.transform, place.x, place.y);
      out.push({ u, v, radius });
    }
  }
  return out;
}

/**
 * Every cone that should be on screen at this instant, in uv.
 *
 * No selection anywhere in here: the layer switch is the only control, and a
 * cone is drawn for every living player whose side is shown.  What it must not
 * get wrong is which way somebody is looking, so the heading goes through
 * `forwardUv`, which probes a world point and transforms it rather than doing
 * trigonometry in image space -- that puts every cone ninety degrees out and
 * looks entirely plausible on screen.
 */
export function sightCones(args: {
  model: ReplayModel;
  art: MapArt;
  snap: Snapshot;
  silhouette: SightMask;
  settings: SightSettings;
  shown: (team: string) => boolean;
  smokes: readonly Occluder[];
}): DrawnCone[] {
  const { model, art, snap, silhouette, settings, shown, smokes } = args;
  const reach = uvRadius(art.transform, settings.max_range_uu);
  const out: DrawnCone[] = [];

  for (const player of model.replay.players) {
    // The same gate the marker loops use: a hidden side drawing a cone but no
    // marker would be a new way for the two to disagree.
    if (!shown(player.team)) {
      continue;
    }
    // `snap.positions`, not `positionOf`: that falls back to where somebody
    // died, and a cone at a corpse is a claim about a dead player's vision.
    if (!snap.alive.has(player.actor_id)) {
      continue;
    }
    const position = snap.positions.get(player.actor_id);
    if (position === undefined) {
      continue;
    }
    const polygon = cone(
      silhouette,
      applyTransform(art.transform, position.x, position.y),
      forwardUv(art.transform, position.x, position.y, position.yaw, settings.probe_uu),
      reach,
      settings,
      smokes,
    );
    // An empty cone means draw nothing. Never a fallback circle: a circle where
    // a cone belongs claims the player can see in every direction.
    if (polygon.length < 3) {
      continue;
    }
    out.push({ side: sideOf(model.replay, player.team, snap.t_ms), polygon });
  }

  /*
    A drone sees, and its cone is as decoded as a player's.

    An ability pawn has a real track, and that track carries a yaw that really
    turns -- measured on Owl Drones, it sweeps across a flight (187 to 192
    degrees, 78 to 44, 266 to 325) rather than sitting at whatever it spawned
    at. So this is the same claim about the same map as a player's cone, drawn
    from the same `sight.cone` through the same `forwardUv`, and it belongs
    under the same switch rather than under one of its own.

    *Which* pawns is looked up rather than guessed from the kind: a Boom Bot
    and a Blast Pack are pawns too and neither of them looks at anything, so it
    is `mechanics.sees` -- Sova's Owl Drone and Tejo's Stealth Drone, and
    nothing else until somebody argues for more.

    It costs the wash nothing. `paintCones` unions a side's cones on a scratch
    at full alpha and stamps the union once, so one cone and six read
    identically; a drone adds coverage and cannot darken anything. Under the
    old `1/N` weighting it would have diluted every player's cone by joining
    the denominator, which is one more thing the flat wash bought.
  */
  const teamByActor = new Map<number, string>();
  for (const player of model.replay.players) {
    teamByActor.set(player.actor_id, player.team);
  }
  for (const cast of snap.roundCasts) {
    if (cast.mechanics?.sees !== true || cast.player_actor_id === null) {
      continue;
    }
    const team = teamByActor.get(cast.player_actor_id);
    // Unattributable: two players share the agent, so there is no side to draw
    // it as. The same refusal every other claim about a caster makes here.
    if (team === undefined || !shown(team)) {
      continue;
    }
    for (const actorId of cast.pawns) {
      const here = snap.abilityPositions.get(actorId);
      if (here === undefined) {
        continue;
      }
      const polygon = cone(
        silhouette,
        applyTransform(art.transform, here.x, here.y),
        forwardUv(art.transform, here.x, here.y, here.yaw, settings.probe_uu),
        reach,
        settings,
        smokes,
      );
      if (polygon.length < 3) {
        continue;
      }
      out.push({ side: sideOf(model.replay, team, snap.t_ms), polygon });
    }
  }
  return out;
}

/**
 * A scratch canvas of a given size, made on first use and kept.
 *
 * Lazily, and **never from a component body**: `getContext("2d")` returns null
 * under jsdom and emits a "not implemented" line on the way, so a scratch built
 * in a `useRef` initialiser would fire once per mount in every page test, for a
 * drawing those tests never reach.  Built here, behind the callers' own guards,
 * it costs nothing where there is nothing to draw.
 */
function scratchFor(
  ref: { current: HTMLCanvasElement | null },
  width: number,
  height: number,
): CanvasRenderingContext2D | null {
  let canvas = ref.current;
  if (canvas === null) {
    canvas = document.createElement("canvas");
    ref.current = canvas;
  }
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return canvas.getContext("2d");
}

/**
 * Paint every cone onto `target`: one side's whole union at one flat alpha.
 *
 * Why this still needs a scratch canvas and two composite modes
 * ------------------------------------------------------------
 * The alpha is on the **blit**, not on the fills, and that is the whole reason
 * the buffer survives a flat wash.  Filling each cone onto the target at
 * `SIGHT_ALPHA` directly would composite them against each other -- at a
 * quarter, two cones over a point would read 43.75% and three 57.8%, the
 * saturating curve that the old `1/N` arithmetic was built to escape -- so the
 * union has to be accumulated somewhere that is not the picture, and stamped
 * once.
 *
 * The fills therefore go on at `globalAlpha = 1`, and on `lighter` rather than
 * `source-over`: at full alpha the two agree over a cone's interior, but a
 * `lighter` fill also saturates the antialiased seam where two of one side's
 * polygons abut, where `source-over` leaves a visible rim down the join.  What
 * `lighter` must never touch is the target itself -- it would add to Riot's
 * radar and brighten the map rather than shade it.
 *
 * The colour is then made solid **structurally** rather than arithmetically.
 * The cones are filled in white, so the scratch holds nothing but coverage in
 * its alpha channel, and one `source-in` rectangle stamps the side's colour
 * through it (`Ar = Ad`, `Cr = C`).
 *
 * `target.globalAlpha` is restored afterwards, and that is load-bearing rather
 * than tidy: `MinimapCanvas` draws markers, trails and the spike onto this same
 * context after the cones, and a leaked alpha would half-fade every one of them
 * -- a whole canvas quietly washed out by a layer that had finished drawing.
 *
 * A requirement rather than a preference: **no stroke.**  An outline is a
 * second ink whose weight counts nothing, and it would cut a hard line around
 * the very shape this layer is made of.
 */
export function paintCones(
  target: CanvasRenderingContext2D,
  cones: readonly DrawnCone[],
  colours: Record<string, string>,
  project: (u: number, v: number) => [number, number],
  ref: { current: HTMLCanvasElement | null },
  size: { width: number; height: number; scale: number },
): void {
  if (cones.length === 0) {
    return;
  }
  const bySide = new Map<string, DrawnCone[]>();
  for (const drawn of cones) {
    const found = bySide.get(drawn.side);
    if (found === undefined) {
      bySide.set(drawn.side, [drawn]);
    } else {
      found.push(drawn);
    }
  }
  // The two known sides first, in a fixed order, then anything else sorted, so
  // an unresolved side can never silently reorder the two that matter.
  const sides = [
    ...SIDE_ORDER.filter((side) => bySide.has(side)),
    ...[...bySide.keys()].filter((side) => !SIDE_ORDER.includes(side)).sort(),
  ];

  const context = scratchFor(
    ref,
    Math.round(size.width * size.scale),
    Math.round(size.height * size.scale),
  );
  if (context === null) {
    return;
  }

  for (const side of sides) {
    const group = bySide.get(side)!;

    context.setTransform(size.scale, 0, 0, size.scale, 0, 0);
    context.clearRect(0, 0, size.width, size.height);
    context.globalCompositeOperation = "lighter";
    context.globalAlpha = 1;
    context.fillStyle = "#ffffff";
    for (const { polygon } of group) {
      context.beginPath();
      polygon.forEach(([u, v], i) => {
        const [x, y] = project(u, v);
        if (i === 0) {
          context.moveTo(x, y);
        } else {
          context.lineTo(x, y);
        }
      });
      context.closePath();
      context.fill();
    }
    // Stamp the side's colour through the coverage those fills accumulated.
    context.globalCompositeOperation = "source-in";
    context.globalAlpha = 1;
    context.fillStyle = sideColour(colours, side);
    context.fillRect(0, 0, size.width, size.height);
    // Back to the default, or the next side's `clearRect` composites rather
    // than clearing and this frame's ATK bleeds into its DEF.
    context.globalCompositeOperation = "source-over";

    target.globalAlpha = SIGHT_ALPHA;
    target.drawImage(context.canvas, 0, 0, size.width, size.height);
    target.globalAlpha = 1;
  }
}
