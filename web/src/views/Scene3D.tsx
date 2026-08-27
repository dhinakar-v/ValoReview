/**
 * The same snapshot, with the elevation the 2D view has always thrown away.
 *
 * `Position` carries x, y, z, yaw and pitch.  The minimap uses x, y and yaw,
 * and the z has been decoded and discarded on every frame the desktop viewer
 * ever drew -- which on Split or Bind is the difference between two players in
 * the same place and one of them standing above the other.
 *
 * **There is no map geometry in this project.**  No collision, no navmesh, no
 * height data: a map is a radar PNG, four transform scalars and a list of point
 * callouts.  So this scene is the radar image as a ground plane, players at
 * their own replicated height, and nothing else.  No walls, no floors, no
 * extruded elevation bands.  That constraint is not a limitation to work
 * around; it is what this view is.
 *
 * Coordinates
 * -----------
 * Scene units *are* uv units, so the ground is a 1x1 quad in XZ and a player's
 * height is
 *
 *     sceneY = (z - floorZ) * transform.vertical_scale
 *
 * `vertical_scale` is served by `/api/maps/{key}`: it is the average
 * `sight.uv_radius` takes, `(|xm| + |ym|) / 2`, which converts an Unreal unit
 * into a fraction of the radar.  Using it puts elevation at the map's own
 * horizontal scale -- a figure derived from a measured transform, not one tuned
 * until it looked right.
 *
 * Two traps, both avoided by construction
 * ---------------------------------------
 * The ground is an **explicit `BufferGeometry`** -- four vertices, four UVs, in
 * the XZ plane -- and not a `PlaneGeometry` rotated by -PI/2.  The rotation
 * sign, `PlaneGeometry`'s bottom-left UV origin, `texture.flipY` and the
 * transform's own axis swap compound into four independent ways to end up
 * mirrored, each of which looks fine until two maps are compared.  Fifteen
 * lines of explicit geometry removes the whole class, and `DoubleSide` removes
 * the winding question with it.
 *
 * And the orientation is **verified rather than asserted**: the callouts layer
 * drops a labelled marker at every callout's scene position, so the 3D scene
 * can be checked against the 2D minimap, which already lands 346 of 346
 * callouts inside the image.
 *
 * Facing uses the same probe trick the minimap does: `forwardUv` gives a
 * direction in uv space, which is scene space here, and the marker is pointed
 * along it.  No scene-space yaw arithmetic, for the same reason as everywhere
 * else -- the transform swaps the axes and either multiplier may be negative.
 *
 * This is the one view that also uses **pitch**, which nothing in this project
 * had ever rendered.  Nothing states whether 350 degrees is looking up or
 * down, so drawing it on an assumed sign would have been the plausible wrong
 * answer; it was measured instead, at every kill in the reference library
 * against the true angle to a victim whose z is also known, and it agrees to a
 * median 0.91 degrees with positive meaning up.  The minimap stays yaw-only,
 * because a top-down projection has nowhere to put the other half.
 */

