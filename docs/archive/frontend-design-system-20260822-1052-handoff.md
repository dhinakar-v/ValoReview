# Frontend design system — handoff

**22 Aug 2026 · branch `vd-develop` · `E:\Personal\val-replay-analyzer`**

The session reworked `web/` from a functional debug harness into an analytics-tool interface: an
SVG icon pack, a layered colour ramp, self-hosted webfonts, synthesised UI sounds, keyboard
shortcuts, and a persistent app frame. **All work is uncommitted.** Everything below is on disk,
green, and unstaged.

---

## Read these first

| Path | What it is | Why it matters |
|---|---|---|
| `C:\Users\Dhina\.claude\plans\rework-the-frontend-design-ticklish-codd.md` | The approved plan for this work, with the full hard-constraints table | The single most useful file. Its "Hard constraints" section is the map of what will break the suite. |
| `CLAUDE.md` — three new paragraphs after the **Browser — `web/`** section | Design-system ownership, the icon-beside-label rule, the sound module contract | Now the canonical statement; do not re-derive from the plan. |
| `web/README.md` — §Colours, §Typefaces, §Icons, §Sound, §Keys | Per-decision reasoning, and the dependency table | The web-facing version of the same, with the pixel-test constraints on team colours spelled out. |
| `web/src/tokens.css` header | Why non-colour tokens are hand-written and not generated from Python | Answers the obvious "why isn't this in `theme.py` too". |
| `web/src/views/icons.tsx` header | The `aria-hidden`-applied-centrally rule and its justification | Read before touching any control. |
| `docs/map-viewers-20260822-0857-handoff.md` | The immediately preceding session | Context on the two map views this session restyled but did not change. |

---

## State

**Done and verified green.** Python 565 passed / 10 skipped; `runners\lint.bat` clean;
`runners\make-theme.bat --check` current; `npx tsc --noEmit` clean; vitest **153 passed**
(139 before, plus 14 new); `npm run build` clean; **Playwright 9/9 passed** with **no e2e spec
edited** — which was the plan's own signal that no constraint was broken.

Uncommitted, in three groups:

- **New files** — `web/src/tokens.css`, `web/src/fonts.css`, `web/src/fonts/` (4 woff2 +
  `OFL.txt`), `web/public/favicon.svg`, `web/src/views/{icons.tsx, ui.tsx, sound.ts,
  AppFrame.tsx, shortcuts.ts, ui.test.tsx, sound.test.ts}`.
- **Modified** — `libraries/vrfview/theme.py`, `scripts/make_theme.py`,
  `web/src/theme.generated.css` (regenerated, never hand-edited), `web/src/app.css` (full
  rewrite), `index.html`, `main.tsx`, all three pages, `views/{Shell, images, MapStage,
  Transport, MinimapCanvas, Scene3D}`, `package.json` (+`lucide-react`), and the three doc files.
- **Untouched by design** — `web/src/model/**`, `web/src/api/**`, `libraries/vrfserve/**`,
  `tests/golden/**`, `web/e2e/**`.

**Half-done: the accessibility pass.** The `web-design-guidelines` skill was run and its findings
gathered, but **none of the fixes were applied** — the session was interrupted at that point. The
findings are listed under *Next steps* and are the first thing to do.

---

## Decisions made

**The colour ramp replaced the brief's five flat greys, in place, without renaming anything.**
`APP_BG` → `#0a0b0d`, `CARD_BG` → `#101216`, `CARD_HOVER` → `#171a20`, `BORDER` → `#262b34`,
`TEXT_PRIMARY` → `#e8eaed`, `TEXT_MUTED` → `#7b7b7b` → `#a2a9b4`, plus four new constants
(`FIELD_BG`, `LINE_STRONG`, `TEXT_FAINT`, `ACCENT_WARN`). Retuning values rather than introducing
new names is what let `palette()` in `images.ts`, the CustomTkinter pages, and `e2e/harness.ts`'s
runtime `getComputedStyle` reader all keep working untouched. `theme.py`'s two palettes (page and
Tk canvas) were unified onto the one ramp — **the desktop app inherits the new look**, which was
intended and is values-only, so no CTk module needed editing.

**`--team-a` and `--team-b` were left exactly as they were.** They are pixel-tested from two
directions and moving either would fail both suites. This is written into `CLAUDE.md` and
`web/README.md`.

**Non-colour tokens are hand-written, not generated.** `theme.py` is a palette; Tk geometry is not
CSS geometry, so there is no Python counterpart for a spacing scale to drift from. `tokens.css`
holds space/radius/type/elevation/motion/stacking and contains **no hex** — elevation shadows use
`color-mix(in srgb, black N%, transparent)` so the "no hex outside the generated file" rule stays
literally true.

**Fonts are bundled, reversing the previous decision.** The old stacks named Tungsten and DIN Next
with nothing behind them, so every machine actually rendered Impact and Arial. Four woff2, 124 KB,
latin subset, referenced by relative `url()` from `fonts.css` so Vite fingerprints them into
`dist/static/` — deliberately not `web/public/`, which would land them at a path near the server's
`/assets` mount. Inter and JetBrains Mono are **variable** builds (one file each covers every
weight); Barlow Condensed is static and needs 600 and 700 separately.

