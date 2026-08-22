/**
 * The one config that runs `e2e/docshots.spec.ts`, and nothing else.
 *
 * The default config ignores that spec on purpose: it writes the README's
 * committed screenshots into `docs/images/ui/`, and a suite that rewrote
 * committed files every time somebody ran it would put a diff in whatever
 * branch happened to run the tests.  So regenerating the pictures is an
 * explicit act -- `npm run docshots` -- rather than a side effect of `npm run
 * test:e2e`.
 *
 * Everything else is the base config, spread rather than repeated: the two
 * servers, the 1500x1000 viewport the stage is sized against, the `chromium`
 * channel the scene needs, and the ninety-second timeout a decode wants.  The
 * only overrides are which files run and where the run's own scratch goes,
 * because the screenshots this writes are *not* Playwright output and must not
 * land beside the traces in `e2e/results/`.
 */

import { defineConfig } from "@playwright/test";

import base from "./playwright.config";

export default defineConfig({
  ...base,
  testIgnore: undefined,
  testMatch: "**/docshots.spec.ts",
  // No HTML report: this run produces seven files a person is about to look at
  // in the repository, not a report to open.
  reporter: [["list"]],
  use: {
    ...base.use,
    /*
      Every card and panel on this interface arrives rather than appearing, on
      a `transform`/`opacity` transition whose duration is `--dur-entry`.  A
      screenshot taken while that is still running catches rows at 40% opacity
      and halfway through their travel, which is a picture of the animation
      rather than of the page -- the first match-list shot came out with two of
      its four cards ghosted.

      `prefers-reduced-motion` zeroes every duration token in `app.css`, so the
      reveal collapses to an instant state change and there is nothing in
      flight to photograph.  It is also the honest setting for a still: a
      screenshot has no motion to preserve.
    */
    reducedMotion: "reduce",
  },
});
