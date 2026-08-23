// Rasterise the product mark into the icon set Tauri's bundler needs.
//
//     node desktop/packaging/make-icon.mjs
//     cd desktop && npx tauri icon packaging/appicon.png
//
// The mark has exactly two committed drawings -- web/src/views/icons.tsx for
// React and web/public/favicon.svg for the tab -- and a Windows app icon must
// not become a third. So this renders the committed SVG rather than redrawing
// it, using the Chromium the e2e suite already installs.
//
// The SVG carries its own opaque square, which is what the icon wants: a
// Windows taskbar and Start tile paint an icon over whatever the user's accent
// colour is, and a transparent ring in brand red disappears into half of them.
// So it is rendered edge to edge with no padding and no second background --
// two nested squares in slightly different greys is a rendering artefact, not
// a design.
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
// Resolved against web/'s package.json rather than this file's directory:
// desktop/ has its own node_modules holding the Tauri CLI and nothing else,
// and Playwright is a dependency of the browser tests, where it belongs.
const { chromium } = createRequire(resolve(here, "../../web/package.json"))(
  "@playwright/test",
);
const svg = readFileSync(resolve(here, "../../web/public/favicon.svg"), "utf8");
const out = resolve(here, "appicon.png");

const SIZE = 1024;

const page = await (await chromium.launch()).newPage({
  viewport: { width: SIZE, height: SIZE },
  deviceScaleFactor: 1,
});
await page.setContent(
  `<style>
     html,body{margin:0;width:${SIZE}px;height:${SIZE}px}
     svg{display:block;width:${SIZE}px;height:${SIZE}px}
   </style>${svg}`,
  { waitUntil: "load" },
);
writeFileSync(out, await page.screenshot({ type: "png" }));
await page.context().browser().close();
console.log(`wrote ${out}`);
