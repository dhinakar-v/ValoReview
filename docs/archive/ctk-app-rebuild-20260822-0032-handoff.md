# Handoff — the CustomTkinter app rebuild (Phases 4–6)

**Date:** 2026-08-22 00:32 · **Branch:** `vd-develop` · **Repo:** `E:\Personal\val-replay-analyzer`

Phase 3 of the approved seven-phase plan is **done and committed**; the working tree is clean.
Player positions, per-player agents and the whole cross-checking apparatus now live in the model.
The next session builds the UI the whole plan exists for: **Phase 4** (dependencies and config),
**Phase 5** (match-list page), **Phase 6** (viewer rebuild with a real minimap).

## Read these first, in order

| Path | What it is |
| --- | --- |
| `C:\Users\Dhina\.claude\plans\docs-valorant-replay-prompt-md-declarative-haven.md` | **The approved plan.** Phases 4, 5, 6 and 7 sections are the specification for this session. Work from it; do not restate it. |
| `docs/valorant-replay-prompt.md` | The original brief the plan implements — colour tokens, the three-column layout, the player-row anatomy, the round strip, the controls bar. Phases 5–6 build exactly this. |
| `docs/payload-decryption-20260821-2338-handoff.md` | The session before this one: how the payload de-obfuscation was ported and what it measured. Still accurate. |
| `CLAUDE.md` | **Corrected this session** — three of its conventions had become false. Re-read the replication-stream, positions and names sections; they now describe reality. |
| `libraries/vrfview/tracks.py` module docstring | What positions are, how they are verified, and why an unsupported build is a sentence and not an exception. |
| `libraries/vrfview/model.py` — `Position`, `Track` | The two types every minimap pixel comes from. `Track.at` is where the interpolate/hold/refuse judgement lives. |
| `docs/replay-viewer-20260821-2004-handoff.md` | The existing Tk viewer layer, which Phase 6 replaces. Still accurate about what is there today. |

Nothing below repeats those.

## State

**Everything is committed. The tree is clean.** `271 passed, 450 subtests`, `ruff check .` clean.

Nine commits this session, oldest first:

```
1e65b51 feat(vrfnet): de-obfuscate replicator bunch payloads      <- prior session's work,
7da4fa7 docs: record the MIT licence of the ported payload transform   committed at the start
8a3e64f feat(vrfnet): decode property blocks and player movement       of this one
85a901f docs: add the payload de-obfuscation handoff
d61961d fix(vrfnet): keep actor identities past the channel that carried them
89f11c1 feat(vrfview): carry player positions into the model
2e34e43 feat(names): name a player from the codename its own pawn stated
9d5ce8d feat(infer): cross-check the team split against the agents on the wire
c85cfe3 feat(vrf-view): add --positions to dump and view
89ac70b docs: correct what positions are, now that they decode
```

**Done:** Phases 1–3, plus the `CLAUDE.md` / findings-doc corrections that Phase 7 had deferred
(pulled forward because this session is what made them false).

**Untouched:** Phase 4 (dependencies, `vrfconfig`, positions in the JSON dump), Phase 5 (match
list), Phase 6 (viewer rebuild), and the remainder of Phase 7 (the "no runtime dependencies" line
in `CLAUDE.md`, which is still true until Phase 4 lands, and the new-test list).

### What Phase 3 handed the UI

The API surface Phases 5–6 build on, all of it headless and tkinter-free:

- `Replay.positions: dict[int, Track]`, `Replay.position_source: str`, `Replay.has_positions`,
  `Replay.track(actor_id)`.
- `Track.at(t_ms) -> Position | None` — binary search; interpolates across a gap up to
  `MAX_INTERPOLATE_MS`, holds a lone sample up to `MAX_HOLD_MS`, then returns `None`. A held
  sample carries its own measured `t_ms`, so a caller can see it is stale.
- `Snapshot.positions` / `Snapshot.death_positions` / `Snapshot.position_of(actor_id)` — the last
  falls back from live to death position, which is what the "dead agents pinned at death
  coordinates" requirement wants.
