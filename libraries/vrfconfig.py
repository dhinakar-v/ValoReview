"""
Where the replay library lives, and how that was decided.

One setting, `DEMO_PATH`: the directory the match list scans for `.vrf` files.
It resolves from the real environment first, then from the nearest `.env`, and
finally to `Demos/` relative to the working directory, so a fresh checkout with
no `.env` at all still finds the captures the repository already expects there.

Why this is not python-dotenv
-----------------------------
The brief asks for `python-dotenv`, and `dotenv_values()` would implement
exactly the contract above -- read the file, mutate nothing, let the real
environment win.  `libraries/envfile.py` already implements that contract, and
`oodlefind` and `valapi` already read `.env` through it.  Adopting the package
here would have put two readers of one file in one process, differing only in
which module they live in, so the dependency was declined and this module calls
`envfile` instead.  The app's other two dependencies (customtkinter, Pillow)
buy things the standard library does not have; this one would not have.

Nothing here mutates `os.environ`, and nothing here touches the disk beyond
reading `.env`: a `DEMO_PATH` that does not exist resolves normally and reports
`exists = False`, because an empty or missing library is the match list's
empty state, not an error at import time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import envfile

DEMO_PATH_KEY = "DEMO_PATH"

# Relative on purpose: the repository keeps its captures in Demos/, which is
# gitignored, so a checkout with no configuration at all still points at the
# right place when run from the project root.
DEFAULT_DEMO_PATH = "Demos"

SOURCE_ENVIRON = "DEMO_PATH from the environment"
SOURCE_ENV_FILE = "DEMO_PATH from {path}"
SOURCE_DEFAULT = f"default {DEFAULT_DEMO_PATH}/ (DEMO_PATH is unset)"


@dataclass(frozen=True)
class DemoRoot:
    """A resolved replay directory, and the sentence that says where it came from."""

    path: Path
    source: str

    @property
    def exists(self) -> bool:
        return self.path.is_dir()

    @property
    def described(self) -> str:
        """One provenance line, in the shape the UI panels want."""
        state = "" if self.exists else " (no such directory)"
        return f"{self.path}{state} -- {self.source}"


def demo_root(override: str | None = None) -> DemoRoot:
    """
    The replay directory, with `override` (a command-line flag) winning outright.

    The search order is the same one `envfile` documents -- an explicit
    argument, then the real environment, then the nearest `.env`, then the
    default -- and whichever answered is reported rather than assumed, because
    "the list is empty" and "the list is somewhere else" look identical
    otherwise.
    """
    if override:
        return DemoRoot(Path(override).expanduser(), "DEMO_PATH from the command line")

    from_environ = os.environ.get(DEMO_PATH_KEY)
    if from_environ:
        return DemoRoot(Path(from_environ).expanduser(), SOURCE_ENVIRON)

    path = envfile.find_upwards(envfile.ENV_FILENAME)
    if path is not None and path.is_file():
        value = envfile.read(path).get(DEMO_PATH_KEY)
        if value:
            return DemoRoot(
                Path(value).expanduser(),
                SOURCE_ENV_FILE.format(path=path),
            )

    return DemoRoot(Path(DEFAULT_DEMO_PATH), SOURCE_DEFAULT)


def replays(override: str | None = None) -> list[Path]:
    """Every `.vrf` under the replay directory, sorted, or [] if it is absent."""
    root = demo_root(override)
    if not root.exists:
        return []
    return sorted(p for p in root.path.glob("*.vrf") if p.is_file())
