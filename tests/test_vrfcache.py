"""
The one directory every regenerable thing goes in, and how it is found.

The interesting property is not the path -- it is that the path does not
depend on the working directory, which is the bug the old `out/` cache had.
So the tests below run the resolution from a subdirectory and from a temp
project, and assert nothing is created merely by asking.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

import envfile
import vrfcache

REPO = Path(__file__).resolve().parents[1]


def _unset_configured_root(case: unittest.TestCase) -> None:
    """
    Run as if nobody had named a cache directory.

    Every assertion about *searching* for the root is only about searching if
    `VRF_CACHE_ROOT` is not answering first, and a developer with the packaged
    app's variable exported would otherwise see this file fail for a reason
    that has nothing to do with the code.
    """
    patch = mock.patch.dict(os.environ, {}, clear=False)
    case.enterContext(patch)
    os.environ.pop(vrfcache.ROOT_ENV, None)


class FindingTheRoot(unittest.TestCase):
    def setUp(self):
        self._cwd = Path.cwd()
        self.addCleanup(os.chdir, self._cwd)
        self.addCleanup(envfile.clear_cache)
        envfile.clear_cache()
        _unset_configured_root(self)

    def test_the_root_is_the_directory_holding_the_marker(self):
        assert vrfcache.project_root() == REPO
        assert (REPO / vrfcache.MARKER).is_file()

    def test_the_cache_is_dot_cache_under_the_root(self):
        assert vrfcache.root() == REPO / vrfcache.CACHE_DIRNAME
        assert vrfcache.CACHE_DIRNAME == ".cache"

    def test_subdir_composes_under_the_cache(self):
        assert vrfcache.subdir("positions") == REPO / ".cache" / "positions"
        assert vrfcache.subdir("a", "b") == REPO / ".cache" / "a" / "b"

    def test_running_from_a_subdirectory_finds_the_same_root(self):
        """
        The whole point.  `out/` was a bare relative path and moved with the
        CWD; this is searched for, so every entry point agrees.
        """
        os.chdir(REPO / "libraries" / "vrfview")
        envfile.clear_cache()
        assert vrfcache.project_root() == REPO

    def test_asking_creates_nothing(self):
        """
        A `cache_root()` with a side effect would mean merely *asking* where
        the cache is made one, and `--no-cache` would still litter.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / vrfcache.MARKER).write_text("", encoding="utf-8")
            os.chdir(root)
            envfile.clear_cache()
            assert vrfcache.root() == root / ".cache"
            assert not (root / ".cache").exists()
            # Windows will not remove a directory that is the CWD.
            os.chdir(self._cwd)

    def test_a_nearer_project_wins(self):
        """
        How a test gets an isolated cache: chdir into a temp project rather
        than writing into this repository's own .cache/.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / vrfcache.MARKER).write_text("", encoding="utf-8")
            os.chdir(root)
            envfile.clear_cache()
            assert vrfcache.project_root() == root
            os.chdir(self._cwd)


class WithNoProjectRoot(unittest.TestCase):
    """
    An installed wheel in site-packages, which has no marker above it.

    Simulated by patching the search rather than by chdir: `find_upwards` also
    walks up from `envfile.__file__`, which lives inside this repository, so
    no working directory can make the real root invisible.
    """

    def setUp(self):
        patch = mock.patch.object(vrfcache.envfile, "find_upwards", return_value=None)
        self.enterContext(patch)
        _unset_configured_root(self)

    def test_project_root_is_none_rather_than_a_guess(self):
        assert vrfcache.project_root() is None

    def test_root_refuses_instead_of_falling_back(self):
        """
        No CWD fallback (that was the `out/` bug) and no %LOCALAPPDATA%
        fallback (that is the directory this module exists to retire).
        """
        with pytest.raises(vrfcache.NoProjectRootError):
            vrfcache.root()

    def test_subdir_refuses_too(self):
        with pytest.raises(vrfcache.NoProjectRootError):
            vrfcache.subdir("positions")

    def test_the_refusal_says_what_would_fix_it(self):
        with pytest.raises(vrfcache.NoProjectRootError) as caught:
            vrfcache.root()
        assert vrfcache.MARKER in str(caught.value)
        assert vrfcache.ROOT_ENV in str(caught.value)

    def test_root_or_none_is_the_half_that_does_not_raise(self):
        """
        `vrfhome.scan` and `vrfview.csharpdecode` both want a directory or
        nothing at all -- a rescan and a temp file are their answers, and
        neither is worth an exception to reach.
        """
        assert vrfcache.root_or_none() is None


class WhenAnInstallerNamesTheRoot(unittest.TestCase):
    """
    The packaged desktop app, which has no checkout for the search to find.

    `VRF_CACHE_ROOT` is read *before* the search, so these cases hold whether
    or not there is a project root above the code -- which is the point: a
    packaged copy must not start caching into whatever tree it was launched
    from.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.named = Path(self._tmp.name).resolve() / "cache"
        patch = mock.patch.dict(os.environ, {vrfcache.ROOT_ENV: str(self.named)})
        self.enterContext(patch)
        self.addCleanup(envfile.clear_cache)
        envfile.clear_cache()

    def test_the_named_directory_is_the_cache(self):
        assert vrfcache.configured_root() == self.named
        assert vrfcache.root() == self.named

    def test_it_is_the_cache_itself_and_not_a_project_root(self):
        """
        An installer has somewhere to put files, not somewhere a pyproject.toml
        pretends to be -- so no `.cache/` is appended to what it names.
        """
        assert vrfcache.CACHE_DIRNAME not in vrfcache.root().parts

    def test_subdir_composes_under_it(self):
        assert vrfcache.subdir("positions") == self.named / "positions"

    def test_it_wins_over_a_project_root_that_does_exist(self):
        """
        This repository is above the code running these tests, so the search
        would succeed.  Being told beats finding out.
        """
        assert vrfcache.project_root() == REPO
        assert vrfcache.root() != REPO / vrfcache.CACHE_DIRNAME

    def test_asking_still_creates_nothing(self):
        vrfcache.subdir("positions")
        assert not self.named.exists()

    def test_it_wins_with_no_project_root_either(self):
        with mock.patch.object(vrfcache.envfile, "find_upwards", return_value=None):
            assert vrfcache.root() == self.named
            assert vrfcache.root_or_none() == self.named
