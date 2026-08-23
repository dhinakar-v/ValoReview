# Deriving a payload transform for `++Ares-Core+release-13.04`

Measured truth about an unfinished piece of work. What is written down here is
what was established by running something, and the open questions at the end are
stated as open questions.

## Why this exists at all

The two captures in `Demos/` are both `++Ares-Core+release-13.04`, and
`payload_transform.SUPPORTED_BRANCHES` holds 12.10, 12.11 and 13.00–13.02. So
neither decodes.

**There is nothing to port.** Upstream `ValorantReplayParser` tops out at 13.02
(`7106d5a`, 2026-07-29) — no branch, tag or stash mentions 13.03 or 13.04, and
the archived `ValorantReplayParserPlayground` carries no transform code at all.
Upstream also preserves no derivation tooling: no offsets, no extraction
script, no decompiler output, and not one comment in the transform files. Its
single statement of provenance is a README credit for LLM-assisted reverse
engineering of the client.

The client cannot supply it either. `strings` over the installed 230 MB
`VALORANT-Win64-Shipping.exe` returns **zero** strings — it is packed, so the
route upstream used is closed here.

So the transform has to be derived from the captures themselves.

## What is settled

**The build is the only thing missing.** `csharpdecode.run` on a 13.04 capture
refuses with

    Unsupported VALORANT replay version: no payload transform is registered
    for replay branch '++Ares-Core+release-13.04'.

`ValorantReplayReader.GetUnsupportedReason` checks `ReplayVersion 5.3.2`,
`GameNetworkProtocolVersion 0`, `UE4Version 522` and `UE5Version 1009` **before**
it looks a transform up. Reaching the transform check means 13.04 moved none of
them, so nothing in the net stack needs revisiting.

**The oracle, and what a right answer scores.** A transform has no checksum and
no redundancy, so wrong output is the right length and looks random. What
separates right from wrong is that underneath the whitening the bits are stock
UE: one bit, then `SerializeIntPacked` (handle, num_bits) pairs, terminated by a
zero handle, consuming the payload to **exactly** zero bits left. Scored over
20,000 real payloads captured from the 12.10 reference capture:

| transform applied | frames |
|---|---|
| none | 0.00% |
| **12.10 (the right one)** | **66.59%** |
| 12.11 | 0.00% |
| 13.00 | 0.00% |
| 13.01 | 0.01% |
| 13.02 | 0.00% |

66% rather than 100% because the corpus mixes rep-layout and ClassNetCache
content blocks and only the former carries a handle chain. The separation is
about 6,600:1, which is what makes every number below worth anything.

**No published transform decodes 13.04.** The same scoring over 20,000 payloads
from `e4fddb4e-…` (Lotus, 13.04): 12.10 0.01%, 12.11 0.04%, 13.00 0.00%,
13.01 0.01%, 13.02 0.06%, none 0.04%. All noise. Riot rotated the transform at
13.04, as it has at every build before it.

**The first block is keyed by a state that is already known.** `apply` sets
`state = seed` and only advances afterwards, and `seed = bit_count ^
actor_net_guid` is plaintext in the bunch header. `seed_addend`,
`init_a_offset`, `init_a_adds` and `tail_xor` reach the keystream only through
`prng_a`, which first matters at block two. Verified rather than assumed: for a
12.10 payload, `_u64(chunk, seed)` reproduces `apply`'s first eight bytes
exactly. This is what splits the problem into "recover the three mixing
functions" and then "recover four constants", instead of one joint search.

**13.04's `_u64` is none of the five known mixings.** Scoring first blocks
alone, with a chain-opening oracle (checksum bit, ascending handles, field
lengths that fit) calibrated the same way — 12.10's own `_u64` scores 7.44% on
the 12.10 corpus against 0.03–0.97% for the other four. On the 13.04 corpus the
best of the five is 0.65%, i.e. nothing.

