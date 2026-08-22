/**
 * The standing guard on which canvas honours which layer.
 *
 * `UTILITY`, `KILL MARKERS` and `RANGE (SIM)` shipped enabled in 3D and drew
 * nothing at all, because `Scene3D` reads three of the six map layers and no
 * file said so.  Nothing caught it and nothing could have: the rows rendered,
 * the boxes flipped, and `e2e/harness.ts:toggleLayer` asserts exactly that the
 * box is enabled and that it flipped -- both true the entire time.  A pixel
 * suite photographs what *is* drawn, so a mark that is simply absent looks
 * like a quiet map rather than a fault.
 *
 * So this walks the two canvas sources the way `tests/test_layering.py` walks
 * the Python tree, and compares what they read against what `LayersMenu`
 * declares.  It fails in both directions -- a layer declared and unread, or
 * read and undeclared -- because either one is the same drift.
 */

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { EVENT_LAYERS, MAP_LAYERS } from "./LayersMenu";

/** Every `layers.<key>` this source actually reads. */
function layersReadBy(file: string): Set<string> {
  const source = readFileSync(new URL(file, import.meta.url), "utf8");
  const found = new Set<string>();
  for (const match of source.matchAll(/layers\.(\w+)/g)) {
    const key = match[1];
    if (key !== undefined) found.add(key);
  }
  return found;
}

const CANVASES = {
  "2d": layersReadBy("./MinimapCanvas.tsx"),
  "3d": layersReadBy("./Scene3D.tsx"),
} as const;

describe("what each canvas honours", () => {
  // Cheap insurance against the regex silently matching nothing -- an empty
  // set would make every assertion below vacuously true in one direction.
  it.each(["2d", "3d"] as const)("finds layer reads in the %s canvas", (view) => {
    expect(CANVASES[view].size).toBeGreaterThan(0);
  });

  it.each(MAP_LAYERS.map((entry) => [entry.label, entry] as const))(
    "%s is drawn by exactly the canvases it claims",
    (_label, entry) => {
      for (const view of ["2d", "3d"] as const) {
        expect({ view, reads: CANVASES[view].has(entry.key) }).toEqual({
          view,
          reads: entry.drawnIn.includes(view),
        });
      }
    },
  );

  it.each(MAP_LAYERS.map((entry) => [entry.label, entry] as const))(
    "%s explains itself in any view it is not drawn in",
    (_label, entry) => {
      for (const view of ["2d", "3d"] as const) {
        if (entry.drawnIn.includes(view)) continue;
        // A row that cannot do anything here must say why.  `hasMask` is true
        // so that SIGHT's own reason cannot stand in for a missing one.
        const why = entry.why?.({ hasMask: true, is3d: view === "3d" }) ?? null;
        expect(why, `${entry.label} is inert in ${view} and gives no reason`).not.toBeNull();
      }
    },
  );

  it("draws every map layer somewhere", () => {
    const orphans = MAP_LAYERS.filter((entry) => entry.drawnIn.length === 0);
    expect(orphans.map((entry) => entry.label)).toEqual([]);
  });

  it("keeps the timeline layers off both canvases", () => {
    // These mark the rail, not the map.  One reaching a canvas would mean a
    // rail tick had quietly become a map mark.
    for (const entry of EVENT_LAYERS) {
      expect(entry.drawnIn).toEqual([]);
      for (const view of ["2d", "3d"] as const) {
        expect(`${entry.label} in ${view}: ${CANVASES[view].has(entry.key)}`).toBe(
          `${entry.label} in ${view}: false`,
        );
      }
    }
  });
});
