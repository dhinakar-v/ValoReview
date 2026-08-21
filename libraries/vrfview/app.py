"""
The window, and the router between its two pages.

One `CTk` root holds the match list and, when a card is opened, the viewer.
The pages are not destroyed and recreated on every navigation -- the list is
built once and hidden, because rescanning a library and rebuilding a hundred
cards to go back one screen is work nobody asked for -- but a viewer *is*
discarded when it is left, because it owns a frame loop, a clock and possibly
199,180 positions, and keeping a stack of those alive is how a viewer becomes
a memory leak with a back button.

Loading a replay is the same four steps everywhere
--------------------------------------------------
`open_replay` is read -> infer -> name, in that order and for the same reasons
`scripts/vrf_view.py` gives: `infer` cross-checks its team split against the
codenames, and `names` needs them to name anybody.  Positions are *not* decoded
here; the viewer offers a button for that, because four minutes before the
first frame is not an opening.

A replay that fails to load is a message, not a traceback
---------------------------------------------------------
The list already knows which files it could not read; a file that parses in the
scanner and then fails here is rarer and worth saying out loud, so the router
shows the error on the list page and stays there.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from vrf_reader import VrfError
from vrfhome import cards, scan
from vrfview import art as art_mod
from vrfview import infer, loader, names, theme
from vrfview.images import ImageCache, Visuals
from vrfview.viewer import Session, ViewerPage

if TYPE_CHECKING:
    from vrfview.model import Replay

WINDOW_TITLE = "Valorant replay analyzer"
WINDOW_SIZE = "1360x860"
MIN_SIZE = (1100, 700)


def open_replay(path: str | Path, catalog=None) -> Replay:
    """Read, infer, then name -- the order the pipeline documents."""
    return names.resolve(infer.annotate(loader.load(path)), catalog)


class ReplayApp(ctk.CTk):
    """The application window: match list, viewer, and the way back."""

    def __init__(
        self,
        result: scan.ScanResult,
        visuals: Visuals,
        catalog=None,
    ):
        super().__init__()
        self.result = result
        self.visuals = visuals
        self.catalog = catalog
        self.viewer: ViewerPage | None = None

        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_SIZE)
        self.configure(fg_color=theme.APP_BG)

        self.list_page = cards.MatchListPage(
            self,
            result,
            on_open=self.show_replay,
            thumbnails=cards.Thumbnails(visuals.art),
        )
        self.list_page.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- navigation ------------------------------------------------------
    def show_replay(self, card: scan.MatchCard) -> None:
        """Open one card's replay, or say on the list why it could not."""
        try:
            replay = open_replay(card.path, self.catalog)
        except (VrfError, OSError, ValueError) as exc:
            self.list_page.provenance.configure(
                text=f"{card.file_name}: {exc}",
                text_color=theme.ACCENT_B,
            )
            return

        self.list_page.pack_forget()
        session = Session(
            replay=replay,
            path=Path(card.path),
            visuals=self.visuals,
            catalog=self.catalog,
        )
        self.viewer = ViewerPage(self, session, on_back=self.show_list)
        self.viewer.pack(fill="both", expand=True)

    def show_list(self) -> None:
        """Leave the viewer and destroy it; the list was never taken down."""
        if self.viewer is not None:
            self.viewer.stop()
            self.viewer.destroy()
            self.viewer = None
        self.list_page.pack(fill="both", expand=True)

    def _on_close(self) -> None:
        if self.viewer is not None:
            self.viewer.stop()
        self.destroy()


def run(
    result: scan.ScanResult,
    art: art_mod.ArtCache | None = None,
    catalog=None,
) -> int:
    """Open the app on the match list and block until it closes."""
    ctk.set_appearance_mode("dark")
    visuals = Visuals.make(art if art is not None else art_mod.ArtCache(), ImageCache())
    ReplayApp(result, visuals, catalog).mainloop()
    return 0
