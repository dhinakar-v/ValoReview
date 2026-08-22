# web

The browser half of the replay analyzer. React over the FastAPI server in
`libraries/vrfserve/`.

    npm install
    npm run dev        vite on 5173, proxying /api and /assets to 127.0.0.1:8000
    npm run build      writes dist/, which the Python server mounts at /
    npm test           vitest
    npm run lint       tsc --noEmit
    npm run types      regenerate src/api/schema.d.ts from a running server

`runners\vrf-serve.bat` starts the Python side. In development run both: Vite
proxies `/api` and `/assets` across, so development and production are equally
same-origin and there is no CORS to grant. In production `vite build` writes
`dist/` and the Python server serves it — one process, one port.

## Two things about the build

The bundle is emitted to `dist/static/`, not Vite's default `dist/assets/`. The
server serves Riot's art at `/assets`, and a bundle emitted there would be
shadowed by it: the page would load and its own JavaScript would 404.
`vite.config.ts` and `vrfserve/app.py` both say so, because both have to agree.

The page routes on the client, so `/replay/<id>` is a real address that no file
answers to. The server serves a file where one exists and the page everywhere
else, which is what makes a bookmark or a reload work away from the root.

## Dependencies, and why each one is here

The Python side adds a dependency only when the standard library genuinely
lacks the thing. That rule cannot be applied as literally on npm — the 3D view
alone brings `three` — so the substitute is this list. Nothing goes in without
a line here saying what it buys.

| Package | What it buys |
|---|---|
| `react`, `react-dom` | The view layer. |
| `react-router-dom` | Real URLs. `/map/:key` is not a convenience: the map reference must be reachable *without* a replay, and a route that can only receive a map key is how the desktop guarantee — `mapref.show` is handed no `Replay` — survives becoming an address. |
| `@tanstack/react-query` | Fetch state. Refetch-on-focus is off: a local server reading files off a disk does not go stale on its own, and a rescan is a button. It also owns the decode mutation, which replaces the whole replay rather than patching the tracks. |

Dev: `vite`, `@vitejs/plugin-react`, `typescript`, `vitest`, `jsdom`,
`@testing-library/react`, `openapi-typescript`.

There is no UI kit, no CSS framework and no charting library. The layout is a
handful of grid rows and two columns, and `src/app.css` is the whole of it.

## Colours

`src/theme.generated.css` is written by `scripts/make_theme.py` from
`libraries/vrfview/theme.py` — **do not edit it, and do not put a hex value
anywhere else.** `tests/test_theme.py` fails if the committed file has gone
stale.

The palette carries an argument, which is why it is generated rather than
copied. The brief names its red ATK and its blue DEF; this project does not
adopt those meanings, because which team attacked is not recoverable from a
replay — spike events carry no actor id. The hues are the brief's, the labels
say A and B, and the reasoning lives beside the constants in `theme.py` where
anyone changing them will read it.

## Types

`src/api/types.ts` mirrors `libraries/vrfserve/schema.py` by hand for now.
`npm run types` generates the full set from the running server's OpenAPI
document into `src/api/schema.d.ts`; until the routes settle it is cheaper to
declare the fields the pages actually read.

The pydantic models are the contract either way, and
`tests/test_vrfserve.py::WireBuilders` asserts every dict the server builds
validates against them.

## What the interface must keep saying

Three of these are load-bearing, and each is pinned by a test in
`src/pages/*.test.tsx`:

- **A capture with no payload transform is held back, never dropped.** The
  footer counts it and SHOW ALL lists it. A library that displays 21 of 101
  files without mentioning the other 80 is lying about what is on the disk.
- **Every card says `result not in file`.** The WIN/LOSS badge the brief asks
  for cannot be built — there is no local player in a replay and the teams are
  A and B by inference — and a blank space where a verdict belongs reads as a
  bug rather than as an absence.
- **Where a map cannot be drawn, there is a sentence.** Never a schematic,
  never a placeholder drawing. A diagram in the place a map goes reads as a map
  however it is captioned, so the two things that can be missing — the decode
  and the radar image — each get words instead.
- **A DECODE button appears only where one can work.** Without a built decoder there is nothing to press, so the sentence names `runners\build-decoder.bat` instead. A control that cannot do anything is worse than an explanation of its absence.

And one about arithmetic: `applyTransform` swaps the axes, world *y* into u.
That is measured, not assumed, and the unswapped form produces a plausible
wrong answer rather than an obvious one. `src/pages/transform.test.ts` pins it
on this side of the wire; `tests/test_vrfview.py` pins it on the other.
