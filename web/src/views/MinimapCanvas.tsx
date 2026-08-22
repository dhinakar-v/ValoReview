/**
 * Agents on Riot's own minimap, where the replication stream said they were.
 *
 * A port of `vrfview.minimap`, including the two rules that make it honest.
 *
 * **Where `trackAt` returns null, this draws nothing.**  There is no
 * last-known-place fallback: the track already refused, and inventing a dot
 * downstream of a refusal is exactly what the refusal exists to prevent.  A
 * player who has died is pinned at the coordinate they died on and drawn with a
 * different glyph, because a corpse shown as a live agent is a lie about where
 * five people are.
 *
 * **Facing lines never do trigonometry in screen space.**  A second world
 * point 100 uu ahead along the yaw goes through the same transform and the
 * difference is renormalised.  The transform swaps the axes and either
 * multiplier may be negative, so screen-space trig puts every heading ninety
 * degrees out -- and it looks entirely plausible, which is why it is worth a
 * paragraph.
 *
 * What replaced the stipple
 * -------------------------
 * A Tk canvas has no alpha, so a wash had to be a `gray25` stipple and a fade
 * had to be `theme.blend` mixing a colour toward the background.  Both are
 * gone: this has `globalAlpha`.
 *
 * Drawing, not reconciling
 * ------------------------
 * The canvas runs its own animation frame and reads the playhead out of
 * `usePlayback.getState()`.  Nothing here is React state per frame, so a frame
 * costs ten binary searches and a few dozen canvas calls rather than a render
 * pass over the page.
 */

import { useCallback, useEffect, useMemo, useRef } from "react";

import type { AbilityCast, MapArt, Player, SightMaskDoc } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { SightMask, SightSettings } from "../model/sight";
import type { Occluder } from "../model/sight";
import { decodeMask, uvRadius } from "../model/sight";
import type { Snapshot } from "../model/state";
import { positionOf, spikeLocation, stateAt } from "../model/state";
import { segments } from "../model/track";
import type { Box } from "../model/transform";
import { applyTransform, placeSquare, uvToPixels } from "../model/transform";
import { sideOf } from "../model/synthetic";
import { markerScale, panBy, viewBox, zoomAt } from "../model/viewport";
import { palette, sideColour, useImages } from "./images";
import { usePlayback, selectedActor, teamShown } from "./playback";
import { paintCones, sightCones, smokesAt } from "./sightlayer";

/** Marker sizes, in CSS pixels, carried over from the desktop viewer. */
const AVATAR_PX = 26;
const DOT_RADIUS = 7;
/*
 * A utility marker's half-size.
 *
 * One constant where there were two at 5 and 6, and bigger than both: the
 * marker carries Riot's ability icon now instead of a name printed beside it,
 * and that art is white line work that is unrecognisable inside a ten-pixel
 * box.  Sixteen across, against the players' twenty-six, keeps utility
 * visibly subordinate to people while staying identifiable.
 */
const UTILITY_HALF = 8;

/**
 * The facing mark: a triangle on the ring, not a line out of it.
 *
 * A line reads as a laser -- something the player is doing -- where a triangle
 * on the edge of the ring reads as the ring having a front, which is what a
 * heading is.  The reference frames draw the same shape, and at three times the
 * size on a picked-out marker it is still one mark rather than a longer line.
 */
const FACING_LENGTH = 11;
const FACING_HALF = 6;

/** How much larger a hovered or pinned marker is drawn. */
const PICKED_SCALE = 3;

/*
 * The death X's arm, in CSS pixels before the zoom scale.
 *
 * One constant where there were two: `KILL_MARK` sized the kill cross and
 * `DEAD_RADIUS` the dead player's own circle, and both were drawn at the same
 * point on the same player.  See `drawDeathMark`.
 */
const DEATH_MARK = 5;

/** How far right of a marker the hover card sits, matching the reference. */
const TIP_OFFSET_PX = 14;

/** Half-height of the spike triangle at fit zoom. */
const SPIKE_HALF = 8;

/*
 * How far a *mark* is allowed to grow with the zoom.
 *
 * `markerScale` reaches 2.2x, which is right for a person -- they occupy room
 * in the world, so they grow with it.  An annotation does not: a map pin does
 * not get bigger when you zoom the map, and a death cross or a spike that
 * doubled would start competing with the players it sits under.  1.4 is the
 * cap the agent label used before it was removed.
 */
const MARK_SCALE_CAP = 1.4;

/**
 * How far ahead the facing probe is placed, in Unreal units.
 *
 * Any distance works -- the line is renormalised to `FACING_LENGTH` pixels --
 * so this only has to be large enough to survive the transform's precision.
 */
