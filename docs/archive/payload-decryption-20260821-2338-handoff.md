# Handoff — payload de-obfuscation and player positions

**Date:** 2026-08-21 23:38 · **Branch:** `vd-develop` · **Repo:** `E:\Personal\val-replay-analyzer`

This session broke the property-payload blocker that both prior handoffs describe as the wall.
**Player positions, rotations and velocities now decode.** The work is Phases 1–2 of an approved
seven-phase plan; Phases 3–7 are untouched.

## Read these first, in order

| Path | What it is |
| --- | --- |
| `C:\Users\Dhina\.claude\plans\docs-valorant-replay-prompt-md-declarative-haven.md` | **The approved plan.** All seven phases, the build census, the verification commands, and the reasoning behind every scoping decision. Do not restate it; work from it. |
| `docs/replay-viewer-20260821-2004-handoff.md` | Prior session. The viewer layer, still accurate. |
| `docs/vrf-decoder-20260821-1938-handoff.md` | Session before that. Decoder internals below the property layer. |
| Module docstrings in `libraries/vrfnet/payload_transform.py`, `properties.py`, `movement.py` | Each states what it measured and what it refuses to assume, in this repo's house style. `movement.py` documents the three-level RPC nest — read it before touching positions. |
| `THIRD_PARTY.md` | MIT attribution for the ported code. Licensing is not optional here. |
| `docs/vrf-decoding-findings.md` § "The premise that did not hold" | **Now wrong.** See *What did not work*. |
| `docs/valorant-replay-prompt.md` | The original CustomTkinter brief that started this. Phases 4–6 implement it. |

Nothing below repeats those.

## State

**Everything from this session is uncommitted.** That is the next agent's first action.

```
 M libraries/vrfnet/datachannel.py     <- incidental: ruff collapsed one wrapped f-string
 M libraries/vrfnet/session.py         <- branch plumbing, movement collection, extracted method
 M scripts/vrf_net.py                  <- new `positions` command, dict dispatch in main()
?? THIRD_PARTY.md
?? libraries/vrfnet/payload_transform.py
?? libraries/vrfnet/properties.py
?? libraries/vrfnet/movement.py
?? tests/test_payload_transform.py
?? tests/test_properties.py
?? tests/test_movement.py
```

`230 passed, 450 subtests` and repo-wide `ruff check` clean as of writing.

**Done:** Phase 1 (transform) and Phase 2 (property loop, movement, CLI diagnostic, tests).

**Untouched:** Phase 3 (positions into `Replay`/`Snapshot`), Phase 4 (CustomTkinter/Pillow/dotenv
dependencies + `DEMO_PATH` config), Phases 5–6 (match-list page, viewer rebuild), Phase 7 (docs
corrections, which are now substantial — see *Open questions*).

**Measured on a real 12.10 capture** (2 REPLAYDATA blocks, ~9.5 MB):

```
property blocks   33,655 (98.63% exact)
  rep layout      11,150 (99.75% exact)      <- 0% before the transform
  class net cache 22,505 (98.07% exact)
fields            40,742 (37,438 named)
movement rpcs     17,164 (0 failed)
moves            148,835 over 14 characters
```

## Decisions made

**The payload is obfuscated, not merely unparsed.** Riot whitens every content-block payload with a
keystream seeded `payload_bits ^ actor_net_guid`. Underneath it is stock UE. This is the entire
unlock and everything else follows from it.

**Ported from `github.com/michel-giehl/ValorantReplayParser` (MIT), not reverse-engineered.** That
project solved this; two independent investigations of it agreed on the mechanism. Its own
known-answer vectors are reproduced verbatim in `tests/test_payload_transform.py`.

**An unsupported build raises; there is no nearest-version fallback.** The archived upstream
silently falls back to the 12.10 transform. Copying that would make a porting bug and a version
mismatch indistinguishable. `vrf_net.py positions` exits **2** on an unsupported build, distinct
from the generic error code 1.

**Two handle encodings, not one.** Rep-layout state uses packed 1-based handles terminated by 0;
ClassNetCache/RPC uses a range-coded handle over the group's export count. Positions arrive on the
RPC path, so both were required. `flag_a` on the content block is `bHasRepLayout` — identified by
measurement (99.75% vs 40% parse rates), not assumption.

**Movement collection is opt-in** (`ReplaySession(collect_movement=True)`). It is the most expensive
thing in the pipeline and no existing consumer needs it.

**The property layer keeps values opaque.** A field is `(handle, num_bits, payload)`; naming needs
the export table, decoding needs a schema. Keeping them separate means a wrong schema can corrupt
the reading of a block but never its framing.

