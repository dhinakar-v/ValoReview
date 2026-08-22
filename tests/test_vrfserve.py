"""
Tests for the HTTP layer.

Everything here runs in-process through Starlette's `TestClient`, so there is no
port, no uvicorn and no network.  Nothing needs a real capture either: the
scanner never raises -- an unreadable file becomes a card carrying its error --
so a temp directory of nonsense exercises the same path a library does, and the
wire builders are checked against `Replay` objects built by hand.

Three properties are worth more than the rest and are pinned individually.

  * **An id is never a path.**  The registry is the only thing that turns a
    request into a file, so no handler can be talked into reading one.
  * **A missing `assets/` costs pictures and nothing else.**  Every sentence the
    interface states is the same with and without art; only the URLs go null.
  * **The map endpoint is handed no replay.**  That is a structural guarantee in
    the desktop app -- `mapref.show` cannot receive one -- and it has to survive
    becoming a URL, or the map reference quietly becomes a second minimap.
"""

from __future__ import annotations

import ast
import base64
import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from vrfhome import scan
from vrfserve import app as app_mod
from vrfserve import ids, schema, wire
from vrfserve.app import Settings, create_app
from vrfview import positionfile, sight, tracks
from vrfview.abilities import AbilityCast
from vrfview.art import ArtCache, Callout, MapArt, Transform
from vrfview.model import Loadout, Player, Position, Replay, Round, Track

REPO = Path(__file__).resolve().parents[1]

# A radar small enough to build in a test and shaped enough to threshold: an
# opaque disc on a transparent field, which is what every published minimap.png
# is a more complicated version of.
RADAR_PX = 64


def _write_radar(path: Path) -> None:
    """One synthetic minimap.png, so the sight tests need no fetched art."""
    from PIL import Image

    image = Image.new("RGBA", (RADAR_PX, RADAR_PX), (0, 0, 0, 0))
    pixels = image.load()
    middle = RADAR_PX / 2
    for row in range(RADAR_PX):
        for col in range(RADAR_PX):
            if (col - middle) ** 2 + (row - middle) ** 2 < (middle * 0.7) ** 2:
                pixels[col, row] = (90, 90, 90, 255)
    image.save(path)


def _supplier():
    """A fresh Replay per call, the way `pipeline.open_replay` gives one."""
    return lambda *_args, **_kwargs: _replay()


def _replay(build: str = "++Ares-Core+release-12.10") -> Replay:
    replay = Replay(
        source="capture.vrf",
        match_id="m-1",
        map_path="/Game/Maps/Triad/Triad",
        map_name="Haven",
        map_name_source="built-in table",
        length_ms=60_000,
        build=build,
        recorded_utc="2026-08-21T19:04:00Z",
    )
    replay.rounds = [Round(number=1, index=0, start_ms=0, end_ms=60_000)]
    replay.players = [
        Player(actor_id=1, team="A", label="A1", codename="Hunter", agent="Sova"),
        Player(actor_id=2, team="B", label="B1"),
    ]
    replay.loadouts = [Loadout(index=0, subject="s-1", character_id="c-1")]
    replay.notes = ["teams split by two-colouring the kill graph"]
    return replay


class Ids(unittest.TestCase):
    def test_the_same_path_always_has_the_same_id(self):
        assert ids.id_for("a/b.vrf") == ids.id_for("a/b.vrf")

    def test_different_paths_have_different_ids(self):
        assert ids.id_for("a/b.vrf") != ids.id_for("a/c.vrf")

    def test_an_id_is_opaque_and_short(self):
        found = ids.id_for("a/b.vrf")
        assert len(found) == ids.ID_LENGTH
        assert found.isalnum()

    def test_an_unregistered_id_resolves_to_nothing(self):
        registry = ids.Registry()
        registry.add("a/b.vrf")
        assert registry.path("0" * ids.ID_LENGTH) is None

    def test_a_path_is_never_derived_from_the_string(self):
        """
        The property the whole module exists for.

        Anything that looks like traversal is simply not in the registry, so it
        resolves to None the same way any other unknown string does.  There is
        no code path that joins a request onto a directory.
        """
        registry = ids.Registry()
        registry.add("a/b.vrf")
        for hostile in ("../../etc/passwd", "..\\..\\windows", "/", "a/b.vrf"):
            assert registry.path(hostile) is None

    def test_a_rescan_forgets_captures_that_have_gone(self):
        registry = ids.Registry()
        gone = registry.add("a/b.vrf")
        registry.replace(["a/c.vrf"])
        assert registry.path(gone) is None
        assert len(registry) == 1


