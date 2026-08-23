# transform-search

Derives a Valorant payload transform for a build nobody has published one for:
the 64-bit lane, the four keystream constants, and the 32-bit and 8-bit lanes
that follow from them.

Riot rotates the whitening applied to replicator bunch payloads every patch, and
`libraries/vrfnet/payload_transform.py` carries one class per build, each ported
from upstream. When a capture arrives on a build upstream has not reached,
there is nothing to port. This searches for the answer instead.

It references nothing — not the parser clone, not `libraries/` — because its
whole input is a JSONL corpus of `{bit count, seed, payload hex}` written by
`csharp/patches/0001-payload-capture.patch`.

    dotnet build csharp/TransformSearch/TransformSearch.csproj -c Release

## Why the first block, and only the first block

`_Transform.apply` sets `state = seed` and advances the keystream only
afterwards, and `seed = payload_bits ^ actor_net_guid` is plaintext in the bunch
header. So the first 64 bits of every payload are keyed by a value already in
hand, and recovering `_u64` needs none of the four keystream constants. Every
later block does, which is a separate and much smaller problem.

## What tells a right answer from a wrong one

A transform has no checksum and no redundancy: wrong output is the right length
and looks random. Four independent measures separate them, each calibrated on
builds whose answers are already published before being believed about one whose
is not.

| measure | correct | wrong |
|---|---|---|
| `Fingerprint` — set bits at 21 positions biased by UE framing | 3.5–3.7 per payload | 10.5 |
| `Framing` — the block parses as a rep-layout handle chain | 81% | ~9% |
| `KnownPlaintext` — the block appears in another capture's correct decode | 12–13% | **0.00%** |
| collapse — distinct ciphertexts decoding to one plaintext, within one capture | 8.0–9.0% | **0.00%** |

The last two are the strong ones, because their wrong-answer floor is zero
rather than merely distant. The last is the strongest of all: it compares a
capture against *itself*, so unlike the other three it cannot be confounded by
how much content two builds happen to share. It works because the same property
update is replicated to many actors — different net GUIDs, so different seeds
and different ciphertext — and only a correct decode brings them back to one
value. A transform that is correct on a fraction *f* of payloads degrades it by
roughly *f²*, which is what makes it sensitive to a nearly-right answer rather
than only to a wrong one.

## Two priors make the space enumerable

**Operands descend.** Across all five published 64-bit lanes — 35 operand uses —
each successive `rotr32(state, k)` uses a strictly smaller k: 8,6,5,4 then
8,6,4,3,2 then 8,6,3,1 then 5,4,1 then 6,3,2. Never a repeat, never an ascent.
That turns the operand choice for m operand ops from 8^m into C(8,m) and
collapses depth seven from about 10^12 compositions to 5x10^8. `--loose` relaxes
it; `validate` is what proves a run under it can still recover a known answer.

**Prefixes are shared.** The score needs decoded values, so a depth-first walk
holding one array of partially-decoded payloads per level pays one operation per
node rather than a whole composition per leaf. Measured at 28–56 million
compositions a second on twelve threads.

## Commands

    # Recover a known answer. Do this before believing any search.
    transform-search validate --corpus cap1210.jsonl --expect 12.10 --depth 6

    # Hunt an unknown one.
    transform-search search --corpus cap1304.jsonl --depth 8 --stage-n 64 \
        --known known.txt

    # Improve a partially-correct answer one edit at a time.
    transform-search refine --corpus cap1304.jsonl --known known.txt \
        --sequence rotr7,xornot6,sub5,swap,add3,add2,rotl1

    # Print decoded first blocks, for checking against the Python.
    transform-search emit --corpus cap1210.jsonl --expect 12.10 --count 500

    # Recover the four keystream constants, once the lane is known.
    transform-search constants --corpus cap1304.jsonl --sequence rotr7,xornot6,sub5,swap,add3,add2,rotl1

    # The same, against a build whose constants are published.
    transform-search constants --corpus cap1210.jsonl --expect 12.10

    # The constants two seeds' recovered `mixed` imply, without a corpus.
    transform-search solve --pairs <seed>:<mixed>,<seed>:<mixed>

    # The 32-bit lane, once the constants are known.
    transform-search lane32 --corpus cap1304.jsonl --constants 076DC658:28:sub \
        --sequence rotr7,xornot6,sub5,swap,add3,add2,rotl1

    # The 8-bit lane, the same way, scored against a second capture as well.
    transform-search lane8 --corpus cap1304.jsonl --check cap1304b.jsonl \
        --constants 076DC658:28:sub \
        --sequence rotr7,xornot6,sub5,swap,add3,add2,rotl1

