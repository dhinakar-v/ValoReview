# ValorantReplayParser, vendored

The replay parser `csharp/VrfPositions` compiles against. It is a **copy**, not
a submodule and not a clone beside this repository: a decoder build needs this
checkout and the .NET 10 SDK and nothing else.

Upstream is [`michel-giehl/ValorantReplayParser`](https://github.com/michel-giehl/ValorantReplayParser),
MIT, and `LICENSE` beside this file is theirs reproduced in full. The copy was
taken from `main` at **`99d9646`** ("feat: Add harbor ultimate", 1 August 2026).

## Why it is here rather than beside

It used to be a sibling clone reached through `$(VrpRoot)`, with the changes
below kept as `git apply` patches in `csharp/patches/`. That arrangement had
one failure it could not be talked out of: **a change nobody had captured as a
patch was invisible**, because the clone is a different git repository and
nothing in a commit here could see into it. Three of the changes below lived
only in one machine's working tree, and one of them is a privacy decision --
a clean clone plus the committed patches would have silently re-enabled
account-identifier decoding, with nothing saying so. The source is the durable
record now, and a diff against upstream is a `git diff` rather than an
archaeology session.

## What was copied

Four of upstream's six projects: `Replay.Models`, `Replay.Encoding`,
`Replay.Unreal`, `Replay.Valorant` -- the transitive closure of what
`VrfPositions` references. The two CLIs (`CliReader`, `NetGuidCacheReader`) and
the five test projects are **not** here; nothing in this repository builds or
runs them, and `csharp/VrfPositions/Program.cs` exists precisely because
`CliReader` exports everything or nothing.

Upstream's root `Directory.Build.props` sets `TreatWarningsAsErrors`. It was
not copied: vendored third-party source should not fail this repository's build
on a warning a future SDK invents. The tree compiles with zero warnings as it
stands.

## What differs from upstream, and why

Four changes, all in `Replay.Valorant` except the last:

* **`GameState/BombPlayerStateDescriptor.cs`** -- `Subject` (a player UUID),
  `CompetitiveTier` and `UniqueId` are **not decoded**. They are replicated and
  upstream reads them; a local review tool has no business writing an account
  identifier into a cache file or a web response, and a field that is never
  decoded cannot leak into one by accident later.
* **`GameState/OwnerExclusivePlayerInfoDescriptor.cs`** and
  **`GameState/AresPlayerRoundInfoDescriptor.cs`** (both new) -- decode real
  per-round credits and loadout value. This is the ground truth that
  `web/src/model/synthetic.ts` currently stands in for; the reasoning behind
  each field is in the files' own docstrings.
* **`Descriptors/ValorantDescriptors.cs`** -- registers
  `OwnerExclusivePlayerInfoDescriptor` and the three armour-item descriptors,
  which are upstream files upstream never registered.
* **`Replay.Encoding/PayloadEncryption/VersionedTransforms/ValorantSeededTransform13_04.cs`**
  (new), and its line in `PayloadTransformRegistry.CreateDefault` -- upstream
  stops at 13.02. This one was **derived** from captured payloads rather than
  read off the client; `docs/payload-transform-13-04.md` is the evidence and
  `csharp/TransformSearch/` is the tool that produced it. Its Python twin is
  `vrfnet.payload_transform.Transform1304`, and the eleven vectors in
  `tests/test_payload_transform.py` were generated from *this* file so the two
  cannot drift.

What is deliberately **absent** is the payload-capture tool
(`csharp/patches/0001-payload-capture.patch`): a passthrough transform and the
framer branch that goes with it. It is a derivation instrument and must never
ship in a decoder. It stays a patch, applied against this directory only while
a new build's transform is being recovered -- see `csharp/patches/README.md`.

## Updating

Re-copy the four projects from a fresh upstream clone, then re-apply the four
changes above and confirm they are all still present. Ground truth is
`tests/test_positions.py`, which decodes real captures with `cache=False`:
killer and victim within weapon range at every `characterDeath`, and every
spawn location on top of that actor's own first movement sample.