class AssetUrls(unittest.TestCase):
    def test_a_file_under_the_root_becomes_a_url(self):
        root = Path("assets")
        found = wire.asset_url(root / "maps" / "Bind" / "minimap.png", root)
        assert found == "/assets/maps/Bind/minimap.png"

    def test_a_name_with_a_slash_in_it_survives(self):
        """
        KAY/O.  The manifest sanitises it to KAY_O and this only re-roots.

        Nothing here ever builds a filename -- the path came out of the
        manifest's own `files` dict -- which is why the agent whose display name
        contains a path separator is not a special case.
        """
        root = Path("assets")
        found = wire.asset_url(root / "agents" / "KAY_O" / "icon.png", root)
        assert found == "/assets/agents/KAY_O/icon.png"

    def test_nothing_resolves_to_nothing(self):
        assert wire.asset_url(None, Path("assets")) is None

    def test_a_file_outside_the_root_is_refused(self):
        """A mistyped --assets should cost pictures, not serve the disk."""
        assert wire.asset_url(Path("C:/windows/system32/x.png"), Path("assets")) is None


class WireBuilders(unittest.TestCase):
    """Every builder's dict must validate against the model that describes it."""

    def test_a_replay_document_matches_its_model(self):
        doc = wire.replay_doc(_replay(), "abc123", None)
        schema.ReplayDoc.model_validate(doc)

    def test_an_empty_replay_still_matches(self):
        schema.ReplayDoc.model_validate(wire.replay_doc(Replay(), "abc123", None))

    def test_a_map_document_matches_its_model(self):
        art = MapArt(
            name="Abyss",
            codename="Infinity",
            map_url="/Game/Maps/Infinity/Infinity",
            transform=Transform(8.1e-05, -8.1e-05, 0.5, 0.5),
            callouts=(Callout("A Tree", 100.0, 200.0),),
        )
        doc = wire.map_art(art, Path("assets"))
        schema.MapDoc.model_validate(doc)
        assert doc["callouts"] == [
            {"name": "A Tree", "world_x": 100.0, "world_y": 200.0},
        ]

    def test_the_vertical_scale_is_the_average_of_the_two_multipliers(self):
        """
        The one derived number in the transform, and where it comes from.

        It is the same average `sight.uv_radius` takes to turn Unreal units into
        a fraction of the radar.  Publishing it means a 3D scene places a
        player's z at the map's own horizontal scale, rather than at a factor
        somebody picked because it looked right.
        """
        art = MapArt(transform=Transform(8.1e-05, -8.1e-05, 0.5, 0.5))
        assert wire.transform_of(art)["vertical_scale"] == 8.1e-05

    def test_the_axis_swap_is_carried_not_corrected(self):
        art = MapArt(transform=Transform(2.0, 3.0, 0.0, 0.0))
        doc = wire.transform_of(art)
        assert doc["x_multiplier"] == 2.0
        assert doc["y_multiplier"] == 3.0

    def test_a_player_carries_the_read_and_the_looked_up_name_apart(self):
        doc = wire.player(_replay().players[0], None)
        assert doc["codename"] == "Hunter"
        assert doc["agent"] == "Sova"

    def test_an_unnamed_player_has_neither_rather_than_a_guess(self):
        doc = wire.player(_replay().players[1], None)
        assert doc["codename"] == ""
        assert doc["agent"] == ""
        assert doc["identity"] == doc["display"]

    def test_a_loadout_is_never_joined_to_an_actor(self):
        """Nothing links a roster slot to an actor net ID, and this must not."""
        doc = wire.loadout(_replay().loadouts[0], None)
        assert "actor_id" not in doc

    def test_a_replay_carries_whether_a_decode_could_ever_work(self):
        """
        `wire` is handed the answer rather than deriving it, and here is why.

        Deriving it means a membership test against `payload_transform
        .SUPPORTED_BRANCHES`, which lives in `vrfnet` -- and `wire` is the one
        module in the server that reaches neither a framework nor a decoder.
        So `vrfserve.app` asks `vrfhome.scan`, which is the same authority the
        match list uses, and passes the answer through.
        """
        supported = wire.replay_doc(
            _replay(),
            "abc123",
            None,
            available=True,
            note=scan.POSITIONS_AVAILABLE,
        )
        assert supported["positions_available"]
        assert supported["positions_note"] == scan.POSITIONS_AVAILABLE

        refused = wire.replay_doc(_replay(), "abc123", None)
        assert not refused["positions_available"]

    def test_a_derived_note_and_a_looked_up_one_stay_in_separate_lists(self):
        replay = _replay()
        replay.catalog_notes = ["the pawn's agent and the loadout's agree"]
        doc = wire.replay_doc(replay, "abc123", None)
        assert doc["notes"] != doc["catalog_notes"]
        assert "two-colouring" in doc["notes"][0]


