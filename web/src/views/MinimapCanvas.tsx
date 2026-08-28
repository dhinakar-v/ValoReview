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
import type { Point } from "./castlayer";
import { castsAt, phaseOf } from "./castlayer";
import { paintCones, sightCones, smokesAt } from "./sightlayer";
import { spikeBody, spikeCore, spikePip } from "./spikeglyph";
import { tracersAt } from "./tracers";

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

/**
 * How much larger a *pinned* marker is drawn.
 *
 * A pin and a hover are not the same act and no longer draw the same way.  A
 * pin is a decision -- somebody clicked this player and wants to keep hold of
 * them in a five-man stack -- so it earns the reference's own treatment, about
 * 104px against a 26px base.  A hover is the pointer passing over, and
 * inflating a portrait to three times its size for that covered the very
 * neighbours the reader was sweeping the stack to tell apart; worse, the
 * roster raises the same state, so pointing at a card three hundred pixels
 * away silently blew up a marker on the map.  Hover is `HOVER_RING` instead:
 * the same mark, ringed in `--marker-hover`, moving nothing.  That colour is
 * magenta and not the warm hue this started as: a ring has to contrast with
 * both sides at once, and an orange one around an attacker is drawn in very
 * nearly the marker's own colour.
 */
const PICKED_SCALE = 3;

/**
 * The hovered marker's outline, in CSS pixels before the zoom scale.
 *
 * Three rather than the ordinary ring's two, because the ring it replaces is
 * already the team colour and a hover has to be legible as a *change* to a
 * mark whose size is now fixed.  It is drawn proud of the portrait like every
 * other ring here, so an agent icon with a pale border cannot swallow it.
 */
const HOVER_RING = 3;

/*
 * The death X's arm, in CSS pixels before the zoom scale.
 *
 * One constant where there were two: `KILL_MARK` sized the kill cross and
 * `DEAD_RADIUS` the dead player's own circle, and both were drawn at the same
 * point on the same player.  See `drawDeathMark`.
 *
 * 4.5 rather than 5, which is the smallest half of a correction: a round with
 * six kills in one choke drew six crosses at very nearly a portrait's own
 * width, and the mark for somebody who is *gone* was reading louder than the
 * marker for somebody who is standing there.
 */
const DEATH_MARK = 4.5;

/*
 * How dark the keyline under a death cross is allowed to be.
 *
 * The keyline exists so the mark survives Ascent's pale mid, and at a full
 * 4px of opaque canvas colour it was doing considerably more than that -- a
 * dark halo two pixels proud of every arm, which is the *bulk* a reader sees
 * before they see the colour.  Half-strength and one pixel narrower still
 * separates the cross from the radar and stops it from being the heaviest
 * thing on a crowded map.  The mark itself stays fully opaque: a stroke
 * blended toward the radar drifts outside the 36-RGB window `minimap.spec.ts`
 * counts as a team colour, so fading *that* would make a dead player pass its
 * check by luck rather than by being drawn.
 */
const DEATH_KEYLINE_ALPHA = 0.45;

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
 * A tracer's stroke, and the dash that says it was not decoded.
 *
 * Two pixels rather than one: a hairline that appears and vanishes is a flicker
 * rather than a mark.  The dash is longer than `drawRange`'s `[4, 4]` because
 * this is a line and that is a circle -- a 4px dash around a 60px ring reads as
 * dashed, and along a 300px line it reads as a dotted rule.
 */
const TRACER_WIDTH = 2;
const TRACER_DASH = [7, 5];

/**
 * The glow, which is the first `shadowBlur` in this interface.
 *
 * A tracer is on screen for well under two seconds, crosses whatever is under
 * it, and is the one mark here a reader is meant to catch out of the corner of
 * an eye.  A canvas shadow is the only glow a 2D context has, and it is
 * confined to the canvas: `review.spec.ts`'s flat-and-square sweep reads
 * `getComputedStyle().boxShadow` off DOM nodes and cannot see this.  **A CSS
 * shadow on the `<canvas>` element itself would be a different matter** -- that
 * spec does see those, and neither `canvas.minimap` nor `.stage-canvas` is on
 * its floating allowlist.
 *
 * Soft along the trail and hard at the head, because they answer different
 * questions: the trail is the geometry of the shot and has to stay a readable
 * dashed line, where the head is the event and has to be unmissable.
 */
