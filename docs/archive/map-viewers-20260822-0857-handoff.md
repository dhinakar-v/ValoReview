# Map viewers — 2D minimap, 3D scene, and the golden-fixture contract

2026-08-22 · branch `vd-develop` · `E:\Personal\val-replay-analyzer`

`docs/webapp-03-map-viewers.md` is implemented end to end — Parts A, B, C and D.
**Everything is uncommitted.** Python 565 pass / 10 skip, ruff clean; web 135 pass,
`tsc --noEmit` clean, `vite build` clean.

## Read these first

| Path | What it is | Why it matters |
|---|---|---|
| `docs/webapp-03-map-viewers.md` | The plan this session executed | Every requirement traces to a section of it; do not re-read the code to work out intent |
| `CLAUDE.md` | Project rules | Five sections were **rewritten this session** — abilities/placements, pitch, the sidecar, the browser model, sight/trails. It is current; trust it over anything older |
| `scripts/make_golden.py` | Generator for `tests/golden/` | Its module docstring is the full account of the two-language exactness contract and the three corrections it needed |
| `web/README.md` | Browser-side rules | Now carries the dependency table (`three`, fiber, drei, zustand) and the extended "what the interface must keep saying" list |
| `docs/039f3991_summary.md` §8 | Backlog of what is not in a `.vrf` | Two entries were **retired by measurement** this session; the replacement text has the numbers |
| `docs/ctk-app-rebuild-20260822-0032-handoff.md` | Previous handoff | Where this session started from |

## State

**Done and green.** Working tree only — nothing has been committed.

- **Part A — the model, ported.** `web/src/model/{angles,track,clock,transform,sight,state,replay}.ts`.
  `scripts/make_golden.py` + `runners/make-golden.bat` write seven committed fixtures to
  `tests/golden/`; `tests/test_golden.py` asserts Python reproduces them byte for byte and
  `web/src/model/__tests__/parity.test.ts` asserts TypeScript computes the same values.
- **Part B — the 2D minimap.** `web/src/views/MinimapCanvas.tsx`, `Transport.tsx` (timeline strip
  + transport bar), `playback.ts` (zustand store + rAF driver), `images.ts`, `MapStage.tsx` (owns
  the queries, the mode toggle, the layer toggles and every sentence).
  New endpoint `GET /api/maps/{key}/sight` (`wire.sight_mask` / `schema.SightDoc`).
- **Part C — the 3D scene.** `web/src/views/Scene3D.tsx`, lazy-loaded so the 2D default does not
  pay for `three` (364 kB main bundle vs 922 kB for the scene chunk).
- **Part D — both measurements ran and both held.** See *Decisions*. They are now standing tests
  in `tests/test_movement.py` (`PitchPointsAtTheVictim`, `SpawnLocationsAreRealCoordinates`).

**Half-done / not attempted.** Nothing from the plan is outstanding. What has *not* happened is a
human looking at the rendered page. jsdom has no 2D context and no WebGL, so the canvas drawing
and the scene are unverified visually; the arithmetic beneath them is pinned by `tests/golden/`
and the sentences by `web/src/views/MapStage.test.tsx`. **Verification items 2, 3 and 4 of the
plan need eyes on a browser.**

**A second session was editing this repo concurrently.** `libraries/vrfcache.py`,
`tests/test_vrfcache.py`, and the modifications to `oodlefind.py`, `csharpdecode.py`,
`positioncache.py`, `vrfhome/scan.py`, `.gitignore`, `README.md` and one line of
`docs/webapp-03-map-viewers.md` are **not this session's work** — they moved the caches from
`%LOCALAPPDATA%` into `<project root>/.cache/`. Two of their tests were red mid-session and are
green now. One stale test of theirs *was* fixed here because it blocked a clean run:
`tests/test_positioncache.py::TestCachePaths` referenced `positioncache.APP_DIRNAME`, which their
change deleted.

## Decisions made