import { Html, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import type { MapArt, SightMaskDoc } from "../api/types";
import { mod, radians } from "../model/angles";
import type { ReplayModel } from "../model/replay";
import { floorZ } from "../model/replay";
import type { SightMask, SightSettings } from "../model/sight";
import { decodeMask, forwardUv } from "../model/sight";
import { positionOf, spikeLocation, stateAt } from "../model/state";
import { segments } from "../model/track";
import { applyTransform } from "../model/transform";
import { sideOf } from "../model/synthetic";
import { palette, sideColour, useImages } from "./images";
import { teamShown, usePlayback } from "./playback";
import { SIGHT_RASTER, paintCones, sightCones, smokesAt } from "./sightlayer";
import { tracersAt } from "./tracers";

/** Marker sizes, in scene units — which are fractions of the radar's side. */
const BODY_RADIUS = 0.006;
const BODY_HEIGHT = 0.018;
const ICON_SIZE = 0.05;
const FACING_LENGTH = 0.035;

/** How far back a trail reaches, in playback ms. */
const TRAIL_MS = 8000;

/* The spike cone, in scene units -- a shade wider and taller than a player
   capsule, because it has to be findable from across the map. */
const SPIKE_RADIUS = 0.009;
const SPIKE_HEIGHT = 0.026;

/** How far ahead the heading probe is placed, in Unreal units. */
const FACING_PROBE_UU = 100;

/**
 * A decoded angle in 0..360 as a signed one, so up is positive.
 *
 * Pitch comes off the same packed angle dword as yaw and is therefore unsigned
 * on the wire.  Which half means *up* is not stated anywhere -- not in the
 * replay, not in the catalogue, not in the manifest -- so it was measured
 * instead, at every kill in the reference library against the true angle to
 * the victim.  See `tests/test_movement.py::PitchPointsAtTheVictim`.
 */
function signedPitch(degrees: number): number {
  const wrapped = mod(degrees, 360);
  return wrapped > 180 ? wrapped - 360 : wrapped;
}

/*
 * Tracers, in scene units -- and the scene is the map, one unit across.
 *
 * `MAX_TRACERS` is a ceiling on how many can be alive at once.  Ten is the
 * whole server: a tracer lives `TRACER_LIFE_MS` and a round has ten players in
 * it, so an eleventh would need somebody to die twice.
 *
 * `TRACER_DASH_UV` is the length of one dash-and-gap along the beam, which the
 * texture repeat is derived from -- so a dash is a fixed size in the *world*
 * rather than stretching with the length of the shot.  A quarter of it is ink,
 * which is what reads as dashed rather than as dotted or as solid.
 */
const MAX_TRACERS = 10;
const TRACER_DASH_UV = 0.01;

/**
 * How wide the beam is, and how big the bullet at its head is.
 *
 * A `THREE.Line` is **one pixel wide in WebGL whatever `linewidth` says** --
 * the widths in the spec were never implemented by the ANGLE backends -- so a
 * line here cannot be made either thick or soft, and the tracer was a hairline
 * that was genuinely hard to find in a scene.  The beam is a camera-facing quad
 * instead, and once it is geometry it can carry a texture that fades at its
 * edges, which is the glow.
 */
const TRACER_HALF_WIDTH = 0.0035;
const TRACER_HEAD_SIZE = 0.024;

/** The stripe and the bullet, drawn once into textures the beams share. */
const TRACER_TEXTURE_PX = 64;

/**
 * Below this the beam is not drawn at all, in scene units.
 *
 * A quad needs a direction to be built along, and at the muzzle flash there is
 * not one yet: the cross product of a zero-length vector with anything is zero,
 * and normalising that is NaN in every component -- which three.js hands
 * straight to the GPU as a triangle that disappears or covers the screen. The
 * bullet is drawn on its own for that one frame.
 */
const MIN_BEAM_LENGTH = 1e-6;

/** Just off the ground, so a flat wedge does not fight the plane for pixels. */
const SIGHT_LIFT = 0.0015;

/*
 * Not a palette colour.  A texture drawn at `#ffffff` is the texture drawn
 * unmodified -- it is the identity tint, the way `1` is for a multiply -- and
 * moving it into `theme.py` would invite somebody to change it, which would
 * silently recolour Riot's own radar and every agent portrait on it.
 */
const WHITE = "#ffffff";

interface SceneProps {
  model: ReplayModel;
  art: MapArt;
  radar: HTMLImageElement | undefined;
  mask: SightMaskDoc | null;
}

export function Scene3D(props: SceneProps) {
  const colours = useMemo(() => palette(document.body), []);
  return (
    <Canvas
      className="scene3d"
      camera={{ position: [0.5, 0.9, 1.6], fov: 40, near: 0.001, far: 20 }}
      onCreated={({ scene }) => {
        scene.background = new THREE.Color(colours.background!);
      }}
    >
      <ambientLight intensity={1.6} />
      <directionalLight position={[1, 2, 1]} intensity={1.2} />
      <OrbitControls target={[0.5, 0, 0.5]} maxDistance={6} minDistance={0.2} />
      <Ground radar={props.radar} colours={colours} />
      <Trails {...props} colours={colours} />
      <Actors {...props} colours={colours} />
      <Spike {...props} colours={colours} />
      <Tracers {...props} colours={colours} />
      <SightOverlay {...props} colours={colours} />
      <Callouts art={props.art} />
    </Canvas>
  );
}

/**
 * The radar, as a 1x1 quad in the XZ plane, built vertex by vertex.
 *
 * `flipY = false` and the UVs written out longhand, so texture (0,0) is the
 * image's first pixel and u, v mean exactly what `applyTransform` returns.
 * `DoubleSide` because a ground plane seen from below should still be a ground
 * plane, and because it makes the winding order stop mattering.
 */
function Ground({
  radar,
  colours,
}: {
  radar: HTMLImageElement | undefined;
  colours: Record<string, string>;
}) {
  const geometry = useMemo(() => {
    const buffer = new THREE.BufferGeometry();
    // (u, v) -> (x, y, z) = (u, 0, v). Four corners, two triangles.
    buffer.setAttribute(
      "position",
      new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 1], 3),
    );
    buffer.setAttribute("uv", new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, 1, 1, 1], 2));
    buffer.setAttribute("normal", new THREE.Float32BufferAttribute([0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0], 3));
    buffer.setIndex([0, 2, 1, 2, 3, 1]);
    return buffer;
  }, []);

  const texture = useMemo(() => {
    if (!radar) {
      return null;
    }
    const made = new THREE.Texture(radar);
    made.flipY = false;
    made.colorSpace = THREE.SRGBColorSpace;
    made.needsUpdate = true;
    return made;
  }, [radar]);

  useEffect(() => () => texture?.dispose(), [texture]);

  return (
    <mesh geometry={geometry} renderOrder={0}>
      {/*
        White where there is a radar to show unmodified, and the panel colour
        where there is not.  That second value used to be the literal
        `#1b1e27`, which is `--panel` written a second time -- exactly the
        duplication `palette()` exists to prevent, and it would have survived
        a palette change silently.
      */}
      <meshBasicMaterial
        map={texture ?? undefined}
        color={texture ? WHITE : colours.panel!}
        transparent
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

/**
 * One group per player: a capsule at their height, a stem down to the plane,
 * and a billboarded agent icon above it.
 *
 * The stem is what makes an elevated player read as *elevated* rather than as
 * misplaced.  Without it a marker floating over the radar is indistinguishable
 * from one drawn at the wrong place, which is precisely the plausible wrong
 * answer this whole view is meant to avoid.
 *
 * Built once and moved every frame.  Ten groups reconciled through React at 60
 * fps would cost more than the arithmetic they carry.
 */
function Actors({
  model,
  art,
  colours,
}: SceneProps & { colours: Record<string, string> }) {
  const icons = useImages(model.replay.players.map((player) => player.icon_url));
  const reference = useMemo(() => floorZ(model), [model]);

  const built = useMemo(() => {
    const root = new THREE.Group();
    const parts = new Map<
      number,
      { group: THREE.Group; stem: THREE.Line; facing: THREE.Line; body: THREE.Mesh; sprite: THREE.Sprite }
    >();
    for (const player of model.replay.players) {
      // Built with the opening side and re-set per frame below: a capture with
      // a recorded swap changes every marker's colour halfway through, and a
      // material built once would show the first half's colours all match.
      const colour = new THREE.Color(sideColour(colours, sideOf(model.replay, player.team, 0)));
      const group = new THREE.Group();

      const body = new THREE.Mesh(
        new THREE.CapsuleGeometry(BODY_RADIUS, BODY_HEIGHT, 4, 10),
        new THREE.MeshStandardMaterial({ color: colour }),
      );
      group.add(body);

      const stem = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(0, 0, 0),
          new THREE.Vector3(0, -1, 0),
        ]),
        new THREE.LineBasicMaterial({ color: colour, transparent: true, opacity: 0.5 }),
      );
      group.add(stem);

      const facing = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(0, 0, 0),
          new THREE.Vector3(0, 0, 0),
        ]),
        new THREE.LineBasicMaterial({ color: colour }),
      );
      group.add(facing);

      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({ color: colour, transparent: true }),
      );
      sprite.scale.setScalar(ICON_SIZE);
      sprite.position.set(0, BODY_HEIGHT + ICON_SIZE * 0.7, 0);
      group.add(sprite);

      root.add(group);
      parts.set(player.actor_id, { group, stem, facing, body, sprite });
    }
    return { root, parts };
  }, [colours, model]);

  useEffect(() => {
    for (const player of model.replay.players) {
      const url = player.icon_url;
      const image = url ? icons.get(url) : undefined;
      const found = built.parts.get(player.actor_id);
      if (!found || !image) {
        continue;
      }
      const texture = new THREE.Texture(image);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.needsUpdate = true;
      found.sprite.material.map = texture;
      // The team colour tinted the placeholder; with a portrait in place it
      // would tint the portrait instead.
      found.sprite.material.color.set(WHITE);
      found.sprite.material.needsUpdate = true;
    }
  }, [built, icons, model]);

  const forward = useRef(new THREE.Vector3());

  useFrame(() => {
    const state = usePlayback.getState();
    const snap = stateAt(model, state.tMs);
    for (const player of model.replay.players) {
      const found = built.parts.get(player.actor_id);
      if (!found) {
        continue;
      }
      // The side, and with it the colour, changes at the recorded swap. Three
      // materials share one colour per player, so this is three writes rather
      // than a rebuild -- and `THREE.Color.set` is a no-op on an equal value.
      const side = sideOf(model.replay, player.team, snap.t_ms);
      const colour = sideColour(colours, side);
      (found.body.material as THREE.MeshStandardMaterial).color.set(colour);
      (found.stem.material as THREE.LineBasicMaterial).color.set(colour);
      (found.facing.material as THREE.LineBasicMaterial).color.set(colour);

      const position = positionOf(snap, player.actor_id);
      // Where the track refused, nothing is drawn -- not a last-known place.
      // A side hidden by its roster funnel is the same answer for a different
      // reason, and both have to reach the scene, not just the minimap.
      if (position === null || !teamShown(state, player.team)) {
        found.group.visible = false;
        continue;
      }
      found.group.visible = true;
      const [u, v] = applyTransform(art.transform, position.x, position.y);
      const height = (position.z - reference) * art.transform.vertical_scale;
      found.group.position.set(u, height + BODY_HEIGHT, v);

      // The stem reaches down to the plane, however high the player is.
      const stemPoints = found.stem.geometry.getAttribute("position") as THREE.BufferAttribute;
      stemPoints.setXYZ(1, 0, -(height + BODY_HEIGHT), 0);
      stemPoints.needsUpdate = true;

      const alive = snap.alive.has(player.actor_id);
      const material = found.body.material as THREE.MeshStandardMaterial;
      material.opacity = alive ? 1 : 0.35;
      material.transparent = !alive;
      found.sprite.visible = alive;
      found.facing.visible = alive;

      if (alive) {
        // The probe again: a direction in uv space, which is scene space here.
        // Never scene-space yaw arithmetic.
        const [du, dv] = forwardUv(
          art.transform,
          position.x,
          position.y,
          position.yaw,
          FACING_PROBE_UU,
        );
        // And the pitch, which nothing in this project had ever rendered until
        // it was measured: at every kill in the reference library the killer's
        // pitch agrees with the true angle to the victim to a median 0.91
        // degrees, and **positive is looking up**. tests/test_movement.py.
        //
        // The horizontal reach shortens by cos(pitch) and the vertical is
        // sin(pitch), and the two are directly comparable because
        // `vertical_scale` and `uvRadius`'s scale are the same average of the
        // same two multipliers -- so this stays a unit vector in scene units.
        const tilt = radians(signedPitch(position.pitch));
        const flat = Math.cos(tilt);
        forward.current.set(du * flat, Math.sin(tilt), dv * flat);
        const points = found.facing.geometry.getAttribute("position") as THREE.BufferAttribute;
        points.setXYZ(
          1,
          forward.current.x * FACING_LENGTH,
          forward.current.y * FACING_LENGTH,
          forward.current.z * FACING_LENGTH,
        );
        points.needsUpdate = true;
      }
    }
  });

  return <primitive object={built.root} />;
}

