# Patches against the parser clone

`csharp/VrfPositions/VrfPositions.csproj` builds against `$(VrpRoot)`, which
defaults to a clone of `michel-giehl/ValorantReplayParser` sitting **beside**
this repository. That clone is a separate git repository, so nothing changed
inside it is captured by a commit here. Anything this project needs from it
lives in this directory as a patch, or the next clean clone silently loses it.

Apply with:

    cd ../ValorantReplayParser
    git apply ../ValoReview/csharp/patches/0001-payload-capture.patch

Then rebuild with `runners\build-decoder.bat`.

---

## `0001-payload-capture.patch`

Records every property payload for one build instead of transforming it, so a
transform can be derived for a build nobody has published one for. Three
changes, all inert unless `VRF_PAYLOAD_CAPTURE` names a file:

* **`ValorantPayloadCaptureTransform`** — a passthrough `IPayloadTransform`
  that writes `{bit count, seed, payload hex}` as JSONL. The passthrough is
  safe for the surrounding parse and that is the whole reason it works: a
  bunch's framing, its content-block header and the payload's own bit count are
  plaintext, and `ContentBlockFramer` advances the outer archive by exactly
  `bitCount` whatever the transform did. So the stream stays in sync and only
  each payload's interior is ciphertext — which is the thing being collected.
* **`PayloadTransformRegistry.CreateDefault`** — registers it only while the
  sink is set, and lets it *replace* a published transform claiming the same
  branch. The first half is load-bearing: registered unconditionally, it would
  turn an unsupported build from a refusal by name into a parse that succeeds
  and produces rubbish. The second half is what makes a capture from a build
  whose answer is already known possible, which is the only way to calibrate
  what a recovery attempt's success rate should look like.
* **`ContentBlockFramer.FrameContentBlocks`** — skips the payload interior
  while capturing. Reading ciphertext as properties yields a field length long
  enough to overflow on the very first block, which killed the whole parse
  after one payload.

Environment:

| variable | meaning |
|---|---|
| `VRF_PAYLOAD_CAPTURE` | JSONL sink path. Unset means the patch does nothing. |
| `VRF_PAYLOAD_CAPTURE_BRANCH` | Branch to claim; defaults to `++Ares-Core+release-13.04`. |
| `VRF_PAYLOAD_CAPTURE_LIMIT` | Payload cap; defaults to 200,000. |

This patch is a **tool**, not a fix — it is not wanted upstream and should not
be merged into a released decoder.
