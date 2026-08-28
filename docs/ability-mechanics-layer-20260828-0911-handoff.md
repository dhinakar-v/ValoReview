# Mechanics-aware abilities — flights, lifecycles, and the icon join that was wrong

28 August 2026 · branch `vd-develop` · `E:\Personal\ValoReview`

This session turned the 2D viewer's ability marks from *one static dot per cast* into a
lifecycle: a thrown ability flies from where it left the caster to where it landed, arms,
stands, and goes. It also found and fixed a **shipped bug** — half the C-slot ability icons on
the map were the wrong ability's picture.

**Everything is uncommitted.** 21 modified files, 2 new, ~2,600 insertions. Committing is the
next agent's first action.

---

## Read these first

| # | Artifact | What it is / why it matters |
|---|---|---|
| 1 | `CLAUDE.md` — the **Ability casts** paragraph in *Conventions that matter here* | Updated this session with every decision below, in the file that carries every other one. It is the durable record; this handoff is the reasoning that did not fit there. |
| 2 | `C:\Users\Dhina\.claude\plans\based-on-this-research-mossy-catmull.md` | The approved plan. Read for intent, **not for status**: three of its claims were corrected by measurement during implementation (see *What did not work*). Outside the repo, not version-controlled. |
| 3 | `docs/Valorant Agent Ability Details.md` | The user-supplied research the ability table is authored from. Covers 17 agents. Cites its own sources per agent. |
| 4 | `libraries/vrfview/abilityfacts.py` module docstring | Rewritten. Why the key is `(codename, slot)`, why the slot is not the keybind, and what is deliberately absent (Viper, walls, cast ranges). |
| 5 | `web/src/views/castlayer.ts` module docstring | The decoded/looked-up split, the four phases, and the two standing prohibitions (no arc, no claim about any player). |
| 6 | `libraries/vrfview/art.py` — `AgentArt.ability` / `ability_named` | The icon-join correction and the measurement behind it. |
| 7 | `docs/desktop-app-shipped-20260823-1947-handoff.md` | Previous handoff, unrelated subject (Tauri shell). Nothing in it is contradicted here. |

---

## State

### Uncommitted — this is the first action

`git status --short` shows 21 modified and 2 untracked (`web/src/views/castlayer.ts`,
`castlayer.test.ts`). Nothing has been committed this session. Last commit is `b7ecd03`.

### Done and verified

- **Python ability table** — `abilityfacts.py` rewritten as one table keyed `(codename, slot)`,
  68 entries over 16 agents, every figure carrying its own source string. Replaces the old
  two-table `_FACTS`/`_SMOKES` split.
- **`Placement.t_ms`** — the spawn instant, which `AbilitySpawn` always had and `_placements`
  was dropping. Threaded through `wire`/`schema`/`types.ts`.
- **`AbilityCast.flights`** — pairs throw origins to landings, with four measured refusals.
- **`web/src/views/castlayer.ts`** — new storeless module, four phases, no store reads.
- **`MECHANICS (SIM)` layer** — new key `castMechanics`, on by default, drawn only in 2D.
- **Icon join corrected** — `art.AgentArt.ability_named` joins on Riot's published ability name.
- **Smoke timing corrected** — `smokesAt` ages each placement from its own arrival.
- **Rail rows** — carry the published ability name, radius and lifetime, with per-figure sources.

### Test status

| Tier | Result |
|---|---|
| `runners\test.bat` | **584 passed**, 9 skipped, 452 subtests |
| `cd web && npm test` | **321 passed** (16 files) |
| `npx playwright test e2e/minimap.spec.ts e2e/review.spec.ts` | **18 passed, 1 failed** |
| `runners\make-golden.bat --check` | current (regenerated twice this session) |

The one Playwright failure is **pre-existing and not from this work** — see *Environment facts*.

### Untouched

`Scene3D` draws none of this, deliberately (`drawnIn: ["2d"]` plus a `why` string). Clove's Ruse
has no occluder. No 3D parity was attempted.

---

## Decisions made

**The table key is `(codename, slot)`, and the old key was retired.** `_FACTS` keyed on
`(agent, internal name)` and `_SMOKES` on `(codename, slot)`. Measured over the 23 cached
decodes: *every* `(codename, slot)` maps to exactly one real ability — Sova's `Q` yields four
internal names (`Sonar Ping`, `Reveal Bolt`, `Sonar Bolt`, `Reveal Bolt Signature`), all Recon
Bolt. The internal name splits; the slot cannot. One table, and `smoke_for` became a *reading*
over it rather than a second copy of each radius, which retires the old "two copies of a number"
cross-check by making it structural.

