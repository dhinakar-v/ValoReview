# transform-search

Derives the 64-bit lane of a Valorant payload transform for a build nobody has
published one for.

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

`emit` output is checked against `vrfnet.payload_transform` bit for bit — all
three published sequences plus synthetic ones covering all ten operation kinds,
because the five published sequences never exercise `not` or `rotl`.

## What this does not do

It derives `_u64` only. The 32-bit and 8-bit lanes are *close* to structural
mirrors of it but not exact — 13.00's 32-bit lane carries a `not` its 64-bit
lane does not, and 12.10's operand complement appears in one lane and not the
other — so they are not derivable from it for free. Those, and the four
keystream constants, are what stands between a recovered `_u64` and a registered
transform. Nothing is registered until ground truth passes; see
`docs/payload-transform-13-04.md`.