class Endpoints(unittest.TestCase):
    """The API over an empty library, which is a real state and not a failure."""

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.client = self._client()

    def tearDown(self):
        self._dir.cleanup()

    def _client(self) -> TestClient:
        """
        A server over the temp directory as it stands right now.

        The scan happens once, at startup, so a test that writes a capture has
        to build its client afterwards -- which is the same thing the running
        server does, and the reason `refresh` exists.
        """
        return TestClient(
            create_app(
                Settings(
                    demo_path=str(self.tmp),
                    web_dir=self.tmp / "nowhere",
                    # A temp library must not write into the repo's .cache/.
                    use_cache=False,
                ),
            ),
        )

    def _with_broken_capture(self) -> TestClient:
        (self.tmp / "broken.vrf").write_bytes(b"not a replay")
        return self._client()

    def test_config_reports_where_it_looked(self):
        doc = self.client.get("/api/config").json()
        schema.ConfigDoc.model_validate(doc)
        assert str(self.tmp) in doc["demo_root"]["path"]
        assert doc["demo_root"]["exists"]

    def test_an_empty_directory_is_an_empty_state_not_an_error(self):
        response = self.client.get("/api/library")
        assert response.status_code == 200
        doc = response.json()
        schema.LibraryDoc.model_validate(doc)
        assert doc["cards"] == []
        # And it says where it looked, rather than just showing nothing.
        assert str(self.tmp) in doc["root"]["described"]

    def test_only_playable_captures_are_listed(self):
        """
        The filter is the handler's, not the request's.

        A build with no payload transform has no positions to draw and there is
        no schematic to fall back to, so there is nothing behind such a card to
        open.  There is no longer a query that turns this off, which is the
        point of asserting it: a stray `playable_only=false` must not resurrect
        the old behaviour.
        """
        client = self._with_broken_capture()
        assert client.get("/api/library").json()["cards"] == []
        assert client.get("/api/library?playable_only=false").json()["cards"] == []

    def test_an_unknown_replay_id_is_a_404(self):
        assert self.client.get("/api/replays/" + "0" * 16).status_code == 404

    def test_a_traversal_shaped_id_is_a_404_like_any_other_unknown_string(self):
        for hostile in ("..", "..%2F..%2Fetc", "%2E%2E%5C%2E%2E"):
            assert self.client.get(f"/api/replays/{hostile}").status_code == 404

    def test_a_replay_says_whether_a_decode_could_ever_work(self):
        """
        A different question from whether one has happened, and both are sent.

        The DECODE button is gated on this, so a capture whose build has no
        payload transform gets the sentence rather than a control that would
        only ever refuse -- and the answer comes from the same
        `vrfhome.scan.positions_available` the match list asks, so a card and a
        replay cannot disagree about a capture.
        """
        doc = wire.replay_doc(
            _replay(build="++Ares-Core+release-11.11"),
            "abc123",
            None,
            available=scan.positions_available("++Ares-Core+release-11.11"),
            note=scan.positions_note("++Ares-Core+release-11.11"),
        )
        assert not doc["positions_available"]
        assert "no payload transform" in doc["positions_note"]

    def test_an_unknown_map_is_a_404(self):
        assert self.client.get("/api/maps/Nowhere").status_code == 404

    def test_an_unbuilt_page_is_a_sentence_naming_the_command(self):
        """Never a stand-in page: say what is missing."""
        response = self.client.get("/")
        assert response.status_code == 200
        assert "npm run build" in response.text

    def test_the_schema_is_published(self):
        assert self.client.get("/openapi.json").status_code == 200


