import react from "@vitejs/plugin-react";
// vitest/config rather than vite: it is the same defineConfig widened to
// accept the `test` block below, which vite's own type does not know about.
import { defineConfig } from "vitest/config";

// The dev server proxies /api and /assets to the Python server, so development
// and production are both same-origin and CORS never enters the picture. A CORS
// middleware on the backend would be a permission granted to every page the
// browser happens to have open, in exchange for nothing.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/assets": "http://127.0.0.1:8000",
    },
  },
  build: {
    // libraries/vrfserve/app.py mounts this directory at / when it exists.
    outDir: "dist",
    emptyOutDir: true,
    // Not the Vite default of "assets": the server already serves Riot's art
    // at /assets, and a bundle emitted there would be shadowed by it -- the
    // page would load and its own JavaScript would 404.
    assetsDir: "static",
  },
  test: {
    // The model ports are pure arithmetic and need no DOM; the page tests do.
    // One environment for both is simpler than two configs.
    environment: "jsdom",
    globals: false,
  },
});
