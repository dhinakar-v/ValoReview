# Handoff — vrfview, the 2D replay viewer

**Date:** 2026-08-21 20:04 · **Branch:** `vd-develop` · **Repo:** `E:\Personal\val-replay-analyzer`

This session built the application layer on top of the decoder. The previous session's handoff
covered the decoder itself and is still accurate for that half.

## Read these first, in order

| Path                                                               | What it is                                                                                                                                                                                                              |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/HANDOFF.md`                                                  | **The prior session's handoff.** Decoder state, the property-payload blocker, and the M0–M8 milestone plan. Still current for everything below the viewer. Note it moved from the repo root this session — see _State_. |
| `docs/vrf-decoding-findings.md`                                    | What was measured against the reference capture, layer by layer. The status table is the authority on what the decoder can and cannot reach.                                                                            |
| `docs/039f3991_summary.md`                                         | Key/value digest of the reference capture. §8 is the "what is not in this file" list the viewer's provenance panel mirrors.**Contains player `subject` UUIDs — do not copy them into new files or send them anywhere.** |
| `C:\Users\Dhina\.claude\plans\can-you-create-an-linked-eclipse.md` | The approved plan for this session's work, with the verification commands.                                                                                                                                              |
| `git log 4a2bd68..HEAD`                                            | Eleven commits.`2fd087f` is the viewer; `2efd1b8` is a correction to the docs that everything else depends on.                                                                                                          |
| Module docstrings in`vrfview/`                                     | Each states what it measured and what it refuses to assume.`infer.py` and `state.py` are the two worth reading before changing anything.                                                                                |

Nothing below repeats those.

## State

**Complete and committed.** The viewer works end to end on all 101 demos. 74 tests pass
(`python -m unittest discover -s tests`). The previous session's untracked decoder work is now
committed too — that was the first action here, as the prior handoff instructed.

**Three uncommitted items, none of them mine:**

- `HANDOFF.md` → `docs/HANDOFF.md`. The file was moved externally partway through the session
  (git shows ` D HANDOFF.md` plus `?? docs/HANDOFF.md`). I left it alone because it was not my
  change. Committing the move is a reasonable first action.
- `ruff.toml` appeared at the repo root mid-session, timestamped April. It selects nearly every
  ruff rule group and ignores `E501` among others. **Ruff is not installed** in either interpreter,
  so no code in this repo has ever been linted against it. If the intent is to enforce it, that is
  a real piece of work — the config is strict (`D`, `ANN`-adjacent, `S`, `TRY`, `FBT`, `PTH`,
  `COM`) and the existing decoder modules were written before it existed.
- Nothing else. The tree is otherwise clean.

**Untouched:** milestones M4/M6/M7/M8 from the prior plan. The Riot match-details API work (M6/M7)
is still the cheapest route to player names, teams, economy and event-anchored positions, and the
viewer was deliberately built with `infer.py` as the seam where such a provider would plug in.

## Decisions made

**The 2D view is a schematic, not a minimap — and the user approved this explicitly.** The original
ask was "all the rounds in 2D space", which implies positions. There are none. I put the options to
the user (schematic offline / real minimap via Riot API / both layered) and they chose the offline
schematic. Do not quietly reinterpret this as a degraded minimap or start hunting for coordinates
to fill it in; the scene draws a `SCHEMATIC — node positions are layout, not map coordinates`
watermark for exactly this reason.

**Tkinter, and no new dependency.** Confirmed Tk 8.6 on both the system Python 3.11.9 and the
project `.venv` (3.11.14). The repo's stdlib-only rule holds.

**`characterDeath.args[1]` is the killer and `args[2]` the victim.** The summary doc had this
backwards and the K/D table was inverted by the same error; both are fixed in `2efd1b8`. The
evidence, because it is worth not re-deriving: under the old reading all 15 rounds contain a player
who dies twice, and in round 1 actor 646 dies at 87.3s, dies again at 105.3s, then scores a kill at
114.0s. Under the corrected reading **0 of 15** rounds have a repeat victim, 13/15 end on an exact
five-player wipe, the scoreline is a coherent 9–2, and every player on the winning side is positive
K/D while every player on the losing side is negative. `test_killer_victim_order_is_not_reversed`
pins it.

**Teams are derived exactly, not heuristically.** §8 of the summary lists team assignment as
absent, but the kill graph is bipartite: 0 same-team kills in 108, and exactly one 5v5 split,
confirmed unique by exhaustive search over all 126 candidates. The shipped implementation is BFS
two-colouring rather than that exhaustive search, because it is O(V+E) and does not assume ten
players or a 5v5 — it degrades honestly to "unknown" on an odd cycle instead of voting.

**Round outcomes take the first terminal condition and stop.** A team losing all its players names
a winner. A defuse or explode records the _reason_ but leaves the winner unknown, because spike
events carry no actor ID (`spikePlanted.args == [4]`, nothing more), so which side planted is not
recoverable. Reference capture: 11 wipes, 1 defuse, 1 explode, 2 left undetermined. Those two stay
undetermined — consistent with the prior handoff's instruction not to quietly resolve gates.

**Snapshots are stateless.** `state_at()` recomputes everything from scratch each frame. Measured
at 0.014 ms against a 16.7 ms budget at 60 fps, because a match is only ~150 events. This is what
makes backward scrubbing, drag-seeking and speed changes correct with no special cases; do not
"optimise" it into an incremental model.

**The entry point is `vrf_view.py`, not `vrfview.py`.** A root script cannot share a name with a
package beside it — the package wins the import, so `import vrfview` never reached the script. The
rename mirrors the existing `vrf_net.py` / `vrfnet/` pairing. I hit this only because a test
imported the module; it would otherwise have stayed latent.

## What did not work

**Small synthetic test fixtures produced nonsense.** My first test rosters used two- and
four-actor "teams". Two problems, both of which cost a full debug cycle: a team of size 2 hits the
wipe threshold after two deaths, so nearly every round reported `wipe`; and a kill graph in several
disconnected two-actor components has many equally valid global splits, so the component-join
heuristic — not the code under test — decided the fixture. The fix is `establish()` in
`tests/test_vrfview.py`: two setup rounds whose kills form a connected path 1-2-3-…-10, giving one
component and a real 5v5. **If you add inference tests, build on `establish()`/`scenario()`; do not
write a fresh three-actor fixture.**

**Writing Python via bash heredocs corrupts content.** The prior handoff warned about this and it
bit again — a heredoc carrying triple-quoted Python strings died with `unexpected EOF while looking for matching`. Use the Write tool for new files and the Edit tool for patches. For scripted
multi-edit patches, write the patch script to the scratchpad with Write and then run it; that
worked reliably.

**`vrf_net.py actors` only decodes `block000`.** I checked all 31: `block000_replaydata.bin`
resolves 55 channels, and blocks 001–030 every one fails with either `unknown PathNameIndex N` or
`external data consumed 1 bytes, ExternalOffset said <huge>`. So the actor layer is 1-of-31, not
generally working. This matters if anyone is tempted to mine agent identity from the bitstream —
the 8 agent codenames are visible only in the pre-round block and cannot be linked to the 10 event
actor IDs anyway.

**Stipple was the wrong way to fake alpha.** Tk canvases have no alpha channel. I planned
`stipple="gray50"` and switched to colour blending (`theme.blend` lerps toward the background,
`theme.ramp` precomputes 16 steps at startup). Blending looks continuous where stipple looks like a
screen door.

## Environment facts

- **Reading a `.vrf` for the viewer needs no Oodle DLL.** `VrfFile(path)` plus `dump_events` /
  `dump_container_header` / `dump_demo_header` / `dump_match_metadata` returns everything in
  **0.04 s** on the 47 MB reference capture. Oodle is only for data-block decompression, which the
  viewer never does. `test_vrf_loads_without_oodle` monkeypatches `Oodle.discover` to raise, to
  keep it that way.
- Python 3.11.9 (system, `D:\python311`) and 3.11.14 (`.venv`). Both have Tk 8.6. No third-party
  packages anywhere; `.venv` has only pip/setuptools.
- `python -m unittest discover -s tests` — 74 tests, ~0.22 s. No pytest.
- `Demos/` holds 101 `.vrf` files and `out/` holds the JSON plus 31 decompressed blocks; both are
  gitignored, so every test touching them is `skipUnless`-guarded and the suite passes on a clean
  checkout.
- **Library survey** (25 demos parsed, 0 failures): round counts run **15–26**; **4 of 25 carry 11
  actor IDs**, not 10. The eleventh is a reconnect — a player who dropped and rejoined under a new
  ID, provable because the two activity spans are disjoint. `4f1f51bc-*.vrf` is the fixture for
  that path (actor 1058 runs 66–889 s, 25604 runs 1079–2769 s). Do not hardcode ten players.
- Existing code wraps at up to **88 columns**, not 79 — `vrf_reader.py` has 31 lines over 79. The
  viewer matches that.
- **Screenshotting the Tk window**, which there is no built-in way to do: launch the app with
  `Start-Process` from the PowerShell tool, `Start-Sleep`, then `CopyFromScreen` via
  `System.Drawing` and save a PNG, cropping with `Bitmap.Clone`. Scripts for this are in the
  session scratchpad; re-create them rather than hunting for them.

## Open questions

- **Is `ruff.toml` meant to be enforced?** Ruff is not installed and nothing has been linted
  against it. Adding it as a dependency contradicts the stdlib-only rule the prior handoff set, so
  this needs the user's call. Guessing wrong either way wastes a session: enforcing it means
  reworking every module for `D`/`S`/`TRY`/`COM`, ignoring it means the config sits there lying
  about the project's standards.
- **Should the `docs/HANDOFF.md` move be committed?** It is the user's reorganisation, left
  untouched deliberately.
- **ATK/DEF sides are recoverable in a limited way, and I did not build it.** A round that both
  resolves by elimination _and_ ends in a defuse (defenders won) or explode (attackers won) pins
  the winning team's side for that half. Rounds 4, 11 and 13 of the reference capture are
  candidates. It would need consistency-checking within each half of the `switchTeams` boundary and
  a `CONFLICT` state rather than a guess. Worth doing only if the user wants side labels; the
  current UI says "Team A / Team B" and marks the swap, which is honest as-is.

## Next steps

**Recommended: `code-review` on the viewer, then decide the ruff question.** `2fd087f` is ~2,700
lines of new code. The model, inference and snapshot layers are well covered by the 74 tests, but
`scene.py`, `controls.py` and `app.py` are Tk rendering code verified by screenshot and a
render-loop smoke test, not by assertions — that is where a correctness pass pays.

First command:

```
python -m unittest discover -s tests && python vrf_view.py Demos\039f3991-5472-4119-bed2-838da0935f60.vrf
```

Then `git log -1 --stat 2fd087f` to see the surface area.

If the user would rather add capability than harden what exists, the prior handoff's
recommendation still stands and is unchanged by this session: **M7, aligning the decoded kill graph
against the Riot match-details API**, which yields names, teams, economy, weapons and
event-anchored positions without touching the bitstream blocker. This session makes it easier —
teams and per-round kill sequences are now derived, so the alignment has more structure to match
on. The caveat from the prior handoff is unresolved and still binding: **ask the user which match
to target first**, since the reference capture is from 2025-12-28 and is probably past Riot's
retention window.

## Cautions

- **Do not weaken a test to make something pass.** The clean-packet rate and the
  no-repeat-victim invariant are the two honest signals in this repo; both collapse rather than
  degrade when something is wrong, which is what makes them useful.
- **Do not add agent names, player names, or ATK/DEF labels to the scene.** None are recoverable,
  and the UI's credibility rests on the provenance panel being true. Inferred values carry a `*`;
  keep that discipline.
- **Do not dump the live Valorant client.** Unchanged from the prior handoff: Vanguard is
  kernel-level and Riot bans for it. Offline `.vrf` parsing is the only sanctioned route.
- `git mv` followed by an edit does not stage the edit — I amended `5773221` to fix exactly that.
  Check `git status` after a rename-plus-edit.

## Suggested skills

- **`commit`** — first, for the `docs/HANDOFF.md` move and whatever is decided about `ruff.toml`.
  The tree should not stay dirty across sessions. Use the skill rather than raw `git commit`; it
  produces Conventional Commits with no AI attribution, matching the eleven commits already there.
- **`code-review`** — after committing, targeted at `2fd087f`. The Tk layer is the untested part
  and the natural target.
- **`init`** — still worth one run. There is no `CLAUDE.md`, and the conventions are now firmer
  than they were: stdlib-only, `unittest` not pytest, 88-column wrap, evidential module docstrings,
  develop against `out/039f3991_blocks/*.bin`, and the Write-tool-not-heredoc rule that has now
  cost two sessions.
- **`run`** — newly applicable. The prior handoff said "no app to launch"; there is one now
  (`python vrf_view.py <path>`), so this skill is the quick way to see a change working.

Not useful here: `dataviz` and the artifact/design skills — the deliverable is a desktop Tk window,
not a chart or a published page. `claude-api` — no LLM code in this project. `security-review` —
the viewer reads local files and makes no network calls.

## Sensitive material

No credentials or keys are involved in anything this session touched; the viewer is entirely
offline and makes no network calls.

Two things to keep contained. `docs/039f3991_summary.md` and the `playerLoadouts` block inside
`out/039f3991.json` contain player `subject` and `characterId` UUIDs — pseudonymous identifiers for
real people. Treat them as do-not-copy: reference the file path rather than quoting values, and do
not paste them into new documents or send them to any external service. `out/` is gitignored;
keep it that way.

If M6/M7 is built later, the Riot local API flow reads a **lockfile password** from
`%LOCALAPPDATA%\Riot Games\Riot Client\Config\lockfile` and derives a bearer token. Read it, use
it, discard it — never log, print, or commit either value.
