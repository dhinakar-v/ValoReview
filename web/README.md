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
| `react-router-dom` | Real URLs. `/replay/<id>` is an address a reader can keep, share and reload; a page that routed in component state would put every capture behind the same URL and lose the back button with it. |
| `@tanstack/react-query` | Fetch state. Refetch-on-focus is off: a local server reading files off a disk does not go stale on its own. It also owns the decode mutation, which replaces the whole replay rather than patching the tracks. |
| `zustand` | The playhead, the view mode and the layer toggles, shared by three components that are not each other's children. Lifting them into the page would re-render the roster and the round table sixty times a second; the canvas and the scene subscribe to nothing at all and read `getState()` inside their own animation frame. |
| `three` | The 3D scene. There is no smaller way to put a textured plane and ten markers in a perspective camera, and writing WebGL by hand to avoid a dependency would be a much larger thing to maintain than the dependency. |
| `@react-three/fiber` | `three` as React components, so the scene's lifetime is the component's and `useFrame` is the per-frame hook. The alternative is a manual renderer, a manual resize observer and a manual teardown, all of which this already gets right. |
| `@react-three/drei` | `OrbitControls` and `Html`. Orbit is a camera rig everybody writes the same way and nobody writes correctly the first time; `Html` is what puts a callout label in the scene without a text-geometry pipeline. |
| `lucide-react` | The icon set. Every control used to be a bare uppercase word and the transport bar was ASCII -- `|<`, `<<`, `PLAY`. Drawing twenty-four glyphs by hand would be twenty-four paths to maintain and a set that stops the day somebody needs a twenty-fifth; the package is MIT, tree-shaken to what is imported, and one consistent grid. It is wrapped in `views/icons.tsx` rather than imported directly -- see *Icons, and the rule that makes them safe*. |

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

There is no UI kit, no CSS framework, no CSS-in-JS and no charting library.
The stylesheet is three files and they have three different owners:

| File | Written by | Holds |
|---|---|---|
| `src/tokens.css` | by hand | space, radius, type scale, elevation, motion, stacking. **No colour.** |
| `src/theme.generated.css` | `scripts/make_theme.py` | every colour, and the argument for the ones that carry one. **Generated -- never edit it.** |
| `src/fonts.css` | by hand | the four bundled `@font-face` declarations. |

`src/app.css` imports the three and is the layout. The split is the point:
colours round-trip through Python because the desktop app and the canvases
share them and the palette carries an argument, while a spacing scale has no
Python counterpart to drift from -- Tk geometry is not CSS geometry.

Tokens rather than literals because the sheet they replaced had paddings at 2,
4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 24 and 28 pixels. A scale nobody can
hold in their head is a scale that gets bypassed.

## Colours

`src/theme.generated.css` is written by `scripts/make_theme.py` from
`libraries/vrfview/theme.py` — **do not edit it, and do not put a hex value
anywhere else.** `tests/test_theme.py` fails if the committed file has gone
stale.

The palette carries an argument, which is why it is generated rather than
copied. The brief names its red for the attacking side and its blue for the
defending one; this project does not adopt those meanings, because which team
attacked is not recoverable from a replay — spike events carry no actor id.
The hues are the brief's, the labels say A and B, and the reasoning lives
beside the constants in `theme.py` where anyone changing them will read it.

The surfaces are a ramp — `--app-bg`, `--card-bg`, `--card-hover`,
`--field-bg` — and the text is three weights down from `--text-primary`. The
brief named five flat greys, and an interface built from five has nowhere to
put the states it actually has: a panel raised above a page, a row hovered
inside it, an input sunk below it, a divider that has to read as stronger than
a hairline. Every one of those was the same value, which is why the old page
read flat.

Two constraints on anyone changing this:

* **`--team-a` and `--team-b` are pixel-tested.** `minimap.spec.ts` counts a
  pixel as a marker within 36 RGB of a team colour and needs the radar's own
  greys to stay outside that; `scene.spec.ts` identifies markers by hue after
  3D lighting (`b - r > 40` for A, `r - b > 40` for B). Moving either toward
  grey, or toward the other, fails both.
* **`tests/test_theme.py` compares the generated file byte for byte**, checks
  the emitted header still contains *not recoverable*, and asserts the CSS
  never contains the substring the brief uses for the attacking side. Adding a
  colour means a constant in `theme.py`, a row in `make_theme.py::COLOURS`, and
  `runners\make-theme.bat`.

`views/images.ts::palette()` reads the tokens back out with `getComputedStyle`,
because a canvas cannot use a custom property. Its fallback hexes are the one
place a colour is written twice, and they are a hazard worth knowing: a
fallback fires silently, so a renamed token does not break the canvas — it
quietly draws in last season's colours.

