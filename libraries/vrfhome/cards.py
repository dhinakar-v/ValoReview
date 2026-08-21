"""
Page 1: the match list, in CustomTkinter.

Ten cards a page, sorted by date, filtered by map or day -- the brief's page,
built on `vrfhome.scan`, which did every file read before this module drew
anything.  Nothing here touches a `.vrf`: a card is handed the facts and asks
only how to show them.

Two things the brief asked for that this page states rather than invents
--------------------------------------------------------------------------
The `WIN` / `LOSS` badge **cannot be built** -- there is no local player in the
file and the teams are A and B by inference, not by side -- so every card
carries `scan.RESULT_NOT_IN_FILE` in the badge's place.  An empty space there
would read as a draw, or as a bug; the sentence reads as what it is.

In exchange the card says something the brief never asked for and the user
actually needs: **whether this capture can be drawn at all**.  It is knowable
from a plain chunk, and on a typical library it is true of about one file in
five.  Since the schematic was removed there is no half-answer for the other
four, so the page shows the playable ones by default and says how many it is
holding back; SHOW ALL reveals them, each carrying the reason.  A list that
quietly drops eighty of a hundred files would be worse than the schematic ever
was.

The second chip is that capture's **preparation state**, from
`vrfhome.prewarm`: a decode is four minutes the first time and instant every
time after, so the difference between QUEUED and READY is the difference
between waiting and not, and it belongs on the card rather than being
discovered after the click.

Art is optional, here as everywhere
-----------------------------------
The thumbnail is `assets/maps/<Map>/listview.png` through `vrfview.art`, which
means a checkout with no `assets/` shows a lettered placeholder and loses
nothing else.  Pillow does the scaling -- this is the reason Phase 4 adopted
it -- so a 456x100 banner becomes a 182x40 thumbnail without Tk's whole-number
subsampling.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from vrfhome import prewarm, scan
from vrfview import art, theme

THUMB_SIZE = (182, 40)

FONT_TITLE = ("Impact", 26)
FONT_CARD = ("Arial", 15, "bold")
FONT_BODY = ("Arial", 12)
FONT_SMALL = ("Arial", 11)

SHOW_ALL = "SHOW ALL"
SHOW_PLAYABLE = "PLAYABLE ONLY"

UNSUPPORTED_CHIP = "UNSUPPORTED BUILD"

# How the preparation states colour.  READY is the only one that is good news
# and FAILED the only one that is bad; QUEUED and PREPARING are neither, so
# they take the muted default rather than a colour that implies a verdict.
_CHIP_COLOUR = {
    prewarm.READY: theme.ACCENT_OK,
    prewarm.FAILED: theme.ACCENT_B,
}


def chip_colour(state: str) -> str:
    """The colour one preparation state is shown in."""
    return _CHIP_COLOUR.get(state, theme.TEXT_MUTED)


EMPTY_TITLE = "No replays here"
EMPTY_HINT = (
    "Set DEMO_PATH in .env to the folder VALORANT writes .vrf files to, "
    "or drop captures into Demos/."
)


class Thumbnails:
    """
    One `CTkImage` per map, made once and kept.

    A page shows ten cards and a library has eighteen maps, so caching by map
    name is enough to make paging free after the first pass over the library.
    """

    def __init__(self, cache: art.ArtCache | None = None):
        self.art = cache if cache is not None else art.load()
        self._made: dict[str, ctk.CTkImage | None] = {}

    def get(self, map_path: str) -> ctk.CTkImage | None:
        """The map's listview banner, or None when there is no art for it."""
        if map_path not in self._made:
            self._made[map_path] = self._make(map_path)
        return self._made[map_path]

    def _make(self, map_path: str) -> ctk.CTkImage | None:
        found = self.art.map_art(map_path)
        path = found.listview if found else None
        if path is None or not Path(path).is_file():
            return None
        try:
            image = Image.open(path).convert("RGB")
        except OSError:
            return None
        return ctk.CTkImage(light_image=image, dark_image=image, size=THUMB_SIZE)


