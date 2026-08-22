# Handoff — VRF replication-stream decoder

**Date:** 2026-08-21 · **Branch:** `vd-develop` · **Repo:** `E:\Personal\val-replay-analyzer`

## Read these first, in order

| Path | What it is |
|---|---|
| `docs/vrf-decoding-findings.md` | **Start here.** Everything measured against the capture: layer-by-layer status, corrections to the research doc, resolved version gates, and the blocker. Written this session. |
| `docs/vrf-decoding-research.md` | Prior literature review of the UE replay wire format. Useful, but **partly wrong for this title** — see the corrections section of the findings doc before trusting it. |
| `C:\Users\Dhina\.claude\plans\can-you-propose-a-hidden-sun.md` | The approved plan (milestones M0–M8 with acceptance tests). |
| `docs/039f3991_summary.md` | Key/value digest of the reference capture. Its §8 "What Is Not in This JSON" is the target list. |

Nothing in this document repeats those. It covers only what a fresh agent cannot recover by
reading them.

## State

M0–M3 complete, M2 complete, M5 half-complete. M4/M6/M7/M8 untouched. Status table, metrics and
reproduction commands are in the findings doc — do not re-derive them.

**All work is untracked.** `git status` shows `?? vrfnet/`, `?? tests/`, `?? vrf_net.py`, plus the
pre-existing untracked `vrf_reader.py`, `vrf_to_json.py`, `docs/`, and a modified `.gitignore`
(adds `Demos/`, `out/`). Nothing has been committed — the repo still has a single `Initial commit`.
**Committing is the first thing to do**, before any further edits.

`pipprobe/` is a stray `six-*.whl` from an earlier environment probe. Unreferenced, safe to delete.

## Environment facts that cost time to discover

- **No pytest, no third-party packages.** Repo is stdlib-only; `.venv` has just pip/setuptools.
  Tests use `unittest`: `python -m unittest discover -s tests`. Do not add a pytest dependency
  without asking.
- Python 3.11. Windows. Both a PowerShell tool and a Git Bash tool are available; they take
  different syntax.
- **Develop against `out/039f3991_blocks/*.bin`** — 31 pre-decompressed blocks, ~123 MB, gitignored.
  No Oodle DLL needed in the test loop. `block000_replaydata.bin` (144 KB) is the fast iteration
  target; `block002` (8.7 MB) gives enough packets for statistically meaningful calibration.
- `Demos/` holds 101 `.vrf` files, gitignored.
- Writing large Python files via a bash heredoc **corrupts backslashes** (`\n` in source becomes a
  real newline). Use the Write tool for new files and the Edit tool for patches. This bit me twice.

## The one blocker

The property payload interior. Full evidence, the two candidate hypotheses, and every variant
already ruled out are in the findings doc under *"The premise that did not hold"* — **read that
before writing any code**, so you do not repeat searches that returned zero.

Short version: content-block framing is confirmed, but the documented
`[packed handle][packed NumBits][payload]` loop yields zero clean parses inside it. Likely
`ReceiveProperties_r` (no bit lengths on the wire) rather than `..._BackwardsCompatible`, which
would make a schema mandatory rather than optional.

The payoff if it cracks: `BombPlayerState_C` handle **23 is named `Subject`** — the actor → player
UUID link that `docs/039f3991_summary.md` §8 says is absent from the file. Handles for `PlayerId`,
`CompetitiveTier`, `PlayerInfo`, `Ping` sit alongside it. Inspect with:

```
python vrf_net.py exports out/039f3991_blocks/block000_replaydata.bin --filter BombPlayerState
```

## Where to go next — recommendation

**Do M7 before pushing further on the payload interior.** It needs no bitstream work at all: the
108 already-decoded `characterDeath` events carry `(time, killer_actor_id, victim_actor_id)`, and
the Riot match-details API returns the same 108 kills keyed by puuid. Aligning the two kill graphs
is a 10×10 assignment problem in plain Python, and it delivers names, teams, economy, weapons and
damage — most of the §8 gap list — without solving the blocker. See plan M6/M7.

Caveat already flagged to the user and unresolved: the reference match was recorded 2025-12-28,
roughly eight months ago, so it is probably past Riot's match-history retention window and may
404. Plan M6 includes a `scan-demos` step to find the newest of the 101 demos to pair instead.
**Ask the user which match to target before writing the API client** — a wrong guess wastes the
one match with a live oracle.

If you do continue on the payload interior instead, the productive method this session was:
enumerate candidate bit layouts, score each by "consumes to exactly zero leftover bits" over
thousands of real packets, and treat near-ties as *undetermined* rather than picking a winner.
That is what `vrfnet/calibrate.py` does, and it is worth extending rather than hand-decoding.

## Cautions

- **Do not dump the live Valorant client.** Vanguard is kernel-level and Riot bans for it. Offline
  `.vrf` parsing is safe and is the only sanctioned route. The research doc explains this.
- **Do not weaken an acceptance test to make a milestone pass.** The clean-packet rate is the only
  honest signal the decoder has; a wrong bit layout collapses it rather than degrading, which is
  precisely what makes it useful.
- Gates the capture cannot exercise (`legacy_close_reason`, which of four flag bits is `bPartial`)
  are recorded as undetermined at the point of use. Keep them that way — do not quietly resolve
  them to make output look cleaner.
- No `CLAUDE.md` exists yet. Style conventions were inferred from `vrf_reader.py` and are described
  in the module docstrings of `vrfnet/`.

## Suggested skills

Call these with the Skill tool:

- **`commit`** — first action of the session. All the work above is untracked; the repo has one
  commit. Use this skill rather than raw `git commit`; it produces Conventional Commits messages
  with no AI attribution. Consider several commits (bit reader + tests, frame/packagemap layer,
  bunch layer + calibration, actors/session/CLI, docs) rather than one.
- **`code-review`** — after committing. `vrfnet/` is ~1,100 lines of new bit-manipulation code with
  only the bit reader unit-tested; the frame, bunch and actor layers are covered by end-to-end
  metrics but not by tests. Good target for a correctness pass.
- **`init`** — worth running once. There is no `CLAUDE.md`, and the stdlib-only/unittest/
  develop-against-decompressed-blocks conventions are exactly what it should capture so future
  sessions do not rediscover them.

Not useful here: `run` (no app to launch), the artifact/design/dataviz skills (no visual
deliverable requested), `claude-api` (no LLM code in this project).

## Sensitive material

No credentials or keys are involved. Note for when M6 is built: the Riot local API flow reads a
**lockfile password** from `%LOCALAPPDATA%\Riot Games\Riot Client\Config\lockfile` and derives a
bearer token. Never log, commit, or print either — read, use, discard. `out/` is gitignored, but
API responses cached there contain player Riot IDs and puuids, so keep it that way.
`docs/039f3991_summary.md` already contains player `subject` UUIDs; treat them as pseudonymous
identifiers and do not copy them into new files or send them anywhere external.
