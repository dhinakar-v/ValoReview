/**
 * That a picture is asked for once and drawn as soon as it arrives.
 *
 * Both of these were real faults and both were **silent**, which is why they
 * are pinned here rather than left to the pixel suite. `useImages` is handed a
 * URL per *drawn thing* -- `MinimapCanvas` passes one per ability cast, six
 * thousand of them on a full match naming about forty files -- and it used to
 * take that list literally and publish nothing until the last request settled.
 * The result was an interface that had every icon on disk, resolved correctly
 * on the wire, and drew none of them: every ability marker fell back to its
 * blank form while a queue of thousands drained six connections at a time, and
 * one request that never settled meant it never drew any of them at all.
 *
 * Nothing threw and no test failed. The only visible symptom was a marker
 * looking like the one case the canvas draws when it genuinely has no picture,
 * which is exactly the confusion the fallback exists to avoid.
 */

import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useImages } from "./images";

/** Every `Image` the hook built, in construction order. */
let built: FakeImage[] = [];

class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  #src = "";

  constructor() {
    built.push(this);
  }

  get src(): string {
    return this.#src;
  }

  /* jsdom will not fetch anything, so the load is driven by the test. */
  set src(value: string) {
    this.#src = value;
  }

  arrive(): void {
    // Inside `act`, because this is the browser calling back into React from
    // outside a render -- which is exactly what the real load does.
    act(() => {
      this.onload?.();
    });
  }
}

/** Renders the hook and exposes whatever it currently holds. */
function harness(urls: Array<string | null>) {
  const seen: Array<Map<string, HTMLImageElement>> = [];
  function Probe() {
    seen.push(useImages(urls));
    return null;
  }
  act(() => {
    render(<Probe />);
  });
  return seen;
}

describe("loading the pictures a canvas needs", () => {
  beforeEach(() => {
    built = [];
    vi.stubGlobal("Image", FakeImage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("asks for each file once however many things are drawn with it", () => {
    // The shape `MinimapCanvas` actually passes: one entry per cast, and a
    // handful of distinct icons behind thousands of them.
    const casts = Array.from({ length: 500 }, (_, i) =>
      i % 2 === 0 ? "/assets/a.png" : "/assets/b.png",
    );
    harness(casts);
    expect(built).toHaveLength(2);
    expect(built.map((image) => image.src).sort()).toEqual([
      "/assets/a.png",
      "/assets/b.png",
    ]);
  });

  it("skips a null rather than requesting it", () => {
    harness(["/assets/a.png", null]);
    expect(built).toHaveLength(1);
  });

  it("publishes a picture the moment it arrives, not once they all have", () => {
    // The half that made the icons invisible. One file still in flight must
    // not hold back the one that has landed.
    const seen = harness(["/assets/a.png", "/assets/b.png"]);
    expect(seen.at(-1)!.size).toBe(0);
    built[0]!.arrive();
    expect(seen.at(-1)!.has(built[0]!.src)).toBe(true);
    // And the other is still absent rather than the map being replaced.
    expect(seen.at(-1)!.has(built[1]!.src)).toBe(false);
    built[1]!.arrive();
    expect(seen.at(-1)!.size).toBe(2);
  });

  it("leaves a picture that never arrives simply absent", () => {
    // The same state as one that failed, which is the state every caller
    // already draws -- a fresh checkout has no `assets/` at all.
    const seen = harness(["/assets/a.png", "/assets/missing.png"]);
    built[0]!.arrive();
    expect(seen.at(-1)!.size).toBe(1);
  });
});
