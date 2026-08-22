# Plan 2 — serve the fast decode

## Context

The web plan was written against a four-minute decode, and most of its
complexity was there to survive one: a job id, a background worker, an
`asyncio.Queue` bridge from a worker thread to the event loop, an SSE stream of
`(done, total)`, a revision counter the browser polls, and a rule about pausing
the prewarmer when a viewer opens. All of that existed because four minutes
cannot happen inside an HTTP request.

`db53278` makes a full match about **four seconds**. That is inside an ordinary
request budget, and the whole apparatus above becomes machinery in service of a
problem that no longer exists.

**This plan deletes more design than it adds.** It replaces the planned
job-and-SSE layer with one synchronous endpoint, and spends the saved effort on
the two things the change actually created: telling the user whether a decoder
is even present, and serving the positions themselves.

Prerequisite: Plan 1 is merged.

## What changes, and what stops being planned

| Planned before | Now |
|---|---|
| `POST /decode` → `202 {job_id}` | `POST /decode` → the updated `ReplayDoc`, synchronously |
| `GET /api/jobs/{id}/events` (SSE) | **dropped** |
| `vrfserve/events.py`, the thread→loop bridge | **dropped** |
| `vrfserve/jobs.py` | **dropped** |
| A `revision` counter the browser watches | kept on `Entry`, but internal — the response *is* the new state |
| "Pause the prewarmer while a viewer is open" | becomes "pause while a foreground decode runs" |
| The tab-closed-leaves-prewarmer-paused regression | **cannot happen** — nothing is paused across a request |

FastAPI runs a sync handler in a threadpool, so a four-second handler occupies a
worker and not the event loop. That is the whole reason this works, and it is
the same reason every other handler in `app.py` is `def` and not `async def`.

## The decoder has to be findable, and its absence has to be sayable

This is the part the speed-up genuinely added work for. A decode now needs a
**built C# binary**, resolved by `csharpdecode.locate()` in the order
`oodlefind` established: `--parser-exe` → `VRF_PARSER_EXE` (real env, then the
nearest `.env`) → `vendor/parser/` → the repository's own build output.

A machine without the .NET SDK and without a drop-in has no decoder, and that is
an ordinary state — the same kind of ordinary as a missing `assets/`. It must
cost positions and nothing else, and it must **say so in a sentence**.

**`Settings` gains `parser_exe: str | None`**, and `scripts/vrf_serve.py` gains
`--parser-exe` to set it.

**`/api/config` gains a `decoder` block**, built by calling
`csharpdecode.locate()` and catching `DecodeError`:

```jsonc
"decoder": {
  "found": true,
  "path": "E:\\...\\csharp\\VrfPositions\\bin\\Release\\net10.0\\vrf-positions.dll",
  "described": "decoder at csharp/VrfPositions/bin/Release/net10.0/vrf-positions.dll",
  "hint": ""                        // when absent: the build-decoder.bat sentence
}
```

`described` and `hint` follow `ArtCache.described` and `DemoRoot.described`: one
line naming what answered, or one line naming the command that fixes it. The
match list footer shows it beside the art line, so "why is there no DECODE
button" is answered on the page rather than in a traceback.

## Endpoints

### `POST /api/replays/{id}/decode`

```python
@app.post(f"{API}/replays/{{replay_id}}/decode", response_model=schema.ReplayDoc)
def decode_replay(replay_id: str) -> dict:
```

- 404 on an unknown id, as everywhere else.
- Take a **module-level decode lock**. The subprocess is CPU-bound and two at
  once halve both; this is the same reason `prewarm` runs one worker.
- Build a **fresh `Replay`** — `pipeline.open_replay(path)` — and run
  `tracks.attach(replay, path, tracks.Options(parser_exe=..., cache=True))` on
  it, then `names.resolve`. Never mutate the cached object: `Replay` is the one
  mutable dataclass and three modules annotate it in place, so a concurrent
  `GET` must see one replay or the other and never one whose positions have
  landed but whose codenames have not.
- `library.replace(replay_id, replay)` swaps it in and bumps `revision`.
- Return the new `ReplayDoc`.

**An unsupported build is a 200, not a 500.** `tracks.attach` is documented to
never raise for want of positions — it writes the refusal into
`position_source` — and the endpoint must not turn that into an error. The
response is a perfectly good replay that says why it has no positions. A test
pins this.

