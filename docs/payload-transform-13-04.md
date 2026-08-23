# Deriving a payload transform for `++Ares-Core+release-13.04`

Measured truth about an unfinished piece of work. What is written down here is
what was established by running something, and the open question at the end is
stated as an open question.

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

## What is open

Recovering the three mixing functions. The next step is a search over the
bounded composition space above, run in C# because Python is two orders of
magnitude too slow for it, and **validated by first re-deriving 12.10's own
`_u64` from the 12.10 corpus** — a searcher that cannot recover a known answer
says nothing about an unknown one.

After that the four constants are cheap, and worth writing down now because the
reduction is not obvious. `_initial_prng_a` computes

    mixed = ((sp >> 15) ^ sp) >> 12  ^  ((seed ∓ off) * 0x02000000)  ^  sp

with `sp = seed + seed_addend`. The middle term is a `<< 25`, so only the low
**seven** bits of `(seed ∓ off)` survive it — 128 possible values for that whole
term, not 2³². Recover `prng_a` for one seed (`prng_b` depends on the seed
alone, so `state₂ = hi32(prng_b + prng_a)` pins it, and `prng_a = mixed *
MULTIPLIER` then leaves about one candidate `mixed`), then for each of the 128
values XOR it out and invert `x ↦ ((x >> 15) ^ x) >> 12 ^ x` to get `sp`, hence
`seed_addend`. A second seed pins `init_a_offset` and the sign. `tail_xor` is
the low byte of `seed_addend` in all five known builds — a cross-check, never a
licence to invent one.

## The tooling

`csharp/patches/0001-payload-capture.patch` and its README. The capture is
inert unless `VRF_PAYLOAD_CAPTURE` names a sink, and it can be pointed at a
build whose answer is already known, which is the only reason any percentage
above is interpretable.

## The rule that still stands

Nothing is registered in `payload_transform.TRANSFORMS` until it is proved
against ground truth. The Python `decode` is never on the positions path —
`tracks.py:266` discards `transform_for`'s return and uses it as a gate — so
registering 13.04 there is enough to unhide the captures and hand them to the
C# decoder. If the two implementations disagreed, nothing would complain and
the coordinates would simply scatter. `tests/test_positions.py` is the only
thing that would catch it.
