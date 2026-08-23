"""
The bridge to the C# decoder: locating it, and reading what it wrote.

Nothing here runs the decoder.  Locating one resolves a *path*, and what a
built decoder does with a capture is that program's business and the real
captures' business -- `tests/test_tracks.py` covers that end.  So every fixture
here is a small file with the right name, in the same spirit as
`tests/test_oodlefind.py`, and the suite stays runnable with no .NET SDK, no
clone and no `.vrf`.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

import envfile
from vrfview import csharpdecode

EXE = "vrf-positions.exe"


def _decode_doc(**overrides) -> dict:
    """The smallest well-formed emitter file: one actor, two samples."""
    doc = {
        "format": "vrf-csharp-decode",
        "version": 1,
        "hz": 10,
        "moves": 7,
        "archetypes": {"642": "/Game/Characters/Wushu/Wushu_PC.Default__Wushu_PC_C"},
        "first_seen": {"642": 660},
        "spawn_locations": {"642": [1800.0, -1900.0, 400.3]},
        "samples": {
            "642": {
                "t": [695, 796],
                "x": [1800.0, 1801.5],
                "y": [-1900.0, -1901.5],
                "z": [400.3, 400.3],
                "yaw": [270.0, 271.0],
                "pitch": [0.0, -1.0],
            },
        },
    }
    doc.update(overrides)
    return doc


class Sandbox(unittest.TestCase):
    """A tmp directory, and an environment with nothing configured in it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        self._env = os.environ.get(csharpdecode.ENV_VAR)
        os.environ.pop(csharpdecode.ENV_VAR, None)
        self.addCleanup(self._restore_env)
        envfile.clear_cache()

    def _restore_env(self):
        if self._env is None:
            os.environ.pop(csharpdecode.ENV_VAR, None)
        else:
            os.environ[csharpdecode.ENV_VAR] = self._env
        envfile.clear_cache()

    def write(self, name: str, doc) -> Path:
        path = self.root / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path


class Reading(Sandbox):
    def test_a_well_formed_file_reads_back(self):
        path = self.write("d.json", _decode_doc())
        decoded = csharpdecode.read(path)

        assert decoded.moves == 7
        assert decoded.hz == 10
        assert decoded.archetypes[642].endswith("Default__Wushu_PC_C")
        assert decoded.spawn_locations[642] == (1800.0, -1900.0, 400.3)

    def test_first_seen_comes_back_in_seconds(self):
        """The file stores milliseconds; abilities.spawns_from wants seconds."""
        path = self.write("d.json", _decode_doc())
        assert csharpdecode.read(path).first_seen[642] == 0.66

    def test_samples_become_positions_carrying_their_actor(self):
        path = self.write("d.json", _decode_doc())
        samples = csharpdecode.read(path).samples[642]

        assert [p.t_ms for p in samples] == [695, 796]
        assert [p.actor_id for p in samples] == [642, 642]
        assert samples[1].yaw == 271.0
        assert samples[1].pitch == -1.0

    def test_floats_survive_the_round_trip_exactly(self):
        """A sidecar written from this must equal one written from a decode."""
        path = self.write("d.json", _decode_doc())
        assert csharpdecode.read(path).samples[642][0].z == 400.3