const FACING_PROBE_UU = 100;

/** How far back along an ability pawn's own path is drawn, in playback ms. */
const PAWN_TRAIL_MS = 20000;

/** And how far back a player's, which is a new layer rather than a port. */
const PLAYER_TRAIL_MS = 8000;

/**
 * How hard the wheel bites.
 *
 * Exponential in the wheel delta rather than linear, so a trackpad's many small
 * events and a mouse wheel's few large ones cover the same ground -- a linear
 * step tuned for one makes the other unusable.
 */
const WHEEL_SENSITIVITY = 0.0016;

/*
 * The canvas type stack, named once.
 *
 * A canvas cannot inherit a font, so this is the one place in the interface
 * where the bundled faces have to be repeated as a string.  Plus Jakarta Sans
 * is the page's UI face and is loaded by the time anything is drawn -- and the
 * tail is the same fallback the stylesheet uses, so a checkout with the woff2
 * files stripped renders the labels in the same face as the page around them.
 *
 * This string and `--font-ui` in tokens.css are the same decision written
 * twice, which is the one duplication this interface cannot design away: the
 * 2D canvas is the thing the Playwright suite photographs, and a label drawn
 * in a different face from the page around it is exactly the kind of drift
 * nobody notices until a screenshot is compared with one from last month.
 * Change one, change the other.
 */
const LABEL_FONT = '"Plus Jakarta Sans", "Segoe UI", system-ui, sans-serif';

/** A dark keyline under a label, because the radar is bright in places. */
const LABEL_OUTLINE = 3;

/** The zoom at which there is room to name every marker rather than one. */
const LABEL_FROM_SCALE = 1.6;

export interface MinimapProps {
  model: ReplayModel;
  art: MapArt;
  radar: HTMLImageElement | undefined;
  mask: SightMaskDoc | null;
}

interface Hit {
  x: number;
  y: number;
  /** The drawn radius, so a zoomed marker is as easy to hit as it looks. */
  radius: number;
  player: Player;
}