class MapsAreAddressedByName(unittest.TestCase):
    """
    The key in `/api/maps/{key}` is the manifest's display name.

    `ArtCache.maps` is keyed by `map_url` because that is the exact join a
    replay states, and a `map_url` cannot be a URL segment: it is
    `/Game/Maps/Infinity/Infinity`, and the percent encoding that would hide
    those slashes is decoded again before the router sees it.  So the wire
    sends the display name as `map_key` and the route resolves that.

    The pair below is the whole test: whatever `map_key` a replay document
    carries must be a key `/api/maps/{key}` answers to.  Sent by one function
    and resolved by another, that agreement is exactly the kind that rots
    quietly.
    """

    def setUp(self):
        self.art = ArtCache(
            root=Path("assets"),
            source="test",
            maps={
                "/Game/Maps/Triad/Triad": MapArt(
                    name="Haven",
                    codename="Triad",
                    map_url="/Game/Maps/Triad/Triad",
                    transform=Transform(8.1e-05, -8.1e-05, 0.5, 0.5),
                    callouts=(Callout("A Site", 100.0, 200.0),),
                ),
            },
        )
        self.client = TestClient(
            create_app(Settings(demo_path=".", use_cache=False, art=self.art)),
        )

    def test_the_map_key_a_replay_sends_is_a_key_the_map_route_answers_to(self):
        key = wire.replay_doc(_replay(), "abc123", self.art)["map_key"]
        assert key == "Haven"
        response = self.client.get(f"/api/maps/{key}")
        assert response.status_code == 200
        assert response.json()["map_url"] == "/Game/Maps/Triad/Triad"

    def test_the_internal_map_path_is_not_a_key(self):
        """
        It reads like one and cannot be one: it has slashes in it.

        Trying it is a 404 rather than a match on the dictionary this cache is
        actually keyed by, which is the mistake this test exists to catch.
        """
        for shaped in (
            "/api/maps//Game/Maps/Triad/Triad",
            "/api/maps/%2FGame%2FMaps%2FTriad%2FTriad",
        ):
            assert self.client.get(shaped).status_code == 404


class SightMaskTravelsWithItsCaption(unittest.TestCase):
    """
    A cone is drawn from a mask, and the mask arrives with the sentence.

    `sight.CAPTION` says what a cone raycast against a radar's alpha channel
    is and is not -- a silhouette, not collision, and two-dimensional.  It
    travels in the same document as the cells so that no client can render a
    wedge without having been handed the words for it.
    """

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.radar = self.tmp / "minimap.png"
        _write_radar(self.radar)
        self.art = ArtCache(
            root=self.tmp,
            source="test",
            maps={
                "/Game/Maps/Triad/Triad": MapArt(
                    name="Haven",
                    map_url="/Game/Maps/Triad/Triad",
                    minimap=self.radar,
                    transform=Transform(8.1e-05, -8.1e-05, 0.5, 0.5),
                ),
                "/Game/Maps/Duality/Duality": MapArt(
                    name="Bind",
                    map_url="/Game/Maps/Duality/Duality",
                    transform=Transform(8.1e-05, -8.1e-05, 0.5, 0.5),
                ),
            },
        )
        self.client = TestClient(
            create_app(Settings(demo_path=".", use_cache=False, art=self.art)),
        )

    def tearDown(self):
        self._dir.cleanup()

    def test_the_mask_is_the_one_python_thresholded(self):
        doc = self.client.get("/api/maps/Haven/sight").json()
        schema.SightDoc.model_validate(doc)
        built = sight.SightMap.from_path(self.radar)
        assert doc["size"] == built.size
        assert base64.b64decode(doc["cells"]) == built.cells
        assert doc["open_fraction"] == pytest.approx(built.open_fraction)

    def test_the_caption_is_sight_pys_own_words(self):
        doc = self.client.get("/api/maps/Haven/sight").json()
        assert doc["caption"] == sight.CAPTION
        assert "not collision" in doc["caption"]

    def test_the_constants_come_from_the_module_that_decides_them(self):
        doc = self.client.get("/api/maps/Haven/sight").json()
        assert doc["max_range_uu"] == sight.MAX_RANGE_UU
        assert doc["fov_degrees"] == sight.FOV_DEGREES
        assert doc["ray_step_degrees"] == sight.RAY_STEP_DEGREES
        assert doc["seed_cells"] == sight.SEED_CELLS
        assert doc["probe_uu"] == sight.PROBE_UU

    def test_a_map_with_no_radar_is_unavailable_rather_than_empty(self):
        """
        An empty mask is a real answer -- a map that is entirely void.

        Sending one for a PNG that is simply not on disk would make every cone
        silently collapse instead of the interface saying the layer is not
        available, so this is a 404 with a sentence.
        """
        response = self.client.get("/api/maps/Bind/sight")
        assert response.status_code == 404
        assert "no radar image" in response.json()["detail"]

    def test_an_unknown_map_is_a_404_like_any_other(self):
        assert self.client.get("/api/maps/Nowhere/sight").status_code == 404


