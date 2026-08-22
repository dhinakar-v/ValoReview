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
import { palette, teamColour, useImages } from "./images";
import { usePlayback, selectedActor } from "./playback";

/** Marker sizes, in CSS pixels, carried over from the desktop viewer. */
const AVATAR_PX = 26;
const DOT_RADIUS = 7;
const DEAD_RADIUS = 6;
const PAWN_HALF = 5;
const PLACED_HALF = 6;
const FACING_LENGTH = 16;

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

/*
 * The canvas type stack, named once.
 *
 * A canvas cannot inherit a font, so this is the one place in the interface
 * where the bundled faces have to be repeated as a string.  Inter is the
 * page's UI face and is loaded by the time anything is drawn -- and the tail
 * is the same fallback the stylesheet uses, so a checkout with the woff2 files
 * stripped renders the labels in the same face as the page around them.
 */
const LABEL_FONT = '"Inter", "Segoe UI", system-ui, sans-serif';

/** A dark keyline under a label, because the radar is bright in places. */
const LABEL_OUTLINE = 3;

export interface MinimapProps {
  model: ReplayModel;
  art: MapArt;
  radar: HTMLImageElement | undefined;
  mask: SightMaskDoc | null;
}

interface Hit {
  x: number;
  y: number;
  player: Player;
}

export function MinimapCanvas({ model, art, radar, mask }: MinimapProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const hitsRef = useRef<Hit[]>([]);
  const boxRef = useRef<Box>({ left: 0, top: 0, side: 0 });

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

      const box = placeSquare(width, height);
      boxRef.current = box;

      const state = usePlayback.getState();
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
      if (state.showSight && silhouette && settings) {
        drawSight(context, { model, art, snap, box, colours, silhouette, settings });
      }
      if (state.showTrails) {
        drawPlayerTrails(context, { model, snap, world, colours });
      }
      if (state.showAbilities) {
        drawAbilities(context, { model, snap, world, colours });
      }

      const hits: Hit[] = [];
      for (const player of model.replay.players) {
        const position = positionOf(snap, player.actor_id);
        if (position === null) {
          continue;
        }
        const [x, y] = world(position.x, position.y);
        const colour = teamColour(colours, player.team);
        const alive = snap.alive.has(player.actor_id);
        const chosen = selectedActor(state) === player.actor_id;

        if (alive) {
          drawFacing(context, { x, y, position, world, colour });
          drawAlive(context, {
            x,
            y,
            colour,
            ring: chosen ? colours.text! : colour,
            icon: iconFor.get(player.actor_id),
            background: colours.background!,
          });
        } else {
          drawDead(context, x, y, colour);
        }

        // Outline then fill.  A white label over Ascent's pale mid is
        // unreadable without one, and a drop shadow costs a composite per
        // player per frame where a stroke costs nothing.
        const label = player.label || player.team;
        const labelY = y - AVATAR_PX / 2 - 7;
        context.font = `600 10px ${LABEL_FONT}`;
        context.textAlign = "center";
        context.lineJoin = "round";
        context.lineWidth = LABEL_OUTLINE;
        context.strokeStyle = colours.canvas!;
        context.strokeText(label, x, labelY);
        context.fillStyle = alive ? colours.text! : colours.muted!;
        context.fillText(label, x, labelY);
        hits.push({ x, y, player });
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

  const at = (event: React.MouseEvent<HTMLCanvasElement>): Player | null => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const reach = (AVATAR_PX / 2 + 4) ** 2;
    for (const hit of hitsRef.current) {
      if ((x - hit.x) ** 2 + (y - hit.y) ** 2 <= reach) {
        return hit.player;
      }
    }
    return null;
  };

  return (
    <canvas
      ref={canvasRef}
      className="minimap"
      onMouseMove={(event) =>
        usePlayback.setState({ hovered: at(event)?.actor_id ?? null })
      }
      onMouseLeave={() => usePlayback.setState({ hovered: null })}
      onClick={(event) => usePlayback.getState().toggleSelected(at(event)?.actor_id ?? null)}
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
  const colour = teamColour(colours, player?.team ?? "?");
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
  },
): void {
  const { model, snap, world, colours } = args;
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
      label(context, colours.muted!, `${cast.slot} ${cast.internal_name}`, x, y + PAWN_HALF + 10);
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
    label(context, colours.muted!, `${cast.slot} ${cast.internal_name}`, x, y + PLACED_HALF + 12);
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
      teamColour(colours, player.team),
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

function drawFacing(
  context: CanvasRenderingContext2D,
  args: {
    x: number;
    y: number;
    position: { x: number; y: number; yaw: number };
    world: (x: number, y: number) => [number, number];
    colour: string;
  },
): void {
  const { x, y, position, world, colour } = args;
  // The probe, not screen-space trigonometry. See the module docstring.
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
  const scale = (AVATAR_PX / 2 + FACING_LENGTH) / length;
  context.strokeStyle = colour;
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(x, y);
  context.lineTo(x + dx * scale, y + dy * scale);
  context.stroke();
}

function drawAlive(
  context: CanvasRenderingContext2D,
  args: {
    x: number;
    y: number;
    colour: string;
    ring: string;
    icon: HTMLImageElement | undefined;
    background: string;
  },
): void {
  const { x, y, colour, ring, icon, background } = args;
  if (icon) {
    const radius = AVATAR_PX / 2;
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
    context.drawImage(icon, x - radius, y - radius, AVATAR_PX, AVATAR_PX);
    context.restore();
    return;
  }
  // No icon: a filled dot, which is visibly a marker rather than a portrait
  // that failed to load.
  context.beginPath();
  context.arc(x, y, DOT_RADIUS, 0, Math.PI * 2);
  context.fillStyle = colour;
  context.fill();
  context.strokeStyle = ring === colour ? background : ring;
  context.lineWidth = 2;
  context.stroke();
}

function drawDead(context: CanvasRenderingContext2D, x: number, y: number, colour: string): void {
  context.save();
  context.globalAlpha = 0.55;
  context.strokeStyle = colour;
  context.lineWidth = 2;
  context.beginPath();
  context.arc(x, y, DEAD_RADIUS, 0, Math.PI * 2);
  context.stroke();
  context.beginPath();
  context.moveTo(x - DEAD_RADIUS, y - DEAD_RADIUS);
  context.lineTo(x + DEAD_RADIUS, y + DEAD_RADIUS);
  context.moveTo(x - DEAD_RADIUS, y + DEAD_RADIUS);
  context.lineTo(x + DEAD_RADIUS, y - DEAD_RADIUS);
  context.stroke();
  context.restore();
}

function label(
  context: CanvasRenderingContext2D,
  colour: string,
  text: string,
  x: number,
  y: number,
): void {
  context.fillStyle = colour;
  context.font = `600 9px ${LABEL_FONT}`;
  context.textAlign = "center";
  context.fillText(text, x, y);
}
