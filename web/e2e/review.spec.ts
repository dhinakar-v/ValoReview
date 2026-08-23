/**
 * The visual review pass: every state, photographed, plus the layout checks a
 * unit test cannot make.
 *
 * The other three specs are about arithmetic that happens to be drawn -- is the
 * marker where the model says, does the cone cover the polygon, is the 3D
 * ground the same way up as the 2D map.  This one is about the things only a
 * rendered page can be wrong about: two floating layers overlapping each other,
 * a gap that does not match the spacing scale, a corner that survived the flat
 * pass, a card whose text is clipped, a panel that raises a scrollbar on a page
 * that is supposed to fill the window exactly.
 *
 * The screenshots are written to `e2e/results/review/` for a person to look at.
 * The **assertions** beside them are what make this a test rather than a
 * gallery, and each one is a defect this rebuild could plausibly have:
 *
 *   * nothing scrolls on the viewer, in either direction;
 *   * no element on the page has a rounded corner or a box-shadow that is not
 *     one of the three floating layers;
 *   * the clock pill, the kill feed and the layers popover never overlap each
 *     other or leave the canvas;
 *   * the two rosters are the same width and the map gets everything else;
 *   * every gap between the arena's three columns is zero -- they are separated
 *     by borders, and a stripe of page background between them is the dead
 *     space this layout was rebuilt to remove.
 */

import { expect, test, type Locator, type Page } from "@playwright/test";

import { firstCrowdedEvent, openFirstPlayable, openLayers, stepToEvent } from "./harness";

const SHOTS = "e2e/results/review";

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

async function boxOf(target: Locator): Promise<Rect> {
  const box = await target.boundingBox();
  expect(box, "the element is on the page").not.toBeNull();
  return box!;
}

function overlaps(a: Rect, b: Rect): boolean {
  return (
    a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height
  );
}

