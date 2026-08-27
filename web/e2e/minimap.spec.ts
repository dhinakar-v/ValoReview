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

import type { Transform } from "../src/api/types";
import type { ReplayModel } from "../src/model/replay";
import {
  decodeMask,
  cone,
  forwardUv,
  uvRadius,
  type SightSettings,
} from "../src/model/sight";
import { positionOf, spikeLocation, stateAt } from "../src/model/state";
import {
  applyTransform,
  placeSquare,
  uvToPixels,
  type Box,
} from "../src/model/transform";
import { smokesAt } from "../src/views/sightlayer";
import { tracersAt, type Tracer } from "../src/views/tracers";
import {
  firstCrowdedEvent,
  momentAt,
  openFirstPlayable,
  palette,
  parseColour,
  pixelAt,
  readCanvas,
  rgbDistance,
  stepToEvent,
  setLayer,
  toggleLayer,
  type Moment,
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
function colouredPixels(
  image: Pixels,
  colours: Array<[number, number, number]>,
): Array<[number, number]> {
  const found: Array<[number, number]> = [];
  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      const i = (y * image.width + x) * 4;
      const rgb: [number, number, number] = [
        image.data[i]!,
        image.data[i + 1]!,
        image.data[i + 2]!,
      ];
      if (
        colours.some((colour) => rgbDistance(rgb, colour) <= COLOUR_TOLERANCE)
      ) {
        found.push([x, y]);
      }
    }
  }
  return found;
}

/**
 * The biggest 8-connected run of pixels in a scattered set.
 *
 * Deliberately not a count of the whole set: see the call site.  Eight-connected
 * rather than four, because a triangle's antialiased edge steps diagonally and a
 * four-connected walk would report one marker as several.
 */
function largestPatch(pixels: Array<[number, number]>): number {
  const left = new Set(pixels.map(([x, y]) => `${x},${y}`));
  let biggest = 0;
  for (const start of [...left]) {
    if (!left.has(start)) {
      continue;
    }
    let size = 0;
    const queue = [start];
    left.delete(start);
    while (queue.length > 0) {
      const [x, y] = queue.pop()!.split(",").map(Number) as [number, number];
      size += 1;
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          const key = `${x + dx},${y + dy}`;
          if (left.delete(key)) {
            queue.push(key);
          }
        }
      }
    }
    biggest = Math.max(biggest, size);
  }
  return biggest;
}

/**
 * How far a player's centre has to be for the spike to be visible under it.
 *
 * A marker is `AVATAR_PX / 2` of portrait plus a 2px ring, and its facing arrow
 * reaches `FACING_LENGTH` beyond that -- 24 px in all at fit zoom -- and the
 * spike triangle is 8 px tall.  So a player centred closer than 32 px has drawn
 * pixels somewhere on the triangle, and the players draw after it.  34 is that
 * sum with a little room, and it is deliberately not read from
 * `MinimapCanvas` -- a test that imported the drawing's own constants would
 * agree with the drawing however wrong the drawing was.
 */
const SPIKE_CLEARANCE = 34;

/**
 * A moment at which the spike is down and nobody is standing on it.
 *
 * The plant instant is never one: the planter is on the coordinate by
 * definition, and this canvas draws players over the spike on purpose.  So walk
 * the event times the transport can actually step to, and take the first at
 * which `spikeLocation` -- the same function `drawSpike` asks -- returns a
 * coordinate that every placeable player is clear of.
 */
function uncoveredPlant(
  model: ReplayModel,
  transform: Transform,
  box: Box,
): { at: { x: number; y: number }; moment: Moment } | null {
  for (const tMs of model.replay.event_times) {
    const snap = stateAt(model, tMs);
    const at = spikeLocation(model, snap);
    if (at === null) {
      continue;
    }
    const moment = momentAt(model, tMs);
    // `presses` is zero for a time the round chip already seeks to, and for one
    // `momentAt` could not place in its round's own event list at all. Either
    // way there is nothing to step, so it is not a moment this test can reach.
    if (moment.presses === 0) {
      continue;
    }
    const [su, sv] = applyTransform(transform, at.x, at.y);
    const [sx, sy] = uvToPixels(box, su, sv);
    const covered = model.replay.players.some((player) => {
      const position = positionOf(snap, player.actor_id);
      if (position === null) {
        return false;
      }
      const [pu, pv] = applyTransform(transform, position.x, position.y);
      const [px, py] = uvToPixels(box, pu, pv);
      return Math.hypot(px - sx, py - sy) < SPIKE_CLEARANCE;
    });
    if (!covered) {
      return { at, moment };
    }
  }
  return null;
}

