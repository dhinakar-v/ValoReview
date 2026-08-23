# Deriving a 13.04 payload transform — handoff

23 August 2026 · branch `vd-1304-port` · `E:\Personal\ValoReview`

The user asked to "port it to 13.04" after both captures in `Demos/` failed to appear in the
browser. There is nothing to port — no 13.04 transform exists anywhere — so the work became
deriving one. A first, independent deliverable shipped along the way.

## Read these first

| What | Why it matters |
|---|---|
| `docs/payload-transform-13-04.md` | **The measured record.** Every number this session produced, the oracle calibration, the confirmed lever, the dead end. Written to be the durable artifact; this handoff does not repeat it. |
| `C:\Users\Dhina\.claude\plans\port-it-to-13-04-sprightly-iverson.md` | The approved seven-phase plan. Phases 1 and 2 are done; 3 onward are not. Read for the intended shape of the rest. |
| commit `6ae5d40` | Phase 1: the match list stops filtering to playable. |
| commit `e43ff2e` | Phase 2 findings + the parser patch. |
| `csharp/patches/README.md` | How to reapply the parser changes to a clean clone, and why each of the three exists. |
| `docs/archive/payload-decryption-20260821-2338-handoff.md` | The predecessor. Records that the five existing transforms were **ported from upstream, not reverse-engineered**, and the ruff N801 rule (`Transform1304`, never `Transform13_04`). |
| `CLAUDE.md` § *Match list*, § *Positions exist for supported builds* | Updated by `6ae5d40`. The house rules on the branch gate still bind. |

## State

**Working tree is clean** apart from `.gitignore` (adds `Demos1/`), which is not mine — leave it or
commit it with whatever else touches it. Both my commits are on `vd-1304-port`, branched from
`2fe3a29` on `vd-develop`.

**The sibling repo has uncommitted changes and that is deliberate.** `E:\Personal\ValorantReplayParser`
carries three modified/new files. It is a *separate git repository*, so nothing there is captured by
a commit here. They are preserved as `csharp/patches/0001-payload-capture.patch`. If that clone is
ever reset or re-cloned, reapply the patch and rebuild before doing anything else.

Done:

- **Phase 1 (shipped).** Both 13.04 captures list and open in the browser, carrying a `NO POSITIONS`
  chip. Verified against a live server, not just tests: Lotus reports 26 rounds, 10 players, 201
  kills, 282 event times, side swap — all from plain chunks. Full Python suite green (469 passed),
  ruff clean, 257 vitest tests + `tsc --noEmit` clean.
- **Phase 2 (complete, both answers decisive).** See the findings doc. In short: the structural
  version gates pass, and no published transform decodes 13.04.
- **Tooling.** Payload capture in the parser, plus two calibrated oracles.
- **A real bug fixed en route:** `tests/test_positions.py` `SpikePlantsAreRealCoordinates` had no
  `skipif` where every sibling class has one, so it *errored* rather than skipped on a machine
  without the reference capture.

Untouched: Phases 3–7. No transform has been written, and nothing is registered in
`payload_transform.TRANSFORMS`.

## Decisions made

**The match list shows unsupported builds rather than filtering them away.** The user asked for this
explicitly ("do it in sequence, but i want everything to be decoded") and it reverses a documented
decision in `CLAUDE.md`. The argument: a library holding *only* unsupported builds rendered as an
empty directory, which is a stronger wrong claim than a row admitting what it cannot do — and
positions are not all a capture states.

**The parser clone is patched, not forked, and the patch lives here.** `PayloadTransformRegistry`'s
constructor is private and `CreateDefault()` hard-codes its list, so there is no injection point; the
clone must be modified. Keeping the patch in `csharp/patches/` is what stops a clean re-clone
silently losing it. The user asked for exactly this route ("try to reuse csharp code by modifying").

**The capture transform is registered only when `VRF_PAYLOAD_CAPTURE` is set.** It passes payloads
through untouched, so registering it unconditionally would turn an unsupported build from a refusal
by name into a parse that succeeds and produces rubbish. That is the one failure the whole registry
is shaped to avoid. **Do not relax this.**

