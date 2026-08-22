/**
 * The one piece of arithmetic the browser must not get wrong.
 *
 * `Transform.apply` swaps the axes: world *y* feeds u and world *x* feeds v.
 * That is measured rather than assumed -- running all 346 callouts in the
 * manifest through the unswapped form lands 200 of them inside the image, and
 * through this form 346 of 346 -- and the wrong version does not crash or look
 * obviously broken.  It produces a plausible wrong answer, which is why Python
 * pins it with a test and why this file exists on the other side of the wire.
 *
 * The numbers below are Abyss's real transform out of assets/manifest.json.
 */

import { describe, expect, it } from "vitest";

import type { Transform } from "../api/types";
import { applyTransform } from "./MapReference";

const ABYSS: Transform = {
  x_multiplier: 8.1e-5,
  y_multiplier: -8.1e-5,
  x_scalar_to_add: 0.5,
  y_scalar_to_add: 0.5,
  usable: true,
  vertical_scale: 8.1e-5,
};

describe("applyTransform", () => {
  it("feeds world y into u and world x into v", () => {
    const [u, v] = applyTransform(ABYSS, 1000, 2000);
    expect(u).toBeCloseTo(2000 * 8.1e-5 + 0.5, 12);
    expect(v).toBeCloseTo(1000 * -8.1e-5 + 0.5, 12);
  });

  it("is not the unswapped form, which is the plausible wrong answer", () => {
    const [u, v] = applyTransform(ABYSS, 1000, 2000);
    const unswappedU = 1000 * 8.1e-5 + 0.5;
    expect(u).not.toBeCloseTo(unswappedU, 6);
    expect(v).not.toBeCloseTo(2000 * -8.1e-5 + 0.5, 6);
  });

  it("puts the world origin at the centre of this radar", () => {
    expect(applyTransform(ABYSS, 0, 0)).toEqual([0.5, 0.5]);
  });

  it("keeps a negative multiplier's sign rather than taking its size", () => {
    const [, v] = applyTransform(ABYSS, 10000, 0);
    expect(v).toBeLessThan(0.5);
  });
});