const TRACER_TRAIL_GLOW = 6;
const TRACER_HEAD_GLOW = 12;

/** The bullet itself, in CSS pixels before the zoom scale. */
const TRACER_HEAD_RADIUS = 3;

/*
  A thrown ability's trail, and its head.

  Its own constants rather than the tracer's, because the two marks answer
  different questions and should not have to move together: a bullet is on
  screen for a second and wants to read as fast, where a throw crosses the
  map over a decoded second or two and sits under an icon. The dash is
  shorter so a slow line still reads as dashed at low zoom.
*/
/*
  How an ability's published extent is inked.

  Bolder than it was, and the previous values are worth recording because they
  were each individually defensible and together invisible: a 1px stroke at
  0.4 alpha over a 0.12 fill, in a side colour, on top of a grey radar. On a
  smoke's forty-pixel ring that is a suggestion of a circle; against Riot's own
  white map lines it disappears entirely.

  Still dashed and still faint compared with anything decoded -- dashed is this
  canvas's token for *generated* and the layer is labelled `(SIM)` -- but a
  reader has to be able to see the shape before the token means anything. The
  dash is longer for the same reason `TRACER_DASH` is longer than the old
  `[4, 4]`: at two pixels wide, a four-pixel dash reads as a dotted rule.
*/
const RING_WIDTH = 2;
const RING_DASH = [6, 5];
const RING_LINE_ALPHA = 0.75;
const RING_FILL_ALPHA = 0.18;

/*
  How a *detection* range is inked, which is a different claim from the ring
  above and has to look like one.

  An area of effect is where the ability does something; a detection range is
  where it *notices* somebody -- a trap's search, a bot's hunt, a bolt's scan --
  and Chamber's Trademark publishes both at once, a 10 m search around a 6 m
  slow. Drawn in the same ink they would read as one thing with a halo.

  It was an unfilled hairline at 0.22, which on Sova's 30 m Recon Bolt is a
  faint circle a quarter of the way across the map with nothing inside it: a
  reader sees an outline and no area. So it is a wash now -- a fill so faint it
  cannot be mistaken for the effect's, under a long sparse dash that cannot be
  mistaken for the effect's either. No countdown arc is ever drawn on one: that
  belongs to the effect and this is not one.
*/
const DETECTION_DASH = [3, 8];
const DETECTION_LINE_ALPHA = 0.4;
const DETECTION_FILL_ALPHA = 0.07;

/*
  How a wall is inked.

  Thicker than a ring because a wall is a piece of geometry rather than an
  extent around a point, and **solid or dashed by where it came from**: Sage's
  barrier is drawn from its own four segment actors' decoded coordinates and is
  therefore solid, like every other stroke on this canvas around something that
  was decoded, while a wall inferred from the caster's facing is dashed like
  every other generated mark. `castlayer` decides which; this only draws it.
*/
const WALL_WIDTH = 3;

/**
 * The dot inside a marker whose ability nothing here can name, as a fraction
 * of the marker's own half-width.  Small enough to read as a centre mark
 * rather than as a filled marker, which is what a player is.
 */
const UNNAMED_DOT = 0.3;

