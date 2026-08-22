/**
 * The browser tests, which exist because jsdom cannot see a drawing.
 *
 * `npm test` (vitest, jsdom) covers the arithmetic and the sentences: the model
 * ports are checked against Python's own fixtures in `tests/golden/`, and
 * `MapStage.test.tsx` checks that every claim the page makes is the claim the
 * server handed it.  Neither can check the two things this project actually
 * puts on screen, because jsdom has no 2D context and no WebGL: the minimap's
 * draw loop and the r3f scene graph.  Everything below the `e2e/` directory is
 * about pixels for that reason, and about nothing else.
 *
 * `channel: "chromium"` rather than the default headless shell -- the shell is
 * the old headless build and its WebGL support is not the browser's.  The scene
 * has to render on the same stack a user would get, or a passing test says
 * nothing about the thing it is named after.
 *
 * Two servers, because that is the arrangement development already uses: the
 * Python server holds the replays and Riot's art, Vite proxies `/api` and
 * `/assets` to it, and both ends are same-origin so CORS never enters the
 * picture.  `reuseExistingServer` is on, so a server already up on either port
 * is used as it stands rather than fought over.
 */

import { defineConfig, devices } from "@playwright/test";

// `localhost`, not `127.0.0.1`: Vite binds the name, which resolves to ::1
// first on Windows, so the dotted-quad form refuses the connection and the
// server looks like it never started.  The API server binds the quad.
export const WEB_URL = "http://localhost:5173";
export const API_URL = "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./e2e",
  // The suite drives one library and one replay; parallel workers would race
  // for the server's two open-replay slots rather than finish any sooner.
  fullyParallel: false,
  workers: 1,
  // A decode is about four seconds and a first paint waits on Riot's art, so
  // the default five seconds is short for reasons that are not failures.
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e/report" }]],
  outputDir: "e2e/results",
  use: {
    baseURL: WEB_URL,
    // Large enough that the stage is not the size of a postage stamp: the
    // orientation check samples the ground texture, and a small canvas is a
    // blurry one.
    viewport: { width: 1500, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        channel: "chromium",
        viewport: { width: 1500, height: 1000 },
      },
    },
  ],
  webServer: [
    {
      command:
        "uv run python scripts/vrf_serve.py --demo-path Demos --port 8000 --no-prewarm",
      cwd: "..",
      url: `${API_URL}/api/config`,
      reuseExistingServer: true,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: "npm run dev",
      url: WEB_URL,
      reuseExistingServer: true,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