export function MinimapCanvas({ model, art, radar, mask }: MinimapProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const hitsRef = useRef<Hit[]>([]);
  const boxRef = useRef<Box>({ left: 0, top: 0, side: 0 });
  /** The un-zoomed square, which is what the camera arithmetic works from. */
  const fitRef = useRef<Box>({ left: 0, top: 0, side: 0 });
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  /**
   * Where the sight cones are accumulated before they reach this canvas.
   *
   * Held across frames rather than made per frame, and deliberately empty here:
   * `paintCones` builds it on first use, so a page test that never draws a cone
   * never asks jsdom for a 2D context it does not have.
   */
  const sightScratch = useRef<HTMLCanvasElement | null>(null);

  const icons = useImages(model.replay.players.map((player) => player.icon_url));
  const iconFor = useMemo(() => {
    const out = new Map<number, HTMLImageElement>();
    for (const player of model.replay.players) {
      const found = player.icon_url ? icons.get(player.icon_url) : undefined;
      if (found) {
        out.set(player.actor_id, found);
      }
    }
    return out;
  }, [icons, model]);

  /*
    Riot's ability art, keyed by url the way the agent portraits are.

    `useImages` never throws and never blocks -- a url that 404s simply never
    arrives in the map -- so a marker falls back to its keybind character
    rather than to a gap.  Keyed by url and not by cast, because the same
    ability cast forty times in a match is one picture.
  */
  const castIcons = useImages(
    useMemo(() => model.replay.ability_casts.map((cast) => cast.icon_url), [model]),
  );

  const silhouette = useMemo<SightMask | null>(
    () => (mask ? decodeMask(mask.size, mask.cells) : null),
    [mask],
  );
  const settings = useMemo<SightSettings | null>(
    () =>
      mask
        ? {
            max_range_uu: mask.max_range_uu,
            fov_degrees: mask.fov_degrees,
            ray_step_degrees: mask.ray_step_degrees,
            seed_cells: mask.seed_cells,
            probe_uu: mask.probe_uu,
          }
        : null,
    [mask],
  );

  const draw = useCallback(
    (canvas: HTMLCanvasElement) => {
      const context = canvas.getContext("2d");
      if (context === null) {
        return;
      }
      const colours = palette(canvas);
      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);

      // Two boxes, and the difference matters.  `fit` is what `placeSquare`
      // gives -- the largest centred square, and what every pixel assertion in
      // `e2e/minimap.spec.ts` computes from.  `box` is that square after the
      // viewport, and at rest the two are the same numbers: `FIT` is the
      // identity, so default zoom is bit-identical to a build with no camera.
      const fit = placeSquare(width, height);
      const state = usePlayback.getState();
      const scale = markerScale(state.viewport);
      const box = viewBox(fit, state.viewport);
      fitRef.current = fit;
      boxRef.current = box;

      const snap = stateAt(model, state.tMs);

      if (radar) {
        context.drawImage(radar, box.left, box.top, box.side, box.side);
      }
      context.strokeStyle = colours.border!;
      context.lineWidth = 1;
      context.strokeRect(box.left + 0.5, box.top + 0.5, box.side - 1, box.side - 1);
      // Nothing else: the radar's own alpha channel is 57-72% transparent, so
      // the canvas background *is* the map's negative space and a fill here
      // would be a shape this project has no data for.

      const world = (x: number, y: number): [number, number] => {
        const [u, v] = applyTransform(art.transform, x, y);
        return uvToPixels(box, u, v);
      };
      // Unreal units to pixels on this frame's box, for the one thing drawn at
      // a radius rather than at a coordinate.
      const uvRadiusOf = (uu: number) => uvRadius(art.transform, uu) * box.side;

      // The draw order is the z-order, and it is the desktop viewer's: the cone
      // is a wash under everything, then ability paths, then utility, then the
      // players on top -- because a player hidden behind their own utility is
      // the one thing on this canvas nobody can afford to lose.
      if (state.layers.sight && silhouette && settings) {
        drawSight(context, {
          model,
          art,
          snap,
          box,
          colours,
          silhouette,
          settings,
          shown: (team: string) => teamShown(state, team),
          smokes: smokesAt(art, snap),
          scratch: sightScratch,
          size: { width, height, scale: dpr },
        });
      }
      if (state.layers.trails) {
        drawPlayerTrails(context, { model, snap, world, colours });
      }
      /*
        There was a whole reservation pass here: the players claimed their icon
        boxes so that a utility *name* printed beside a marker would be dropped
        rather than painted across a face.  Both the names and the machinery
        are gone -- a marker carries Riot's ability icon inside its own box now,
        and a mark that cannot leave its box cannot collide with anything.
      */
      if (state.layers.utility) {
        drawAbilities(context, {
          model,
          snap,
          world,
          uvRadiusOf,
          colours,
          icons: castIcons,
          showRange: state.layers.abilityRange,
        });
      }
      /*
        The spike, if it is on the ground.

        Deliberately not behind a layer switch.  The nine switches are grouped
        MAP and TIMELINE, and `spike` sits under TIMELINE where it gates the
        rail's event ticks; the planted spike is not an overlay on the round,
        it *is* the round, in the same category as the player markers -- which
        have no switch either.  It draws under the players for the same reason
        everything else does: a player hidden behind an object is the one thing
        this canvas cannot afford to lose.
      */
      drawSpike(context, { model, snap, world, colours, scale });

      const hits: Hit[] = [];
      const chosenId = selectedActor(state);
      for (const player of model.replay.players) {
        if (!teamShown(state, player.team)) {
          continue;
        }
        const alive = snap.alive.has(player.actor_id);
        /*
          KILL MARKERS now decides whether the dead are drawn at all, which is
          a switch that means something: on, the map shows where each player
          died this round; off, it shows only the living.  It used to gate a
          second mark drawn on top of the first.
        */
        if (!alive && !state.layers.killMarkers) {
          continue;
        }
        const position = positionOf(snap, player.actor_id);
        if (position === null) {
          continue;
        }
        const [x, y] = world(position.x, position.y);
        // By side, not by team: every surface in the interface derives from the
        // same two colours, and a card that swaps at halftime while its marker
        // does not is the one inconsistency a viewer would actually notice.
        const colour = sideColour(colours, sideOf(model.replay, player.team, snap.t_ms));
        const chosen = chosenId === player.actor_id;
        // The picked-out marker is three times the size, which is the
        // reference's own treatment: about 104px against a 26px base. It is
        // what makes one player findable inside a five-man stack.
        const radius = (AVATAR_PX * scale * (chosen ? PICKED_SCALE : 1)) / 2;

        if (alive) {
          drawFacing(context, { x, y, position, world, colour, radius });
          drawAlive(context, {
            x,
            y,
            radius,
            colour,
            ring: chosen ? colours.text! : colour,
            icon: iconFor.get(player.actor_id),
            background: colours.background!,
          });
        } else {
          drawDeathMark(context, { x, y, colour, keyline: colours.canvas!, scale });
        }

        /*
          A name, but not ten of them.

          This drew `player.label` under every marker unconditionally -- A1,
          A2, B4 -- which is two problems in one string.  The labels are the
          inferred group, and this interface says ATK and DEF; and ten of them
          at fit zoom, where five players stand in one spawn, is a smear rather
          than a roster.  So the name is the **agent**, which is what a viewer
          recognises, and it is drawn for whoever is being pointed at, or once
          the map has been zoomed in far enough for ten of them to have room.
          The reference frames draw no names at fit zoom at all.

          Outline then fill: a white label over Ascent's pale mid is unreadable
          without one, and a drop shadow costs a composite per player per frame
          where a stroke costs nothing.
        */
        if (chosen || state.viewport.scale >= LABEL_FROM_SCALE) {
          const label = player.agent || player.codename || player.label;
          const labelY = y - radius - 7;
          const size = Math.round(10 * Math.min(scale, 1.4));
          context.font = `600 ${size}px ${LABEL_FONT}`;
          context.textAlign = "center";
          context.lineJoin = "round";
          context.lineWidth = LABEL_OUTLINE;
          context.strokeStyle = colours.canvas!;
          context.strokeText(label, x, labelY);
          context.fillStyle = alive ? colours.text! : colours.muted!;
          context.fillText(label, x, labelY);
        }
        hits.push({ x, y, radius, player });
      }
      hitsRef.current = hits;
    },
    [art, iconFor, model, radar, settings, silhouette],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    let frame = 0;
    const loop = () => {
      draw(canvas);
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [draw]);

  const at = (event: React.MouseEvent<HTMLCanvasElement>): Hit | null => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    for (const hit of hitsRef.current) {
      // The drawn radius plus a few pixels of forgiveness, so a marker is as
      // easy to hit at 4x as it is at rest rather than four times easier.
      const reach = (hit.radius + 4) ** 2;
      if ((x - hit.x) ** 2 + (y - hit.y) ** 2 <= reach) {
        return hit;
      }
    }
    return null;
  };

  /*
    The wheel listener is attached by hand rather than through `onWheel`,
    because React attaches its own passively and a passive listener may not
    call `preventDefault` -- so every zoom would also scroll whatever is behind
    the canvas.  There is nothing to scroll on this page, which makes it look
    like it works right up until the window is short.
  */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * WHEEL_SENSITIVITY);
      usePlayback.setState((state) => ({
        viewport: zoomAt(
          fitRef.current,
          state.viewport,
          event.clientX - rect.left,
          event.clientY - rect.top,
          factor,
        ),
      }));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="minimap"
      onMouseMove={(event) => {
        const drag = dragRef.current;
        if (drag !== null) {
          const dx = event.clientX - drag.x;
          const dy = event.clientY - drag.y;
          dragRef.current = { x: event.clientX, y: event.clientY };
          usePlayback.setState((state) => ({
            viewport: panBy(fitRef.current, state.viewport, dx, dy),
          }));
          return;
        }
        const hit = at(event);
        // The hit-test coordinate the canvas already has, published so the
        // tooltip can anchor to it. Projecting the world position a second
        // time in DOM space would be a copy of the transform, and two copies
        // of a transform are two chances to disagree about where a marker is.
        // Offset here rather than in `MarkerTip`: the store holds where the
        // tip goes, and a roster card raising the same tip needs a different
        // offset from a marker's.  See `RosterPanel.tipAnchor`.
        usePlayback.setState({
          hovered: hit?.player.actor_id ?? null,
          hoveredAt: hit === null ? null : { x: hit.x + TIP_OFFSET_PX, y: hit.y },
        });
      }}
      onMouseDown={(event) => {
        // Panning starts only away from a marker, so a click on somebody is
        // still a click on somebody.
        if (at(event) === null) {
          dragRef.current = { x: event.clientX, y: event.clientY };
        }
      }}
      onMouseUp={() => {
        dragRef.current = null;
      }}
      onMouseLeave={() => {
        dragRef.current = null;
        usePlayback.setState({ hovered: null, hoveredAt: null });
      }}
      onDoubleClick={() => usePlayback.getState().resetViewport()}
      onClick={(event) =>
        usePlayback.getState().toggleSelected(at(event)?.player.actor_id ?? null)
      }
    />
  );
}

