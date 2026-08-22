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

import type { MapArt, Player, SightMaskDoc } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { SightMask, SightSettings } from "../model/sight";
import { cone, decodeMask, forwardUv, uvRadius } from "../model/sight";
import type { Snapshot } from "../model/state";
import { positionOf, stateAt } from "../model/state";
import { segments } from "../model/track";
import type { Box } from "../model/transform";
import { applyTransform, placeSquare, uvToPixels } from "../model/transform";
import { sideOf } from "../model/synthetic";
import { markerScale, panBy, viewBox, zoomAt } from "../model/viewport";
import { palette, sideColour, teamColour, useImages } from "./images";
import { usePlayback, selectedActor, teamShown } from "./playback";

/** Marker sizes, in CSS pixels, carried over from the desktop viewer. */
const AVATAR_PX = 26;
const DOT_RADIUS = 7;
const DEAD_RADIUS = 6;
const PAWN_HALF = 5;
const PLACED_HALF = 6;

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

/** A kill mark's arm, in CSS pixels before the zoom scale. */
const KILL_MARK = 6;

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

      // The draw order is the z-order, and it is the desktop viewer's: the cone
      // is a wash under everything, then ability paths, then utility, then the
      // players on top -- because a player hidden behind their own utility is
      // the one thing on this canvas nobody can afford to lose.
      if (state.layers.sight && silhouette && settings) {
        drawSight(context, { model, art, snap, box, colours, silhouette, settings });
      }
      if (state.layers.trails) {
        drawPlayerTrails(context, { model, snap, world, colours });
      }
      if (state.layers.killMarkers) {
        drawKillMarks(context, { model, snap, world, colours, scale });
      }
      /*
        The players claim their own icons before any utility name is placed.
        Abilities draw underneath players by z-order, so without this a cast
        name lands on a face and is then painted over -- present in the pixels,
        readable by nobody.  Reserving first is what makes the rejection below
        prefer the label that can still be read.
      */
      const names = labelSpace();
      for (const player of model.replay.players) {
        if (!teamShown(state, player.team)) {
          continue;
        }
        const position = positionOf(snap, player.actor_id);
        if (position !== null) {
          const [px, py] = world(position.x, position.y);
          reserve(names, px, py, (AVATAR_PX * scale) / 2);
        }
      }
      if (state.layers.utility) {
        drawAbilities(context, { model, snap, world, colours, space: names });
      }

      const hits: Hit[] = [];
      const chosenId = selectedActor(state);
      for (const player of model.replay.players) {
        if (!teamShown(state, player.team)) {
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
        const alive = snap.alive.has(player.actor_id);
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
          drawDead(context, x, y, colour, DEAD_RADIUS * scale);
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
        usePlayback.setState({
          hovered: hit?.player.actor_id ?? null,
          hoveredAt: hit === null ? null : { x: hit.x, y: hit.y },
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
 * The selected player's approximate view cone.
 *
 * Everything about this is an approximation and the caption under the canvas
 * says so.  What it must not be is wrong about which way somebody is looking,
 * so the heading goes through `forwardUv`, which probes a world point and
 * transforms it rather than doing trigonometry in image space.
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
  },
): void {
  const { model, art, snap, box, colours, silhouette, settings } = args;
  const actorId = selectedActor(usePlayback.getState());
  if (actorId === null || !snap.alive.has(actorId)) {
    return;
  }
  const position = snap.positions.get(actorId);
  if (position === undefined) {
    return;
  }
  const polygon = cone(
    silhouette,
    applyTransform(art.transform, position.x, position.y),
    forwardUv(art.transform, position.x, position.y, position.yaw, settings.probe_uu),
    uvRadius(art.transform, settings.max_range_uu),
    settings,
  );
  // An empty cone means draw nothing. Never a fallback circle: a circle where
  // a cone belongs claims the player can see in every direction.
  if (polygon.length < 3) {
    return;
  }
  const player = model.replay.players.find((p) => p.actor_id === actorId);
  const colour = sideColour(
    colours,
    player ? sideOf(model.replay, player.team, snap.t_ms) : "?",
  );
  context.save();
  context.beginPath();
  polygon.forEach(([u, v], i) => {
    const [x, y] = uvToPixels(box, u, v);
    if (i === 0) {
      context.moveTo(x, y);
    } else {
      context.lineTo(x, y);
    }
  });
  context.closePath();
  // What the `gray25` stipple was standing in for, now that there is an alpha
  // channel to say it with.
  context.globalAlpha = 0.22;
  context.fillStyle = colour;
  context.fill();
  context.globalAlpha = 0.5;
  context.strokeStyle = colour;
  context.lineWidth = 1;
  context.stroke();
  context.restore();
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
    colours: Record<string, string>;
    /** Boxes already claimed -- the players, who outrank every label here. */
    space: LabelBox[];
  },
): void {
  const { model, snap, world, colours, space } = args;
  const byCodename = new Map<string, string>();
  for (const player of model.replay.players) {
    if (player.codename) {
      // A codename two players share is refused rather than resolved to
      // whichever was found first, so an ambiguous cast simply has no colour.
      byCodename.set(player.codename, byCodename.has(player.codename) ? "?" : player.team);
    }
  }

  for (const cast of snap.roundCasts) {
    const colour = teamColour(colours, byCodename.get(cast.codename) ?? "?");
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
      // A square, so it is never mistaken for a player: circles are people and
      // squares are utility, and at this size that has to survive a glance.
      context.fillStyle = colour;
      context.strokeStyle = colours.background!;
      context.lineWidth = 1;
      context.fillRect(x - PAWN_HALF, y - PAWN_HALF, PAWN_HALF * 2, PAWN_HALF * 2);
      context.strokeRect(x - PAWN_HALF, y - PAWN_HALF, PAWN_HALF * 2, PAWN_HALF * 2);
      label(
        context,
        colours.muted!,
        `${cast.slot} ${cast.internal_name}`,
        x,
        y + PAWN_HALF + 10,
        space,
      );
    }

    // A cast with no pawn: one coordinate, no path, and no arc anywhere. The
    // hollow diamond says "something is here" without implying it moved.
    if (cast.landed === null) {
      continue;
    }
    const [x, y] = world(cast.landed.x, cast.landed.y);
    context.save();
    context.translate(x, y);
    context.rotate(Math.PI / 4);
    context.globalAlpha = 0.85;
    context.strokeStyle = colour;
    context.lineWidth = 2;
    context.strokeRect(-PLACED_HALF, -PLACED_HALF, PLACED_HALF * 2, PLACED_HALF * 2);
    context.restore();
    label(
      context,
      colours.muted!,
      `${cast.slot} ${cast.internal_name}`,
      x,
      y + PLACED_HALF + 12,
      space,
    );
  }
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
function drawKillMarks(
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
  const arm = KILL_MARK * scale;
  context.save();
  context.globalAlpha = 0.8;
  context.lineWidth = 2;
  for (const [actorId, position] of snap.deathPositions) {
    const player = model.replay.players.find((p) => p.actor_id === actorId);
    if (player === undefined || !teamShown(usePlayback.getState(), player.team)) {
      continue;
    }
    const [x, y] = world(position.x, position.y);
    context.strokeStyle = sideColour(
      colours,
      sideOf(model.replay, player.team, snap.t_ms),
    );
    context.beginPath();
    context.moveTo(x - arm, y);
    context.lineTo(x + arm, y);
    context.moveTo(x, y - arm);
    context.lineTo(x, y + arm);
    context.stroke();
    context.beginPath();
    context.arc(x, y, arm * 0.55, 0, Math.PI * 2);
    context.stroke();
  }
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

function drawDead(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  colour: string,
  radius: number = DEAD_RADIUS,
): void {
  context.save();
  context.globalAlpha = 0.55;
  context.strokeStyle = colour;
  context.lineWidth = 2;
  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.stroke();
  context.beginPath();
  context.moveTo(x - radius, y - radius);
  context.lineTo(x + radius, y + radius);
  context.moveTo(x - radius, y + radius);
  context.lineTo(x + radius, y - radius);
  context.stroke();
  context.restore();
}

/**
 * The boxes already spoken for on this frame.
 *
 * Utility labels were drawn unconditionally, one per pawn and one per landed
 * cast, so a round where several pieces of utility land near each other put
 * four or five names through the same twenty pixels -- legible in none of
 * them.  The committed gallery screenshot has one such smear beside B site,
 * which is what makes this a defect rather than a preference: the layer's job
 * is saying what is there, and a smear says nothing.
 *
 * Greedy rejection is the whole algorithm.  There is no cleverer placement
 * here on purpose: moving a label away from the thing it names is a worse lie
 * than omitting it, because a name six pixels off is still read as belonging
 * to whatever it is now nearest.  So a label either sits where its own marker
 * is or is not drawn, and the marker -- the square, the diamond -- is always
 * drawn regardless.  What is on the map never depends on whether its name fit.
 */
type LabelBox = { left: number; right: number; top: number; bottom: number };

function overlaps(a: LabelBox, b: LabelBox): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

export function labelSpace(): LabelBox[] {
  return [];
}

/** Reserve a box without drawing anything -- how a player claims their icon. */
export function reserve(space: LabelBox[], x: number, y: number, half: number): void {
  space.push({ left: x - half, right: x + half, top: y - half, bottom: y + half });
}

/**
 * Draw a label unless something is already there.  Returns whether it landed,
 * which nothing needs yet and which makes the rejection visible to a test.
 */
function label(
  context: CanvasRenderingContext2D,
  colour: string,
  text: string,
  x: number,
  y: number,
  space?: LabelBox[],
): boolean {
  context.fillStyle = colour;
  context.font = `600 9px ${LABEL_FONT}`;
  context.textAlign = "center";

  if (space) {
    // `measureText` reads the font set above, so the order matters.  A 9px
    // line box plus two pixels of air is what stops two rows of names from
    // touching where their columns happen not to.
    const width = context.measureText(text).width;
    const box: LabelBox = {
      left: x - width / 2 - 1,
      right: x + width / 2 + 1,
      top: y - 9,
      bottom: y + 2,
    };
    if (space.some((taken) => overlaps(box, taken))) {
      return false;
    }
    space.push(box);
  }

  context.fillText(text, x, y);
  return true;
}
