# Searching for 13.04's payload transform — handoff

23 August 2026 · branch `vd-1304-port` · `E:\Personal\ValoReview`

The previous session ended asking whether to build a search harness for 13.04's mixing functions.
The user was asked and answered **"Build the searcher"**. It is built, validated against three
builds whose answers are published, and it has produced a 64-bit lane for 13.04 that four
independent measures agree is correct. The 32-bit lane, the 8-bit lane and the four keystream
constants are still missing, so nothing is registered and no capture decodes yet.

## Read these first

| What | Why it matters |
|---|---|
| `docs/payload-transform-13-04-20260823-1041-handoff.md` | The predecessor. Its *What did not work* and *Cautions* sections still bind in full — do not re-derive them. |
| `docs/payload-transform-13-04.md` | The measured record from that session: oracle calibration, the confirmed lever, the dead ends. **Not yet updated with this session's results** — see *State*. |
| `csharp/TransformSearch/README.md` | Written this session. The tool's method, its four oracles with their calibrated numbers, the two priors that make the space enumerable, and its validation table. Everything about *how it works* is there and is not repeated here. |
| `C:\Users\Dhina\.claude\plans\port-it-to-13-04-sprightly-iverson.md` | The approved seven-phase plan. Phases 1–2 done previously; this session did phase 3–4 and most of 5. |
| `csharp/patches/README.md` | How to reapply the payload-capture patch to a clean parser clone. Still required before any corpus can be captured. |

## State

**Everything from this session is uncommitted.** `git status --short`:

```
 M .gitignore                     # not mine, pre-existing (adds Demos1/)
?? csharp/TransformSearch/        # the whole searcher, new
?? docs/payload-transform-13-04-20260823-1041-handoff.md   # previous session's handoff
```

Committing is the next agent's first action. `csharp/TransformSearch/bin` and `obj` are in that
untracked directory and must not be committed — check `.gitignore` covers them before staging.

### Done

**The searcher exists** — `csharp/TransformSearch/`, a standalone .NET 10 console project
referencing nothing (not the parser clone, not `libraries/`). Its only input is a JSONL corpus from
the capture patch. Seven source files, about 1,100 lines.

**It is validated.** `validate` recovers all three published builds the reference library holds
captures for, each at **rank 1** of thousands of surviving behaviours: 12.10 (depth 6, 1 of 14,177),
13.00 (depth 6, 1 of 508), 12.11 (depth **8**, 1 of 9,611). Separately, `emit` output was checked
against `vrfnet.payload_transform` bit for bit — three published sequences plus synthetic ones
covering **all ten** operation kinds, because the five published sequences never exercise `not` or
`rotl` and an untested op in the vocabulary is worse than a missing one.

**13.04's 64-bit lane, with high confidence:**

```
rotr7,xornot6,sub5,swap,add3,add2,rotl1
```

which is, spelled out: `rotr64(v, (ror7 % 63) + 1)` → `v ^ ~ror6` → `v - ror5` → `swap64` →
`v + ror3` → `v + ror2` → `rotl64(v, (ror1 % 63) + 1)`, where `ror_k = rotr32(state, k)` and, for
the first block, `state = seed`.

### Half-done

`csharp/TransformSearch/make-known-plaintext.sh` pools a known-plaintext set by decoding every
capture in a library whose build is already solved. It is **functionally correct but untested
end-to-end**, and it has one cosmetic defect worth fixing on sight: line 32 contains a literal
carriage-return byte inside `tr -d '…'` where the source should read `tr -d '\r'`. It works — `tr`
deletes the CR either way — but an invisible control character in source is a trap. The 3-capture
set the session actually used was built by hand and is enough for the work that remains.

### Untouched

The 32-bit lane, the 8-bit lane, the four constants, the Python port, registration, and ground
truth. That is phases 5–7 of the plan and is where the next session starts.

## Decisions made

**The searcher lives in the repo, at `csharp/TransformSearch/`.** Riot rotates the transform every
patch, so this is not single-use: 13.05 will need it again. It references nothing, so it neither
complicates the decoder build nor depends on the parser clone.

**Two priors bound the search, and both are written down as priors rather than facts.** The
load-bearing one is that **operands descend**: across all five published 64-bit lanes — 35 operand
uses — each successive `rotr32(state, k)` uses a strictly smaller k (8,6,5,4 / 8,6,4,3,2 / 8,6,3,1 /
5,4,1 / 6,3,2), never repeating and never ascending. That turns the operand choice for m operand ops
from 8^m into C(8,m) and collapses depth seven from ~10^12 compositions to ~5×10^8. `--loose`
relaxes it. This was discovered by reading the five transforms, not assumed, and it is the single
reason the search is affordable.