/**
 * The planted spike, at the coordinate the plant actor spawned at.
 *
 * Amber, and that is a constraint rather than a taste: `--spike-armed` was
 * `#ff5252` until this landed, which is **12 RGB** from `--team-a` -- inside
 * the 36 `minimap.spec.ts` counts as "this pixel is a player marker".  A red
 * spike was not merely hard to tell from an attacker, it was arithmetically
 * the same colour.  See `libraries/vrfview/theme.py`.
 *
 * An upward triangle, because the canvas vocabulary is closed and every member
 * has to be distinct at six pixels: circle is a living person, square a live
 * ability pawn, hollow diamond a landed cast, X a death, and this is the only
 * filled triangle standing on its own.
 *
 * Near-constant in screen space, like the death mark: the spike is a thing
 * being pointed at rather than a person occupying room, and a marker that
 * grows to 2.2x competes with the players it is meant to sit under.
 */
function drawSpike(
  context: CanvasRenderingContext2D,
  args: {
    model: ReplayModel;
    snap: Snapshot;
    world: (x: number, y: number) => [number, number];
    colours: Record<string, string>;
    scale: number;
  },
): void {
  const { model, snap, world, colours, scale } = args;
  const at = spikeLocation(model, snap);
  if (at === null) {
    return;
  }
  const [x, y] = world(at.x, at.y);
  const half = SPIKE_HALF * Math.min(Math.max(scale, 0.9), MARK_SCALE_CAP);
  const path = new Path2D();
  path.moveTo(x, y - half);
  path.lineTo(x + half * 0.9, y + half * 0.7);
  path.lineTo(x - half * 0.9, y + half * 0.7);
  path.closePath();

  context.save();
  // Keyline first, so the mark reads over Ascent's pale mid as well as over
  // the dark void -- the same trick the player label used before it went.
  context.lineWidth = 3;
  context.strokeStyle = colours.canvas!;
  context.stroke(path);
  context.fillStyle = colours.spikeArmed!;
  context.fill(path);
  // A ring at a fixed radius, so the eye finds it in a crowded site without
  // the mark itself having to be large enough to cover somebody.
  context.beginPath();
  context.arc(x, y, half * 2.1, 0, Math.PI * 2);
  context.globalAlpha = 0.55;
  context.lineWidth = 1;
  context.strokeStyle = colours.spikeArmed!;
  context.stroke();
  context.restore();
}


