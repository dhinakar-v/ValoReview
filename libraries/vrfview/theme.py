"""
Colours, and the arithmetic that stands in for an alpha channel.

A Tk canvas has no alpha: an item is drawn at full opacity or not at all.
Fading therefore has to be done by mixing the accent colour toward the
background and re-setting the item's colour, which is what `blend` does.
`ramp` precomputes the steps once at startup so a fading kill arrow costs a
list index per frame rather than a string format.

On the palette
--------------
Team colours are Valorant's attacker red and defender blue, and the browser
interface labels them ATK and DEF.  **Neither the colour nor the label is read
from the file.**  Which team attacked is not recoverable -- spike events carry
no actor ID -- so `infer` two-colours the kill graph into A and B, and the web
interface assigns A to the attacking side.  That assignment is part of the
generated layer `web/src/model/synthetic.ts` owns and is marked on the page as
such; the model underneath still says A and B and knows nothing about sides.

They were blue and coral for exactly this reason until the interface grew a
place to say so.  The pair still has to stay far apart in hue: `minimap.spec.ts`
counts a marker within 36 RGB of a team colour and `scene.spec.ts` identifies
one by hue after 3D lighting, so moving either toward grey or toward the other
fails both.  Red against blue is further apart than blue against coral was.

The surfaces are a ramp, not a handful of flat greys.  The brief named five
(background, panel, hover, border, tooltip) and an interface built from five
has nowhere to put the states it actually has: a panel raised above a page, a
row hovered inside that panel, an input sunk below it, a divider that has to
read as stronger than a hairline.  Every one of those was previously the same
`#1f1f1f`, which is why the old page read flat.  So there are six steps from
`APP_BG` up to `FIELD_BG` and three text weights down from `TEXT_PRIMARY`, and
each is one deliberate stop from the one beside it.

There used to be two palettes in this file, one per surface the desktop app
drew on.  They are one ramp now, and the desktop app is gone: what reads these
constants today is `scripts/make_theme.py`, which writes them into
`web/src/theme.generated.css`.  The file stays here rather than moving into the
generator because the palette carries an argument -- see the paragraph above --
and the values and the reason belong together.
"""

from __future__ import annotations

# Surfaces, dark to light.  The canvas sits one step *below* the page, so a
# minimap reads as a hole cut in the interface rather than a card on it.
BACKGROUND = "#08090b"
PANEL = "#101216"
PANEL_EDGE = "#262b34"
TEXT = "#e8eaed"
MUTED = "#a2a9b4"
FAINT = "#4b515c"

TEAM_COLOURS = {"A": "#ff4655", "B": "#3e8bff", "?": "#8a90a2"}

# The page's own ramp.  The hues descend from the brief -- its blue and its red
# are still here -- but the greys are a scale rather than the brief's five flat
# values, for the reason in the module docstring.
#
# The brief names accent-red as the attacking side and accent-blue as the
# defending one.  `ACCENT_A` and `ACCENT_B` are the page's own two accents and
# are not the team pair above: `TEAM_COLOURS` is what a marker is drawn in and
# what the pixel specs measure, and these two are for chips, links and the
# playhead.  Keeping them separate is what let the team pair move to red and
# blue without every neutral accent on the page following it.
APP_BG = "#0a0b0d"
CARD_BG = "#101216"
CARD_HOVER = "#171a20"
FIELD_BG = "#1e222a"
TEXT_PRIMARY = "#e8eaed"
TEXT_MUTED = "#a2a9b4"
TEXT_FAINT = "#6b7280"
BORDER = "#262b34"
LINE_STRONG = "#333a45"
TOOLTIP_BG = "#12151b"
ACCENT_A = "#4d9eff"
ACCENT_B = "#ff4655"
ACCENT_OK = "#3ecf8e"
ACCENT_WARN = "#f5a623"

ULT = "#ffd166"

# The spike is amber, and that is a constraint rather than a taste.
#
# These three were picked when the team pair was blue and coral, and an armed
# spike could be red without colliding with anything.  Team A is now Valorant's
# attacker red (#ff4655), and the old SPIKE_ARMED was #ff5252 -- **12 RGB
# away**, inside the 36 that `minimap.spec.ts` counts as "this pixel is a team
# marker".  So a planted spike drawn in it was not merely hard to tell from an
# attacker; it was arithmetically the same colour, and the pixel suite would
# have counted every one of its pixels as a player drawn somewhere no player
# was.  Amber is 90 away from team A and 269 from team B, reads as armed rather
# than as either side, and is what Valorant's own planted-spike UI uses.
#
# The three stay far apart from each other too (47 between armed and boom), so
# the rail tick that carries one of them says which event it is.
SPIKE_ARMED = "#ff9f45"
SPIKE_SAFE = "#3ecf8e"
SPIKE_BOOM = "#ff7043"
PLAYHEAD = "#ffffff"
ACCENT = "#7c8cff"

# What the pointer is on, and it is a colour rather than a size.
#
# A hovered marker used to be drawn at PICKED_SCALE -- three times across --
# which is right for a marker somebody *pinned* and wrong for one the mouse
# merely passed over: sweeping a five-man stack inflated one portrait after
# another to 104px, each one covering the neighbours the reader was trying to
# tell apart, and the roster raises the same state, so pointing at a card blew
# up a marker somewhere else on the map.  An outline says the same thing and
# moves nothing.
#
# It is magenta because it has to contrast with *both* sides at once and with
# the map under them, and the warm end of this palette cannot: an orange ring
# around an attacker is a ring drawn in nearly the marker's own hue, which is
# exactly what it was on the first attempt.  Magenta is the farthest this
# canvas has room for -- 172 RGB from TEAM_COLOURS["A"] and 191 from ["B"],
# 182 from TEXT (which is what a *pinned* ring is drawn in), and 161 from the
# nearest thing on the whole canvas, which is TEAM_COLOURS["?"].  Every one of
# those is far outside the 36 `minimap.spec.ts` counts as "this pixel is a
# player".
#
# It is also the one colour `sight.py` refuses to produce: compositing the two
# side washes additively would give magenta, which is why SIDE_ORDER makes one
# side win outright instead.  That was written when magenta meant nothing here.
# It now means "the pointer is on this", so the rule holds harder than before.
HOVER = "#e935ff"

# The wordmark, and the one red on the page that is not a claim about a match.
#
# It is Valorant's own red rather than a fifth hue because the product is named
# after the game and reads its files, and a mark in a colour the game does not
# use would be the one thing on this page pretending to be from somewhere else.
# That it equals ACCENT_A is the point and not a duplication waiting to be
# folded: ACCENT_A is a *page* accent and may move with the interface, while
# this one is fixed by what it refers to, and collapsing them would let a
# palette tweak repaint the logo.
#
# It is deliberately **not** a team colour, even though the value matches
# TEAM_COLOURS["A"] today.  Nothing in the app bar is drawn on a canvas, so the
# 36-RGB proximity rule that `minimap.spec.ts` and `scene.spec.ts` enforce does
# not reach it -- but a reader comparing hexes should know the collision is
# outside their scope rather than an oversight inside it.
BRAND = "#ff4655"

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