- `Player.codename` (read from the pawn archetype) and `Player.agent` (looked up), plus
  `Player.identity` which falls back agent → codename → label.
- `tracks.attach(replay, path, tracks.Options(...))` and `tracks.extract(...)`.
- `vrf-view.bat dump x.vrf --positions [--blocks N] [--oodle-dll PATH]`.

Measured on the full 12.10 Haven capture: **199,180 positions, 10 tracks, 10 Hz**, decoded in
**241 s**; `state_at` costs **0.127 ms/call** against 16.7 ms of budget at 60 fps, so the
recompute-from-scratch rule survives untouched.

## Decisions made

**`tracks.py` is the only module that imports vrfnet into the viewer.** `model`, `infer`, `state`
and `layout` still import neither tkinter nor the decoder. Phase 6 must not breach that — the
minimap gets `Snapshot.positions`, never a `ReplaySession`.

**Positions are opt-in and never fatal.** An unsupported build, a missing Oodle DLL and a JSON
dump all end as a sentence in `Replay.position_source`; nothing raises. Phase 6's centre canvas
therefore has to switch on `replay.has_positions` and say which of the two it is showing.

**The build is checked before anything expensive.** `extract` calls `transform_for(build)` before
`Oodle.discover`, so 80 of the 101 captures refuse in **0.3 s** with no DLL and no decompression.
Phase 5's "positions available" card indicator can use the same plain-header read.

**Movement is thinned to 10 Hz on the way in** (`model.POSITION_HZ`), from about 100 Hz on the
wire, and drained per block so a full match holds one block of moves rather than all 3.09 million.
At a walking 300 uu/s the loss is ~30 uu, well inside the dot that draws it.

**A player's agent comes from its own pawn, never from a loadout slot.** The archetype path states
a codename (`Hunter`) and `developerName` names it (Sova). The loadout roster still attaches to no
actor. The two joins share no term, so `names._cross_check_roster` notes when they agree — on the
reference capture they name the same ten agents.

**`infer` now uses the agents as evidence.** A reconnect merge is refused when the two actors play
different agents and confirmed when they match; a team holding two of the same agent is reported,
never acted on, because a custom game is as likely as a mis-colouring.

**Doc corrections were pulled forward out of Phase 7.** Leaving `CLAUDE.md` saying "No positions
exist" through three more phases would have actively misled the next agent — including you.

## What did not work

**Reading codenames from the live channel table.** `ChannelTable.channels` drops a channel on
close and is cleared wholesale at a checkpoint, so the first implementation silently lost the
codename of exactly the player a reconnect merge most needs one for (actor 1370 on the reference
capture came back with no agent). Fixed by `ChannelTable.archetypes`, an actor-GUID → path record
that survives both. **Do not read identities out of `channels` at the end of a run.**

**Counting ignored actors per block.** `actors_ignored` incremented once per (actor, block) pair
and reported 143 non-player actors as several hundred. It is a `set` now.

**A codename-only `Catalog` read as empty.** `Catalog.empty` was `not maps and not agents`, which
called a perfectly good third join nothing. It now includes `codenames`.

**Three test fixtures that were wrong rather than the code.** The reconnect fixture produced three
candidate pairings, so the merge declined on ambiguity and never reached the codename check it was
written to exercise — one member has to span the whole match so only one pair is disjoint. And a
`checked > 10` assertion on kills-in-window was brittle: two blocks cover 135 s and nine kills, not
the 227 s three blocks cover. The test now asks per-kill whether both actors' own tracks span the
instant, which is precise and does not move with `BLOCKS`.

**Do not re-run the spawn-transform search.** It was falsified exhaustively across 2,700
(offset × scale) combinations in an earlier session and is correct: no location is present at any
fixed offset on an opening bunch. Positions come from the movement RPC. `actors.py` now says this.

**Bash heredocs still fail on apostrophes in this environment.** Writing `tracks.py` through
`cat <<'PY'` died with `unexpected EOF while looking for matching '`. Use the Write tool for new
files with prose docstrings; short `python - <<'EOF'` patch scripts are fine.

## Environment facts