/** World to canvas, the same two steps every drawing here goes through. */
function screenPoint(
  transform: Transform,
  box: Box,
  x: number,
  y: number,
): [number, number] {
  const [u, v] = applyTransform(transform, x, y);
  return uvToPixels(box, u, v);
}

/** How far a pixel is from a line segment, which is what "on the line" means. */
function distanceToSegment(
  x: number,
  y: number,
  ax: number,
  ay: number,
  bx: number,
  by: number,
): number {
  const dx = bx - ax;
  const dy = by - ay;
  const span = dx * dx + dy * dy;
  const t =
    span === 0
      ? 0
      : Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / span));
  return Math.hypot(x - (ax + t * dx), y - (ay + t * dy));
}

/**
 * The first kill this capture draws exactly one tracer for, long enough to see.
 *
 * **One**, because the test measures the difference between two reads and a
 * second line in the frame would be counted as a stray off the first one's
 * path.  **Long**, because both ends of a tracer are underneath a player
 * marker -- the killer's and the victim's -- and a shot taken from three feet
 * away is entirely covered by the two portraits, which is the drawing behaving
 * as designed rather than something to loosen an assertion for.
 */
function firstLoneTracer(
  model: ReplayModel,
  transform: Transform,
  box: Box,
): { moment: Moment; tracer: Tracer } | null {
  for (const kill of model.replay.kills) {
    if (!model.replay.event_times.includes(kill.t_ms)) {
      continue;
    }
    const drawn = tracersAt(model, stateAt(model, kill.t_ms));
    if (drawn.length !== 1) {
      continue;
    }
    const tracer = drawn[0]!;
    const [ax, ay] = screenPoint(transform, box, tracer.from.x, tracer.from.y);
    const [bx, by] = screenPoint(transform, box, tracer.to.x, tracer.to.y);
    if (Math.hypot(bx - ax, by - ay) < 3 * MARKER_REACH) {
      continue;
    }
    return { moment: momentAt(model, kill.t_ms), tracer };
  }
  return null;
}

