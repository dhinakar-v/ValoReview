"""
The 2D field, drawn on a Tk canvas.

Two rules shape this module.

Create once, then mutate.  Every item the scene will ever need is created when
the canvas is first sized and is afterwards only moved with `coords` or
restyled with `itemconfigure`; items that are momentarily not wanted are
hidden, never deleted.  A Tk canvas is not double buffered, so rebuilding the
display list every frame flickers visibly on Windows and throws away Tk's
dirty-region tracking.  Item count is therefore constant after startup, which
is also how the resize path is checked.

Draw only from the snapshot.  Nothing here holds animation state -- a kill
arrow's opacity is a function of `t - kill.t_ms`, not of a timer that was
started when the kill happened.  That is what makes dragging the scrubber
backwards, jumping between rounds and playing at 8x all render correctly
without special cases.

The scene is a schematic and says so on screen.  There are no coordinates in
this pipeline, so node placement carries no spatial meaning; only who, when,
and against whom.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from vrfview import layout as layout_mod
from vrfview import theme
from vrfview.model import (
    SPIKE_DEFUSED,
    SPIKE_EXPLODED,
    SPIKE_PLANTED,
    TEAM_A,
    TEAM_B,
    Replay,
)

if TYPE_CHECKING:
    from vrfview.state import Snapshot

# Below this the canvas is too small to lay anything out on.
MIN_CANVAS_PX = 40

ARROW_POOL = 16
PULSE_POOL = 8
DEATH_POP_MS = 260

FONT_LABEL = ("Segoe UI Semibold", 11)
FONT_SUB = ("Consolas", 8)
FONT_KD = ("Consolas", 9)
FONT_HEAD = ("Segoe UI Semibold", 12)
FONT_COUNT = ("Segoe UI", 22, "bold")
FONT_BANNER = ("Segoe UI Semibold", 15)
FONT_SCORE = ("Segoe UI", 26, "bold")
FONT_SMALL = ("Segoe UI", 8)
FONT_DEAD = ("Segoe UI", 10, "bold")


class SceneView:
    """The upper canvas: nodes, kill arrows, ult pulses, spike, banner."""

    def __init__(self, master: tk.Misc, replay: Replay) -> None:
        self.replay = replay
        self.canvas = tk.Canvas(master, bg=theme.BACKGROUND, highlightthickness=0, bd=0)
        self.layers = {
            "kills": True,
            "trails": False,
            "ults": True,
            "spike": True,
            "kd": True,
        }
        self.on_hover = None

        self._layout = layout_mod.Layout()
        self._nodes: dict[int, dict[str, int]] = {}
        self._arrows: list[int] = []
        self._pulses: list[int] = []
        self._chrome: dict[str, int] = {}
        self._built = False
        self._resize_job: str | None = None
        self._size = (0, 0)
        self._hovered: int | None = None

        self._ramp = {
            t: theme.ramp(theme.team_colour(t)) for t in (TEAM_A, TEAM_B, "?")
        }
        self._ult_ramp = theme.ramp(theme.ULT)

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(None))

    @property
    def widget(self) -> tk.Canvas:
        return self.canvas

    def set_layer(self, name: str, *, on: bool) -> None:
        if name in self.layers:
            self.layers[name] = on

    # --- construction ----------------------------------------------------

    def _on_configure(self, event: tk.Event) -> None:
        """Debounce resizes; dragging an edge must not relayout every pixel."""
        self._size = (event.width, event.height)
        if self._resize_job is not None:
            self.canvas.after_cancel(self._resize_job)
        self._resize_job = self.canvas.after(100, self._apply_size)

    def _apply_size(self) -> None:
        self._resize_job = None
        width, height = self._size
        if width < MIN_CANVAS_PX or height < MIN_CANVAS_PX:
            return
        self._layout = layout_mod.compute(self.replay, width, height)
        if not self._built:
            self._build()
            self._built = True
        self._reposition()

    def _build(self) -> None:
        c = self.canvas
        for p in self.replay.players:
            colour = theme.team_colour(p.team)
            self._nodes[p.actor_id] = {
                "ring": c.create_oval(0, 0, 0, 0, outline="", width=2, state="hidden"),
                "oval": c.create_oval(0, 0, 0, 0, fill=colour, outline=colour, width=2),
                "dead": c.create_text(
                    0,
                    0,
                    text="✕",
                    fill=theme.MUTED,
                    font=FONT_DEAD,
                    state="hidden",
                ),
                "ult": c.create_oval(
                    0,
                    0,
                    0,
                    0,
                    fill=theme.ULT,
                    outline="",
                    state="hidden",
                ),
                "label": c.create_text(
                    0,
                    0,
                    text=p.label,
                    fill=theme.BACKGROUND,
                    font=FONT_LABEL,
                ),
                "sub": c.create_text(
                    0,
                    0,
                    text=f"#{p.actor_id}",
                    fill=theme.MUTED,
                    font=FONT_SUB,
                ),
                "kd": c.create_text(0, 0, text="", fill=theme.MUTED, font=FONT_KD),
            }
        self._arrows = [
            c.create_line(
                0,
                0,
                0,
                0,
                fill=theme.MUTED,
                width=3,
                smooth=True,
                arrow=tk.LAST,
                arrowshape=(11, 13, 4),
                state="hidden",
            )
            for _ in range(ARROW_POOL)
        ]
        self._pulses = [
            c.create_oval(0, 0, 0, 0, outline=theme.ULT, width=2, state="hidden")
            for _ in range(PULSE_POOL)
        ]
        self._chrome = {
            "a_head": c.create_text(
                0,
                0,
                text="",
                fill=theme.team_colour(TEAM_A),
                font=FONT_HEAD,
            ),
            "b_head": c.create_text(
                0,
                0,
                text="",
                fill=theme.team_colour(TEAM_B),
                font=FONT_HEAD,
            ),
            "a_count": c.create_text(
                0,
                0,
                text="",
                fill=theme.team_colour(TEAM_A),
                font=FONT_COUNT,
            ),
            "b_count": c.create_text(
                0,
                0,
                text="",
                fill=theme.team_colour(TEAM_B),
                font=FONT_COUNT,
            ),
            "banner": c.create_text(0, 0, text="", fill=theme.TEXT, font=FONT_BANNER),
            "score": c.create_text(0, 0, text="", fill=theme.TEXT, font=FONT_SCORE),
            "swap": c.create_text(0, 0, text="", fill=theme.ACCENT, font=FONT_SMALL),
            "spike": c.create_polygon(
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                fill="",
                outline=theme.FAINT,
                width=2,
            ),
            "spike_text": c.create_text(
                0,
                0,
                text="",
                fill=theme.MUTED,
                font=FONT_SMALL,
            ),
            "mark": c.create_text(
                0,
                0,
                text="SCHEMATIC - node positions are layout, not map coordinates",
                fill=theme.FAINT,
                font=FONT_SMALL,
                anchor="se",
            ),
        }

    def _reposition(self) -> None:
        """Move every long-lived item to suit the current layout."""
        c, lay = self.canvas, self._layout
        r = lay.radius
        for actor_id, item in self._nodes.items():
            pos = lay.of(actor_id)
            if pos is None:
                continue
            x, y = pos
            c.coords(item["oval"], x - r, y - r, x + r, y + r)
            c.coords(item["ring"], x - r, y - r, x + r, y + r)
            c.coords(item["dead"], x - r * 0.72, y - r * 0.72)
            c.coords(item["ult"], x + r - 5, y - r, x + r + 3, y - r + 8)
            c.coords(item["label"], x, y)
            c.coords(item["sub"], x, y + r + 10)
            outward = -1 if x < lay.centre[0] else 1
            c.coords(item["kd"], x + outward * (r + 26), y)

        cx, _cy = lay.centre
        width, height = self._size
        c.coords(self._chrome["banner"], cx, lay.top - 34)
        c.coords(self._chrome["score"], cx, lay.top + 6)
        c.coords(self._chrome["swap"], cx, lay.top + 34)
        c.coords(self._chrome["a_head"], lay.left, lay.top - 56)
        c.coords(self._chrome["b_head"], lay.right, lay.top - 56)
        c.coords(self._chrome["a_count"], lay.left, lay.top - 30)
        c.coords(self._chrome["b_count"], lay.right, lay.top - 30)
        c.coords(self._chrome["mark"], width - 12, height - 8)
        s = max(12.0, lay.radius * 0.7)
        sy = lay.bottom - 4
        c.coords(self._chrome["spike"], cx, sy - s, cx + s, sy, cx, sy + s, cx - s, sy)
        c.coords(self._chrome["spike_text"], cx, sy + s + 12)

    # --- rendering -------------------------------------------------------

    def render(self, snap: Snapshot) -> None:
        if not self._built:
            self._apply_size()
            if not self._built:
                return
        self._render_nodes(snap)
        self._render_arrows(snap)
        self._render_pulses(snap)
        self._render_chrome(snap)

    def _render_nodes(self, snap: Snapshot) -> None:
        c, lay, r = self.canvas, self._layout, self._layout.radius
        for p in self.replay.players:
            item = self._nodes.get(p.actor_id)
            pos = lay.of(p.actor_id)
            if item is None or pos is None:
                continue
            x, y = pos
            colour = theme.team_colour(p.team)
            alive = snap.is_alive(p.actor_id)

            if alive:
                c.itemconfigure(item["oval"], fill=colour, outline=colour, dash=())
                c.itemconfigure(item["label"], fill=theme.BACKGROUND)
                c.itemconfigure(item["dead"], state="hidden")
                c.itemconfigure(item["sub"], fill=theme.MUTED)
                rr = r
            else:
                since = snap.dead_since.get(p.actor_id, snap.t_ms)
                pop = min(1.0, max(0.0, (snap.t_ms - since) / DEATH_POP_MS))
                rr = r - (r * 0.32) * pop
                faded = theme.blend(colour, theme.BACKGROUND, 0.55)
                c.itemconfigure(
                    item["oval"],
                    fill=theme.BACKGROUND,
                    outline=faded,
                    dash=(3, 3),
                )
                c.itemconfigure(item["label"], fill=faded)
                c.itemconfigure(item["sub"], fill=theme.FAINT)
                c.itemconfigure(item["dead"], state="normal", fill=faded)
            c.coords(item["oval"], x - rr, y - rr, x + rr, y + rr)

            hovered = self._hovered == p.actor_id
            c.itemconfigure(
                item["ring"],
                state="normal" if hovered else "hidden",
                outline=theme.TEXT if hovered else "",
            )
            c.itemconfigure(
                item["ult"],
                state=(
                    "normal"
                    if (self.layers["ults"] and p.actor_id in snap.ulted_this_round)
                    else "hidden"
                ),
            )
            kills, deaths = snap.kd.get(p.actor_id, (0, 0))
            c.itemconfigure(
                item["kd"],
                text=f"{kills}/{deaths}" if self.layers["kd"] else "",
            )

    def _render_arrows(self, snap: Snapshot) -> None:
        c, lay = self.canvas, self._layout
        drawn = 0
        if self.layers["kills"]:
            faded_first = list(snap.recent_kills)
            if self.layers["trails"]:
                recent = {id(k) for k, _ in faded_first}
                faded_first += [
                    (k, 0.88) for k in snap.round_kills if id(k) not in recent
                ]
            for kill, age in faded_first:
                if drawn >= len(self._arrows):
                    break
                start = lay.of(kill.killer)
                end = lay.of(kill.victim)
                if start is None or end is None or kill.is_suicide:
                    continue
                team = self.replay.player(kill.killer)
                ramp = self._ramp.get(team.team if team else "?", self._ramp["?"])
                colour = theme.ramp_at(ramp, age)
                # Offset the curve by killer/victim order so a kill and its
                # revenge between the same pair never lie on top of each other.
                sign = 1 if kill.killer < kill.victim else -1
                c.coords(
                    self._arrows[drawn],
                    *_curve(start, end, sign * 16.0, lay.radius + 3),
                )
                c.itemconfigure(
                    self._arrows[drawn],
                    state="normal",
                    fill=colour,
                    width=max(1.0, 3.4 * (1.0 - age)),
                )
                drawn += 1
        for item in self._arrows[drawn:]:
            c.itemconfigure(item, state="hidden")

    def _render_pulses(self, snap: Snapshot) -> None:
        c, lay = self.canvas, self._layout
        used = 0
        if self.layers["ults"]:
            for actor_id, age in snap.recent_ults:
                if used >= len(self._pulses):
                    break
                pos = lay.of(actor_id)
                if pos is None:
                    continue
                x, y = pos
                rad = lay.radius * (1.0 + 1.4 * age)
                c.coords(self._pulses[used], x - rad, y - rad, x + rad, y + rad)
                c.itemconfigure(
                    self._pulses[used],
                    state="normal",
                    outline=theme.ramp_at(self._ult_ramp, age),
                    width=max(1.0, 3.0 * (1.0 - age)),
                )
                used += 1
        for item in self._pulses[used:]:
            c.itemconfigure(item, state="hidden")

    def _render_chrome(self, snap: Snapshot) -> None:
        c = self.canvas
        rnd = snap.round
        total = len(self.replay.rounds)
        if rnd is None:
            c.itemconfigure(self._chrome["banner"], text="pre-round")
        else:
            tail = "" if rnd.decided else "  ?"
            c.itemconfigure(
                self._chrome["banner"],
                text=f"ROUND {rnd.number} / {total}{tail}",
            )
        a, b = snap.score
        c.itemconfigure(self._chrome["score"], text=f"{a}  -  {b}")

        swapped = (
            self.replay.side_swap_ms is not None
            and snap.t_ms >= self.replay.side_swap_ms
        )
        c.itemconfigure(self._chrome["swap"], text="sides swapped *" if swapped else "")

        alive_a = sum(1 for p in self.replay.team(TEAM_A) if snap.is_alive(p.actor_id))
        alive_b = sum(1 for p in self.replay.team(TEAM_B) if snap.is_alive(p.actor_id))
        c.itemconfigure(self._chrome["a_head"], text="Team A *")
        c.itemconfigure(self._chrome["b_head"], text="Team B *")
        c.itemconfigure(self._chrome["a_count"], text=str(alive_a))
        c.itemconfigure(self._chrome["b_count"], text=str(alive_b))

        self._render_spike(snap)

    def _render_spike(self, snap: Snapshot) -> None:
        c = self.canvas
        if not self.layers["spike"] or snap.spike_state == "none":
            c.itemconfigure(self._chrome["spike"], fill="", outline=theme.FAINT)
            c.itemconfigure(self._chrome["spike_text"], text="")
            return
        if snap.spike_state == SPIKE_PLANTED:
            since = snap.spike_since_ms or snap.t_ms
            elapsed = max(0, snap.t_ms - since)
            # Elapsed since the plant, never a countdown: the file records the
            # plant instant but says nothing about the fuse length.
            pulse = 0.5 + 0.5 * (((elapsed // 60) % 8) / 8.0)
            fill = theme.blend(theme.SPIKE_ARMED, theme.BACKGROUND, 1.0 - pulse)
            c.itemconfigure(self._chrome["spike"], fill=fill, outline=theme.SPIKE_ARMED)
            c.itemconfigure(
                self._chrome["spike_text"],
                text=f"planted  +{elapsed // 60000}:{(elapsed // 1000) % 60:02d}",
                fill=theme.SPIKE_ARMED,
            )
        elif snap.spike_state == SPIKE_DEFUSED:
            c.itemconfigure(self._chrome["spike"], fill="", outline=theme.SPIKE_SAFE)
            c.itemconfigure(
                self._chrome["spike_text"],
                text="defused",
                fill=theme.SPIKE_SAFE,
            )
        elif snap.spike_state == SPIKE_EXPLODED:
            c.itemconfigure(
                self._chrome["spike"],
                fill=theme.SPIKE_BOOM,
                outline=theme.SPIKE_BOOM,
            )
            c.itemconfigure(
                self._chrome["spike_text"],
                text="exploded",
                fill=theme.SPIKE_BOOM,
            )

    # --- hover -----------------------------------------------------------

    def _on_motion(self, event: tk.Event) -> None:
        self._set_hover(self._hit(event.x, event.y))

    def _hit(self, x: float, y: float) -> int | None:
        r = self._layout.radius + 4
        for actor_id, (nx, ny) in self._layout.positions.items():
            if (nx - x) ** 2 + (ny - y) ** 2 <= r * r:
                return actor_id
        return None

    def _set_hover(self, actor_id: int | None) -> None:
        if actor_id == self._hovered:
            return
        self._hovered = actor_id
        if self.on_hover is not None:
            self.on_hover(actor_id)


def _curve(
    start: tuple[float, float],
    end: tuple[float, float],
    offset: float,
    trim: float = 0.0,
) -> tuple[float, ...]:
    """Three points bowing from start to end, trimmed clear of both nodes."""
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / length, dy / length
    if trim * 2 < length:
        x1, y1 = x1 + ux * trim, y1 + uy * trim
        x2, y2 = x2 - ux * trim, y2 - uy * trim
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    px, py = -uy, ux
    return (x1, y1, mx + px * offset, my + py * offset, x2, y2)