- **Interpreter:** `./.venv/Scripts/python.exe`, Python 3.11.14, Tk 8.6. `pip` is not installed in
  the uv venv — use `uv add` / `uv sync`, and `python -c "import x"` to check for a package.
- **`customtkinter`, `dotenv` and `PIL` are all ABSENT from the venv** (verified this session).
  Phase 4 needs network for `uv add`.
- **`.env` currently holds only `RIOT_API`**; `.env.example` holds `VRF_OODLE_DLL` and `RIOT_API`.
  **There is no `DEMO_PATH` yet** — Phase 4 adds it to `.env.example`, and `vrfconfig` must
  default to `Demos/` so a checkout with no `.env` still works.
- **`assets/manifest.json` has no `developer_name` yet.** `plan_agents` records it now, but the
  cached manifest predates that, so the codename join currently falls through to
  `names.AGENT_CODENAMES` (which answers correctly and says so in the provenance line). Refetching
  redownloads art, so it was left alone deliberately — the user's call.
- **Reference captures.** 12.10 Haven, 27 REPLAYDATA blocks, ~190 MB decompressed:
  `Demos/03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf`. 11.11, the canonical capture, which correctly
  refuses positions: `Demos/039f3991-5472-4119-bed2-838da0935f60.vrf`. `Demos/` is gitignored, so
  every capture-backed test is `skipif`-gated.
- **Decode cost:** ~9 s per REPLAYDATA block; 241 s for the full 12.10 match; `--blocks 2` is
  ~12 s and covers 135 s of match and nine kills.
- **Test/lint:** `runners\test.bat`, `runners\lint.bat`, `runners\format.bat`. Tests are
  `unittest.TestCase` classes using plain `assert` and `pytest.raises` (`assertEqual` trips PT009,
  `assertRaises` trips PT027). Class names must be CapWords with no underscores (N801).
  `ruff` will also flag >5 function arguments (PLR0913) and >10 complexity (C901) — the fix used
  here was an `Options` dataclass and an extracted `_print_players`.
- **The full suite now takes ~30 s** (was 18 s); the added time is `tests/test_tracks.py` decoding
  two real blocks.

## Open questions

**`python-dotenv` versus `envfile.py`, and this is worth five minutes before writing code.** The
brief mandates `python-dotenv` and the plan adopts it for the new `vrfconfig.DEMO_PATH`, while
`envfile.py` stays for `oodlefind` and `valapi`. That leaves **two readers of the same `.env`** in
one process. `envfile.py` already implements precisely the contract the plan asks `vrfconfig` to
reproduce — real environment first, then the nearest `.env`, no `os.environ` mutation — so
`dotenv_values()` buys nothing but a dependency and a second code path. Three ways out, in
increasing order of deviation from the plan: (a) follow the plan literally; (b) add
`python-dotenv` to `requirements.txt` to satisfy the brief but have `vrfconfig` call `envfile`;
(c) drop `python-dotenv` and say why in `CLAUDE.md`. **This was discovered at the very end of the
session and never put to the user.** Ask before implementing.

**Where do positions go in the JSON dump?** Phase 4 says to persist decoded positions and the
actor→agent map into `vrf_to_json` so the JSON path stays DLL-free. 199,180 samples is a lot of
JSON — at ~60 bytes a sample that is roughly 12 MB on top of the existing ~5 MB. Consider a
coarser rate for the dump, or a separate sidecar file, and note that `tests/test_vrfview.py`
asserts the `.vrf` and JSON paths produce **equal** models, so whatever shape is chosen has to
round-trip exactly or that test needs a documented exemption.

**The `WIN`/`LOSS` badge the brief demands cannot be built.** There is no local player and A/B is
arbitrary, so the plan renders an explicit "result not in file" chip instead. Same for
`BUY PHASE` — no buy event exists. Do not let the brief's layout pressure either into being
invented.

## Next steps

Start with Phase 4, and resolve the dotenv question above first — it changes what `vrfconfig`
looks like.

```bash
cd E:/Personal/val-replay-analyzer
git log --oneline -3          # expect 89ac70b at the top, clean tree
./.venv/Scripts/python.exe -m pytest -q     # expect 271 passed, 450 subtests
```