/**
 * Precomputed polylines, one per contiguous run of samples.
 *
 * **Split at gaps longer than `MAX_INTERPOLATE_MS`.**  `trackAt` refuses to
 * interpolate across a long gap precisely because a straight line would cross
 * whatever is between the two points, and a trail that joined them anyway would
 * throw that refusal away.  `segments` applies the same rule, so a trail can
 * never draw a line the position lookup would not.
 *
 * Geometry is built once and `drawRange` moved per frame, rather than rebuilt.
 */
function Trails({
  model,
  art,
  colours,
}: SceneProps & { colours: Record<string, string> }) {
  const reference = useMemo(() => floorZ(model), [model]);

  const built = useMemo(() => {
    const root = new THREE.Group();
    const pieces: Array<{ line: THREE.Line; times: number[] }> = [];
    for (const player of model.replay.players) {
      const track = model.positions.get(player.actor_id);
      if (track === undefined) {
        continue;
      }
      // Built with the opening side and re-set per frame below: a capture with
      // a recorded swap changes every marker's colour halfway through, and a
      // material built once would show the first half's colours all match.
      const colour = new THREE.Color(sideColour(colours, sideOf(model.replay, player.team, 0)));
      for (const run of segments(track, 0, Number.MAX_SAFE_INTEGER)) {
        const points = new Float32Array(run.length * 3);
        run.forEach((sample, i) => {
          const [u, v] = applyTransform(art.transform, sample.x, sample.y);
          points[i * 3] = u;
          points[i * 3 + 1] = (sample.z - reference) * art.transform.vertical_scale;
          points[i * 3 + 2] = v;
        });
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.BufferAttribute(points, 3));
        const line = new THREE.Line(
          geometry,
          new THREE.LineBasicMaterial({ color: colour, transparent: true, opacity: 0.55 }),
        );
        line.visible = false;
        root.add(line);
        pieces.push({ line, times: run.map((sample) => sample.t_ms) });
      }
    }
    return { root, pieces };
  }, [art, colours, model, reference]);

  useFrame(() => {
    const state = usePlayback.getState();
    const from = state.tMs - TRAIL_MS;
    for (const piece of built.pieces) {
      if (!state.layers.trails) {
        piece.line.visible = false;
        continue;
      }
      let start = piece.times.findIndex((t) => t >= from);
      if (start < 0) {
        piece.line.visible = false;
        continue;
      }
      let end = start;
      while (end < piece.times.length && piece.times[end]! <= state.tMs) {
        end += 1;
      }
      const count = end - start;
      if (count < 2) {
        piece.line.visible = false;
        continue;
      }
      // Start one sample earlier where there is one, so the trail meets the
      // marker rather than lagging a tenth of a second behind it.
      start = Math.max(0, start);
      piece.line.geometry.setDrawRange(start, count);
      piece.line.visible = true;
    }
  });

  return <primitive object={built.root} />;
}