## Typefaces, and why they are bundled now

Three families, four `woff2` files, 103KB, latin subset, in `src/fonts/`.
Barlow Condensed 600/700 for headings, Plus Jakarta Sans for everything that is
a sentence or a label, JetBrains Mono for anything that has to line up in a
column.

The UI face was Inter, which is a good face and the wrong one to have reached
for: it is the default a decade of interfaces already picked, so a tool set in
it reads as unstyled rather than as neutral. Plus Jakarta Sans is the same shape
of decision with a taller x-height, which is what keeps the 11px and 12px labels
this interface is full of legible at the density they are set -- and it is 27KB
against Inter's 48KB.

They used to be stacks with no files behind them -- Tungsten falling back to
Impact, DIN Next falling back to Arial -- on the argument that shipping a
webfont for a heading was a poor trade for a local app. The trade changed when
the fallbacks turned out to be what every machine actually rendered: the
interface was Impact and Arial, not the brief's faces, and an analytics tool
that renders in Impact reads as an accident.

Bundled rather than linked, for the same reason nothing else here reaches the
network: this page is served by a local Python process against files on a disk
and is expected to work offline. A Google Fonts `<link>` would render the
fallbacks with no connection and then reflow the page when there was one.
Plus Jakarta Sans and JetBrains Mono are the variable builds, so one file each
covers every weight. All three are SIL OFL 1.1 -- `src/fonts/OFL.txt` and `THIRD_PARTY.md`.

The old stacks survive as the fallback tail, so a checkout with the font files
stripped still looks deliberate rather than broken.

## Icons, and the rule that makes them safe

`views/icons.tsx` wraps `lucide-react`, and the wrapper exists for one reason:
**an icon never replaces a label.**

There is not one `data-testid` in this repository. Every DOM assertion is text,
ARIA role-name, class or `title` -- `findByText("SIGHT")`,
`getByRole("button", { name: "TRAILS", exact: true })`,
`getByTitle("Next event")`. So `2D`, `3D`, `UTILITY`, `TRAILS`, `SIGHT`,
`CALLOUTS` and `DECODE POSITIONS` are an interface other files depend on, and
an icon inside a button is exactly the change that would rename them without
any file that mentions them being edited.

Hence `aria-hidden` and `focusable={false}` are set centrally in `Icon` rather
than at each call site, the label is always its own text node beside the glyph,
and the one control with no words -- the sound toggle -- carries an
`aria-label`. `views/ui.test.tsx` is the standing check on all of it.

The wordmark and the favicon are inline `<svg>` and a file, never an `<img>`:
`MatchList.test.tsx` asserts `container.querySelector("img")` is null over the
whole page in the no-thumbnail state, so a logo that happened to be an `<img>`
would fail a test about map art.

## Sound

`views/sound.ts`, six voices, synthesised from oscillators and gain envelopes.
No audio files and no dependency: a sampled set would be six binaries whose
provenance and licence would need tracking the way the fonts' does, in exchange
for warmth this interface has no use for. What it needs is confirmation -- a
press landed, a decode finished, a request failed -- and a 20ms envelope says
that as well as a recording does.

Three things about it are pinned by `views/sound.test.ts`:

* **off by default**, remembered in `localStorage`, toggled from the app bar.
  An analytics tool that beeps before it was asked to is a defect report;
* **no `AudioContext` until one is needed** -- built on the first sound played
  while enabled, never at import, which is why no page test needs a mock;
* **`prefers-reduced-motion` wins.** The stylesheet zeroes its transitions on
  the same query. A sound is the one thing here that can be dropped without
  changing what anything says.

## Reach, and the two roles that were a promise rather than a label

Everything under this heading is a fix, not a policy statement: each item was a
real defect found by reading the code against the Web Interface Guidelines.

**A `<label>` names its control by its text content, not by its `aria-label`.**
`ui.Field` wraps a `<select>` in a `<label>` whose only other child is an
`aria-hidden` glyph, and set `aria-label` on the label element -- which names
the label and leaves the control anonymous. The match list's map filter
therefore reached a screen reader as an unnamed combo box reading out whichever
option was selected. It now renders a real text node in an `.sr-only` span:
clipped to a 1px box rather than `display: none` or `visibility: hidden`, both
of which take an element back *out* of the accessibility tree, which is the
thing being fixed.

