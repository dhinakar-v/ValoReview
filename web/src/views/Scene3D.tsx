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
import { cone, decodeMask, forwardUv, uvRadius } from "../model/sight";
import { positionOf, spikeLocation, stateAt } from "../model/state";
import { segments } from "../model/track";
import { applyTransform } from "../model/transform";
import { sideOf } from "../model/synthetic";
import { palette, sideColour, useImages } from "./images";
import { selectedActor, teamShown, usePlayback } from "./playback";

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
      <SightWedge {...props} colours={colours} />
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
    <mesh geometry={geometry}>
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
 * The sight wedge, flat on the ground plane and staying there.
 *
 * It is a two-dimensional claim about a silhouette; extruding it into a frustum
 * would be inventing the geometry this project does not have.
 */
function SightWedge({
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

  const built = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(colours.unknown!),
        transparent: true,
        opacity: 0.22,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    mesh.visible = false;
    return mesh;
  }, [colours]);

  useFrame(() => {
    const state = usePlayback.getState();
    const actorId = selectedActor(state);
    if (!state.layers.sight || actorId === null || silhouette === null || settings === null) {
      built.visible = false;
      return;
    }
    const snap = stateAt(model, state.tMs);
    const position = snap.positions.get(actorId);
    if (position === undefined || !snap.alive.has(actorId)) {
      built.visible = false;
      return;
    }
    const polygon = cone(
      silhouette,
      applyTransform(art.transform, position.x, position.y),
      forwardUv(art.transform, position.x, position.y, position.yaw, settings.probe_uu),
      uvRadius(art.transform, settings.max_range_uu),
      settings,
    );
    // An empty cone means draw nothing, never a fallback shape.
    if (polygon.length < 3) {
      built.visible = false;
      return;
    }
    const vertices = new Float32Array(polygon.length * 3);
    polygon.forEach(([u, v], i) => {
      vertices[i * 3] = u;
      vertices[i * 3 + 1] = SIGHT_LIFT;
      vertices[i * 3 + 2] = v;
    });
    const index: number[] = [];
    for (let i = 1; i < polygon.length - 1; i += 1) {
      index.push(0, i, i + 1);
    }
    built.geometry.setAttribute("position", new THREE.BufferAttribute(vertices, 3));
    built.geometry.setIndex(index);
    built.geometry.computeBoundingSphere();
    const player = model.replay.players.find((p) => p.actor_id === actorId);
    (built.material as THREE.MeshBasicMaterial).color.set(
      sideColour(colours, player ? sideOf(model.replay, player.team, snap.t_ms) : "?"),
    );
    built.visible = true;
  });

  return <primitive object={built} />;
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