/**
 * The planted spike, standing on the ground where it was planted.
 *
 * One cone, built once and moved: a round has at most one plant, and rebuilding
 * geometry every frame for a single marker would be the most expensive object
 * in the scene.  Amber for the reason `theme.py` gives -- an armed spike wants
 * to be red, and team A already is.
 *
 * A cone rather than the 2D triangle because this is a scene and the marker has
 * to read from any bearing the orbit camera reaches; a flat triangle vanishes
 * edge-on, which is the one thing a marker for "the most important object in
 * the round" may not do.
 */
function Spike({
  model,
  art,
  colours,
}: SceneProps & { colours: Record<string, string> }) {
  const reference = useMemo(() => floorZ(model), [model]);

  const built = useMemo(() => {
    const mesh = new THREE.Mesh(
      new THREE.ConeGeometry(SPIKE_RADIUS, SPIKE_HEIGHT, 12),
      new THREE.MeshStandardMaterial({ color: new THREE.Color(colours.spikeArmed!) }),
    );
    mesh.visible = false;
    return mesh;
  }, [colours]);

  useFrame(() => {
    const state = usePlayback.getState();
    const snap = stateAt(model, state.tMs);
    const at = spikeLocation(model, snap);
    if (at === null) {
      built.visible = false;
      return;
    }
    const [u, v] = applyTransform(art.transform, at.x, at.y);
    // Half a cone up, so it stands on the ground rather than through it.
    built.position.set(
      u,
      (at.z - reference) * art.transform.vertical_scale + SPIKE_HEIGHT / 2,
      v,
    );
    built.visible = true;
  });

  return <primitive object={built} />;
}


