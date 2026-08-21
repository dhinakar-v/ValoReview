"""
The two player panels, mirrored, one team each.

The brief's row is portrait, HP, shield, name, ult points, HP bar.  Three of
those six are not in this file at any version -- health, armour and credits are
never replicated to a spectator recording -- so they keep their slot and show
`NOT_IN_FILE` rather than a plausible 100.  An invented health bar is the exact
failure this project spends most of its docstrings avoiding.

What a row can actually say
---------------------------
* the agent, from the pawn's own archetype path, named through the catalogue
  (`Player.identity` falls back agent -> codename -> label, so a row always has
  something true to show);
* the label (`A1`..`B5`), which is what the file supports instead of a name --
  there are no player names in a `.vrf`;
* running K/D at this instant, from `Snapshot.kd`;
* alive or dead, and dead is drawn as dimmed rather than removed, because a
  panel that shrinks mid-round loses the reader's place;
* whether the ultimate has been used this round -- `Snapshot.ulted_this_round`
  is a fact from the event stream, unlike ult *points*, which are not.

Rows are built once and updated
-------------------------------
Ten rows at 30 fps is 300 widget rebuilds a second if a redraw destroys them,
which CustomTkinter will not survive.  Each row is constructed once and
`render` only reconfigures text and colour -- the same discipline the canvas
views follow, for the same reason.

Team A and team B, not attackers and defenders
----------------------------------------------
Which team attacked is not recoverable from the file, so the headers say TEAM A
and TEAM B and the two accents mean exactly that.  `infer` derives the split
from the kill graph and cross-checks it against the agents on the wire; it is
an inference, and the panel header says so when asked.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from vrfview import theme
from vrfview.images import CIRCLE, Visuals

if TYPE_CHECKING:
    from vrfview.art import ArtCache
    from vrfview.model import Player, Replay
    from vrfview.state import Snapshot

PORTRAIT_PX = 46

# A row is exactly this tall.  Without it the rows share out whatever height
# the panel has, and five players in a tall window become five banners.
ROW_HEIGHT = 62

NOT_IN_FILE = "--"
NOT_IN_FILE_HINT = "HP / armour / credits are not in the file"

FONT_TEAM = ("Impact", 20)
FONT_NAME = ("Arial", 13, "bold")
FONT_SUB = ("Arial", 11)
FONT_STAT = ("Consolas", 12)

# How far a dead row is faded toward the background.
DEAD_FADE = 0.55


def agent_art_by_name(cache: ArtCache, name: str):
    """
    Art for an agent named rather than identified by UUID.

    `ArtCache.agent_art` keys on the UUID, which is what a loadout slot
    carries.  A `Player` has no UUID -- its agent is *read* from the pawn's
    archetype codename and named through the catalogue -- so the only join left
    is the display name, and it is exact on both sides because both come from
    the same published catalogue.
    """
    if not name:
        return None
    wanted = name.lower()
    for entry in cache.agents.values():
        if entry.name.lower() == wanted:
            return entry
    return None


class PlayerRow(ctk.CTkFrame):
    """One player: portrait, identity, K/D, ult, and the three absent numbers."""

    def __init__(
        self,
        master,
        player: Player,
        visuals: Visuals,
        *,
        mirrored: bool = False,
    ):
        super().__init__(
            master,
            fg_color=theme.CARD_BG,
            corner_radius=6,
            height=ROW_HEIGHT,
        )
        self.grid_propagate(False)
        self.player = player
        self.mirrored = mirrored
        self.colour = theme.team_colour(player.team)

        # Mirrored rows put the portrait on the outside edge, as the brief's
        # sketch does: the two panels face each other across the map.
        portrait_column = 2 if mirrored else 0
        text_anchor = "e" if mirrored else "w"
        self.grid_columnconfigure(1, weight=1)
        # The row's height is fixed, so its two text rows share it evenly
        # rather than each asking for whatever the panel happens to have.
        self.grid_rowconfigure((0, 1), weight=1, uniform="row")

        self.portrait = ctk.CTkLabel(
            self,
            text="",
            width=PORTRAIT_PX,
            height=PORTRAIT_PX,
            fg_color=theme.TOOLTIP_BG,
            corner_radius=PORTRAIT_PX // 2,
        )
        self.portrait.grid(row=0, column=portrait_column, rowspan=2, padx=8, pady=6)
        self._set_portrait(visuals)

        self.name = ctk.CTkLabel(
            self,
            text=player.identity,
            font=FONT_NAME,
            text_color=theme.TEXT_PRIMARY,
            anchor=text_anchor,
        )
        self.name.grid(row=0, column=1, sticky="ew", padx=4, pady=(6, 0))

        self.detail = ctk.CTkLabel(
            self,
            text="",
            font=FONT_SUB,
            text_color=theme.TEXT_MUTED,
            anchor=text_anchor,
        )
        self.detail.grid(row=1, column=1, sticky="ew", padx=4, pady=(0, 6))

        # The team's colour as a bar down the row's own edge, so a row read on
        # its own still says which side it belongs to.
        self.stripe = ctk.CTkFrame(self, width=3, fg_color=self.colour)
        self.stripe.grid(
            row=0,
            column=0 if mirrored else 2,
            rowspan=2,
            sticky="ns",
            padx=(0, 0),
        )

    def _set_portrait(self, visuals: Visuals) -> None:
        entry = agent_art_by_name(visuals.art, self.player.agent)
        path = entry.icon if entry is not None else None
        image = visuals.images.ctk(path, (PORTRAIT_PX, PORTRAIT_PX), CIRCLE)
        if image is not None:
            self.portrait.configure(image=image, text="")
            return
        # No art, or an agent the cache does not carry: the label's own letter,
        # which is visibly a placeholder rather than a portrait that failed.
        self.portrait.configure(
            text=self.player.label,
            font=FONT_STAT,
            text_color=theme.TEXT_MUTED,
        )

    def render(self, snap: Snapshot) -> None:
        """Reconfigure this row for one instant.  No widgets are made here."""
        alive = snap.is_alive(self.player.actor_id)
        kills, deaths = snap.kd.get(self.player.actor_id, (0, 0))
        ulted = self.player.actor_id in snap.ulted_this_round

        name_colour = (
            theme.TEXT_PRIMARY
            if alive
            else theme.blend(theme.TEXT_PRIMARY, theme.APP_BG, DEAD_FADE)
        )
        self.name.configure(text=self.player.identity, text_color=name_colour)
        self.stripe.configure(
            fg_color=(
                self.colour if alive else theme.blend(self.colour, theme.APP_BG, DEAD_FADE)
            ),
        )

        # Short enough to fit the panel at its narrowest.  The three absent
        # numbers are stated once per panel, not once per row: repeating
        # "HP --" ten times crowds out the facts that are real.
        state = "alive" if alive else "dead"
        ult = "  ULT" if ulted else ""
        self.detail.configure(
            text=f"{self.player.label}   {kills}/{deaths}   {state}{ult}",
        )


class TeamPanel(ctk.CTkFrame):
    """One team's five rows, plus a header saying which team and how it scored."""

    def __init__(
        self,
        master,
        replay: Replay,
        team: str,
        visuals: Visuals,
        *,
        mirrored: bool = False,
    ):
        super().__init__(master, fg_color=theme.APP_BG)
        self.replay = replay
        self.team = team
        self.mirrored = mirrored
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 8))
        header.grid_columnconfigure(1, weight=1)

        self.title = ctk.CTkLabel(
            header,
            text=f"TEAM {team}",
            font=FONT_TEAM,
            text_color=theme.team_colour(team),
        )
        self.title.grid(row=0, column=0 if not mirrored else 2)
        self.score = ctk.CTkLabel(
            header,
            text="0",
            font=FONT_TEAM,
            text_color=theme.TEXT_PRIMARY,
        )
        self.score.grid(row=0, column=2 if not mirrored else 0)
        ctk.CTkLabel(
            header,
            text="inferred split",
            font=FONT_SUB,
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=1)

        self.rows = [
            PlayerRow(self, player, visuals, mirrored=mirrored)
            for player in replay.players
            if player.team == team
        ]
        for index, row in enumerate(self.rows, start=1):
            row.grid(row=index, column=0, sticky="ew", padx=6, pady=3)

        # One line saying what the whole column cannot show, once, instead of
        # repeating "not in file" beside three numbers in every row.
        ctk.CTkLabel(
            self,
            text=NOT_IN_FILE_HINT,
            font=FONT_SUB,
            text_color=theme.TEXT_MUTED,
        ).grid(row=len(self.rows) + 1, column=0, pady=(8, 4))

        # Whatever height is left over goes below the rows, not into them.
        self.grid_rowconfigure(len(self.rows) + 2, weight=1)

    def render(self, snap: Snapshot) -> None:
        a, b = snap.score
        self.score.configure(text=str(a if self.team == "A" else b))
        for row in self.rows:
            row.render(snap)
