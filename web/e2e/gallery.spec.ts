/**
 * Pictures of every view, for the judgements no assertion can make.
 *
 * The rest of this directory asserts things: where a marker is, which way a
 * cone points, whether a plane is mirrored.  Some questions are not of that
 * kind -- whether a marker is a readable size, whether a busy round's worth of
 * utility diamonds is legible, whether the scene's camera frames anything worth
 * looking at -- and answering them by adding a threshold would be inventing a
 * standard rather than applying one.
 *
 * So this renders each view and saves it.  It asserts only that a view came out
 * non-empty; the files are for a person, and `npx playwright show-report`
 * carries them.
 */

import { expect, test } from "@playwright/test";

import { positionOf, stateAt } from "../src/model/state";
import { applyTransform, placeSquare, uvToPixels } from "../src/model/transform";
import {
  firstCrowdedEvent,
  openFirstPlayable,
  readCanvas,
  setLayer,
  stepToEvent,
  toggleLayer,
} from "./harness";

test("every view, rendered and saved for a person to look at", async ({ page }, testInfo) => {
  const { replay, art, model } = await openFirstPlayable(page);
  // A quarter of the way in, so this is a round in progress with utility on
  // the map rather than two spawn rooms -- which is the thing that actually
  // needs looking at.
  const moment = firstCrowdedEvent(model, 8, 0.25);
  const tMs = moment.tMs;
  await stepToEvent(page, moment);

  const stage = page.locator(".panel.stage");
  const shots: Array<[string, Buffer]> = [];

  const take = async (name: string) => {
    // Both: a file on disk under `outputDir`, which is where somebody looking
    // for these will look, and an attachment, which is what the HTML report
    // carries when the run happened somewhere else.
    const shot = await stage.screenshot({ path: testInfo.outputPath(name) });
    shots.push([name, shot]);
    await testInfo.attach(name, { body: shot, contentType: "image/png" });
  };

  await take("2d-minimap.png");
  await toggleLayer(page, "TRAILS");
  await take("2d-trails.png");
  await toggleLayer(page, "TRAILS");

  // A cone is drawn for every living player now, so this no longer *needs* a
  // selection -- but the picked player's wedge is the heavier one, and a
  // gallery shot of the layer should show that difference rather than ten
  // identical washes. So the click stays, and it lands where the model says a
  // player is: clicking empty canvas selects nobody.
  const minimap = page.locator("canvas.minimap");
  const image = await readCanvas(page, minimap);
  const box = placeSquare(image.width, image.height);
  const snap = stateAt(model, tMs);
  const chosen = model.replay.players
    .map((player) => positionOf(snap, player.actor_id))
    .find((position) => position !== null)!;
  const [u, v] = applyTransform(art.transform, chosen.x, chosen.y);
  const [px, py] = uvToPixels(box, u, v);
  await minimap.click({ position: { x: px, y: py } });
  await setLayer(page, "SIGHT", true);
  await take("2d-sight.png");
  await setLayer(page, "SIGHT", false);

  await page.getByRole("button", { name: "3D", exact: true }).click();
  await expect(page.locator(".stage-canvas canvas")).toBeVisible();
  await page.evaluate(
    () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
  );
  await take("3d-scene.png");
  await toggleLayer(page, "CALLOUTS");
  await take("3d-callouts.png");

  for (const [name, body] of shots) {
    expect(body.byteLength, `${name} is a real picture`).toBeGreaterThan(5000);
  }

  // The scene has to have drawn *something* other than its own background.
  const solid = await readCanvas(page, page.locator(".stage-canvas canvas"));
  const distinct = new Set<number>();
  for (let i = 0; i < solid.data.length; i += 4) {
    distinct.add((solid.data[i]! << 16) | (solid.data[i + 1]! << 8) | solid.data[i + 2]!);
  }
  expect(distinct.size, "the scene is not one flat colour").toBeGreaterThan(50);

  // eslint-disable-next-line no-console
  console.log(
    `${replay.map_name} at ${tMs} ms -> ${shots.map(([name]) => name).join(", ")} in ` +
      `${testInfo.outputDir}`,
  );
});
