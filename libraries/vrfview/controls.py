"""
The docked bottom: round strip, scrubber and transport.

The strip is a canvas rather than a slider widget because the playhead, the round
bands, the event ticks and the side-swap divider all have to share one
coordinate system; a themed slider owns its own geometry and cannot be drawn
into.  `ms_to_x` and `x_to_ms` are the only place pixels and milliseconds meet.

Bands are proportional to real time, so a long round is visibly wider than a
short one.  On the reference capture rounds run 65 to 143 seconds, and at the
observed maximum of 26 rounds the narrowest band is about 29 px, so labels
degrade -- the "R" prefix is dropped, then the number, then only the tint
remains -- rather than overprinting each other.

Round outcome chips appear only once the round has ended, so scrubbing forward
does not reveal a result before the playhead reaches it.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import customtkinter as ctk

from vrf_reader import _fmt_ms
from vrfview import icons, theme
from vrfview.clock import SPEEDS
from vrfview.icons import ICON_PX
from vrfview.model import TEAM_A, TEAM_B, Replay

if TYPE_CHECKING:
    from vrfview.images import Visuals
    from vrfview.state import Snapshot

STRIP_HEIGHT = 76
GUTTER = 12
CHIP_ROW = 13
BAND_TOP = 20
BAND_BOTTOM = 52
TICK_TOP = 54
TICK_BOTTOM = 70

# Below this the strip has no room for round bands at all; a band narrower than
# CHIP_LABEL_FULL loses the "R" prefix, and below CHIP_LABEL_SHORT its number.
MIN_STRIP_WIDTH = 60
CHIP_LABEL_FULL = 40
CHIP_LABEL_SHORT = 20

_SPIKE_GLYPH = {
    "planted": ("▲", theme.SPIKE_ARMED),
    "defused": ("■", theme.SPIKE_SAFE),
    "exploded": ("✹", theme.SPIKE_BOOM),
}


class ToggleLayer(Protocol):
    """Turn one scene layer on or off; `on` is keyword-only at both ends."""

    def __call__(self, name: str, *, on: bool) -> None: ...


@dataclass
class Callbacks:
    """What the control bar asks the app to do."""

    toggle_play: Callable[[], None]
    step_event: Callable[[int], None]
    step_round: Callable[[int], None]
    set_speed: Callable[[float], None]
    seek: Callable[[int], None]
    toggle_layer: ToggleLayer
    show_provenance: Callable[[], None]
    show_map: Callable[[], None]


class TimelineStrip:
    """Round bands, event ticks and the draggable playhead."""

    def __init__(self, master: tk.Misc, replay: Replay, cb: Callbacks) -> None:
        self.replay = replay
        self.cb = cb
        self.canvas = tk.Canvas(
            master,
            bg=theme.PANEL,
            height=STRIP_HEIGHT,
            highlightthickness=0,
            bd=0,
        )
        self._width = 0
        self._playhead = self.canvas.create_line(
            0,
            0,
            0,
            0,
            fill=theme.PLAYHEAD,
            width=2,
        )
        self._ghost = self.canvas.create_line(
            0,
            0,
            0,
            0,
            fill=theme.FAINT,
            width=1,
            state="hidden",
        )
        self._chips: dict[int, int] = {}
        self.on_hover_time = None

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_press)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind(
            "<Leave>",
            lambda _e: self.canvas.itemconfigure(self._ghost, state="hidden"),
        )

    @property
    def widget(self) -> tk.Canvas:
        return self.canvas

    # --- geometry --------------------------------------------------------

    @property
    def _x0(self) -> float:
        return GUTTER

    @property
    def _x1(self) -> float:
        return max(GUTTER + 1, self._width - GUTTER)

    def ms_to_x(self, ms: float) -> float:
        length = self.replay.length_ms or 1
        frac = min(1.0, max(0.0, ms / length))
        return self._x0 + frac * (self._x1 - self._x0)

    def x_to_ms(self, x: float) -> int:
        span = self._x1 - self._x0 or 1
        frac = min(1.0, max(0.0, (x - self._x0) / span))
        return round(frac * self.replay.length_ms)

    # --- static furniture ------------------------------------------------

    def _on_configure(self, event: tk.Event) -> None:
        self._width = event.width
        self._rebuild()

    def _rebuild(self) -> None:
        """Redraw the parts that only change on resize."""
        c = self.canvas
        c.delete("static")
        self._chips.clear()
        if self._width < MIN_STRIP_WIDTH:
            return

        for i, rnd in enumerate(self.replay.rounds):
            x0, x1 = self.ms_to_x(rnd.start_ms), self.ms_to_x(rnd.end_ms)
            shade = theme.PANEL_EDGE if i % 2 == 0 else theme.PANEL
            c.create_rectangle(
                x0,
                BAND_TOP,
                x1,
                BAND_BOTTOM,
                fill=shade,
                outline="",
                tags="static",
            )
            width = x1 - x0
            if width >= CHIP_LABEL_FULL:
                text = f"R{rnd.number}"
            elif width >= CHIP_LABEL_SHORT:
                text = str(rnd.number)
            else:
                text = ""
            if text:
                c.create_text(
                    (x0 + x1) / 2,
                    (BAND_TOP + BAND_BOTTOM) / 2,
                    text=text,
                    fill=theme.MUTED,
                    font=("Segoe UI", 8),
                    tags="static",
                )
            self._chips[rnd.number] = c.create_text(
                (x0 + x1) / 2,
                CHIP_ROW,
                text="",
                fill=theme.MUTED,
                font=("Segoe UI Semibold", 9),
                tags="static",
            )

        for kill in self.replay.kills:
            x = self.ms_to_x(kill.t_ms)
            player = self.replay.player(kill.victim)
            colour = theme.blend(
                theme.team_colour(player.team if player else "?"),
                theme.BACKGROUND,
                0.35,
            )
            c.create_line(
                x,
                TICK_TOP,
                x,
                TICK_BOTTOM - 6,
                fill=colour,
                width=1,
                tags="static",
            )
        for ult in self.replay.ultimates:
            x = self.ms_to_x(ult.t_ms)
            c.create_line(
                x,
                TICK_TOP,
                x,
                TICK_BOTTOM,
                fill=theme.ULT,
                width=1,
                tags="static",
            )
        for spike in self.replay.spike:
            glyph, colour = _SPIKE_GLYPH.get(spike.kind, ("?", theme.MUTED))
            c.create_text(
                self.ms_to_x(spike.t_ms),
                TICK_BOTTOM - 3,
                text=glyph,
                fill=colour,
                font=("Segoe UI", 7),
                tags="static",
            )
        if self.replay.side_swap_ms is not None:
            x = self.ms_to_x(self.replay.side_swap_ms)
            c.create_line(
                x,
                2,
                x,
                STRIP_HEIGHT - 2,
                fill=theme.ACCENT,
                width=1,
                dash=(3, 2),
                tags="static",
            )
            c.create_text(
                x + 4,
                6,
                text="swap",
                anchor="w",
                fill=theme.ACCENT,
                font=("Segoe UI", 7),
                tags="static",
            )
        c.tag_raise(self._ghost)
        c.tag_raise(self._playhead)

    # --- per-frame -------------------------------------------------------

    def render(self, snap: Snapshot) -> None:
        x = self.ms_to_x(snap.t_ms)
        self.canvas.coords(self._playhead, x, 0, x, STRIP_HEIGHT)
        for rnd in self.replay.rounds:
            item = self._chips.get(rnd.number)
            if item is None:
                continue
            if snap.t_ms < rnd.end_ms:
                self.canvas.itemconfigure(item, text="")
                continue
            if rnd.winner == TEAM_A:
                self.canvas.itemconfigure(
                    item,
                    text="A",
                    fill=theme.team_colour(TEAM_A),
                )
            elif rnd.winner == TEAM_B:
                self.canvas.itemconfigure(
                    item,
                    text="B",
                    fill=theme.team_colour(TEAM_B),
                )
            else:
                self.canvas.itemconfigure(item, text="?", fill=theme.MUTED)

    # --- interaction -----------------------------------------------------

    def _on_press(self, event: tk.Event) -> None:
        self.cb.seek(self.x_to_ms(event.x))

    def _on_motion(self, event: tk.Event) -> None:
        self.canvas.coords(self._ghost, event.x, 0, event.x, STRIP_HEIGHT)
        self.canvas.itemconfigure(self._ghost, state="normal")
        if self.on_hover_time is not None:
            self.on_hover_time(self.x_to_ms(event.x))



class TransportBar(ctk.CTkFrame):
    """
    Transport, speed, readout and the two panel buttons.

    CustomTkinter rather than ttk, and every control carries a glyph from
    `scripts/make_icons.py` with a text fallback: `assets/` is gitignored, so a
    fresh checkout has no icons and must still get a usable bar.  `images.ctk`
    returns None for a missing file, which is the whole fallback test.
    """

    def __init__(
        self,
        master,
        replay: Replay,
        cb: Callbacks,
        visuals: Visuals,
    ) -> None:
        super().__init__(master, fg_color=theme.APP_BG, corner_radius=0)
        self.replay = replay
        self.cb = cb
        self.visuals = visuals
        self._speed_buttons: dict[float, ctk.CTkButton] = {}

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", padx=(12, 0), pady=8)
        self._icon_button(left, "round_back", lambda: cb.step_round(-1))
        self._icon_button(left, "step_back", lambda: cb.step_event(-1))
        self.play_button = self._icon_button(left, "play", cb.toggle_play, wide=True)
        self._icon_button(left, "step_forward", lambda: cb.step_event(1))
        self._icon_button(left, "round_forward", lambda: cb.step_round(1))

        self.time_label = ctk.CTkLabel(
            self,
            text="",
            font=("Consolas", 13),
            text_color=theme.TEXT_PRIMARY,
        )
        self.time_label.pack(side="left", padx=16)

        speeds = ctk.CTkFrame(self, fg_color="transparent")
        speeds.pack(side="left")
        for value in SPEEDS:
            button = ctk.CTkButton(
                speeds,
                text=f"{value:g}x",
                width=42,
                height=26,
                corner_radius=4,
                fg_color=theme.CARD_BG,
                hover_color=theme.CARD_HOVER,
                text_color=theme.TEXT_MUTED,
                command=lambda v=value: cb.set_speed(v),
            )
            button.pack(side="left", padx=2)
            self._speed_buttons[value] = button

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=(0, 12))
        self._icon_button(right, "info", cb.show_provenance, side="right")
        # Offered only when the art cache holds a radar image for this map: a
        # button that can only report its own absence is worse than no button.
        art = visuals.art.map_art(replay.map_path)
        if art is not None and art.plottable:
            self._icon_button(right, "map", cb.show_map, side="right")

    def _icon_button(
        self,
        master,
        name: str,
        command,
        *,
        side: str = "left",
        wide: bool = False,
    ) -> ctk.CTkButton:
        image = self.visuals.images.ctk(icons.path_for(name), ICON_PX)
        button = ctk.CTkButton(
            master,
            text="" if image is not None else icons.FALLBACK.get(name, name),
            image=image,
            width=48 if wide else 36,
            height=30,
            corner_radius=4,
            fg_color=theme.CARD_BG,
            hover_color=theme.CARD_HOVER,
            text_color=theme.TEXT_PRIMARY,
            command=command,
        )
        button.pack(side=side, padx=3)
        return button

    @property
    def widget(self) -> ctk.CTkFrame:
        return self

    def refresh(self, snap: Snapshot, *, playing: bool, speed: float) -> None:
        glyph = "pause" if playing else "play"
        image = self.visuals.images.ctk(icons.path_for(glyph), ICON_PX)
        self.play_button.configure(
            image=image,
            text="" if image is not None else icons.FALLBACK[glyph],
        )
        rnd = snap.round.number if snap.round else "-"
        self.time_label.configure(
            text=f"{_fmt_ms(snap.t_ms)} / {_fmt_ms(self.replay.length_ms)}"
            f"   R{rnd}/{len(self.replay.rounds)}",
        )
        for value, button in self._speed_buttons.items():
            chosen = value == speed
            button.configure(
                fg_color=theme.CARD_HOVER if chosen else theme.CARD_BG,
                text_color=theme.TEXT_PRIMARY if chosen else theme.TEXT_MUTED,
            )