**Icons sit beside labels, never instead of them.** There is no `data-testid` anywhere in the repo,
so seven control labels, two `title` attributes and five class names are an effective public API.
`aria-hidden`/`focusable={false}` are applied centrally in `icons.tsx::Icon`, and `ui.tsx` takes
`label` as a **`string`** rather than a `ReactNode` specifically so no caller can split one across
nodes. `ui.test.tsx` is the standing check.

**Sound is synthesised, off by default, and has its own store.** Six voices from oscillators and
gain envelopes — no audio assets whose licence would need tracking. Its zustand store is separate
from `usePlayback` because `MapStage.test.tsx` writes to that store directly and a sound preference
has no business being reset by a caption test. The `AudioContext` is built lazily on the first
sound played *while enabled*, which is why no page test needs a WebAudio mock under jsdom.

**The stage canvas is bounded by viewport height, not just column width.** `width: min(100%,
max(320px, calc(100vh - 380px)))`. A square as wide as the 1440px layout is taller than the screen,
and it put the transport bar below the fold on the one page where the map is the point. Verified by
screenshot before and after.

**No new filters on the match list.** The server offers `playable_only`, `map_name` and `page`; a
client-side search box would filter one page of ten and report a count that is wrong about a
library of 101.

---

## What did not work

**A `cat > file <<'EOF'` heredoc failed for the large `app.css` rewrite** with
``unexpected EOF while looking for matching `'`` — bash parsed a quote inside the body despite the
quoted delimiter, and **the file was silently not written** (the old 435-line version stayed on
disk and `grep -c ""` was what caught it). Use the `Write` tool for large files with prose comments;
`python - <<'PYEOF'` with `pathlib` replacements worked reliably for every targeted edit.

**Icons inside caption paragraphs were the one real risk to the test suite, and they were safe** —
but only because of a mechanic worth knowing rather than rediscovering: Testing Library's
`getNodeText` joins only an element's **direct text-node children**, not all descendants. So
`<p><svg/><span>{caption}</span></p>` matches on the `<span>` alone and does not produce a
"found multiple elements" error. Playwright's text engine independently resolves to the smallest
matching element. Both were confirmed by running the suites, not by reasoning.

**Empty card thumbnails on the match-list screenshot were a false alarm.** Probing with Playwright
showed `naturalWidth: 456`, `complete: true`, and a correct 200×52 bounding box — the listview art
simply reads as dark at full-page scale. A close-up screenshot of a single `a.card` confirmed it.
Do not go looking for a bug there.

**`Panel` drops its `actions` when given no `title`** — the `panel-head` div is only rendered when
`title !== undefined`. This bit once (the score chip vanished from the Timeline panel) and was
fixed by giving that panel a title. It is still the component's behaviour.

**The initial sound-toggle wiring made turning sound *on* silent** — `IconButton` played its
feedback before calling `onClick`, and `play()` is a no-op while the store still says off. Fixed
with a `silent` prop plus an explicit `play()` after `toggle()` in `AppFrame`.

---

## Environment facts

- `Demos/` holds **101 captures** and `assets/maps/` is populated, so **the Playwright suite can
  actually run here** — that is not true of a clean checkout and it is the only tier that can see
  what the page draws. `npx playwright test` takes ~2–4 min; it starts the Python server and Vite
  itself.
- The **Bash tool's working directory persists between calls**, and several commands silently ran
  from the wrong directory (`npx tsc` from the repo root installed a bogus `tsc@2.0.4` package).
  Prefix with `cd /e/Personal/val-replay-analyzer/web &&` every time.
- **jsdom's `localStorage` is unreliable under this vitest config** — it warns
  ``--localstorage-file` was provided without a valid path`` and hands back an object with no
  `getItem`. `sound.test.ts` stubs an in-memory storage rather than depending on it.
- Google Fonts is reachable from this machine; the latin-subset woff2 URLs come from
  `https://fonts.googleapis.com/css2?family=...` fetched **with a Chrome User-Agent** (without one
  it serves TTF). Inter and JetBrains Mono return byte-identical files for every weight because
  they are variable builds — verified with `md5sum` before deduplicating.
- `tests/test_theme.py` has two traps beyond the byte comparison: the generated CSS must still
  contain the phrase `not recoverable`, and must **not** contain the three-letter abbreviation the
  brief uses for the attacking side (checked case-insensitively over the whole file). Comments in
  `theme.py` and `make_theme.py` were written to avoid it.
- `lucide-react` resolved to `^1.33.0`, ISC, *Copyright (c) 2026 Lucide Icons and Contributors* —
  verified from `node_modules/lucide-react/LICENSE`, not assumed.

---

## Open questions

**Nothing blocks progress.** Two things are worth a decision from the user rather than a guess:

