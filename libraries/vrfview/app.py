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
here; the viewer offers a button for that, because a decode before the
first frame is not an opening.

The decode happens anyway -- earlier, and in the background
----------------------------------------------------------------
`vrfhome.prewarm` starts once the window is up and decodes the playable
captures one at a time into `vrfview.positioncache`, so by the time a card is
clicked the decode has usually already happened and `tracks.attach` finds it
rather than doing it.  It is paused whenever a viewer is open: the viewer's own
DECODE POSITIONS button is a request the user made, and it must not queue
behind twenty they did not.  Every status arrives on a worker thread and is
marshalled onto Tk with `after`, the same rule the viewer's decode follows.

A replay that fails to load is a message, not a traceback
---------------------------------------------------------
The list already knows which files it could not read; a file that parses in the
scanner and then fails here is rarer and worth saying out loud, so the router
shows the error on the list page and stays there.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from vrf_reader import VrfError
from vrfhome import cards, prewarm, scan
from vrfview import art as art_mod
from vrfview import pipeline, theme
from vrfview.images import ImageCache, Visuals
from vrfview.viewer import Session, ViewerPage

WINDOW_TITLE = "Valorant replay analyzer"

# How long the background decode waits for the window to appear before it
# starts competing with it for the CPU.
PREWARM_DELAY_MS = 800
WINDOW_SIZE = "1360x860"
MIN_SIZE = (1100, 700)


# The load pipeline moved to vrfview.pipeline so it is not the toolkit's
# property -- it is the same four steps in the same order, and this name is
# kept because it is what the window calls.
open_replay = pipeline.open_replay


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

        self.prewarmer = prewarm.Prewarmer(result.cards, on_change=self._prepared)
        self.list_page = cards.MatchListPage(
            self,
            result,
            on_open=self.show_replay,
            thumbnails=cards.Thumbnails(visuals.art),
            prewarmer=self.prewarmer,
        )
        self.list_page.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # After the window has painted, not during construction: the first
        # decode competes for the CPU and the list should be on screen before
        # it starts.
        self.after(PREWARM_DELAY_MS, self.prewarmer.start)

    # -- background preparation ------------------------------------------
    def _prepared(self, path, status) -> None:
        """
        A capture changed state.  Called on the worker thread, never Tk's.

        Nothing here touches a widget; `after` hands the whole thing to the Tk
        thread, because a chip reconfigured from a worker fails in ways that
        look like a layout bug.

        `after` itself is the part that can fail.  Closing the window tears
        down the interpreter's Tk half while the worker is still inside a
        block, and registering a callback against a dead one raises
        `RuntimeError` *on the worker thread*, where nothing is catching it --
        the queue dies and the user gets a traceback on the way out of the
        app.  A window that has gone simply has nothing to tell, so this stops
        the queue instead.
        """
        try:
            self.after(0, self._show_status, path, status)
        except (RuntimeError, tk.TclError):
            self.prewarmer.stop()

    def _show_status(self, path, status) -> None:
        try:
            if self.list_page.winfo_exists():
                self.list_page.set_status(path, status)
        except tk.TclError:
            # The page was destroyed between the `after` and its callback.
            self.prewarmer.stop()

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

        # The viewer may want to decode this very capture; two decodes at once
        # would halve both.  The queue picks up again on the way back.
        self.prewarmer.pause()
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
        # A viewer that decoded its own capture has just filled a cache entry,
        # so refresh before resuming: the chip should say READY the moment the
        # card is visible again.
        self.list_page.refresh()
        self.prewarmer.resume()

    def _on_close(self) -> None:
        if self.viewer is not None:
            self.viewer.stop()
        # Asked, not waited for: the worker checks between blocks, so it drops
        # out within a second or so, and it is a daemon thread besides.
        self.prewarmer.stop()
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