**`clean_packet_rate` is not the metric for this layer.** It is computed from bunch *headers* and
never enters a payload, so it is blind to property-layout errors — it sat at 99.98% throughout the
period when 100% of payloads were undecodable. `PropertyStats.rep_layout_rate` is the honest one.

## What did not work

**The prior sessions' conclusion that positions are absent was wrong, and the reasoning that
produced it was sound.** An investigation brute-forced the UE spawn transform across 2,700
(offset × scale) combinations against Abyss ground truth and correctly falsified it three ways
(253/286 opening bunches reporting "rotation but no location"; survivors aliasing onto a 22-bit
constant run; the first 17 bits identical across all ten pawns). It then concluded positions were
NOT RECOVERABLE. The flaw was scope: every probe ran against *scrambled bytes*, so no bit layout
could ever have matched. **Do not re-run any of that work** — it is sound about the spawn transform,
which genuinely is not present at any fixed offset, and irrelevant to positions.

**`docs/vrf-decoding-findings.md` § "The premise that did not hold" is now false.** The premise held.
The measured symptom it records — "leading packed integers decode to implausible values (billions,
not small handles)" — is exactly what a correct packed-int reader does on obfuscated bytes.

**The handle-width hypothesis was refuted, twice.** `read_int(61)` and `read_int(62)` using the
export table's real `NumExports` both scored 0/151, same as packed. The blocker was never the
handle encoding.

**Inferring code from a `diff` cost a debugging cycle.** The first port passed 51/55 vectors, failing
only 12.11 — because that version's byte loop ends with a trailing `SwapAdjacentBits` that the diff
rendered as an *unchanged context line*, so it was dropped. Read the upstream file verbatim; do not
reconstruct a function body from a diff hunk.

**The transform is not an involution.** It was documented as one; applying it twice does not return
the original bytes (verified at 64/287/288 bits). There is no encode path and none is needed.

**Heredocs failed twice on `\n` inside Python string literals.** Writing `"\\n".join(...)` through a
`bash` heredoc flattened to a real newline and produced a syntax error, twice. Use the Write tool for
files containing escape sequences, or build them with `chr(10)`/`chr(92)`.

## Environment facts

- **Interpreter:** `./.venv/Scripts/python.exe`, Python 3.11.14, Tk 8.6. Deps are pytest + ruff only;
  no runtime dependencies yet. `customtkinter`, `python-dotenv` are absent from both interpreters;
  Pillow 12.3.0 exists in *system* Python but not the venv. Phase 4 needs network for `uv add`.
- **Oodle resolves** via the cached Steam scan to an unrelated game's `oo2core_5_win64.dll`.
  `VRF_OODLE_DLL` is commented out in `.env` and `vendor/` holds only a README — the cache is what
  answers. Decompressing 2 blocks takes ~6 s.
- **Build census of `Demos/` (101 files):** only **21 are decodable** — 12.10 ×11, 12.11 ×5,
  13.00 ×5. Everything else (11.10, 11.11, 12.00, 12.04–12.09) has no transform and never will
  without a Ghidra pass on that build's binary. Read the build with a plain-header regex for
  `\+\+Ares-Core\+release-[0-9.]+`; no Oodle needed.
- **The canonical reference capture `039f3991…` is 11.11 and therefore cannot be used for position
  work.** New capture-backed tests use `Demos/03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf` (12.10,
  Haven) and `skipif` when absent, since `Demos/` is gitignored.
- **Upstream source is cloned** at
  `C:\Users\Dhina\AppData\Local\Temp\claude\E--Personal-val-replay-analyzer\e94118e0-f6b5-490e-93c8-cdf63946cdca\scratchpad\vrp`.
  Scratchpad, so treat it as disposable — re-clone with
  `git clone --depth 1 https://github.com/michel-giehl/ValorantReplayParser.git`.
- **Test/lint:** `runners\test.bat`, `runners\lint.bat`, `runners\format.bat`. Tests are
  `unittest.TestCase` classes but use **plain `assert` and `pytest.raises`** — `assertEqual` trips
  PT009 and `assertRaises` trips PT027. Class names must be CapWords with no underscores (N801), so
  transform classes are `Transform1210`, not `Transform12_10`.
- **Probe scripts** from this session live in the same scratchpad (`probe_real.py`, `probe2.py`,
  `probe3.py`, `probe4.py`). Superseded by `vrf_net.py positions`; delete freely.

## Open questions