**The slot is not the keybind, and `keybind` is a looked-up field.** The archetype path's letters
are Riot's internal ones — Sova's `C` is Shock Bolt, which the game binds to Q. Each entry
carries both. Six of the sixteen agents are shuffled. `tests/test_abilityfacts.py::TheSlotIsNotTheKeybind`
lists all fourteen shuffled pairs so that "simplifying" the table by dropping `keybind` fails.

**A flight is decoded at both ends; only the straight line is invented.** This is the whole basis
for animating a throw without violating the repo's rules, and it mirrors `tracers.ts` exactly.
100% of `Projectile_` and placed spawns carry coordinates; the two spawn instants give a real
duration. **There is still no arc** — only `Pawn_` actors emit movement.

**`FLIGHT_MAX_MS = 3000`, argued from a density collapse.** Below 3 s the library produces 833
pairs per second of delta; from 3–9 s it produces 3.3 — a factor of 250, holding 97.96% of
forward pairs. Above it are remote detonations (a Nanoswarm set off half a minute later), not
projectiles in the air.

**Pairing is k-to-k or refused.** 2,870 of 6,304 casts open unequal numbers of projectiles and
landings. Earliest-to-earliest produced a 72-second "throw".

**`duration_ms` and `persists` are two different questions.** This was the second-round
correction and the most important modelling decision here. `duration_ms` is how long the
*effect* lasts; `persists` is whether the thing is still there. Trademark publishes a 4-second
slow and waits on the floor all round; a Turret publishes no duration and stands until shot.
Conflating them broke both ends at once. Three outcomes now: `persists` → stands to round end;
`duration_ms` → expires; a **named** ability with neither → a *moment*, shown for `EVENT_MS`.

**An ability the table does not name changes nothing.** 13 of 29 agents are unnamed. My first
cut made any cast with no duration momentary, which would have swept their marks off the map
after two seconds — a claim made from an absence. Only positive knowledge (named, no lifetime,
no persistence) makes something a moment.

**Expiry lives in the view, never in `abilitiesAt`.** Both `model/state.ts` and
`libraries/vrfview/state.py` keep a cast for the whole round on purpose and are parity-tested
against `tests/golden/snapshots.json`. Nothing was added to `Snapshot`, which is why `castsAt`
and `phaseOf` are free functions — same reason `tracersAt` and `spikeLocation` are.

**Icons join by name, not by letter.** See *What did not work* — this began as a bug hunt.
`abilityfacts` names the published ability in each internal slot; the manifest names every
ability Riot publishes. Matching them is an identity: **68 of 68, none ambiguous, none missed.**
Q and E carry Riot's artwork for the first time.

**`MECHANICS (SIM)` and `RANGE (SIM)` are both on by default.** Both shipped off following
`abilityRange`'s "ask for looked-up things deliberately" argument. That argument is right about
the *number* and wrong about the *default*: with the layer off, a placed ability appears when
cast and stays all round, so by the end every utility anybody used is on screen at once —
claiming a dozen things are standing that are not. That is not neutral. They follow `tracers`
instead: on, dashed, `(SIM)`.

**One switch, not two.** The throw and the rings are one story about one ability; a thrown thing
that arrives and then never lands anywhere is a worse picture than either half.

**No claim about any player, ever.** No "these three were flashed". Position is 10 Hz and
interpolated, the sight approximation already wrongly closes ~38% of real sightlines, and
whether somebody faced a flash is not in the file. `castlayer.test.ts` walks the returned
structure to keep it that way. The user confirmed this scope explicitly when asked.

---

## What did not work

**The C-slot icon join that was already shipping was wrong for half the agents.** This is the
highest-value finding of the session. `art.SLOT_TO_MANIFEST` mapped internal `C` → Riot's
`Grenade`, on the reasoning that `Grenade` is C on every agent. Measured against the new table:
correct for 8 of 16, **wrong for the other 8**. Brimstone's Sky Smoke drew Stim Beacon's icon,
Omen's Dark Cover drew Shrouded Step's, Sova's Shock Bolt drew Owl Drone's — every round,
silently, because one white glyph at 14 px looks like another. The `C` entry is gone; only `X`
survives (exact on all 16). `tests/test_abilityfacts.py::EveryAbilityNameJoinsRiotsCatalogue`
asserts the C-by-letter join *would still be wrong*, so widening it again has to be deliberate.

**Joining icons by keybind does not work either — do not retry it.** The obvious repair, once
`keybind` existed, was keybind → Riot slot (`Q`→`Ability1`, `E`→`Ability2`, `C`→`Grenade`).
Measured: 65 of 68, and the 3 failures are decisive. Riot's `Ability1` for **Phoenix** is Hot
Hands, which the game binds to **E**; his `Ability2` is Curveball, bound to **Q**. Deadlock's
`Grenade` is Barrier Mesh where internal C is GravNet. So *both* namespaces are shuffled against
the keybind, and shuffled differently. No arrangement of letters joins them. Only the name does.

