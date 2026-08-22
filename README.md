# val-replay-analyzer

Decode and replay Valorant `.vrf` replay files.

## Layout

    libraries/      importable code -- vrf_reader.py, vrf_to_json.py, vrfnet/, vrfview/, vrfserve/
    scripts/        standalone CLIs -- vrf_serve.py, fetch_assets.py, make_*.py
    csharp/         the position decoder (VrfPositions); see The decoder below
    web/            the browser interface (React over vrfserve; web/dist gitignored)
    runners/        .bat launchers; each one works from any directory
    tests/          test suite
    docs/           decoding research, findings, API reference and session handoffs
    Demos/          .vrf captures (gitignored)
    out/            vrf_to_json output (gitignored)
    .cache/         decodes, scans and scratch; delete to reset (gitignored)
    assets/         downloaded Valorant art (gitignored)
    vendor/         Oodle and decoder drop-ins (gitignored except its README)

`libraries/` is the source root, not a package: `uv sync` installs its contents so
`import vrf_reader` and `import vrfnet` resolve from anywhere.

`.cache/` is everything the project can regenerate -- decoded positions, the
resolved Oodle path, the match-list scan and the decoder's scratch.
`libraries/vrfcache.py` finds it by walking up for `pyproject.toml`, so it is
the same directory whatever you run from. Deleting it is a complete reset; the
next run simply does the work again.

## Running

Every runner forwards its arguments and returns the underlying exit code.

    runners\vrf-reader.bat <replay.vrf> --events    inspect the container
    runners\vrf-to-json.bat <replay.vrf> -o out.json
    runners\vrf-to-json.bat <replay.vrf> -o out.json --positions
                                                    and a positions sidecar
    runners\vrf-serve.bat                           the replay library, in a browser
    runners\vrf-serve.bat --routes                  list the endpoints, bind nothing
    runners\build-decoder.bat                       build the position decoder
    runners\fetch-assets.bat list                   plan the art download
    runners\fetch-assets.bat fetch                  ~85 MB into assets/

Pass `--help` to any of them for the full argument list.

`DEMO_PATH` in `.env` says where the replay library lives; it defaults to
`Demos/`. `libraries/vrfconfig.py` resolves it and reports which of the three
sources answered, so an empty list can always say where it looked.

## Positions on a machine with no decoder

Decoding positions needs the built decoder and about four seconds on a full
match, and works only on the builds `vrfnet/payload_transform.py` supports.
`vrf-to-json.bat ... --positions` does that decode once and writes
`<out>.positions.json` beside the dump; from then on anything that opens the
capture reads the sidecar and needs no decoder at all. A sidecar belonging to
another match is refused rather than drawn.

The server does the same on its own account: `vrfhome/prewarm.py` decodes the
library in the background, one capture at a time, into `.cache/positions/`, so
a card is usually ready before it is clicked. The viewer's DECODE POSITIONS
button handles whatever is not.

## The decoder