**Four oracles, each calibrated on a solved build before being believed about an unsolved one**, and
they are deliberately independent so agreement is evidence rather than one measurement counted
twice. Full numbers in the README. The important ranking among them:

- The **bit-bias fingerprint** (21 UE-framing bit positions) is the cheap one, used at every node.
  It separates correct from wrong by many sigma but its wrong-answer floor is *near* zero, not zero.
- The **known-plaintext** and **collapse** oracles have a wrong-answer floor of **exactly 0.00%**,
  which makes a single hit evidence in a way a bias score never is.
- **Collapse is the strongest and should be the first thing reached for next time.** It counts
  distinct ciphertexts within *one* capture that decode to the *same* plaintext — the same property
  update replicated to many actors, so different net GUIDs, different seeds, different ciphertext.
  Only a correct decode brings them back together. Because it compares a capture against itself it
  is the only one of the four that **cannot be confounded by how much content two builds share**,
  and a transform correct on a fraction *f* of payloads degrades it by roughly *f²*, so it is
  sensitive to a nearly-right answer rather than only to a wrong one.

**A bounded top-K heap replaced a threshold-plus-cap.** The first design kept every candidate under
a threshold up to a flat per-thread cap and dropped the rest — which discards by *arrival order*, so
a run that overflowed could have thrown away the answer and its ranking could not be trusted. The
heap only ever evicts a strictly worse candidate.

**The 32-bit and 8-bit lanes are NOT structural mirrors of the 64-bit lane, and this was checked
rather than assumed.** It is nearly true and the temptation is real, so the counter-examples matter:
13.00's 32-bit lane carries a `not` its 64-bit lane does not; 12.10's 64-bit lane has `xor ~ror4`
where its 32-bit lane has plain `xor rol4`. Same operation skeleton, same k order, but complement
placement differs — almost certainly because a `~` applies to a 32-bit intermediate and the
widening to 64 bits differs. So the other lanes are a small neighbourhood around the recovered
skeleton, not a free derivation. (Note also `rotl32(state,k) == rotr32(state,32-k)`, so a lane
reaching for the left-handed operand needs k in 24..31; `Ops.Stride` is 31 for this reason.)

**Nothing is registered until ground truth passes.** Unchanged from the previous session and still
right: `tracks.py:266` uses `transform_for` only as a gate and discards its return, so registering
13.04 in Python alone unhides the captures and hands them to the C# decoder. If the two
implementations disagreed nothing would complain and the coordinates would simply scatter.

## Why the 64-bit lane is believed correct

This is the part a fresh agent should not have to re-derive, because the evidence looked *negative*
for a while and the reversal came from fixing a measurement error.

| measure | correct decodes (3 solved builds) | **13.04 candidate** | runner-up | any wrong transform |
|---|---|---|---|---|
| bias, set bits/payload | 3.49 / 3.67 / 3.69 | 4.26 | 4.96 | 10.5 |
| opens as a handle chain | 81.9% / 81.2% / 80.9% | 78.0% | 73.8% | ~9% |
| known plaintext (held out) | 12.21% / 13.16% / 12.89% | 7.85% | 4.15% | **0.00%** |
| **collapse (within capture)** | **8.67% / 8.98% / 8.05%** | **8.29%** | 3.65% | **0.00%** |
| collapse, largest group | 128 / 102 / 100 | 116 | 66 | 1 |

Replicated on the *second* 13.04 capture, which the search never saw: collapse 9.60%,
known-plaintext 6.74%, against 0.00% / 0.00% for a control decode using 12.10's transform.

The known-plaintext row is the one that misleads. It sits well below the solved-build baseline,
which reads as "partially correct" — but the collapse row, which has no cross-build content
confound, sits squarely inside the correct band. A transform correct on only ~62% of payloads would
show collapse near 0.62² × 8.3% ≈ 3.2%, which is precisely what the runner-up shows and precisely
what the candidate does not. **The known-plaintext shortfall is content drift**: 13.04 is four
patches past the newest solved capture, on maps and with agents the older captures never held.

## What did not work

**Measuring overlap as distinct-values-in-common over distinct-set-size.** This is the error that
cost the most and nearly buried a correct answer. It made correct-vs-correct read 6.0% and the
candidate 2.5%, i.e. "clearly wrong". The right denominator is *payloads*, not distinct values — how
often does a decode produce something recognisable — which moved the candidate to 6.04% against a
correct-decode 10%. Do not compare decodes by set-overlap ratios; count payload hits.