**The u64 lane's operands are a small set.** Across all five builds the 64-bit
mixer draws its state operands only from `_rotr32(state, k)` with k in 1..8.
The arbitrary multipliers (`0x533`, `0x79`, `0x0CC6DB61`, `0x2751B`, …) appear
**only** in the 8-bit lane. So the u64 search space is a composition of roughly
five or six operations over a vocabulary of about ten — bit reversal, adjacent
bit swap, substitution table, NOT, add/subtract/xor a rotated state, and rotate
by `(rotated state % 63) + 1` — with eight operand choices each. Large, but
enumerable, and nothing like the space the arbitrary constants would have made.

**Operands descend, and that is what makes the space affordable.** Across all
five published 64-bit lanes — 35 operand uses — each successive
`rotr32(state, k)` uses a strictly smaller k: 8,6,5,4 then 8,6,4,3,2 then
8,6,3,1 then 5,4,1 then 6,3,2. Never a repeat, never an ascent. That turns the
operand choice for m operand ops from 8^m into C(8,m) and collapses depth seven
from about 10^12 compositions to 5×10^8. It is a **prior** read off five
transforms, not a fact about the sixth, so the searcher's `--loose` relaxes it
and `validate` is what proves a run under it still recovers a known answer.

**The searcher exists and is validated.** `csharp/TransformSearch/` is a
standalone .NET 10 console project whose only input is a JSONL corpus from the
capture patch; its method, oracles and commands are documented in its own
README. `validate` recovers all three published builds this library holds
captures for, each at rank 1 of thousands of surviving behaviours — 12.10 at
depth 6 (1 of 14,177), 13.00 at depth 6 (1 of 508), 12.11 at depth **8** (1 of
9,611) — and `emit` is checked against `vrfnet.payload_transform` bit for bit
over all ten operation kinds, because the published sequences never exercise
`not` or `rotl` and an untested op in the vocabulary is worse than a missing
one.

**Four oracles, each calibrated on a solved build before being believed about an
unsolved one**, and deliberately independent so that agreement is evidence
rather than one measurement counted twice:

| measure | correct decode | wrong transform |
|---|---|---|
| bit-bias fingerprint — set bits at 21 positions biased by UE framing | 3.5–3.7 per payload | 10.5 |
| framing — the block opens as a rep-layout handle chain | 81% | ~9% |
| known plaintext — the block appears in another capture's correct decode | 12–13% | **0.00%** |
| **collapse** — distinct ciphertexts decoding to one plaintext, within one capture | **8.0–9.0%** | **0.00%** |

The fingerprint is the cheap one and is scored at every node; it separates
right from wrong by many sigma, but its wrong-answer floor is *near* zero rather
than zero. The last two have a floor of **exactly** 0.00%, which is what makes a
single hit evidence in a way a bias score never is. **Collapse is the strongest
and is the first thing to reach for.** It counts distinct ciphertexts within one
capture that decode to the same plaintext — the same property update replicated
to many actors, so different net GUIDs, different seeds, different ciphertext —
and only a correct decode brings them back together. Because it compares a
capture against itself it is the only one of the four that cannot be confounded
by how much content two builds share, and a transform correct on a fraction *f*
of payloads degrades it by roughly *f²*, so it is sensitive to a nearly-right
answer rather than only to a wrong one.

**13.04's 64-bit lane, with high confidence:**

    rotr7,xornot6,sub5,swap,add3,add2,rotl1

Spelled out: `rotr64(v, (ror7 % 63) + 1)`, then `v ^ ~ror6`, then `v - ror5`,
then `swap64`, then `v + ror3`, then `v + ror2`, then
`rotl64(v, (ror1 % 63) + 1)` — where `ror_k = rotr32(state, k)` and, for the
first block, `state = seed`.

The evidence, with the three solved builds as the calibration band:

