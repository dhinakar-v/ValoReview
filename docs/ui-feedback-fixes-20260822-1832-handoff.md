# UI feedback fixes — session handoff

**22 August 2026 · branch `vd-develop` · `E:\Personal\val-replay-analyzer`**

One session, working through all 23 items in `docs/ui-feedback.md`. Every item is implemented.
**Nothing is committed**, one e2e test is failing, and there is temporary debug instrumentation in
the tree that currently breaks `tsc`. Read *State* and *Next steps* before touching anything.

---

## Read these first

| What | Where | Why |
|---|---|---|
| The approved plan | `C:\Users\Dhina\.claude\plans\can-you-create-a-inherited-biscuit.md` | The full design for all 23 items, with per-item reasoning and the test constraints each must respect. Outside the repo. |
| The review being answered | `docs/ui-feedback.md` (untracked) | The 23 numbered items and the screenshot each came from. Screenshots are in `images/` (untracked). |
| The spike measurement | `docs/vrf-decoding-findings.md` § "The spike has a coordinate after all" | New this session. The evidence that `TimedBomb` spawns are the plant. |
| The durable record | `CLAUDE.md` | Updated this session in six places; the conventions it states are binding. |

Do not re-read the plan for *what changed* — the diff is the truth now, and the plan predates two
findings that overturned parts of it (see *What did not work*).

---

## State

**Everything is uncommitted.** 45 modified files, 5 new source files, plus untracked
`docs/ui-feedback.md` and `images/`. `git status --short` is the inventory.

All 23 review items are implemented, plus four live bugs the review did not name (the review's
items are 1.1–7.3; these four were found while working on them):

| # | Bug | Fixed in |
|---|---|---|
| i | `AbilityCast.actor_id` is the *ability actor's* id, so `sideAt(cast.actor_id, …)` resolved nobody and **every ability row in the round timeline was sideless** | `wire.py` ships `player_actor_id`; `RoundTimeline.tsx` uses it |
| ii | Ability markers used `teamColour`, so they did not swap at halftime while the players beside them did | `MinimapCanvas.drawAbilities` uses `sideColour` |
| iii | Spike rail ticks were drawn in `--team-b`, attributing a sideless event to a side | `Transport.tsx` `spikeColour()` |
| iv | `seek()` clamped only the *upper* round edge, so `,` at a round start walked into the previous round | `Transport.seekTo` uses `roundclock.clampToRound` (which had been dead code) |

### Green

- Python: **473 passed**, 9 skipped, 450 subtests. `runners\lint.bat` clean.
- Vitest: **205 passed** (before the debug instrumentation below).
- Playwright: **22/22 passed** on the last clean run, including the flat-and-square sweep and both
  pixel suites.

### Not green — deal with this first

1. **`web/e2e/minimap.spec.ts` has a failing new test**, `"draws the spike where it was planted"`.
   It is a real failure, not a flake: the spike marker is not appearing at the coordinate the model
   says it is at. Diagnosis so far is in *Next steps*.
2. **Debug instrumentation is in the tree and `tsc` fails on it.** Two places, both mine, both must
   be removed:
   - `web/src/views/MinimapCanvas.tsx` ~line 527 — a `window.__spikeDebug = {…}` assignment inside
     `drawSpike`.
   - `web/e2e/minimap.spec.ts` ~lines 305–335 — three `console.log` blocks (`SPIKEDEBUG`, `PROBE`,
     `DEBUG plant …`) and a `probes` loop. `npx tsc --noEmit` reports two errors here (a `window`
     cast and a possibly-null object); both are in this code and nowhere else.
3. **`web/src/model/__tests__/spikeloc.test.ts` is a scratch file** written to isolate the bug. Its
   three tests pass and they are genuinely useful (they pin `spikeLocation` before, at and after a
   plant). Either keep it and give it a proper docstring in the house style, or delete it — do not
   leave it as-is.
4. A stray `/tmp/spike.test.ts` was created early in debugging and never used. Outside the repo;
   delete if you care.

---

## Decisions made

### The four the user chose explicitly

| Question | Choice |
|---|---|
| Product name (2.1) | **VANTAGE**. `web/src/views/brand.ts` is the single constant; `web/index.html` is a documented second copy because static HTML cannot import it. |
| Ability range (4.1) | Research real radii from the wiki, ship as a sourced table, draw as **simulated**. |
| Used abilities (4.3) | **Synthetic charges for all four slots**, under the existing SIMULATED banner. |
| Spike location (1.4) | **Measure first**, draw only if ground truth passes. It passed overwhelmingly. |

