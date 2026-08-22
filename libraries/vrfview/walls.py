"""
The wall lines Riot draws on a radar, read back off the picture.

Every published `minimap.png` draws its walls.  Measured over all 18 radars in
the reference `assets/`, each 1024x1024 RGBA:

  * the void outside the map is alpha 0 -- 47% of Kasbah, 72% of Bind;
  * the playable floor is *exactly* `(118, 118, 118)`, 69% to 79% of every
    opaque pixel, with elevation tiers stepping up through 139, 145 and 152;
  * the lines are white, one to three pixels wide, and 1.6% to 4.1% of the
    frame.  46% to 84% of the pixels taken here are exactly `(255, 255, 255)`
    and 75% to 95% are above luminance 200; the remainder is the antialiased
    shoulder of those same lines and the dimmer lines drawn on raised storeys.

`sight.SightMap.from_image` folds what this extracts into the same bitmask as
the alpha silhouette, so a cone stops at the interior walls the silhouette
misses.  `scripts/make_walls.py` also writes it to `assets/maps/<Map>/walls.png`,
one per map, which is a picture for a person to look at -- nothing reads those
files back, and the raycaster re-derives.

A brightness threshold is not enough, and that is measured
----------------------------------------------------------
The obvious rule is "bright pixels are ink", and it was the first one here: the
luminance histogram is trimodal and the region from 155 to 250 holds only about
2% of the opaque pixels, so a cut at 200 looks unarguable.

It misses lines.  Riot draws over *elevation tiers* as well as over the base
floor, and a line drawn on a raised storey is dimmer than one drawn on the
floor -- around 179 to 188 where the plain ones are 255.  Auditing the band
just under the cut, against the 18 maps, that is up to 13.3% of Icebox's ink,
9.8% of Ascent's and 9.1% of District's simply not taken: real, structured,
closed lines, invisible unless you go looking for what was left behind.

Lowering the cut cannot fix it.  Some *areas* are as bright as some lines --
Icebox's raised platforms are a filled 186 -- so any global value either drops
the dim lines or floods the bright floors.  The separating property is not
brightness but **local contrast**: a line is brighter than what surrounds it,
whatever it is drawn on, and it is thin.  That is a white top-hat, and it takes
the dim lines while leaving the tiers alone.  Missed ink falls to zero on nine
maps and to 203 pixels of 32,885 on Icebox.

What the ink costs, and it is not free
--------------------------------------
These lines are the occluder, and they are a **worse** occluder than the
silhouette alone.  That is measured, it is not close, and anybody touching this
module should know the number before they trust a cone.

The ground truth is the one this project always uses: at every
`characterDeath` the killer could see the victim.  Over 3,128 kills in the 21
playable captures, counting the sightlines each mask wrongly closes:

    alpha silhouette alone           1.05%     <- what ships
    + the ink, 256 grid             38.17%
    + the ink, 512 grid             34.14%
    + the ink, 1024 grid            31.27%     <- not a resolution problem
    + interior ink only, 256 grid   37.15%     <- not the map rim either
    + ink eroded to >=3px wide       4.60%     <- keeps 20,838 px of 233,171

The reading is not that the extraction is wrong -- `--overlay` shows it tracing
the lines cleanly and closing them.  It is that **Riot already encodes opaque
geometry as the silhouette**: a wall you cannot see through is a *hole* in the
radar, which is why alpha alone is right at 99% of real kills.  What the lines
mark on top of the floor is the map's readable detail -- doorframes, crates,
ledges, stair treads, the lip of a raised platform -- and a quarter of all
kills in Valorant are through or over one of those.

So the trade is a cone that stops at interior structure, which is the picture
that was asked for and the more useful one to look at, against a cone that
stops short of things a bullet would not.  Both rates are pinned by
`tests/test_positions.py::WhatTheDrawnLinesCost`, which is the whole of what
this project can honestly do about it.

The last row closes off the obvious rescue.  Thick ink is not a different
population from thin ink -- eroding to lines at least three pixels wide throws
away 91% of the ink and is still four times worse than the silhouette, and
eroding one step further keeps 210 pixels across eight maps, at which point it
scores well by having kept nothing.

Every one of these is worse than the brightness rule this module started with,
which scored 31.97% at the 256 grid.  That is the expected direction and worth
saying out loud: the rule below takes *more* of what Riot drew, and taking more
of it makes line of sight worse, which is itself evidence about what the lines
are.

`tests/test_positions.py::WhatTheDrawnLinesCost` is the standing check on both
halves -- that the silhouette is right, and what the lines cost on top of it --
so a change here that quietly makes sight worse fails with the numbers in front
of it.

Everything here is one Pillow call per step and none of it loops in Python, so
a caller can afford to re-derive rather than cache.
"""

from __future__ import annotations

# An opaque pixel has to be at least this bright to be ink at all.  This is the
# one absolute number left and it sits above every floor tier the palette scan
# found -- 118 base, then 139, 145 and 152 -- and below the dimmest line
# measured, which is about 179.  It exists so that contrast alone cannot pick
# out a dark feature that merely happens to be surrounded by something darker.
INK_FLOOR = 160