class MapEndpointTakesNoReplay(unittest.TestCase):
    """
    The map reference describes the map, not the match, and must keep doing so.

    In the desktop app that is structural: `mapref.show` is handed no `Replay`
    and so cannot plot one.  An endpoint could quietly acquire a replay id and
    become a second minimap, so the shape of the handler is asserted rather
    than trusted.
    """

    def test_the_handler_accepts_a_map_key_and_nothing_else(self):
        app = create_app(Settings(demo_path=".", use_cache=False))
        routes = [r for r in app.routes if getattr(r, "path", "") == "/api/maps/{key}"]
        assert len(routes) == 1
        signature = routes[0].dependant.path_params + routes[0].dependant.query_params
        assert [p.name for p in signature] == ["key"]

    def test_the_map_document_shares_no_field_with_the_replay_document(self):
        overlap = set(schema.MapDoc.model_fields) & set(schema.ReplayDoc.model_fields)
        assert overlap == {"name"} or not overlap - {"name"}


class TheBuiltPageDoesNotAnswerForTheApi(unittest.TestCase):
    """
    The page's catch-all sits below every route, including the API's.

    It has to: the browser routes on the client, so `/replay/<id>` is an
    address no file answers to and the page has to be served for it.  But the
    same rule would have a withdrawn or mistyped endpoint reply 200 with a
    document of HTML -- and then the client parses it as JSON and reports
    something with no relation to what actually went wrong.
    """

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        built = self.tmp / "dist"
        (built / app_mod.SPA_ASSETS).mkdir(parents=True)
        (built / "index.html").write_text("<!doctype html><title>page</title>")
        self.client = TestClient(
            create_app(
                Settings(demo_path=str(self.tmp), web_dir=built, use_cache=False),
            ),
        )

    def tearDown(self):
        self._dir.cleanup()

    def test_a_client_route_is_served_the_page(self):
        response = self.client.get("/replay/abc123")
        assert response.status_code == 200
        assert "<title>page</title>" in response.text

    def test_an_api_address_that_matches_no_route_is_a_404_not_the_page(self):
        response = self.client.get("/api/nothing-here")
        assert response.status_code == 404
        assert "no such endpoint" in response.json()["detail"]

    def test_a_map_key_shaped_like_an_internal_path_is_a_404_not_the_page(self):
        """
        The slashes in `/Game/Maps/...` split it across the router's segments.

        Percent-encoding them does not help -- the path is decoded before the
        route is matched -- so this falls through to the catch-all, and would
        have answered 200 with the page.
        """
        for shaped in (
            "/api/maps//Game/Maps/Triad/Triad",
            "/api/maps/%2FGame%2FMaps%2FTriad%2FTriad",
        ):
            assert self.client.get(shaped).status_code == 404


class ArtIsAPictureOnly(unittest.TestCase):
    """Turning art off changes URLs and nothing the interface states."""

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def _doc(self, art: ArtCache | None):
        settings = Settings(
            demo_path=str(self.tmp),
            web_dir=self.tmp / "nowhere",
            use_cache=False,
        )
        if art is not None:
            settings.art = art
        return wire.replay_doc(_replay(), "abc123", settings.art if art else None)

    def test_every_claim_is_the_same_with_and_without_art(self):
        with_art = self._doc(ArtCache())
        without = self._doc(None)
        for key in ("notes", "catalog_notes", "position_source", "map_name", "rounds"):
            assert with_art[key] == without[key]

    def test_a_missing_assets_directory_does_not_stop_the_server_starting(self):
        settings = Settings(demo_path=str(self.tmp), use_cache=False)
        settings.art = ArtCache(root=self.tmp / "no-such-assets")
        client = TestClient(create_app(settings))
        assert client.get("/api/config").status_code == 200
        assert client.get("/assets/maps/Bind/minimap.png").status_code == 404


class Headless(unittest.TestCase):
    """
    `wire` must not reach a framework.

    The toolkit half of this rule moved to `tests/test_layering.py`, which now
    asserts it over the whole of `libraries/` rather than over this package --
    there is no widget set left anywhere to make an exception for.

    What is left is the rule that keeps serialisation testable without a
    server, and it is the reason `wire` builds plain dicts instead of models:
    a builder that needed a request or a PNG would be inventing a claim at the
    edge rather than carrying one.
    """

    BANNED: ClassVar[dict[str, set[str]]] = {
        "wire": {
            "fastapi",
            "starlette",
            "pydantic",
            "PIL",
            "vrfnet",
        },
    }

    @staticmethod
    def _imports(module: str) -> set[str]:
        source = REPO / "libraries" / "vrfserve" / f"{module}.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        return names

    def test_nothing_imports_what_it_must_not(self):
        for module, banned in self.BANNED.items():
            for name in self._imports(module):
                root = name.split(".")[0]
                assert root not in banned, f"vrfserve.{module} imports {name}"