### Derived during the work

**The spike coordinate is real and is now decoded.** Planting spawns a
`/Game/GameModes/Bomb/TimedBomb` actor whose transform `csharpdecode` has always carried and
`tracks.py` discarded (it kept only `/Game/Characters/`). Over 21 captures / 274 plants: counts
equal in every capture, 274 paired one-to-one, constant +8–15 ms offset, median 69.5 uu from a
player's own position, **274/274 inside the radar silhouette**. Full numbers in
`docs/vrf-decoding-findings.md` and in `tracks._plants_from`'s docstring.

**`--spike-armed` had to change colour, and that is a correctness fix rather than taste.** It was
`#ff5252`, which is **12 RGB** from `--team-a` — inside the 36 that `minimap.spec.ts` counts as
"this pixel is a player marker". A red spike was not merely hard to tell from an attacker; it was
arithmetically the same colour, and every one of its pixels would have counted as a player drawn
where no player was. It is now amber `#ff9f45` (90 from team A, 269 from team B). `--spike-boom`
moved to `#ff7043` to stay clear of it. Changed in `theme.py` and regenerated.

**The sidecar is at version 4**, storing raw `(t_ms, x, y, z)` plants and re-pairing on every load
— the same argument that keeps ability spawns stored raw and regrouped. v1–v3 stay readable.

**`abilities.attribute()` was wired into `wire.py`.** It was dead code called only from a test while
`MinimapCanvas` re-implemented the same join by hand, untested, in another language. It fixes bug
(i) in one line.

**`scan.py`'s `recorded` and `duration` properties were deleted.** They were `strftime` output
travelling beside the ISO instant they were formatted from, so the match list and the viewer header
wrote the same fact two different ways. `web/src/model/format.ts` owns it now and writes the
reader's own zone, which a server formatting in UTC cannot.

**The layer-availability rule was reversed, deliberately.** The old rule — "a control that cannot do
anything is worse than an explanation of its absence" — made `LayersMenu` *drop* the row, so
CALLOUTS was simply missing in 2D. A missing row reads as a missing feature. Rows are now always
shown, disabled, carrying the reason via `aria-describedby` **outside** the `<label>` (inside it, the
reason becomes part of the checkbox's accessible name and breaks every role-and-name lookup). Four
passages stating the old rule were rewritten in the same pass: `CLAUDE.md`, `LayersMenu.tsx`,
`MapStage.tsx`, `shortcuts.ts`.

**SIGHT's behaviour was kept and only explained.** Drawing a cone per player was considered and
rejected — `DEFAULT_LAYERS` already argues ten overlapping wedges say nothing, and ten per-frame
raycasts in the side colour would put thousands of near-team-coloured pixels against
`minimap.spec.ts`'s 200-pixel budget. A caption now says a player must be selected.

> **Reversed later.** The layer is now on by default and draws a wedge per living player, and the
> caption above was deleted with the behaviour it explained. The first objection was answered by
> ink rather than by count — unpicked cones fill at 0.09 against the picked 0.22 — and the second
> by the observation that the 200-pixel budget is a test about *markers*: `minimap.spec.ts` now
> sets SIGHT off for that spec and checks the cones in its own, against every cone rotated about
> its own player. That also needed a `setLayer` helper, because `toggleLayer` is a flip and every
> caller meant "on", so three specs would have silently photographed a switched-*off* layer.

---

## What did not work

**A sourced Q/E slot map — abandoned after measurement, and it should stay abandoned.**
The plan proposed extending the wiki research into a table mapping each agent's Q and E onto Riot's
`Ability1`/`Ability2`, which would have let `art.AgentArt.ability` resolve all four slots and
collapsed most of 4.3's synthetic surface. Two measurements killed it:

- The archetype path's letters are Riot's **internal** ones and do not track today's keybinds. The
  decode calls Sova's Recon Bolt `Q` where the game binds it to E, and Brimstone's Stim Beacon `E`
  where the game binds it to C.
- Matching decoded internal names against the manifest's display names (difflib similarity, script
  in scratchpad) agrees on **3 of the 40** (agent, slot) pairs the library produces — and one of
  those three is wrong.

So `abilityfacts` is keyed on **(agent, internal name)**, carries no slot map, and
`art.AgentArt.ability` goes on refusing Q and E. Both docstrings now record the measurement so this
is not retried.

