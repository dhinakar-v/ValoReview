"""
Page 2: the replay viewer, assembled.

Five rows on a grid -- top bar, body, round strip, transport, status -- and the
body is the brief's three columns: team A, the centre canvas, team B mirrored.
Only the body stretches, so resizing the window grows the map and never the
furniture.

The centre canvas is the whole point
------------------------------------
It is a `MinimapView` when this replay has decoded positions *and* the art
cache holds a radar image for the map, and the schematic `SceneView` otherwise.
Both present `widget`, `render(snapshot)` and `on_hover`, so the swap changes
nothing else, and the caption under the map says which of the two is showing
and why -- `Replay.position_source` is a sentence written by whichever step
refused, so it is never blank and never a guess.

Positions are decoded here, not at load
---------------------------------------
A full match costs about four minutes and an Oodle DLL.  Blocking the window
for that before it draws anything would be the wrong trade, so the viewer opens
on the schematic and the DECODE POSITIONS button runs `tracks.attach` on a
worker thread, reporting block by block and swapping the canvas when it lands.
The thread only ever hands back a finished `Replay`; every widget call happens
on the Tk thread through `after`, because Tk is not thread-safe and a canvas
touched from a worker fails in ways that look like data corruption.

The clock is not re-implemented
-------------------------------
`PlaybackClock` and the `after` loop are the ones the Tk viewer used: already
headless, already exact, already tested.  A frame recomputes `state_at` from
scratch -- 0.127 ms against 16.7 ms of budget -- so seeking backwards is as
correct as playing forward.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from vrf_reader import _fmt_ms
from vrfview import art as art_mod
from vrfview import icons, mapref, names, theme, tracks
from vrfview.clock import SPEEDS, PlaybackClock
from vrfview.controls import STRIP_HEIGHT, Callbacks, TimelineStrip, TransportBar
from vrfview.images import ImageCache, Visuals
from vrfview.minimap import MinimapView
from vrfview.panels import TeamPanel
from vrfview.scene import SceneView
from vrfview.state import state_at

if TYPE_CHECKING:
    from vrfview.art import ArtCache
    from vrfview.model import Replay

FPS = 30

# Stepping back this far into a round restarts it, the way a track-back button
# does; earlier than that and the step goes to the previous round instead.
RESTART_WINDOW_MS = 1500

PANEL_WIDTH = 330

FONT_TITLE = ("Impact", 22)
FONT_CLOCK = ("Consolas", 20)
FONT_SUB = ("Arial", 11)

SCHEMATIC_CAPTION = "SCHEMATIC — not a map. "
MINIMAP_CAPTION = "MAP — real coordinates. "


@dataclass(frozen=True)
class Session:
    """
    One opened replay: the model, where it came from, and what draws it.

    The path is not on the `Replay` on purpose.  The model states what the
    file says, and both input paths -- a `.vrf` and a JSON dump -- have to
    produce the same model for the tests that compare them to mean anything.
    Where the bytes live is the caller's fact, so it travels beside the model
    rather than inside it, and the position decode reads it from here.
    """

    replay: Replay
    path: Path
    visuals: Visuals
    # Kept so the viewer can name the agents a decode reveals: codenames
    # arrive from the replication stream long after `names.resolve` first ran.
    catalog: object | None = None


class ViewerPage(ctk.CTkFrame):
    """One replay, playing."""

    def __init__(self, master, session: Session, on_back=None):
        super().__init__(master, fg_color=theme.APP_BG)
        self.session = session
        self.replay = session.replay
        self.path = session.path
        self.visuals = session.visuals
        self.catalog = session.catalog
        self.on_back = on_back

        self.clock = PlaybackClock(self.replay.length_ms)
        self._event_times = self.replay.event_times
        self._dirty = True
        self._last_wall = time.perf_counter()
        self._after_id: str | None = None
        self._hover_text = ""
        self._map_window: tk.Toplevel | None = None
        self._decoding = False

        self.map_art = self.visuals.art.map_art(self.replay.map_path)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_top()
        self._build_body()
        self._build_bottom()
        self._bind_keys()
        self.start()

    # -- construction ----------------------------------------------------
    def _build_top(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        bar.grid_columnconfigure(2, weight=1)

        image = self.visuals.images.ctk(icons.path_for("back"), icons.ICON_PX)
        ctk.CTkButton(
            bar,
            text="" if image is not None else icons.FALLBACK["back"],
            image=image,
            width=40,
            height=30,
            fg_color=theme.CARD_BG,
            hover_color=theme.CARD_HOVER,
            text_color=theme.TEXT_PRIMARY,
            command=self._back,
        ).grid(row=0, column=0, padx=(0, 12))

        ctk.CTkLabel(
            bar,
            text=self.replay.map_name.upper(),
            font=FONT_TITLE,
            text_color=theme.TEXT_PRIMARY,
        ).grid(row=0, column=1)

        self.clock_label = ctk.CTkLabel(
            bar,
            text="",
            font=FONT_CLOCK,
            text_color=theme.TEXT_PRIMARY,
        )
        self.clock_label.grid(row=0, column=2)

        self.decode_button = ctk.CTkButton(
            bar,
            text="DECODE POSITIONS",
            width=170,
            height=30,
            fg_color=theme.CARD_BG,
            hover_color=theme.CARD_HOVER,
            text_color=theme.TEXT_PRIMARY,
            command=self._start_decode,
        )
        self.decode_button.grid(row=0, column=3, padx=(12, 0))
        if self.replay.has_positions:
            self.decode_button.configure(state="disabled", text="POSITIONS DECODED")

    def _build_body(self) -> None:
        # The body frame itself survives a rebuild; only its contents change.
        body = getattr(self, "body", None)
        if body is None:
            body = ctk.CTkFrame(self, fg_color="transparent")
            body.grid(row=1, column=0, sticky="nsew", padx=10)
            body.grid_columnconfigure(1, weight=1)
            # The two panels keep their width whatever the window does; only
            # the map grows, which is the one thing worth more pixels.
            body.grid_columnconfigure(0, minsize=PANEL_WIDTH)
            body.grid_columnconfigure(2, minsize=PANEL_WIDTH)
            body.grid_rowconfigure(0, weight=1)
            self.body = body

        self.left = TeamPanel(body, self.replay, "A", self.visuals)
        self.left.grid(row=0, column=0, sticky="nsew")
        self.left.configure(width=PANEL_WIDTH)

        centre = ctk.CTkFrame(body, fg_color="transparent")
        centre.grid(row=0, column=1, sticky="nsew", padx=10)
        centre.grid_columnconfigure(0, weight=1)
        centre.grid_rowconfigure(0, weight=1)
        self.centre = centre

        self.caption = ctk.CTkLabel(
            centre,
            text="",
            font=FONT_SUB,
            text_color=theme.TEXT_MUTED,
            wraplength=560,
        )
        self.caption.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self.view = self._make_view()
        self.view.widget.grid(row=0, column=0, sticky="nsew")
        self.view.on_hover = self._on_hover_node

        self.right = TeamPanel(body, self.replay, "B", self.visuals, mirrored=True)
        self.right.grid(row=0, column=2, sticky="nsew")
        self.right.configure(width=PANEL_WIDTH)

    def _make_view(self):
        """The minimap where positions and art allow it, the schematic otherwise."""
        plottable = self.map_art is not None and self.map_art.plottable
        if self.replay.has_positions and plottable:
            self.caption.configure(
                text=MINIMAP_CAPTION + self.replay.position_source,
            )
            return MinimapView(self.centre, self.replay, self.map_art, self.visuals.images)
        why = self.replay.position_source or tracks.NOT_REQUESTED
        if self.replay.has_positions and not plottable:
            why = f"positions decoded, but no minimap image for {self.replay.map_name}"
        self.caption.configure(text=SCHEMATIC_CAPTION + why)
        return SceneView(self.centre, self.replay)

    def _build_bottom(self) -> None:
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
        self.strip = TimelineStrip(self, self.replay, cb)
        self.strip.widget.grid(row=2, column=0, sticky="ew", padx=10)
        self.strip.widget.configure(height=STRIP_HEIGHT)
        self.strip.on_hover_time = self._on_hover_time

        self.bar = TransportBar(self, self.replay, cb, self.visuals)
        self.bar.grid(row=3, column=0, sticky="ew")

        self.status = ctk.CTkLabel(
            self,
            text="",
            font=FONT_SUB,
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        self.status.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 8))

    def _bind_keys(self) -> None:
        root = self.winfo_toplevel()
        root.bind("<space>", lambda _e: self._toggle_play())
        root.bind("<Left>", lambda _e: self._step_event(-1))
        root.bind("<Right>", lambda _e: self._step_event(1))
        root.bind("<comma>", lambda _e: self._step_round(-1))
        root.bind("<period>", lambda _e: self._step_round(1))
        root.bind("<Home>", lambda _e: self._seek(0))
        root.bind("<End>", lambda _e: self._seek(self.replay.length_ms))
        for i, speed in enumerate(SPEEDS, start=1):
            root.bind(str(i), lambda _e, s=speed: self._set_speed(s))

    # -- loop ------------------------------------------------------------
    def start(self) -> None:
        """Begin the frame loop.  Idempotent."""
        if self._after_id is None:
            self._last_wall = time.perf_counter()
            self._tick()

    def stop(self) -> None:
        """Cancel the frame loop.  A page not on screen must not draw."""
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None

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
        self.view.render(snap)
        self.strip.render(snap)
        self.left.render(snap)
        self.right.render(snap)
        self.bar.refresh(snap, playing=self.clock.playing, speed=self.clock.speed)
        rnd = snap.round.number if snap.round else "-"
        self.clock_label.configure(text=f"{_fmt_ms(snap.t_ms)}   R{rnd}")
        self.status.configure(text=self._status_text(snap))

    def _status_text(self, snap) -> str:
        if self._hover_text:
            return self._hover_text
        a, b = snap.score
        return (
            f"From file: {len(self.replay.kills)} kills, "
            f"{len(self.replay.rounds)} rounds, {len(self.replay.ultimates)} ults   |   "
            f"Inferred *: team split, round outcomes, score {a}-{b}   |   "
            f"Not in file: player names, HP, armour, credits, ATK/DEF sides"
        )

    # -- callbacks -------------------------------------------------------
    def _back(self) -> None:
        self.stop()
        if self.on_back is not None:
            self.on_back()

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
            if current is not None and t - current.start_ms > RESTART_WINDOW_MS:
                target = current.start_ms
            else:
                prev = [x for x in starts if x < t]
                target = prev[-1] if prev else 0
        self._seek(target)

    def _set_speed(self, speed: float) -> None:
        self.clock.set_speed(speed)
        self._dirty = True

    def _toggle_layer(self, name: str, *, on: bool) -> None:
        self.view.set_layer(name, on=on)
        self._dirty = True

    def _on_hover_node(self, actor_id) -> None:
        # The minimap hands back a Player, the schematic an actor id; both are
        # allowed to say "nothing".
        if actor_id is None:
            self._hover_text = ""
            self._dirty = True
            return
        if not isinstance(actor_id, int):
            actor_id = actor_id.actor_id
        snap = state_at(self.replay, self.clock.t_ms)
        player = self.replay.player(actor_id)
        kills, deaths = snap.kd.get(actor_id, (0, 0))
        merged = (
            f" (merged from {', '.join(str(m) for m in player.merged_from)})"
            if player and player.merged_from
            else ""
        )
        state = "alive" if snap.is_alive(actor_id) else "dead"
        where = snap.position_of(actor_id)
        at = f" at ({where.x:,.0f}, {where.y:,.0f})" if where else ""
        self._hover_text = (
            f"#{actor_id} - {player.identity if player else '?'} - "
            f"{kills} kills / {deaths} deaths - {state}{merged}{at}"
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
        self._map_window = mapref.show(
            self.winfo_toplevel(),
            self.map_art,
            self.visuals.images,
        )

    def _show_provenance(self) -> None:
        top = ctk.CTkToplevel(self)
        top.title("Provenance")
        top.geometry("820x520")
        top.configure(fg_color=theme.APP_BG)
        box = ctk.CTkTextbox(
            top,
            fg_color=theme.APP_BG,
            text_color=theme.TEXT_PRIMARY,
            font=("Consolas", 11),
            wrap="word",
        )
        box.pack(fill="both", expand=True, padx=10, pady=10)
        box.insert("end", provenance_text(self.replay, self.visuals.art))
        box.configure(state="disabled")

    # -- decoding positions ----------------------------------------------
    def _start_decode(self) -> None:
        """
        Decode positions on a worker thread, leaving the window alive.

        Nothing about the model is touched here: `tracks.attach` mutates the
        replay on the worker and the Tk side only learns that it finished, then
        rebuilds the centre view on the main thread.  `attach` never raises for
        want of positions, so the failure path is a sentence in the caption,
        not an exception crossing a thread boundary.
        """
        if self._decoding:
            return
        self._decoding = True
        self.decode_button.configure(state="disabled", text="DECODING...")

        def progress(done: int, total: int) -> None:
            self.after(0, self._decode_progress, done, total)

        def work() -> None:
            tracks.attach(self.replay, self.path, tracks.Options(progress=progress))
            self.after(0, self._decode_finished)

        threading.Thread(target=work, daemon=True, name="decode-positions").start()

    def _decode_progress(self, done: int, total: int) -> None:
        self.decode_button.configure(text=f"DECODING {done}/{total}")

    def _decode_finished(self) -> None:
        self._decoding = False
        self.decode_button.configure(
            state="disabled" if self.replay.has_positions else "normal",
            text="POSITIONS DECODED" if self.replay.has_positions else "DECODE POSITIONS",
        )
        # A decode does not only produce positions: each pawn also states its
        # own agent codename, and those were not there when names.resolve last
        # ran.  Naming them again is what turns `Hunter` into Sova in the
        # panels, so it has to happen before the body is rebuilt.
        names.resolve(self.replay, self.catalog)
        self._rebuild_body()

    def _rebuild_body(self) -> None:
        """
        Throw the body away and build it again.

        The schematic and the minimap are different widgets, and a portrait is
        chosen when a row is constructed, so the decode's two effects -- a real
        map, and agents with faces -- both land by rebuilding rather than by
        reconfiguring ten things in place.
        """
        for child in self.body.winfo_children():
            child.destroy()
        self._build_body()
        self._dirty = True


def provenance_text(replay: Replay, art: ArtCache | None = None) -> str:
    """Every claim the interface makes, and where each one came from."""
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
        "DECODED FROM THE REPLICATION STREAM",
        f"  positions         {replay.position_source or 'not requested'}",
        f"  agent per actor   {_codename_summary(replay)}",
    ]
    lines += [
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
    lines += ["  the map reference window plots Riot's callouts, never players"]
    lines += ["", "INFERRED (marked * in the interface)"]
    lines += [f"  {note}" for note in replay.notes]
    lines += [
        "",
        "NOT IN THE FILE",
        "  player names / Riot IDs   absent; they need val-match-v1, which a",
        "                            personal development key cannot reach",
        "  health, armour, credits   never replicated to a spectator recording;",
        "                            the player rows show -- rather than a number",
        "  attacker / defender       spike events carry no actor id, so which",
        "                            side planted is not recoverable, and the two",
        "                            colours mean team A and team B",
        "  weapon held               in the property payload but not yet decoded",
    ]
    return "\n".join(lines)


def _codename_summary(replay: Replay) -> str:
    named = [p for p in replay.players if p.codename]
    if not named:
        return "not decoded; no pawn archetype was read"
    return (
        f"{len(named)} of {len(replay.players)} actors state their own agent "
        f"({', '.join(sorted({p.identity for p in named}))})"
    )


def run(
    replay: Replay,
    art: ArtCache | None = None,
    path: str | Path = "",
    catalog=None,
) -> int:
    """
    Open one replay in its own window and block until it closes.

    `path` is where the replay was loaded from; without it the DECODE POSITIONS
    button has nothing to read and says so rather than guessing at a filename.
    """
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.title(f"vrfview - {replay.source} - {replay.map_name}")
    root.geometry("1360x860")
    root.minsize(1100, 700)
    root.configure(fg_color=theme.APP_BG)

    visuals = Visuals.make(art if art is not None else art_mod.ArtCache(), ImageCache())
    session = Session(
        replay=replay,
        path=Path(path or replay.source),
        visuals=visuals,
        catalog=catalog,
    )
    page = ViewerPage(root, session, on_back=root.destroy)
    page.pack(fill="both", expand=True)
    root.mainloop()
    return 0
