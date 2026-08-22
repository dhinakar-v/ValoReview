# Plan 1 — bring the C# decoder onto the web branch

## Context

`vd-develop` gained one commit while this branch was being built:

    db53278  perf(vrfview): decode positions in C#, four minutes to four seconds

It is **local only** — `origin/vd-develop` does not have it. It adds
`csharp/VrfPositions` (a small emitter over `michel-giehl/ValorantReplayParser`)
and `vrfview/csharpdecode.py` to run it, and rewires `tracks.extract` to call
that instead of driving `vrfnet`. A full match decodes in about 4 s where it
took about 4 min; across the reference library, 21 of 21 supported captures in
75 s against roughly 84 minutes.

`vrfnet` stays in the tree deliberately: it is the independent check on the new
decoder, and the two agree on all 10,544 samples of the stored 12.10 decode
exactly. Do not delete it.

This plan is only the merge. What the change *means* for the server and the
browser is Plan 2; what it unlocks for the map is Plan 3.

## The merge is smaller than it looks

`git merge-tree --write-tree vd-webapp-migration vd-develop` gives exactly two
conflicts, both prose:

| File | |
|---|---|
| `CLAUDE.md` | **conflict** — both rewrote the architecture section |
| `README.md` | **conflict** — both rewrote the runner table and the dependency paragraph |
| `libraries/vrfview/app.py` | auto-merges |
| `libraries/vrfview/positionfile.py` | auto-merges |
| `libraries/vrfview/viewer.py` | auto-merges |
| `tests/test_vrfview.py` | auto-merges |

The three Python files auto-merge because their edits and mine do not overlap:
theirs are docstring prose ("four minutes" → "a few seconds"), mine are
structural (`open_replay` extracted, `to_document` extracted,
`provenance_text` reduced to a renderer).

## Sequence

**1. Push `vd-develop` first.** `origin/vd-develop` is still at `6799226`. If
this branch merges the local commit and pushes, the open PR shows `db53278` as
part of *this* branch's diff, which it is not.

    git push origin vd-develop

**2. Merge, do not rebase.** This branch is pushed and has a PR open against it;
rebasing would need a force-push over a branch someone may already be reading.
Three honest commits plus a merge is the better history here.

    git merge vd-develop

## Resolving the two conflicts

**`CLAUDE.md`.** Both sides restructured "Architecture". The merged section needs
every layer from both:

1. Container (`vrf_reader`, `vrf_to_json`)
2. **Decoder** (`csharp/VrfPositions` + `csharpdecode`) — theirs
3. Replication stream (`vrfnet`) — theirs, reframed as the independent check
4. Names (`valapi`, `valcatalog`)
5. Viewer (`vrfview`) — **both**: their "four minutes" edits *and* my
   `pipeline` / `provenance` sentences
6. **Server** (`vrfserve`) — mine
7. **Browser** (`web/`) — mine
8. Match list (`vrfhome`)

Fix the count in the lead sentence to match what is actually there — both sides
independently wrote "Five layers" and neither is right after the merge.

Also merge, not choose, in the conventions section:

- **Two runtime dependencies** → their `--parser-exe` reality plus my
  `fastapi`/`uvicorn` paragraph. `Pillow` stays for the sight mask and the
  glyphs; `customtkinter` still goes when the desktop app does.
- The **ability paragraph** keeps their wording. See the note below before
  touching "a smoke has a time and no coordinate".

**`README.md`.** Interleave rather than pick a side: their `--parser-exe`
replacing `--oodle-dll`, the decoder section and the rewritten Oodle section;
my `vrf-serve.bat` / `make-theme.bat` runner rows and the "The browser
interface" section. The dependency paragraph needs both facts —
`fastapi`/`uvicorn` *and* that only `vrf-reader --decode` and `vrf-net` still
want the Oodle DLL.

## Checks that a clean auto-merge does not give you

Compiling is not the bar. Four things to assert by hand:

1. **`tests/test_vrfview.py::TestHeadless::MODEL_MODULES` contains both
   `csharpdecode` and `provenance`.** Both sides added an entry to that tuple in
   nearly the same place; git will take both, but read it and confirm.
2. **`test_provenance.py::Headless` still passes.** It walks `pipeline`, which
   now reaches `tracks` → `csharpdecode` → `subprocess`. Still no toolkit, but
   that is the assertion, not an assumption.
3. **`tests/test_vrfserve.py::Headless` still passes.** It bans `vrfnet` from
   `wire.py`. `wire` does not import `tracks`, so this should hold — confirm it
   rather than assume it, because the ban exists to keep serialisation testable
   without a decoder.
4. **`positionfile.to_document` survived.** They edited that module's docstring;
   I restructured `write` around a new builder. Confirm `write` is still
   `json.dump(to_document(sidecar), fh)` and that
   `test_vrfconfig.py::SidecarRoundTrip::test_the_document_is_what_the_file_holds`
   passes — that invariant is what lets an HTTP body be checked against the
   sidecar format.

## Two inconsistencies the merge inherits — record, do not silently fix

**`prewarm`'s prompt-stop claim is now weaker than its docstring.** The stop
flag is checked in `Options.progress`, and progress is now called exactly twice
per capture — `(0, 1)` before the subprocess and `(1, 1)` after
(`tracks.py:193-201`). The docstring still says stopping is prompt *because* the
check is per-block rather than between captures; in practice it is now
effectively between captures. That is about 4 s, not 4 minutes, so the behaviour
is fine — the paragraph explaining it is not. Worth a one-line correction, but
it belongs in its own commit, not in a merge resolution.

**`Decoded.spawn_locations` is emitted and never read.** `csharp/VrfPositions`
captures `spawned.Location` per actor, `csharpdecode.read` parses it into
`Decoded.spawn_locations`, and **nothing in `tracks.py` consumes it**. CLAUDE.md
still states "the spawn transform is not decoded at all, so a smoke has a time
and no coordinate."

Leave that sentence exactly as it is during this merge. It is currently true of
what the model carries, and the values are unverified. Plan 3 has the check that
would settle it.

## Verification

    runners\test.bat                 expect all green, 26 skipped without Demos/
    runners\lint.bat
    cd web && npm test               9 passing, untouched by this merge
    uv run python scripts/vrf_serve.py --routes

Then, with a real library and a built decoder:

    runners\build-decoder.bat
    runners\vrf-serve.bat --open

The match list should be unchanged — `scan` reads plain chunks and never touched
the decoder — and a prepared capture should still open on its provenance panel.