**The "empty band" argument for the flight ceiling was wrong.** The Plan agent measured a gap at
4000–5000 ms over the 1,300 one-to-one casts and proposed `FLIGHT_MAX_MS = 4000` as a
"gap between two populations". Over the full 2,842 same-count pairs the band is **not empty**
(4072, 4250, 4605 ms) and the tail runs continuously to 72 seconds. At ~3 samples/second an
empty 250 ms bin up there is a coincidence. Replaced with the density argument above. The
lesson generalises: an empty bin in a sparse tail is not a gap.

**The plan's claim that the golden stays current was wrong.** `tests/golden/replay.json` is
built by `wire.replay_doc` and already contained `placements`, so `Placement.t_ms` broke it
immediately. Regenerated twice — once for `t_ms`/`flights`, once for `persists`.

**`firstLoneRing` — the first e2e selector — was wrong.** It looked for an instant with exactly
one cast carrying a radius, and picked Phoenix `C` in `placed` phase, which draws nothing, while
*other* casts drew detection rings 582 px away. 100% of changed pixels were "outside". Replaced
with `predictedDiscs` + `firstDrawnMechanics`, which predicts the whole layer's geometry from
`castsAt` and asserts every painted pixel falls inside some claimed disc.

**Clove's Ruse radius could not be sourced.** The research doc publishes its duration, cost and
charges but no radius. `WebFetch` on `valorant.fandom.com/wiki/Ruse` returns **HTTP 402** and
`liquipedia.net/valorant/Clove` returns **HTTP 403**. So `blocks_sight=True` with
`radius_uu=None`, and `smoke_for` refuses it — half a smoke is not a smoke. Clove is the most
common smoke in the library (1,609 `E` spawns), so this is the most visible remaining gap. If
the next session can reach a source, it is one line.

**The research document contradicts itself on Clove.** Its summary table gives Ruse (Alive) as
14.25 s; its own Clove section gives 14.0 s. The entry takes 14.0 (more specific) and the source
string records the disagreement. Do not silently "fix" this to 14.25.

**A `sleep 45 && echo` in Bash is blocked** by the harness; use `run_in_background` or an
`until` loop.

---

## Environment facts

- **23 decoded captures** in `.cache/positions/*.json` and 103 `.vrf` in `Demos/`. Both
  gitignored. Every measurement in this session came from them; a fresh clone cannot re-run them
  and the tests `skipUnless` accordingly.
- Iterating over the whole library via `pipeline.open_replay` costs **~16 s** (reads the cache,
  no decode). Acceptable inside a test.
- `abilities.casts(spawns)` **without `round_of`** groups per whole match, not per round — it
  gave 517 casts instead of 6,304 and badly distorts per-cast measurements. Always go through
  `pipeline.open_replay`.
- Codename casing in archetype paths matters for table keys: `AggroBot` (capital B), `Cable`,
  `Mage`, `Nox`. `names.AGENT_CODENAMES` keys are lowercase; the table's are not.
- **Viper has zero casts** in the library, which is why she is refused.
- Ruff enforces `COM812` trailing commas and `D213` docstring style; run
  `runners\lint.bat` then `runners\format.bat` — the formatter reflows what the linter fixes.
- **Pre-existing Playwright failure**: `minimap.spec.ts` → *"every living player gets a cone,
  pointing where they are facing"*, forward coverage 0.354 against a required 0.6. Confirmed by
  `git stash push --include-untracked` and re-running: **byte-identical numbers** on the clean
  tree. Not caused by this work; worth its own session.
- **The 3D pixel tests are flaky under full-suite load.** A baseline full run failed *"draws a
  player above the plane"*; a run with these changes failed *"draws the fatal shot in the
  scene"*. Each passes in isolation on both trees. Do not chase one without first running it
  alone.
- Playwright full suite takes **~10 minutes** and exceeds the 600 s foreground timeout — run it
  with `run_in_background: true`.
- The Bash tool's working directory persists across calls; several commands failed with
  `cd: web: No such file or directory` because a previous call had already moved there. Use
  absolute paths.

---

## Open questions

1. **Clove's Ruse radius.** Blocked on reaching a source (both wikis refuse this environment).
   Cost of guessing: a made-up-width smoke standing on the map for 14 s and occluding sight — a
   plausible wrong answer of exactly the kind `tests/test_positions.py` exists to prevent.
   Currently refused, which is visibly absent rather than quietly wrong.
