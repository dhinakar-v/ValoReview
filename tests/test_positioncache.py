"""
Decode once: the sidecar, the machine cache, and the order `attach` tries them.

The bug these exist to prevent is the one that shipped: `positionfile` could
write a sidecar and `tracks.attach` would only ever *read* one for a non-`.vrf`
path, so opening `Foo.vrf` re-decoded it every time even with the answer
sitting beside it.  Every test below is about which source answered and how
the replay reported it, because "positions appeared" is not the interesting
part -- where they came from is.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from vrfview import positioncache, positionfile, tracks
from vrfview.model import Position, Replay, Track

MATCH = "039f3991-5472-4119-bed2-838da0935f60"

# Two actors from one Killjoy turret placement: the sub-actor that fires and
# the pawn that stands there.  The sub-actor is earlier and worse named, which
# is exactly the case the grouping rules exist for.
TURRET_CAST = (
    "/Game/Characters/Killjoy/S0/Ability_E/Ability_Killjoy_E_TurretAttack"
    ".Default__Ability_Killjoy_E_TurretAttack_C"
)
TURRET_PAWN = (
    "/Game/Characters/Killjoy/S0/Ability_E/Pawn_Killjoy_E_Turret"
    ".Default__Pawn_Killjoy_E_Turret_C"
)
SPAWNS = {41: (TURRET_CAST, 1200), 42: (TURRET_PAWN, 1400)}


def track(actor_id=1, count=3):
    return Track(
        actor_id=actor_id,
        samples=tuple(
            Position(t_ms=i * 100, actor_id=actor_id, x=float(i), y=2.0, z=3.0)
            for i in range(count)
        ),
    )


def sidecar(**kwargs):
    base = {
        "positions": {1: track()},
        "codenames": {1: "Hunter"},
        "description": "a test decode",
        "match_id": MATCH,
        "build": "++Ares-Core+release-12.10",
    }
    base.update(kwargs)
    return positionfile.Sidecar(**base)


class TestCachePaths(unittest.TestCase):
    def test_the_cache_lives_beside_the_oodle_one(self):
        """
        Not `out/`, which `scan` uses and which is relative to the CWD.

        A four-second rescan can afford to lose its cache when the app is run
        from another directory; a four-minute decode per capture cannot.
        """
        root = positioncache.cache_root()
        assert root.name == positioncache.CACHE_DIRNAME
        assert root.parent.name == positioncache.APP_DIRNAME

    def test_an_entry_is_named_from_the_capture(self):
        found = positioncache.cache_path(f"Demos/{MATCH}.vrf", root=Path("cache"))
        assert found == Path("cache") / f"{MATCH}{positionfile.SUFFIX}"

    def test_a_missing_entry_is_none_rather_than_an_error(self):
        with TemporaryDirectory() as tmp:
            assert positioncache.read("nope.vrf", root=Path(tmp)) is None
            assert not positioncache.has("nope.vrf", root=Path(tmp))

    def test_a_written_entry_reads_back_equal(self):
        with TemporaryDirectory() as tmp:
            positioncache.write("x.vrf", sidecar(), root=Path(tmp))
            assert positioncache.has("x.vrf", root=Path(tmp))
            back = positioncache.read("x.vrf", root=Path(tmp))
            assert back.positions == {1: track()}
            assert back.match_id == MATCH

    def test_a_corrupt_entry_is_deleted_rather_than_kept(self):
        """
        Otherwise a format change costs a decode on every run, not just once.

        The cache is regenerable by definition, so dropping an entry that
        cannot be read is strictly better than reading around it forever.
        """
        with TemporaryDirectory() as tmp:
            path = positioncache.cache_path("x.vrf", root=Path(tmp))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("this is not json", encoding="utf-8")
            assert positioncache.read("x.vrf", root=Path(tmp)) is None
            assert not path.exists()

    def test_an_unwritable_cache_costs_a_decode_and_nothing_else(self):
        with TemporaryDirectory() as tmp:
            wall = Path(tmp) / "file"
            wall.write_text("not a directory", encoding="utf-8")
            assert positioncache.write("x.vrf", sidecar(), root=wall / "under") is None


class TestSidecarFormat(unittest.TestCase):
    def test_ability_spawns_survive_a_round_trip(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.positions.json"
            positionfile.write(
                path,
                sidecar(ability_spawns=SPAWNS, ability_tracks={42: track(42)}),
            )
            back = positionfile.read(path)
        assert back.ability_spawns == SPAWNS
        assert back.ability_tracks == {42: track(42)}

    def test_spawns_are_stored_raw_and_not_as_casts(self):
        """
        A spawn is a fact off the wire; a cast is a reading of several.

        The reading has already changed once -- naming a Killjoy turret after
        its `TurretAttack` sub-actor -- so the sidecar keeps the facts and the
        grouping is redone on load.  Otherwise every improvement to
        `abilities.casts` would mean throwing away every cached decode.
        """
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.positions.json"
            positionfile.write(path, sidecar(ability_spawns=SPAWNS))
            raw = json.loads(path.read_text(encoding="utf-8"))
        assert "ability_casts" not in raw
        assert raw["ability_spawns"]["41"] == [TURRET_CAST, 1200]

    def test_a_malformed_spawn_is_refused(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.positions.json"
            positionfile.write(path, sidecar(ability_spawns=SPAWNS))
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["ability_spawns"]["41"] = ["only a path"]
            path.write_text(json.dumps(doc), encoding="utf-8")
            with pytest.raises(positionfile.PositionFileError):
                positionfile.read(path)

    def test_a_version_one_sidecar_still_reads(self):
        """
        v1 files are real decodes written before abilities existed.

        Refusing them would throw away four minutes of correct work over a
        field they were never asked to carry.
        """
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.positions.json"
            positionfile.write(path, sidecar())
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["version"] = 1
            del doc["ability_spawns"]
            del doc["ability_tracks"]
            path.write_text(json.dumps(doc), encoding="utf-8")

            back = positionfile.read(path)
        assert back.positions == {1: track()}
        assert back.ability_spawns == {}

    def test_an_unknown_version_is_still_refused(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "future.positions.json"
            positionfile.write(path, sidecar())
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["version"] = 99
            path.write_text(json.dumps(doc), encoding="utf-8")
            with pytest.raises(positionfile.PositionFileError):
                positionfile.read(path)


class TestAttachSources(unittest.TestCase):
    """
    Which of the three sources answered, for a `.vrf` that is never opened.

    None of these reach a decode: each one puts an answer in front of
    `attach` and checks it was taken and described.  A decode needs Oodle and
    a 47 MB capture and is covered by `tests/test_tracks.py`.
    """

    def setUp(self):
        self.tmp = self.enterContext(TemporaryDirectory())
        self.vrf = Path(self.tmp) / f"{MATCH}.vrf"
        self.vrf.write_bytes(b"not really a replay")
        self.cache = Path(self.tmp) / "cache"

    def replay(self):
        return Replay(source=str(self.vrf), match_id=MATCH)

    def test_a_sidecar_beside_the_file_answers_first(self):
        positionfile.write(positionfile.sidecar_path(self.vrf), sidecar())
        found = tracks.attach(self.replay(), self.vrf)
        assert found.has_positions
        assert "read from" in found.position_source
        assert ".positions.json" in found.position_source

    def test_the_cache_answers_when_there_is_no_sidecar(self):
        positioncache.write(self.vrf, sidecar(), root=self.cache)
        with CacheRoot(self.cache):
            found = tracks.attach(self.replay(), self.vrf)
        assert found.has_positions
        assert "read from cache" in found.position_source

    def test_the_cache_is_skipped_when_it_is_turned_off(self):
        """
        `Options(cache=False)` is how a test forces the decoder to run.

        Without it a cached entry would make a decoding regression invisible.
        """
        positioncache.write(self.vrf, sidecar(), root=self.cache)
        with CacheRoot(self.cache):
            found = tracks.attach(
                self.replay(),
                self.vrf,
                tracks.Options(cache=False),
            )
        assert not found.has_positions

    def test_abilities_arrive_with_the_positions(self):
        positionfile.write(
            positionfile.sidecar_path(self.vrf),
            sidecar(ability_spawns=SPAWNS, ability_tracks={42: track(42)}),
        )
        found = tracks.attach(self.replay(), self.vrf)
        assert found.has_abilities
        assert found.ability_track(42) == track(42)
        cast = found.ability_casts[0]
        assert cast.codename == "Killjoy"
        assert cast.slot == "E"
        assert cast.pawns == (42,)

    def test_casts_are_regrouped_on_load_not_read_back_grouped(self):
        """
        The pawn names the cast, even though the `Ability_` spawn is earlier.

        This is the grouping rule applying to a sidecar written before it
        existed -- which is the whole point of storing spawns.
        """
        positionfile.write(
            positionfile.sidecar_path(self.vrf),
            sidecar(ability_spawns=SPAWNS),
        )
        found = tracks.attach(self.replay(), self.vrf)
        assert [c.name for c in found.ability_casts] == ["Turret"]

    def test_a_sidecar_for_another_match_is_refused_not_drawn(self):
        """
        A loose file can be copied next to the wrong capture.

        The tracks would look entirely plausible, which is exactly why both
        sides record the match id and this refuses rather than draws.
        """
        positionfile.write(
            positionfile.sidecar_path(self.vrf),
            sidecar(match_id="a-different-match"),
        )
        found = tracks.attach(self.replay(), self.vrf, tracks.Options(cache=False))
        assert not found.has_positions
        assert "a-different-match" in found.position_source

    def test_a_codename_from_the_sidecar_reaches_the_player(self):
        replay = self.replay()
        replay.players = [_player(1)]
        positionfile.write(positionfile.sidecar_path(self.vrf), sidecar())
        found = tracks.attach(replay, self.vrf)
        assert found.players[0].codename == "Hunter"


def _player(actor_id):
    from vrfview.model import Player

    return Player(actor_id=actor_id, team="A", label="A1")


class CacheRoot:
    """Point `positioncache` at a temporary directory for one block."""

    def __init__(self, root):
        self.root = root

    def __enter__(self):
        self.was = positioncache.cache_root
        positioncache.cache_root = lambda: self.root
        return self.root

    def __exit__(self, *_exc):
        positioncache.cache_root = self.was
        return False