/**
 * Every living player's approximate view cone, one wedge each.
 *
 * Nobody is picked out any more, and that is the point rather than a
 * simplification.  This drew one cone for a selected player once, then ten at
 * two different weights so the selection still read; both made the switch mean
 * something about *a player* when the question it answers is about the map --
 * which parts of it nobody can see.  A selection has nothing to say about that,
 * so the marker keeps `PICKED_SCALE` and the cone does not.
 *
 * The weight is the count instead: `sightlayer.paintCones` gives each cone
 * `1/N` of its side's ink and accumulates overlap additively, so k cones over a
 * point read as exactly `k/N` and a full side covering one lane paints it
 * solid.  No stroke -- an outline is a second ink that counts nothing and cuts
 * a hard line through the gradient this layer is made of.
 *
 * `Scene3D` paints the identical picture from the identical two functions, at
 * the identical alphas; the only difference is that it rasterises in uv onto a
 * ground quad where this rasterises in screen space.
 */
function drawSight(
  context: CanvasRenderingContext2D,
  args: {
    model: ReplayModel;
    art: MapArt;
    snap: Snapshot;
    box: Box;
    colours: Record<string, string>;
    silhouette: SightMask;
    settings: SightSettings;
    shown: (team: string) => boolean;
    smokes: readonly Occluder[];
    scratch: { current: HTMLCanvasElement | null };
    size: { width: number; height: number; scale: number };
  },
): void {
  const { model, art, snap, box, colours, silhouette, settings } = args;
  const { shown, smokes, scratch, size } = args;

  paintCones(
    context,
    sightCones({ model, art, snap, silhouette, settings, shown, smokes }),
    colours,
    (u, v) => uvToPixels(box, u, v),
    scratch,
    size,
  );
}

/**
 * Where each ability pawn has been, and where each cast came to rest.
 *
 * Two different claims, drawn as two different things.  A pawn has a track and
 * moves; a smoke has one coordinate and never moves, and until the spawn
 * transform was measured it had none at all.  Neither is a player, so neither
 * is a circle.
 */