# ...and this much brighter than what surrounds it, out of 255.  The step from
# the base floor to the brightest tier is 34, so a value below that would take
# every tier boundary; the dimmest line stands about 60 above the tier it is
# drawn on.  25 sits between those two, nearer the smaller, because a line's
# own antialiased shoulder has to come with it or the line arrives dashed.
INK_CONTRAST = 25

# How far out "surrounds it" reaches, in pixels, as the side of the square the
# opening uses.  A bright structure *wider* than this is a floor, not a line:
# the opening keeps it, so the top-hat subtracts it away to nothing.  Lines are
# one to three pixels wide and the widest tier is hundreds, so this only has to
# land somewhere in between -- 9 is comfortably clear of both.
INK_WINDOW = 9

# The base floor grey, used to fill the void before the opening runs.  Without
# it the transparent surround reads as pitch black, every pixel along the
# silhouette rim stands 118 above its own neighbourhood, and a band of plain
# floor is taken as ink all the way around the map.
FLOOR_GREY = 118

# How much of a working-grid cell has to be ink, out of 255, before
# `wall_cells` calls the cell wall.  The full-resolution mask is box-*averaged*
# down, so this reads as a coverage fraction: a two-pixel line crossing a 4x4
# block covers 8/16 and arrives at 128, a one-pixel line covers 4/16 and
# arrives at 64, and a line merely clipping a corner arrives at 16.
#
# 1 is a plain max-pool -- any ink at all -- and that is the right default for
# a mask whose job is to lose nothing.  It is deliberately *not* tuned: the
# measurement above swept it from 1 to 160 and the answer never came near the
# silhouette's, so there is no value here that would make the ink an occluder
# and picking one would only make it look as though there were.
POOL_FLOOR = 1

# The working grid and the alpha cutoff belong to `sight` and are passed in
# rather than imported, with no default on either.  Both numbers are already
# published -- they sit in the golden fixture's constants block and travel with
# the mask itself -- so a default here would be a second place the occluder's
# numbers could come from.


def wall_ink(image, *, alpha_floor: int):
    """
    One radar's drawn lines at full resolution, as an `"L"` mask, 255 where ink.

    Three tests, and a pixel has to pass all of them: it is opaque, it is at
    least `INK_FLOOR` bright, and it stands `INK_CONTRAST` above the darkest
    thing within `INK_WINDOW` of it.  The third is what makes this work on a
    raised storey as well as on the base floor -- see the module docstring.

    Pillow is imported in the body for the reason `sight.SightMap.from_path`
    gives: a caller may have no image library, and everything else that touches
    occlusion is arithmetic over bytes.  `alpha_floor` is `sight.ALPHA_FLOOR`,
    handed in rather than imported.
    """
    from PIL import Image, ImageChops, ImageFilter  # noqa: PLC0415  (see above)

    rgba = image.convert("RGBA")
    opaque = rgba.getchannel("A").point(lambda a: 255 if a >= alpha_floor else 0)

    # The void is filled with floor grey rather than left black, or the whole
    # silhouette rim reads as a bright ridge.  See FLOOR_GREY.
    flat = Image.new("L", rgba.size, FLOOR_GREY)
    flat.paste(rgba.convert("L"), mask=opaque)

    window = min(INK_WINDOW, _odd_at_most(min(rgba.size)))
    opened = flat.filter(ImageFilter.MinFilter(window)).filter(
        ImageFilter.MaxFilter(window),
    )
    ridge = ImageChops.subtract(flat, opened).point(
        lambda p: 255 if p >= INK_CONTRAST else 0,
    )
    bright = flat.point(lambda p: 255 if p >= INK_FLOOR else 0)
    return ImageChops.multiply(ImageChops.multiply(ridge, bright), opaque)


def _odd_at_most(size: int) -> int:
    """
    The largest odd window an image this small can carry, and at least 3.

    Pillow's rank filters read a full square around every pixel, so a window
    wider than the image itself is not a smaller effect -- it is an error.  A
    radar is 1024 and never reaches this; a synthetic fixture is eight pixels
    across and always does.
    """
    return max(3, size - (size + 1) % 2)


def wall_cells(image, size: int, *, alpha_floor: int) -> bytes:
    """
    The same lines on a square working grid, one byte per cell, 1 = wall.

    The downsample is the load-bearing step and it is a *box average*, not the
    plain resize `SightMap` uses for alpha.  A two-pixel line taken from 1024
    to 256 by the default bicubic filter averages straight back into the floor
    band and vanishes -- the mask would come out empty and whatever was reading
    it would silently do nothing.  Box-averaging keeps a cell's ink coverage as
    a number, and `POOL_FLOOR` is where that number becomes a wall.

    Nothing in the app calls this.  It exists so the measurement in
    `tests/test_positions.py` can build the occluder the ink *would* make and
    show what it costs, which is a claim that has to be re-checkable rather
    than a paragraph of prose.
    """
    from PIL import Image  # noqa: PLC0415  (see `wall_ink`)

    ink = wall_ink(image, alpha_floor=alpha_floor)
    pooled = ink.resize((size, size), Image.Resampling.BOX)
    return bytes(1 if p >= POOL_FLOOR else 0 for p in pooled.tobytes())