2. **Is `EVENT_MS = 2000` right?** It is an admitted presentation figure with no measurement
   behind it, like `tracers.FLIGHT_MS`. A wrong value is cosmetic — too short and a flash blinks,
   too long and moments pile up. Not worth a measurement unless a reader complains.
3. **The 13 unnamed agents.** Deadlock, Gekko, Harbor, Iso, KAY/O, Miks, Neon, Tejo, Veto, Vyse,
   Waylay, Yoru have partial or no entries. Each is one dict entry; the blocker is sourced
   figures, not code.
4. **Whether the sight-cone e2e failure matters.** It has been failing since before this session
   and nobody has attributed it.

---

## Next steps

**Commit first.** The tree holds a complete, tested, self-consistent change and nothing is
half-finished. Suggested split, if the next agent wants reviewable commits rather than one:

1. `fix(art)` — the icon join (`art.py`, the wire's icon block, the census test). This is a
   standalone bug fix and the most valuable thing here; it deserves its own commit and message.
2. `feat(abilities)` — `Placement.t_ms`, `flights`, `abilityfacts` rewrite, wire/schema/types,
   golden regeneration, Python tests.
3. `feat(viewer)` — `castlayer.ts`, `MinimapCanvas`, `LayersMenu`, `playback`, `roundevents`,
   CSS, the browser tests and the e2e spec.

First command:

```
git status --short && git diff --stat
```

Then run the full verification once more before committing, because the tree has not been
re-verified since the last edit to `CLAUDE.md`:

```
runners\lint.bat && runners\test.bat && runners\make-golden.bat --check
cd web && npm test && npm run build
```

After committing, the highest-value follow-ups in order: source Clove's Ruse radius (one line,
biggest visible gap); attribute the sight-cone failure; then extend the table to the unnamed
agents.

---

## Cautions

- **Do not re-run `git stash`** casually — the new files are untracked, so any stash must use
  `--include-untracked` or `castlayer.ts` is left behind and the tree will not compile. This was
  done twice safely this session; both times the stash was popped immediately.
- **Do not widen `art.SLOT_TO_MANIFEST` back to include `C`.** A test asserts it would be wrong.
- **Do not add a nearest-ability fallback or a default radius/duration.** Every refusal in
  `abilityfacts` is deliberate and tested.
- **Do not draw a curve for a flight.** Both endpoints are decoded and the path is not; a curve
  would be a path nobody took drawn in the same ink as one that was decoded.
- **Do not loosen `minimap.spec.ts`'s `< 200` pixel budget** to accommodate a new layer. Turn
  the layer off in the spec with `setLayer` — never `toggleLayer`, which is a flip and once left
  three specs silently green.
- **Do not "fix" Clove's 14.0 s to 14.25 s** without reading the note in the source string.
- Regenerating the golden is safe and expected after any wire change; editing
  `tests/golden/*.json` by hand is not.

---

## Suggested skills

1. **`commit`** — first, and unavoidable: 23 files are uncommitted. Use it for each of the three
   commits above; it is the only sanctioned path to a commit in this repo and it produces the
   Conventional Commits messages `CLAUDE.md` expects, with no AI attribution tags.
2. **`code-review`** — after committing, on the diff. `castlayer.ts` is 316 lines of new logic
   written in one pass, the phase machine has eight branches with half-open boundaries, and the
   `persists`/`duration_ms`/momentary split was reworked twice under time pressure. That is
   exactly the shape of code where a second reading pays.
3. **`handoff`** — at the end of the next session, since this work will still be mid-stream if
   Clove and the unnamed agents are picked up.

Not useful here: `init` (a substantial `CLAUDE.md` exists and was updated this session);
`security-review` (no auth, no network, no untrusted input — the only fetch attempt was outbound
and refused); `web-design-guidelines` and `high-end-visual-design` (the canvas work is pixel
geometry checked by Playwright, not DOM styling, and the flat-and-square sweep already passes);
`dataviz` (not a chart).

---

## Sensitive material

Nothing sensitive was handled. Two notes for the next agent:

- `Demos/*.vrf` and `.cache/positions/*.json` are **real matches with real player UUIDs** in
  them. They are gitignored and must stay so. Filenames are match GUIDs — a prior convention in
  this repo is to refer to captures by *build* rather than by GUID where possible; test constants
  like `DEMO_12_10` follow it. Do not paste sidecar contents into a document.
- `csharp/parser` deliberately does **not** decode `Subject`, a player UUID. That refusal is
  recorded in `csharp/parser/README.md` and must not be reversed.
- No API keys, tokens or `.env` values were read or written. `libraries/oodlefind.py` resolves a
  DLL path through `envfile`; it was not touched.