| measure | correct decodes (12.10 / 12.11 / 13.00) | **13.04 candidate** | runner-up | any wrong transform |
|---|---|---|---|---|
| bias, set bits per payload | 3.49 / 3.67 / 3.69 | 4.26 | 4.96 | 10.5 |
| opens as a handle chain | 81.9% / 81.2% / 80.9% | 78.0% | 73.8% | ~9% |
| known plaintext (held out) | 12.21% / 13.16% / 12.89% | 7.85% | 4.15% | **0.00%** |
| **collapse (within capture)** | **8.67% / 8.98% / 8.05%** | **8.29%** | 3.65% | **0.00%** |
| collapse, largest group | 128 / 102 / 100 | 116 | 66 | 1 |

Replicated on the *second* 13.04 capture, which the search never saw: collapse
9.60% and known-plaintext 6.74%, against 0.00% / 0.00% for a control decode
using 12.10's transform.

**The known-plaintext row is the one that misleads, and the reason is content
drift.** It sits well below the solved-build baseline, which reads as "partially
correct" — but collapse, which has no cross-build content confound, sits
squarely inside the correct band. A transform correct on only ~62% of payloads
would show collapse near 0.62² × 8.3% ≈ 3.2%, which is precisely what the
runner-up shows and precisely what the candidate does not. 13.04 is four patches
past the newest solved capture, on maps and with agents the older captures never
held.

**The four keystream constants, recovered and cross-checked:**

    seed_addend = 0x076DC658, init_a_offset = 0x28, init_a_adds = False, tail_xor = 0x58

`init_a_offset = 0x58` with `init_a_adds = True` is the same function and is
reported beside it: only the low seven bits of `seed -+ init_a_offset` survive
the shift left by 25, and 0x28 and 0x58 differ by 0x80, so no capture can tell
the two forms apart. `tail_xor` is the low byte of `seed_addend`, as it is in
all five published builds -- a cross-check that agreed, never a derivation.

**How they were recovered, and why it is not the route the previous session
planned.** That route was to enumerate 32-bit-lane variants and brute-force
`state2` alongside them, because `state2` cannot be observed directly. It does
not need to be. `prng_a` is `mixed * MULTIPLIER` for a **32-bit** `mixed`, and
`prng_b` depends on the seed alone, so a single 2^32 sweep over `mixed` -- for
one seed -- produces *every* state that seed's payloads use, and it needs no
lane but the 64-bit one. What makes that testable without the other two lanes is
the payloads whose bit count is a whole multiple of 64: `apply` runs 64-bit
blocks while more than 63 bits remain, so those never reach the 32-bit lane, the
8-bit lane or the tail XOR.

Two seeds then pin the constants. One cannot: a keystream that decodes a seed's
payloads is consistent with 128 offsets per sign, and the sweep keeps every
keystream that seed cannot tell apart -- 198,027 of them for 13.04. But the
constants each survivor implies predict the keystream of *every other* seed, and
predicting a seed the sweep never saw is a far stronger claim than fitting the
one it was fitted to. Six check seeds leave one answer.

**Validated on all three published builds this library holds captures for**,
each recovering the published constants and nothing else but its own mirror
image: 12.10 (explaining 3 of its 4 check seeds), 12.11 (2 of 2), 13.00 (3 of
3).

**What the recovered transform decodes.** Scored over the payloads the 64-bit
lane decodes whole -- a complete rep layout consuming to exactly zero bits:

| corpus | 13.04's recovered transform | a published transform as control |
|---|---|---|
| 13.04 Lotus capture (swept) | **58 of 167, 34.7%**, across 38 seeds | 12.10: 0 of 167 |
| 13.04 second capture (never seen) | **62 of 173, 35.8%**, across 58 seeds | 12.10 and 13.00: 0 of 173 |
| 12.10 capture under 12.10's own transform | 12 of 141, 8.5% | -- |
| 12.11 capture under 12.11's own transform | 20 of 179, 11.2% | -- |
| 13.00 capture under 13.00's own transform | 15 of 135, 11.1% | -- |

