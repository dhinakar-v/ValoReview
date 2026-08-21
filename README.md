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

## Development

Requires [uv](https://docs.astral.sh/uv/). No runtime dependencies — the project is
stdlib + tkinter.

    uv sync                       # create .venv and install the project + dev tools
    runners\test.bat              # run tests      (uv run pytest)
    runners\lint.bat              # lint           (config: ruff.toml)
    runners\format.bat            # format