**How much of `CLAUDE.md` should be rewritten, and when?** Three of its stated conventions are now
false: "No positions exist" (positions decode for 12.10+), the roster rule "nothing in the file links
a loadout to an actor net ID" (the archetype join closes 10/10 — established last session, still
unimplemented), and "No runtime dependencies" (Phase 4 breaks it deliberately). The plan defers all
of this to Phase 7. Leaving it stale through Phases 3–6 means the file actively misleads anyone
reading it — including a future agent. **Consider pulling the `CLAUDE.md` corrections forward.**

**`PlantedAtSite` appears in the rep-layout properties** (3,242 occurrences, the most common property
in the capture). `CLAUDE.md` states the spike site is not recoverable. Nobody has decoded the value
yet — it needs the schema layer — but the field is demonstrably on the wire. Cheap to check, and it
would close a documented gap.

**Credits, HP and armor remain out of reach**, and upstream confirms rather than solves this: all 279
`AresAttributeSet` exports are named `BaseValue`/`CurrentValue`, so attribute *identity* is not on
the wire. There is one untried lever — each attribute set is a distinct subobject with its own
NetGUID, and upstream's `ContentBlockPathResolver` resolves subobject paths. Nobody has tried it.

**The remaining 1.37% of property blocks fail** (461 of 33,655), mostly `rpc wants N bits, 7 left`.
Unclear whether this is a real framing gap or benign. It does not affect movement, which is 0-failure.

## Next steps

Commit first — a large body of new, working, lint-clean code should not stay untracked:

```bash
cd E:/Personal/val-replay-analyzer
git status --short          # confirm the 9 paths above
runners\test.bat            # expect 230 passed, 450 subtests
```

Then invoke the `commit` skill. Suggested split: one commit for the transform + its tests, one for
the property loop and movement, one for `THIRD_PARTY.md`. The `datachannel.py` hunk is pure
formatting — fold it in or drop it, but do not let it stand alone.

After that, **Phase 3** (positions into the model) is the natural continuation and the thing every UI
phase depends on. Re-read the plan's Phase 3 section; the shape is `model.Position`,
`Replay.positions`, and `Snapshot.positions` interpolated to `t` — while preserving `state_at`'s
recompute-from-scratch property, which is what makes backwards seeking correct.

Verify the decoder still works before building on it:

```bash
./.venv/Scripts/python.exe scripts/vrf_net.py positions \
  "Demos/03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf" --blocks 2
```

Expect 10 players in two clusters — five near `(1742, -2643)`, five near `(2946, -12715)` — plus a
few stationary ability actors.

## Cautions

- **Never add a nearest-version fallback to `payload_transform`.** It is the one failure mode this
  module is built to avoid.
- **Do not point position work at the 11.11 reference capture.** It will correctly refuse. The
  existing 11.11-based tests are fine and must keep passing untouched.
- **Do not pattern-match `/Game/Characters/*/X_PC`** to find player pawns — it over-collects
  ability-spawned clones (12 instead of 10 on one capture). Intersect against the event actor-ID set.
- The transform has **no redundancy and no self-check**: a wrong rotation still yields output of the
  right length that still looks random. Any change must be re-run against all 55 vectors.
- Movement has no per-record checksum beyond the 3-bit marker cycle, so a desynced move produces
  *plausible coordinates*. `batches_failed == 0` is the assertion that matters, not the move count.

## Suggested skills

- **`commit`** — first action, before anything else. Nine uncommitted paths including three new
  library modules; this is exactly what the skill exists for, and the repo's conventional-commit
  history should not be broken by a hand-written message.
- **`code-review`** — after committing, before Phase 3. Three new modules (~900 lines) written in one
  session, ported from another language, where a subtle arithmetic error yields plausible-looking
  output rather than an error. High value here specifically because the tests prove the *happy path*
  against known answers but cannot prove the error paths.
- **`handoff`** — again at the end of Phase 3 or whenever context runs short.

Not useful here: `init` (`CLAUDE.md` exists — it needs *correcting*, which is ordinary editing, not
re-initialisation), `security-review` (this change parses local files and opens no sockets),
`run` (the viewer is untouched this session and the CLI diagnostic is the faster check).

## Sensitive material

- `.env` holds a real `RIOT_API` value. It is read at runtime via `envfile.get("RIOT_API")`; never
  print, copy or commit it. `.env.example` is the safe template.
- `docs/039f3991_summary.md` contains player `subject` UUIDs. **Do not copy them into new files or
  send them anywhere** — reference the doc by path instead.
- `Demos/` filenames are match UUIDs. They are gitignored and safe to name in local paths (the tests
  already do), but do not publish them.