class MatchCardRow(ctk.CTkFrame):
    """
    One replay: thumbnail, map, date, duration, and what is not in the file.

    The whole row is the click target, children included -- a card whose text
    is not clickable is a card that feels broken -- so every child gets the
    same two bindings the frame does.
    """

    def __init__(
        self,
        master,
        card: scan.MatchCard,
        on_open: Callable[[scan.MatchCard], None],
        thumbnails: Thumbnails | None = None,
        status: prewarm.Status | None = None,
    ):
        super().__init__(
            master,
            fg_color=theme.CARD_BG,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=6,
        )
        self.card = card
        self.on_open = on_open
        self.status_chip: ctk.CTkLabel | None = None
        self.grid_columnconfigure(1, weight=1)

        self._thumbnail(thumbnails)
        self._facts()
        self._badges(status)
        self._bind_all(self)

    def set_status(self, status: prewarm.Status) -> None:
        """Repaint the preparation chip in place, without rebuilding the row."""
        if self.status_chip is None:
            return
        self.status_chip.configure(
            text=status.label,
            text_color=chip_colour(status.state),
        )

    # -- pieces ----------------------------------------------------------
    def _thumbnail(self, thumbnails: Thumbnails | None) -> None:
        image = thumbnails.get(self.card.map_path) if thumbnails else None
        if image is not None:
            ctk.CTkLabel(self, text="", image=image).grid(
                row=0,
                column=0,
                rowspan=2,
                padx=(10, 14),
                pady=10,
            )
            return
        # No art cache, or a map it does not carry: a lettered plate, which is
        # visibly a placeholder rather than a thumbnail that failed to load.
        ctk.CTkLabel(
            self,
            text=(self.card.map_name or "?")[:1].upper(),
            width=THUMB_SIZE[0],
            height=THUMB_SIZE[1],
            fg_color=theme.TOOLTIP_BG,
            text_color=theme.TEXT_MUTED,
            font=FONT_TITLE,
            corner_radius=4,
        ).grid(row=0, column=0, rowspan=2, padx=(10, 14), pady=10)

    def _facts(self) -> None:
        title = self.card.map_name or self.card.file_name
        ctk.CTkLabel(
            self,
            text=title.upper(),
            font=FONT_CARD,
            text_color=theme.TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(10, 0))

        detail = f"{self.card.recorded}   ·   {self.card.duration}"
        if self.card.rounds:
            detail += f"   ·   {self.card.rounds} rounds"
        if self.card.players:
            detail += f"   ·   {self.card.players} players"
        ctk.CTkLabel(
            self,
            text=detail,
            font=FONT_BODY,
            text_color=theme.TEXT_MUTED,
            anchor="w",
        ).grid(row=1, column=1, sticky="w", pady=(0, 10))

    def _badges(self, status: prewarm.Status | None) -> None:
        column = ctk.CTkFrame(self, fg_color="transparent")
        column.grid(row=0, column=2, rowspan=2, padx=(12, 12), pady=10, sticky="e")

        if not self.card.readable:
            self._chip(column, "UNREADABLE", theme.ACCENT_B)
            ctk.CTkLabel(
                column,
                text=self.card.error[:70],
                font=FONT_SMALL,
                text_color=theme.TEXT_MUTED,
                anchor="e",
            ).pack(anchor="e")
            return

        self._chip(column, scan.RESULT_NOT_IN_FILE, theme.TEXT_MUTED)
        if not self.card.positions_available:
            # Only ever visible under SHOW ALL, and it is the whole reason this
            # card was held back, so it says so rather than showing a state.
            self._chip(column, UNSUPPORTED_CHIP, theme.TEXT_MUTED)
            ctk.CTkLabel(
                column,
                text=self.card.positions_note,
                font=FONT_SMALL,
                text_color=theme.TEXT_MUTED,
                anchor="e",
            ).pack(anchor="e")
            return

        found = status or prewarm.Status()
        self.status_chip = ctk.CTkLabel(
            column,
            text=found.label,
            font=FONT_SMALL,
            text_color=chip_colour(found.state),
            fg_color=theme.TOOLTIP_BG,
            corner_radius=4,
            padx=8,
            pady=2,
        )
        self.status_chip.pack(anchor="e", pady=2)

    def _chip(self, master, text: str, colour: str) -> None:
        ctk.CTkLabel(
            master,
            text=text,
            font=FONT_SMALL,
            text_color=colour,
            fg_color=theme.TOOLTIP_BG,
            corner_radius=4,
            padx=8,
            pady=2,
        ).pack(anchor="e", pady=2)

    # -- behaviour -------------------------------------------------------
    def _bind_all(self, widget) -> None:
        widget.bind("<Button-1>", self._clicked)
        widget.bind("<Enter>", self._enter)
        widget.bind("<Leave>", self._leave)
        for child in widget.winfo_children():
            self._bind_all(child)

    def _clicked(self, _event=None) -> None:
        # An unreadable file has nothing to open; the card already says why.
        if self.card.readable:
            self.on_open(self.card)

    def _enter(self, _event=None) -> None:
        self.configure(fg_color=theme.CARD_HOVER)

    def _leave(self, _event=None) -> None:
        self.configure(fg_color=theme.CARD_BG)


