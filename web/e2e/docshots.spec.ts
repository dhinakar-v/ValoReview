/**
 * The screenshots the README is made of.
 *
 * `gallery.spec.ts` renders every view for a person to look at and drops the
 * files in `e2e/results/`, which is gitignored -- they are working material for
 * whoever is looking at the interface that day.  These are the opposite: seven
 * pictures that are **committed**, under `docs/images/ui/`, because a front page
 * with no picture on it does not say what this project is.
 *
 * They are generated rather than taken by hand for the same reason the rest of
 * this directory computes instead of eyeballing.  A hand-taken screenshot is a
 * moment nobody can find again: the next one is of a different round, a
 * different map and a different ten people, so a README that is re-shot after a
 * UI change silently becomes a README about a different match.  Here the moment
 * is `firstCrowdedEvent(model, 8, 0.25)` -- the first event a quarter of the way
 * in with at least eight players placeable -- reached by pressing the transport
 * a computed number of times, so re-running this produces the same frame of the
 * same capture until the capture itself changes.
 *
 * **It is not part of `npm run test:e2e`.**  `playwright.config.ts` ignores this
 * file and `playwright.docshots.config.ts` is the only thing that runs it, via
 * `npm run docshots`.  A test run must not rewrite committed files as a side
 * effect of testing: the diff would appear in whatever branch happened to run
 * the suite, and `git status` would stop meaning anything.
 *
 * Prerequisites are the suite's own -- a populated `Demos/`, positions decoded
 * or cached, and `assets/` fetched -- plus one more that only matters here: the
 * pictures contain Riot's map and agent art, so they are a screenshot of an
 * interface rather than a copy of the asset pack, and the README says so.
 */

import path from "node:path";

import { expect, test, type Locator, type Page } from "@playwright/test";

import { positionOf, stateAt } from "../src/model/state";
import { applyTransform, placeSquare, uvToPixels } from "../src/model/transform";
import {
  firstCrowdedEvent,
  openFirstPlayable,
  openLayers,
  readCanvas,
  stepToEvent,
  setLayer,
  toggleLayer,
  waitForArt,
} from "./harness";

/**
 * Park the pointer and let two frames go by.
 *
 * The same precaution `readCanvas` takes, and for the same reason: a Playwright
 * screenshot clips the page rather than isolating an element, so a marker left
 * hovered draws at three times the size and names itself.  In a picture that is
 * about to sit on the front page that is not a measurement error, it is a
 * screenshot of the interface doing something nobody asked it to.
 */
async function park(page: Page): Promise<void> {
  await page.mouse.move(2, 2);
  await page.evaluate(
    () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
  );
}