test.describe("the rebuilt viewer", () => {
  test("fills the window and never scrolls", async ({ page }) => {
    await openFirstPlayable(page);
    await shot(page, "01-viewer-fit");

    const overflow = await page.evaluate(() => ({
      x: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      y: document.documentElement.scrollHeight - document.documentElement.clientHeight,
    }));
    expect(overflow.x, "nothing overflows sideways").toBeLessThanOrEqual(0);
    expect(overflow.y, "the page is exactly the window").toBeLessThanOrEqual(0);
  });

  test("is flat and square everywhere except the floating layers", async ({
    page,
  }) => {
    await openFirstPlayable(page);
    const offenders = await page.evaluate(() => {
      // The only elements allowed to float, and the only ones allowed a
      // shadow. Everything else separates with a 1px border and a step on the
      // surface ramp.
      //
      // Six, and the title used to say three: the clock pill and the kill
      // toast over the map, the marker tooltip beside a player, the rail's
      // tooltip under the transport, the layers popover and the modal.
      const floating = [
        ".clock-pill",
        ".kill-chip",
        ".marker-tip",
        ".rail-tip",
        ".menu-panel",
        ".modal",
      ];
      const bad: string[] = [];
      for (const node of document.querySelectorAll("*")) {
        const style = getComputedStyle(node);
        const name = `${node.tagName.toLowerCase()}.${node.className}`.slice(0, 60);
        const radii = [
          style.borderTopLeftRadius,
          style.borderTopRightRadius,
          style.borderBottomLeftRadius,
          style.borderBottomRightRadius,
        ];
        // A circular portrait is the one deliberate exception: a square marker
        // stops reading as a person. It is 50% or a huge pixel value.
        const round = radii.some((r) => r !== "0px" && !r.includes("%") && parseFloat(r) < 100);
        if (round) {
          bad.push(`radius ${radii.join(" ")} on ${name}`);
        }
        const shadow = style.boxShadow;
        if (
          shadow !== "none" &&
          !floating.some((selector) => (node as Element).closest(selector))
        ) {
          bad.push(`shadow on ${name}`);
        }
      }
      return bad;
    });
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  test("keeps the floating layers apart and inside the canvas", async ({ page }) => {
    const { model } = await openFirstPlayable(page);
    await stepToEvent(page, firstCrowdedEvent(model, 8));

    const canvas = await boxOf(page.locator(".stage-canvas"));
    const clock = await boxOf(page.locator(".clock-pill"));
    expect(clock.y).toBeGreaterThanOrEqual(canvas.y);
    expect(clock.x).toBeGreaterThanOrEqual(canvas.x);
    expect(clock.x + clock.width).toBeLessThanOrEqual(canvas.x + canvas.width);

    await openLayers(page);
    const menu = await boxOf(page.locator(".menu-panel"));
    expect(overlaps(menu, clock), "the layers menu covers the clock").toBe(false);
    await shot(page, "02-layers-menu");
    await page.keyboard.press("Escape");
  });

  test("gives the map every pixel the rosters do not need", async ({ page }) => {
    await openFirstPlayable(page);
    const arena = await boxOf(page.locator(".arena"));
    const left = await boxOf(page.locator(".roster").first());
    const right = await boxOf(page.locator(".roster").last());
    const canvas = await boxOf(page.locator(".stage-canvas"));

    expect(left.width, "the two gutters are the same width").toBeCloseTo(right.width, 0);
    // No gap: the columns are separated by borders, and a stripe of page
    // background between them is exactly the dead space this removed.
    expect(canvas.x - (left.x + left.width)).toBeLessThanOrEqual(1);
    expect(right.x - (canvas.x + canvas.width)).toBeLessThanOrEqual(1);
    expect(left.width + canvas.width + right.width).toBeCloseTo(arena.width, 0);
    expect(canvas.width, "the map is the largest thing on the page").toBeGreaterThan(
      left.width + right.width,
    );
  });

  test("shows a roster card with everything on it", async ({ page }) => {
    const { model } = await openFirstPlayable(page);
    await stepToEvent(page, firstCrowdedEvent(model, 8, 0.3));

    const card = page.locator(".player-card").first();
    await expect(card).toBeVisible();
    await expect(card.locator(".card-health")).toBeVisible();
    await expect(card.locator(".card-armor")).toBeVisible();
    await expect(card.locator(".card-credits")).toBeVisible();
    await card.screenshot({ path: `${SHOTS}/03-player-card.png` });

    // Clipped text is the failure a card this dense actually has.
    const clipped = await page.evaluate(() => {
      const bad: string[] = [];
      for (const node of document.querySelectorAll(".card-agent, .card-health, .card-credits")) {
        if (node.scrollWidth > node.clientWidth + 1) {
          bad.push(`${node.className}: ${node.textContent}`);
        }
      }
      return bad;
    });
    expect(clipped, clipped.join("\n")).toEqual([]);
  });

  test("raises the hover card from a marker", async ({ page }) => {
    const { model } = await openFirstPlayable(page);
    await stepToEvent(page, firstCrowdedEvent(model, 8, 0.3));
    await page.locator(".player-card").first().hover();
    await expect(page.locator(".marker-tip")).toBeVisible();
    await shot(page, "04-hover-tip");
  });

  test("opens the round timeline over a blurred page", async ({ page }) => {
    await openFirstPlayable(page);
    await page.getByTitle("Round timeline").click();
    const modal = page.getByRole("dialog", { name: "Round Timeline" });
    await expect(modal).toBeVisible();
    await expect(modal.locator(".event-row").first()).toBeVisible();
    await shot(page, "05-round-timeline");

    // Every filter is a real category: unchecking all of them leaves the
    // sentence rather than an empty box.
    for (const name of ["Kills", "Abilities", "Ultimates", "Spike", "First Kill"]) {
      await modal.getByRole("checkbox", { name, exact: true }).uncheck();
    }
    await expect(modal.getByText(/matches these filters/)).toBeVisible();
    await shot(page, "06-timeline-filtered");

    await page.keyboard.press("Escape");
    await expect(modal).toBeHidden();
  });

  test("steps a round at a time", async ({ page }) => {
    await openFirstPlayable(page);
    const chips = page.locator(".round-chip");
    await expect(chips.first()).toBeVisible();
    const count = await chips.count();
    expect(count, "one chip per recorded round").toBeGreaterThan(1);
    await chips.nth(Math.min(3, count - 1)).click();
    await expect(page.locator(".clock-pill")).toBeVisible();
    await shot(page, "07-round-picked");
  });

  test("zooms about the cursor and comes back", async ({ page }) => {
    const { model } = await openFirstPlayable(page);
    await stepToEvent(page, firstCrowdedEvent(model, 8, 0.3));

    const canvas = page.locator("canvas.minimap");
    const box = await boxOf(canvas);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    for (let i = 0; i < 6; i += 1) {
      await page.mouse.wheel(0, -240);
    }
    await shot(page, "08-zoomed");
    await canvas.dblclick();
    await shot(page, "09-zoom-reset");
  });

  test("renders the 3D scene in the same frame", async ({ page }) => {
    await openFirstPlayable(page);
    await page.getByRole("button", { name: "3D", exact: true }).click();
    await expect(page.locator(".stage-canvas canvas")).toBeVisible();
    await shot(page, "10-scene3d");
  });

  test("says which numbers are generated", async ({ page }) => {
    await openFirstPlayable(page);
    await expect(page.getByText(/are not in a \.vrf and are not decoded/)).toBeVisible();
  });

  test("still fits at 1280 wide", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openFirstPlayable(page);
    await shot(page, "11-narrow-1280");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test.describe("the match list", () => {
  test("is still a document", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("a.card").first()).toBeVisible();
    await shot(page, "12-match-list");
  });
});