class DecoderReported(unittest.TestCase):
    """
    Whether a decode is possible has to be answerable without attempting one.

    A machine with no .NET SDK and no drop-in has no decoder. That is ordinary,
    it costs positions and nothing else, and the page has to be able to say so
    rather than offer a button that cannot work.
    """

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def _config(self, parser_exe: str | None):
        settings = Settings(
            demo_path=str(self.tmp),
            web_dir=self.tmp / "nowhere",
            use_cache=False,
            parser_exe=parser_exe,
        )
        return TestClient(create_app(settings)).get("/api/config").json()

    def test_a_parser_exe_pointing_at_nothing_is_reported_not_raised(self):
        doc = self._config(str(self.tmp / "no-such-decoder.dll"))
        schema.ConfigDoc.model_validate(doc)
        assert not doc["decoder"]["found"]
        assert doc["decoder"]["hint"]
        assert "no-such-decoder.dll" in doc["decoder"]["hint"]

    def test_the_server_still_starts_and_serves_without_a_decoder(self):
        settings = Settings(
            demo_path=str(self.tmp),
            web_dir=self.tmp / "nowhere",
            use_cache=False,
            parser_exe=str(self.tmp / "absent.dll"),
        )
        client = TestClient(create_app(settings))
        assert client.get("/api/library").status_code == 200

    def test_a_real_decoder_is_named(self):
        fake = self.tmp / "vrf-positions.dll"
        fake.write_bytes(b"not really a decoder, but it is a file")
        doc = self._config(str(fake))
        assert doc["decoder"]["found"]
        assert str(fake) in doc["decoder"]["described"]
        assert doc["decoder"]["hint"] == ""