**Ability spawn coordinates are real, so a smoke now has a place on the map.** The plan's check —
a player's first decoded position is ground truth for where they spawned — held across all 21
playable captures: 210/210 player pawns within 100 uu of their own first sample, median 0.0,
max 91.7. All 18,946 ability actors carry a location, and 98–100 % of each kind lands inside the
radar's playable silhouette (a random coordinate lands inside about a third of the time). The one
exception is `Actor_` — 13 instances, tens of thousands of units off-map — so
`AbilityCast.landed` **refuses** a kind `PLACING_KINDS` does not name rather than ranking it last.

**`PLACING_KINDS` is nearly the reverse of `NAMING_KINDS`, deliberately.** One cast opens several
channels in several places. The `Ability_` actor appears at the caster's feet (median 1 uu from
them) so it names the ability well and says nothing about where it went; the `GameObject_` appears
where the smoke came to rest (median 1,296 uu away). Taking the first spawn would put every smoke
on the thrower — plausible on a minimap, and wrong. Facts (`placements`) live on the model, the
reading (`landed`) is a property beside them, same split as the sidecar's.

**Sidecar version 3, with v1 and v2 still readable.** A spawn with no known transform is written
as two fields, never five with three zeros — defaulting would put every such actor on the map's
origin.

**Positive pitch is looking up, and it is rendered in 3D only.** Measured over 2,949 kills across
the library: median error 0.91°, 98.4 % inside 10°, against yaw's 98.7 % as the control; the
negated reading is four times worse. The minimap stays yaw-only because a top-down projection has
nowhere to put the other half.

**`Track.at` now interpolates pitch with `_lerp_angle`, not `_lerp`.** This was a real bug the
pitch measurement uncovered: pitch is an angle in 0..360 like yaw, so a player crossing the
horizon between two samples (359 → 1) landed at 180 — pointing backwards. p99 error went from
159° to 11.4°. **This changes decoded output**, which is why the golden fixtures were generated
after the fix.

**A lookup fills one field with `dataclasses.replace`, never by rebuilding the record.** See *What
did not work* — this cost the most time in the session.

**Exact cross-language equality, with exactly one stated tolerance.** Three corrections were
needed; each is commented where it lives. The single irreducible exception is `atan2`/`cos`/`sin`,
approximate by specification in *both* languages — so `sight.ray_directions` was split out of
`sight.cone` and is written into `cone.json` beside each polygon. The parity test compares
directions within 1e-12 and then marches *Python's own* directions through `march`, which is plain
arithmetic and matches to the bit. The occlusion a cone depends on stays exact.

**`sight.forward_uv` uses `math.sqrt`, not `math.hypot`.** `hypot` is approximate by spec in both
languages and implemented differently in each. This changed production Python for the sake of the
port, and says so in a comment.

**Two pre-existing server defects were fixed because Plan 3 depends on them.**
`/api/maps/{key}` was looked up in a dict keyed by `map_url` while the wire sends the display name
as `map_key` — the map reference page could never have resolved. Maps are now addressed by display
name (`ArtCache.map_art_by_name`), because `/Game/Maps/Infinity/Infinity` cannot be a URL segment.
And the SPA catch-all answered 200-with-HTML for any unmatched `/api/` path; it now 404s, or the
client parses a page as JSON and reports something unrelated.

**`positions_available` / `positions_note` were added to `ReplayDoc`**, so the DECODE button is
gated on whether a decode *could* work, not just on whether a decoder exists. The answer is handed
into `wire.replay_doc` as a keyword rather than derived there, because deriving it means importing
`vrfnet.payload_transform` and `tests/test_vrfserve.py::Headless` bans `wire` from reaching the
decoder. `vrfhome.scan.positions_available()` is the single authority; `vrfserve.app` asks it.

**Trails split at `MAX_INTERPOLATE_MS`** (`model/track.ts:segments`), fixing the desktop viewer's
inconsistency with its own track lookup, in both ports. Player trails are a new layer, default off.

**`Scene3D` is behind `React.lazy` and `SCENE_CAPTION` lives in its own module**, so rendering the
sentence does not pull in the megabyte it describes.

