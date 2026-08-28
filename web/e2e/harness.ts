/**
 * What the browser tests share: getting to a replay, and reading pixels back.
 *
 * These tests exist to check drawings, so almost everything here is about
 * turning a rendered canvas into numbers.  Two facts shape how that is done.
 *
 * **The page decodes its own screenshots.**  A WebGL canvas cannot be read with
 * `getImageData`, and `toDataURL` on one is blank unless the drawing buffer is
 * preserved -- which is a production setting that would exist only for tests.
 * So a canvas is captured with Playwright's element screenshot and handed back
 * into the page as a data URL, where a 2D context decodes it.  The browser is
 * the PNG decoder, no dependency is added, and the 2D and 3D views are read the
 * same way, which is what makes comparing them meaningful.
 *
 * **The playhead is stepped, never guessed.**  `>>` seeks to the next entry in
 * `Replay.event_times`, so a press lands on an exact millisecond rather than
 * near one.  The clock readout is only second-resolution and a rail click is a
 * fraction of a pixel, but this is exact -- which is what lets a test compute
 * where every player should be and then look there.
 *
 * **Stepping is scoped to a round**, because the transport is: a chip picks a
 * round, the rail spans it, and `>>` walks that round's events and stops at its
 * end.  So a target is reached in two moves rather than one -- click the chip,
 * then press N times -- and `firstCrowdedEvent` returns both numbers.  Pressing
 * `>>` from the top of the capture would stop at the first round boundary and
 * every assertion after it would be about the wrong instant.
 */

import { expect, type Locator, type Page } from "@playwright/test";

import type { MapArt, Replay, SightMaskDoc } from "../src/api/types";
import { buildModel, type PositionsDoc, type ReplayModel } from "../src/model/replay";
import { stateAt } from "../src/model/state";
import { positionOf } from "../src/model/state";

export const API_URL = "http://127.0.0.1:8000";

/** One decoded image, in CSS pixels, RGBA row-major. */
export interface Pixels {
  width: number;
  height: number;
  data: number[];
}

export interface Opened {
  id: string;
  replay: Replay;
  positions: PositionsDoc;
  art: MapArt;
  sight: SightMaskDoc;
  model: ReplayModel;
}

async function api<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) {
    throw new Error(`GET ${path} -> ${response.status}`);
  }
  return (await response.json()) as T;
}

/**
 * Open the first capture the library offers, and fetch what it is made of.
 *
 * Deliberately the *first card* rather than a hard-coded id: an id is a digest
 * of a resolved path, so naming one would tie the suite to one machine's
 * `Demos/`.  What the suite needs is a capture the server itself considers
 * playable, and `a.card.playable` is the scanner's own word for that.
 *
 * It used to be `a.card`, which worked only because `/api/library` filtered to
 * playable and every row on the page was one.  The list shows unsupported
 * builds now, so the first row by date can be a capture with no positions --
 * and this helper would then have opened it and left every layer spec
 * asserting against a document that draws nothing.
 */
export async function openFirstPlayable(page: Page): Promise<Opened> {
  await page.goto("/");
  const card = page.locator("a.card.playable").first();
  await expect(card).toBeVisible();
  await card.click();
  await page.waitForURL(/\/replay\/[0-9a-f]+/);

  const id = page.url().split("/replay/")[1]!;
  const replay = await api<Replay>(`/api/replays/${id}`);
  expect(replay.has_positions, "the first playable capture has decoded positions").toBe(
    true,
  );
  const positions = await api<PositionsDoc>(`/api/replays/${id}/positions`);
  const art = await api<MapArt>(`/api/maps/${encodeURIComponent(replay.map_key)}`);
  const sight = await api<SightMaskDoc>(
    `/api/maps/${encodeURIComponent(replay.map_key)}/sight`,
  );

  // The stage only exists once the art and the tracks have both landed.
  await expect(page.locator("canvas.minimap")).toBeVisible();

  await waitForArt(page);

  return { id, replay, positions, art, sight, model: buildModel(replay, positions) };
}