class Decoding(unittest.TestCase):
    """
    The decode endpoint, with the decoder itself patched out.

    Nothing here runs the C# program: what is being tested is the endpoint's
    contract, and the decoder has its own tests. The most important case is the
    refusal -- `tracks.attach` is documented never to raise for want of
    positions, and an endpoint that turned that into a 500 would make an honest
    answer look like a server fault.
    """

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        (self.tmp / "broken.vrf").write_bytes(b"not a replay")
        self.client = TestClient(
            create_app(
                Settings(
                    demo_path=str(self.tmp),
                    web_dir=self.tmp / "nowhere",
                    use_cache=False,
                ),
            ),
        )

    def tearDown(self):
        self._dir.cleanup()

    def test_an_unknown_id_is_a_404(self):
        response = self.client.post("/api/replays/" + "0" * 16 + "/decode")
        assert response.status_code == 404

    def test_a_traversal_shaped_id_is_a_404_too(self):
        assert self.client.post("/api/replays/..%2F..%2Fx/decode").status_code == 404

    def _decoding(self, attach):
        """
        The endpoint with the two things it stands on replaced.

        `open_replay` and `attach` are patched at the boundary of what is being
        tested: this is about what the handler does with their answers, and
        neither reading a container nor running a subprocess is its job.
        """
        replay_id = ids.id_for(self.tmp / "broken.vrf")
        with (
            mock.patch.object(app_mod.pipeline, "open_replay", side_effect=_supplier()),
            mock.patch.object(app_mod.tracks, "attach", side_effect=attach),
            mock.patch.object(app_mod.names, "resolve", side_effect=lambda r: r),
        ):
            return self.client.post(f"/api/replays/{replay_id}/decode")

    def test_a_build_with_no_transform_is_a_200_carrying_the_refusal(self):
        """
        The rule the whole decoding layer stands on.

        `tracks.attach` never raises for want of positions -- it writes the
        reason into `position_source` -- and an endpoint that turned that into
        a 500 would make an honest answer look like a server fault. An 11.11
        capture is not an error; it is a capture nobody can decode.
        """
        refusal = "no payload transform for ++Ares-Core+release-11.11"

        def refuse(replay, _path, _options=None):
            replay.position_source = refusal
            return replay

        response = self._decoding(refuse)
        assert response.status_code == 200
        doc = response.json()
        schema.ReplayDoc.model_validate(doc)
        assert doc["position_source"] == refusal
        assert doc["has_positions"] is False

    def test_a_successful_decode_returns_the_whole_replay_not_just_tracks(self):
        """
        A decode changes the roster too, so the response has to carry it.

        Each pawn states its own agent codename and every cast names the agent
        that made it, so a client that refreshed only the map would still show
        ten players called by their actor id.
        """

        def decode(replay, _path, _options=None):
            replay.positions = {
                1: Track(
                    actor_id=1,
                    samples=(Position(t_ms=0, actor_id=1, x=1.0, y=2.0, z=3.0),),
                ),
            }
            replay.position_source = "decoded 1 position"
            replay.players = [
                Player(actor_id=1, team="A", label="A1", codename="Hunter"),
            ]
            return replay

        response = self._decoding(decode)
        assert response.status_code == 200
        doc = response.json()
        assert doc["has_positions"] is True
        assert doc["players"][0]["codename"] == "Hunter"

    def test_the_cached_entry_is_replaced_and_its_revision_moves(self):
        library = self.client.app.state.library
        replay_id = ids.id_for(self.tmp / "broken.vrf")

        def decode(replay, _path, _options=None):
            replay.position_source = "decoded"
            return replay

        with (
            mock.patch.object(app_mod.pipeline, "open_replay", side_effect=_supplier()),
            mock.patch.object(app_mod.tracks, "attach", side_effect=decode),
            mock.patch.object(app_mod.names, "resolve", side_effect=lambda r: r),
        ):
            library.open(replay_id)
            before = library.entry(replay_id).revision
            self.client.post(f"/api/replays/{replay_id}/decode")
        assert library.entry(replay_id).revision == before + 1

    def test_decodes_do_not_overlap(self):
        """One at a time: the decoder is a CPU-bound subprocess."""
        inside = []
        peak = 0

        def decode(replay, _path, _options=None):
            nonlocal peak
            inside.append(1)
            peak = max(peak, len(inside))
            time.sleep(0.05)
            inside.pop()
            replay.position_source = "decoded"
            return replay

        replay_id = ids.id_for(self.tmp / "broken.vrf")
        with (
            mock.patch.object(app_mod.pipeline, "open_replay", side_effect=_supplier()),
            mock.patch.object(app_mod.tracks, "attach", side_effect=decode),
            mock.patch.object(app_mod.names, "resolve", side_effect=lambda r: r),
        ):
            threads = [
                threading.Thread(
                    target=lambda: self.client.post(f"/api/replays/{replay_id}/decode"),
                )
                for _ in range(4)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        assert peak == 1


class Positions(unittest.TestCase):
    """
    The positions document, and the one builder that also writes the sidecar.
    """

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def test_it_is_the_same_document_the_sidecar_would_hold(self):
        """
        One builder feeds the sidecar, the machine cache and this response.

        Two builders would be two chances to disagree about what a track looks
        like, and the disagreement would be invisible until something drew it.
        """
        replay = _replay()
        replay.positions = {
            1: Track(
                actor_id=1,
                samples=(
                    Position(t_ms=0, actor_id=1, x=1.5, y=-2.5, z=64.0, yaw=90.0),
                    Position(t_ms=100, actor_id=1, x=2.5, y=-3.5, z=64.0, yaw=91.0),
                ),
            ),
        }
        replay.position_source = "a line about the decode"
        sidecar = tracks.sidecar_of(replay)
        document = positionfile.to_document(sidecar)

        written = self.tmp / "m.positions.json"
        positionfile.write(written, sidecar)
        assert document == json.loads(written.read_text(encoding="utf-8"))
        assert positionfile.read(written).positions == replay.positions

    def test_a_replay_with_no_decode_says_so_rather_than_404ing(self):
        """
        Whether a decode happened is a fact about the replay, not a 404.

        A 404 would say the replay does not exist, which is a different and
        wrong claim.
        """
        replay = _replay()
        replay.position_source = "positions not decoded (not requested)"
        document = positionfile.to_document(tracks.sidecar_of(replay))
        assert document["tracks"] == {}
        assert document["position_source"] == replay.position_source

    def test_ability_spawns_are_empty_and_that_is_deliberate(self):
        """
        The raw spawns do not survive a load, and none are invented here.

        `_apply_sidecar` regroups spawns into casts on every load, precisely so
        the grouping rules can improve without invalidating a cached decode --
        which means a `Replay` no longer carries the archetype paths they were
        read from. Filling this in from the casts would be inventing facts.
        """
        replay = _replay()
        assert tracks.sidecar_of(replay).ability_spawns == {}

    def test_the_document_and_its_model_declare_the_same_fields(self):
        """
        `PositionsDoc` drifted from the document because nothing compared them.

        The route hands back pre-serialised bytes, so no response has ever been
        validated against this model, and the model was referenced by no route
        and no test -- so when `spike_plants` was added to `to_document` at
        version 4, the model simply did not gain it and nothing said so.  The
        endpoint also had no `response_model`, which meant the OpenAPI document
        did not describe this route at all.

        Key-set equality rather than `model_validate`, because validation only
        catches the half where the model demands more than the document sends.
        The half that actually happened is the other one.
        """
        replay = _replay()
        replay.positions = {
            1: Track(
                actor_id=1,
                samples=(Position(t_ms=0, actor_id=1, x=1.5, y=-2.5, z=64.0),),
            ),
        }
        document = positionfile.to_document(tracks.sidecar_of(replay))
        assert set(document) == set(schema.PositionsDoc.model_fields)
        schema.PositionsDoc.model_validate(document)


class BackgroundPreparation(unittest.TestCase):
    """
    The queue that fills the cache, and the one thing it must not do.

    It runs only when asked for, and it is paused for exactly the length of a
    foreground decode -- not for as long as a viewer is open. The desktop app
    could resume on a window closing; a browser tab that goes away tells the
    server nothing, so tying the pause to a request is what keeps a closed tab
    from leaving the queue stopped forever.
    """

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        (self.tmp / "broken.vrf").write_bytes(b"not a replay")

    def tearDown(self):
        self._dir.cleanup()

    def _client(self, *, prewarm: bool):
        return TestClient(
            create_app(
                Settings(
                    demo_path=str(self.tmp),
                    web_dir=self.tmp / "nowhere",
                    use_cache=False,
                    prewarm=prewarm,
                ),
            ),
        )

    def test_it_does_not_start_when_it_was_not_asked_for(self):
        with self._client(prewarm=False) as client:
            assert client.app.state.preparation.all() == {}

    def test_an_unreadable_capture_is_never_queued(self):
        """`Prewarmer` queues only playable cards; nothing here changes that."""
        with self._client(prewarm=True) as client:
            statuses = client.app.state.preparation.all()
        assert statuses == {}

    def test_a_decode_pauses_and_resumes_the_queue_around_itself(self):
        replay_id = ids.id_for(self.tmp / "broken.vrf")

        def decode(replay, _path, _options=None):
            replay.position_source = "decoded"
            return replay

        with self._client(prewarm=True) as client:
            preparation = client.app.state.preparation
            with (
                mock.patch.object(preparation, "pause") as paused,
                mock.patch.object(preparation, "resume") as resumed,
                mock.patch.object(
                    app_mod.pipeline,
                    "open_replay",
                    side_effect=_supplier(),
                ),
                mock.patch.object(app_mod.tracks, "attach", side_effect=decode),
                mock.patch.object(
                    app_mod.names,
                    "resolve",
                    side_effect=lambda r: r,
                ),
            ):
                client.post(f"/api/replays/{replay_id}/decode")
        assert paused.call_count == 1
        assert resumed.call_count == 1

    def test_it_resumes_even_when_the_decode_fails(self):
        """A raise inside the decode must not leave the queue stopped."""
        replay_id = ids.id_for(self.tmp / "broken.vrf")
        with self._client(prewarm=True) as client:
            preparation = client.app.state.preparation
            with (
                mock.patch.object(preparation, "resume") as resumed,
                mock.patch.object(
                    app_mod.pipeline,
                    "open_replay",
                    side_effect=OSError("no such capture"),
                ),
                pytest.raises(OSError, match="no such capture"),
            ):
                client.post(f"/api/replays/{replay_id}/decode")
        assert resumed.call_count == 1


class AbilityCastsCarryTheirCaster(unittest.TestCase):
    """
    `actor_id` on a cast is the *ability actor*, and no player has it.

    That is why `player_actor_id` exists: the browser's round timeline looked
    the side up by `actor_id`, found nobody, and drew every ability row with no
    side at all -- silently, because a missing side is a missing tint rather
    than an error.  The join refuses an ambiguous codename instead of picking a
    player, which is the property worth pinning.
    """

    def _doc(self, players, casts):
        replay = Replay()
        replay.players = players
        replay.ability_casts = casts
        return wire.replay_doc(replay, "id", None)

    def test_a_unique_codename_names_its_caster(self):
        players = [
            Player(actor_id=11, team="A", codename="Hunter"),
            Player(actor_id=22, team="B", codename="Gumshoe"),
        ]
        casts = [AbilityCast(t_ms=1, codename="Hunter", slot="Q", name="Reveal_Bolt")]
        doc = self._doc(players, casts)
        assert doc["ability_casts"][0]["player_actor_id"] == 11
        # And it is not the ability actor's own id, which is the whole point.
        assert doc["ability_casts"][0]["actor_id"] != 11

    def test_a_shared_codename_is_refused_rather_than_guessed(self):
        players = [
            Player(actor_id=11, team="A", codename="Hunter"),
            Player(actor_id=22, team="B", codename="Hunter"),
        ]
        casts = [AbilityCast(t_ms=1, codename="Hunter", slot="Q", name="Reveal_Bolt")]
        doc = self._doc(players, casts)
        assert doc["ability_casts"][0]["player_actor_id"] is None