Then confirm the decode still works before building a UI on it — this is the fast check, twelve
seconds rather than four minutes:

```bash
./.venv/Scripts/python.exe scripts/vrf_view.py dump \
  "Demos/03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf" --positions --blocks 2
```

Expect ten players with an `agent` and a `codename` each, `actor 36998 merged into 1370 ... both
pawns are Pine`, and `the team split is corroborated by the agents on the wire`.

**Phase 4** then: `uv add customtkinter Pillow python-dotenv` (network), a `requirements.txt`, a
new `libraries/vrfconfig.py` for `DEMO_PATH`, `DEMO_PATH` into `.env.example`, and positions into
the `vrf_to_json` dump. Amend `CLAUDE.md`'s "No runtime dependencies" line in the same commit that
breaks it — not later.

**Phase 6's minimap has one thing already solved for it.** `vrfview/art.py`'s `Transform.apply`
converts a world coordinate to a `(u, v)` fraction of `minimap.png` and already implements the
x/y axis swap, measured against all 346 callouts in the manifest rather than assumed. Feed it
`Position.x` and `Position.y` directly. `vrfview/mapref.py` is a working example of drawing at
real map coordinates — but note it is deliberately handed no `Replay`, so the minimap is a new
widget rather than a change to that one.

## Cautions

- **Never add a nearest-version fallback to `payload_transform`.** An unsupported build must
  raise. This is the one failure mode the module exists to prevent.
- **Do not point position work at the 11.11 reference capture.** It refuses correctly and fast.
  The existing 11.11-based tests must keep passing untouched.
- **Do not adopt the brief's ATK-red / DEF-blue semantics.** Sides are not recoverable from the
  file. The colours mean team A and team B and must be labelled so.
- **`scene.py` stays.** It is the fallback for unsupported builds and keeps its SCHEMATIC
  watermark. The centre canvas switches between it and the minimap and says which it is showing.
- **Keep the existing `after()` loop and `PlaybackClock` unchanged.** Both are already headless,
  exact and tested.
- **Do not put an agent icon on a roster slot.** The loadout roster still attaches to no actor;
  only `Player.agent` may name a node. `vrfview/roster.py` and `vrfview/names.py` both say why.
- Deleting `art.png_size` and `art.subsample_for` is a Phase 6 step that depends on Pillow being
  in place — do not do it before Phase 4 lands.

## Suggested skills

- **`code-review`** — worth running early in the next session, before more code is built on top.
  Roughly 2,000 lines were added across two sessions, including ported arithmetic where a subtle
  error produces plausible-looking output rather than an exception. The tests prove the happy path
  against known answers and real captures; they prove much less about the error paths.
- **`commit`** — at each phase boundary. The repo's conventional-commit history is consistent and
  should not be broken by a hand-written message.
- **`run`** — once Phase 6 has something to look at. The viewer is a GUI and screenshots are the
  only honest check that the minimap draws where it claims.
- **`handoff`** — again at the end of Phase 6, or whenever context runs short.

Not useful here: `init` (`CLAUDE.md` exists and was just corrected — further changes are ordinary
editing), `security-review` (this code parses local files; the only socket is the pre-existing
`catalog --refresh`), `dataviz` and `artifact-design` (this is a desktop Tk app, not a web page or
a chart).

## Sensitive material

- `.env` holds a real `RIOT_API` value, read at runtime via `envfile.get("RIOT_API")`. Never
  print, copy or commit it. `.env.example` is the safe template. The brief also shows a real
  `DEMO_PATH` under the user's profile — treat that as configuration, not something to hard-code.
- `docs/039f3991_summary.md` contains player `subject` UUIDs. **Do not copy them into new files or
  send them anywhere** — reference the doc by path.
- `Demos/` filenames are match UUIDs. They are gitignored and safe to name in local paths (the
  tests already do), but do not publish them.
- `dump --positions` prints agent names and actor IDs but no player identity; `val-match-v1`,
  which would carry real names, is still 403 without a production key and is not depended on.