/**
 * Wait until every picture on the page has actually arrived.
 *
 * The canvas draws an agent portrait where one has loaded and a plain dot
 * where it has not, so a frame read before the icons arrive is a legitimately
 * different drawing of the same instant -- which is indistinguishable from the
 * non-determinism `scrubbing backwards` exists to catch.
 *
 * `networkidle` was the instrument here and it **lied**, measurably: at the
 * first read 37 of the page's 59 images were still incomplete and the last one
 * landed fifteen seconds later, so the first frame drew ten dots and the second
 * ten portraits -- a stable 5,017-pixel difference between two reads of the same
 * millisecond, and one that only appeared when another spec had run first.
 * Idle means five hundred quiet milliseconds, and this page asks for ten
 * portraits and forty ability icons at about 450KB each: the requests queue six
 * at a time behind the browser's own connection limit, so there are quiet
 * moments all the way through the load.
 *
 * The question is "has every picture arrived", so that is what is asked --
 * of the DOM, which holds the same portrait URLs the canvas asks for, so the
 * canvas's own copies are served from the memory cache by the time this returns.
 * It is asked twice with a frame between, because `document.images` grows as
 * cards mount and "all complete" is momentarily true of a shorter list.
 */
export async function waitForArt(page: Page): Promise<void> {
  const allComplete = () => {
    const images = Array.from(document.images);
    return images.length > 0 && images.every((image) => image.complete);
  };
  for (let round = 0; round < 2; round += 1) {
    await page.waitForFunction(allComplete, undefined, { timeout: 60_000 });
    await page.evaluate(
      () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
    );
  }
}

/**
 * The first event time at which at least `wanted` players can be drawn.
 *
 * Round one starts some way into a capture and a track does not begin at zero,
 * so t=0 is a legitimate frame with nothing on it.  This finds a moment the
 * assertions can actually say something about, and returns how many times `>>`
 * has to be pressed to reach it.
 *
 * `after` skips that fraction of the match first, which is how the gallery
 * reaches a round with utility on the map rather than ten people standing in
 * two spawn rooms.
 */
export interface Moment {
  /** The round to pick first, 1-based as `infer` numbers them. */
  roundNo: number;
  /** How many times `>>` reaches the moment from where picking the round lands. */
  presses: number;
  tMs: number;
}

/**
 * An event time, as the two presses that reach it.
 *
 * Which round it falls in, and how far into that round's own event list -- the
 * list `>>` walks once a chip has been pressed. An event sitting exactly where
 * the chip lands needs no presses at all, because picking it already seeks
 * there.
 *
 * That landing place is `action_start_ms`, the barrier drop, and not `start_ms`:
 * a chip seeks past the buy phase, so the buy phase's own start is behind the
 * playhead and `>>` never offers it.  The two have to agree -- this filter and
 * where `Transport.pick` seeks -- or every count here is one out.
 */
export function momentAt(model: ReplayModel, tMs: number): Moment {
  const replay = model.replay;
  const round = roundHolding(model, tMs);
  if (tMs < round.action_start_ms) {
    /*
      Inside the buy phase, and therefore behind the playhead the moment a chip
      is pressed.  `>>` only walks forward, so no number of presses reaches it.

      This is reachable by hand -- the rail spans the whole round and scrubbing
      back into the buy phase works -- so it is a limit of this helper and not
      of the interface.  It throws rather than returning a count that would land
      somewhere else, because a spec that then photographed the wrong instant
      would fail with a pixel count nobody could trace back to here.
    */
    throw new Error(
      `${tMs}ms is inside round ${round.number}'s buy phase (barrier drops at ` +
        `${round.action_start_ms}ms); pressing forward cannot reach it`,
    );
  }
  const inside = replay.event_times.filter(
    (t) => t > round.action_start_ms && t < round.end_ms,
  );
  const at = inside.indexOf(tMs);
  return { roundNo: round.number, presses: at < 0 ? 0 : at + 1, tMs };
}

/** The round an instant falls in, or the first where it falls before them all. */
function roundHolding(model: ReplayModel, tMs: number) {
  const round =
    model.replay.rounds.find((entry) => tMs >= entry.start_ms && tMs < entry.end_ms) ??
    model.replay.rounds[0];
  if (round === undefined) {
    throw new Error("the capture records no rounds");
  }
  return round;
}