/**
 * The fatal shot: a glowing beam with a bullet travelling along it.
 *
 * The same two decoded endpoints and the same invented line between them that
 * `MinimapCanvas.drawTracers` draws -- `views/tracers.ts` holds the geometry,
 * the argument, and the reason the flight is on screen before the kill it ends
 * at.  What the scene adds is the half the minimap has nowhere to put: a shot
 * from a heaven spot to a player on the floor below is a line that slopes, and
 * both z values are decoded.
 *
 * **This was a `THREE.Line`, and a line here can be neither wide nor soft.**
 * WebGL draws every line one pixel across whatever `linewidth` says -- the
 * widths in the spec were never implemented by the platform backends -- so the
 * tracer was a hairline in a scene full of lit capsules, which is the "hard to
 * see" half of why this was rewritten.  The beam is a **camera-facing quad**
 * instead: four vertices per slot, rebuilt each frame from the shot's own
 * direction crossed with the direction to the camera, so it keeps its width
 * from any bearing the orbit controls reach rather than vanishing edge-on.
 *
 * Once it is geometry it can carry a picture, and that is where both the glow
 * and the dash now live -- a stripe bright along its centre line and
 * transparent at its edges, with a gap in every repeat.  **The dash had to
 * survive the move**: it is the token that says this line was generated, it was
 * a `LineDashedMaterial` property, and it is a texture property now.  The
 * repeat is derived from the beam's own world length, so a dash stays a fixed
 * size on the map rather than stretching with the distance of the shot.
 *
 * `AdditiveBlending`, and the rule that forbids it next door does not apply.
 * `SightOverlay` may not blend additively because a wash is meant to *shade*
 * the radar and adding would brighten the map instead.  A tracer is a light:
 * adding is what it is for, and it is what makes two shots crossing read as two
 * lights rather than as one flat overlap.
 *
 * One object per slot rather than one per side, because colour and opacity are
 * material properties and two tracers of one side a quarter of a second apart
 * have to fade independently.  Ten of each is nothing.
 */

/** The beam's stripe: bright down the middle, out at the edges, with a gap. */
function beamTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = TRACER_TEXTURE_PX;
  canvas.height = TRACER_TEXTURE_PX;
  const context = canvas.getContext("2d")!;
  // Across the beam: a soft falloff, so its edge is a glow and not a cut.
  const across = context.createLinearGradient(0, 0, 0, TRACER_TEXTURE_PX);
  across.addColorStop(0, "rgba(255,255,255,0)");
  across.addColorStop(0.5, "rgba(255,255,255,1)");
  across.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = across;
  // Along it: a quarter of every repeat is a gap. This is the dash, and it is
  // the only thing on this mark that says it was not decoded.
  context.fillRect(0, 0, Math.round(TRACER_TEXTURE_PX * 0.75), TRACER_TEXTURE_PX);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  return texture;
}