function drawAbilities(
  context: CanvasRenderingContext2D,
  args: {
    model: ReplayModel;
    snap: Snapshot;
    world: (x: number, y: number) => [number, number];
    uvRadiusOf: (uu: number) => number;
    colours: Record<string, string>;
    icons: Map<string, HTMLImageElement>;
    showRange: boolean;
  },
): void {
  const { model, snap, world, uvRadiusOf, colours, icons, showRange } = args;
  const byActor = new Map<number, Player>();
  for (const player of model.replay.players) {
    byActor.set(player.actor_id, player);
  }

  for (const cast of snap.roundCasts) {
    /*
      By **side**, like every other marker on this canvas.

      This used `teamColour` and re-derived the caster from the codename by
      hand, which meant two things went wrong quietly: an ability marker kept
      its opening colour across the halftime swap while the players beside it
      changed, and the join was a second implementation of
      `abilities.attribute()`.  `player_actor_id` is now on the wire, refused
      where a codename is ambiguous, so this is a lookup.
    */
    const caster = cast.player_actor_id === null ? undefined : byActor.get(cast.player_actor_id);
    const colour =
      caster === undefined
        ? colours.unknown!
        : sideColour(colours, sideOf(model.replay, caster.team, snap.t_ms));
    const icon = cast.icon_url === null ? undefined : icons.get(cast.icon_url);

    for (const actorId of cast.pawns) {
      const here = snap.abilityPositions.get(actorId);
      if (here === undefined) {
        continue;
      }
      const track = model.abilityTracks.get(actorId);
      if (track) {
        drawTrail(context, track, snap.t_ms - PAWN_TRAIL_MS, snap.t_ms, world, colour, 0.45);
      }
      const [x, y] = world(here.x, here.y);
      drawRange(context, { x, y, cast, colour, uvRadiusOf, show: showRange });
      // A square, so it is never mistaken for a player: circles are people and
      // squares are utility, and at this size that has to survive a glance.
      context.fillStyle = colour;
      context.strokeStyle = colours.background!;
      context.lineWidth = 1;
      context.fillRect(x - UTILITY_HALF, y - UTILITY_HALF, UTILITY_HALF * 2, UTILITY_HALF * 2);
      context.strokeRect(x - UTILITY_HALF, y - UTILITY_HALF, UTILITY_HALF * 2, UTILITY_HALF * 2);
      drawUtilityMark(context, { x, y, icon, cast, colours, over: colours.background! });
    }

    // A cast with no pawn: one coordinate, no path, and no arc anywhere. The
    // hollow diamond says "something is here" without implying it moved.
    if (cast.landed === null) {
      continue;
    }
    const [x, y] = world(cast.landed.x, cast.landed.y);
    drawRange(context, { x, y, cast, colour, uvRadiusOf, show: showRange });
    context.save();
    context.translate(x, y);
    context.rotate(Math.PI / 4);
    context.globalAlpha = 0.85;
    context.strokeStyle = colour;
    context.lineWidth = 2;
    context.strokeRect(-UTILITY_HALF, -UTILITY_HALF, UTILITY_HALF * 2, UTILITY_HALF * 2);
    // Restored *before* the mark: the diamond is the marker and the icon is
    // the identity, and an ability icon rotated 45 degrees stops being
    // recognisable as itself.
    context.restore();
    drawUtilityMark(context, { x, y, icon, cast, colours, over: colours.canvas! });
  }
}

/**
 * What a utility marker says it is: Riot's icon, or the keybind it was cast on.
 *
 * The marker used to carry `\`${cast.slot} ${cast.internal_name}\`` as text
 * beside it -- `Q Possessable Camera` across the map at nine pixels, colliding
 * with the geometry underneath and with every other cast in the same site.
 * The icon identifies the ability the way the agent portrait identifies the
 * player, and it cannot smear because it sits inside the marker's own box.
 *
 * `icon_url` resolves for X and C only: `art.AgentArt.ability` refuses Q and E
 * because Riot's `Ability1`/`Ability2` map to them in an order that varies by
 * agent, and the archetype path's own letters do not track the game's current
 * keybinds either -- see `vrfview.abilityfacts`.  So the fallback is the one
 * character that **was** read rather than guessed: the slot the path named.
 * One glyph inside the box, which is why the label-collision machinery this
 * canvas used to need is gone.
 */
function drawUtilityMark(
  context: CanvasRenderingContext2D,
  args: {
    x: number;
    y: number;
    icon: HTMLImageElement | undefined;
    cast: AbilityCast;
    colours: Record<string, string>;
    over: string;
  },
): void {
  const { x, y, icon, cast, colours, over } = args;
  if (icon !== undefined) {
    const box = UTILITY_HALF * 2 - 2;
    context.drawImage(icon, x - box / 2, y - box / 2, box, box);
    return;
  }
  context.save();
  context.font = `700 9px ${LABEL_FONT}`;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillStyle = over === colours.canvas! ? colours.text! : over;
  context.fillText(cast.slot, x, y + 0.5);
  context.restore();
}

/**
 * A published radius, drawn dashed because nothing in this capture states it.
 *
 * Every other geometry on this canvas is a solid stroke around something that
 * was decoded, so **dashed is the token that means generated** -- the canvas's
 * equivalent of the SIMULATED chip on the stage head.  The figure is looked up
 * in `vrfview.abilityfacts`, which is community research about a game that
 * rebalances every few weeks, and the layer that switches it on is labelled
 * `RANGE (SIM)` for the same reason.
 *
 * Off unless asked for, and absent entirely for the many abilities nobody
 * publishes a radius for: a ring at a made-up size is worse than no ring.
 */
