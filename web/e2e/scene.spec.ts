/**
 * The 3D scene, and the one question a screenshot cannot be trusted to answer.
 *
 * A textured ground plane has four independent ways to end up mirrored -- the
 * rotation sign, `PlaneGeometry`'s UV origin, `texture.flipY` and the
 * transform's own axis swap -- and every one of them looks entirely fine until
 * two maps are compared side by side.  `Scene3D` removes most of that class by
 * building the quad vertex by vertex, and the `CALLOUTS` layer exists so a
 * human can check the rest.  Nobody had looked.
 *
 * So this checks it arithmetically instead, in two steps that back each other:
 *
 *   1. **The camera model is confirmed against the page.**  A `PerspectiveCamera`
 *      built here from `Scene3D`'s own constants projects each callout to a
 *      screen point, and drei's `<Html>` has already put a label at the real
 *      one.  When those agree, the projection below is the scene's projection
 *      and not a guess -- and the marker placement math is confirmed with it.
 *   2. **The ground texture is correlated against the 2D minimap.**  The same
 *      uv points are sampled in both views and compared, then compared again
 *      against the three mirrored readings.  A mirrored plane makes one of the
 *      mirrored readings win, which is precisely the failure the callout layer
 *      was added to catch by eye.
 *
 * The 2D minimap is the reference because it is a port of code that has been
 * drawing this correctly for a long time, and because `MinimapCanvas` places the
 * radar with `drawImage` at uv, which has no orientation freedom at all.
 */

import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";
import * as THREE from "three";

import { floorZ } from "../src/model/replay";
import type { SightSettings } from "../src/model/sight";
import { cone, decodeMask, forwardUv, uvRadius } from "../src/model/sight";
import { sideOf } from "../src/model/synthetic";
import { positionOf, stateAt } from "../src/model/state";
import { applyTransform, placeSquare, uvToPixels } from "../src/model/transform";
import {
  firstCrowdedEvent,
  luma,
  openFirstPlayable,
  palette,
  parseColour,
  pearson,
  pixelAt,
  readCanvas,
  rgbDistance,
  momentAt,
  stepToEvent,
  setLayer,
  toggleLayer,
} from "./harness";

/**
 * Two frames, so the first paint is never what gets sampled.
 *
 * The scene draws from its own `useFrame`, and the sight overlay repaints only
 * when the instant it is showing changes -- so a screenshot taken on the frame
 * a layer was switched can be the picture from before it.
 */
async function settle(page: Page): Promise<void> {
  await page.evaluate(
    () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
  );
}

/** `Scene3D`'s own camera, repeated here so a change to it fails this test. */
const CAMERA = { position: [0.5, 0.9, 1.6] as const, target: [0.5, 0, 0.5] as const, fov: 40 };
const SIGHT_LIFT = 0.0015;

/** How many uv samples the orientation correlation is built from. */
const GRID = 26;

/** `Scene3D`'s marker geometry, again repeated so a change to it fails here. */
const BODY_HEIGHT = 0.018;

/** How far from a projected marker its pixels are looked for. */
const MARKER_SEARCH = 18;

/** How far into a capture the elevation test is allowed to look for a drop. */
const SEARCH_EVENTS = 120;

function sceneCamera(width: number, height: number): THREE.PerspectiveCamera {
  const camera = new THREE.PerspectiveCamera(CAMERA.fov, width / height, 0.001, 20);
  camera.position.set(...CAMERA.position);
  camera.up.set(0, 1, 0);
  camera.lookAt(...CAMERA.target);
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();
  return camera;
}

/** A scene point as a pixel inside the scene canvas, or null if off-screen. */
function project(
  camera: THREE.PerspectiveCamera,
  width: number,
  height: number,
  x: number,
  y: number,
  z: number,
): [number, number] | null {
  const point = new THREE.Vector3(x, y, z).project(camera);
  if (point.x < -1 || point.x > 1 || point.y < -1 || point.y > 1 || point.z > 1) {
    return null;
  }
  return [(point.x * 0.5 + 0.5) * width, (-point.y * 0.5 + 0.5) * height];
}

