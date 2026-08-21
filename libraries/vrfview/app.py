"""
Window assembly and the frame loop.

Five rows on a grid: the scene takes every spare pixel, and the roster band
above it and the strip, control bar and status line below are all fixed height,
so resizing the window grows the field and never the furniture.  The roster band
is dropped entirely when no art resolves, which restores the previous four-row
layout exactly.

The loop is driven only by `after`.  It keeps running while paused so that
keyboard and drag events still repaint, but it recomputes nothing unless the
clock actually moved or something marked the view dirty.  The wall-time
reference is refreshed every frame whether or not playback is running, which
is what makes pausing exact: no time accumulates while stopped.
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from vrf_reader import _fmt_ms
from vrfview import art as art_mod
from vrfview import mapref, theme
from vrfview.clock import SPEEDS, PlaybackClock
from vrfview.controls import STRIP_HEIGHT, Callbacks, ControlBar, TimelineStrip
from vrfview.images import ImageCache
from vrfview.roster import RosterBand
from vrfview.scene import SceneView
from vrfview.state import state_at

if TYPE_CHECKING:
    from vrfview.art import ArtCache
    from vrfview.model import Replay

FPS = 30

# Stepping back this far into a round restarts it, the way a track-back button
# does; earlier than that and the step goes to the previous round instead.
_RESTART_WINDOW_MS = 1500


class ViewerApp(tk.Tk):
    """The whole viewer."""

    def __init__(self, replay: Replay, art: ArtCache | None = None) -> None:
        super().__init__()
        self.replay = replay
        self.clock = PlaybackClock(replay.length_ms)
        self._event_times = replay.event_times
        self._dirty = True
        self._last_wall = time.perf_counter()
        self._after_id: str | None = None
        self._hover_text = ""
        self.art = art if art is not None else art_mod.ArtCache()
        self.images = ImageCache()
        self.map_art = self.art.map_art(replay.map_path)
        self._map_window: tk.Toplevel | None = None

        self.title(f"vrfview - {replay.source} - {replay.map_name}")
        self.configure(bg=theme.BACKGROUND)
        self.minsize(940, 640)
        self.geometry("1280x820")
        self._style()

        cb = Callbacks(
            toggle_play=self._toggle_play,
            step_event=self._step_event,
            step_round=self._step_round,
            set_speed=self._set_speed,
            seek=self._seek,
            toggle_layer=self._toggle_layer,
            show_provenance=self._show_provenance,
            show_map=self._show_map,
        )
        plottable = self.map_art is not None and self.map_art.plottable
        self.roster = RosterBand(self, replay, self.art, self.images)
        self.scene = SceneView(self, replay)
        self.strip = TimelineStrip(self, replay, cb)
        self.bar = ControlBar(self, replay, cb, map_available=plottable)
        self.status = ttk.Label(self, text="", style="Status.TLabel", anchor="w")

        self.scene.on_hover = self._on_hover_node
        self.strip.on_hover_time = self._on_hover_time

        self.columnconfigure(0, weight=1)
        # Only the scene stretches; the band is gridded above it and taken out
        # entirely when there is no art, so a checkout with no assets/ gets the
        # same window it got before.
        self.rowconfigure(1, weight=1)
        if self.roster.useful:
            self.roster.widget.grid(row=0, column=0, sticky="ew")
        self.scene.widget.grid(row=1, column=0, sticky="nsew")
        self.strip.widget.grid(row=2, column=0, sticky="ew")
        self.bar.widget.grid(row=3, column=0, sticky="ew")
        self.status.grid(row=4, column=0, sticky="ew")
        self.strip.widget.configure(height=STRIP_HEIGHT)

        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick()

    # --- styling ---------------------------------------------------------

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            ".",
            background=theme.PANEL,
            foreground=theme.TEXT,
            borderwidth=0,
            focuscolor=theme.PANEL,
        )
        style.configure("TFrame", background=theme.PANEL)
        style.configure("TLabel", background=theme.PANEL, foreground=theme.TEXT)
        style.configure("Read.TLabel", background=theme.PANEL, foreground=theme.TEXT)
        style.configure(
            "Status.TLabel",
            background=theme.BACKGROUND,
            foreground=theme.MUTED,
            padding=(10, 4),
            font=("Segoe UI", 8),
        )
        style.configure(
            "TButton",
            background=theme.PANEL_EDGE,
            foreground=theme.TEXT,
            padding=(6, 3),
        )
        style.map(
            "TButton",
            background=[("pressed", theme.ACCENT), ("active", "#39405266")],
            foreground=[("pressed", theme.BACKGROUND)],
        )
        style.configure("TCheckbutton", background=theme.PANEL, foreground=theme.MUTED)
        style.map("TCheckbutton", foreground=[("selected", theme.TEXT)])

    def _bind_keys(self) -> None:
        self.bind_all("<space>", lambda _e: self._toggle_play())
        self.bind_all("<Left>", lambda _e: self._step_event(-1))
        self.bind_all("<Right>", lambda _e: self._step_event(1))
        self.bind_all("<comma>", lambda _e: self._step_round(-1))
        self.bind_all("<period>", lambda _e: self._step_round(1))
        self.bind_all("<Home>", lambda _e: self._seek(0))
        self.bind_all("<End>", lambda _e: self._seek(self.replay.length_ms))
        self.bind_all("<Escape>", lambda _e: self._on_close())
        for i, speed in enumerate(SPEEDS, start=1):
            self.bind_all(str(i), lambda _e, s=speed: self._set_speed(s))

    # --- loop ------------------------------------------------------------

    def _tick(self) -> None:
        now = time.perf_counter()
        delta_ms = (now - self._last_wall) * 1000.0
        self._last_wall = now
        if self.clock.tick(delta_ms) or self._dirty:
            self._redraw()
            self._dirty = False
        self._after_id = self.after(1000 // FPS, self._tick)

    def _redraw(self) -> None:
        snap = state_at(self.replay, self.clock.t_ms)
        self.scene.render(snap)
        self.strip.render(snap)
        self.bar.refresh(snap, playing=self.clock.playing, speed=self.clock.speed)
        self.status.configure(text=self._status_text(snap))

    def _status_text(self, snap) -> str:
        if self._hover_text:
            return self._hover_text
        a, b = snap.score
        roster = ", ".join(self.replay.roster)
        # The roster goes last because this label clips on the right: the
        # caveat must stay readable, and the full roster is in the provenance
        # panel either way.
        named = f"   |   Agents (roster, unattributed): {roster}" if roster else ""
        return (
            f"From file: {len(self.replay.kills)} kills, {len(self.replay.rounds)} "
            f"rounds, {len(self.replay.ultimates)} ults, {len(self.replay.spike)} "
            f"spike events   |   Inferred *: team split, round outcomes, score "
            f"{a}-{b}   |   Not in file: player names, agent per actor, "
            f"ATK/DEF sides, positions{named}"
        )

    # --- callbacks -------------------------------------------------------

    def _toggle_play(self) -> None:
        self.clock.toggle()
        self._dirty = True

    def _seek(self, ms: float) -> None:
        self.clock.seek(ms)
        self._dirty = True

    def _step_event(self, direction: int) -> None:
        t = self.clock.t_ms
        if direction > 0:
            nxt = [x for x in self._event_times if x > t]
            target = nxt[0] if nxt else self.replay.length_ms
        else:
            prev = [x for x in self._event_times if x < t]
            target = prev[-1] if prev else 0
        self.clock.pause()
        self._seek(target)

    def _step_round(self, direction: int) -> None:
        t = self.clock.t_ms
        starts = [r.start_ms for r in self.replay.rounds]
        if direction > 0:
            nxt = [x for x in starts if x > t]
            target = nxt[0] if nxt else self.replay.length_ms
        else:
            current = self.replay.round_at(t)
            if current is not None and t - current.start_ms > _RESTART_WINDOW_MS:
                target = current.start_ms
            else:
                prev = [x for x in starts if x < t]
                target = prev[-1] if prev else 0
        self._seek(target)

    def _set_speed(self, speed: float) -> None:
        self.clock.set_speed(speed)
        self._dirty = True

    def _toggle_layer(self, name: str, *, on: bool) -> None:
        self.scene.set_layer(name, on=on)
        self._dirty = True

    def _on_hover_node(self, actor_id: int | None) -> None:
        if actor_id is None:
            self._hover_text = ""
        else:
            snap = state_at(self.replay, self.clock.t_ms)
            player = self.replay.player(actor_id)
            kills, deaths = snap.kd.get(actor_id, (0, 0))
            merged = (
                f" (merged from {', '.join(str(m) for m in player.merged_from)})"
                if player and player.merged_from
                else ""
            )
            state = "alive" if snap.is_alive(actor_id) else "dead"
            self._hover_text = (
                f"#{actor_id} - {player.label if player else '?'} * - "
                f"{kills} kills / {deaths} deaths - {state}{merged}"
            )
        self._dirty = True

    def _on_hover_time(self, ms: int) -> None:
        rnd = self.replay.round_at(ms)
        where = f"round {rnd.number}" if rnd else "pre-round"
        self._hover_text = f"{_fmt_ms(ms)} - {where}"
        self._dirty = True

    def _show_map(self) -> None:
        """Open the map reference, or raise the one already open."""
        if self._map_window is not None and self._map_window.winfo_exists():
            self._map_window.lift()
            return
        self._map_window = mapref.show(self, self.map_art, self.images)

    def _show_provenance(self) -> None:
        top = tk.Toplevel(self)
        top.title("Provenance")
        top.configure(bg=theme.BACKGROUND)
        top.geometry("760x440")
        text = tk.Text(
            top,
            bg=theme.BACKGROUND,
            fg=theme.TEXT,
            bd=0,
            wrap="word",
            font=("Consolas", 9),
            padx=14,
            pady=12,
            insertbackground=theme.TEXT,
        )
        text.pack(fill="both", expand=True)
        text.insert("end", _provenance_text(self.replay, self.art))
        text.configure(state="disabled")
        top.transient(self)

    def _on_close(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        self.destroy()


def _provenance_text(replay: Replay, art: ArtCache | None = None) -> str:
    lines = [
        "READ FROM THE FILE",
        f"  replay            {replay.source}",
        f"  match id          {replay.match_id or 'not recorded'}",
        f"  recorded (UTC)    {replay.recorded_utc}",
        f"  build             {replay.build}",
        f"  duration          {_fmt_ms(replay.length_ms)}",
        f"  map (internal)    {replay.map_path}",
        f"  rounds            {len(replay.rounds)}, from roundStarted events",
        (
            f"  kills             {len(replay.kills)}, characterDeath: "
            "args[1] killer, args[2] victim"
        ),
        f"  ultimates         {len(replay.ultimates)}, characterUltimateUsed",
        (
            f"  spike events      {len(replay.spike)}, timestamps only - the events "
            "carry no actor id"
        ),
        (
            f"  side swap         "
            f"{_fmt_ms(replay.side_swap_ms) if replay.side_swap_ms else 'not recorded'}"
        ),
        f"  agent UUIDs       {len(replay.loadouts)} loadout slots, agent ids only",
        "",
        "RESOLVED AGAINST RIOT'S CONTENT CATALOGUE",
        f"  catalogue         {replay.catalog_source}",
        f"  map name          {replay.map_name}, from the {replay.map_name_source}",
        f"  agents (roster)   {', '.join(replay.roster) or 'unresolved'}",
    ]
    lines += [f"  {note}" for note in replay.catalog_notes]

    cache = art if art is not None else art_mod.ArtCache()
    lines += ["", "ART CACHE (pictures only; it names nothing and infers nothing)"]
    lines += [
        f"  {line}"
        for line in art_mod.coverage(
            cache,
            replay.map_path,
            [x.character_id for x in replay.loadouts],
        )
    ]
    lines += [
        "  the map reference window plots Riot's callouts, never players",
    ]
    lines += [
        "",
        "INFERRED (marked * in the interface)",
    ]
    lines += [f"  {note}" for note in replay.notes]
    lines += [
        "",
        "NOT IN THE FILE",
        "  player names / Riot IDs   absent; they need val-match-v1, which a",
        "                            personal development key cannot reach",
        "  agent per actor id        the roster above is in the file's own order",
        "                            and links to no actor id; 8 codenames are",
        "                            visible in block000 and link to none either",
        "  attacker / defender       spike events carry no actor id, so which",
        "                            side planted is not recoverable",
        "  positions and rotations   the UE property payload interior is",
        "                            undecoded and spawn transforms are skipped;",
        "                            the 2D scene is schematic, not a map",
    ]
    return "\n".join(lines)


def run(replay: Replay, art: ArtCache | None = None) -> int:
    """
    Open the window and block until it closes.

    The caller supplies the art cache, already loaded, so that --no-art is an
    empty ArtCache rather than a second flag this layer has to understand.  Art
    is not part of the model: it changes nothing the replay claims, only what
    the window can draw.
    """
    app = ViewerApp(replay, art)
    app.mainloop()
    return 0
