r"""
One entry point for the packaged desktop backend.

    valoreview-backend serve --port 8123 --demo-path D:\Demos ...
    valoreview-backend fetch-assets --out %LOCALAPPDATA%\ValoReview\assets

A frozen bundle has one executable, and the desktop shell needs two things out
of it: the server, and the first-run art fetch.  Those are `scripts/vrf_serve.py`
and `scripts/fetch_assets.py`, both of which already own their own argument
parsing, so this is an argv switch and nothing else -- it moves no logic, makes
no decision and adds no third place a claim could come from.

The fetch is a subcommand here rather than a route on the server because
`create_app` resolves art exactly once, at startup: `build_settings` calls
`art.load()`, `create_app` captures the `ArtCache`, and `_mount_static` decides
then and there whether to mount the pictures or install the 404 handler.  Art
that lands afterwards is not picked up, so a fetch has to finish *before* the
server is spawned -- which a route could not arrange for itself, and which is
also why `vrfserve`'s closed route list stays closed.

`serve` is the default, so an argv that names no subcommand starts the server.
"""

from __future__ import annotations

import sys

import fetch_assets
import vrf_serve

COMMANDS = ("serve", "fetch-assets")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args and args[0] in COMMANDS else "serve"
    rest = args[1:] if args and args[0] in COMMANDS else args
    if command == "fetch-assets":
        # fetch_assets takes the command itself as a positional, defaulting to
        # `fetch`; only that one is wanted here, since `list` prints a catalogue
        # to a console the desktop app does not have.
        return fetch_assets.main(["fetch", *rest])
    return vrf_serve.main(rest)


if __name__ == "__main__":
    sys.exit(main())