/** The bullet: a radial falloff, which is a glow with nothing else in it. */
function headTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = TRACER_TEXTURE_PX;
  canvas.height = TRACER_TEXTURE_PX;
  const context = canvas.getContext("2d")!;
  const half = TRACER_TEXTURE_PX / 2;
  const glow = context.createRadialGradient(half, half, 0, half, half, half);
  glow.addColorStop(0, "rgba(255,255,255,1)");
  glow.addColorStop(0.25, "rgba(255,255,255,0.85)");
  glow.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = glow;
  context.fillRect(0, 0, TRACER_TEXTURE_PX, TRACER_TEXTURE_PX);
  return new THREE.CanvasTexture(canvas);
}

function Tracers({
  model,
  art,
  colours,
}: SceneProps & { colours: Record<string, string> }) {
  const reference = useMemo(() => floorZ(model), [model]);

  const built = useMemo(() => {
    const group = new THREE.Group();
    // One texture each, shared by every slot: they differ only in colour, and
    // colour is a material tint over a white picture.
    const beam = beamTexture();
    const bullet = headTexture();
    const slots: Array<{ mesh: THREE.Mesh; head: THREE.Sprite }> = [];
    for (let i = 0; i < MAX_TRACERS; i += 1) {
      const geometry = new THREE.BufferGeometry();
      /*
        Four corners, two triangles: muzzle-left, muzzle-right, head-left,
        head-right. V runs across the beam, so the gradient is its width; U
        runs along it and is rewritten per frame from the real world length.
      */
      geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(12), 3));
      geometry.setAttribute(
        "uv",
        new THREE.BufferAttribute(new Float32Array([0, 0, 0, 1, 1, 0, 1, 1]), 2),
      );
      geometry.setIndex([0, 1, 2, 2, 1, 3]);
      const mesh = new THREE.Mesh(
        geometry,
        new THREE.MeshBasicMaterial({
          map: beam,
          transparent: true,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          side: THREE.DoubleSide,
        }),
      );
      const head = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: bullet,
          transparent: true,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      );
      head.scale.setScalar(TRACER_HEAD_SIZE);
      mesh.visible = false;
      head.visible = false;
      /*
        A bounding sphere is computed once, from the buffer as it stood the
        first time something asked -- four points at the origin -- and nothing
        here recomputes it. Left culled, every beam would be discarded as
        off-screen the moment the camera looked anywhere but the map's corner.
      */
      mesh.frustumCulled = false;
      // Over the ground, and over the sight quad, which is `renderOrder = 1`.
      mesh.renderOrder = 2;
      head.renderOrder = 2;
      group.add(mesh);
      group.add(head);
      slots.push({ mesh, head });
    }
    return { group, slots };
  }, []);

  useFrame((frame) => {
    const state = usePlayback.getState();
    const drawn = state.layers.tracers ? tracersAt(model, stateAt(model, state.tMs)) : [];
    // Chest height, the same lift `Actors` stands a body at, so a shot leaves
    // the shooter and lands on the victim rather than crossing the floor
    // between their feet.
    const lift = (z: number) => (z - reference) * art.transform.vertical_scale + BODY_HEIGHT;

    built.slots.forEach((slot, i) => {
      const tracer = drawn[i];
      if (tracer === undefined) {
        slot.mesh.visible = false;
        slot.head.visible = false;
        return;
      }
      const [u1, v1] = applyTransform(art.transform, tracer.from.x, tracer.from.y);
      const [u2, v2] = applyTransform(art.transform, tracer.to.x, tracer.to.y);
      const muzzle = new THREE.Vector3(u1, lift(tracer.from.z), v1);
      const impact = new THREE.Vector3(u2, lift(tracer.to.z), v2);
      // The beam reaches only as far as the bullet has flown, so a reader
      // follows a head with a line behind it rather than a line with a dot on
      // it.
      const at = new THREE.Vector3().lerpVectors(muzzle, impact, tracer.progress);

      const along = new THREE.Vector3().subVectors(at, muzzle);
      const length = along.length();
      const colour = sideColour(colours, tracer.side ?? "");

      if (length < MIN_BEAM_LENGTH) {
        // The instant of the muzzle flash: there is no direction to face a
        // quad along yet, and a degenerate cross product would be NaN.
        slot.mesh.visible = false;
      } else {
        const toCamera = new THREE.Vector3().subVectors(frame.camera.position, muzzle);
        const wide = new THREE.Vector3()
          .crossVectors(along, toCamera)
          .normalize()
          .multiplyScalar(TRACER_HALF_WIDTH);
        const points = slot.mesh.geometry.getAttribute("position") as THREE.BufferAttribute;
        points.setXYZ(0, muzzle.x - wide.x, muzzle.y - wide.y, muzzle.z - wide.z);
        points.setXYZ(1, muzzle.x + wide.x, muzzle.y + wide.y, muzzle.z + wide.z);
        points.setXYZ(2, at.x - wide.x, at.y - wide.y, at.z - wide.z);
        points.setXYZ(3, at.x + wide.x, at.y + wide.y, at.z + wide.z);
        points.needsUpdate = true;

        // The dash, held to a fixed size on the map rather than stretched
        // across however far this particular shot happened to travel.
        const uv = slot.mesh.geometry.getAttribute("uv") as THREE.BufferAttribute;
        const repeats = Math.max(1, Math.round(length / TRACER_DASH_UV));
        uv.setXY(2, repeats, 0);
        uv.setXY(3, repeats, 1);
        uv.needsUpdate = true;

        const material = slot.mesh.material as THREE.MeshBasicMaterial;
        material.color.set(colour);
        material.opacity = tracer.alpha;
        slot.mesh.visible = true;
      }

      const headMaterial = slot.head.material as THREE.SpriteMaterial;
      headMaterial.color.set(colour);
      headMaterial.opacity = tracer.alpha;
      slot.head.position.copy(at);
      slot.head.visible = true;
    });
  });

  return <primitive object={built.group} />;
}