**Every rate is calibrated against a build whose answer is known before it is believed about one
whose is not.** This is why the capture transform can *replace* a published transform for the same
branch. Without a known-good run, a 0% score on 13.04 says nothing about whether the method works.
Any new oracle added from here should be calibrated the same way before its numbers are quoted.

**Nothing gets registered until ground truth passes.** The Python `decode` is never on the positions
path — `tracks.py:266` discards `transform_for`'s return and uses it as a gate — so registering 13.04
in Python alone unhides the captures and hands them to the C# decoder. If the two implementations
disagreed, nothing would complain; the coordinates would just scatter.

## What did not work

**Reversing the client.** `strings` over the installed 230 MB `VALORANT-Win64-Shipping.exe` returns
**zero** strings. It is packed, and unpacking it means fighting Vanguard. Do not spend time here.

**Finding a published 13.04 transform.** Checked exhaustively: upstream `ValorantReplayParser` at
`99d9646` tops out at 13.02 (`7106d5a`, 2026-07-29) with nothing in `git log --all`, `branch -a`,
`tag`, or `stash list`; the GitHub tree confirms the same five files; the archived
`ValorantReplayParserPlayground` has no transform code at all. Upstream keeps **no** derivation
tooling — no offsets, no script, no decompiler output, not one comment. Do not re-search this.

**Hoping an existing transform still works.** Scored at noise (best 0.06% against a calibrated
66.59%). Riot rotated the transform, as at every build before it.

**Hoping 13.04 reuses a known *structure* with new constants.** Testable cheaply because the first
block's constants do not participate — rejected, best 0.65% against a calibrated 7.44%.

**Anchoring on a constant plaintext bit.** This one is worth understanding before it is retried,
because the algebra is genuinely attractive. Every u64 operation moves bit 0 in one of two ways:
permutations (rotate, swap, reverse) make it some other input bit, and NOT/XOR/ADD/SUB all flip it
by a known amount — including the arithmetic ones, since a carry cannot reach the least significant
bit. So for a table-free composition, decoded bit 0 is exactly `input_bit_j ^ c`, and if bit 0 were a
constant `bDoChecksum` the pair could be read straight off the ciphertext. **It is not constant**:
decoding the 12.10 corpus with its own transform, bit 0 is zero in 48.00% of payloads with a 64-bit
first block and 38.90% of those that frame correctly.

**A first attempt at the block-1 oracle scored 0.00% even for the correct transform.** The cause was
a wrong attribute name (`reader.position`; it is `reader.pos`) swallowed by a bare `except
Exception`. If a new oracle reads as uniformly dead, suspect the harness before the hypothesis.

## Environment facts

- **`Demos1/` holds the full 101-capture reference library**, including
  `03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf` — the exact 12.10 capture `tests/test_positions.py:37`
  names as `DEMO_12_10`. That constant points at `Demos/`, where it is **not** present. Repointing or
  parameterising it is what unblocks the ground-truth suite. Build census of `Demos1/`: 12.10 ×11,
  12.11 ×5, 13.00 ×5 are decodable; the other 80 are not. There are no 13.01 or 13.02 captures.
- `Demos/` holds only the two 13.04 captures (Plummet, Lotus).
- Oodle resolves from an unrelated game install via `oodlefind.locate()`; it works, nothing to set.
- **A server was already running on port 8000 from another session**, pointing at `Demos1`, and
  silently shadowed mine. Use `--port 8123` or similar when spot-checking.
- **Another session works in this same tree.** A transient read returned pristine file contents
  mid-session. Everything was in fact intact — verify with `git diff --numstat` rather than trusting
  a single `grep` if files look reverted.
- Build the decoder with `.\runners\build-decoder.bat` from PowerShell; the `runners\...` path does
  not survive the Bash tool's escaping.
- Capture run, roughly 25 s for 80k payloads:
  ```powershell
  $env:VRF_PAYLOAD_CAPTURE = "$env:TEMP\claude\cap.jsonl"
  $env:VRF_PAYLOAD_CAPTURE_BRANCH = "++Ares-Core+release-13.04"
  $env:VRF_PAYLOAD_CAPTURE_LIMIT = "80000"
  & dotnet .\csharp\VrfPositions\bin\Release\net10.0\vrf-positions.dll <capture>.vrf out.json --hz 10
  ```
