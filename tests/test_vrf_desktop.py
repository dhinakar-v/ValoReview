"""The desktop backend's argv switch.

`scripts/vrf_desktop.py` is one entry point over two existing ones, because a
frozen bundle has one executable and the desktop shell needs both the server
and the first-run art fetch.  It moves no logic, so what is worth pinning is
exactly the dispatch: which `main` is called, and with which argv.

The two are patched out here rather than run.  Calling the real `vrf_serve.main`
would scan a replay directory and bind a port, and the real `fetch_assets.main`
would open a socket -- neither of which any other test in this tree does.
"""

from __future__ import annotations

import unittest
from unittest import mock

import vrf_desktop


class TheDispatcherPicksOneEntryPoint(unittest.TestCase):
    def setUp(self):
        serve = mock.patch.object(vrf_desktop.vrf_serve, "main", return_value=0)
        fetch = mock.patch.object(vrf_desktop.fetch_assets, "main", return_value=0)
        self.serve = serve.start()
        self.fetch = fetch.start()
        self.addCleanup(serve.stop)
        self.addCleanup(fetch.stop)

    def test_serve_forwards_the_rest_of_the_argv(self):
        assert vrf_desktop.main(["serve", "--port", "8123"]) == 0
        self.serve.assert_called_once_with(["--port", "8123"])
        self.fetch.assert_not_called()

    def test_naming_no_subcommand_serves(self):
        """The shell always names one, but a person running the exe by hand
        should get the server rather than a usage error."""
        assert vrf_desktop.main(["--port", "8123"]) == 0
        self.serve.assert_called_once_with(["--port", "8123"])

    def test_an_empty_argv_serves_too(self):
        assert vrf_desktop.main([]) == 0
        self.serve.assert_called_once_with([])

    def test_fetch_assets_asks_for_the_fetch_and_never_the_listing(self):
        """`fetch_assets` takes its command as a positional, and `list` prints a
        catalogue to a console a packaged app does not have."""
        assert vrf_desktop.main(["fetch-assets", "--out", "D:\\art"]) == 0
        self.fetch.assert_called_once_with(["fetch", "--out", "D:\\art"])
        self.serve.assert_not_called()

    def test_a_flag_that_looks_like_a_subcommand_is_not_one(self):
        """Only the first token selects, and only when it is one of the two."""
        assert vrf_desktop.main(["--demo-path", "serve"]) == 0
        self.serve.assert_called_once_with(["--demo-path", "serve"])


if __name__ == "__main__":
    unittest.main()
