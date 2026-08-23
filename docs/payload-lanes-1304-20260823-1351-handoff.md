# Finishing 13.04's payload transform — handoff

23 August 2026 · branch `vd-1304-port` · `E:\Personal\ValoReview`

The previous session recovered 13.04's 64-bit lane. This one recovered **the four keystream
constants** and **the 32-bit lane**, built the tooling for both into `csharp/TransformSearch`, and
took the 8-bit lane as far as a named failure. Everything is committed. What remains is the 8-bit
lane, then the port and ground truth.

## Read these first

| What | Why it matters |
|---|---|
| `docs/payload-transform-13-04.md` | The measured record, **updated this session**. Carries the recovered lane, the constants, the 32-bit lane, every dead end with its numbers, and the plan for the 8-bit lane. Read it before anything else. |
| `csharp/TransformSearch/README.md` | The tool: its five commands, its oracles, its priors, its validation table. How each search works is there and is not repeated here. |
| `docs/transform-search-1304-20260823-1151-handoff.md` | The previous handoff. Its *Cautions* still bind; its *Next steps* section is **superseded** — the route it proposed was not the one that worked (see below). |
| `git log ea36522 d55663f` | The two feature commits, with the reasoning in their messages. |
| `csharp/patches/README.md` | How to reapply the payload-capture patch to a clean parser clone. Needed before any corpus can be captured. |

## State

**Nothing is uncommitted** except a pre-existing `.gitignore` edit that is not this work's (it adds
`Demos1/`). Four commits sit on `vd-1304-port`; nothing is pushed.

### Done

**The four keystream constants**, recovered and cross-checked:

    seed_addend = 0x076DC658, init_a_offset = 0x28, init_a_adds = False, tail_xor = 0x58

`init_a_offset = 0x58` with `init_a_adds = True` is the same function — only the low seven bits of
`seed -+ offset` survive the `<< 25`, and the two differ by 0x80 — so both forms are reported and no
capture can separate them.

**The 32-bit lane**: `rotr7,xor6,sub5,swap,add3,add2,rotl1`, with `rotl32` operands and `% 31`
distances. The 64-bit skeleton with a plain `xor rol6` where the 64-bit lane has `xor ~ror6`.

**Three new commands in the tool** — `constants`, `solve`, `lane32`, `lane8` — each validated by
recovering the published answer for 12.10, 12.11 and 13.00 before being believed about 13.04.

### Untouched

The 8-bit lane, the Python port, the parser-clone port, registration, and ground truth.

## Decisions made

**The previous session's route to the constants was abandoned, and it was the wrong route.** It
proposed enumerating 32-bit-lane variants and brute-forcing `state2` alongside them, because
`state2` cannot be observed directly. It does not need to be: `prng_a` is `mixed * MULTIPLIER` for a
**32-bit** `mixed`, and `prng_b` needs no constants, so one 2^32 sweep over `mixed` for one seed
produces every state that seed's payloads use — with no lane but the 64-bit one.

**Payloads whose bit count is a whole multiple of 64 are what make that testable.** `apply` runs
64-bit blocks while more than 63 bits remain, so such a payload never reaches the 32-bit lane, the
8-bit lane or the tail XOR. That single observation is what unlocked the constants, and the same
shape of observation — a bit count that leaves exactly one lane's remainder — is what unlocked each
lane afterwards. The previous session's note that "only `bit_count == 64` is decodable by `_u64`
alone, and each corpus holds exactly one" is true and was read too narrowly; 167 payloads in the
first 13.04 corpus are whole multiples.

**One seed cannot name the constants and several can.** A keystream that decodes a seed's payloads
is consistent with 128 offsets per sign, and the sweep keeps every keystream that seed cannot tell
apart — 198,027 of them for 13.04. But the constants a survivor implies predict *every other* seed's
keystream, so `--check-seeds` decodes other seeds under each candidate. Predicting a seed the sweep
never saw is a far stronger claim than fitting the one it was fitted to.

**Seeds are chosen by what their payloads are, not by how many there are.** Two filters, both read
off the first block, which needs no keystream: every payload must *open cleanly* (ascending handles,
no field longer than the payload), and the seed is ranked by how many keystream states its payloads
exercise — one per block past the first. Both were learned the hard way; see below.

**`lane8` stops on an answer, never on a count.** Six fitted cases are 2^48 against a wrong lane and
still admit lanes that fit those six and no others — 13.00 produces three before the published one.
The search ends on a lane that reproduces every held-out case.

**The scratch Python prototypes are not the deliverable.** Each search was prototyped in Python
against a solved build first, then ported to C# once it worked. The Python lives in this session's
scratchpad and is disposable; the repo carries the C#.

## What did not work

