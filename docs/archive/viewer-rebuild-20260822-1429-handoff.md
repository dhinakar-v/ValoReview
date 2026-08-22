# Replay viewer rebuild — handoff

**22 Aug 2026 · branch `vd-develop` · `E:\Personal\val-replay-analyzer`**

The session rebuilt the browser replay viewer against six reference frames of a commercial
VALORANT VOD tool (`images/`). Flat and square instead of bezelled and rounded; edge-to-edge
instead of a bounded column; playback and clock scoped to a **round**; roster cards with real
agent, ability and weapon art; a kill toast, a hover card, a layers menu, a round-timeline modal,
2D zoom/pan, and a triangular facing marker.

**All work is uncommitted.** Everything is on disk. One Playwright test is failing and is the
next agent's first job — see *Open questions*.

---

## Read these first

| Path | What it is | Why it matters |
|---|---|---|
| `C:\Users\Dhina\.claude\plans\can-you-create-a-iridescent-metcalfe.md` | The approved plan | Written against the user's fourteen numbered instructions. Its §12 file table and *Names that cannot be renamed* section are the map of what breaks the suite. |
| `images/README-ui-reference.md` | The reference UI, read off the pixels | The spec being implemented. **Two errata** — see *Decisions made*. |
| `CLAUDE.md` — the **Browser — `web/`** block and the six paragraphs after it | Updated this session | Now the canonical statement on the flat pass, the arena layout, the generated values, the layers menu and round-scoped playback. Do not re-derive from the plan. |
| `web/README.md` — §Icons, §What came out, §Reach | Updated this session | The web-facing version of the same. |
| `web/src/model/synthetic.ts` header | Why fabricated values are allowed here and the three rules that contain them | Read before touching anything that shows a number. |
| `docs/frontend-design-system-20260822-1052-handoff.md` | The preceding session | Built the bezel and the sound module that this session deliberately removed. |

---

## State