The recovered transform scores *above* the published baselines because what a
capture's whole-block payloads are is a property of the capture -- the rest are
ClassNetCache blobs, which carry no handle chain and parse under no transform at
all. What matters is the control column: a wrong transform is 0.0%, and 58
payloads over 38 seeds terminating on exactly the right bit is not something a
wrong keystream does once.

**The 32-bit and 8-bit lanes are not structural mirrors of the 64-bit lane**,
and that was checked rather than assumed, because it is nearly true and the
temptation is real: 13.00's 32-bit lane carries a `not` its 64-bit lane does
not, and 12.10's 64-bit lane has `xor ~ror4` where its 32-bit lane has plain
`xor rol4`. Same operation skeleton, same k order, but complement placement
differs — almost certainly because a `~` applies to a 32-bit intermediate and
the widening to 64 bits differs. So the other lanes are a small neighbourhood
around the recovered skeleton, not a free derivation. Note also that
`rotl32(state, k) == rotr32(state, 32 - k)`, so a lane reaching for the
left-handed operand needs k in 24..31.

## What was tried and did not work

**Anchoring on a known plaintext bit.** Every operation in the u64 lane moves
bit 0 in one of two ways: the permutations (rotate, swap, reverse) make it some
other input bit, and NOT, XOR, ADD and SUB all flip it by a known amount —
including the arithmetic ones, because a carry propagates upward and cannot
reach the least significant bit. So for a table-free composition, decoded bit 0
is exactly `input_bit_j ^ c`. If bit 0 were a constant in the plaintext, `(j, c)`
could be read straight off the ciphertext and would pin one exact relation.

It is not a constant. Decoding the 12.10 corpus with its own transform, bit 0
is zero in **48.00%** of payloads with a 64-bit first block, and **38.90%** of
those that frame correctly. So the first payload bit is not a `bDoChecksum`
that replays leave off, and there is no free algebraic anchor here.

**Measuring overlap as distinct-values-in-common over distinct-set-size.** This
is the error that cost the most and nearly buried a correct answer: it made
correct-vs-correct read 6.0% and the candidate 2.5%, i.e. "clearly wrong". The
right denominator is *payloads*, not distinct values — how often does a decode
produce something recognisable — which moved the candidate to 6.04% against a
correct decode's 10%. Do not compare decodes by set-overlap ratios; count
payload hits.

**Concluding from a scalar that a candidate is wrong.** Two candidates each
produced hundreds of exact known-plaintext hits, which seemed impossible for
wrong answers, and the same top shared values appeared under both. The
explanation was that the two compositions are *the same function on 53% of
inputs*: they differ by `sub ror5` versus `add ror5, sub ror4`, which are equal
exactly when `ror4 == 2·ror5`, i.e. when bit 4 of the seed is clear. When two
candidates behave alike, check where they agree before theorising.

**Searching deeper.** Depth 9 under the descending prior with k ≤ 8 walked
**24.2 billion** compositions in 10.5 minutes and found nothing better than the
depth-8 leader — which is itself only 7 ops, so the space had room. Depth is not
the missing ingredient.

**Widening the operand range.** Hill-climbing with k up to 31, covering every
`rotl32` the 32-bit lanes use, is still a local maximum: none of 2,850 single
edits improves the candidate. Together with the depth result, this is now
evidence that the candidate *is* the answer rather than evidence that the space
was too small.

**Validating a whole payload without the constants.** Only payloads with
`bit_count == 64` are decoded by `_u64` alone, and each 13.04 corpus holds
exactly **one**. That is true, and it was read as "nothing longer can be checked
until the constants are known", which does not follow: a payload of *any* whole
multiple of 64 bits is decoded by `_u64` alone once a keystream is proposed, and
the 167 of them in the first 13.04 corpus are what recovered the constants.

