"""
The HTTP interface: routes, mounts, and nothing that decides anything.

Every handler here reads something the rest of the project already computed and
hands it over.  There is no inference in this file and there is not meant to be:
`infer` derives, `names` looks up and `tracks` decodes, and a route that started
deciding things would be a fourth place a claim could come from.

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

import json
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import vrfconfig
from vrfhome import prewarm, scan
from vrfserve import schema, wire
from vrfserve.library import Library
from vrfview import art as art_mod
from vrfview import csharpdecode, names, pipeline, positionfile, sight, tracks

if TYPE_CHECKING:
    from vrfview.art import ArtCache

API = "/api"

WEB_DIR = Path("web") / "dist"
WEB_HINT = "the web interface is not built; run: cd web && npm install && npm run build"

NO_SUCH_REPLAY = "no replay with that id in the current scan"
NO_SUCH_MAP = "no art for that map"
NO_SIGHT_MASK = (
    "no radar image for that map, so there is no silhouette to raycast "
    "against; the sight layer is unavailable rather than empty"
)

# Where Vite is told to emit the bundle. Not its default of `assets`: that
# is where Riot's art is served from, and a bundle there would be shadowed
# by it -- the page would load and its own JavaScript would 404.
SPA_ASSETS = "static"

# Below this a response is not worth compressing; a metadata payload is
# comfortably above it and a page of cards usually is too.
GZIP_MINIMUM = 1024

# Decodes are serialised: the decoder is a CPU-bound subprocess and two at
# once make both slower, which is the same reason the prewarmer runs one
# worker. Module level rather than per-app so a test client cannot
# accidentally get a second one.
_DECODE_LOCK = threading.Lock()


class _Preparation:
    """
    The background decode, and the statuses it reports.

    `Prewarmer.on_change` fires on its own worker thread. There is no event
    loop to marshal onto here -- the plan for a four-minute decode wanted an
    SSE stream and a thread-to-loop bridge, and a four-second one does not, so
    a status is just written into a dict behind a lock and read by whoever
    polls. That is the whole of the machinery this replaced.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._statuses: dict[str, dict] = {}
        self.worker = None

    def start(self, cards, catalog, registry) -> None:
        self.worker = prewarm.Prewarmer(
            cards,
            on_change=lambda path, status: self._record(registry, path, status),
            catalog=catalog,
        )
        # Seed from the worker's own queue, not from every card. `Prewarmer`
        # queues only what is playable, and reporting QUEUED for a capture that
        # will never be prepared would be a chip claiming a wait that is not
        # going to end. No chip at all is the honest answer there.
        for card in self.worker.queue:
            self._record(registry, card.path, self.worker.status(card.path))
        self.worker.start()

    def _record(self, registry, path, status) -> None:
        with self._guard:
            self._statuses[registry.id_for_path(path)] = {
                "state": status.state,
                "note": status.note,
                "done": status.done,
                "total": status.total,
                "label": status.label,
            }

    def status(self, replay_id: str) -> dict | None:
        with self._guard:
            return self._statuses.get(replay_id)

    def all(self) -> dict:
        with self._guard:
            return dict(self._statuses)

    def pause(self) -> None:
        if self.worker is not None:
            self.worker.pause()

    def resume(self) -> None:
        if self.worker is not None:
            self.worker.resume()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()


@dataclass
class Settings:
    """What the server was started with."""

    demo_path: str | None = None
    art: ArtCache = field(default_factory=art_mod.ArtCache)
    catalog: object | None = None
    web_dir: Path = WEB_DIR
    use_cache: bool = True
    # The compiled decoder. None lets csharpdecode resolve it the way
    # oodlefind established: environment, then a vendor drop-in, then whatever
    # this working tree last built.
    parser_exe: str | None = None
    # Whether to fill the position cache in the background, the way the desktop
    # app does. On by default for the same reason it is there: a prepared
    # capture opens on the map instead of on a button. Off is for anyone who
    # started the server to look at one replay and would rather it not decode
    # twenty others.
    prewarm: bool = True

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