- The scratch oracles are in this session's scratchpad
  (`...\5dd81c1a-...\scratchpad\{oracle,block1,bit0}.py`) and are **disposable** — the findings doc
  carries everything they proved. Rewrite rather than hunt for them.

## Open questions

**Is the search worth the spend?** This is the one the user left open, and the session ended on it.
The remaining work is a C# search harness over roughly 5–6 operations from a ten-operation
vocabulary with eight operand choices each — a large build plus a compute run that may not converge.
The user's stated intent is "i want everything to be decoded", and they approved the full plan, so
the default reading is *proceed*. But they were explicitly offered the alternative of stopping with
Phase 1 shipped and the findings on record, and did not answer. **Ask before spending hours on it.**

**If it converges, what validates it?** `tests/test_positions.py` against a 13.04 capture. Its
thresholds were measured on 12.10; treat any that need moving as a finding, not a tuning knob.

## Next steps

1. Confirm with the user whether to build the searcher (see above). If yes:
2. Reapply the parser patch if the clone was touched, and rebuild:
   ```
   cd ../ValorantReplayParser && git status --short
   ```
   If clean, `git apply ../ValoReview/csharp/patches/0001-payload-capture.patch`, then
   `.\runners\build-decoder.bat`.
3. Write the search in **C#** — Python is roughly two orders of magnitude too slow. Vocabulary and
   the operand bound are in the findings doc under *The u64 lane's operands are a small set*.
4. **Validate the searcher by re-deriving 12.10's own `_u64` from the 12.10 corpus before pointing it
   at 13.04.** A searcher that cannot recover a known answer says nothing about an unknown one. Its
   target is in `libraries/vrfnet/payload_transform.py:292-301`.
5. Only then run it on 13.04, and follow the findings doc's closing section for the four constants —
   that part is cheap and near-certain, because the offset term is a `<< 25` and collapses to 128
   trials rather than 2³².

## Cautions

- **Never add a nearest-version fallback.** House rule, and this session's evidence supports it: the
  structure is not monotonic across builds, and a fallback would make a porting bug and a version
  mismatch indistinguishable.
- **Do not register `Transform1304` before ground truth passes.** `test_every_registered_build_is_covered`
  (`tests/test_payload_transform.py:156-158`) fires the moment a class is registered without its 11
  vectors — that tripwire is intended; let it fire rather than working around it.
- **Do not upstream the capture patch.** It is a tool, and a released decoder that passes payloads
  through would be actively harmful.
- **Do not `git reset`/`checkout` in either repo without checking `git status` first** — another
  session shares this tree, and the sibling repo's uncommitted changes are the only live copy of the
  parser patch besides the exported `.patch` file.
- Do not re-derive the negative results in *What did not work*; they were each measured.

## Suggested skills

- **`commit`** — as soon as anything is changed. There is uncommitted work in the tree today
  (`.gitignore`) and the sibling repo, and the project forbids running `git commit` directly.
- **`code-review`** — after the searcher exists. It will be a block of new, lightly-tested numeric
  code where a silent arithmetic error is indistinguishable from "the build's transform is different",
  which is exactly the failure this project has been bitten by before.
- **`handoff`** — again at the end, since this work spans sessions by nature.

Not useful here: `init` (`CLAUDE.md` exists and is the durable record), `artifact-design` and
`dataviz` (nothing to publish; the deliverable is a decoder), `run` (the app is already verified
end-to-end for Phase 1), and `security-review` (the change surface is a match-list filter and an
offline file parser).

## Sensitive material

The `.vrf` captures under `Demos/` and `Demos1/` contain real match and player identifiers, and both
directories are gitignored deliberately — **do not commit them, quote match GUIDs, or paste player
UUIDs into documents or issues**. Replay ids in the browser are digests of resolved paths and are
machine-local, so a URL from one machine means nothing on another; do not hard-code one in a test.
No API keys or credentials are involved anywhere in this work — `val-match-v1` is 403 on a personal
key and the whole API path was deleted from this project long ago.