- **The desktop CustomTkinter app now renders in the new palette and nobody has looked at it.** The
  change is values-only and its tests are import/headless checks, so nothing failed — but the
  visual result is unverified. Since `CLAUDE.md` says the web interface is replacing it, "leave it"
  is a defensible answer; confirm rather than assume.
- **Whether the `--rail-w` 380px provenance rail should be collapsible.** It scrolls inside itself
  now, which was the main complaint, but it is still the widest single claim on the page.

---

## Next steps

**Apply the accessibility findings from the `web-design-guidelines` review, then commit.** The
review ran against the guidelines at
`https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`; these are
the findings that survived checking against the actual code:

1. **`ui.tsx::Field` leaves its `<select>` with no accessible name** — the real bug in the set.
   `<label className="field" aria-label="Filter by map">` names the *label element*, and a label
   names a wrapped control by its **text content**, of which there is none (the only child is an
   `aria-hidden` icon). Fix by rendering a visually-hidden `<span>{label}</span>` inside the label
   and adding an `.sr-only` class. Used by the match-list map filter.
2. **`ui.tsx::Tabs` claims `role="tablist"`/`role="tab"` without the keyboard pattern** — no
   `aria-controls`, no `role="tabpanel"`, no roving `tabIndex`, no arrow keys. Either implement it
   (~15 lines) or drop the roles for plain `aria-pressed` buttons. Implementing it is the right
   call for this interface.
3. **No `color-scheme: dark`** on `:root` — native scrollbars and `<select>` popups render light on
   Windows. Add it, and give `option` an explicit `background-color`/`color`.
4. **`<img>` without explicit `width`/`height`** at `pages/Viewer.tsx:64` (player portrait),
   `pages/MatchList.tsx:43` (card thumb) and `pages/MapReference.tsx:116` (radar) — CLS. CSS sizes
   them; the attributes are still wanted.
5. **Missing** `touch-action: manipulation`, `-webkit-tap-highlight-color`,
   `overscroll-behavior: contain` on `.page-body`/`.rail`/`.scroll-y`, and `text-wrap: balance` on
   headings.
6. **No skip link** to `<main>`, and the decode region has no `aria-live="polite"` for its async
   result.

Not findings: `transition:` lists its properties explicitly in both places, focus-visible rings are
present throughout, ellipses are the `…` character, `tabular-nums` is set, and the lists are all
under 60 rows.

First command:

```bash
cd /e/Personal/val-replay-analyzer/web && npx vitest run
```

Then after the fixes, the full gate — Python first because the theme check lives there:

```bash
runners\make-theme.bat --check && runners\test.bat && runners\lint.bat
cd web && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test
```

---

## Cautions

- **Never hand-edit `web/src/theme.generated.css`.** `tests/test_theme.py` compares it byte for
  byte. Colours change in `libraries/vrfview/theme.py`; a *new* token also needs a row in
  `scripts/make_theme.py::COLOURS`; then `runners\make-theme.bat`.
- **Do not touch `web/src/model/**`** — pinned exactly against `tests/golden/` by `parity.test.ts`.
- **Do not change `Scene3D`'s `CAMERA`, `BODY_HEIGHT`, `SIGHT_LIFT` or `GRID`.** They are
  deliberately duplicated in `e2e/scene.spec.ts` so a change fails that spec; materials and colours
  only. This session changed only the material colour and the callout label style.
- **Keep `assetsDir: "static"`** in `vite.config.ts`, in lockstep with `SPA_ASSETS = "static"` in
  `libraries/vrfserve/app.py`. `/assets` belongs to Riot's art and is mounted first, so a bundle
  there is shadowed and every JS request 404s while `index.html` still serves.
- **If an e2e spec needs editing, treat it as a signal that a constraint was broken**, not as the
  fix. All 9 passed twice without edits.
- Screenshots under `web/e2e/results/` are generated output; `web/e2e/shots*` scratch specs were
  already deleted.

---

## Suggested skills

- **`code-review`** — first, before committing. This is ~2,500 lines of new and rewritten UI code
  that no reviewer has seen, and the accessibility fixes above will add more. Run it after applying
  them, at `high`.
- **`commit`** — last. Thirty-one paths are unstaged and they split cleanly into logical commits:
  the palette (`theme.py`, `make_theme.py`, the regenerated CSS), the token/font foundation, the
  icon and component primitives, sound and shortcuts, the page rework, and the docs. Do not squash
  them into one.

Not useful here: `init` (`CLAUDE.md` exists and was updated this session); `handoff` (this is it);
`web-design-guidelines` (already run — its findings are transcribed above, so re-running it before
applying them wastes a turn).

---

## Sensitive material

`.env` in the repo root holds `DEMO_PATH` and may hold `<RIOT_API_KEY>`; it is gitignored and was
not read or modified. Nothing in this session touched credentials. Note for anyone quoting
screenshots or provenance output: replay filenames and match ids are UUIDs identifying real
matches — `40d2242e-…` appears in the viewer footer — and `Demos/` is gitignored for that reason.
Do not copy them into public issues.