**Green:** Python `559 passed / 10 skipped`; `ruff check` clean; `ruff format` clean;
`make-theme.bat` regenerated and current; `make_golden.py` regenerated (a wire field was added, so
`tests/golden/replay.json` legitimately changed); `npx tsc --noEmit` clean; vitest **190 passed**
(154 before this session's three new model suites); `npm run build` clean.

**Playwright: 21 of 22 passing.** The one failure is
`e2e/minimap.spec.ts:224 "scrubbing backwards lands on exactly the same frame"` — it reports
**exactly 5017 differing pixels**, the same number across four separate runs. See *Open questions*;
this is the single outstanding item.

**New files** (all untracked): `web/src/model/{viewport,roundclock,synthetic}.ts`,
`web/src/model/__tests__/{viewport,roundclock,synthetic}.test.ts`,
`web/src/views/{RosterPanel,KillToast,MarkerTip,ClockPill,RoundStrip,LayersMenu,RoundTimeline}.tsx`,
`web/src/views/{catalogue,live}.ts`, `web/e2e/review.spec.ts`.

**Deleted:** `web/src/views/sound.ts`, `web/src/views/sound.test.ts`.

**Server side is finished and green.** A tenth route `GET /api/weapons`, `PlayerDoc.abilities`,
`art.WeaponArt`, and a `weapons` group in `scripts/fetch_assets.py`. Weapon art has already been
fetched to `assets/weapons/` (20 weapons × 2 icons) on this machine — `assets/` is gitignored, so a
fresh checkout needs `runners\fetch-assets.bat fetch --only weapons`.

**Untouched:** the desktop CustomTkinter interface, `vrfnet`, the C# decoder, `vrfhome`.

---

## Decisions made

**Missing values are generated, and the user chose that.** I flagged in conversation that this
codebase's stated rule is that the interface never makes a claim the file cannot support
(`provenance.ABSENT`, `RESULT_NOT_IN_FILE`), and that synthetic health looks identical to decoded
health in a screenshot. The user reaffirmed. The containment is: one module (`model/synthetic.ts`),
deterministic (xorshift seeded on match id + actor + round — a Playwright suite cannot photograph
noise), driven by real events wherever any exist, and marked on screen by a `SIMULATED` chip plus
the full sentence in the captions block.

**Two things are still not generated, and this was my call rather than the user's.** No fabricated
**coordinates** — no ult orbs, no spike position on the map. Numbers on a card are one thing;
coordinates on a map are what the entire pixel suite exists to defend, and a fabricated map object
is indistinguishable from a decoded one. And no fabricated **player or org names** — cards read
`Sova`, not `T1 iZu`. If the user wants either, they are small additions, but say so explicitly.

**Two errata in `images/README-ui-reference.md`, followed rather than the doc.** The circled card
number is **armour, not ultimate points** (the `275` tooltip reads Health / Armor / Money, and
crazyguy goes `100 (25)` → `79 (0)`). The roving grey dot is the **mouse cursor, not the spike**
(in `038` it sits outside the map polygon; in `226` it is on the modal).

**Markers are coloured by side, not by team** (`images.sideColour`). `--team-a` is now attacker red
and `--team-b` defender blue. Every surface — roster header, card accent, kill-feed name, timeline
row, map marker — derives from the same two. Deriving from the *team* is consistent right up to the
halftime swap, at which point the cards change side and the markers do not. The swap instant is
real (`Replay.side_swap_ms`); which side is which is generated.

**The palette change was safe because both pixel specs read the vars off `document.body`** rather
than hard-coding them. One place did hard-code a hue and had to be fixed: `scene.spec.ts` asserted
`player.team === "A" ? blue : red`.

**Round bounds live in the driver and the loop in the transport, never in `PlaybackClock`.** That
class is a byte-for-byte port pinned by `tests/golden/clock.json` in two languages; a bound it does
not have in Python would break parity before it played anything twice.

**The countdown runs from `Round.duration_ms`, not a fixed 1:40.** A real round is a fixed timer
plus a spike timer; what a capture holds is when `roundStarted` fired and when the next one did.

**Layer switches moved into a `LAYERS` popover but kept their exact labels.** There are nine now.
`harness.toggleLayer` and a matching helper in `MapStage.test.tsx` open the menu first; no label
string changed.

---

## What did not work

**Bash heredocs mangle backticks.** `python - <<'PY'` with TypeScript/Markdown content containing
backticks fails with ``unexpected EOF while looking for matching ` `` — the quoted heredoc is not
being honoured in this harness. Cost several retries. **Write the patch script to a file with the
Write tool, then `python path/to/script.py`.** Scratch scripts from this session are in
`C:\Users\Dhina\AppData\Local\Temp\claude\E--Personal-val-replay-analyzer\2f121303-...\scratchpad\`
and are disposable.

**`loading="lazy"` on the roster's portraits and ability icons.** Ten local 10KB images that are on
screen from the first paint; the attribute bought nothing and made every screenshot catch a blank
card. Removed.

**`filter: invert(1)` on weapon and ability art.** Riot's `displayIcon`, `killStreamIcon` and
ability icons are already white — measured means of 197, 255 and 247 over their opaque pixels — so
inverting them drew black silhouettes on a black page: in the DOM, in the layout, visible to
nobody. Removed from `.card-weapon`, `.kill-weapon`, `.ev-weapon`.

**`killfeedIcon` is not a field on valorant-api's `/weapons`.** It is **`killStreamIcon`**. Guessing
the obvious name fetches nothing *and reports success*, because `_files_for` skips a field that is
not present — the first fetch wrote 20 files instead of 40 and said "20 weapons".

**Quantising the playhead and then taking the snapshot at the quantised value.** `useLiveSnapshot`
did `stateAt(model, floor(tMs/200)*200)`. Round one starts 63ms into the reference capture, so the
opening frame resolved to t=0, which is before any round: `Snapshot.round` null, `alive` empty, all
ten cards reading 0 HP and rendering as dead. Fixed — the quantised value is now only the
*subscription trigger* and the snapshot is taken at the real playhead.

**A clipped checkbox input cannot be clicked programmatically.** `clip-path: inset(50%)` keeps the
input in the accessibility tree but leaves a one-pixel target under the drawn box, so Playwright
reports `<span class="check-box"> intercepts pointer events`. Fixed by making the input cover the
whole row at `opacity: 0` (`display: none` and `visibility: hidden` would take it back out of the
tree).

**Hypotheses tried and ruled out for the remaining failure** — see below, so they are not retried.

---

## Environment facts

- `runners\test.bat`, `runners\lint.bat`, `runners\make-theme.bat`, `runners\make-golden.bat`,
  `runners\fetch-assets.bat`, `runners\vrf-serve.bat`. Python via `uv run`.
- `cd web && npm test` (vitest/jsdom), `npx tsc --noEmit -p tsconfig.json`,
  `npx playwright test` (starts its own Python + Vite servers, `reuseExistingServer` on).
- **Two Playwright runs must not overlap.** A second run started while the first is shutting down
  gets `ERR_CONNECTION_REFUSED at localhost:5173` on every test. Wait for one to finish.
- A full Playwright run is ~4.5 minutes; a single spec ~40s.
- Playwright output is **buffered until the process exits** when backgrounded — tailing the task
  output file mid-run returns nothing.
- `Demos/` holds 101 captures and `.cache/positions/` 21 decoded sidecars on this machine; both are
  gitignored. The suite opens the first playable card, so it needs them.
- `assets/` now includes `weapons/` — also gitignored.
- Adding a field to `PlayerDoc` changes `tests/golden/replay.json`; regenerate with
  `uv run python scripts/make_golden.py`, do not hand-edit.

---

## Open questions

**The one failing test, and it needs data rather than another hypothesis.**
`e2e/minimap.spec.ts:224` reports exactly **5017** differing pixels between two reads of the same
instant, stably across four runs. The clock readout matches on both reads (second resolution).

Ruled out already:

- *Image loading.* Added `waitForLoadState("networkidle")` plus a two-frame settle to
  `openFirstPlayable`. No change to the count.
- *A stray hover enlarging a marker to 3×* (about the right pixel count — a hovered roster card
  sets `hovered`, and closing the layers menu leaves the pointer over a card). Added
  `page.mouse.move(2, 2)` and a two-frame settle to `readCanvas`. **No change to the count**, which
  is what makes this suspicious: a stable 5017 is not a race.
- *Non-determinism in the model.* A throwaway diagnostic spec running the identical steps **in
  isolation reported `count 0`** — the frames were bit-identical. So the difference only appears
  when the test runs after the other three in `minimap.spec.ts`, each of which uses a fresh page.

That last fact is the lead. The next step is not another guess: re-create the diagnostic spec (it
was deleted; its shape is in this session's history — read both canvases, report count, bounding
box and six sample pixels) and **run it as a fourth test inside `minimap.spec.ts`** rather than
alone, so it reproduces. The bounding box will say immediately whether the difference is a marker,
an overlay (clock pill / kill toast, both of which are inside `.stage-canvas` and therefore inside
a Playwright element screenshot), or the radar itself.

A plausible remaining cause worth checking first: `firstCrowdedEvent` now returns `presses: 0` for
this capture (the readout was `0:00 / 2:12`), so the test is comparing two reads of *round one's
first millisecond* — where players are stacked in spawn and a single marker's draw order could
differ. Consider whether the moment the test picks is a good one.

**Whether the user wants the two deliberate omissions.** Fabricated orb/spike coordinates, and
fabricated player names. Both were my call, both are stated in `CLAUDE.md`, neither was asked for.

---

## Next steps

1. Reproduce and fix the failing spec:
   ```
   cd web && npx playwright test e2e/minimap.spec.ts --reporter=list
   ```
   Run the whole file, not the one test — it passes in isolation.
2. Re-run everything: `npx playwright test`, `npm test`, `runners\test.bat`, `runners\lint.bat`.
3. Look at `web/e2e/results/review/*.png` — twelve captured states from `review.spec.ts`. That spec
   is the standing visual check and already asserts no stray radius or shadow, no overlap between
   floating layers, equal gutters, and no clipped card text.
4. Commit. There is a lot here and it wants more than one commit — the server/asset work
   (`fetch_assets`, `art`, `wire`, `schema`, `app`, golden) is independent of the browser rebuild
   and lands cleanly on its own.

---

## Cautions

- **Do not hand-edit `web/src/theme.generated.css`** — it is written from `libraries/vrfview/theme.py`
  and `tests/test_theme.py` fails when it goes stale.
- **Do not rename** `2D`, `3D`, `UTILITY`, `TRAILS`, `SIGHT`, `CALLOUTS`, `DECODE POSITIONS`,
  `RESCAN`, `BACK`, `title="Next event"`, `title="Back to the start"`, `a.card`, `canvas.minimap`,
  `.clock-readout` (its text must be exactly `M:SS / M:SS`), `.stage-canvas` (exactly one canvas
  inside it), `.panel.stage`, or `.cap`.
- **Do not put a bound or a loop flag inside `PlaybackClock`** — cross-language parity.
- **Do not delete `web/src/model/viewport.ts`'s `FIT` identity guarantee.** `e2e/minimap.spec.ts`
  computes marker positions from `placeSquare` alone; that stays valid only because the default
  viewport is the *exact* identity, not something very close to it.
- Two Playwright runs at once will fail spuriously (see *Environment facts*).

---

## Suggested skills

- `code-review` — first. This is roughly 3,000 lines of new and rewritten frontend code across
  seventeen new files, written in one pass, with one known failing test. Run it before committing.
- `commit` — after the review and after the suite is green. Everything is uncommitted; this wants
  splitting into at least a server/asset commit and a browser-rebuild commit, and the repo's
  history is conventional-commits with no AI attribution.
- `run` — if you want to look at the interface by hand rather than through the screenshots
  (`runners\vrf-serve.bat`, then open a playable capture).

Not useful here: `init` (a thorough `CLAUDE.md` exists and was updated this session);
`handoff` (this document); `web-design-guidelines` and `high-end-visual-design` (the design
direction came from `images/` and fourteen explicit user instructions, not from generic guidance,
and re-deriving it would fight the reference).

---

## Sensitive material

Nothing in this document. Two notes for the next agent: `Demos/*.vrf` filenames are match UUIDs
and `Loadout.subject` values are player UUIDs — neither belongs in a commit message, an issue, or
a shared screenshot. `RIOT_API` is read through `libraries/envfile.py` from the nearest `.env` at
runtime and is not needed for any of this work: no command in this session opened a socket except
`fetch-assets`, which is unauthenticated.