Positions come from `csharp/VrfPositions`, a small C# program that references
[`michel-giehl/ValorantReplayParser`](https://github.com/michel-giehl/ValorantReplayParser)
and writes the thinned movement samples and actor spawns this project consumes.
It exists because the same decode is about four seconds there and about four
minutes in Python -- the cost was never the decompression, it was three million
movement records through a bit reader backed by a Python int.

Build it once:

    git clone https://github.com/michel-giehl/ValorantReplayParser.git ..\ValorantReplayParser
    runners\build-decoder.bat

That needs the .NET 10 SDK. `runners\build-decoder.bat -p:VrpRoot=<path>` if
the clone lives somewhere other than beside this repository.
`libraries/vrfview/csharpdecode.py` then looks in this order:

    --parser-exe PATH     an argument beats everything
    VRF_PARSER_EXE        real environment, then the nearest .env
    vendor/parser/        a published, self-contained drop-in
    csharp/VrfPositions/  whatever this working tree last built

`libraries/vrfnet/` used to decode the same stream in pure Python, and the two
agreed on all 10,544 samples of the reference 12.10 decode, exactly, in
x, y, z, yaw and pitch. That check has been made; the 2,400 lines that made it
have been removed. What is left of the package is `payload_transform` -- which
builds can be decoded, and the keystream each one whitens its payloads with --
and the bit reader its test uses. See `docs/valorant-replay-parser-features.md`.

## Oodle

Positions no longer need Oodle -- the decoder does its own decompression. What
still does: `--decode` and `vrf-to-json` without `--no-decompress`, both of
which touch the compressed REPLAYDATA and CHECKPOINT payloads directly. The
viewer and the event timeline need no setup at all:
everything they read lives in plain chunks. Those payloads are Oodle (Mermaid),
which needs an `oo2core_*_win64.dll` at runtime.

Valorant cannot supply it. Its shipping exe links Oodle statically and exports
no Oodle symbols, so there is nothing to load from the game directory. The DLL
has to come from elsewhere, and `libraries/oodlefind.py` looks in this order:

    --oodle-dll PATH          an argument beats everything
    VRF_OODLE_DLL             real environment, then the nearest .env
    vendor/                   drop the DLL in, nothing else to configure
    cache                     whatever a previous scan resolved
    Steam and Epic libraries  any installed UE4/UE5 game ships one

The scan globs a few known layouts per game rather than walking whole installs,
and caches its answer in `.cache/oodle.json`, so it costs a fraction of a
second once per checkout. The first two are configured deliberately, so a path
that does not exist is an error rather than a silent fall-through to the scan.

To set it explicitly, copy `.env.example` to `.env` and fill in:

    VRF_OODLE_DLL=C:\path\to\oo2core_9_win64.dll

`vendor/README.md` covers where to find a DLL. It is not committed here: Oodle
is Epic's, licensed for redistribution inside a licensed title rather than as a
standalone download, so this repository ships none and never will.

## Assets

`fetch-assets` caches Riot's map, agent and ability art from
[valorant-api.com](https://valorant-api.com) into `assets/`, alongside a
`manifest.json` holding each map's UUID, its internal codename and the
`xMultiplier` / `yMultiplier` / `xScalarToAdd` / `yScalarToAdd` transform that
converts a world coordinate to a fraction of the radar image. Existing files are
skipped, so a run resumes; `--force` re-downloads and `--only maps|agents|roles`
narrows the set. The art is Riot Games' intellectual property and the cache is
gitignored; nothing here redistributes it. `docs/valorant-assets.md` documents the
folder, the manifest schema and the measured world-to-minimap transform.

## Names, and the Riot API

A replay states its map as an internal asset path (`/Game/Maps/Infinity/Infinity`)
and its agents as UUIDs. Both resolve against Riot's published content catalogue,
which is what turns them into `Abyss` and `Astra, Killjoy, Waylay, ...` in the
viewer and in `dump`.

The lookup is cache-first and needs no key: `libraries/valcatalog.py` reads
`assets/content-<locale>.json` if a refresh has written one, else the
`assets/manifest.json` that `fetch-assets` already produces, else it falls back to
a built-in codename table -- and it always says which of the three answered.

`fetch-assets` is unauthenticated and is what the server actually consumes; the
`val-content-v1` refresh path in `libraries/valapi.py` is the only thing in the
project that calls api.riotgames.com, and it needs a personal development key in
`.env` as `RIOT_API=RGAPI-...`. Everything else works offline and keyless.

## Art

`fetch-assets` caches Riot's map, agent, role and weapon art under `assets/`,
and the server hands it to the page by URL: `GET /api/maps/{name}` carries the
radar image, the world-to-image transform and Riot's own callouts, and
`GET /api/weapons` carries the weapon catalogue as one document.

Art is a picture and never a claim. A missing or partial `assets/` costs
thumbnails, portraits and the radar image and changes nothing the interface
states -- `--no-art` forces that path deliberately.

## Positions

Player positions are in a `.vrf`, but not in the open. Riot obfuscates every
property payload in the replication stream; the decoder undoes that and decodes
the movement RPC underneath, which carries a position, a heading and a velocity
per player about a hundred times a second.

It is the slowest thing here: it needs the decoder built by
`runners\build-decoder.bat` and takes about four seconds on a full match,
against 0.04s for everything else. It took four minutes until the same decode
moved out of Python; see **The decoder** above.
Decoding also names each player -- an agent's pawn states its own archetype, so
a per-player agent is read beside the unattributable loadout roster, and the two
agree by two joins that share no term.

Only some builds decode. The transform changes every patch, so `12.10`, `12.11`
and `13.00`--`13.02` work and everything older -- including the reference capture
-- refuses by name rather than guessing:

    - positions: no positions: no payload transform for build
      '++Ares-Core+release-11.11'; supported: ...

Nothing else changes when positions are absent, and nothing invents one when they
are: a player with no track is drawn with no track. A capture whose build has no
transform is not listed as playable at all, which costs one string comparison and
no decompression.

    runners\vrf-serve.bat --no-art            serve no pictures at all
    runners\vrf-serve.bat --assets DIR        read the cache from somewhere else

Player names, ranks and per-round economy live in `val-match-v1`, which is
**403 on a personal development key** --
every endpoint, including `/matches/{matchId}`, before the match id is even parsed.
So `dump` reports the match id it read from the container header and does not look
it up. `libraries/valapi.py` implements the call for the day a production key is
granted, and diagnoses the 403 rather than blaming the key.
`docs/valorant-api.md` is the full endpoint and DTO reference.

## The browser interface

`runners\vrf-serve.bat` scans `DEMO_PATH` and serves it on `http://127.0.0.1:8000`,
binding the loopback interface and nothing else. It serves what the file states,
what was decoded out of it, what was looked up and what was inferred — each
labelled as which — and `/docs` carries the generated OpenAPI reference.

The page lives in `web/` and is built with `cd web && npm install && npm run build`;
the server mounts `web/dist` at `/` when it is there, and says which command builds
it when it is not. In development run `npm run dev` alongside the server: Vite
proxies `/api` and `/assets` across, so both modes are same-origin and no CORS is
granted to anyone. `web/README.md` covers the rest, including why each npm
dependency is there.

There was a CustomTkinter desktop app beside it, reading the same model through
`vrfview.pipeline`. It has been removed: the browser interface replaced every
page it had, and two interfaces over one model meant every claim had two places
to be made and two places to drift.

## Development

Requires [uv](https://docs.astral.sh/uv/). The decoding pipeline is stdlib and stays
that way; the interface on top of it is not. `fastapi`/`uvicorn` are the web
interface and `Pillow` reads the radar PNG's alpha channel for the sight mask.
`pyproject.toml`
is the only dependency list — there is no `requirements.txt` mirroring it, because
two lists drift. `pip install .` reads it as readily as `uv sync` does.
`python-dotenv` is deliberately not used — `libraries/envfile.py`
already reads `.env` with the same precedence and mutates nothing.

Two things outside pip. Positions need the compiled decoder — "The decoder" above,
built by `runners\build-decoder.bat` — and the browser interface needs node
(`cd web && npm install`). Neither is needed to run the tests, and the Oodle DLL is
now wanted only by `vrf-reader --decode` and `vrf-to-json`, which read compressed
chunks directly.

    uv sync                       # create .venv and install the project + dev tools
    runners\test.bat              # run tests      (uv run pytest)
    runners\lint.bat              # lint           (config: ruff.toml)
    runners\format.bat            # format
    runners\make-theme.bat        # regenerate web/src/theme.generated.css
    runners\make-golden.bat       # regenerate tests/golden (the two-language contract)
    cd web && npm test            # the browser tests
