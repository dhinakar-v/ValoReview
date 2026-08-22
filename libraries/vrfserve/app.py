"""
The HTTP interface: routes, mounts, and nothing that decides anything.

Every handler here reads something the rest of the project already computed and
hands it over.  There is no inference in this file and there is not meant to be:
`infer` derives, `names` looks up, `tracks` decodes, `provenance` accounts for
all three, and a route that started deciding things would be a fifth place a
claim could come from.

Handlers are plain `def`, not `async def`, and that is deliberate.  FastAPI runs
a sync handler in a threadpool and an async one on the event loop, so a
`loader.load` or a twelve-megabyte sidecar read inside `async def` would block
every other request for its duration.  Only something genuinely non-blocking
should ever be async here.

Two mounts, in this order, for two different reasons.  `/assets` is
`StaticFiles` over the art directory with `check_dir=False`, because a missing
`assets/` is the ordinary state of a fresh checkout: it has to 404 a picture,
not refuse to start.  The page is mounted last, at `/`, so it cannot shadow the
API; when it has not been built the mount is replaced by one sentence naming the
command that builds it, on the same principle as `MissingArtView` -- say what is
missing rather than draw something in its place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import vrfconfig
from vrfhome import scan
from vrfserve import schema, wire
from vrfserve.library import Library
from vrfview import art as art_mod

if TYPE_CHECKING:
    from vrfview.art import ArtCache

API = "/api"

WEB_DIR = Path("web") / "dist"
WEB_HINT = "the web interface is not built; run: cd web && npm install && npm run build"

NO_SUCH_REPLAY = "no replay with that id in the current scan"
NO_SUCH_MAP = "no art for that map"

# Where Vite is told to emit the bundle. Not its default of `assets`: that
# is where Riot's art is served from, and a bundle there would be shadowed
# by it -- the page would load and its own JavaScript would 404.
SPA_ASSETS = "static"

# Below this a response is not worth compressing; a metadata payload is
# comfortably above it and a page of cards usually is too.
GZIP_MINIMUM = 1024


@dataclass
class Settings:
    """What the server was started with."""

    demo_path: str | None = None
    art: ArtCache = field(default_factory=art_mod.ArtCache)
    catalog: object | None = None
    web_dir: Path = WEB_DIR
    use_cache: bool = True

    @property
    def web_built(self) -> bool:
        return (self.web_dir / "index.html").is_file()


def demo_root_doc(root) -> dict:
    return {
        "path": str(root.path),
        "exists": root.exists,
        "source": root.source,
        "described": root.described,
    }


def art_doc(cache: ArtCache) -> dict:
    return {
        "described": cache.described,
        "empty": cache.empty,
        "root": str(cache.root),
        "source": cache.source,
        "version": cache.version,
        "maps": len(cache.maps),
        "agents": len(cache.agents),
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application over one scan of one replay directory."""
    config = settings if settings is not None else Settings()
    library = Library(catalog=config.catalog, root=config.demo_path)
    library.rescan(cache=config.use_cache)

    app = FastAPI(
        title="Valorant replay analyzer",
        description=(
            "Reads .vrf captures off DEMO_PATH and serves what they state, "
            "what was decoded out of them, what was looked up and what was "
            "inferred -- each labelled as which."
        ),
        version="0.1.0",
    )
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM)
    app.state.library = library
    app.state.settings = config

    _add_config_routes(app, config)
    _add_library_routes(app, library, config)
    _add_replay_routes(app, library, config)
    _add_map_routes(app, config)
    _mount_static(app, config)
    return app


def _add_config_routes(app: FastAPI, config: Settings) -> None:
    @app.get(f"{API}/config", response_model=schema.ConfigDoc)
    def read_config() -> dict:
        """Where the server looked, and what it found there."""
        return {
            "demo_root": demo_root_doc(vrfconfig.demo_root(config.demo_path)),
            "art": art_doc(config.art),
            "catalog_source": getattr(config.catalog, "described", "") or "",
            "web_built": config.web_built,
            "web_hint": "" if config.web_built else WEB_HINT,
        }


