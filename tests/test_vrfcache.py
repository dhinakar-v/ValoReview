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


class FindingTheRoot(unittest.TestCase):
    def setUp(self):
        self._cwd = Path.cwd()
        self.addCleanup(os.chdir, self._cwd)
        self.addCleanup(envfile.clear_cache)
        envfile.clear_cache()

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