**Concluding from a scalar that a candidate is wrong.** Two candidates each produced hundreds of
exact known-plaintext hits, which seemed impossible for wrong answers, and the same top shared
values appeared under both. The explanation was that the two compositions are *the same function on
53% of inputs*: they differ by `sub ror5` versus `add ror5, sub ror4`, which are equal exactly when
`ror4 == 2·ror5`, i.e. when bit 4 of the seed is clear. When two candidates behave alike, check
where they agree before theorising.

**Deeper search.** Depth 9 under the descending prior with k ≤ 8 walked **24.2 billion**
compositions in 10.5 minutes and found nothing better than the depth-8 leader — which is itself only
7 ops, so the space had room. Depth is not the missing ingredient.

**Widening the operand range.** Hill-climbing with k up to 31 (covering every `rotl32` the 32-bit
lanes use) is still a local maximum: none of 2,850 single edits improves the candidate. Combined
with the above, this is now evidence the candidate *is* the answer rather than evidence the space
was too small.

**Validating a full payload without the constants.** Only payloads with `bit_count == 64` are
decoded by `_u64` alone, and each 13.04 corpus holds exactly **one**. Everything longer needs
`state2`, hence the constants. There is no shortcut; do not go looking for one again.

## Environment facts

- **Git Bash converts `/c/...` paths in argv but not inside a `python -c` string.** A path that
  works as an argument fails as a literal. Pass scratch paths as `sys.argv`, never inline.
- **Python's `print()` writes CRLF on Windows**, so a file it generates and `read` consumes leaves a
  carriage return on the end of every field. The symptom is a path error naming a file that is
  plainly there. This broke `make-known-plaintext.sh` for all 21 captures.
- **An XML comment cannot contain `--`.** The `.csproj` failed to load on the house prose style —
  the same rule `tests/test_svg.py` exists to catch for committed SVGs. Consider whether that test
  should grow to cover `.csproj`.
- **`dotnet build` fails while the executable is running** ("used by another process"). A long
  background search blocks rebuilds; sequence them.
- Search throughput: **28–56M compositions/second on 12 threads**. Depth 8 ≈ 80 s, depth 9 ≈ 10.5
  min, both over a 64-payload stage corpus.
- A 200,000-line capture yields about **46,000 distinct 64-bit first blocks** after deduplication on
  `(seed, ciphertext)`. Deduplication is mandatory, not an optimisation — the stream re-sends the
  same payload thousands of times.
- Reference library build census (`Demos1/`, 101 captures, via `vrfhome.scan`): 12.10 ×11, 12.11 ×5,
  13.00 ×5 are solvable; there are **no 13.01 or 13.02 captures**, so those two transforms cannot be
  used for calibration here. `Demos/` holds the two 13.04 captures.
- Scratch for this session:
  `C:\Users\Dhina\AppData\Local\Temp\claude\E--Personal-ValoReview\dc758d38-…\scratchpad`. It holds
  the four corpora, the pooled `known.txt` (104,217 blocks), and the emitted plaintext files. All
  **regenerable** and safe to lose; the capture command is in `csharp/TransformSearch/README.md`.

## Open questions

**Is the recovered lane exactly right, or right on ~96% of states?** The collapse evidence puts
*f* between 0.96 and 1.0 and cannot distinguish further. Ground truth settles it and nothing else
will. If the constants are recovered and a full decode *almost* works, suspect this before
suspecting the constants.

**Does the descending-operand prior hold for 13.04?** The recovered lane uses 7,6,5,3,2,1 —
descending, consistent — but it was *found under* the constraint, so this is not independent
confirmation. The hill-climb that ignores the prior did not move off it, which is weak support.

## Next steps

The remaining chain is: recover the four constants → derive the 32-bit and 8-bit lanes → port to
`payload_transform.py` → register → validate against ground truth.

**Start with the constants, and use the 32-bit lane to get them.** The findings doc's algebra
assumes `state2` can be observed, and it cannot be directly — it has to be recovered jointly with
the 32-bit lane. The cheapest route found this session:

1. Enumerate 32-bit-lane variants from the recovered 64-bit skeleton — same op order and same k
   order, varying only complement placement (`xor` vs `xor ~`, an inserted `not`), with widths 32
   and `% 31` in the rotate distance. Expect fewer than about sixteen.
2. For one seed carrying many payloads with `bit_count >= 96`, brute-force `state2` over 2^32 and
   keep the value whose block-2 decode continues the handle chain across all of them. Roughly 10 s
   per variant on twelve threads.
3. Recover `mixed` from `state2`: iterate `mixed` over 2^32 and keep those with
   `hi32(prng_b0 + mixed * MULTIPLIER) == state2`. `prng_b0` needs only the seed, so it is already
   computable. Expect about one solution.