**`valorant.fandom.com` returns HTTP 402 to WebFetch.** Use `wiki.playvalorant.com` — it is the
official wiki, has a clean stats table per ability, and returned exact figures for every ability
tried (`https://wiki.playvalorant.com/en-us/<Ability_Name>`, underscores for spaces). Astra's page
is `Nebula_/_Dissipate`, not `Nebula`.

**Re-warming the position cache by calling `tracks.attach` does nothing on its own.** `attach` reads
the cache *before* it decodes, so a stale v3 entry is handed straight back and the plants never
appear. The entry has to be evicted first —
`positioncache.cache_path(path).unlink(missing_ok=True)` — then attached. This cost a full 21-capture
pass to discover. All 21 caches are now v4 with plants.

**A ground-truth test must not read the machine's cache.** `tests/test_positions.py`'s new spike test
uses `Options(decode=True, cache=False)` deliberately: with the cache on it passed or failed
depending on what an earlier run had left there, and a readable v3 sidecar with no plants is a real
state, not a corrupt one.

**Prettier is not part of this project's checks.** `npm run lint` is `tsc --noEmit`. Untouched files
fail `prettier --check` too, so running `--write` would reformat the whole codebase into the diff.
Do not.

---

## Environment facts

- **The C# decoder was not built at session start.** `dotnet build csharp/VrfPositions/VrfPositions.csproj -c Release`
  (~7 s). .NET SDK 10.0.400 is installed; the parser clone is at `E:\Personal\ValorantReplayParser`,
  beside the repo, which is where the csproj expects it.
- Full library present: 101 captures in `Demos/`, `assets/` populated, 21 playable, all 21 now
  cached at sidecar v4.
- Test commands: `.venv\Scripts\python.exe -m pytest -q` (~23 s), `runners\lint.bat`,
  `cd web && npm test` (~4 s), `cd web && npx playwright test` (**~6.5 min**, starts its own Python
  server and Vite).
- `runners\make-golden.bat` regenerates `tests/golden/`; two files legitimately changed this session
  (`positions.json` → v4 + `spike_plants`, `replay.json` → spike `x/y/z` plus the new cast fields).
  `tests/test_golden.py` fails until you regenerate, which is the intended signal.
- `runners\make-theme.bat` regenerates `web/src/theme.generated.css` from `theme.py`.
  `tests/test_theme.py` pins the literal phrase **"not recoverable"** in the generated header — a
  rewrite that drops it fails.
- Scratch scripts from this session (spike pairing check, cast dump, slot matching, cache re-warm)
  are in
  `C:\Users\Dhina\AppData\Local\Temp\claude\E--Personal-val-replay-analyzer\75210cd6-51eb-4ff2-9115-b009ccf5852d\scratchpad\`
  along with 21 full raw decodes (`*.decode.json`, large). Useful if you need to re-measure; nothing
  depends on them.

---

## Open questions

1. **Why the spike marker does not draw.** The only blocking issue. See *Next steps*.
2. **`.clock-readout` counts up while `.clock-pill` counts down**, two inches apart. Item 7.3 named
   only the round timeline, which is fixed. Left as elapsed/duration on the argument that `A / B` is
   a progress idiom. Changing it is one token plus a one-line change to `minimap.spec.ts:90-92`,
   which pins that span's exact text. **User's call.**
3. **A first blood renders as two rows** at the same millisecond — a weapon row and a
   `killed … FIRST BLOOD` row. `RoundTimeline.tsx:193-200` ranks them deliberately, so it is by
   design, but it reads as a duplicate. Noted in the plan as out of scope.
4. **`abilityfacts` covers 15 abilities**, chosen as the ones that occupy an area a person could
   point at. Everything else returns `None` and draws no ring. Whether that is enough coverage is a
   judgement the user has not seen rendered yet.
5. `web/e2e/results/` and `web/e2e/report/` contain committed-looking artefacts that predate this
   session; several were rewritten by test runs. Not touched deliberately.

---

## Next steps

**Fix the failing spike test, then commit.**

The bug is narrowed to the drawing, not the data. Confirmed by instrumentation:

- `spikeLocation` returns the right value **in the browser**:
  `{x: -3277.5, y: -7513.4, z: -96.3}`, `spikeState: "planted"`, `spikeSinceMs: 286352`,
  `colours.spikeArmed: "#ff9f45"`. So `drawSpike` gets past its null guard and has a colour.
- The wire carries coordinates (the test reads them off the API before it ever looks at pixels).
- `spikeLocation`'s logic is correct in isolation (`spikeloc.test.ts`, 3 passing tests).
- The test expects amber at canvas **(321.1, 641.7)** on a 976×807 canvas, box side 787, uv
  (0.288, 0.803). It finds **0 amber pixels within 26 px** of there, and **180 amber pixels
  elsewhere** with centroid (536.3, 32.8).
- The failure screenshot
  (`web/e2e/results/minimap-the-2D-minimap-draws-the-spike-where-it-was-planted-chromium/test-failed-1.png`)
  shows the clock pill reading `R3 0:36 SPIKE DOWN`, death X marks and ability markers all drawing
  correctly, and **no amber triangle anywhere on the map**.

The decisive experiment not yet run — one line, inside `drawSpike`:

```ts
const [x, y] = world(at.x, at.y);
(window as unknown as Record<string, unknown>).__spikeXY = [x, y, half, scale];
```

then compare against the test's `(321.1, 641.7)`. If they differ, the `world`/`box` the canvas draws
with is not the `placeSquare` the test computes (a viewport or DPR difference) and the *test* is
wrong. If they match, the triangle is being drawn there and then covered or drawn transparent — in
which case suspect an inherited `globalAlpha`: `drawSpike` calls `context.save()` and only sets
`globalAlpha` *after* its `fill()`, so it fills at whatever alpha was live when it was entered. Setting
`context.globalAlpha = 1` explicitly at the top of the save block is correct regardless and is worth
doing either way.

Also worth knowing: those 180 stray amber pixels are unexplained and may be a second, separate
finding — nothing else on that canvas should be within 36 RGB of `#ff9f45`.