**Two oracles for the keystream that do not work, and both look reasonable.** A
prefix parse -- decode the blocks of a longer payload and ask whether the chain
so far contradicts a rep layout -- cannot contradict enough. One seed's payloads
are one actor replicating one property layout, so they agree with each other
rather than constraining each other: measured on 12.10 seed 75, a wrong
keystream keeps 37% of the payloads individually and **2%** of them together,
where independence would have given 10^-11. Two per cent of 2^32 is eighty-six
million survivors, and staging more payloads of that seed does not move it.

The bias mask is worse than useless here. It is calibrated on first blocks and
it does hold in the interior -- over one seed's blocks the published keystream
scores 4.57 masked bits per block against a wrong one's 10.55, best of thirty
wrong draws 6.91 -- but it rewards decoded blocks with *few set bits*, and across
2^32 candidates the winners are keystreams that drive the lane toward zeros. The
published answer ranked below more than a million of them. A statistic that
separates two populations by many sigma still says nothing about the extreme
tail of four billion draws.

**Picking the seed to sweep by how busy it is.** The busiest seed in the 12.10
corpus carries 89 whole payloads and every one is a ClassNetCache blob: the
first block opens `handle 495, length 2` then `handle 72`, a handle that
descends, so it is not a chain and no keystream makes it one. A sweep over it
keeps nothing after three minutes, correctly. A seed is chosen instead by
whether every one of its payloads opens *cleanly* -- ascending handles, no field
longer than the payload -- which the first block answers before any candidate is
tried, and then by how many keystream states its payloads exercise: one per
block past the first, so a 22-block payload is twenty-one constraints and a
128-bit payload is one. Ranking 13.04 by payload count picks a seed of 128-bit
payloads and overflows the survivor list; ranking by states picks one with five
payloads of 1,408 bits and keeps 198,027.

## What is open

**The 32-bit and 8-bit lanes.** They are what stands between the recovered
keystream and a payload of arbitrary length: a payload whose bit count is not a
multiple of 64 ends in a 32-bit block, some 8-bit blocks and a tail XOR, and
those need lanes nothing has recovered yet. The states are no longer the
obstacle -- with the constants in hand every state of every seed is computable,
so each lane can be searched on its own against the payloads whose bit count
leaves exactly that lane's remainder, under the same exact-consumption oracle.
They are a small neighbourhood around the 64-bit skeleton rather than a free
derivation, for the reason stated above.

**Is the recovered 64-bit lane exactly right, or right on ~96% of states?** The
collapse evidence put *f* between 0.96 and 1.0 and could not distinguish
further, and the constants recovery narrows it: a lane wrong on a few per cent
of states would not decode 58 payloads of 22 blocks each to the exact bit,
because one wrong state anywhere in a payload breaks its chain. It does not
close the question -- the seeds that decode whole are a sample rather than the
library -- and ground truth still settles it.

**Does the descending-operand prior hold for 13.04?** The recovered lane uses
7,6,5,3,2,1 -- descending, consistent -- but it was *found under* the
constraint, so this is not independent confirmation. The hill-climb that ignores
the prior did not move off it, which is weak support.

## The tooling

`csharp/patches/0001-payload-capture.patch` and its README write the corpus. The
capture is inert unless `VRF_PAYLOAD_CAPTURE` names a sink, and it can be
pointed at a build whose answer is already known, which is the only reason any
percentage above is interpretable. `csharp/TransformSearch/` is the searcher
over that corpus, and it lives in the repo rather than in scratch because Riot
rotates the transform every patch: 13.05 will need it again.

## The rule that still stands

Nothing is registered in `payload_transform.TRANSFORMS` until it is proved
against ground truth. The Python `decode` is never on the positions path —
`tracks.py:266` discards `transform_for`'s return and uses it as a gate — so
registering 13.04 there is enough to unhide the captures and hand them to the
C# decoder. If the two implementations disagreed, nothing would complain and
the coordinates would simply scatter. `tests/test_positions.py` is the only
thing that would catch it.