def _add_library_routes(app: FastAPI, library: Library, config: Settings) -> None:
    @app.get(f"{API}/library", response_model=schema.LibraryDoc)
    def read_library(query: Annotated[schema.LibraryQuery, Query()]) -> dict:
        """
        The match list, filtered, sorted and paged the way the scanner does it.

        All three stay here rather than in the browser because `sort_cards`
        already encodes a judgement -- an undated card sorts to the end, not to
        the epoch -- and a second implementation of that in another language is
        exactly the drift this project spends its docstrings avoiding.

        A capture held back by `playable_only` is counted in `counts.hidden`,
        never silently dropped: there is no schematic to fall back to, so the
        honest thing is to say how many are not shown and let one request show
        them.
        """
        if query.refresh:
            library.rescan(cache=False)
        result = library.result
        cards = scan.filter_cards(
            result.cards,
            map_name=query.map_name,
            date=query.date,
        )
        if query.playable_only:
            cards = [c for c in cards if c.playable]
        cards = scan.sort_cards(cards, descending=query.descending)
        root = result.root or vrfconfig.demo_root(config.demo_path)
        return {
            "root": demo_root_doc(root),
            "described": result.described,
            "read": result.read,
            "cached": result.cached,
            "counts": {
                "total": len(result.cards),
                "playable": len(result.playable),
                "hidden": len(result.hidden),
                "failed": len(result.failed),
            },
            "maps_present": scan.maps_present(result.cards),
            "page": query.page,
            "page_count": scan.page_count(cards),
            "per_page": scan.PER_PAGE,
            "cards": [
                wire.card(c, library.id_of(c.path), config.art, None)
                for c in scan.page(cards, number=query.page)
            ],
        }


def _add_replay_routes(app: FastAPI, library: Library, config: Settings) -> None:
    @app.get(f"{API}/replays/{{replay_id}}", response_model=schema.ReplayDoc)
    def read_replay(replay_id: str) -> dict:
        """
        One replay: read, inferred, named, and whatever decode was already done.

        Opening does not decode.  `pipeline.open_replay` picks up a sidecar or a
        cache entry if one exists, and otherwise says so in `position_source` --
        four minutes before the first frame is not an opening.
        """
        entry = library.open(replay_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=NO_SUCH_REPLAY)
        with entry.lock:
            return wire.replay_doc(entry.replay, replay_id, config.art)

    @app.delete(f"{API}/replays/{{replay_id}}")
    def close_replay(replay_id: str) -> dict:
        """Let go of an open replay.  An unknown id is not an error to close."""
        return {"closed": library.close(replay_id)}


def _add_map_routes(app: FastAPI, config: Settings) -> None:
    @app.get(f"{API}/maps", response_model=list[schema.MapSummary])
    def read_maps() -> list[dict]:
        art = config.art
        return [
            {
                "name": entry.name,
                "codename": entry.codename,
                "map_url": entry.map_url,
                "plottable": entry.plottable,
                "listview_url": wire.asset_url(entry.listview, art.root),
                "minimap_url": wire.asset_url(entry.minimap, art.root),
                "callout_count": len(entry.callouts),
            }
            for entry in sorted(art.maps.values(), key=lambda m: m.name)
        ]

    @app.get(f"{API}/maps/{{key}}", response_model=schema.MapDoc)
    def read_map(key: str) -> dict:
        """
        One map's picture and coordinates.

        This handler takes a map key and nothing else, and that is a structural
        promise rather than an oversight: the desktop map reference is handed no
        `Replay` by design, because it describes the map and not the match.
        Positions belong on the minimap and are not smuggled in here.
        """
        entry = config.art.maps.get(key)
        if entry is None:
            raise HTTPException(status_code=404, detail=NO_SUCH_MAP)
        return wire.map_art(entry, config.art.root)


def _mount_static(app: FastAPI, config: Settings) -> None:
    """The art directory, then the built page -- in that order, always."""
    if Path(config.art.root).is_dir():
        app.mount(
            wire.ASSET_PREFIX,
            StaticFiles(directory=str(config.art.root)),
            name="assets",
        )
    else:
        # A clean checkout has no assets/ at all, and that has to cost pictures
        # rather than the server.  `check_dir=False` is not enough on its own:
        # it skips the check at construction and StaticFiles then raises
        # RuntimeError on the first request instead, which is a 500 where a 404
        # belongs.  So the mount is simply not made, and every asset URL misses.
        @app.get(f"{wire.ASSET_PREFIX}/{{path:path}}")
        def no_art(path: str) -> None:  # noqa: ARG001  (the path is the 404)
            raise HTTPException(status_code=404, detail=art_mod.FETCH_HINT)

    if not config.web_built:

        @app.get("/", response_class=PlainTextResponse)
        def unbuilt() -> str:
            """One sentence naming what is missing, never a stand-in page."""
            return WEB_HINT

        return

    index = config.web_dir / "index.html"

    # The page routes on the client, so /replay/<id> is a real address that no
    # file answers to.  StaticFiles alone would 404 it, which breaks every
    # bookmark and every reload away from the root.  Files win where they
    # exist; everything else that is not the API gets the page and lets the
    # router read the URL.
    app.mount(
        f"/{SPA_ASSETS}",
        StaticFiles(directory=str(config.web_dir / SPA_ASSETS)),
        name="web-static",
    )

    @app.get("/{path:path}", response_class=FileResponse)
    def page(path: str) -> FileResponse:
        candidate = (config.web_dir / path).resolve()
        root = config.web_dir.resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)