def decoder_doc(parser_exe: str | None) -> dict:
    """
    Whether a decode is possible at all, and where the decoder came from.

    A machine with no .NET SDK and no drop-in has no decoder, and that is an
    ordinary state -- the same kind of ordinary as a missing `assets/`.  It
    costs positions and nothing else, so it is reported as a sentence rather
    than raised: the page can then say why there is no DECODE button instead of
    offering one that cannot work.
    """
    try:
        found = csharpdecode.locate(parser_exe)
    except csharpdecode.DecodeError as exc:
        return {"found": False, "path": "", "described": str(exc), "hint": str(exc)}
    return {
        "found": True,
        "path": str(found),
        "described": f"decoder at {found}",
        "hint": "",
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application over one scan of one replay directory."""
    config = settings if settings is not None else Settings()
    library = Library(catalog=config.catalog, root=config.demo_path)
    library.rescan(cache=config.use_cache)

    preparation = _Preparation()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Fill the position cache while nobody is asking for anything."""
        if config.prewarm:
            preparation.start(library.result.cards, config.catalog, library.registry)
        yield
        # Asked, not waited for: the worker is a daemon and checks between
        # captures, so it drops out inside a second.
        preparation.stop()

    app = FastAPI(
        lifespan=lifespan,
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
    app.state.preparation = preparation

    _add_config_routes(app, config)
    _add_library_routes(app, library, config, preparation)
    _add_replay_routes(app, library, config, preparation)
    _add_map_routes(app, config)
    _mount_static(app, config)
    return app


def _add_config_routes(app: FastAPI, config: Settings) -> None:
    @app.get(f"{API}/config", response_model=schema.ConfigDoc)
    def read_config() -> dict:
        """Where the server looked, and what it found there."""
        return {
            "demo_root": demo_root_doc(vrfconfig.demo_root(config.demo_path)),
            "decoder": decoder_doc(config.parser_exe),
            "catalog_source": getattr(config.catalog, "described", "") or "",
            "web_built": config.web_built,
            "web_hint": "" if config.web_built else WEB_HINT,
        }


def _add_library_routes(
    app: FastAPI,
    library: Library,
    config: Settings,
    preparation: _Preparation,
) -> None:
    @app.get(f"{API}/library", response_model=schema.LibraryDoc)
    def read_library(query: Annotated[schema.LibraryQuery, Query()]) -> dict:
        """
        The match list, filtered, sorted and paged the way the scanner does it.

        All three stay here rather than in the browser because `sort_cards`
        already encodes a judgement -- an undated card sorts to the end, not to
        the epoch -- and a second implementation of that in another language is
        exactly the drift this project spends its docstrings avoiding.

        Only playable captures are listed.  A build with no payload transform
        has no positions to draw and there is no schematic to fall back to, so
        the interface offers nothing to open; the filter is applied here rather
        than being asked for, because there is no longer a request that would
        turn it off.
        """
        result = library.result
        cards = scan.filter_cards(result.cards, map_name=query.map_name)
        cards = [c for c in cards if c.playable]
        cards = scan.sort_cards(cards)
        root = result.root or vrfconfig.demo_root(config.demo_path)
        return {
            "root": demo_root_doc(root),
            "maps_present": scan.maps_present(result.cards),
            "page": query.page,
            "page_count": scan.page_count(cards),
            "per_page": scan.PER_PAGE,
            "cards": [
                wire.card(
                    c,
                    library.id_of(c.path),
                    config.art,
                    preparation.status(library.id_of(c.path)),
                )
                for c in scan.page(cards, number=query.page)
            ],
        }


def _decode_now(library: Library, config: Settings, replay_id: str, path) -> object:
    """
    Read the capture fresh, decode it, name it, and swap it in.

    A fresh `Replay`, never the cached one. `Replay` is the only mutable
    dataclass in the model and three modules annotate it in place, so a GET
    arriving mid-decode must see one replay or the other -- never one whose
    positions have landed but whose codenames have not.
    """
    replay = pipeline.open_replay(path, config.catalog)
    tracks.attach(replay, path, tracks.Options(parser_exe=config.parser_exe))
    # Again, because the codenames only exist once the stream has been read:
    # naming before the decode leaves every agent a `Hunter`.
    names.resolve(replay, config.catalog)
    library.replace(replay_id, replay)
    return replay


def _replay_doc(replay, replay_id: str, config: Settings) -> dict:
    """
    One replay on the wire, with the question `wire` cannot answer answered.

    Whether a decode *could* work is a membership test against the decoder's
    own branch table, and `wire` reaches no decoder by design -- so the answer
    is asked here, of `vrfhome.scan`, which is the one place the rule lives and
    which the match list already asks the same way.
    """
    return wire.replay_doc(
        replay,
        replay_id,
        config.art,
        available=scan.positions_available(replay.build),
        note=scan.positions_note(replay.build),
    )


def _add_replay_routes(
    app: FastAPI,
    library: Library,
    config: Settings,
    preparation: _Preparation,
) -> None:
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
            return _replay_doc(entry.replay, replay_id, config)

    @app.post(f"{API}/replays/{{replay_id}}/decode", response_model=schema.ReplayDoc)
    def decode_replay(replay_id: str) -> dict:
        """
        Decode this capture's positions now, and answer with the whole replay.

        Synchronous, and that is the design rather than a shortcut.  The decode
        is about four seconds since it moved to `csharp/VrfPositions`, which is
        inside an ordinary request; a job id, a progress stream and a client
        that polls for them would all be machinery in service of a wait that no
        longer happens.  FastAPI runs a sync handler in a threadpool, so those
        seconds occupy a worker and not the event loop.

        The whole replay comes back, not just the tracks.  A decode does not
        only produce positions: each pawn also states its own agent codename,
        and every ability cast names the agent that made it, so the roster and
        the cast list are different afterwards too.  The desktop viewer has to
        rebuild its body and its transport bar by hand for exactly this reason.

        **A build with no payload transform is a 200.**  `tracks.attach` is
        documented never to raise for want of positions -- it writes the
        refusal into `position_source` -- and turning that into a 500 here
        would make an honest answer look like a server fault.
        """
        path = library.registry.path(replay_id)
        if path is None:
            raise HTTPException(status_code=404, detail=NO_SUCH_REPLAY)

        # One at a time. The decoder is a CPU-bound subprocess, and two at once
        # halve both -- the same reason vrfhome.prewarm runs a single worker.
        # The queue is paused for the duration: the user asked for this one,
        # and it must not compete with twenty they did not. Unlike the desktop
        # app there is no window whose closing resumes it, so the pause lasts
        # exactly as long as the request and cannot be left on by a closed tab.
        preparation.pause()
        try:
            with _DECODE_LOCK:
                replay = _decode_now(library, config, replay_id, path)
        finally:
            preparation.resume()
        return _replay_doc(replay, replay_id, config)

    @app.get(f"{API}/replays/{{replay_id}}/positions")
    def read_positions(replay_id: str) -> Response:
        """
        The decoded tracks, in the format the sidecar and the cache already use.

        Six parallel arrays per actor rather than a record per sample: about a
        third of the bytes, and the shape a typed array wants at the far end.
        One builder feeds all three, so a test can assert this body is what
        `positionfile.write` would have put on disk.

        A replay with no positions gets the document with empty tracks **and
        its `position_source`**, not a 404. Whether a decode happened is a fact
        about the replay; 404 would say the replay does not exist.
        """
        entry = library.open(replay_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=NO_SUCH_REPLAY)
        with entry.lock:
            if entry.positions_json is None:
                document = positionfile.to_document(tracks.sidecar_of(entry.replay))
                entry.positions_json = json.dumps(document).encode("utf-8")
            body = entry.positions_json
        return Response(content=body, media_type="application/json")


def _add_map_routes(app: FastAPI, config: Settings) -> None:
    # One silhouette per radar image, built on demand and kept.  A server
    # shows many maps over its life where a viewer shows one, so the cache
    # earns more here than it does on the desktop -- and building one costs
    # opening a 1024x1024 PNG, which is not something to do per request.
    silhouettes = sight.SightCache()

    @app.get(f"{API}/maps/{{key}}", response_model=schema.MapDoc)
    def read_map(key: str) -> dict:
        """
        One map's picture and coordinates.

        This handler takes a map key and nothing else, and that is a structural
        promise rather than an oversight: the desktop map reference is handed no
        `Replay` by design, because it describes the map and not the match.
        Positions belong on the minimap and are not smuggled in here.
        """
        entry = config.art.map_art_by_name(key)
        if entry is None:
            raise HTTPException(status_code=404, detail=NO_SUCH_MAP)
        return wire.map_art(entry, config.art.root)

    @app.get(f"{API}/maps/{{key}}/sight", response_model=schema.SightDoc)
    def read_sight(key: str) -> dict:
        """
        The playable silhouette a sight cone is raycast against.

        Handed a map key and nothing else, exactly as `read_map` is: a
        silhouette is a fact about Bind, not about a match on it.

        A map with no radar image on disk is a 404 rather than an empty mask.
        An empty mask is a real answer -- a map that is entirely void -- and
        sending one for a missing PNG would have every cone silently collapse
        to nothing instead of the interface saying the layer is unavailable.
        """
        entry = config.art.map_art_by_name(key)
        if entry is None:
            raise HTTPException(status_code=404, detail=NO_SUCH_MAP)
        mask = silhouettes.get(entry.minimap)
        if mask is None:
            raise HTTPException(status_code=404, detail=NO_SIGHT_MASK)
        return wire.sight_mask(mask, key)

    @app.get(f"{API}/weapons", response_model=schema.WeaponsDoc)
    def read_weapons() -> dict:
        """
        The weapon art catalogue.

        Not a fact about any replay -- nothing decoded here says who is holding
        what -- which is why it sits beside the map routes rather than under
        one: it describes the game, the way a radar image and a callout list
        describe a map.  A checkout with no `assets/weapons/` answers with an
        empty list, and the client falls back to the weapon's name in text.
        """
        return wire.weapons(config.art)


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
        # An API address that matched no route is a 404, never the page.  This
        # catch-all sits below every route including the API ones, so without
        # this a mistyped or withdrawn endpoint answers 200 with a document of
        # HTML -- and the client parses it as JSON and reports something that
        # has nothing to do with what went wrong.
        if path == API.lstrip("/") or path.startswith(f"{API.lstrip('/')}/"):
            raise HTTPException(status_code=404, detail=f"no such endpoint: /{path}")
        candidate = (config.web_dir / path).resolve()
        root = config.web_dir.resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)