const THROW_DASH = [5, 4];
const THROW_HEAD_RADIUS = 5;

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
          liveOnly: state.layers.castMechanics,
        });
      }
      /*
        What each ability is doing at this instant, rather than only where it
        is.  Drawn after the static marks so a live ring sits over the diamond
        it belongs to, and before the tracers and the players: a bullet and a
        person both have to stay on top of the map's furniture.
      */
      if (state.layers.castMechanics) {
        drawCastMechanics(context, {
          model,
          snap,
          world,
          uvRadiusOf,
          colours,
          icons: castIcons,
        });
      }
      if (state.layers.tracers) {
        drawTracers(context, { model, snap, world, colours, scale });
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
      // Two questions, not one.  `chosenId` is whoever is being pointed at --
      // pinned, else hovered -- and decides who is *named*; `pinnedId` is the
      // narrower one and is the only thing that changes a marker's size.
      const chosenId = selectedActor(state);
      const pinnedId = state.selected;
      /*
        And the pointer's own player is painted last.

        A ring is no use underneath the four markers stacked on top of it, and
        a five-man spawn is exactly where somebody is pointing at one to find
        out who it is.  `sort` is stable, so this moves one player to the end
        and leaves the rest in the replay's own order -- which is what keeps
        the picture steady while the pointer is somewhere else entirely.
      */
      const order = model.replay.players
        .slice()
        .sort(
          (a, b) => Number(a.actor_id === chosenId) - Number(b.actor_id === chosenId),
        );
      for (const player of order) {
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
        const pinned = pinnedId === player.actor_id;
        // Only a pin grows the marker -- see `PICKED_SCALE`.  A hover keeps
        // the size and takes the magenta ring below, so nothing on the canvas
        // moves under a pointer that is only passing through.
        const radius = (AVATAR_PX * scale * (pinned ? PICKED_SCALE : 1)) / 2;

        if (alive) {
          drawFacing(context, { x, y, position, world, colour, radius });
          drawAlive(context, {
            x,
            y,
            radius,
            colour,
            ring: pinned ? colours.text! : chosen ? colours.hover! : colour,
            ringWidth: chosen && !pinned ? HOVER_RING : 2,
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
      /*
        Reversed, so the hit test answers with whatever is on *top*.

        `at` returns the first hit within reach and the list is built in paint
        order, so it used to answer with the bottom-most marker of a stack --
        the one drawn first and covered by every other.  Harmless while nothing
        depended on it; not harmless now that the answer decides which marker
        comes to the front, because pointing at the player on top would ring
        the one buried underneath them.
      */
      hits.reverse();
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
 * The spike's own mark, and it is **drawn here because nobody publishes one**:
 * `assets/manifest.json` has no spike and no bomb in it, and Riot's content
 * API has none either, so the alternative was the bare triangle this replaces.
 * `views/spikeglyph.ts` carries the mark and the argument for it being an
 * original rather than a trace.  The canvas vocabulary stays closed and every
 * member stays distinct at six pixels: circle is a living person, square a
 * live ability pawn, hollow diamond a landed cast, X a death, and this is the
 * only filled upward mark standing on its own.
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
  // Unchanged from the triangle this replaces, and that is a constraint rather
  // than inertia: `minimap.spec.ts` finds the plant by counting amber pixels
  // within 26 px of it, so the mark's screen footprint is part of a test.
  const half = SPIKE_HALF * Math.min(Math.max(scale, 0.9), MARK_SCALE_CAP);
  const path = spikeBody(x, y, half);

  context.save();
  // Keyline first, so the mark reads over Ascent's pale mid as well as over
  // the dark void -- the same trick the player label used before it went.
  context.lineWidth = 3;
  context.strokeStyle = colours.canvas!;
  context.stroke(path);
  context.fillStyle = colours.spikeArmed!;
  context.fill(path);
  // The core, painted *over* the body in the canvas colour rather than cut out
  // of it: a hole would break the amber into a ring and a pip, and the spec
  // requires the plant to be the largest connected amber patch on the canvas.
  context.fillStyle = colours.canvas!;
  context.fill(spikeCore(x, y, half));
  context.fillStyle = colours.spikeArmed!;
  context.fill(spikePip(x, y, half));
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
 * The fatal shot: a glowing bullet crossing a dashed line to the victim.
 *
 * **Dashed because it is generated.**  Every other stroke on this canvas is
 * around something the capture states; a `.vrf` has no shot in it at all, and
 * `views/tracers.ts` carries the whole argument for what is read here, what is
 * drawn, and why the flight is on screen before the kill it ends at.  The dash
 * is the same token `drawRange` uses for a looked-up radius.
 *
 * The trail is drawn only as far as the bullet has flown, so what a reader
 * follows is a head with a line behind it rather than a line with a dot on it.
 * Once it lands the whole line is there and holds, which is what makes the
 * geometry readable on a paused playhead -- an animation nobody can stop on is
 * no use to somebody reviewing a round.
 *
 * Under the players and under the spike, like everything else, and with no
 * arrowhead: the bullet is the direction, and the victim end already has
 * `drawDeathMark` on it.
 */
function drawTracers(
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
  const tracers = tracersAt(model, snap);
  if (tracers.length === 0) {
    return;
  }
  const mark = Math.min(Math.max(scale, 1), MARK_SCALE_CAP);
  /*
    `save`/`restore` rather than putting anything back by hand: the player loop
    draws into this same context afterwards, and a leaked `globalAlpha`,
    `shadowBlur` or dash would quietly repaint a whole canvas from a layer that
    had finished drawing.
  */
  context.save();
  context.lineCap = "round";
  for (const tracer of tracers) {
    const [x1, y1] = world(tracer.from.x, tracer.from.y);
    const [x2, y2] = world(tracer.to.x, tracer.to.y);
    const hx = x1 + (x2 - x1) * tracer.progress;
    const hy = y1 + (y2 - y1) * tracer.progress;
    const colour = sideColour(colours, tracer.side ?? "");

    context.globalAlpha = tracer.alpha;
    context.strokeStyle = colour;
    context.shadowColor = colour;
    context.shadowBlur = TRACER_TRAIL_GLOW * mark;
    context.lineWidth = TRACER_WIDTH * mark;
    context.setLineDash(TRACER_DASH);
    context.beginPath();
    context.moveTo(x1, y1);
    context.lineTo(hx, hy);
    context.stroke();

    // The bullet: a hot core inside the side's own glow, so it reads as a
    // light rather than as a third, larger marker on a canvas full of discs.
    context.setLineDash([]);
    context.shadowBlur = TRACER_HEAD_GLOW * mark;
    context.fillStyle = colour;
    context.beginPath();
    context.arc(hx, hy, TRACER_HEAD_RADIUS * mark, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = colours.text!;
    context.beginPath();
    context.arc(hx, hy, TRACER_HEAD_RADIUS * mark * 0.45, 0, Math.PI * 2);
    context.fill();
  }
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
 * There is no weight at all now: `sightlayer.paintCones` unions each side's
 * cones and paints the union at one flat alpha, so a lone survivor's wedge and
 * a five-man stack read exactly the same.  It weighed the count for a while --
 * `1/N` per cone, accumulated additively, so k of them read as `k/N` -- and
 * that gradient is gone.  No stroke either: an outline is a second ink that
 * counts nothing and cuts a hard line around the shape this layer is made of.
 *
 * `Scene3D` paints the identical picture from the identical two functions, at
 * the identical alpha; the only difference is that it rasterises in uv onto a
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
    /** Whether a placed mark disappears once its published lifetime is up. */
    liveOnly: boolean;
  },
): void {
  const { model, snap, world, uvRadiusOf, colours, icons, showRange, liveOnly } = args;
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
      /*
        Not handed over, and that was a real regression. `castsAt` skips a cast
        with a pawn on purpose -- a pawn has a decoded track and a spawn point
        beside it is a staler answer to the same question -- so with MECHANICS
        on, handing the ring over meant nobody drew one at all: Sova's drone,
        Killjoy's turret and alarmbot, Raze's Boom Bot, Cypher's camera and
        Deadlock's net each lost their published extent entirely. A ring is
        handed over only to a layer that will actually draw it.
      */
      drawRange(context, { x, y, cast, colour, uvRadiusOf, show: showRange, handedOver: false });
      // A square, so it is never mistaken for a player: circles are people and
      // squares are utility, and at this size that has to survive a glance.
      context.fillStyle = colour;
      context.strokeStyle = colours.background!;
      context.lineWidth = 1;
      context.fillRect(x - UTILITY_HALF, y - UTILITY_HALF, UTILITY_HALF * 2, UTILITY_HALF * 2);
      context.strokeRect(x - UTILITY_HALF, y - UTILITY_HALF, UTILITY_HALF * 2, UTILITY_HALF * 2);
      drawUtilityMark(context, { x, y, icon, colours, over: colours.background! });
    }

    /*
      A cast with no pawn: one coordinate, no path, and no arc anywhere. The
      hollow diamond says "something is here" without implying it moved.

      `liveOnly` is what makes it stop saying so. Without it the diamond is
      drawn from the moment the cast is reached until the round ends, so a
      smoke that went out twenty seconds ago sits on the map beside one that
      has just landed, and by the end of a round every utility anybody used is
      on screen at once. That is not a neutral picture: it claims a dozen
      things are standing that are not.

      It is a *phase* test rather than an age test, so it fixes the other end
      too -- `phaseOf` returns null before a throw's origin channel opened, so
      the mark no longer appears at the landing point while the thing is still
      in the air.

      Gated on the mechanics layer because the lifetime it reads is looked up:
      switch that off and this goes back to being the round's full record,
      which is what `abilitiesAt` keeps and what the parity fixtures pin. An
      ability the table publishes no lifetime for stays `placed` for ever and
      is unaffected either way.
    */
    if (cast.landed === null) {
      continue;
    }
    if (liveOnly && phaseOf(cast, cast.landed, snap.t_ms) === null) {
      continue;
    }
    const [x, y] = world(cast.landed.x, cast.landed.y);
    drawRange(context, { x, y, cast, colour, uvRadiusOf, show: showRange, handedOver: liveOnly });
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
    drawUtilityMark(context, { x, y, icon, colours, over: colours.canvas! });
  }
}

/**
 * What a utility marker says it is: Riot's own icon, or nothing at all.
 *
 * The marker used to carry `\`${cast.slot} ${cast.internal_name}\`` as text
 * beside it -- `Q Possessable Camera` across the map at nine pixels, colliding
 * with the geometry underneath and with every other cast in the same site.
 * The icon identifies the ability the way the agent portrait identifies the
 * player, and it cannot smear because it sits inside the marker's own box.
 *
 * **The fallback is a dot, and it used to be a letter.**  `icon_url` now
 * resolves for all four slots of every agent `abilityfacts` names, because the
 * join is by Riot's published ability name -- so what is left over is an agent
 * the table does not name at all, and for those the letter was actively
 * misleading. It is the *archetype's internal slot*, which is not the key the
 * player pressed: Sova's Recon Bolt decodes as `Q` and the game binds it to E,
 * so an `E` on the map beside a `Q` in the timeline described one ability two
 * ways. The `Passive` slot printed the whole word. A dot says "an ability this
 * project cannot name", which is the visibly-absent answer this tree prefers
 * to a confident wrong one; the marker's own square or diamond has already
 * said that something was cast here, and its colour has said by which side.
 */
function drawUtilityMark(
  context: CanvasRenderingContext2D,
  args: {
    x: number;
    y: number;
    icon: HTMLImageElement | undefined;
    colours: Record<string, string>;
    over: string;
  },
): void {
  const { x, y, icon, colours, over } = args;
  if (icon !== undefined) {
    const box = UTILITY_HALF * 2 - 2;
    context.drawImage(icon, x - box / 2, y - box / 2, box, box);
    return;
  }
  context.save();
  context.beginPath();
  context.arc(x, y, UTILITY_HALF * UNNAMED_DOT, 0, Math.PI * 2);
  context.fillStyle = over === colours.canvas! ? colours.text! : over;
  context.fill();
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
    /** Whether the mechanics layer is drawing this cast's ring instead. */
    handedOver: boolean;
  },
): void {
  const { x, y, cast, colour, uvRadiusOf, show, handedOver } = args;
  if (!show || handedOver || cast.range_uu === null) {
    return;
  }
  const radius = uvRadiusOf(cast.range_uu);
  if (!Number.isFinite(radius) || radius <= 0) {
    return;
  }
  context.save();
  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.globalAlpha = RING_FILL_ALPHA;
  context.fillStyle = colour;
  context.fill();
  context.globalAlpha = RING_LINE_ALPHA;
  context.setLineDash(RING_DASH);
  context.lineWidth = RING_WIDTH;
  context.strokeStyle = colour;
  context.stroke();
  context.restore();
}

/**
 * What each ability is doing at this instant: flying, arming, standing, going.
 *
 * Everything here is dashed, because everything here is either a looked-up
 * figure or a straight line this project drew between two decoded points --
 * and dashed is this canvas's token for *generated*, the way solid is its
 * token for a coordinate that was decoded.
 *
 * The four phases are drawn as four different things rather than four shades
 * of one, because the request they answer is "what happened here and when",
 * and a reader has to separate them at a glance on a busy site:
 *
 *   * **in flight** -- a dashed line from the throw origin to where the thing
 *     is now, with a head at the leading end.  Both ends and the clock were
 *     decoded; the straightness was not, and there is no arc because nothing
 *     records where a projectile was halfway.
 *   * **arming** -- a dashed ring with no fill, in `--text-muted` rather than
 *     the caster's side colour.  A device that has landed and not yet armed is
 *     not doing anything to anybody, and painting it in the ink that means
 *     "this side owns this ground" would say it is.
 *   * **active** -- the side's colour, a dashed ring with the faint fill, and a
 *     solid arc around the rim that sweeps away as the published lifetime runs
 *     out.  The arc is the one thing on this canvas that answers *how much
 *     longer*.
 *   * **expiring** -- the same ring fading out over `EXPIRE_MS`.
 *
 * A trigger range is drawn as its own ring, wider and fainter and never
 * filled: Chamber's Trademark searches 10 m and slows 6, and a single ring
 * would merge a question about who it notices with a claim about what it does.
 *
 * Nothing here reports which players were inside anything.  See `castlayer`.
 */
function drawCastMechanics(
  context: CanvasRenderingContext2D,
  args: {
    model: ReplayModel;
    snap: Snapshot;
    world: (x: number, y: number) => [number, number];
    uvRadiusOf: (uu: number) => number;
    colours: Record<string, string>;
    icons: Map<string, HTMLImageElement>;
  },
): void {
  const { model, snap, world, uvRadiusOf, colours, icons } = args;
  context.save();
  for (const drawn of castsAt(model, snap)) {
    const colour = drawn.side === null ? colours.unknown! : sideColour(colours, drawn.side);
    const icon = drawn.cast.icon_url === null ? undefined : icons.get(drawn.cast.icon_url);
    const { phase } = drawn;
    if (phase.kind === "flight") {
      drawThrow(context, { phase, world, colour, colours, icon });
      continue;
    }
    if (phase.kind === "wall") {
      drawWall(context, { phase, world, colour });
      continue;
    }
    const [x, y] = world(phase.at.x, phase.at.y);
    // The trigger range first, so the smaller area of effect draws over it.
    if (drawn.detectionUu !== null && phase.kind !== "arming") {
      drawDashedRing(context, {
        x,
        y,
        radius: uvRadiusOf(drawn.detectionUu),
        colour,
        alpha: DETECTION_LINE_ALPHA,
        fill: true,
        dash: DETECTION_DASH,
        fillAlpha: DETECTION_FILL_ALPHA,
      });
    }
    if (drawn.radiusUu === null) {
      continue;
    }
    const radius = uvRadiusOf(drawn.radiusUu);
    if (phase.kind === "arming") {
      drawDashedRing(context, {
        x,
        y,
        radius,
        colour: colours.muted!,
        alpha: 0.5,
        fill: false,
      });
      continue;
    }
    if (phase.kind === "placed") {
      /*
        A thing that stands, or one the table says nothing about: its extent
        is drawn and nothing counts down, because nothing here knows when it
        ends. `drawAbilities` has handed its ring over to this layer, so
        skipping here would leave a turret with no extent at all.
      */
      drawDashedRing(context, { x, y, radius, colour, alpha: RING_LINE_ALPHA, fill: true });
      continue;
    }
    const alpha = phase.kind === "expiring" ? phase.alpha : 1;
    drawDashedRing(context, { x, y, radius, colour, alpha: RING_LINE_ALPHA * alpha, fill: true });
    if (phase.kind === "active") {
      drawRemaining(context, { x, y, radius, colour, left: 1 - phase.progress });
    }
  }
  context.restore();
}

/** The thrown thing, part way along the straight line between its two ends. */
function drawThrow(
  context: CanvasRenderingContext2D,
  args: {
    phase: { from: Point; to: Point; at: Point; progress: number };
    world: (x: number, y: number) => [number, number];
    colour: string;
    colours: Record<string, string>;
    icon: HTMLImageElement | undefined;
  },
): void {
  const { phase, world, colour, colours, icon } = args;
  const [fromX, fromY] = world(phase.from.x, phase.from.y);
  const [atX, atY] = world(phase.at.x, phase.at.y);
  context.save();
  context.beginPath();
  context.moveTo(fromX, fromY);
  context.lineTo(atX, atY);
  context.setLineDash(THROW_DASH);
  context.lineWidth = 1.5;
  context.globalAlpha = 0.7;
  context.strokeStyle = colour;
  context.stroke();
  // The head, which is the thing itself rather than the trail behind it, so it
  // is solid where the trail is dashed and carries the ability's own icon
  // where Riot publishes one for this slot.
  context.setLineDash([]);
  context.globalAlpha = 1;
  context.beginPath();
  context.arc(atX, atY, THROW_HEAD_RADIUS, 0, Math.PI * 2);
  context.fillStyle = colour;
  context.fill();
  context.lineWidth = 1;
  context.strokeStyle = colours.background!;
  context.stroke();
  if (icon !== undefined) {
    const box = THROW_HEAD_RADIUS * 2;
    context.drawImage(icon, atX - box / 2, atY - box / 2, box, box);
  }
  context.restore();
}

/** A published extent: dashed, because nothing in the capture states it. */
function drawDashedRing(
  context: CanvasRenderingContext2D,
  args: {
    x: number;
    y: number;
    radius: number;
    colour: string;
    alpha: number;
    fill: boolean;
    /** The dash, so a detection range cannot be inked as an area of effect. */
    dash?: number[];
    /** Passed rather than derived from `alpha`, for the same reason. */
    fillAlpha?: number;
  },
): void {
  const { x, y, radius, colour, alpha, fill } = args;
  const dash = args.dash ?? RING_DASH;
  const fillAlpha = args.fillAlpha ?? RING_FILL_ALPHA;
  if (!Number.isFinite(radius) || radius <= 0) {
    return;
  }
  context.save();
  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  if (fill) {
    context.globalAlpha = alpha * fillAlpha;
    context.fillStyle = colour;
    context.fill();
  }
  context.globalAlpha = alpha;
  context.setLineDash(dash);
  context.lineWidth = RING_WIDTH;
  context.strokeStyle = colour;
  context.stroke();
  context.restore();
}

/**
 * A wall, from the two ends `castlayer` read out of its own segment actors.
 *
 * **Solid**, and it is the one thing this layer draws that is: every other
 * mark here is a looked-up radius or a straight line between two decoded
 * points, where a wall's line, length and orientation were all decoded. The
 * dash is this canvas's token for *generated* and there is nothing generated
 * about this one. See `castlayer.wallsOf` for why there is no second kind.
 */
function drawWall(
  context: CanvasRenderingContext2D,
  args: {
    phase: { from: Point; to: Point };
    world: (x: number, y: number) => [number, number];
    colour: string;
  },
): void {
  const { phase, world, colour } = args;
  const [fromX, fromY] = world(phase.from.x, phase.from.y);
  const [toX, toY] = world(phase.to.x, phase.to.y);
  context.save();
  context.beginPath();
  context.moveTo(fromX, fromY);
  context.lineTo(toX, toY);
  context.lineWidth = WALL_WIDTH;
  context.lineCap = "butt";
  context.globalAlpha = RING_LINE_ALPHA;
  context.strokeStyle = colour;
  context.stroke();
  context.restore();
}

/**
 * How much of the published lifetime is left, as an arc around the rim.
 *
 * Solid where the ring under it is dashed, and that is not an inconsistency:
 * the ring is a claim about *size*, which is looked up, and this is a reading
 * of the playhead against a clock -- so the two are different kinds of thing
 * and are drawn as two. It starts at twelve o'clock and unwinds clockwise,
 * which is the direction every countdown a person has ever seen unwinds.
 */
function drawRemaining(
  context: CanvasRenderingContext2D,
  args: { x: number; y: number; radius: number; colour: string; left: number },
): void {
  const { x, y, radius, colour, left } = args;
  if (!Number.isFinite(radius) || radius <= 0 || left <= 0) {
    return;
  }
  const top = -Math.PI / 2;
  context.save();
  context.beginPath();
  context.arc(x, y, radius, top, top + Math.PI * 2 * left);
  context.globalAlpha = 0.85;
  context.lineWidth = 2;
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
 * readable over Ascent's pale mid before it was removed.  The *mark* is fully
 * opaque: the old 0.55 and 0.8 were half the illegibility, and a stroke blended
 * toward the radar underneath can also drift outside the 36-RGB window
 * `minimap.spec.ts` counts as a team colour -- so a dead player was being
 * *checked* by luck as well as read by squinting.  The keyline is not the mark
 * and takes `DEATH_KEYLINE_ALPHA` instead; round caps rather than square for
 * the same reason, a squared arm end reading as a stub of a thicker stroke.
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
  context.lineCap = "round";
  context.globalAlpha = DEATH_KEYLINE_ALPHA;
  context.lineWidth = 3;
  context.strokeStyle = keyline;
  context.stroke(path);
  context.globalAlpha = 1;
  context.lineWidth = 1.75;
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
    ringWidth: number;
    icon: HTMLImageElement | undefined;
    background: string;
  },
): void {
  const { x, y, radius, colour, ring, ringWidth, icon, background } = args;
  if (icon) {
    // The ring is drawn first and slightly proud of the portrait, so the team
    // colour survives an agent icon with a pale border.
    context.beginPath();
    context.arc(x, y, radius + 2, 0, Math.PI * 2);
    context.fillStyle = colour;
    context.fill();
    context.strokeStyle = ring;
    context.lineWidth = ringWidth;
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
  context.lineWidth = ringWidth;
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

