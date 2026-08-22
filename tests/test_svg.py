"""
Every committed SVG has to parse, because a broken one fails silently.

An SVG is XML, and XML is not HTML: a malformed document is a *fatal* error,
not a warning to recover from.  A browser that cannot parse `favicon.svg`
renders nothing at all and reports nothing anywhere -- no console message, no
network failure, no missing-image glyph in the tab.  The tab simply shows the
blank-page default, which is also what a tab shows while a page is loading and
what it shows for a site with no icon, so the failure is indistinguishable
from three ordinary states.

That is not hypothetical.  `web/public/favicon.svg` shipped with a doubled
hyphen inside its comment -- the house prose style everywhere else in this
repository, and illegal inside an XML comment -- so the icon never rendered
once.  Nothing caught it because there was nothing to catch: the file was
valid on disk, served with a 200, and drew nothing.

`web/e2e/report/` is excluded: it is Playwright's own generated output.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from xml.parsers import expat

REPO = Path(__file__).resolve().parents[1]

# Directories that hold somebody else's files, or generated ones.
SKIP = {
    ".cache",
    ".git",
    ".venv",
    "assets",
    "bin",
    "dist",
    "node_modules",
    "obj",
    "report",
    "vendor",
}


def parse(path: Path) -> None:
    """Raise `ExpatError` unless `path` is well-formed XML.

    expat directly rather than `minidom` or `ElementTree`: this asks one
    question -- does it parse -- and wants no tree back, and the two DOM
    front-ends are both flagged as parsers of untrusted input.  These files are
    the repository's own, but the narrower call is the honest one anyway.
    Entity expansion is off, which is the actual thing those rules are about.
    """
    parser = expat.ParserCreate()
    parser.DefaultHandler = lambda _data: None
    parser.Parse(path.read_bytes(), True)


def committed_svgs() -> list[Path]:
    return sorted(
        p
        for p in REPO.rglob("*.svg")
        if not SKIP.intersection(p.relative_to(REPO).parts)
    )


class EverySvgParses(unittest.TestCase):
    def test_the_repository_has_at_least_the_favicon(self):
        # A rglob that silently matched nothing would make the test below pass
        # for the wrong reason.
        names = [p.name for p in committed_svgs()]
        assert "favicon.svg" in names, f"favicon.svg is gone; found {names}"

    def test_every_svg_is_well_formed_xml(self):
        for path in committed_svgs():
            with self.subTest(svg=str(path.relative_to(REPO))):
                try:
                    parse(path)
                except expat.ExpatError as exc:
                    rel = path.relative_to(REPO)
                    msg = (
                        f"{rel} is not well-formed XML and will render as "
                        f"nothing at all: {exc}. A doubled hyphen inside an "
                        f"XML comment is the usual cause here."
                    )
                    raise AssertionError(msg) from exc
