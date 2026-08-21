# val-replay-analyzer

Decode and replay Valorant `.vrf` replay files.

## Layout

    libraries/      importable code -- vrf_reader.py, vrf_to_json.py, vrfnet/, vrfview/
    scripts/        standalone CLIs -- vrf_net.py, vrf_view.py
    runners/        .bat launchers; each one works from any directory
    tests/          test suite
    docs/           decoding research, findings and session handoffs
    Demos/          .vrf captures (gitignored)
    out/            vrf_to_json output (gitignored)

`libraries/` is the source root, not a package: `uv sync` installs its contents so
`import vrf_reader` and `import vrfnet` resolve from anywhere.

## Running

Every runner forwards its arguments and returns the underlying exit code.

    runners\vrf-reader.bat <replay.vrf> --events    inspect the container
    runners\vrf-to-json.bat <replay.vrf> -o out.json
    runners\vrf-net.bat actors <block.bin>          decode the replication stream
    runners\vrf-view.bat <replay.vrf>               open the 2D viewer
    runners\vrf-view.bat dump <replay.json>         headless text dump

Pass `--help` to any of them for the full argument list.

## Development

Requires [uv](https://docs.astral.sh/uv/). No runtime dependencies — the project is
stdlib + tkinter.

    uv sync                       # create .venv and install the project + dev tools
    runners\test.bat              # run tests      (uv run pytest)
    runners\lint.bat              # lint           (config: ruff.toml)
    runners\format.bat            # format