**Two oracles for the keystream sweep, both plausible, both useless.** Written into
`docs/payload-transform-13-04.md` with their numbers, and worth not retrying:

- A **prefix parse** — decode the blocks of a longer payload and ask whether the chain contradicts a
  rep layout. One seed's payloads are one actor replicating one property layout, so they agree with
  each other rather than constraining each other: a wrong keystream keeps 37% of them individually
  and **2%** of them together, where independence would give 10^-11. Two per cent of 2^32 is
  eighty-six million survivors, and staging more payloads does not move it.
- The **bias mask** (`Fingerprint`). It does hold in the interior — 4.57 masked bits per block for
  the published keystream against 10.55 for a wrong one, best of thirty wrong draws 6.91 — but it
  rewards blocks with *few set bits*, and over 2^32 candidates the winners are keystreams driving
  the lane toward zeros. The published answer ranked below more than a million of them. A statistic
  that separates two populations by many sigma still says nothing about the tail of four billion
  draws.

**Ranking seeds by payload count.** The busiest seed in the 12.10 corpus carries 89 whole payloads
and every one is a ClassNetCache blob — the first block opens `handle 495, length 2` then
`handle 72`, a handle that descends. Three minutes of sweep, nothing kept, correctly.

**`Framing.OpensAsChain` as the seed filter.** It asks whether *one pair* parses, which those blobs
satisfy. The filter has to ask whether anything *contradicts* instead.

**Ranking clean seeds by count rather than by length.** 13.04's most numerous clean seed carries
five payloads of 128 bits — one unknown state each — and the sweep overflowed its survivor cap. The
seed with five payloads of 1,408 bits keeps 198,027.

**The published multiplier vocabulary for 13.04's 8-bit lane.** Ten minutes over all eighteen
shapes and all 256 residues of both byte slots, and nothing fits. Riot rotates these constants like
the others (12.10/12.11 use 0x0CC6DB61 and 0x2751B, 13.00/13.01 use 0x0B and 0x533, 13.02 uses
0x79), so the prior is simply wrong for this build.

**Returning `lane8`'s first few fits as the answer.** See the stop rule above — 13.00 exposed it.

## Environment facts

- **The previous session's scratchpad was deleted mid-session**, taking all four corpora with it.
  They are regenerable and were regenerated; capture into *this* session's scratchpad or somewhere
  durable. The capture command is in `csharp/TransformSearch/README.md`; each corpus takes about
  25 s and the reference captures used were, by build: 12.10 `03fcbb4a-…`, 12.11 `2f49807c-…`,
  13.00 `50105627-…` (all in `Demos1/`), 13.04 `e4fddb4e-…` and `3001c204-…` (in `Demos/`).
- **The Bash tool eats backslashes inside quoted heredocs.** A `python - <<'PY'` script containing
  `\r`, `\n` or `\\` arrives mangled, and a C# string literal written that way ends up with a real
  newline inside it (a parse error). Write the script to a file with the Write tool and run it, or
  patch with explicit byte values.
- `dotnet build` fails while the executable is running ("used by another process"). Sequence them.
- Timings on twelve threads: the keystream sweep is 130–260 s, `lane32` is instant, `lane8` is under
  a second per published build and 10 minutes when it finds nothing for 13.04.
- `SeedCorpus.MaxBits` is 4096 and bounds every lane search's payload length.
- Reference library build census is unchanged: `Demos1/` holds 12.10 ×11, 12.11 ×5, 13.00 ×5 and no
  13.01 or 13.02; `Demos/` holds the two 13.04 captures.

## Open questions

**Is the recovered 64-bit lane exactly right, or right on ~96% of states?** The constants recovery
narrows it — a lane wrong on a few per cent of states would not decode 58 payloads of 22 blocks each
to the exact bit — but the seeds that decode whole are a sample, not the library. Ground truth
settles it.

**Does 13.04's 8-bit lane share the 64-bit skeleton at all?** Every published pair does, and the
search assumes it. If solving the rotate distances still finds nothing, that assumption is the next
thing to drop — the shape would then have to be searched, not varied.

## Next steps

### 1. Recover the 8-bit lane by solving the rotate distances

This is the whole remaining derivation and the method is worked out; it is only unimplemented.

`Lane8Search.Run` currently enumerates each rotate slot's **multiplier** over ten published values,
because a rotate distance is `(state * M % 7) + 1` and the mask-to-a-byte trick that makes byte
slots cheap does not apply. Stop guessing the multiplier. A distance is one of **seven** values, so
a case admits 49 distance pairs for a two-rotate shape:

1. For each shape, enumerate the prefix byte multipliers (256 per slot; 13.04 has two prefix slots,
   so 65,536) and, for the first fitted case only, the 49 distance pairs. Solve the final byte slot
   exactly as `Required` already does. Cost is 49 x 256^2 per shape and it assumes nothing about any
   multiplier.
