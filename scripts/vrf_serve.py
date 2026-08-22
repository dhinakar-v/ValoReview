r"""
Serve the replay library over HTTP.

    runners\vrf-serve.bat                   scan DEMO_PATH and serve on 8000
    runners\vrf-serve.bat --open            and open a browser at it
    runners\vrf-serve.bat --demo-path D:\x  scan somewhere else
    runners\vrf-serve.bat --no-art          serve with no pictures at all
    runners\vrf-serve.bat --routes          list the endpoints and exit

Binds to 127.0.0.1 and nothing else.  This reads a directory of captures off
the local disk and has no authentication, because it is one person's desktop
app that happens to render in a browser; `--host` exists for the case where
that is deliberately not true, and says so.

The scan happens at startup rather than on the first request, so the process
that is listening is one that has already found the library or already knows it
has not.  Cold on 101 captures that is about four seconds and warm about a
thirtieth of one, because `vrfhome.scan` caches by `(path, mtime, size)`.
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

# This file drives libraries/vrfserve/, and the two are named differently on
# purpose: a script and a package of the same name collide on import, and the
# package wins, so `import vrfserve` would never reach this module.
import uvicorn

from vrfserve.app import Settings, create_app, decoder_doc
from vrfview import art as art_mod

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# How long to let uvicorn bind before pointing a browser at it.  A browser that
# arrives first shows a connection error the user then has to reload past.
BROWSER_DELAY_S = 1.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="vrf-serve",
        description="Serve the replay library and the web interface.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="interface to bind (default 127.0.0.1; anything else is public)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--demo-path",
        default=None,
        help="replay directory, overriding DEMO_PATH",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="art directory (default assets/)",
    )
    parser.add_argument(
        "--no-art",
        action="store_true",
        help="serve no pictures; every claim the interface makes is unchanged",
    )
    parser.add_argument(
        "--parser-exe",
        default=None,
        help="the built position decoder, overriding VRF_PARSER_EXE",
    )
    parser.add_argument(
        "--no-prewarm",
        action="store_true",
        help="do not decode the library in the background",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="re-read every capture rather than trusting the scan cache",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="open a browser once the server is listening",
    )
    parser.add_argument(
        "--routes",
        action="store_true",
        help="print the endpoints and exit, without binding a port",
    )
    return parser.parse_args(argv)


def build_settings(args: argparse.Namespace) -> Settings:
    """Resolve art the way every other entry point does, then bundle it."""
    if args.no_art:
        art = art_mod.ArtCache()
    elif args.assets:
        art = art_mod.load(Path(args.assets))
    else:
        art = art_mod.load()
    return Settings(
        demo_path=args.demo_path,
        art=art,
        use_cache=not args.no_cache,
        parser_exe=args.parser_exe,
        prewarm=not args.no_prewarm,
    )


def print_routes(app) -> None:
    """Every path the server answers on, for a check that needs no browser."""
    for route in app.routes:
        methods = ",".join(sorted(getattr(route, "methods", {"MOUNT"})))
        print(f"  {methods:<12} {route.path}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = build_settings(args)
    app = create_app(settings)

    library = app.state.library
    print(f"replays  {library.result.described}")
    print(f"art      {settings.art.described}")
    print(f"decoder  {decoder_doc(settings.parser_exe)['described']}")
    if not settings.web_built:
        print(f"page     {app.state.settings.web_dir}: not built")

    if args.routes:
        print_routes(app)
        return 0

    url = f"http://{args.host}:{args.port}/"
    print(f"serving  {url}")
    if args.open:
        threading.Timer(BROWSER_DELAY_S, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
