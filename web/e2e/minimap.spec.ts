/**
 * The 2D minimap, checked against the model that is supposed to have drawn it.
 *
 * `MapStage.test.tsx` already checks every sentence this page says; jsdom has
 * no 2D context, so it cannot check a single thing this page *draws*.  These
 * tests compute where each player should be from the same ported model the
 * canvas uses -- which `tests/golden/` has already pinned against Python -- and
 * then look at the pixels there.  That makes them a test of the draw loop and
 * the transform, which is the part nothing else covers.
 *
 * The two assertions that matter are two-sided on purpose:
 *
 *   * every player the model can place **is** drawn where it says, and
 *   * nothing else in a team colour is on the canvas at all.
 *
 * The second is the one that catches an invented marker -- a last-known
 * position drawn after `trackAt` refused, which is the failure this codebase
 * keeps saying it will not make and which looks entirely plausible on screen.
 */

import { expect, test } from "@playwright/test";

import { decodeMask, cone, forwardUv, uvRadius, type SightSettings } from "../src/model/sight";
import { positionOf, stateAt } from "../src/model/state";
import { applyTransform, placeSquare, uvToPixels } from "../src/model/transform";
import {
  firstCrowdedEvent,
  openFirstPlayable,
  palette,
  parseColour,
  pixelAt,
  readCanvas,
  rgbDistance,
  stepToEvent,
  type Pixels,
} from "./harness";

/**
 * How close a pixel has to be to a team colour to count as one.
 *
 * Both team colours are saturated and sit about 140 away from the radar's own
 * greys, so this has a wide margin.  `--team-unknown` does not -- it is a grey
 * itself and lands within about 39 of the map -- which is why the test below
 * refuses to run against a capture whose players have no team rather than
 * quietly matching the whole picture.
 */
const COLOUR_TOLERANCE = 36;

/** How far from a marker's centre its ring and facing line can reach. */
const MARKER_REACH = 26;

function clockText(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Every pixel within tolerance of one of the given colours. */
function colouredPixels(image: Pixels, colours: Array<[number, number, number]>): Array<[number, number]> {
  const found: Array<[number, number]> = [];
  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      const i = (y * image.width + x) * 4;
      const rgb: [number, number, number] = [image.data[i]!, image.data[i + 1]!, image.data[i + 2]!];
      if (colours.some((colour) => rgbDistance(rgb, colour) <= COLOUR_TOLERANCE)) {
        found.push([x, y]);
      }
    }
  }
  return found;
}