## What did not work

**`((a % n) + n) % n` is the wrong port of Python's `%`.** It gets the *sign* right and the
*value* subtly wrong — three roundings where CPython's `float_rem` does one, so `9.8` comes back
as `9.800000000000011`. It looks fine on screen and fails the golden fixtures. `model/angles.ts`
ports `float_rem` including the signed-zero case. Do not "simplify" it back.

**`(degrees * Math.PI) / 180` is not `math.radians`.** CPython multiplies by a stored `pi / 180`.
The difference is a bit or two in the angle, which is nothing — until a ray is marched cell by cell
against a 256-wide mask and stops a whole cell early, moving a polygon vertex by 5 % of the map.

**`names.resolve` silently dropped a whole feature.** It rebuilt each `AbilityCast` by listing its
fields, so the newly added `placements` were decoded, cached, read back — and lost on the way past.
**Nothing failed**: the API returned 252 casts with zero placements, which looks exactly like a
decode that found none. It cost roughly an hour, including a wrong hypothesis that the running
uvicorn process was stale (it was not; two processes were restarted for nothing). `tracks._name_pawns`
had the same shape and was changed the same way.
`tests/test_abilities.py::TestNamingKeepsEveryOtherField` walks `dataclasses.fields` and pins it.

**Byte-for-byte JSON equality across the two languages is not achievable and was not attempted.**
`json.dumps` writes `1.0` and `1e-05` where `JSON.stringify` writes `1` and `0.00001`, while both
recover the identical double. Python asserts bytes (it wrote them); TypeScript asserts values.

**`new URL(..., import.meta.url)` cannot read `tests/golden/` in vitest** — Vite rewrites that
pattern into an asset reference and refuses the path as outside the project root. The parity test
uses `fileURLToPath` + `join` + `readFileSync`, which needs `@types/node` and `"node"` in
`tsconfig.json`'s `types`.

**Testing Library does not auto-clean with `globals: false`.** `web/vitest` config sets it, so
`MapStage.test.tsx` calls `cleanup()` explicitly in `afterEach`; without it every render
accumulates and `findByText` matches two of everything. (`MatchList.test.tsx` has the same latent
issue and currently passes.)

**A `useQuery` that is never `enabled` reports `pending` forever.** A replay whose map is in no art
entry has an empty `map_key`, so `MapStage` sat on "Reading the decoded tracks…" instead of saying
what was missing. Found by running the server with `--no-art`, not by a test. There is now an
explicit `!replay.map_key` branch above the loading check, and a test for it.

## Environment facts

- Runners are `.bat`; `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format .`.
  **Do not run repo-wide `ruff format`** while another session is editing — it will reformat their
  in-flight files.
- New runner: `runners\make-golden.bat` (`--check` fails when `tests/golden/` is stale).
  `tests/test_golden.py` runs the same check, so CI catches it without npm.
- The position cache moved to `<project root>/.cache/positions/` this session (not by this work —
  see *State*). All 21 playable captures are cached there at sidecar v3.
- `Demos/` holds 101 captures, 21 playable; `assets/` and the C# decoder are both present, so the
  measurement tests in `tests/test_movement.py` actually run here rather than skipping.
- A full decode is ~4 s. The reference 12.10 capture used by `test_movement.py` is
  `Demos/03fcbb4a-…vrf`; the capture used for manual API checks was `Demos/40d2242e-…vrf`
  (Ascent, id `67a23337b59912df` under `--demo-path Demos`).
- Server for manual checks: `uv run python scripts/vrf_serve.py --demo-path Demos --port 8125
  --no-prewarm`. **Three uvicorn processes were left running on ports 8123–8126 during the
  session; kill any survivors before starting another.**
- Web: `npm test`, `npm run lint`, `npm run build`. New deps: `three`, `@react-three/fiber`,
  `@react-three/drei`, `zustand`, `@types/three`, `@types/node`.