function drawRange(
  context: CanvasRenderingContext2D,
  args: {
    x: number;
    y: number;
    cast: AbilityCast;
    colour: string;
    uvRadiusOf: (uu: number) => number;
    show: boolean;
  },
): void {
  const { x, y, cast, colour, uvRadiusOf, show } = args;
  if (!show || cast.range_uu === null) {
    return;
  }
  const radius = uvRadiusOf(cast.range_uu);
  if (!Number.isFinite(radius) || radius <= 0) {
    return;
  }
  context.save();
  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.globalAlpha = 0.12;
  context.fillStyle = colour;
  context.fill();
  context.globalAlpha = 0.4;
  context.setLineDash([4, 4]);
  context.lineWidth = 1;
  context.strokeStyle = colour;
  context.stroke();
  context.restore();
}

function drawPlayerTrails(
  context: CanvasRenderingContext2D,
  args: {
    model: ReplayModel;
    snap: Snapshot;
    world: (x: number, y: number) => [number, number];
    colours: Record<string, string>;
  },
): void {
  const { model, snap, world, colours } = args;
  for (const player of model.replay.players) {
    const track = model.positions.get(player.actor_id);
    if (track === undefined) {
      continue;
    }
    drawTrail(
      context,
      track,
      snap.t_ms - PLAYER_TRAIL_MS,
      snap.t_ms,
      world,
      sideColour(colours, sideOf(model.replay, player.team, snap.t_ms)),
      0.35,
    );
  }
}

/**
 * One track's recent path, split where the record goes quiet.
 *
 * `segments` refuses to join two samples more than `MAX_INTERPOLATE_MS` apart,
 * for the same reason `trackAt` refuses to interpolate across that gap: the
 * straight line would cross whatever is between the two points.  The desktop
 * viewer joined every sample in its window regardless, which was an
 * inconsistency with its own track lookup; both ports split.
 */