test("the README's screenshots, regenerated", async ({ page }, testInfo) => {
  // `web/e2e` -> the repository root.  Not `__dirname`: this package is ESM and
  // what Playwright's loader defines is its own business, where the project's
  // own test directory is a documented value.
  const outDir = path.resolve(testInfo.project.testDir, "..", "..", "docs", "images", "ui");
  const written: Array<[string, number]> = [];

  const shot = async (
    name: string,
    target: Locator | Page,
    clip?: { x: number; y: number; width: number; height: number },
  ) => {
    await park(page);
    const body = await target.screenshot({ path: path.join(outDir, name), clip });
    written.push([name, body.byteLength]);
  };

  // 1. The library, before anything is opened.  `openFirstPlayable` navigates
  // here too, but it clicks straight through, and the match list is a page in
  // its own right.
  //
  await page.goto("/");
  await expect(page.locator("a.card").first()).toBeVisible();
  await waitForArt(page);
  /*
    Wait for the reveal to have finished, and ask about opacity rather than
    about the attribute that drives it.

    `MatchList.useReveal` marks each row `data-enter="pending"`, an
    `IntersectionObserver` flips it to `"in"`, and the row transitions in --
    but each one also carries `--enter-delay: min(index, 8) * 45ms`, and
    `prefers-reduced-motion` zeroes the *durations* in `app.css`, not that
    delay.  So `pending` can be gone from the whole page while the last row is
    still three hundred milliseconds from starting to appear, which is exactly
    what the first two attempts at this shot photographed.  Opacity is the
    thing the picture is about, so opacity is what is waited on.

    Do not try to shrink the viewport around the list instead: a card below the
    fold never enters view, so the observer never fires and it stays at opacity
    zero indefinitely.  The window stays as the suite sizes it and the
    screenshot is clipped to the list instead.
  */
  await page.waitForFunction(() => {
    const rows = Array.from(document.querySelectorAll("[data-enter]"));
    return (
      rows.length > 0 &&
      rows.every((row) => Number(getComputedStyle(row).opacity) > 0.99)
    );
  });
  // Clipped to the pager, which is the last thing on the page: a short library
  // leaves the rest of a 1000px window as empty ground, which in a README reads
  // as an empty library rather than as a tall screen.  Measured rather than
  // guessed, so a longer or shorter page of cards still frames correctly.
  const pager = await page.getByRole("button", { name: "Next page" }).boundingBox();
  await shot("01-match-list.png", page, {
    x: 0,
    y: 0,
    width: 1500,
    height: Math.ceil((pager?.y ?? 960) + (pager?.height ?? 32) + 24),
  });

  const { replay, art, model } = await openFirstPlayable(page);
  const moment = firstCrowdedEvent(model, 8, 0.25);
  await stepToEvent(page, moment);

  // 2 and 3. The whole viewer, then the radar on its own.  The crop is of
  // `canvas.minimap` and not of `.panel.stage`, which was the first attempt and
  // came out as the same picture as 02 less forty pixels of chrome: what is
  // worth a second image is the drawing itself, square and with nothing around
  // it -- ten markers, the utility on the ground and the spike, at real map
  // coordinates.
  const stage = page.locator(".panel.stage");
  await shot("02-viewer-2d.png", page);
  await shot("03-radar.png", page.locator("canvas.minimap"));

  // 4. The layers popover, open.  Nine switches, and the rows that cannot be
  // used in this view carrying the reason rather than being missing.
  await openLayers(page);
  await shot("04-layers.png", page);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "LAYERS", exact: true })).toHaveAttribute(
    "aria-expanded",
    "false",
  );

  // 5. Sight and trails. The cone is drawn for every living player, so this
  // no longer needs a selection -- the click stays because the picked wedge is
  // the heavier one and the picture should show that.
  // Where the click goes is computed the way `gallery.spec.ts` computes it --
  // through the model's own transform, so it lands on a player rather than near
  // one.
  const minimap = page.locator("canvas.minimap");
  const image = await readCanvas(page, minimap);
  const box = placeSquare(image.width, image.height);
  const snap = stateAt(model, moment.tMs);
  const chosen = model.replay.players
    .map((player) => positionOf(snap, player.actor_id))
    .find((position) => position !== null)!;
  const [u, v] = applyTransform(art.transform, chosen.x, chosen.y);
  const [px, py] = uvToPixels(box, u, v);
  await minimap.click({ position: { x: px, y: py } });
  await toggleLayer(page, "TRAILS");
  await setLayer(page, "SIGHT", true);
  await shot("05-sight-trails.png", stage);
  await setLayer(page, "SIGHT", false);
  await toggleLayer(page, "TRAILS");

  // 6. The scene, with Riot's callouts on it.
  await page.getByRole("button", { name: "3D", exact: true }).click();
  await expect(page.locator(".stage-canvas canvas")).toBeVisible();
  await page.evaluate(
    () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
  );
  await toggleLayer(page, "CALLOUTS");
  await shot("06-scene-3d.png", stage);
  await toggleLayer(page, "CALLOUTS");

  // 7. The round timeline, which is a dialog over the page rather than a view,
  // so it is photographed with the page behind it.
  await page.getByRole("button", { name: "2D", exact: true }).click();
  await expect(minimap).toBeVisible();
  await page.getByTitle("Round timeline").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await shot("07-round-timeline.png", page);
  await page.keyboard.press("Escape");

  // The only assertion, and it is the same one `gallery.spec.ts` makes: this is
  // a generator, not a check.  A file that came out empty is worth failing on;
  // whether the picture is a good one is a judgement no threshold makes.
  for (const [name, bytes] of written) {
    expect(bytes, `${name} is a real picture`).toBeGreaterThan(5000);
  }

  // eslint-disable-next-line no-console
  console.log(
    `${replay.map_name} at ${moment.tMs} ms -> ${written.length} files in ${outDir}`,
  );
});