`make-known-plaintext.sh <scratch> <demo-dir> <out>` builds the oracle's block
set by decoding every capture in a library whose build is already solved.

## Capturing a corpus

Apply the parser patch and rebuild the decoder first
(`csharp/patches/README.md`), then:

```powershell
$env:VRF_PAYLOAD_CAPTURE = "$env:TEMP\cap.jsonl"
$env:VRF_PAYLOAD_CAPTURE_BRANCH = "++Ares-Core+release-13.04"
$env:VRF_PAYLOAD_CAPTURE_LIMIT = "200000"
& dotnet .\csharp\VrfPositions\bin\Release\net10.0\vrf-positions.dll <capture>.vrf out.json --hz 10
```

Point `VRF_PAYLOAD_CAPTURE_BRANCH` at a build whose transform *is* published and
the capture transform replaces it, which is the only way to calibrate what a
recovery attempt's numbers should look like.

## Validation status

`validate` recovers all three published builds this library holds captures for,
each at rank 1 of thousands of distinct surviving behaviours:

| build | depth | recovered | of |
|---|---|---|---|
| 12.10 | 6 | rank 1 | 14,177 behaviours |
| 13.00 | 6 | rank 1 | 508 behaviours |
| 12.11 | 8 | rank 1 | 9,611 behaviours |

`constants`, `lane32` and `lane8` recover all three builds' published answers
too, and `lane8` is the one to re-run first after any change here: it exercises
the keystream, the 64-bit lane and the chain parser on the way to its own answer,
so a fault anywhere upstream shows up as a lane that does not recover.

`emit` output is checked against `vrfnet.payload_transform` bit for bit — all
three published sequences plus synthetic ones covering all ten operation kinds,
because the five published sequences never exercise `not` or `rotl`.

## The constants, and why they need no second search

`_initial_prng_a` mixes the four constants into a 32-bit value and multiplies it
by `MULTIPLIER`; `prng_b` needs no constants at all. So the whole keystream of
one seed follows from a single 32-bit `mixed`, and `constants` sweeps all 2^32
of them.

What makes a candidate testable without the other two lanes is the payloads
whose **bit count is a whole multiple of 64**: `apply` runs 64-bit blocks while
more than 63 bits remain, so those never reach the 32-bit lane, the 8-bit lane
or the tail XOR, and a candidate keystream either decodes one to a rep layout
that consumes to exactly zero bits or it does not. A wrong keystream manages
that for 6 payloads in 100,000.

Two things about the seed decide whether the sweep ends, and both are read off
the first block, which needs no keystream:

- **Its payloads must open cleanly** -- ascending handles, no field longer than
  the payload. The busiest seed in the 12.10 corpus carries 89 whole payloads
  that open `handle 495, length 2` then `handle 72`, which is not a chain, and a
  sweep over it correctly keeps nothing.
- **Its payloads must be long.** A candidate must survive one state per block
  past the first, so a 22-block payload is twenty-one constraints and a 128-bit
  payload is one.

One seed still cannot name the constants -- only the low seven bits of
`seed -+ init_a_offset` survive the shift left by 25, so 128 offsets per sign
fit any recovered keystream. The constants each survivor implies predict the
keystream of every *other* seed, and that is what settles it: `--check-seeds`
decodes those seeds' payloads under each candidate and keeps the ones that
explain the most.