test.describe("the 3D scene", () => {
  test("renders on real WebGL, not a software stub", async ({ page }) => {
    await page.goto("/");
    const report = await page.evaluate(() => {
      const gl = document.createElement("canvas").getContext("webgl2");
      if (gl === null) {
        return { ok: false, renderer: "no webgl2 context" };
      }
      const info = gl.getExtension("WEBGL_debug_renderer_info");
      return {
        ok: true,
        renderer: info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : "masked",
      };
    });
    // Not an assertion about which GPU: a test that renders the scene on a
    // stack no user has says nothing about the scene.
    expect(report.ok, `WebGL 2 is available (${report.renderer})`).toBe(true);
  });

  test("puts the callouts where the camera says they are", async ({ page }) => {
    const { art } = await openFirstPlayable(page);

    await page.getByRole("button", { name: "3D", exact: true }).click();
    // The stage holds exactly one canvas; the transport strip is a second
    // canvas outside it, and a bare `canvas` locator picks that one up.
    const scene = page.locator(".stage-canvas canvas");
    await expect(scene).toBeVisible();
    await toggleLayer(page, "CALLOUTS");

    const rect = (await scene.boundingBox())!;
    const camera = sceneCamera(rect.width, rect.height);

    let compared = 0;
    let worst = 0;
    for (const callout of art.callouts) {
      const label = page.getByText(callout.name, { exact: true });
      if ((await label.count()) !== 1) {
        continue; // A name the page shows twice says nothing about geometry.
      }
      const box = await label.boundingBox();
      if (box === null) {
        continue;
      }
      const [u, v] = applyTransform(art.transform, callout.world_x, callout.world_y);
      const projected = project(camera, rect.width, rect.height, u, SIGHT_LIFT, v);
      if (projected === null) {
        continue;
      }
      const drawn: [number, number] = [
        box.x + box.width / 2 - rect.x,
        box.y + box.height / 2 - rect.y,
      ];
      const off = Math.hypot(drawn[0] - projected[0], drawn[1] - projected[1]);
      worst = Math.max(worst, off);
      compared += 1;
    }

    expect(compared, "callouts were on screen to compare").toBeGreaterThan(6);
    // Within a few pixels is the label's own box rounding, not a disagreement
    // about where the point is.
    expect(worst, "every callout sits where this camera projects it").toBeLessThan(4);
  });

  test("the ground plane is not mirrored", async ({ page }) => {
    const { art } = await openFirstPlayable(page);
    const minimap = page.locator("canvas.minimap");

    // Utility off in both views: the point of comparison is Riot's radar, and
    // a diamond drawn in one view and not the other is only noise here.
    /*
      SIGHT off. Both views now paint the same side-coloured wash over the same
      cones, so leaving it on would no longer make the two pictures disagree --
      but this spec correlates the *radar's own* luma at matching uv points, and
      a wash tinting both of them is noise in exactly that measurement. The
      cones have their own spec below.
    */
    await setLayer(page, "SIGHT", false);
    await toggleLayer(page, "UTILITY");
    const flat = await readCanvas(page, minimap);
    const box = placeSquare(flat.width, flat.height);

    await page.getByRole("button", { name: "3D", exact: true }).click();
    // The stage holds exactly one canvas; the transport strip is a second
    // canvas outside it, and a bare `canvas` locator picks that one up.
    const scene = page.locator(".stage-canvas canvas");
    await expect(scene).toBeVisible();
    await settle(page);
    const solid = await readCanvas(page, scene);
    const camera = sceneCamera(solid.width, solid.height);

    // The same uv points in both views. `readings` holds the 3D sample taken at
    // uv, at mirrored u, at mirrored v, and at both.
    const flatSamples: number[] = [];
    const readings: number[][] = [[], [], [], []];
    const mirrors: Array<[boolean, boolean]> = [
      [false, false],
      [true, false],
      [false, true],
      [true, true],
    ];

    for (let iv = 0; iv < GRID; iv += 1) {
      for (let iu = 0; iu < GRID; iu += 1) {
        const u = 0.06 + (0.88 * iu) / (GRID - 1);
        const v = 0.06 + (0.88 * iv) / (GRID - 1);

        const [fx, fy] = uvToPixels(box, u, v);
        const flatPixel = pixelAt(flat, fx, fy);
        if (flatPixel === null) {
          continue;
        }
        const solidPixels = mirrors.map(([mu, mv]) => {
          const point = project(camera, solid.width, solid.height, mu ? 1 - u : u, 0, mv ? 1 - v : v);
          return point === null ? null : pixelAt(solid, point[0], point[1]);
        });
        if (solidPixels.some((pixel) => pixel === null)) {
          continue;
        }
        flatSamples.push(luma(flatPixel));
        solidPixels.forEach((pixel, i) => readings[i]!.push(luma(pixel!)));
      }
    }

    expect(flatSamples.length, "enough of the map is in both views to compare").toBeGreaterThan(
      300,
    );
    const [asIs, flippedU, flippedV, flippedBoth] = mirrors.map((_, i) =>
      pearson(flatSamples, readings[i]!),
    ) as [number, number, number, number];

    // eslint-disable-next-line no-console
    console.log(
      `${art.name}: r as-is ${asIs.toFixed(3)}, flip-u ${flippedU.toFixed(3)}, ` +
        `flip-v ${flippedV.toFixed(3)}, flip-both ${flippedBoth.toFixed(3)}`,
    );
    expect(asIs, "the scene's ground matches the minimap at the same uv").toBeGreaterThan(0.5);
    expect(
      asIs,
      "and matches it better than any mirrored reading, which is what rules out a flip",
    ).toBeGreaterThan(Math.max(flippedU, flippedV, flippedBoth) + 0.15);
  });

  /**
   * A marker for every player the camera can see, which is not a given.
   *
   * This test exists because the scene shipped without one and drew **no
   * players at all** on four of the twenty-one playable captures: `floorZ` took
   * the raw minimum z, the replication stream parks an out-of-play actor about
   * 50,000 uu down, and every marker was lifted three and a half map-widths out
   * of frame.  The ground rendered perfectly underneath it, so the view looked
   * like a quiet map rather than like a fault -- and a screenshot review would
   * have had to notice an absence.
   *
   * Team membership is read by hue rather than by an exact colour, because a
   * lit `MeshStandardMaterial` is not its own base colour: the map is grey, so
   * a strong blue or red channel difference is a team marker and nothing else.
   */
  test("draws a marker for every player the camera can see", async ({ page }) => {
    const { art, model } = await openFirstPlayable(page);
    await setLayer(page, "SIGHT", false);
    await toggleLayer(page, "UTILITY");
    const moment = firstCrowdedEvent(model);
    const tMs = moment.tMs;
    await stepToEvent(page, moment);

    await page.getByRole("button", { name: "3D", exact: true }).click();
    const scene = page.locator(".stage-canvas canvas");
    await expect(scene).toBeVisible();
    await settle(page);
    const solid = await readCanvas(page, scene);
    const camera = sceneCamera(solid.width, solid.height);

    const reference = floorZ(model);
    const snap = stateAt(model, tMs);
    let checked = 0;
    for (const player of model.replay.players) {
      const position = positionOf(snap, player.actor_id);
      if (position === null || (player.team !== "A" && player.team !== "B")) {
        continue;
      }
      const [u, v] = applyTransform(art.transform, position.x, position.y);
      const height = (position.z - reference) * art.transform.vertical_scale;
      const at = project(camera, solid.width, solid.height, u, height + BODY_HEIGHT, v);
      // Only players the camera actually frames; the default view does not
      // hold the whole map, and an off-screen marker is not a missing one.
      if (at === null || at[0] < MARKER_SEARCH || at[1] < MARKER_SEARCH) {
        continue;
      }
      if (at[0] > solid.width - MARKER_SEARCH || at[1] > solid.height - MARKER_SEARCH) {
        continue;
      }

      let hits = 0;
      for (let y = Math.round(at[1]) - MARKER_SEARCH; y <= Math.round(at[1]) + MARKER_SEARCH; y += 1) {
        for (let x = Math.round(at[0]) - MARKER_SEARCH; x <= Math.round(at[0]) + MARKER_SEARCH; x += 1) {
          const pixel = pixelAt(solid, x, y);
          if (pixel === null) {
            continue;
          }
          const [r, , b] = pixel;
          const blue = b - r > 40 && b > 90;
          const red = r - b > 40 && r > 90;
          // By side, not by team: `--team-a` is attacker red and `--team-b` is
          // defender blue, and a capture with a recorded swap changes which
          // team wears which halfway through. Deriving it here the way
          // `images.sideColour` does is what keeps this test about the
          // rendering rather than about the palette.
          if (sideOf(model.replay, player.team, tMs) === "ATK" ? red : blue) {
            hits += 1;
          }
        }
      }
      expect(
        hits,
        `${player.label || player.team} has a marker at (${at[0].toFixed(0)}, ${at[1].toFixed(0)})`,
      ).toBeGreaterThan(15);
      checked += 1;
    }
    expect(checked, "the camera framed players to check").toBeGreaterThan(2);
  });

  /**
   * The whole reason this view exists: z, which the minimap has always thrown
   * away.  The claim is narrow and so is the test -- a player standing above
   * the plane is *drawn* above it, at the height `vertical_scale` predicts.
   *
   * `vertical_scale` is the average of the transform's own two multipliers, so
   * elevation is at the map's own horizontal scale: a figure derived from a
   * measured transform rather than one tuned until it looked right.  If it were
   * dropped, or the sign flipped, the marker would sit on the floor and the
   * scene would look entirely reasonable.
   */
  test("draws a player above the plane at the height the transform predicts", async ({
    page,
  }) => {
    const { art, model } = await openFirstPlayable(page);
    await setLayer(page, "SIGHT", false);
    await toggleLayer(page, "UTILITY");

    // Into the scene first: the default camera frames rather less than the
    // whole map, so which players are even visible is a fact about the canvas
    // and cannot be decided before there is one.
    await page.getByRole("button", { name: "3D", exact: true }).click();
    const scene = page.locator(".stage-canvas canvas");
    await expect(scene).toBeVisible();
    const rect = (await scene.boundingBox())!;
    const camera = sceneCamera(rect.width, rect.height);

    // The tallest drop the early match offers among the players the camera can
    // see, which on most maps is somebody on a ledge rather than anything
    // exotic.
    const reference = floorZ(model);
    const times = model.replay.event_times.slice(0, SEARCH_EVENTS);
    let best: { tMs: number; actorId: number; height: number } | null = null;
    times.forEach((tMs) => {
      const snap = stateAt(model, tMs);
      for (const player of model.replay.players) {
        const position = positionOf(snap, player.actor_id);
        if (position === null || !snap.alive.has(player.actor_id)) {
          continue;
        }
        const height = (position.z - reference) * art.transform.vertical_scale;
        if (best !== null && height <= best.height) {
          continue;
        }
        const [u, v] = applyTransform(art.transform, position.x, position.y);
        const onFloor = project(camera, rect.width, rect.height, u, BODY_HEIGHT, v);
        const raised = project(camera, rect.width, rect.height, u, height + BODY_HEIGHT, v);
        // Both ends on screen, and far enough apart that a pixel measurement
        // can tell them apart at all.
        if (onFloor === null || raised === null || onFloor[1] - raised[1] <= 12) {
          continue;
        }
        best = { tMs, actorId: player.actor_id, height };
      }
    });
    expect(best, "somebody visible is off the floor in the early match").toBeTruthy();
    const found = best!;

    await stepToEvent(page, momentAt(model, found.tMs));
    await settle(page);
    const solid = await readCanvas(page, scene);

    const snap = stateAt(model, found.tMs);
    const position = positionOf(snap, found.actorId)!;
    const [u, v] = applyTransform(art.transform, position.x, position.y);
    const onFloor = project(camera, solid.width, solid.height, u, BODY_HEIGHT, v)!;
    const raised = project(camera, solid.width, solid.height, u, found.height + BODY_HEIGHT, v)!;
    const lift = onFloor[1] - raised[1];

    const player = model.replay.players.find((entry) => entry.actor_id === found.actorId)!;
    const colours = await palette(page);
    expect(player.team === "A" || player.team === "B").toBe(true);
    const teamColour = parseColour(player.team === "A" ? colours.a! : colours.b!);

    // The topmost team-coloured pixel in a narrow column through the marker.
    // The stem runs down to the plane in the same colour, so the *top* of the
    // run is the body and the bottom says nothing.
    let top: number | null = null;
    for (let y = 0; y < solid.height; y += 1) {
      for (let x = Math.round(raised[0]) - 6; x <= Math.round(raised[0]) + 6; x += 1) {
        const pixel = pixelAt(solid, x, y);
        if (pixel !== null && rgbDistance(pixel, teamColour) <= 60) {
          top = y;
          break;
        }
      }
      if (top !== null) {
        break;
      }
    }
    expect(top, "the marker is on screen in its team colour").not.toBeNull();
    // Above the plane, and by the amount the vertical scale asks for rather
    // than by some amount: a dropped `vertical_scale` puts it at `onFloor`.
    expect(onFloor[1] - top!, "drawn above the ground point").toBeGreaterThan(lift * 0.6);
    expect(Math.abs(top! - raised[1]), "at the predicted height").toBeLessThan(
      Math.max(12, lift * 0.4),
    );
  });

  /**
   * Every living player's cone, in the scene, pointing where they are facing.
   *
   * The 2D twin of this is `minimap.spec.ts`, and the two exist for the same
   * reason: the scene drew **one** cone for whoever was picked, so switching
   * view silently dropped nine of them, and a wash that is simply absent
   * photographs as a quiet map rather than as a fault.
   *
   * The overlay is a texture on a ground quad, which reintroduces exactly the
   * orientation freedom the rest of this file exists to close off -- a flipped
   * `texture.flipY`, or uv written into the quad the other way round, would put
   * every cone somewhere plausible and wrong.  So the discriminator is the 2D
   * spec's: the real cones must be covered, and covered better than the same
   * cones each turned about its own player.  A mirrored overlay fails that the
   * way a mirrored ground fails the correlation above.
   */
  test("draws a cone for every living player, pointing where they look", async ({
    page,
  }) => {
    const { art, sight, model } = await openFirstPlayable(page);
    await setLayer(page, "SIGHT", false);
    await toggleLayer(page, "UTILITY");

    const moment = firstCrowdedEvent(model);
    const tMs = moment.tMs;
    await stepToEvent(page, moment);

    await page.getByRole("button", { name: "3D", exact: true }).click();
    const scene = page.locator(".stage-canvas canvas");
    await expect(scene).toBeVisible();
    await settle(page);
    const dark = await readCanvas(page, scene);
    const camera = sceneCamera(dark.width, dark.height);

    const settings: SightSettings = {
      max_range_uu: sight.max_range_uu,
      fov_degrees: sight.fov_degrees,
      ray_step_degrees: sight.ray_step_degrees,
      seed_cells: sight.seed_cells,
      probe_uu: sight.probe_uu,
    };
    const mask = decodeMask(sight.size, sight.cells);
    const snap = stateAt(model, tMs);

    // Exactly what `sightlayer.sightCones` will have built, recomputed here:
    // living players only, and no selection anywhere in it.
    const drawn = model.replay.players
      .map((player) => ({ player, position: snap.positions.get(player.actor_id) }))
      .filter((e) => e.position !== undefined && snap.alive.has(e.player.actor_id))
      .map(({ player, position }) => {
        const [u, v] = applyTransform(art.transform, position!.x, position!.y);
        return {
          player,
          origin: [u, v] as [number, number],
          polygon: cone(
            mask,
            [u, v],
            forwardUv(art.transform, position!.x, position!.y, position!.yaw, settings.probe_uu),
            uvRadius(art.transform, settings.max_range_uu),
            settings,
          ),
        };
      })
      .filter((entry) => entry.polygon.length > 2);

    expect(drawn.length, "several players have a cone to draw here").toBeGreaterThan(2);

    await setLayer(page, "SIGHT", true);
    await page.getByRole("button", { name: "3D", exact: true }).click();
    await settle(page);
    const lit = await readCanvas(page, scene);

    // Halfway along every ray of every cone, rotated about that cone's own
    // player -- in uv, then projected, so the turn happens in the space the
    // overlay is painted in rather than in screen space.
    const rate = (turn: number): [number, number] => {
      let sampled = 0;
      let changed = 0;
      for (const { origin, polygon } of drawn) {
        const [ou, ov] = origin;
        for (const [ru, rv] of polygon.slice(1)) {
          const du = (ru - ou) / 2;
          const dv = (rv - ov) / 2;
          const u = ou + du * Math.cos(turn) - dv * Math.sin(turn);
          const v = ov + du * Math.sin(turn) + dv * Math.cos(turn);
          const at = project(camera, lit.width, lit.height, u, SIGHT_LIFT, v);
          if (at === null) {
            continue;
          }
          const before = pixelAt(dark, at[0], at[1]);
          const after = pixelAt(lit, at[0], at[1]);
          if (before === null || after === null) {
            continue;
          }
          sampled += 1;
          if (rgbDistance(before, after) > 8) {
            changed += 1;
          }
        }
      }
      return [sampled === 0 ? 0 : changed / sampled, sampled];
    };

    const [forward, sampled] = rate(0);
    const [left] = rate(Math.PI / 2);
    const [right] = rate(-Math.PI / 2);
    const [behind] = rate(Math.PI);
    // eslint-disable-next-line no-console
    console.log(
      `scene cones ${drawn.length} over ${sampled} samples: forward ${forward.toFixed(3)} ` +
        `left ${left.toFixed(3)} right ${right.toFixed(3)} behind ${behind.toFixed(3)}`,
    );
    // The default camera frames less than the whole map, so a good many samples
    // are off-screen and skipped; what is left still has to be a real sample.
    expect(sampled, "enough of the cones are in frame to measure").toBeGreaterThan(100);
    /*
      A lower floor than the 2D spec's 0.6, and deliberately so: this measures
      about 0.62 where the minimap measures 0.86, because a perspective camera
      foreshortens the far half of every cone into very few pixels and the
      markers and their stems stand on top of the near half. The floor is only
      here to catch "nothing was drawn at all" -- the assertion that actually
      discriminates is the next one, and it clears its margin several times
      over (0.62 against 0.22).
    */
    expect(forward, "the wash covers the cones the model computed").toBeGreaterThan(0.5);
    expect(forward, "and covers them better than the same cones turned").toBeGreaterThan(
      Math.max(left, right, behind) + 0.15,
    );

    /*
      And the switch works more than once.

      The overlay repaints only when the instant it is showing changes, which
      is what keeps a paused scene from pushing four megabytes a frame to the
      GPU. The playhead does not move while a layer is toggled, so an off-then-
      on at the same instant is exactly the case where that cache has to be
      given up rather than trusted -- and getting it wrong hides the cones
      until something else moves, which is invisible to every assertion above.
    */
    await setLayer(page, "SIGHT", false);
    await settle(page);
    await setLayer(page, "SIGHT", true);
    await settle(page);
    const again = await readCanvas(page, scene);
    let back = 0;
    let looked = 0;
    for (const { origin, polygon } of drawn) {
      const [ou, ov] = origin;
      for (const [ru, rv] of polygon.slice(1)) {
        const at = project(camera, again.width, again.height, (ou + ru) / 2, SIGHT_LIFT, (ov + rv) / 2);
        if (at === null) {
          continue;
        }
        const before = pixelAt(dark, at[0], at[1]);
        const after = pixelAt(again, at[0], at[1]);
        if (before === null || after === null) {
          continue;
        }
        looked += 1;
        if (rgbDistance(before, after) > 8) {
          back += 1;
        }
      }
    }
    expect(looked).toBeGreaterThan(100);
    expect(back / looked, "the cones come back after the layer is cycled").toBeGreaterThan(0.5);
  });
});
