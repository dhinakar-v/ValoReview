"""
Colours, and the arithmetic that stands in for an alpha channel.

A Tk canvas has no alpha: an item is drawn at full opacity or not at all.
Fading therefore has to be done by mixing the accent colour toward the
background and re-setting the item's colour, which is what `blend` does.
`ramp` precomputes the steps once at startup so a fading kill arrow costs a
list index per frame rather than a string format.

On the palette
--------------
Team colours are blue and coral, deliberately not Valorant's attacker red and
defender green.  Which team attacked is not recoverable from the file -- spike
events carry no actor ID -- so using the sides' familiar colours would assert
something the data does not support.
"""

from __future__ import annotations

BACKGROUND = "#12141a"
PANEL = "#1b1e27"
PANEL_EDGE = "#2a2f3d"
TEXT = "#d7dae3"
MUTED = "#7d8496"
FAINT = "#4a5162"

TEAM_COLOURS = {"A": "#4ea3ff", "B": "#ff6b5a", "?": "#8a90a2"}

# The brief's own palette, used by the CustomTkinter pages (vrfhome.cards and
# the Phase 6 viewer).  The canvas constants above stay as they are: they are
# the canvas palette -- the minimap, the strip, the map reference -- and the
# two are drawn by different toolkits.
#
# The brief names accent-red ATK and accent-blue DEF.  Those *semantics* are
# not adopted -- which team attacked is not recoverable from the file -- so the
# two colours are team A and team B here, and every label that shows them says
# A or B.  The hues are the brief's; the meaning is what the data supports.
APP_BG = "#0d0d0d"
CARD_BG = "#161616"
CARD_HOVER = "#1f1f1f"
TEXT_PRIMARY = "#ece8e1"
TEXT_MUTED = "#7b7b7b"
BORDER = "#2a2a2a"
TOOLTIP_BG = "#1a1a1a"
ACCENT_A = "#4d9eff"
ACCENT_B = "#ff4655"
ACCENT_OK = "#5ddba0"

ULT = "#ffd166"
SPIKE_ARMED = "#ff5252"
SPIKE_SAFE = "#5ddba0"
SPIKE_BOOM = "#ff9f45"
PLAYHEAD = "#ffffff"
ACCENT = "#8b7bd8"

RAMP_STEPS = 16

# A fade needs a start and an end; fewer steps than that is just the colour.
_MIN_RAMP_STEPS = 2


def _to_rgb(colour: str) -> tuple[int, int, int]:
    c = colour.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def blend(colour: str, toward: str, t: float) -> str:
    """Mix `colour` toward `toward` by `t` in 0..1, as a #rrggbb string."""
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    r1, g1, b1 = _to_rgb(colour)
    r2, g2, b2 = _to_rgb(toward)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def ramp(colour: str, toward: str = BACKGROUND, steps: int = RAMP_STEPS) -> list[str]:
    """Precomputed fade from `colour` to `toward`, `steps` entries long."""
    if steps < _MIN_RAMP_STEPS:
        return [colour]
    return [blend(colour, toward, i / (steps - 1)) for i in range(steps)]


def ramp_at(table: list[str], age: float) -> str:
    """Pick the ramp entry for an age in 0..1."""
    if not table:
        return TEXT
    i = int(age * (len(table) - 1))
    return table[0 if i < 0 else (len(table) - 1 if i >= len(table) else i)]


def team_colour(team: str) -> str:
    return TEAM_COLOURS.get(team, TEAM_COLOURS["?"])
