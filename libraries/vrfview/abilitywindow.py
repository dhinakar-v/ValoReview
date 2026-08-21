"""
The ability timeline: every cast the replication stream gave up, by round.

A separate `Toplevel` rather than a fourth column, for the same reason
`mapref` is one: the viewer's three columns are the brief's layout and this is
extra.  It is also the only place in the interface with room to say what a
cast *cannot* tell you, and that sentence has to sit next to the list rather
than in a provenance panel two clicks away.

What a row states, and where each half comes from
-------------------------------------------------
    R3  1:12   [icon]  Killjoy  E  Turret   ·  pawn travelled 0 uu

* the round, the time, the agent and the slot are **read**: the round from the
  event stream, the time from the instant the actor's channel opened, and the
  agent and slot from the archetype path of the actor the cast spawned;
* the ability's *name* is read for Q and E and **looked up** for C and X.  Riot
  publishes ability slots as `Ability1`/`Ability2`/`Grenade`/`Ultimate`, and
  `Ability1` and `Ability2` are Q and E in an order that varies by agent, so
  only two of the four can be joined.  `art.AgentArt.ability` is where that is
  decided; the rows here show the icon when it joined and the internal name
  when it did not, and the footer says which is which;
* the travel figure is **measured** off the pawn's own track and is not a
  published range, because no ability range is published anywhere -- not in the
  replay, not in val-content-v1, not in the valorant-api.com manifest.

Most casts have no pawn and therefore no distance, and they say so rather than
showing a zero: `abilities.NO_POSITION` is the sentence, and the reason is that
a thrown projectile does not replicate through the movement RPC at all.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk

from vrf_reader import _fmt_ms
from vrfview import abilities, theme

if TYPE_CHECKING:
    from vrfview.images import Visuals
    from vrfview.model import Replay

ICON_PX = 22
WINDOW_SIZE = "620x680"

FONT_ROUND = ("Impact", 15)
FONT_ROW = ("Arial", 12)
FONT_SLOT = ("Consolas", 12, "bold")
FONT_NOTE = ("Arial", 11)

FOOTER = (
    "Read from the archetype paths of the actors each cast spawned — there is "
    "no ability event in a .vrf.  C and X names come from Riot's catalogue; Q "
    "and E names are Riot's internal ones, because the catalogue publishes "
    "those two in an order that varies by agent.  Distances are measured off "
    "the pawn's own decoded track, not a published range: no ability range "
    "exists in the replay or the catalogue.  A cast with no distance spawned "
    "nothing that moves, so the file says when it happened and never where."
)

EMPTY = (
    "No ability casts were decoded for this replay.\n\n"
    "They arrive with the positions, from the same pass over the replication "
    "stream, so a replay with no positions has none of these either."
)


def show(master: tk.Misc, replay: Replay, visuals: Visuals) -> ctk.CTkToplevel:
    """Open the timeline.  Returns the window so the caller can raise it again."""
    top = ctk.CTkToplevel(master)
    top.title(f"Abilities - {replay.map_name}")
    top.geometry(WINDOW_SIZE)
    top.configure(fg_color=theme.APP_BG)
    top.bind("<Escape>", lambda _e: top.destroy())

    body = ctk.CTkScrollableFrame(top, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=12, pady=(12, 4))
    body.grid_columnconfigure(0, weight=1)

    if not replay.ability_casts:
        ctk.CTkLabel(
            body,
            text=EMPTY,
            font=FONT_ROW,
            text_color=theme.TEXT_MUTED,
            wraplength=540,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=20)
    else:
        _fill(body, replay, visuals)

    ctk.CTkLabel(
        top,
        text=FOOTER,
        font=FONT_NOTE,
        text_color=theme.TEXT_MUTED,
        wraplength=580,
        justify="left",
    ).pack(fill="x", padx=12, pady=(0, 12))
    return top


def _fill(body, replay: Replay, visuals: Visuals) -> None:
    """One heading per round, then that round's casts in the order they were made."""
    row = 0
    for number in sorted({c.round_no for c in replay.ability_casts}):
        ctk.CTkLabel(
            body,
            text=f"ROUND {number}" if number else "BEFORE THE FIRST ROUND",
            font=FONT_ROUND,
            text_color=theme.TEXT_PRIMARY,
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", pady=(14, 4))
        row += 1
        for cast in replay.casts_in(number):
            _row(body, cast, replay, visuals).grid(
                row=row,
                column=0,
                sticky="ew",
                pady=2,
            )
            row += 1


def _row(body, cast, replay: Replay, visuals: Visuals) -> ctk.CTkFrame:
    """One cast, with whatever of it resolved."""
    frame = ctk.CTkFrame(body, fg_color=theme.CARD_BG, corner_radius=6)
    frame.grid_columnconfigure(3, weight=1)

    ctk.CTkLabel(
        frame,
        text=_fmt_ms(cast.t_ms),
        font=("Consolas", 12),
        text_color=theme.TEXT_MUTED,
        width=64,
    ).grid(row=0, column=0, padx=(10, 6), pady=6)

    art = visuals.art.agent_art_by_name(cast.agent)
    published = art.ability(cast.slot) if art is not None else None
    icon = visuals.images.ctk(
        published.icon if published is not None else None,
        (ICON_PX, ICON_PX),
    )
    # Blank rather than lettered when there is no icon: the slot is already in
    # the next column, and a fallback that repeats it makes every Q and E row
    # read "Q  Killjoy  Q".  An empty square here says "no published icon for
    # this slot", which is exactly the true statement.
    ctk.CTkLabel(
        frame,
        text="",
        image=icon,
        width=ICON_PX,
    ).grid(row=0, column=1, padx=(0, 8))

    ctk.CTkLabel(
        frame,
        text=f"{cast.identity}  {cast.slot}",
        font=FONT_SLOT,
        text_color=_colour_for(cast, replay),
        anchor="w",
        width=150,
    ).grid(row=0, column=2, sticky="w")

    # The published name when the slot joined, the internal one when it could
    # not.  Never both, and never a published name for a slot that did not join.
    name = published.name if published is not None else cast.display_name
    ctk.CTkLabel(
        frame,
        text=name,
        font=FONT_ROW,
        text_color=theme.TEXT_PRIMARY,
        anchor="w",
    ).grid(row=0, column=3, sticky="ew")

    ctk.CTkLabel(
        frame,
        text=_travel(cast, replay),
        font=FONT_NOTE,
        text_color=theme.TEXT_MUTED,
        anchor="e",
    ).grid(row=0, column=4, padx=(8, 10), sticky="e")
    return frame


def _colour_for(cast, replay: Replay) -> str:
    """The casting team's colour, where the codename attributes to one player."""
    actor_id = abilities.attribute(replay.players).by_codename.get(cast.codename)
    player = replay.player(actor_id) if actor_id is not None else None
    return theme.team_colour(player.team if player else "?")


def _travel(cast, replay: Replay) -> str:
    """
    How far this cast's pawns went, measured, or why there is no figure.

    Zero is a real answer and is shown as one: a Killjoy turret is placed and
    stays there, and "0 uu" says that where a blank would read as missing data.
    """
    if not cast.pawns:
        return abilities.NO_POSITION
    total = sum(
        abilities.travel(replay.ability_tracks[a])
        for a in cast.pawns
        if a in replay.ability_tracks
    )
    return f"{total:,.0f} uu travelled"
