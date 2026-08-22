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
 * **The playhead is stepped, never guessed.**  `usePlayback` starts paused at
 * zero and `>>` seeks to the next entry in `Replay.event_times`, so pressing it
 * N times from the start lands on exactly `event_times[N - 1]`.  The clock
 * readout is only second-resolution and a strip click is a fraction of a pixel,
 * but this is exact -- which is what lets a test compute where every player
 * should be and then look there.
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
 * playable, which is exactly what the default filter leaves on the page.
 */
export async function openFirstPlayable(page: Page): Promise<Opened> {
  await page.goto("/");
  const card = page.locator("a.card").first();
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

  return { id, replay, positions, art, sight, model: buildModel(replay, positions) };
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
export function firstCrowdedEvent(
  model: ReplayModel,
  wanted = 8,
  after = 0,
): { presses: number; tMs: number } {
  const times = model.replay.event_times;
  const from = after * model.replay.length_ms;
  for (let i = 0; i < times.length; i += 1) {
    const tMs = times[i]!;
    if (tMs < from) {
      continue;
    }
    const snap = stateAt(model, tMs);
    const drawn = model.replay.players.filter(
      (player) => positionOf(snap, player.actor_id) !== null,
    ).length;
    if (drawn >= wanted) {
      return { presses: i + 1, tMs };
    }
  }
  throw new Error(`no event time has ${wanted} players on the map`);
}

/** Press `>>` the given number of times, landing on an exact event time. */
export async function stepToEvent(page: Page, presses: number): Promise<void> {
  const next = page.getByTitle("Next event");
  for (let i = 0; i < presses; i += 1) {
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