- `GET /api/replays/<id>` for an unreadable `.vrf` raises `VrfError` → **500**. Pre-existing, not
  fixed here, out of Plan 3's scope. A card carries its error but opening one is a traceback.

## Open questions

1. **Does the scene's orientation actually match the minimap?** The `CALLOUTS` toggle in 3D exists
   precisely to check this and nobody has looked. A mirrored ground plane looks fine until two maps
   are compared. This is the single highest-value manual check.
2. **Marker sizes in the 3D scene are guesses** (`BODY_RADIUS = 0.006` etc., in fractions of the
   radar's side). They were never seen rendered.
3. **Should a v2 cache entry be refreshed to gain spawn coordinates?** The plan says v1 and v2 stay
   readable and this followed it — so a capture decoded before today shows no ability placements
   forever. Moot on this machine (the cache was rebuilt at v3), but it will bite a user with an
   older cache. A wrong guess here costs either a silently missing feature or throwing away
   correct decodes.
4. **Ability placements are drawn for every non-moving cast**, which on a busy round is a lot of
   diamonds. Whether that reads well is a judgement nobody has made yet.

## Next steps

Start by looking at it:

```
uv run python scripts/vrf_serve.py --demo-path Demos --port 8000 --open
```

Open a playable capture, then in order: check the 2D minimap puts ten players on the map and the
transport scrubs; toggle `SIGHT` on a selected player and confirm the cone points where they face
(a 90° error means trigonometry went into uv space instead of through the probe); switch to `3D`
and turn on `CALLOUTS` to compare the scene's orientation against the minimap; on a Split capture
check that heaven reads as above.

After that, the work is committable. It is one large change but it divides cleanly:
the model/measurement changes (`abilities`, `model`, `positionfile`, `tracks`, `names`), the server
changes (`wire`, `schema`, `app`, `art`, `scan`), the golden fixtures, and the browser. Prefer
several commits over one.

## Cautions

- **`tests/golden/` is committed and must stay committed.** It is synthetic, needs no `.vrf`, and
  is the contract two languages are compared against. Regenerating it is a deliberate act — if a
  fixture diff appears without a matching model change, something is wrong.
- **Do not relax the golden assertions to a tolerance.** The one tolerance in the suite covers
  three libm calls and is argued for in the generator's docstring. `toBeCloseTo` anywhere else
  would hide precisely the bugs these exist for.
- **Do not delete `libraries/vrfnet/`.** It is still the only independent check on the C# decoder.
- Another session may still be editing `oodlefind.py`, `csharpdecode.py`, `positioncache.py`,
  `vrfcache.py`, `vrfhome/scan.py` and `.gitignore`. Check `git status` timestamps before touching
  those.
- The position cache is disposable and regenerable in ~90 s, but it is still the user's data —
  ask before deleting `.cache/`.

## Suggested skills

- **`commit`** — first, and non-optional: the entire session is uncommitted across ~50 files, and
  the tree also carries another session's work that should not be swept into the same commit.
  Stage deliberately.
- **`code-review`** — after committing. Roughly 3,500 lines of new, lightly-exercised code, and the
  parts jsdom cannot reach (the canvas draw loop, the r3f scene graph, the rAF playback driver) have
  no test coverage at all. `MinimapCanvas.tsx` and `Scene3D.tsx` are where a review earns most.
- **`run`** — if the manual verification above is being done in this session rather than by hand.

Not useful here: `init` (`CLAUDE.md` exists and was just updated), `security-review` (nothing
touches auth, network egress or untrusted input; the server binds 127.0.0.1 and reads local files),
`simplify` (the code is new and the docstring density is deliberate house style, not accident).

## Sensitive material

Nothing in this document is sensitive. For the record, and do-not-copy if you generate output from
them: `Demos/*.vrf` filenames are Riot match UUIDs and the loadout roster carries player `subject`
UUIDs — real account identifiers. They appear in API responses and in `.cache/positions/*.json`.
Never paste them into an issue, a commit message or an artifact. `RIOT_API` (if ever set) lives in
`.env`, which is gitignored; no command in this session needed it.
