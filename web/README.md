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
| `zustand` | The playhead, the view mode and the layer toggles, shared by three components that are not each other's children. Lifting them into the page would re-render the roster, the round table and the provenance panel sixty times a second; the canvas and the scene subscribe to nothing at all and read `getState()` inside their own animation frame. |
| `three` | The 3D scene. There is no smaller way to put a textured plane and ten markers in a perspective camera, and writing WebGL by hand to avoid a dependency would be a much larger thing to maintain than the dependency. |
| `@react-three/fiber` | `three` as React components, so the scene's lifetime is the component's and `useFrame` is the per-frame hook. The alternative is a manual renderer, a manual resize observer and a manual teardown, all of which this already gets right. |
| `@react-three/drei` | `OrbitControls` and `Html`. Orbit is a camera rig everybody writes the same way and nobody writes correctly the first time; `Html` is what puts a callout label in the scene without a text-geometry pipeline. |

`three` and its two wrappers are about a megabyte, and the 2D view is the
default — so `Scene3D` is behind a `React.lazy`, and the readable view costs
nothing for a renderer it never uses. `SCENE_CAPTION` lives in its own module
for the same reason: rendering the sentence must not pull in the thing it is a
sentence about.

Dev: `vite`, `@vitejs/plugin-react`, `typescript`, `vitest`, `jsdom`,
`@testing-library/react`, `openapi-typescript`, `@types/node` (the parity test
reads `tests/golden/` off disk rather than importing it, because those fixtures
are Python's output and live outside `web/`), `@types/three`, and
`@playwright/test` — which is there because jsdom has no 2D context and no
WebGL, so nothing else in this repo can look at a single thing this page draws.
See *Two test tiers* below.

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

Each of these is load-bearing, and each is pinned by a test in
`src/pages/*.test.tsx` or `src/views/MapStage.test.tsx`:

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
- **A DECODE button appears only where one can work**, and there are two ways
  it cannot. A build with no payload transform will refuse whatever is pressed,
  so the card's own sentence goes there instead; a machine with no decoder has
  nothing to press at all, so the sentence names `runners\build-decoder.bat`.
  They are fixed by different things and therefore say different things. A
  control that cannot do anything is worse than an explanation of its absence.
- **A sight cone is never drawn without its caption.** The sentence saying what
  the wedge is — the radar silhouette, not collision, 2D only — travels in the
  same document as the cells it is raycast against, so there is no state in
  which the page has one and not the other.
- **The 3D scene says it has no geometry.** The ground is Riot's radar image at
  one flat height and the heights are the players' own replicated z; there is
  no floor, wall or ceiling anywhere in this project, and on Split a player in
  heaven and one in the tunnel beneath sit above the same pixel.
- **Where `Track.at` refuses, nothing is drawn.** Not a last-known position, in
  either view. The refusal exists to stop a plausible coordinate being
  invented, and a fallback downstream of it would undo exactly that.

And one about arithmetic: `applyTransform` swaps the axes, world *y* into u.
That is measured, not assumed, and the unswapped form produces a plausible
wrong answer rather than an obvious one. `src/pages/transform.test.ts` pins it
on this side of the wire; `tests/test_vrfview.py` pins it on the other.

## Two test tiers, because jsdom cannot see a drawing

`npm test` is vitest under jsdom: the model ports against Python's fixtures,
and `MapStage.test.tsx` against every sentence the page says. It runs in three
seconds and needs no server, no `.vrf` and no `assets/`.

`npm run test:e2e` is Playwright against a real Chromium — `channel: "chromium"`
rather than the headless shell, because the shell's WebGL is not the browser's
and a scene that renders on a stack no user has proves nothing. It starts the
Python server and Vite itself, so it needs a populated `Demos/` and `assets/`,
and it is about pixels only:

| Spec | What it settles |
|---|---|
| `minimap.spec.ts` | Every player the model can place is drawn where it says, and **nothing else in a team colour is on the canvas** — the two-sided form, because an invented marker is the failure that looks plausible. The sight cone covers the polygon `sight.cone` computed and covers it better than the same cone rotated a quarter turn, which is the ninety-degrees-out bug as an assertion. Scrubbing forward past a round boundary and back is pixel-identical, because `stateAt` accumulates nothing. |
| `scene.spec.ts` | A camera built from `Scene3D`'s own constants projects every callout to within four pixels of where drei's `<Html>` put its label — so the projection below is the scene's and not a guess. Then the ground texture is correlated against the 2D minimap at the same uv points and against all three mirrored readings: **as-is 0.92, mirrored 0.07 / 0.33 / 0.18.** That is the "is the plane flipped" question the `CALLOUTS` layer was added for, answered by arithmetic instead of by eye. Also: a marker for every player the camera frames, and a player above the plane drawn at the height `vertical_scale` predicts. |
| `gallery.spec.ts` | Renders each view a quarter of the way into a match and saves it. It asserts almost nothing on purpose — whether a marker is a readable size and whether a round's utility is legible are judgements, and encoding one as a threshold would be inventing a standard rather than applying one. |

Two mechanics are worth knowing before editing them. **The page decodes its own
screenshots** — a WebGL canvas cannot be read with `getImageData` and
`toDataURL` on one is blank without `preserveDrawingBuffer`, which would be a
production setting existing only for tests; so a canvas is screenshotted and
handed back in as a data URL for a 2D context to decode. And **the playhead is
stepped, never guessed**: the store starts paused at zero and `>>` seeks to the
next `Replay.event_times` entry, so N presses land on exactly `event_times[N-1]`
and a test can compute where everybody should be and then look there.

This tier found a real defect on its first run. `floorZ` took the raw minimum z,
the replication stream parks an out-of-play actor about 50,000 uu below the map,
and so **four of the twenty-one playable captures drew no players at all in 3D**
— every marker lifted three and a half map-widths out of frame while the ground
rendered perfectly underneath. It read as a quiet map rather than as a fault,
which is exactly why a screenshot review would not have caught it.

## The model, and why there are two of them

`src/model/` is a port of `libraries/vrfview/model.py`, `state.py`, `clock.py`,
`art.Transform` and `sight.py`. It exists because `state_at` costs 0.127 ms on
a 199,180-sample replay and a round trip to the server does not — a frame's
worth of work is ten binary searches, and asking for it over HTTP would be
three orders of magnitude slower than doing it.

Two implementations of one set of rules is a liability, so it is held to a
contract rather than to discipline. `scripts/make_golden.py` builds one
synthetic `Replay` and writes `tests/golden/`: the wire replay, its columnar
tracks, every branch of `Track.at`, forty-four snapshots, the Abyss transform,
a raycast cone and a scripted playback session. `tests/test_golden.py` asserts
**Python** still reproduces those files byte for byte, and
`src/model/__tests__/parity.test.ts` asserts **TypeScript** computes the same
values. A Python change that would break this page fails in Python's own CI
first.

Everything is compared **exactly** — never `toBeCloseTo`, never `Math.fround`.
Both languages are IEEE-754 doubles and `JSON.parse` recovers exactly the
double `json.dumps` wrote, so a tolerance would hide precisely the class of bug
this is for. Three corrections were needed to earn that, each commented where
it lives:

- `((a % n) + n) % n` gives JavaScript Python's *sign* and the wrong *value* —
  three roundings where CPython does one, so `9.8` comes back as
  `9.800000000000011`. `model/angles.ts` ports CPython's `float_rem`.
- `math.radians` multiplies by a stored `pi / 180`; `(x * Math.PI) / 180` does
  not, and a last-bit difference in an angle stops a marched ray a whole cell
  earlier.
- `hypot` is *approximate by specification* in both languages and implemented
  differently in each, so `sight.forward_uv` uses `sqrt`. That one changed the
  Python.

The single exception is `atan2`, `cos` and `sin`, which are approximate in both
by specification. So `sight.ray_directions` is written into `cone.json` beside
every polygon: the parity test compares the directions within a bound, then
marches *Python's own* directions through `march`, which is plain arithmetic
and matches to the bit. The occlusion a cone actually depends on — which cell
stopped which ray — is therefore exact.