/**
 * Every living player's sight cone, as one overlay lying on the ground plane.
 *
 * It is a two-dimensional claim about a silhouette; extruding it into a frustum
 * would be inventing the geometry this project does not have.
 *
 * One quad rather than one mesh per player, and that is what makes this view
 * agree with the minimap instead of merely resembling it.  The flat wash this
 * layer is built on -- one cone and five overlapping ones reading identically
 * -- cannot be had from k separate transparent meshes: fixed-function alpha
 * blending composites them against each other, so at `SIGHT_ALPHA`'s quarter
 * two overlapping cones would come out at 43.75% and three at 57.8% instead of
 * the flat quarter a side's wash is, and an additive blend would brighten the
 * radar instead of shading it -- which is the opposite of what a wash is for,
 * and is exactly why `Tracers` above *may* blend additively where this may not:
 * a tracer is a light, and a wash is a shadow.  The union has to be accumulated
 * somewhere that is not the framebuffer.
 * So `sightlayer` rasterises the cones exactly as it does for the 2D canvas,
 * and the result arrives here as a texture -- same selection, same gates, same
 * colours, same arithmetic, one implementation.
 *
 * What is *not* the same is edge fidelity: the minimap rasterises in screen
 * space and stays crisp at any zoom, where this is a fixed `SIGHT_RASTER` grid
 * in uv.  At 1024 that matches the radar underneath it and is four times finer
 * than the 256-cell mask the cone shape comes from, so nothing is lost that was
 * ever there -- but zoomed hard into a corner, this rim is resampled and that
 * one is not.
 *
 * Two things this gains by sharing the code, both of which were quiet faults
 * rather than deliberate differences: a hidden side no longer draws a cone with
 * no marker under it, and a smoke now cuts the cone here the way it always has
 * on the minimap.
 */