export function firstCrowdedEvent(model: ReplayModel, wanted = 8, after = 0): Moment {
  const replay = model.replay;
  const from = after * replay.length_ms;
  for (const tMs of replay.event_times) {
    if (tMs < from) {
      continue;
    }
    // Skipped rather than counted: a crowded instant inside a buy phase is a
    // real one -- everybody is alive and nobody has moved -- and simply not one
    // the transport lands on, so pick the next.
    if (tMs < roundHolding(model, tMs).action_start_ms) {
      continue;
    }
    const snap = stateAt(model, tMs);
    const drawn = replay.players.filter(
      (player) => positionOf(snap, player.actor_id) !== null,
    ).length;
    if (drawn >= wanted) {
      return momentAt(model, tMs);
    }
  }
  throw new Error(`no event time has ${wanted} players on the map`);
}

/** Pick a round by its chip, which seeks to that round's barrier drop. */
export async function pickRound(page: Page, roundNo: number): Promise<void> {
  await page.locator(".round-chip").nth(roundNo - 1).click();
}

/**
 * Open the layers menu, which the layer switches now live inside.
 *
 * They used to be four buttons on the stage head; there are nine of them and a
 * head cannot carry nine beside a map name without the map getting smaller.
 * The labels are unchanged and still exact -- UTILITY, TRAILS, SIGHT, CALLOUTS
 * -- so this is one press before the press, not a rewrite of what a spec looks
 * for.  `MapStage.test.tsx` has the same helper.
 */
export async function openLayers(page: Page): Promise<void> {
  const button = page.getByRole("button", { name: "LAYERS", exact: true });
  if ((await button.getAttribute("aria-expanded")) !== "true") {
    await button.click();
  }
}

/**
 * Switch one layer, and put the menu away again.
 *
 * Closing matters: the popover floats over the top-right of the map, and a
 * spec that left it open would screenshot a panel across the canvas it is
 * about to count pixels in.
 */
export async function toggleLayer(page: Page, name: string): Promise<void> {
  await openLayers(page);
  // The row, not the input: the input is clipped to a pixel so a reader still
  // announces it, and clicking it directly lands on the drawn box instead.
  // A person clicks the label, and so does this.
  const row = page
    .locator(".check-row")
    .filter({ has: page.getByText(name, { exact: true }) });
  /*
    Assert the switch was enabled and actually flipped.

    A row that cannot be used is now shown disabled with a reason rather than
    dropped from the menu, and this helper used to be blind to that in the
    worst possible way: Playwright's actionability checks all pass on the
    `<label>`, the browser then declines to activate a disabled control, and
    the only thing asserted afterwards was that the menu closed -- which it
    did.  Every layer spec would have gone on passing while toggling nothing.
  */
  const box = row.getByRole("checkbox");
  await expect(box, `${name} is offered as a working switch here`).toBeEnabled();
  const before = await box.isChecked();
  await row.click();
  await expect(box, `${name} flipped`).toBeChecked({ checked: !before });
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "LAYERS", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
}

/**
 * Put one layer into a known state, whether or not it is already there.
 *
 * `toggleLayer` is a *flip*, and every spec that called it meant "turn this
 * on".  That was fine while every layer this suite touches started off, and it
 * failed silently the moment one did not: the helper asserts only that the box
 * changed, so `toggleLayer(page, "SIGHT")` on an on-by-default layer switches
 * it **off**, the spec goes green, and the screenshot it was taking has no
 * cone in it.  Three specs were in that state.
 *
 * So a spec that wants a layer on says so, and one that wants it off -- to
 * count marker pixels without a cone wash over them -- says that.
 */
export async function setLayer(page: Page, name: string, on: boolean): Promise<void> {
  await openLayers(page);
  const row = page
    .locator(".check-row")
    .filter({ has: page.getByText(name, { exact: true }) });
  const box = row.getByRole("checkbox");
  await expect(box, `${name} is offered as a working switch here`).toBeEnabled();
  if ((await box.isChecked()) !== on) {
    await row.click();
  }
  await expect(box, `${name} is ${on ? "on" : "off"}`).toBeChecked({ checked: on });
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "LAYERS", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
}