First command:

```
cd web && npx playwright test e2e/minimap.spec.ts --reporter=line -g "spike"
```

After it is green: strip the debug instrumentation listed in *State*, run the four suites, then
commit. The change is large and coherent enough to want more than one commit — the plan's phase
boundaries (measurement/research, broken behaviour, identity, icons, text, layout, styling,
formatting) are a reasonable split.

---

## Cautions

- **Do not `git checkout` or `git stash` anything.** A full session of work is uncommitted and there
  is no backup.
- **Do not delete `.cache/positions/`** casually. It is 21 freshly re-warmed v4 sidecars; rebuilding
  is ~10 s per capture and needs the C# decoder built.
- **Do not run `prettier --write`** — see *What did not work*.
- **Do not weaken `e2e/harness.ts`'s `toggleLayer`.** It was strengthened this session to assert the
  checkbox is enabled and actually flipped. Without that, a disabled layer row makes every layer
  spec pass *silently while toggling nothing* — that was the live hazard introduced by showing
  disabled rows.
- **Do not add a field to `Snapshot`.** It is serialised field-for-field against `tests/golden/` by
  `parity.test.ts`, so a new member needs a Python counterpart, a regenerated golden and a
  `make-golden --check` pass in two languages. Both new pieces of per-frame state this session
  (`spikeLocation`, `slotStateAt`) are free functions for that reason.
- **Do not put a spike marker at a site centroid** if the decode ever fails to produce one. The whole
  measurement exists to avoid a plausible coordinate.
- `images/` and `docs/ui-feedback.md` are untracked review inputs. Decide deliberately whether they
  belong in the repo; the earlier commit `498cb74` did track reference frames, so there is precedent.

---

## Suggested skills

1. **`code-review`** — first, once the spike test is green. This is ~45 files of new and heavily
   edited code across two languages, written in one pass, and much of it is canvas drawing and wire
   plumbing that the unit tests cover only indirectly. Worth a pass before it becomes history.
2. **`commit`** — required; everything is uncommitted, and the repo's history is conventional-commit
   style with descriptive bodies that match the codebase's documentation voice.

Not useful here: `init` (`CLAUDE.md` exists and was updated this session), `handoff` (this document),
`web-design-guidelines` and `high-end-visual-design` (the visual decisions were made against a
specific review and a pixel-test suite that encodes this project's own constraints — generic design
guidance would fight both).

---

## Sensitive material

Nothing sensitive was handled. No API keys, tokens or credentials were read or written — the project
opens no sockets except `fetch-assets`, which needs no key, and the wiki lookups this session were
public unauthenticated pages. Match GUIDs appearing in filenames and in this document are local
capture identifiers from the user's own `Demos/` directory and are not account identifiers.