class RefusingBadFiles(Sandbox):
    def test_a_file_that_is_not_a_decode_is_refused(self):
        path = self.write("d.json", {"format": "something-else", "version": 1})
        with pytest.raises(csharpdecode.DecodeError) as caught:
            csharpdecode.read(path)
        assert "vrf-csharp-decode" in str(caught.value)

    def test_an_unknown_version_is_refused_rather_than_guessed(self):
        path = self.write("d.json", _decode_doc(version=99))
        with pytest.raises(csharpdecode.DecodeError) as caught:
            csharpdecode.read(path)
        assert "99" in str(caught.value)

    def test_a_missing_column_is_refused(self):
        doc = _decode_doc()
        del doc["samples"]["642"]["pitch"]
        path = self.write("d.json", doc)
        with pytest.raises(csharpdecode.DecodeError):
            csharpdecode.read(path)

    def test_ragged_columns_are_refused(self):
        """Six arrays that disagree on length cannot all describe one sample."""
        doc = _decode_doc()
        doc["samples"]["642"]["yaw"] = [270.0]
        path = self.write("d.json", doc)
        with pytest.raises(csharpdecode.DecodeError) as caught:
            csharpdecode.read(path)
        assert "ragged" in str(caught.value)

    def test_an_absent_file_is_refused_with_its_name(self):
        with pytest.raises(csharpdecode.DecodeError) as caught:
            csharpdecode.read(self.root / "nope.json")
        assert "nope.json" in str(caught.value)


class Locating(Sandbox):
    def test_an_explicit_path_wins(self):
        exe = self.root / EXE
        exe.write_text("", encoding="utf-8")
        assert csharpdecode.locate(exe) == exe

    def test_an_explicit_path_that_does_not_exist_is_an_error(self):
        """Configured deliberately, so a wrong path is a mistake, not a hint."""
        with pytest.raises(csharpdecode.DecodeError) as caught:
            csharpdecode.locate(self.root / "absent.exe")
        assert "--parser-exe" in str(caught.value)

    def test_the_environment_is_read_when_nothing_is_passed(self):
        exe = self.root / EXE
        exe.write_text("", encoding="utf-8")
        os.environ[csharpdecode.ENV_VAR] = str(exe)
        assert csharpdecode.locate() == exe

    def test_a_wrong_environment_variable_is_an_error_not_a_fallthrough(self):
        os.environ[csharpdecode.ENV_VAR] = str(self.root / "absent.exe")
        with pytest.raises(csharpdecode.DecodeError) as caught:
            csharpdecode.locate()
        assert csharpdecode.ENV_VAR in str(caught.value)

    def test_quotes_around_a_configured_path_are_stripped(self):
        exe = self.root / EXE
        exe.write_text("", encoding="utf-8")
        os.environ[csharpdecode.ENV_VAR] = f'"{exe}"'
        assert csharpdecode.locate() == exe


class Invoking(unittest.TestCase):
    """How the two shapes of decoder are launched."""

    def test_a_dll_is_run_through_the_runtime_launcher(self):
        command = csharpdecode._command(
            Path("x/vrf-positions.dll"),
            Path("m.vrf"),
            Path("o.json"),
            10,
        )
        assert command[0] == "dotnet"
        assert command[1].endswith("vrf-positions.dll")

    def test_a_published_exe_runs_itself(self):
        command = csharpdecode._command(
            Path("x/vrf-positions.exe"),
            Path("m.vrf"),
            Path("o.json"),
            10,
        )
        assert command[0].endswith("vrf-positions.exe")
        assert "dotnet" not in command

    def test_the_rate_is_passed_through(self):
        command = csharpdecode._command(
            Path("x/vrf-positions.exe"),
            Path("m.vrf"),
            Path("o.json"),
            25,
        )
        assert command[-2:] == ["--hz", "25"]

    def test_windows_gets_no_console_and_everywhere_else_gets_nothing(self):
        """
        A GUI host has no console to lend a child, so Windows gives it one of
        its own and it flashes.  One decode would be a blemish; `prewarm` runs
        a library of them back to back.  The flag is Windows-only, and
        `subprocess` refuses a non-zero one elsewhere, so the other platforms
        have to come back exactly 0 rather than merely falsy.
        """
        with mock.patch.object(csharpdecode.os, "name", "nt"):
            assert csharpdecode._quiet_flags() == csharpdecode._CREATE_NO_WINDOW
        with mock.patch.object(csharpdecode.os, "name", "posix"):
            assert csharpdecode._quiet_flags() == 0


if __name__ == "__main__":
    unittest.main()