/**
 * Reach a moment: pick its round, then press `>>` into it.
 *
 * Both halves are the interface a person uses, which is the rule the rest of
 * this suite follows -- a test that seeked by writing to the store would pass
 * against a transport that no longer works.
 */
export async function stepToEvent(page: Page, moment: Moment): Promise<void> {
  await pickRound(page, moment.roundNo);
  const next = page.getByTitle("Next event");
  for (let i = 0; i < moment.presses; i += 1) {
    await next.click();
  }
}

/**
 * A canvas as pixels, via a screenshot the page itself decodes.
 *
 * See the module docstring for why it goes the long way round.  The screenshot
 * is taken at the default device scale factor of one, so the returned image is
 * in CSS pixels and lines up with everything `placeSquare` computes.
 */
export async function readCanvas(page: Page, target: Locator): Promise<Pixels> {
  /*
    Park the pointer first.

    A Playwright element screenshot clips the *page* to the element's box; it
    does not isolate the element, so anything painted over the canvas is in the
    read. Hovering a player -- on the map or on their roster card -- draws that
    marker at three times the size and names it, which is about five thousand
    pixels of legitimate difference between two reads of the same instant. The
    pointer ends up over a roster card by accident often enough to matter: it is
    where it was left when the layers menu closed.

    The top-left corner is the back button, which changes nothing that is drawn.
  */
  await page.mouse.move(2, 2);
  await page.evaluate(
    () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
  );
  const shot = (await target.screenshot()).toString("base64");
  return page.evaluate(async (base64) => {
    const image = new Image();
    image.src = `data:image/png;base64,${base64}`;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
    return { width: canvas.width, height: canvas.height, data: Array.from(data) };
  }, shot);
}

/** The colour at a point, or null where the point is off the image. */
export function pixelAt(image: Pixels, x: number, y: number): [number, number, number] | null {
  const px = Math.round(x);
  const py = Math.round(y);
  if (px < 0 || py < 0 || px >= image.width || py >= image.height) {
    return null;
  }
  const i = (py * image.width + px) * 4;
  return [image.data[i]!, image.data[i + 1]!, image.data[i + 2]!];
}

/** Perceptual-enough luminance, which is all a correlation needs. */
export function luma(rgb: [number, number, number]): number {
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}

export function rgbDistance(a: [number, number, number], b: [number, number, number]): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/** `#rrggbb` (or a `rgb()` string) as three numbers. */
export function parseColour(value: string): [number, number, number] {
  const hex = value.trim();
  if (hex.startsWith("#")) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const parts = hex.match(/\d+/g);
  if (parts === null || parts.length < 3) {
    throw new Error(`not a colour: ${value}`);
  }
  return [Number(parts[0]), Number(parts[1]), Number(parts[2])];
}

/** The theme's own palette, read from the page rather than repeated here. */
export async function palette(page: Page): Promise<Record<string, string>> {
  return page.evaluate(() => {
    const style = getComputedStyle(document.body);
    const read = (name: string) => style.getPropertyValue(name).trim();
    return {
      a: read("--team-a"),
      b: read("--team-b"),
      unknown: read("--team-unknown"),
      background: read("--app-bg"),
      // The spike, which is deliberately neither team's: it was `#ff5252`,
      // twelve RGB from the attacker red, so a pixel of it counted as a
      // player marker in the very assertions this palette feeds.
      spikeArmed: read("--spike-armed"),
    };
  });
}

/** Pearson's r, which is blind to the brightness and contrast differences
 *  between a flat 2D drawing and a lit 3D one, and sensitive to the shape. */
export function pearson(xs: number[], ys: number[]): number {
  const n = xs.length;
  if (n === 0 || n !== ys.length) {
    throw new Error("pearson needs two equal, non-empty series");
  }
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let dx = 0;
  let dy = 0;
  for (let i = 0; i < n; i += 1) {
    const a = xs[i]! - mx;
    const b = ys[i]! - my;
    num += a * b;
    dx += a * a;
    dy += b * b;
  }
  return dx === 0 || dy === 0 ? 0 : num / Math.sqrt(dx * dy);
}