4. Repeat for a second seed, then solve the constants: for each of the 128 surviving values of the
   offset term (it is a `<< 25`, so only the low seven bits of `seed ∓ init_a_offset` survive),
   invert `x ↦ ((x >> 15) ^ x) >> 12 ^ x` to get `seed_plus`, hence `seed_addend`; the second seed
   pins `init_a_offset` and the sign. `tail_xor` is the low byte of `seed_addend` in all five known
   builds — a cross-check, never a licence to invent one.
5. Cross-check step 4 against the ~331 payloads with `bit_count` in 65..71, whose only unknown past
   the first block is the single tail byte `(state2 & 0xFF) ^ tail_xor`.

First command, to re-establish the corpora (about 25 s each):

```powershell
$env:VRF_PAYLOAD_CAPTURE = "$env:TEMP\claude\cap1304.jsonl"
$env:VRF_PAYLOAD_CAPTURE_BRANCH = "++Ares-Core+release-13.04"
$env:VRF_PAYLOAD_CAPTURE_LIMIT = "200000"
& dotnet .\csharp\VrfPositions\bin\Release\net10.0\vrf-positions.dll .\Demos\<the Lotus capture>.vrf out.json --hz 10
```

Then confirm the searcher still reproduces this session's result before building on it:

```
dotnet csharp/TransformSearch/bin/Release/net10.0/transform-search.dll validate \
    --corpus <12.10 corpus> --expect 12.10 --depth 6
```

Validation must come first every time. A searcher that cannot recover a known answer says nothing
about an unknown one, and that rule caught a broken harness in the previous session.

## Cautions

- **Do not register `Transform1304` before ground truth passes.**
  `test_every_registered_build_is_covered` (`tests/test_payload_transform.py:156-158`) fires the
  moment a class is registered without its 11 vectors — that tripwire is intended; let it fire.
- **Never add a nearest-version fallback.** House rule, and this session strengthens the evidence:
  13.04's lane shares no structure with 13.02's.
- **The sibling parser clone `E:\Personal\ValorantReplayParser` still carries three uncommitted
  files** and is a separate git repository. They are the payload-capture patch and the only live
  copy besides `csharp/patches/0001-payload-capture.patch`. Do not `git reset`/`checkout` in either
  repo without reading `git status` first; another session may share this tree.
- **Do not upstream the capture patch.** A released decoder that passes payloads through untouched
  would be actively harmful.
- Do not re-derive anything in the predecessor handoff's *What did not work* — the packed client,
  the search for a published 13.04 transform, the constant-plaintext-bit anchor. Each was measured.
- `csharp/TransformSearch/bin/` and `obj/` sit inside the new untracked directory. Confirm they are
  ignored before `git add`.

## Suggested skills

- **`commit`** — first, before anything else. The whole searcher is untracked and the project
  forbids running `git commit` directly. Consider two commits: the tool, then the docs update.
- **`code-review`** — immediately after committing, on `csharp/TransformSearch/`. It is exactly what
  the previous handoff anticipated: a block of new, lightly-tested numeric code where a silent
  arithmetic error is indistinguishable from "the build's transform is different". The parity checks
  against Python cover the ten primitives; nothing yet covers the search, heap, or dedup logic.
- **`handoff`** — again at the end. This work spans sessions by nature.

Not useful here: `init` (`CLAUDE.md` exists and is the durable record), `run` (nothing user-facing
changed; the app is unaffected until a transform is registered), `artifact-design` and `dataviz`
(the deliverable is a decoder, not a document), and `security-review` (an offline file parser and a
search harness, no network and no untrusted input beyond replay files already parsed elsewhere).

## Documentation debt

`docs/payload-transform-13-04.md` is the durable measured record and **has not been updated with
this session's results**. It still says the 64-bit lane is open. It should gain: the descending-
operand prior, the four oracles with their calibrated numbers, the collapse test and why it is the
strongest, the recovered lane, and the evidence table above. Doing that as part of the first commit
is better than deferring it — `CLAUDE.md` calls that file the record, and a record that lags is
worse than one that admits uncertainty.

## Sensitive material

The `.vrf` files under `Demos/` and `Demos1/` contain real match and player identifiers, and both
directories are gitignored deliberately — **do not commit them, quote full match GUIDs, or paste
player UUIDs into documents or issues**. Capture filenames are referenced here only by short
prefixes; recover full names from `vrfhome.scan` over the directory rather than from a document.
The captured JSONL corpora are payload ciphertext from real matches and belong in scratch only —
never commit one. Replay ids in the browser are digests of resolved paths and are machine-local, so
a URL from one machine means nothing on another; never hard-code one in a test. No API keys or
credentials are involved anywhere in this work.