function SightOverlay({
  model,
  art,
  mask,
  colours,
}: SceneProps & { colours: Record<string, string> }) {
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

  /** Where the cones are accumulated before they reach the texture's canvas. */
  const scratch = useRef<HTMLCanvasElement | null>(null);
  /*
    What was painted last, so a paused viewer costs nothing.

    `useFrame` runs at 60 Hz and the cone set changes only with the playhead,
    the layer switch, which sides are shown and which map this is.  Without
    this the overlay would push four megabytes to the GPU sixty times a second
    to redraw a picture that had not changed -- and this viewer is paused most
    of the time, and always paused when Playwright photographs it.
  */
  const painted = useRef<string | null>(null);

  /*
    The canvas, the texture over it and the mesh, built together and kept
    together.

    The canvas is deliberately *returned* rather than parked in a ref during
    render.  Under `StrictMode` React invokes this factory twice and throws one
    result away, so a ref written here can end up holding the discarded
    canvas while the surviving texture wraps the other -- and then every frame
    paints cones into a canvas the GPU never samples, which is a scene with no
    cones in it and no error anywhere.  Keeping them in one object makes that
    unrepresentable.
  */
  const built = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = SIGHT_RASTER;
    canvas.height = SIGHT_RASTER;

    const texture = new THREE.CanvasTexture(canvas);
    // `flipY = false` and the UVs written out longhand below, so texture (0,0)
    // is the first pixel painted and u, v mean exactly what `applyTransform`
    // returns -- the same contract `Ground` holds itself to.
    texture.flipY = false;
    texture.colorSpace = THREE.SRGBColorSpace;
    // No mip chain: it would be rebuilt on every upload, which is the cost
    // nobody profiles, and this quad is never seen at a minifying distance.
    texture.generateMipmaps = false;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;

    const geometry = new THREE.BufferGeometry();
    // (u, v) -> (x, y, z) = (u, SIGHT_LIFT, v), the same quad as the ground.
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(
        [0, SIGHT_LIFT, 0, 1, SIGHT_LIFT, 0, 0, SIGHT_LIFT, 1, 1, SIGHT_LIFT, 1],
        3,
      ),
    );
    geometry.setAttribute("uv", new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, 1, 1, 1], 2));
    geometry.setAttribute(
      "normal",
      new THREE.Float32BufferAttribute([0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0], 3),
    );
    geometry.setIndex([0, 2, 1, 2, 3, 1]);

    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        // The alpha is in the texture, put there once by `paintCones`. A
        // material opacity here would be a second place the wash's strength
        // lived, and the two canvases would drift the day one of them moved.
        opacity: 1,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    // Explicit, rather than relying on the transparent sort to favour the
    // lifted quad: the ground is 0, and this lies on top of it.
    mesh.renderOrder = 1;
    mesh.visible = false;
    return { mesh, texture, canvas };
  }, []);

  useEffect(
    () => () => {
      built.texture.dispose();
      built.mesh.geometry.dispose();
      (built.mesh.material as THREE.Material).dispose();
    },
    [built],
  );

  useFrame(() => {
    const state = usePlayback.getState();
    if (!state.layers.sight || silhouette === null || settings === null) {
      built.mesh.visible = false;
      // Forget what was painted, so switching the layer back on repaints even
      // though nothing else moved.  Without this, toggling SIGHT off and on
      // again while paused leaves the key unchanged, takes the early return
      // below, and never puts the mesh back -- a switch that works once.
      painted.current = null;
      return;
    }
    const key = `${state.tMs}|${state.hiddenTeams.join(",")}|${mask?.map_key ?? ""}`;
    if (key === painted.current) {
      return;
    }

    const context = built.canvas.getContext("2d");
    if (context === null) {
      built.mesh.visible = false;
      return;
    }
    const snap = stateAt(model, state.tMs);
    const cones = sightCones({
      model,
      art,
      snap,
      silhouette,
      settings,
      shown: (team: string) => teamShown(state, team),
      smokes: smokesAt(art, snap),
    });

    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, SIGHT_RASTER, SIGHT_RASTER);
    paintCones(
      context,
      cones,
      colours,
      (u, v) => [u * SIGHT_RASTER, v * SIGHT_RASTER],
      scratch,
      { width: SIGHT_RASTER, height: SIGHT_RASTER, scale: 1 },
    );
    built.texture.needsUpdate = true;
    built.mesh.visible = cones.length > 0;
    // Only once the paint has actually happened: marking the key done above
    // would make any early exit permanent for that instant.
    painted.current = key;
  });

  return <primitive object={built.mesh} />;
}

/**
 * Riot's own callouts, at their scene positions.  A check, not a feature.
 *
 * `mapref` already proves the transform lands 346 of 346 callouts inside the
 * image in two dimensions.  Dropping the same points here and comparing the two
 * views is what *verifies* the scene's orientation rather than asserting it --
 * the four independent ways a textured ground plane can end up mirrored all
 * show up immediately as callouts in the wrong halves.
 *
 * It draws the map and never the match, which is why it is handed a `MapArt`
 * and has no way to reach a player.
 */
function Callouts({ art }: { art: MapArt }) {
  const show = usePlayback((state) => state.layers.callouts);
  if (!show) {
    return null;
  }
  return (
    <group>
      {art.callouts.map((callout) => {
        const [u, v] = applyTransform(art.transform, callout.world_x, callout.world_y);
        return (
          <Html
            key={`${callout.name}-${callout.world_x}-${callout.world_y}`}
            position={[u, SIGHT_LIFT, v]}
            center
            style={{
              pointerEvents: "none",
              whiteSpace: "nowrap",
              fontSize: 9,
              fontFamily: "monospace",
              color: "var(--text-primary)",
              // A plate rather than stacked shadows against a hard-coded
              // black: the radar is light in places and dark in others.
              background: "color-mix(in srgb, var(--app-bg) 78%, transparent)",
              border: "1px solid color-mix(in srgb, var(--border) 70%, transparent)",
              borderRadius: "var(--radius-sm)",
              padding: "1px 4px",
            }}
          >
            {callout.name}
          </Html>
        );
      })}
    </group>
  );
}