test.describe("the 2D minimap", () => {
  test("draws every player the model can place, and nothing else", async ({
    page,
  }) => {
    const { replay, art, model } = await openFirstPlayable(page);
    const canvas = page.locator("canvas.minimap");

    /*
      Utility and sight off: both draw in team colours and this test is about
      players. Turning SIGHT off is the point rather than a workaround -- the
      assertion below counts team-coloured pixels that are near no predicted
      player and allows fewer than 200, and a cone is a team-coloured wash
      across half the map by design. Leaving it on would mean loosening the
      budget until it stopped catching what it exists to catch, which is a
      marker drawn where nobody is. The cones have their own spec below.
    */
    /*
      And tracers off, for the same reason SIGHT is off: a tracer is drawn
      in a side colour, and this counts side-coloured pixels. It is on screen
      for half a second before its kill and most of another after, and
      `stepToEvent` seeks to an `event_times` entry -- which is often a kill,
      landing the playhead on one at full opacity. Its own test is below.
    */
    await setLayer(page, "TRACERS (SIM)", false);
    await setLayer(page, "SIGHT", false);
    await toggleLayer(page, "UTILITY");

    const moment = firstCrowdedEvent(model);
    const tMs = moment.tMs;
    await stepToEvent(page, moment);
    // The playhead is exact, so the readout is the arithmetic's own witness.
    // It reads *into the round* over the round's own length, because the
    // transport is scoped to a round -- a scrubber spanning twenty-six minutes
    // gave round four about forty pixels.
    const round = replay.rounds.find(
      (entry) => entry.number === moment.roundNo,
    )!;
    await expect(page.locator(".clock-readout")).toHaveText(
      `${clockText(tMs - round.start_ms)} / ${clockText(round.duration_ms)}`,
    );

    const image = await readCanvas(page, canvas);
    const box = placeSquare(image.width, image.height);
    const snap = stateAt(model, tMs);

    const expected = replay.players
      .map((player) => ({
        player,
        position: positionOf(snap, player.actor_id),
      }))
      .filter((entry) => entry.position !== null)
      .map((entry) => {
        const [u, v] = applyTransform(
          art.transform,
          entry.position!.x,
          entry.position!.y,
        );
        const [x, y] = uvToPixels(box, u, v);
        return { player: entry.player, x, y };
      });
    expect(
      expected.length,
      "the chosen instant has players to draw",
    ).toBeGreaterThanOrEqual(8);

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
    expect(
      matched.length,
      "team colours are on the canvas at all",
    ).toBeGreaterThan(0);

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
    expect(
      unclaimed,
      "team-coloured pixels away from any predicted player",
    ).toBeLessThan(200);
  });

  test("every living player gets a cone, pointing where they are facing", async ({
    page,
  }) => {
    const { art, sight, model } = await openFirstPlayable(page);
    const canvas = page.locator("canvas.minimap");
    /*
      And tracers off, for the same reason SIGHT is off: a tracer is drawn
      in a side colour, and this counts side-coloured pixels. It is on screen
      for half a second before its kill and most of another after, and
      `stepToEvent` seeks to an `event_times` entry -- which is often a kill,
      landing the playhead on one at full opacity. Its own test is below.
    */
    await setLayer(page, "TRACERS (SIM)", false);
    await setLayer(page, "SIGHT", false);
    await toggleLayer(page, "UTILITY");

    const moment = firstCrowdedEvent(model);
    const tMs = moment.tMs;
    await stepToEvent(page, moment);

    const first = await readCanvas(page, canvas);
    const box = placeSquare(first.width, first.height);
    const snap = stateAt(model, tMs);

    const settings: SightSettings = {
      max_range_uu: sight.max_range_uu,
      fov_degrees: sight.fov_degrees,
      ray_step_degrees: sight.ray_step_degrees,
      seed_cells: sight.seed_cells,
      probe_uu: sight.probe_uu,
    };
    const mask = decodeMask(sight.size, sight.cells);

    /*
      Every cone the model says should be on the canvas, not just one.

      This spec used to select a player and check their single wedge against
      the same wedge rotated a quarter turn -- the control that catches
      trigonometry done in uv space, which puts every cone ninety degrees out
      and looks entirely plausible. The layer draws one per living player now,
      so a rotated control aimed at one of them lands inside somebody else's
      cone and the comparison stops discriminating. Rotating *every* cone about
      *its own* player restores it: the real set covers what the model
      predicts, and any turn of the whole set does not.
    */
    const drawn = model.replay.players
      .map((player) => ({
        player,
        position: snap.positions.get(player.actor_id),
      }))
      .filter(
        (e) => e.position !== undefined && snap.alive.has(e.player.actor_id),
      )
      .map(({ player, position }) => {
        const [u, v] = applyTransform(art.transform, position!.x, position!.y);
        return {
          player,
          origin: uvToPixels(box, u, v),
          /*
              The same occluders the canvas passes, and not an empty list.

              `MinimapCanvas` and `Scene3D` both hand `smokesAt(art, snap)` to
              `cone`, so a cone recomputed without them is a *different* cone --
              longer wherever a smoke is standing in it -- and the coverage this
              spec measures would read as the layer failing to paint what it was
              told to.  It went unnoticed while the moment this lands on was the
              capture's first millisecond, where no utility is out at all; the
              transport opens a round at the barrier drop now, and five pieces
              are out within a frame of it.
            */
          polygon: cone(
            mask,
            [u, v],
            forwardUv(
              art.transform,
              position!.x,
              position!.y,
              position!.yaw,
              settings.probe_uu,
            ),
            uvRadius(art.transform, settings.max_range_uu),
            settings,
            smokesAt(art, snap),
          ),
        };
      })
      .filter((entry) => entry.polygon.length > 2);

    expect(
      drawn.length,
      "several players have a cone to draw here",
    ).toBeGreaterThan(2);

    await setLayer(page, "SIGHT", true);
    const lit = await readCanvas(page, canvas);

    // Sample halfway along every ray of every cone, each rotated about the
    // player it belongs to.
    const rate = (turn: number): number => {
      let sampled = 0;
      let changed = 0;
      for (const { origin, polygon } of drawn) {
        const [px, py] = origin;
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
          /*
            Four, not eight: `SIGHT_ALPHA` is a quarter now and was a half, so
            the delta this looks for is half the size it was. The question is
            "did this pixel change at all" -- leaving the threshold where it
            was would quietly turn it into "did it change a lot" and drop every
            sample over the paler parts of the radar, which is a different test
            passing under the same name.
          */
          if (rgbDistance(before, after) > 4) {
            changed += 1;
          }
        }
      }
      return sampled === 0 ? 0 : changed / sampled;
    };

    const forward = rate(0);
    const left = rate(Math.PI / 2);
    const right = rate(-Math.PI / 2);
    const behind = rate(Math.PI);
    // eslint-disable-next-line no-console
    console.log(
      `cones ${drawn.length}: forward ${forward.toFixed(3)} left ${left.toFixed(3)} ` +
        `right ${right.toFixed(3)} behind ${behind.toFixed(3)}`,
    );
    expect(
      forward,
      "the wash covers the cones the model computed",
    ).toBeGreaterThan(0.6);
    expect(
      forward,
      "and covers them better than the same cones turned",
    ).toBeGreaterThan(Math.max(left, right, behind) + 0.15);
  });

  test("scrubbing backwards lands on exactly the same frame", async ({
    page,
  }) => {
    const { model } = await openFirstPlayable(page);
    const canvas = page.locator("canvas.minimap");
    await toggleLayer(page, "UTILITY");

    const moment = firstCrowdedEvent(model);
    await stepToEvent(page, moment);
    const there = await readCanvas(page, canvas);
    const readout = await page.locator(".clock-readout").textContent();

    // Out to the end of the round and back to its start. `stateAt` accumulates
    // nothing, so the returning frame has to be the outgoing one to the pixel.
    await page.getByTitle("To the end").click();
    await page.getByTitle("Back to the start").click();
    await stepToEvent(page, moment);
    const back = await readCanvas(page, canvas);

    expect(await page.locator(".clock-readout").textContent()).toBe(readout);
    // Size first, and it is not a formality: the two reads are compared index
    // by index, so a canvas that grew by a row between them reports tens of
    // thousands of differing pixels and says nothing about what was drawn.
    expect(
      [back.width, back.height],
      "the canvas is the same size in both reads",
    ).toEqual([there.width, there.height]);
    let differing = 0;
    for (let i = 0; i < there.data.length; i += 4) {
      if (
        there.data[i] !== back.data[i] ||
        there.data[i + 1] !== back.data[i + 1]
      ) {
        differing += 1;
      }
    }
    expect(
      differing,
      "the same instant is drawn identically from either side",
    ).toBe(0);
  });

  /*
    The planted spike is on the map, and this is the test that says so.

    The failure this guards is the quiet one.  A marker that is computed, laid
    out and then drawn nowhere -- because a coordinate never arrived, or a
    colour resolved to the background, or the layer was gated on something that
    is never true -- looks exactly like a round in which nobody planted.  That
    is how `floorZ` lifted every player out of frame on four captures for nine
    months while the ground rendered perfectly underneath.

    So: seek to a moment at which the model says the spike is down, and require
    amber pixels at the coordinate it says the plant is at.  `--spike-armed` is
    the one colour on this canvas that is neither team's -- deliberately, it is
    90 RGB from the attacker red it used to be 12 from -- so finding it is
    unambiguous.

    **Not the plant instant itself, and that is the point of `uncoveredPlant`.**
    The spike draws *under* the players, which is a rule this canvas keeps on
    purpose: a person hidden behind an object is the one thing it cannot afford
    to lose.  At the millisecond of the plant the planter is by definition
    standing on the spike -- measured at 2.2 px away on the reference capture --
    so their portrait covers the triangle completely and there is no amber to
    find.  That is the drawing behaving as designed, so the test moves to the
    first later event in the same round at which nobody is near enough to cover
    it, rather than the drawing moving to suit the test.
  */
  test("draws the spike where it was planted", async ({ page }) => {
    const { model, art } = await openFirstPlayable(page);
    const canvas = page.locator("canvas.minimap");

    // `clientWidth`/`clientHeight`, not `boundingBox()`: those are the two
    // numbers `MinimapCanvas` itself hands `placeSquare`, and they are whole
    // pixels where the bounding box is fractional -- a third of a pixel of
    // disagreement moves the box's side and with it every coordinate below.
    const [width, height] = await canvas.evaluate((element) => [
      element.clientWidth,
      element.clientHeight,
    ]);
    const box = placeSquare(width, height);

    const found = uncoveredPlant(model, art.transform, box);
    // Every playable capture in the reference library has a located plant, but
    // a library that had none -- or none the planter ever walks away from --
    // should skip rather than fail: this is about the drawing.
    test.skip(
      found === null,
      "no located plant this capture ever leaves uncovered",
    );
    const { at, moment } = found!;

    // `Replay.event_times` includes every spike event, so `>>` lands on the
    // chosen moment exactly rather than near it.
    await stepToEvent(page, moment);

    const image = await readCanvas(page, canvas);
    // Within a pixel, never equal: an element screenshot clips the page to the
    // element's *bounding box*, which is fractional (975.03 x 806.42 here), and
    // rounds it out to whole raster pixels -- so the image is up to one pixel
    // larger than the CSS box the canvas laid itself out in.  That is half a
    // pixel of drift on a coordinate, against a `MARKER_REACH` of 26.
    expect(
      Math.max(Math.abs(image.width - width), Math.abs(image.height - height)),
      "the screenshot is the box the moment was chosen against",
    ).toBeLessThanOrEqual(1);
    const [u, v] = applyTransform(art.transform, at.x, at.y);
    const [x, y] = uvToPixels(box, u, v);

    const colours = await palette(page);
    const amber = parseColour(colours.spikeArmed!);
    /*
      Nothing is stepped over any more.  While the clock floated over the map it
      carried a `SPIKE DOWN` badge whose text and 1px border are `currentcolor`
      -- `--spike-armed` -- and an element screenshot clips the page rather than
      isolating it, so ~210 amber pixels were in the read of the canvas without
      one of them having been drawn on it.  The clock is in the stage head now
      and outside this box entirely, so every amber pixel below was painted here.
    */
    let near = 0;
    const stray: Array<[number, number]> = [];
    for (const [px, py] of colouredPixels(image, [amber])) {
      if (Math.hypot(px - x, py - y) <= MARKER_REACH) {
        near += 1;
      } else {
        stray.push([px, py]);
      }
    }
    expect(near, `spike at (${x.toFixed(1)}, ${y.toFixed(1)})`).toBeGreaterThan(
      20,
    );
    /*
      And nowhere else -- but as the largest *patch* rather than as a total.

      A count cannot say this.  Riot's own radar art has warm orange detail on
      it, 33 to 41 pixels of it within tolerance of `--spike-armed` on the
      reference capture, and turning the utility layer off *raises* that number
      because ability markers had been covering some of it.  So the map's own
      amber is a permanent floor that no budget can distinguish from a second
      marker of the same size.

      What the two failure modes this guards do have in common is a *patch*: a
      marker at the wrong coordinate is a whole triangle somewhere else, and a
      canvas drawn without clearing is a trail of them.  The map's noise is
      scattered -- its biggest connected run is 14 pixels -- so the assertion is
      that the plant is the biggest amber thing on the canvas, which needs no
      threshold at all.
    */
    expect(
      largestPatch(stray),
      "an amber patch away from the plant, as large as the plant's own",
    ).toBeLessThan(near);
  });
  /*
    The tracer, which is the one mark on this canvas that nothing decoded.

    A `.vrf` holds no shot: what is read is that two players were in two known
    places at one known millisecond, and the line between them is drawn by this
    project.  So the assertion cannot be "a line is where the file says", the
    way the spike's is -- it is that the line is where the *model* says, in the
    killer's own side colour, and nowhere else.

    It is measured as a **difference** between two reads of the same instant
    rather than as a colour count, and that is what makes it specific.  Both
    team colours are already all over this canvas as player markers; a total
    could be satisfied by the markers alone.  The playhead does not move between
    the two reads and `stateAt` accumulates nothing, so the only pixels that can
    differ are the ones this layer painted.
  */
  test("draws the fatal shot between the two players, in the killer's colour", async ({
    page,
  }) => {
    const { model, art } = await openFirstPlayable(page);
    const canvas = page.locator("canvas.minimap");
    await setLayer(page, "SIGHT", false);
    await toggleLayer(page, "UTILITY");

    const [width, height] = await canvas.evaluate((element) => [
      element.clientWidth,
      element.clientHeight,
    ]);
    const box = placeSquare(width, height);

    const found = firstLoneTracer(model, art.transform, box);
    // A capture whose kills all land on top of each other, or whose killers
    // have no track at the instant they fired, has nothing to photograph here.
    test.skip(
      found === null,
      "no kill this capture draws a lone, long tracer for",
    );
    const { moment, tracer } = found!;

    // `Replay.event_times` carries every kill, so `>>` lands on the shot
    // itself -- which is the instant the bullet *lands*, so the whole line is
    // drawn at full opacity. The flight is the second before this.
    await stepToEvent(page, moment);

    await setLayer(page, "TRACERS (SIM)", false);
    const without = await readCanvas(page, canvas);
    await setLayer(page, "TRACERS (SIM)", true);
    const with_ = await readCanvas(page, canvas);

    const changed: Array<[number, number]> = [];
    for (let y = 0; y < Math.min(with_.height, without.height); y += 1) {
      for (let x = 0; x < Math.min(with_.width, without.width); x += 1) {
        const lit = pixelAt(with_, x, y);
        const dark = pixelAt(without, x, y);
        if (lit !== null && dark !== null && rgbDistance(lit, dark) > 20) {
          changed.push([x, y]);
        }
      }
    }
    expect(
      changed.length,
      "the layer painted something at all",
    ).toBeGreaterThan(40);

    const [ax, ay] = screenPoint(
      art.transform,
      box,
      tracer.from.x,
      tracer.from.y,
    );
    const [bx, by] = screenPoint(art.transform, box, tracer.to.x, tracer.to.y);
    /*
      Everything it painted is on the line it claims to be.

      The slack is the stroke and its glow: `TRACER_WIDTH` is 2 and
      `TRACER_TRAIL_GLOW` spreads a further six, and a `shadowBlur` of six
      reaches about that far before it is lost in the radar. Plus the half
      pixel a clipped element screenshot can drift by.
    */
    const strays = changed.filter(
      ([x, y]) => distanceToSegment(x, y, ax, ay, bx, by) > 10,
    );
    expect(
      strays.length / changed.length,
      "pixels this layer changed that are not on the killer-to-victim line",
    ).toBeLessThan(0.1);

    /*
      And it is the killer's side that colours it, which is the whole of what
      "red or blue" means here: the side, never the team, so it stays right
      across the halftime swap.

      Measured as the **shift** each pixel took rather than the colour it
      ended at, and that is a correction rather than a loosening. Most of a
      glow is gradient -- a few percent of the side's colour over Riot's grey
      -- so asking whether the pixel is *within 36 of red* answers "no" for
      ink that is unmistakably red to a reader, and the assertion measured the
      hardness of the stroke instead of its hue. What actually has to be true
      is that the light this layer added is the killer's: for an attacker the
      pixel moved further toward red than toward blue, and for a defender the
      other way. That is the same red-minus-blue test `scene.spec.ts` uses on
      the markers, and it survives any alpha.
    */
    const towardMine = changed.filter(([x, y]) => {
      const lit = pixelAt(with_, x, y);
      const dark = pixelAt(without, x, y);
      if (lit === null || dark === null) {
        return false;
      }
      const warmer = lit[0] - dark[0] - (lit[2] - dark[2]);
      return tracer.side === "ATK" ? warmer > 0 : warmer < 0;
    });
    expect(
      towardMine.length / changed.length,
      `the light this tracer added is the ${tracer.side} colour`,
    ).toBeGreaterThan(0.9);
  });
});
