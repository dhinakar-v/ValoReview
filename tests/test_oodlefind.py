"""
Tests for the .env reader and the Oodle discovery order.

None of these touch a real oo2core runtime: discovery resolves a *path*, and
binding that path is ctypes' problem, so every fixture here is an empty file
with the right name.  That keeps the suite runnable on a machine with no Oodle
DLL at all -- which, per oodlefind's module docstring, is any machine whose
only Unreal game is Valorant.

The behaviour worth pinning is that steps 1 and 2 of the search order raise on
a bad path instead of falling through to a scan.  A typo in .env used to be
indistinguishable from a missing DLL, and the scan that followed it could take
seconds before reporting the wrong thing.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

import envfile
import oodlefind

DLL_NAME = "oo2core_9_win64.dll"


class EnvFileParsing(unittest.TestCase):
    def test_plain_pairs(self):
        got = envfile.parse("A=1\nB=two\n")
        assert got == {"A": "1", "B": "two"}

    def test_comments_and_blanks_are_skipped(self):
        got = envfile.parse("# note\n\nA=1\nnot a pair\n")
        assert got == {"A": "1"}

    def test_export_prefix_is_tolerated(self):
        assert envfile.parse("export A=1\n") == {"A": "1"}

    def test_quoted_value_keeps_its_spaces_and_hash(self):
        got = envfile.parse('A="C:\\Program Files\\x #1\\oo2.dll"\n')
        assert got == {"A": "C:\\Program Files\\x #1\\oo2.dll"}

    def test_unquoted_value_drops_a_trailing_comment(self):
        assert envfile.parse("A=1 # why\n") == {"A": "1"}

    def test_windows_path_survives_unquoted(self):
        """Backslashes are literal; only ` #` is special."""
        got = envfile.parse("VRF_OODLE_DLL=C:\\Games\\x\\oo2core_9_win64.dll\n")
        assert got == {"VRF_OODLE_DLL": "C:\\Games\\x\\oo2core_9_win64.dll"}

    def test_later_duplicate_wins(self):
        assert envfile.parse("A=1\nA=2\n") == {"A": "2"}

    def test_value_may_contain_equals(self):
        assert envfile.parse("A=b=c\n") == {"A": "b=c"}

    def test_missing_file_reads_as_empty(self):
        envfile.clear_cache()
        assert envfile.read(Path("no-such-file-anywhere.env")) == {}


class Sandbox(unittest.TestCase):
    """
    A temp project root, with cwd, the env var and the game scan all restored.

    game_roots is stubbed to nothing so the machine running the suite cannot
    decide a result: a developer with Fortnite installed would otherwise see
    the scan succeed where a clean CI box sees it fail.  Tests that want the
    real scan call self.real_game_roots.
    """

    def setUp(self):
        self._cwd = Path.cwd()
        self._environ = dict(os.environ)
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "pyproject.toml").write_text("", encoding="utf-8")
        os.chdir(self.root)
        os.environ.pop(oodlefind.ENV_VAR, None)
        envfile.clear_cache()
        self.real_game_roots = oodlefind.game_roots
        oodlefind.game_roots = list

    def tearDown(self):
        oodlefind.game_roots = self.real_game_roots
        os.chdir(self._cwd)
        os.environ.clear()
        os.environ.update(self._environ)
        envfile.clear_cache()
        self._tmp.cleanup()

    def make_dll(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    def write_env(self, text: str) -> None:
        (self.root / ".env").write_text(text, encoding="utf-8")
        envfile.clear_cache()

    def locate(self, explicit=None):
        # use_cache=False: a real cache in %LOCALAPPDATA% must not decide a test.
        return oodlefind.locate(explicit, use_cache=False)


class DiscoveryOrder(Sandbox):
    def test_explicit_argument_wins(self):
        chosen = self.make_dll("elsewhere", DLL_NAME)
        self.make_dll("vendor", DLL_NAME)
        self.write_env(f"{oodlefind.ENV_VAR}={self.root / 'vendor' / DLL_NAME}\n")
        assert self.locate(chosen) == chosen

    def test_real_environment_beats_dotenv(self):
        from_environ = self.make_dll("environ", DLL_NAME)
        from_file = self.make_dll("dotenv", DLL_NAME)
        self.write_env(f"{oodlefind.ENV_VAR}={from_file}\n")
        os.environ[oodlefind.ENV_VAR] = str(from_environ)
        assert self.locate() == from_environ

    def test_dotenv_is_read_when_the_environment_is_unset(self):
        expected = self.make_dll("dotenv", DLL_NAME)
        self.write_env(f"{oodlefind.ENV_VAR}={expected}\n")
        assert self.locate() == expected

    def test_dotenv_value_may_be_quoted(self):
        expected = self.make_dll("dotenv", DLL_NAME)
        self.write_env(f'{oodlefind.ENV_VAR}="{expected}"\n')
        assert self.locate() == expected

    def test_dotenv_beats_vendor(self):
        expected = self.make_dll("dotenv", DLL_NAME)
        self.make_dll("vendor", DLL_NAME)
        self.write_env(f"{oodlefind.ENV_VAR}={expected}\n")
        assert self.locate() == expected

    def test_vendor_is_used_when_nothing_is_configured(self):
        expected = self.make_dll("vendor", DLL_NAME)
        assert self.locate() == expected

    def test_vendor_prefers_the_highest_version(self):
        self.make_dll("vendor", "oo2core_5_win64.dll")
        newest = self.make_dll("vendor", "oo2core_10_win64.dll")
        self.make_dll("vendor", "oo2core_9_win64.dll")
        assert self.locate() == newest

    def test_vendor_ignores_an_unrelated_dll(self):
        self.make_dll("vendor", "something_else.dll")
        with pytest.raises(oodlefind.OodleNotFoundError):
            self.locate()


class ConfiguredPathsFailLoudly(Sandbox):
    """Steps 1 and 2 are deliberate, so a miss is an error, not a fallback."""

    def test_bad_explicit_path_raises_even_though_vendor_has_one(self):
        self.make_dll("vendor", DLL_NAME)
        with pytest.raises(oodlefind.OodleNotFoundError) as caught:
            self.locate(self.root / "nope.dll")
        assert "--oodle-dll" in str(caught.value)

    def test_bad_dotenv_path_names_the_file_it_came_from(self):
        self.make_dll("vendor", DLL_NAME)
        self.write_env(f"{oodlefind.ENV_VAR}={self.root / 'nope.dll'}\n")
        with pytest.raises(oodlefind.OodleNotFoundError) as caught:
            self.locate()
        message = str(caught.value)
        assert ".env" in message
        assert "nope.dll" in message

    def test_bad_environment_path_says_it_came_from_the_environment(self):
        os.environ[oodlefind.ENV_VAR] = str(self.root / "nope.dll")
        with pytest.raises(oodlefind.OodleNotFoundError) as caught:
            self.locate()
        assert "environment" in str(caught.value)

    def test_a_directory_is_not_a_dll(self):
        (self.root / "dir.dll").mkdir()
        with pytest.raises(oodlefind.OodleNotFoundError):
            self.locate(self.root / "dir.dll")


class NotFoundMessage(unittest.TestCase):
    def test_lists_every_way_to_supply_a_dll(self):
        message = oodlefind.not_found_message(0)
        assert "vendor" in message
        assert oodlefind.ENV_VAR in message
        assert "--oodle-dll" in message

    def test_says_valorant_cannot_provide_one(self):
        """The install looks like it should have a DLL; it does not."""
        assert "Valorant" in oodlefind.not_found_message(0)

    def test_singular_and_plural_agree(self):
        assert "1 game directory" in oodlefind.not_found_message(1)
        assert "0 game directories" in oodlefind.not_found_message(0)
        assert "7 game directories" in oodlefind.not_found_message(7)


class GameScanning(Sandbox):
    def test_unreal_layout_is_matched(self):
        game = self.root / "game"
        dll = game / "Engine/Binaries/ThirdParty/Oodle/Win64" / DLL_NAME
        dll.parent.mkdir(parents=True)
        dll.write_bytes(b"")
        assert oodlefind._match_in(game) == dll

    def test_dll_beside_the_exe_is_matched(self):
        game = self.root / "game"
        dll = game / "ShooterGame/Binaries/Win64" / DLL_NAME
        dll.parent.mkdir(parents=True)
        dll.write_bytes(b"")
        assert oodlefind._match_in(game) == dll

    def test_a_game_without_oodle_matches_nothing(self):
        game = self.root / "game"
        (game / "Engine/Binaries/Win64").mkdir(parents=True)
        (game / "Engine/Binaries/Win64/other.dll").write_bytes(b"")
        assert oodlefind._match_in(game) is None

    def test_scan_does_not_walk_the_whole_install(self):
        """A deeply buried DLL is intentionally missed; the globs are bounded."""
        game = self.root / "game"
        buried = game / "a/b/c/d/e/f" / DLL_NAME
        buried.parent.mkdir(parents=True)
        buried.write_bytes(b"")
        assert oodlefind._match_in(game) is None

    def test_every_source_degrades_to_a_list_rather_than_raising(self):
        """Whatever this machine has or lacks, none of these may blow up."""
        assert isinstance(oodlefind.steam_libraries(), list)
        assert isinstance(oodlefind.epic_installs(), list)
        assert isinstance(self.real_game_roots(), list)


class VdfParsing(unittest.TestCase):
    def test_current_format(self):
        text = (
            '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"D:\\\\Games\\\\S"\n\t}\n}'
        )
        found = oodlefind._VDF_PATH_RE.findall(text)
        assert "D:\\\\Games\\\\S" in found

    def test_legacy_numeric_keys(self):
        found = oodlefind._VDF_PATH_RE.findall('"1"\t\t"E:\\\\SteamLibrary"')
        assert found == ["E:\\\\SteamLibrary"]


if __name__ == "__main__":
    unittest.main()
