"""
The structural rules the packages keep about each other.

These used to be four separate guards, one per package, each asserting that its
own sources reached for no widget set.  They existed to make deleting the
CustomTkinter interface safe, and now that it is gone the interesting statement
is the stronger and simpler one: **nothing under `libraries/` imports a toolkit
at all.**  One walk over the whole source root says that, and it cannot go
stale as modules are added the way a hand-maintained list of package names can.

The second rule is the one the decoder boundary rests on and is unaffected by
that deletion: `tracks` is the only module allowed to reach the build table,
because everything else in the model layer has to run with no decoder present.

Both are read statically rather than by importing.  A source walk catches an
import hiding inside a function body or behind a branch, and it names the file
that broke the rule instead of failing somewhere down an import chain.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIBRARIES = REPO / "libraries"

# The widget sets.  Not PIL: `sight.SightMap` reads the radar PNG's alpha
# channel and `art` resolves the files it reads, so Pillow is a model-layer
# dependency and outlived the interface it was first added for.
TOOLKITS = ("tkinter", "customtkinter")

# Everything in `vrfview` that must run with no decoder built and no `.vrf`
# open.  `tracks` is deliberately absent: it is the one bridge from the
# replication stream into the model, and the rule is that it is the only one.
MODEL_MODULES = (
    "abilities",
    "art",
    "clock",
    "csharpdecode",
    "infer",
    "loader",
    "model",
    "names",
    "positioncache",
    "positionfile",
    "sight",
    "state",
    "theme",
)

# `vrfnet` is the build table and its bit reader, and nothing else -- the net
# stack that gave the package its name is gone.
BUILD_TABLE = "vrfnet"


def _imports(path: Path) -> set[str]:
    """Every module name this file imports, however deeply nested."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


class NoToolkitAnywhere(unittest.TestCase):
    """
    The whole library runs headlessly, and there is no exception to carve out.

    Every entry point left is a CLI or the server: `vrf-serve` renders in a
    browser, `vrf-to-json` prints, and the prewarmer decodes on a background
    thread with nothing on screen.  So a toolkit import anywhere under
    `libraries/` is a mistake rather than a layer, which is what lets this be
    one assertion over one glob instead of a list that has to be maintained.
    """

    def test_no_module_under_libraries_imports_a_toolkit(self):
        sources = sorted(LIBRARIES.rglob("*.py"))
        assert sources, "no sources found under libraries/"
        for path in sources:
            for name in _imports(path):
                root = name.split(".")[0]
                assert root not in TOOLKITS, f"{path.relative_to(REPO)} imports {name}"


class OnlyTracksReachesTheDecoder(unittest.TestCase):
    """
    The model layer must not learn how a position was decoded.

    `tracks` reads the replication stream and consults the build table to
    decide whether a capture can be decoded at all.  Everything else works on
    a `Replay` that already has -- or does not have -- positions, and a module
    that reached the table would make a decode a prerequisite for opening a
    file that needs none.
    """

    def test_the_model_modules_never_reach_the_build_table(self):
        for module in MODEL_MODULES:
            path = LIBRARIES / "vrfview" / f"{module}.py"
            assert path.exists(), f"{module} is not in vrfview any more"
            for name in _imports(path):
                assert name.split(".")[0] != BUILD_TABLE, (
                    f"vrfview.{module} imports {name}"
                )

    def test_tracks_is_the_module_that_does(self):
        """The rule above is only worth asserting while something still does."""
        names = _imports(LIBRARIES / "vrfview" / "tracks.py")
        assert any(n.split(".")[0] == BUILD_TABLE for n in names)


if __name__ == "__main__":
    unittest.main()