Validated the same way as the lane search, on the three published builds this
library holds captures for -- 12.10, 12.11 and 13.00 -- each recovering the
published constants and nothing else but its own mirror image (an offset and a
sign that differ by 0x80 are the same function).

## The other two lanes

Each has an oracle of its own, and both come from the same observation: with the
keystream recovered, every state of every seed is computable, so a payload whose
bit count leaves exactly one lane's remainder has exactly one unknown.

- **32-bit** (`lane32`): a bit count 32 past a multiple of 64 runs the 64-bit
  blocks and then one 32-bit block -- the 8-bit loop needs eight bits left and
  the tail XOR needs a partial byte, so neither runs. The candidates are the
  complement variants of the recovered 64-bit skeleton with `rotl32` operands
  and `% 31` distances: sixteen of them, and the right one decodes 15 to 22
  payloads where every other variant decodes **zero**.

- **8-bit** (`lane8`): a bit count 8 to 15 past a multiple of 64 runs one 8-bit
  block and nothing else -- the 32-bit lane needs more than 31 bits, and the tail
  XOR that runs on the spare bits needs no lane at all, only `tail_xor` and the
  keystream byte. The rep layout then says what that one byte must be, and a
  wrong lane has one chance in 256 (or 128, see the mask below) per case. This
  lane is a search rather than a neighbourhood, because its operands are
  arbitrary multipliers; four things make it tractable. A chain of multipliers is
  one multiplier. A byte operand only depends on its multiplier modulo 256. The
  last byte slot is solved rather than enumerated -- which is why a fitted case
  must have an **odd** state, since solving it inverts a multiplication by the
  state and an even one names up to 128 multipliers instead of one. And a rotate
  slot's multiplier is not searched at all: a distance is one of seven values, so
  each case picks its own, and the multiplier behind them is a 2^32 scan per slot
  afterwards -- which is a **filter** as much as a recovery, because one
  multiplier has to produce the distance every case needed.

  **What a case can pin is measured, and it decided the shape of all of this.** A
  payload whose bit count is a whole number of bytes pins its byte to `0x00`
  every time -- it is the chain's terminating zero handle, byte-aligned -- so a
  lane ending in a rotate has *no* evidence about that rotate, since every
  distance rotates zero to zero. A payload with a partial byte pins seven bits of
  eight and the eighth is real, which is what pins a distance; 13.00's corpus
  holds 27 of the first kind and thousands of the second. So a case carries a
  `Mask`, the fitted cases are the fully pinned ones and everything else is
  held-out evidence. Cases are also deduplicated **by state**: two payloads under
  one state say the same thing to a multiplier scan, and 13.00's 212 cases turned
  out to carry 26 distinct states.

Both are validated the same way as everything else here: 12.10, 12.11 and 13.00
recover their published lanes -- every operation, every byte multiplier and every
rotate multiplier, including 13.00's trailing `0x0B`, which the older search only
ever got by having it in a list. 13.04's comes back holding all 349 cases of the
capture it was searched on and **all 203 of a second capture it never saw**,
which is what `--check` reports.

**`lane8` stops on an answer, never on a count.** Six fitted cases are 2^48
against a wrong lane and still admit lanes that fit those six and no others --
13.00 produces three before the published one. What ends the search is a lane
that reproduces every held-out case as well *and* whose per-case distances one
multiplier per slot explains.

## What this does not do

It derives `_u64`, the four constants and both narrower lanes, which is the whole
transform. What it does not do is prove one: a transform is proved against ground
truth, by decoding a match and checking positions, and nothing here decodes a
match. The 32-bit and 8-bit lanes are *close* to structural
mirrors of the 64-bit one but not exact — 13.00's 32-bit lane carries a `not` its 64-bit
lane does not, and 12.10's operand complement appears in one lane and not the
other — so they are not derivable from it for free -- which is why
each is searched rather than copied. Nothing is registered until ground truth
passes; see `docs/payload-transform-13-04.md`.
