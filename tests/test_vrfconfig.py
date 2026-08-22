"""
Tests for DEMO_PATH resolution and the positions sidecar.

Neither needs a capture, a display or a DLL.  The sidecar tests build Tracks by
hand and assert the file round-trips them *exactly* -- not approximately --
because a Replay read from a sidecar has to be the same Replay the decoder
built, or the JSON path quietly draws something slightly else.

The DEMO_PATH tests run in a temporary directory with the real environment
variable cleared, because envfile deliberately lets a shell export win and this
machine may well have one.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

import envfile
import vrfconfig
from vrfview import positionfile, tracks
from vrfview.model import Position, Replay, Track


class DemoPathResolution(unittest.TestCase):
    def setUp(self):
        self._cwd = Path.cwd()
        self._demo_path = os.environ.pop(vrfconfig.DEMO_PATH_KEY, None)
        self._dir = TemporaryDirectory()
        os.chdir(self._dir.name)
        envfile.clear_cache()

    def tearDown(self):
        os.chdir(self._cwd)
        self._dir.cleanup()
        if self._demo_path is not None:
            os.environ[vrfconfig.DEMO_PATH_KEY] = self._demo_path
        else:
            os.environ.pop(vrfconfig.DEMO_PATH_KEY, None)
        envfile.clear_cache()

    def test_default_is_demos_and_says_so(self):
        """
        With nothing set anywhere, the default answers and names itself.

        `find_upwards` is patched out rather than merely chdir-ing to a temp
        directory, because it deliberately searches from *this module's* home
        as well as from the cwd -- that is what makes an installed wheel find
        the `.env` beside it.  Here that means a developer who has a real
        `.env` at the repository root would otherwise have it decide the
        result, and the one thing this test is for is what happens when
        nothing has been decided.
        """
        with mock.patch.object(envfile, "find_upwards", return_value=None):
            root = vrfconfig.demo_root()
        assert root.path == Path(vrfconfig.DEFAULT_DEMO_PATH)
        assert root.source == vrfconfig.SOURCE_DEFAULT

    def test_environment_wins_over_the_env_file(self):
        Path(".env").write_text("DEMO_PATH=from_file\n", encoding="utf-8")
        envfile.clear_cache()
        os.environ[vrfconfig.DEMO_PATH_KEY] = "from_environ"
        root = vrfconfig.demo_root()
        assert root.path == Path("from_environ")
        assert root.source == vrfconfig.SOURCE_ENVIRON

    def test_env_file_is_read_and_named(self):
        Path(".env").write_text("DEMO_PATH=captures\n", encoding="utf-8")
        envfile.clear_cache()
        root = vrfconfig.demo_root()
        assert root.path == Path("captures")
        assert ".env" in root.source

    def test_an_override_beats_everything(self):
        os.environ[vrfconfig.DEMO_PATH_KEY] = "from_environ"
        root = vrfconfig.demo_root("explicit")
        assert root.path == Path("explicit")
        assert "command line" in root.source

    def test_nothing_mutates_the_real_environment(self):
        Path(".env").write_text("DEMO_PATH=captures\n", encoding="utf-8")
        envfile.clear_cache()
        vrfconfig.demo_root()
        assert vrfconfig.DEMO_PATH_KEY not in os.environ

    def test_a_missing_directory_resolves_and_reports_itself(self):
        root = vrfconfig.demo_root("nowhere")
        assert not root.exists
        assert "no such directory" in root.described
        assert vrfconfig.replays("nowhere") == []

    def test_replays_lists_only_vrf_files_sorted(self):
        library = Path("library")
        library.mkdir()
        for name in ("b.vrf", "a.vrf", "notes.txt"):
            (library / name).write_bytes(b"")
        found = vrfconfig.replays("library")
        assert [p.name for p in found] == ["a.vrf", "b.vrf"]


def _track(actor_id: int, count: int) -> Track:
    return Track(
        actor_id=actor_id,
        samples=tuple(
            Position(
                t_ms=i * 100,
                actor_id=actor_id,
                # Values a float cannot express in decimal, so a lossy writer
                # (rounding, %.3f) would be caught by the equality assertion.
                x=1000.0 + i / 3,
                y=-2000.0 - i / 7,
                z=64.5,
                yaw=(i * 37) % 360 + 0.125,
                pitch=-0.5,
            )
            for i in range(count)
        ),
    )


class SidecarRoundTrip(unittest.TestCase):
    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def test_path_sits_beside_the_dump(self):
        side = positionfile.sidecar_path("out/match.json")
        assert side == Path("out/match.positions.json")

    def test_tracks_survive_exactly(self):
        positions = {12: _track(12, 50), 34: _track(34, 3)}
        path = self.tmp / "m.positions.json"
        positionfile.write(
            path,
            positionfile.Sidecar(
                positions=positions,
                codenames={12: "Hunter"},
                description="a line about the decode",
                match_id="match-1",
                build="++Ares-Core+release-12.10",
                hz=10,
            ),
        )
        back = positionfile.read(path)
        assert back.positions == positions
        assert back.codenames == {12: "Hunter"}
        assert back.description == "a line about the decode"
        assert back.match_id == "match-1"
        assert back.hz == 10

    def test_the_document_is_what_the_file_holds(self):
        """
        One builder feeds the sidecar, the machine cache and the wire.

        Positions have to travel over HTTP as well as onto disk now, and two
        builders would be two chances to disagree about what a track looks
        like.  Asserting the in-memory document is byte-for-byte what `write`
        put in the file is what lets a served body be checked against this
        format rather than against a second description of it.
        """
        sidecar = positionfile.Sidecar(
            positions={12: _track(12, 20)},
            ability_tracks={99: _track(99, 4)},
            ability_spawns={
                99: ("/Game/Characters/Killjoy/Turret", 4200, (1.5, -2.5, 3.5)),
            },
            codenames={12: "Hunter"},
            description="a line about the decode",
            match_id="match-1",
            build="++Ares-Core+release-12.10",
            hz=10,
        )
        path = self.tmp / "m.positions.json"
        positionfile.write(path, sidecar)
        assert positionfile.to_document(sidecar) == json.loads(
            path.read_text(encoding="utf-8"),
        )

    def test_the_document_reads_back_as_the_same_tracks(self):
        sidecar = positionfile.Sidecar(positions={12: _track(12, 20)}, hz=10)
        path = self.tmp / "m.positions.json"
        path.write_text(json.dumps(positionfile.to_document(sidecar)), encoding="utf-8")
        assert positionfile.read(path).positions == sidecar.positions

    def test_a_foreign_file_is_refused(self):
        path = self.tmp / "x.positions.json"
        path.write_text(json.dumps({"hello": 1}), encoding="utf-8")
        with pytest.raises(positionfile.PositionFileError):
            positionfile.read(path)

    def test_ragged_columns_are_refused(self):
        path = self.tmp / "x.positions.json"
        path.write_text(
            json.dumps(
                {
                    "format": positionfile.FORMAT,
                    "version": positionfile.VERSION,
                    "tracks": {
                        "7": {
                            "t": [0, 1],
                            "x": [0.0],
                            "y": [0.0],
                            "z": [0.0],
                            "yaw": [0.0],
                            "pitch": [0.0],
                        },
                    },
                },
            ),
            encoding="utf-8",
        )
        with pytest.raises(positionfile.PositionFileError):
            positionfile.read(path)


class AttachFromSidecar(unittest.TestCase):
    """What tracks.attach does with a JSON dump, with and without a sidecar."""

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.dump = self.tmp / "match.json"
        self.dump.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._dir.cleanup()

    def _replay(self, match_id: str = "match-1") -> Replay:
        from vrfview.model import Player

        replay = Replay(source="match.json", match_id=match_id)
        replay.players = [Player(actor_id=12), Player(actor_id=34)]
        return replay

    def _write_sidecar(self, match_id: str = "match-1") -> None:
        positionfile.write(
            positionfile.sidecar_path(self.dump),
            positionfile.Sidecar(
                positions={12: _track(12, 5)},
                codenames={12: "Hunter"},
                description="12.10: 5 positions",
                match_id=match_id,
            ),
        )

    def test_no_sidecar_is_a_sentence_not_an_exception(self):
        replay = tracks.attach(self._replay(), self.dump)
        assert not replay.has_positions
        assert replay.position_source == tracks.NO_SOURCE_JSON

    def test_a_sidecar_supplies_positions_and_codenames(self):
        self._write_sidecar()
        replay = tracks.attach(self._replay(), self.dump)
        assert replay.has_positions
        assert len(replay.track(12)) == 5
        assert replay.players[0].codename == "Hunter"
        assert "read from match.positions.json" in replay.position_source

    def test_a_sidecar_for_another_match_is_refused(self):
        self._write_sidecar(match_id="some-other-match")
        replay = tracks.attach(self._replay(), self.dump)
        assert not replay.has_positions
        assert "not match-1" in replay.position_source

    def test_a_corrupt_sidecar_is_a_sentence_too(self):
        positionfile.sidecar_path(self.dump).write_text("{", encoding="utf-8")
        replay = tracks.attach(self._replay(), self.dump)
        assert not replay.has_positions
        assert replay.position_source.startswith("no positions:")