function drawTrail(
  context: CanvasRenderingContext2D,
  track: { actor_id: number; samples: Array<{ t_ms: number; x: number; y: number }> },
  fromMs: number,
  toMs: number,
  world: (x: number, y: number) => [number, number],
  colour: string,
  alpha: number,
): void {
  const pieces = segments(track as Parameters<typeof segments>[0], fromMs, toMs);
  if (pieces.length === 0) {
    return;
  }
  context.save();
  context.globalAlpha = alpha;
  context.strokeStyle = colour;
  context.lineWidth = 2;
  context.lineJoin = "round";
  for (const piece of pieces) {
    context.beginPath();
    piece.forEach((sample, i) => {
      const [x, y] = world(sample.x, sample.y);
      if (i === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    });
    context.stroke();
  }
  context.restore();
}

/**
 * Which way the player is looking, as a triangle sitting on the ring.
 *
 * The heading still comes from a world-space probe run through the transform,
 * which is the one thing about this that must not change: the transform swaps
 * the axes and either multiplier may be negative, so trigonometry in screen
 * space puts every marker ninety degrees out -- and it looks entirely plausible
 * on a map nobody has memorised, which is why it is worth a paragraph.
 *
 * What changed is the shape.  A line out of the ring reads as something the
 * player is doing; a triangle on the ring reads as the ring having a front.
 */
function drawFacing(
  context: CanvasRenderingContext2D,
  args: {
    x: number;
    y: number;
    position: { x: number; y: number; yaw: number };
    world: (x: number, y: number) => [number, number];
    colour: string;
    radius: number;
  },
): void {
  const { x, y, position, world, colour, radius } = args;
  // The probe, not screen-space trigonometry. See above.
  const radians = (position.yaw * Math.PI) / 180;
  const [tipX, tipY] = world(
    position.x + FACING_PROBE_UU * Math.cos(radians),
    position.y + FACING_PROBE_UU * Math.sin(radians),
  );
  const dx = tipX - x;
  const dy = tipY - y;
  const length = Math.sqrt(dx * dx + dy * dy);
  if (length <= 0) {
    return;
  }
  // A unit heading and its perpendicular, both in screen space now that the
  // direction itself has been through the transform.
  const ux = dx / length;
  const uy = dy / length;
  const reach = radius * (FACING_LENGTH / (AVATAR_PX / 2));
  const half = FACING_HALF * (radius / (AVATAR_PX / 2));
  const baseX = x + ux * radius;
  const baseY = y + uy * radius;

  context.beginPath();
  context.moveTo(baseX + ux * reach, baseY + uy * reach);
  context.lineTo(baseX - uy * half, baseY + ux * half);
  context.lineTo(baseX + uy * half, baseY - ux * half);
  context.closePath();
  context.fillStyle = colour;
  context.fill();
}

/**
 * Where each player died this round.
 *
 * `Snapshot.death_positions` is the last place the event stream saw somebody
 * before their `characterDeath`, so this is read rather than derived -- and it
 * is scoped to the round, which is why a mark disappears at the next round
 * start instead of accumulating across a match.
 *
 * A cross and not a portrait: the player is not there any more, and a marker
 * that still looks like a person is a lie about where five people are.
 */
/**
 * Where a player died: one X, drawn once.
 *
 * This replaces two marks that were both drawn at the same point.  `positionOf`
 * falls back to `deathPositions`, so a dead player's own marker already sat on
 * their death coordinate -- and with KILL MARKERS on (the default) they also
 * got a cross and a concentric circle here.  Two circles and five strokes
 * inside fourteen pixels at two different transparencies is the "fuzzy blue
 * smudge that reads as a marker for something alive" the UI review reported,
 * and no redesign of either shape alone would have fixed it, because the
 * problem was that there were two.
 *
 * A bare X with no enclosure, because the canvas vocabulary has to stay
 * distinguishable at six pixels and **an X has no interior**: a circle, a
 * square and a diamond all collapse into a blob at that size and an X cannot.
 * Circle is a living person, square a live ability pawn, hollow diamond a
 * landed cast, filled triangle the spike, and this is the only bare cross.
 *
 * Keyline first and then the mark, which is how the agent label used to stay
 * readable over Ascent's pale mid before it was removed.  Fully opaque: the
 * old 0.55 and 0.8 were half the illegibility, and a stroke blended toward the
 * radar underneath can also drift outside the 36-RGB window `minimap.spec.ts`
 * counts as a team colour -- so a dead player was being *checked* by luck as
 * well as read by squinting.
 */
function drawDeathMark(
  context: CanvasRenderingContext2D,
  args: { x: number; y: number; colour: string; keyline: string; scale: number },
): void {
  const { x, y, colour, keyline, scale } = args;
  const arm = DEATH_MARK * Math.min(Math.max(scale, 0.85), MARK_SCALE_CAP);
  const path = new Path2D();
  path.moveTo(x - arm, y - arm);
  path.lineTo(x + arm, y + arm);
  path.moveTo(x - arm, y + arm);
  path.lineTo(x + arm, y - arm);

  context.save();
  context.lineCap = "square";
  context.lineWidth = 4;
  context.strokeStyle = keyline;
  context.stroke(path);
  context.lineWidth = 2;
  context.strokeStyle = colour;
  context.stroke(path);
  context.restore();
}

function drawAlive(
  context: CanvasRenderingContext2D,
  args: {
    x: number;
    y: number;
    radius: number;
    colour: string;
    ring: string;
    icon: HTMLImageElement | undefined;
    background: string;
  },
): void {
  const { x, y, radius, colour, ring, icon, background } = args;
  if (icon) {
    // The ring is drawn first and slightly proud of the portrait, so the team
    // colour survives an agent icon with a pale border.
    context.beginPath();
    context.arc(x, y, radius + 2, 0, Math.PI * 2);
    context.fillStyle = colour;
    context.fill();
    context.strokeStyle = ring;
    context.lineWidth = 2;
    context.stroke();

    context.save();
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.clip();
    context.drawImage(icon, x - radius, y - radius, radius * 2, radius * 2);
    context.restore();
    return;
  }
  // No icon: a filled dot, which is visibly a marker rather than a portrait
  // that failed to load.
  context.beginPath();
  context.arc(x, y, Math.max(DOT_RADIUS, radius * 0.55), 0, Math.PI * 2);
  context.fillStyle = colour;
  context.fill();
  context.strokeStyle = ring === colour ? background : ring;
  context.lineWidth = 2;
  context.stroke();
}


/*
 * There was a label-collision system here -- `LabelBox`, `overlaps`,
 * `labelSpace`, `reserve` and `label` -- about ninety lines of it.
 *
 * It existed for one reason: utility markers printed their name beside them
 * (`Q Possessable Camera`), and a name is wider than the thing it names, so
 * two casts in one site smeared into each other and a cast behind a player
 * painted itself across their face.  The machinery reserved each player's icon
 * box first and then dropped any label that would not fit.
 *
 * The names are gone -- a marker carries Riot's ability icon inside its own
 * box now, and the one text fallback is a single keybind character drawn in
 * the centre of that box.  A mark that cannot leave its box cannot collide
 * with anything, so there is nothing left to arbitrate.
 */