class MatchListPage(ctk.CTkFrame):
    """
    The page: filter bar, ten cards, a pager, and a line saying where it looked.

    Sorting, filtering and paging are `vrfhome.scan`'s pure functions; this
    class owns only the three pieces of interface state (`page`, the two filter
    strings and the sort direction) and redraws the list from them.  Redrawing
    the whole list rather than diffing it is the same judgement `state_at`
    makes in the viewer: ten rows is nothing, and a view rebuilt from state
    cannot drift out of step with it.
    """

    def __init__(
        self,
        master,
        result: scan.ScanResult,
        on_open: Callable[[scan.MatchCard], None],
        thumbnails: Thumbnails | None = None,
        prewarmer: prewarm.Prewarmer | None = None,
    ):
        super().__init__(master, fg_color=theme.APP_BG)
        self.result = result
        self.on_open = on_open
        self.thumbnails = thumbnails if thumbnails is not None else Thumbnails()
        self.prewarmer = prewarmer

        self.page_number = 1
        self.descending = False
        self.show_all = False
        # Path -> the row currently showing it, so a status change repaints one
        # chip instead of rebuilding ten rows thirty times a minute.
        self._rows: dict[Path, MatchCardRow] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_list()
        self._build_footer()
        self.refresh()

    # -- construction ----------------------------------------------------
    def _build_header(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        bar.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            bar,
            text="MATCHES",
            font=FONT_TITLE,
            text_color=theme.TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        maps = ["All maps", *scan.maps_present(self.result.cards)]
        self.map_menu = ctk.CTkOptionMenu(
            bar,
            values=maps,
            width=140,
            command=self._map_chosen,
            fg_color=theme.CARD_BG,
            button_color=theme.BORDER,
            text_color=theme.TEXT_PRIMARY,
        )
        self.map_menu.grid(row=0, column=1, padx=(0, 8))

        # No textvariable: CustomTkinter hides an entry's placeholder as soon as
        # one is attached, and the placeholder is what says what to type here.
        self.date_entry = ctk.CTkEntry(
            bar,
            placeholder_text="date, e.g. 2026-06",
            width=160,
            fg_color=theme.CARD_BG,
            border_color=theme.BORDER,
            text_color=theme.TEXT_PRIMARY,
        )
        self.date_entry.grid(row=0, column=2, padx=(0, 8))
        self.date_entry.bind("<KeyRelease>", lambda _e: self._filters_changed())

        self.sort_button = ctk.CTkButton(
            bar,
            text="OLDEST FIRST",
            width=140,
            command=self._toggle_sort,
            fg_color=theme.CARD_BG,
            hover_color=theme.CARD_HOVER,
            border_color=theme.BORDER,
            border_width=1,
            text_color=theme.TEXT_PRIMARY,
        )
        self.sort_button.grid(row=0, column=4, sticky="e")

        # Offered only when something is actually being held back, so the
        # button never invites a user to reveal an empty set.
        if self.result.hidden:
            self.filter_button = ctk.CTkButton(
                bar,
                text=SHOW_ALL,
                width=130,
                command=self._toggle_filter,
                fg_color=theme.CARD_BG,
                hover_color=theme.CARD_HOVER,
                border_color=theme.BORDER,
                border_width=1,
                text_color=theme.TEXT_MUTED,
            )
            self.filter_button.grid(row=0, column=5, sticky="e", padx=(8, 0))

    def _build_list(self) -> None:
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=16)
        self.list_frame.grid_columnconfigure(0, weight=1)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 14))
        footer.grid_columnconfigure(1, weight=1)

        pager = ctk.CTkFrame(footer, fg_color="transparent")
        pager.grid(row=0, column=0, sticky="w")
        self.prev_button = ctk.CTkButton(
            pager,
            text="<",
            width=36,
            command=lambda: self._go(self.page_number - 1),
            fg_color=theme.CARD_BG,
            hover_color=theme.CARD_HOVER,
            text_color=theme.TEXT_PRIMARY,
        )
        self.prev_button.pack(side="left", padx=(0, 6))
        self.page_label = ctk.CTkLabel(
            pager,
            text="",
            font=FONT_BODY,
            text_color=theme.TEXT_MUTED,
            width=110,
        )
        self.page_label.pack(side="left")
        self.next_button = ctk.CTkButton(
            pager,
            text=">",
            width=36,
            command=lambda: self._go(self.page_number + 1),
            fg_color=theme.CARD_BG,
            hover_color=theme.CARD_HOVER,
            text_color=theme.TEXT_PRIMARY,
        )
        self.next_button.pack(side="left", padx=(6, 0))

        # Where the list came from, verbatim from the scan.  A user who sees
        # nothing needs to know which directory was empty.
        self.provenance = ctk.CTkLabel(
            footer,
            text=self.result.described,
            font=FONT_SMALL,
            text_color=theme.TEXT_MUTED,
            anchor="e",
        )
        self.provenance.grid(row=0, column=1, sticky="e")

        # How far the background decode has got.  Its own line rather than
        # appended to the provenance one, which is a fact about the scan and
        # does not change while the app is open.
        self.progress = ctk.CTkLabel(
            footer,
            text=self.prewarmer.described if self.prewarmer is not None else "",
            font=FONT_SMALL,
            text_color=theme.TEXT_MUTED,
            anchor="e",
        )
        self.progress.grid(row=1, column=1, sticky="e")

    # -- state -----------------------------------------------------------
    @property
    def visible(self) -> list[scan.MatchCard]:
        """The cards the current filter and sort leave, before paging."""
        chosen = self.map_menu.get()
        pool = self.result.cards if self.show_all else self.result.playable
        return scan.sort_cards(
            scan.filter_cards(
                pool,
                map_name="" if chosen.startswith("All") else chosen,
                date=self.date_entry.get(),
            ),
            descending=self.descending,
        )

    def refresh(self) -> None:
        """Redraw the visible page from the current filter, sort and page."""
        for child in self.list_frame.winfo_children():
            child.destroy()

        cards = self.visible
        total = scan.page_count(cards)
        self.page_number = min(max(1, self.page_number), total)
        rows = scan.page(cards, self.page_number)

        self._rows.clear()
        if not rows:
            self._empty_state()
        for row, card in enumerate(rows):
            widget = MatchCardRow(
                self.list_frame,
                card,
                self.on_open,
                self.thumbnails,
                self._status_of(card),
            )
            widget.grid(row=row, column=0, sticky="ew", pady=4)
            self._rows[Path(card.path)] = widget

        self.page_label.configure(text=f"page {self.page_number} of {total}")
        self.prev_button.configure(state="normal" if self.page_number > 1 else "disabled")
        self.next_button.configure(
            state="normal" if self.page_number < total else "disabled",
        )

    def _status_of(self, card: scan.MatchCard):
        """The card's preparation state, or None where nothing is preparing."""
        if self.prewarmer is None or not card.playable:
            return None
        return self.prewarmer.status(card.path)

    def set_status(self, path, status) -> None:
        """
        Repaint one card's chip.  Called from the app's Tk thread only.

        A path that is not on the current page is neither an error nor a
        missed update: the page reads every status again when it is next
        drawn, so a card scrolled past catches up on its own.
        """
        row = self._rows.get(Path(path))
        if row is not None:
            row.set_status(status)
        if self.prewarmer is not None:
            self.progress.configure(text=self.prewarmer.described)

    def _toggle_filter(self) -> None:
        self.show_all = not self.show_all
        self.filter_button.configure(
            text=SHOW_PLAYABLE if self.show_all else SHOW_ALL,
            text_color=theme.TEXT_PRIMARY if self.show_all else theme.TEXT_MUTED,
        )
        self.page_number = 1
        self.refresh()

    def _empty_state(self) -> None:
        holder = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        holder.grid(row=0, column=0, sticky="ew", pady=40)
        ctk.CTkLabel(
            holder,
            text=EMPTY_TITLE if not self.result.cards else "Nothing matches that filter",
            font=FONT_CARD,
            text_color=theme.TEXT_PRIMARY,
        ).pack()
        ctk.CTkLabel(
            holder,
            text=EMPTY_HINT if not self.result.cards else "Clear the map or date filter.",
            font=FONT_BODY,
            text_color=theme.TEXT_MUTED,
            wraplength=520,
        ).pack(pady=(6, 0))

    # -- events ----------------------------------------------------------
    def _map_chosen(self, _value: str) -> None:
        self._filters_changed()

    def _filters_changed(self) -> None:
        self.page_number = 1
        self.refresh()

    def _toggle_sort(self) -> None:
        self.descending = not self.descending
        self.sort_button.configure(
            text="NEWEST FIRST" if self.descending else "OLDEST FIRST",
        )
        self.page_number = 1
        self.refresh()

    def _go(self, number: int) -> None:
        self.page_number = number
        self.refresh()