Note that `Options` no longer has a `blocks` knob and takes `parser_exe` rather
than `oodle_dll`; the decoder reads the stream in one pass, so a partial decode
is neither cheap to ask for nor useful to have.

### `GET /api/replays/{id}/positions`

Serves `positionfile.to_document(...)` — the same six-parallel-array columnar
shape the sidecar and the machine cache already use, which is what lets a test
assert the HTTP body is byte-identical to what `write` would have produced.

`tracks.sidecar_for` takes an `Extraction`, which only exists in the moments
after a decode. A replay loaded from cache has `replay.positions` directly, so
this needs a small builder — **`positionfile.Sidecar` from a `Replay`** — which
belongs in `tracks` beside `sidecar_for` rather than in `vrfserve`, because it
is a statement about the model and not about HTTP:

```python
def sidecar_of(replay: Replay) -> positionfile.Sidecar:
    """The stored shape of whatever positions a replay is already carrying."""
```

`codenames` comes from `replay.players`, `ability_spawns` from
`replay.ability_casts`, `description` from `position_source`. Cache the encoded
bytes on `Entry.positions_json` and drop them when `revision` moves — the field
is already there for this.

A replay with no positions returns the document with empty `tracks` **and its
`position_source`**, not a 404. Whether a decode happened is a fact about the
replay, and 404 would say the resource does not exist.

### `GET /api/jobs` — reduced, not dropped

The prewarmer is still worth having: 21 supported captures at four seconds each
is 75 s of waiting that can happen while someone reads the match list. But it no
longer needs a stream. One polled endpoint returning the current `Status` per
capture is enough at this speed, and `wire.card`'s `prewarm` field — already in
the schema, currently always `null` — is where it lands.

Start the `Prewarmer` in a FastAPI lifespan handler, pause it for the duration
of the decode lock, stop it on shutdown. `on_change` fires on a worker thread;
with no SSE there is nothing to marshal, so it writes into a plain dict behind a
lock.

## Frontend

- `MatchList` shows the decoder line from `/api/config` beside the art line, and
  the per-card `prewarm` chip when one is present.
- `Viewer` gains a **DECODE POSITIONS** button, shown when
  `has_positions === false` and the config says a decoder was found; when it was
  not, the sentence names `runners\build-decoder.bat` instead of offering a
  button that cannot work.
- The button is a `useMutation` that replaces the cached replay with the
  response. No polling, no event source. Four seconds of a disabled button with
  "DECODING…" is a worse experience than a progress bar and a much better one
  than either was at four minutes.
- After a decode the page must re-render **everything**, not just the map: the
  codenames and the ability casts only exist once the stream has been read, so
  the roster and the cast table change too. Replacing the whole query datum does
  this for free, which is exactly what the desktop viewer had to do by hand.

## Tests

`tests/test_vrfserve.py`:

- `POST /decode` on an unknown id → 404.
- `POST /decode` with `csharpdecode.run` patched to raise `DecodeError` → **200**
  with the refusal in `position_source`. This is the one most worth having; it
  is the rule the whole decoding layer is built on.
- `POST /decode` with a patched decode → the response's `has_positions` is true
  and the entry's `revision` moved.
- `/positions` on a replay with no decode → 200, empty `tracks`, non-empty
  `position_source`.
- `/positions` bytes equal `positionfile.write`'s for the same replay, and read
  back through `positionfile.read` to the same tracks.
- `/api/config` with `parser_exe` pointing at nothing → `found: false` and a
  `hint` naming the build runner, and the server still starts.
- Two concurrent decodes serialise rather than overlap.

`tests/test_tracks.py`: `sidecar_of(replay)` round-trips a replay's positions.

## Verification

    runners\build-decoder.bat
    runners\vrf-serve.bat --open

1. `/api/config` names the decoder it found, or names the command that builds
   one. Rename the binary and reload: the page says so and nothing 500s.
2. Open an unprepared, supported capture: DECODE POSITIONS, about four seconds,
   and the roster gains agent names it did not have — that is the codenames
   arriving with the stream, and the cheapest visible proof the whole document
   was replaced and not just the tracks.
3. Open an 11.11 capture: no button, one sentence, `position_source` verbatim.
4. `GET /api/replays/{id}/positions | python -c "import json,sys; ..."` against
   `positionfile.read` on the same capture's cache entry — identical tracks.