2. For every other fitted case, accept it if **some** distance pair reproduces its plaintext byte.
   Keep the per-case distance vector alongside the byte multipliers.
3. Filter the survivors on the held-out cases the same way.
4. For each survivor and each rotate slot, recover the multiplier by scanning `R` over 2^32 for
   `((state_i * R) % 7) + 1 == d_i` across the cases. The first case rejects seven candidates in
   eight, so the scan is seconds; keep survivors few enough that this stays cheap.

Validate on 12.10, 12.11 and 13.00 **before** believing anything about 13.04 — all three are
published and all three currently recover, so a regression is visible immediately.

First command, to re-establish a corpus (about 25 s):

```powershell
$env:VRF_PAYLOAD_CAPTURE = "$env:TEMP\claude\cap1304.jsonl"
$env:VRF_PAYLOAD_CAPTURE_BRANCH = "++Ares-Core+release-13.04"
$env:VRF_PAYLOAD_CAPTURE_LIMIT = "200000"
& dotnet .\csharp\VrfPositions\bin\Release\net10.0\vrf-positions.dll .\Demos\<the Lotus capture>.vrf out.json --hz 10
```

Then, before touching anything:

```
dotnet csharp/TransformSearch/bin/Release/net10.0/transform-search.dll lane8 \
    --corpus <12.10 corpus> --expect 12.10
```

It should print a lane holding every held-out case in well under a second.

### 2. Port the transform

Two places, and the file says so: `libraries/vrfnet/payload_transform.py` gets a `Transform1304`
class, and the parser clone at `E:\Personal\ValorantReplayParser` gets the same transform in its own
registry so the C# decoder can decode a 13.04 capture. Registering in Python alone unhides the
captures and hands them to a decoder that cannot read them — `tracks.py:266` uses `transform_for`
as a gate and discards its return.

### 3. Ground truth, and only then registration

`tests/test_positions.py` is the standing check: killer and victim within weapon range at every
`characterDeath`, and every spawn location on top of that actor's own first movement sample. Run it
over the two 13.04 captures. `test_every_registered_build_is_covered`
(`tests/test_payload_transform.py:156-158`) fires the moment a class is registered without its 11
vectors — that tripwire is intended; let it fire, and generate the vectors from the decode once
ground truth passes.

## Cautions

- **Do not register `Transform1304` before ground truth passes.** Unchanged from two sessions ago
  and still right.
- **Never add a nearest-version fallback.** House rule, and the evidence keeps strengthening: 13.04
  shares no constants and no complement placement with 13.02.
- **The sibling parser clone is a separate git repository and carries three uncommitted files** —
  the payload-capture patch, and the only live copy besides
  `csharp/patches/0001-payload-capture.patch`. Read `git status` in both before any `reset`,
  `checkout` or `clean`.
- **Do not upstream the capture patch.** A released decoder passing payloads through untouched
  would be actively harmful.
- Do not re-derive anything in either predecessor handoff's *What did not work*, or this one's.
- The equivalent forms `lane8` and `constants` print are not duplicates to be pruned: an offset and
  a sign differing by 0x80, or a `not` commuted past a rotate, are the same function, and the
  capture cannot separate them.

## Suggested skills

- **`code-review`** — first, on `csharp/TransformSearch/`. Four files are new and lightly tested
  (`Keystream.cs`, `Constants.cs`, `Sweep.cs`, `Lanes.cs`, `Lane8.cs`), and a silent arithmetic
  error in any of them is indistinguishable from "the build's transform is different". The published
  builds validate the *searches*; nothing yet covers the heap, the dedup, or the bit reader.
- **`commit`** — after each piece of the 8-bit work lands; the project forbids running `git commit`
  directly.
- **`handoff`** — again at the end. This work has spanned three sessions and will span a fourth.

Not useful here: `init` (`CLAUDE.md` exists and is the durable record), `run` (nothing user-facing
changes until a transform is registered), `artifact-design` and `dataviz` (the deliverable is a
decoder), and `security-review` (an offline file parser and a search harness, no network, no
untrusted input beyond replay files already parsed elsewhere).

## Sensitive material

The `.vrf` files under `Demos/` and `Demos1/` contain real match and player identifiers, and both
directories are gitignored deliberately — **do not commit them, quote full match GUIDs, or paste
player UUIDs into documents or issues**. Capture filenames appear here by short prefix only; recover
full names from `vrfhome.scan` over the directory. The captured JSONL corpora are payload ciphertext
from real matches and belong in scratch only — never commit one. No API keys or credentials are
involved anywhere in this work.