**`role="tablist"` is a contract.** A reader that sees those roles tells the
user to arrow between the tabs, announces "1 of 2", and looks for the panel
each tab controls. `ui.Tabs` claimed all three and implemented none, which is
worse than plain buttons because the instructions it puts in somebody's ear are
wrong. It now has a roving `tabIndex` (one tab stop for the strip, not one per
tab), arrow keys with Home/End and wrapping, and `aria-controls` pointing at a
`ui.TabPanel` that names the tab back. Selection follows focus, which is the
right pattern here because both panels are already in hand -- there is nothing
to fetch, so nothing makes an arrow key expensive.

The two ids they agree on are derived from the tab's own id rather than from
`useId`, because the strip and its panel are rendered by two different
components -- the caller decides what goes in the panel, which is the point --
and a generated id cannot cross that boundary without a context for one string.
Tab ids are unique within a page by construction: they are what `active` is
compared against.

**`color-scheme: dark`.** Scrollbars, `<select>` popups, the caret and the ring
inside a form control are painted by the platform, and on Windows the platform
paints them light unless told otherwise. It is not a colour and so is not in
the generated palette; it names which of the browser's own two themes to use.
`option` gets an explicit background too, because the rows inside a popup still
inherit from the page on some platforms.

**A skip link that moves the focus, not just the scroll.** `AppFrame` renders
it first in the DOM, hidden until focused. Reaching the map from the keyboard
was seven presses on every navigation -- brand, breadcrumb, decoder light,
sound, and three more in the viewer's page head. `Shell.Page`'s `<main>` takes
`id="main"` and `tabIndex={-1}` so the link lands the focus there; a link that
only scrolls leaves the focus in the bar, so the next Tab returns to the first
thing it was meant to skip.

**The decode region is `aria-live="polite"`.** A decode takes about four
seconds and reports itself only by changing a button's own words; without the
live region its failure is a sentence that appears in silence. Polite rather
than assertive: it is the result of something the user just pressed.

Smaller, and each for a stated reason in `app.css`: `touch-action:
manipulation` on the interactive set (no 300ms wait before a press registers on
a control that is pressed in sequence), `-webkit-tap-highlight-color:
transparent` (the hover and active states already say a press landed),
`overscroll-behavior: contain` on the regions that scroll inside themselves (a
table dragging the page under it is how the row you were reading gets lost),
`text-wrap: balance` on headings, and explicit
`width`/`height` on all three `<img>` elements.

Those dimensions are measured, not assumed. Every published `minimap.png` is
1024 square and every `listview.png` 456x100, checked across the asset cache;
the card thumbnail states the 200x52 box its CSS already reserves rather than
the file's own size, because `object-fit: cover` reconciles the two and what
the attributes are for is holding the row's height before the picture arrives.
The player portrait states its 28x28 box for the same reason and because
`icon.png` is 512 square for one agent and 1024 for the other twenty-eight.

`views/ui.test.tsx` is the standing check on the first two, which are the two
that can regress silently.

## Keys

`views/shortcuts.ts`. Every binding calls the same function the button beside
it calls -- a key is a faster way to press a control, never a second
implementation of what it meant. A shortcut that seeked by its own arithmetic
would drift from `Replay.event_times` the first time the server's list changed.

Two things follow from that rule and both were bugs before they were rules.

**The listener is on the `window`, so it asks the focused element first.** That
is what makes the bindings work wherever you are on the page, and it is also
why a widget calling `preventDefault` does not stop them -- a window listener
runs afterwards regardless. `ownsKey` is the guard: Space belongs to a focused
`<button>` (taking it left Enter as the only way to work every layer switch on
the page, for as long as a stage was mounted), and the arrow keys with Home/End
belong to a `role="tablist"` (ArrowRight in the timeline's strip changed the tab
*and* stepped the playhead; Home jumped to Rounds *and* seeked to zero).

**A key exists exactly where its control does.** `MapStage` draws SIGHT only
where there is a mask and CALLOUTS only in 3D, so `useTransportKeys` is handed
the same two booleans. Without them `S` on a map with no mask set `showSight`
with no effect and no caption -- and because the store is module-level, the
next replay opened in the same session came up with the layer already on.

`views/shortcuts.test.tsx` is the standing check on all three, and each
assertion was confirmed to fail against the code it fixes.

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

- **The list is captures whose build has a payload transform, and only those.**
  The filter is `/api/library`'s own and there is no request that turns it off:
  a build with no transform has no positions to decode and no schematic to fall
  back to, so there is nothing behind such a card to open. What is on the disk
  beyond that is not stated anywhere in the interface.
- **A capture that will not parse is still listed, carrying its error.** A file
  the scanner could not read is a fact about the library, and dropping it
  silently is the failure that looks like nothing happening.
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
