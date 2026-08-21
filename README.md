# val-replay-analyzer

Decode and replay Valorant `.vrf` replay files.

## Layout

    libraries/      importable code -- vrf_reader.py, vrf_to_json.py, vrfnet/, vrfview/
    scripts/        standalone CLIs -- vrf_net.py, vrf_view.py, fetch_assets.py
    runners/        .bat launchers; each one works from any directory
    tests/          test suite
    docs/           decoding research, findings, API reference and session handoffs
    Demos/          .vrf captures (gitignored)
    out/            vrf_to_json output (gitignored)
    assets/         downloaded Valorant art (gitignored)
    vendor/         Oodle runtime drop-in (gitignored except its README)

`libraries/` is the source root, not a package: `uv sync` installs its contents so
`import vrf_reader` and `import vrfnet` resolve from anywhere.

## Running

Every runner forwards its arguments and returns the underlying exit code.

    runners\vrf-reader.bat <replay.vrf> --events    inspect the container
    runners\vrf-to-json.bat <replay.vrf> -o out.json
    runners\vrf-net.bat actors <block.bin>          decode the replication stream
    runners\vrf-view.bat <replay.vrf>               open the 2D viewer
    runners\vrf-view.bat dump <replay.json>         headless text dump
    runners\vrf-view.bat catalog                    what names and art are cached
    runners\fetch-assets.bat list                   plan the art download
    runners\fetch-assets.bat fetch                  ~85 MB into assets/

Pass `--help` to any of them for the full argument list.

## Oodle

The viewer and the event timeline need no setup: everything they read lives in
plain chunks. Only `--decode`, `vrf-to-json` without `--no-decompress`, and
`vrf-net` on a `.vrf` touch the compressed REPLAYDATA and CHECKPOINT payloads,
and those are Oodle (Mermaid), which needs an `oo2core_*_win64.dll` at runtime.

Valorant cannot supply it. Its shipping exe links Oodle statically and exports
no Oodle symbols, so there is nothing to load from the game directory. The DLL
has to come from elsewhere, and `libraries/oodlefind.py` looks in this order:

    --oodle-dll PATH          an argument beats everything
    VRF_OODLE_DLL             real environment, then the nearest .env
    vendor/                   drop the DLL in, nothing else to configure
    cache                     whatever a previous scan resolved
    Steam and Epic libraries  any installed UE4/UE5 game ships one

The scan globs a few known layouts per game rather than walking whole installs,
and caches its answer, so it costs a fraction of a second once per machine. The
first two are configured deliberately, so a path that does not exist is an
error rather than a silent fall-through to the scan.

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

The lookup is cache-first and needs no key: `vrf-view` reads
`assets/content-<locale>.json` if a refresh has written one, else the
`assets/manifest.json` that `fetch-assets` already produces, else it falls back to
a built-in codename table -- and it always says which of the three answered.

    runners\vrf-view.bat catalog             what is cached, and where it is looked for
    runners\vrf-view.bat catalog --refresh   fetch val-content-v1 (needs RIOT_API)
    runners\vrf-view.bat dump x.vrf --no-catalog     ignore any catalogue

`--refresh` is the only command in the project that calls api.riotgames.com. Put a
personal development key in `.env` as `RIOT_API=RGAPI-...`; they expire every 24
hours. Everything else works offline and keyless.

## Art

`fetch-assets` caches Riot's map and agent art under `assets/`, and the viewer
draws two things with it. A **roster band** across the top: the map's menu strip
and one icon per loadout slot, in the file's own order -- the file links a loadout
to no actor net ID, so the band is captioned as unattributable. (A player can still
be named, but from its own pawn; see *Positions* below.) And a **map reference
window**, behind the `Map` button: Riot's
radar image with Riot's own callouts, placed through the world-to-image transform
in `assets/manifest.json`.

That window plots nothing from the replay: it describes the map, not the match, and
is handed no replay to be tempted by.

## Positions

Player positions are in a `.vrf`, but not in the open. Riot obfuscates every
property payload in the replication stream; `vrfnet` undoes that and decodes the
movement RPC underneath, which carries a position, a heading and a velocity per
player about a hundred times a second.

    runners\vrf-view.bat dump x.vrf --positions          decode and report them
    runners\vrf-view.bat dump x.vrf --positions --blocks 2   stop after 2 blocks

It is opt-in because it is the one slow thing here: it needs the Oodle DLL and
takes around four minutes on a full match, against 0.04s for everything else.
Decoding also names each player -- an agent's pawn states its own archetype, so
`dump` reports a per-player agent alongside the unattributable loadout roster,
and the two agree by two joins that share no term.

Only some builds decode. The transform changes every patch, so `12.10`, `12.11`
and `13.00`--`13.02` work and everything older -- including the reference capture
-- refuses by name rather than guessing:

    - positions: no positions: no payload transform for build
      '++Ares-Core+release-11.11'; supported: ...

Nothing else changes when positions are absent, and nothing invents one when they
are: a player with no track is drawn with no track.

    runners\vrf-view.bat x.vrf --no-art       draw no art at all
    runners\vrf-view.bat x.vrf --assets DIR   read the cache from somewhere else

Art is optional everywhere: with no `assets/`, the viewer loses the band and the
button and states exactly what it stated before. `dump` and `catalog` both report
what resolved.

Player names, ranks and per-round economy live in `val-match-v1`, which is
**403 on a personal development key** --
every endpoint, including `/matches/{matchId}`, before the match id is even parsed.
So `dump` reports the match id it read from the container header and does not look
it up. `libraries/valapi.py` implements the call for the day a production key is
granted, and diagnoses the 403 rather than blaming the key.
`docs/valorant-api.md` is the full endpoint and DTO reference.

## Development

Requires [uv](https://docs.astral.sh/uv/). No runtime dependencies — the project is
stdlib + tkinter.

    uv sync                       # create .venv and install the project + dev tools
    runners\test.bat              # run tests      (uv run pytest)
    runners\lint.bat              # lint           (config: ruff.toml)
    runners\format.bat            # format