test.describe("the 2D minimap", () => {
  test("draws every player the model can place, and nothing else", async ({ page }) => {
    const { replay, art, model } = await openFirstPlayable(page);
    const canvas = page.locator("canvas.minimap");

    // Utility off: ability markers are drawn in team colours too, and this
    // test is about players. The toggle is part of the interface, not a hook.
    await page.getByRole("button", { name: "UTILITY", exact: true }).click();

    const { presses, tMs } = firstCrowdedEvent(model);
    await stepToEvent(page, presses);
    // The playhead is exact, so the readout is the arithmetic's own witness.
    await expect(page.locator(".clock-readout")).toHaveText(
      `${clockText(tMs)} / ${clockText(replay.length_ms)}`,
    );

    const image = await readCanvas(page, canvas);
    const box = placeSquare(image.width, image.height);
    const snap = stateAt(model, tMs);

    const expected = replay.players
      .map((player) => ({ player, position: positionOf(snap, player.actor_id) }))
      .filter((entry) => entry.position !== null)
      .map((entry) => {
        const [u, v] = applyTransform(art.transform, entry.position!.x, entry.position!.y);
        const [x, y] = uvToPixels(box, u, v);
        return { player: entry.player, x, y };
      });
    expect(expected.length, "the chosen instant has players to draw").toBeGreaterThanOrEqual(8);

    const colours = await palette(page);
    const teams = new Set(expected.map((marker) => marker.player.team));
    expect(
      [...teams].every((team) => team === "A" || team === "B"),
      "every player has an inferred team; an unteamed one is drawn in a grey the radar shares",
    ).toBe(true);
    const teamColours = [...teams].map((team) =>
      parseColour(team === "A" ? colours.a! : colours.b!),
    );
    const matched = colouredPixels(image, teamColours);
    expect(matched.length, "team colours are on the canvas at all").toBeGreaterThan(0);

    // Every predicted player is drawn where the model says.
    const claimed = new Set<number>();
    for (const marker of expected) {
      let near = 0;
      matched.forEach(([x, y], index) => {
        if (Math.hypot(x - marker.x, y - marker.y) <= MARKER_REACH) {
          near += 1;
          claimed.add(index);
        }
      });
      expect(
        near,
        `${marker.player.label || marker.player.team} at (${marker.x.toFixed(1)}, ${marker.y.toFixed(1)})`,
      ).toBeGreaterThan(30);
    }

    // And nothing in a team colour is anywhere else. A handful of stray pixels
    // is antialiasing; a marker is hundreds.
    const unclaimed = matched.length - claimed.size;
    expect(unclaimed, "team-coloured pixels away from any predicted player").toBeLessThan(200);
  });

  test("the sight cone points where the player is facing", async ({ page }) => {
    const { art, sight, model } = await openFirstPlayable(page);
    const canvas = page.locator("canvas.minimap");
    await page.getByRole("button", { name: "UTILITY", exact: true }).click();

    const { presses, tMs } = firstCrowdedEvent(model);
    await stepToEvent(page, presses);

    const first = await readCanvas(page, canvas);
    const box = placeSquare(first.width, first.height);
    const snap = stateAt(model, tMs);

    // Pick a living player the model can place, and select them by clicking
    // the pixel the model says they are on -- which also exercises hit-testing.
    const chosen = model.replay.players
      .map((player) => ({ player, position: snap.positions.get(player.actor_id) }))
      .find((entry) => entry.position !== undefined && snap.alive.has(entry.player.actor_id));
    expect(chosen, "somebody is alive and placeable here").toBeTruthy();
    const position = chosen!.position!;

    const [u, v] = applyTransform(art.transform, position.x, position.y);
    const [px, py] = uvToPixels(box, u, v);
    await canvas.click({ position: { x: px, y: py } });

    const settings: SightSettings = {
      max_range_uu: sight.max_range_uu,
      fov_degrees: sight.fov_degrees,
      ray_step_degrees: sight.ray_step_degrees,
      seed_cells: sight.seed_cells,
      probe_uu: sight.probe_uu,
    };
    const polygon = cone(
      decodeMask(sight.size, sight.cells),
      [u, v],
      forwardUv(art.transform, position.x, position.y, position.yaw, settings.probe_uu),
      uvRadius(art.transform, settings.max_range_uu),
      settings,
    );
    expect(polygon.length, "this player has a cone to draw").toBeGreaterThan(2);

    await page.getByRole("button", { name: "SIGHT", exact: true }).click();
    // The sentence travels with the mask, and is rendered verbatim.
    await expect(page.getByText(sight.caption, { exact: true })).toBeVisible();
    const lit = await readCanvas(page, canvas);

    // Sample halfway along each ray, then along the same rays rotated about the
    // player. A cone drawn ninety degrees out -- trigonometry done in uv space
    // instead of through the probe -- looks entirely plausible, and is exactly
    // what a rotated control catches.
    const rate = (turn: number): number => {
      let sampled = 0;
      let changed = 0;
      for (const [ru, rv] of polygon.slice(1)) {
        const [ex, ey] = uvToPixels(box, ru, rv);
        const dx = (ex - px) / 2;
        const dy = (ey - py) / 2;
        const x = px + dx * Math.cos(turn) - dy * Math.sin(turn);
        const y = py + dx * Math.sin(turn) + dy * Math.cos(turn);
        const before = pixelAt(first, x, y);
        const after = pixelAt(lit, x, y);
        if (before === null || after === null) {
          continue;
        }
        sampled += 1;
        if (rgbDistance(before, after) > 8) {
          changed += 1;
        }
      }
      return sampled === 0 ? 0 : changed / sampled;
    };

    const forward = rate(0);
    const left = rate(Math.PI / 2);
    const right = rate(-Math.PI / 2);
    const behind = rate(Math.PI);
    expect(forward, "the wash covers the cone the model computed").toBeGreaterThan(0.6);
    expect(forward, "and covers it better than a cone rotated a quarter turn").toBeGreaterThan(
      Math.max(left, right, behind) + 0.15,
    );
  });

  test("scrubbing backwards lands on exactly the same frame", async ({ page }) => {
    const { model } = await openFirstPlayable(page);
    const canvas = page.locator("canvas.minimap");
    await page.getByRole("button", { name: "UTILITY", exact: true }).click();

    const { presses } = firstCrowdedEvent(model);
    await stepToEvent(page, presses);
    const there = await readCanvas(page, canvas);
    const readout = await page.locator(".clock-readout").textContent();

    // Forward past a round boundary and back. `stateAt` accumulates nothing, so
    // the returning frame has to be the outgoing one to the pixel.
    await stepToEvent(page, 40);
    await page.getByTitle("Back to the start").click();
    await stepToEvent(page, presses);
    const back = await readCanvas(page, canvas);

    expect(await page.locator(".clock-readout").textContent()).toBe(readout);
    let differing = 0;
    for (let i = 0; i < there.data.length; i += 4) {
      if (there.data[i] !== back.data[i] || there.data[i + 1] !== back.data[i + 1]) {
        differing += 1;
      }
    }
    expect(differing, "the same instant is drawn identically from either side").toBe(0);
  });
});
