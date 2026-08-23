"""
Reading barrier positions off a screenshot of somebody else's replay viewer.

This is the measurement behind `barriers.json` and the only module that opens
anything in `features/`.  Nothing in the app imports it; `make_barriers.py
--decode` does, once, when a new reference frame arrives.  It is kept in the
tree for the reason `csharp/TransformSearch/` is: Riot ships maps, the reference
library will grow, and a derivation that cannot be re-run is a number nobody
can check.

What the reference frames are
-----------------------------
Nine PNGs under `features/map-barriers/`, each a capture of a third-party 2D
replay viewer at round 1 with the buy-phase barriers up.  That viewer draws the
map as a wireframe -- void `(9, 15, 20)`, floor `(12, 41, 59)`, site tint
`(13, 78, 84)`, strokes `(29, 255, 231)` -- and draws each barrier as a solid
axis-aligned bar six pixels thick in one of two flat colours, Material Red 500
`(244, 67, 54)` and Material Blue 500 `(33, 150, 243)`.

The problem, and why it is a fit rather than a lookup
-----------------------------------------------------
Those bars are in *that viewer's* pixels.  Nothing states its scale, its
origin, or its rotation, and its orientation is not the radar's: measured over
the nine frames, three maps (Ascent, Haven, Split) are the radar turned a
quarter turn and six are not turned at all.  So the transform has to be
recovered from the pictures themselves, and the only thing the two images share
is the shape of the map.

`align` therefore searches the eight ways a square picture can be laid down --
four rotations, each with and without a mirror -- and within each, a scale and
an offset, maximising the overlap between the viewer's own floor and the
**alpha silhouette of Riot's radar**, which `sight` already establishes as the
map's real extent.  The winner is not close: over the nine frames the best
orientation scores 0.961 to 0.980 and the best of the other seven scores 0.438
to 0.561, a margin of at least 1.7x and usually more than 2x.  That gap is the
evidence the orientation was found rather than assumed, so `Fit` carries both
numbers into the table and `tests/test_barriers.py` asserts the gap survives.

Two details are load-bearing
----------------------------
**The transport bar is occluded, not empty.**  The viewer draws a control bar
across the bottom of the frame, and on several maps the map continues behind
it.  Scored as though that region were void, the fit is pulled several pixels
and one map (Pearl) loses its whole lower half to a stray wide row and lands at
0.48.  So the bar's own band is carried through the search as a *known* mask
and excluded from both halves of the ratio: those pixels say nothing either
way.

**A bar is thin, long and solid, and the filter says so in those terms.**  The
same two flat colours are also the ring around a player's portrait and the tick
marks on the scrub bar, and both survive a colour match.  They do not survive a
shape test: a barrier is 3 to 9 pixels on its short axis, at least 18 on its
long one, and at least 75% of its own bounding box.  Over the nine frames that
takes 76 bars and no portrait, and every one of the 76 lands on the radar's
playable floor -- which is the check that matters, and the one
`tests/test_barriers.py` keeps.

What it cannot see
------------------
A barrier hidden behind the transport bar is not in the table.  Fracture is the
visible case: it is the one map with two attacker spawns, the frame shows a bar
clipped to eleven pixels at the bar's top edge, and the shape filter drops it
rather than record a bar whose length was set by a piece of UI.  A short table
is honest; a bar of invented length is not.  The remedy is another screenshot,
and `barriers.json` is hand-editable so one can be added by hand meanwhile.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from vrfview import barriers, sight

# The reference viewer's own palette, matched within `PALETTE_TOL` per pixel as
# a Manhattan distance over RGB.  These are flat UI fills rather than
# photographs, so the tolerance only has to cover PNG rounding.
VIEWER_VOID = (9, 15, 20)
VIEWER_CHROME = (16, 25, 39)
PALETTE_TOL = 6

# The two barrier inks, and the tolerance that separates them from everything
# else on the frame.  36 is wide enough to take the antialiased shoulder of a
# bar and far narrower than the distance to any other flat colour the viewer
# uses -- the nearest is the scrub bar's own blue at 158 away.
BARRIER_INK: dict[barriers.Side, tuple[int, int, int]] = {
    "attack": (244, 67, 54),
    "defence": (33, 150, 243),
}
INK_TOL = 36

# Where a mask byte counts as set.  The masks here are made by `point` and are
# already 0 or 255, so this only has to sit between them -- it is a name for
# the midpoint rather than a threshold anything was tuned to.
MASK_ON = 127

# What separates a barrier from a player's team ring and a scrub-bar tick.  See
# the module docstring: these are a shape test, not a colour one.
MIN_THICK, MAX_THICK = 3, 9
MIN_LENGTH = 18
MIN_FILL = 0.75

# Finding the viewer's control bar.  It is drawn in VIEWER_CHROME, it is about
# 938 pixels wide on every frame, and it always sits in the bottom stripe --
# measured, the highest of the nine starts at 88% of the frame height.  The
# same colour is also the background of a player's name pill up at spawn, which
# is why the search is confined to the stripe and why a row has to carry more
# of the colour than a row of pills ever does.
CHROME_STRIPE = 0.80
CHROME_ROW_MIN = 300

# The orientations a reference frame is tried in.  Four rotations, each with
# and without a mirror.  The mirrors are searched even though no frame has ever
# needed one, because leaving them out would make "no frame is mirrored" an
# assumption rather than the eight-way result it is.
ORIENTATIONS = (
    "none",
    "r90",
    "r180",
    "r270",
    "flip",
    "flip_r90",
    "flip_r180",
    "flip_r270",
)

# The staircase the search walks: pick the orientation cheaply on a small grid,
# then refine the winner alone at rising resolution.  The alternative -- taking
# every orientation to full resolution -- is eight times the work for an answer
# the 96-pixel pass already separates by a factor of two.
ORIENT_GRID = 96
REFINE = ((192, (10.0, 4.0)), (256, (4.0, 1.5)), (384, (1.5, 0.5)))

# The radar side the fit is expressed against.  Every published minimap.png is
# 1024 square; `Fit.scale` and the offsets are in those pixels, and `Barrier`
# stores uv so nothing downstream has to know this number.
RADAR_SIZE = 1024


@dataclass(frozen=True, slots=True)
class Reference:
    """One reference frame, reduced to the two masks the search needs."""

    path: Path
    # Floor in the red channel, "not hidden by the control bar" in the green:
    # packed into one RGB image so a candidate placement warps both in a single
    # transform rather than two.
    packed: object
    width: int
    height: int
    chrome_top: int


def read_reference(path: Path) -> Reference:
    """
    A reference frame as its floor mask and its occlusion mask.

    Floor is simply "not the viewer's void colour", which takes the navy floor,
    the site tint and the cyan strokes together -- the same silhouette Riot's
    alpha channel carries, drawn by a different program.  Player portraits and
    name pills are inside it and are left in: they sit on spawn, which is
    floor, and they are under 1% of the mask.
    """
    from PIL import Image, ImageChops  # noqa: PLC0415  (see vrfview/walls.wall_ink)

    image = Image.open(path).convert("RGB")
    width, height = image.size
    floor = ImageChops.invert(_within(image, VIEWER_VOID, PALETTE_TOL))
    chrome_top = _chrome_top(_within(image, VIEWER_CHROME, PALETTE_TOL // 2), height)

    known = Image.new("L", (width, height), 255)
    if chrome_top < height:
        known.paste(0, (0, chrome_top, width, height))
    packed = Image.merge("RGB", (ImageChops.multiply(floor, known), known, known))
    return Reference(path, packed, width, height, chrome_top)


def _within(image, target: tuple[int, int, int], tol: int):
    """An `"L"` mask, 255 where the pixel is within `tol` of `target`."""
    from PIL import Image, ImageChops  # noqa: PLC0415  (see above)

    diff = ImageChops.difference(image, Image.new("RGB", image.size, target))
    red, green, blue = diff.split()
    total = ImageChops.add(ImageChops.add(red, green), blue)
    return total.point(lambda p: 255 if p <= tol else 0)


def _chrome_top(chrome, height: int) -> int:
    """
    The first row of the viewer's control bar, or `height` if it draws none.

    The topmost row *in the bottom stripe* carrying enough of the chrome
    colour, rather than the top of a contiguous run: the bar's own buttons are
    a different colour and break the run in the middle, which reads as a bar
    eighty pixels shorter than it is and leaves a slab of UI scored as map.
    """
    pixels = chrome.load()
    width = chrome.size[0]
    rows = [
        y
        for y in range(int(CHROME_STRIPE * height), height)
        if sum(1 for x in range(0, width, 2) if pixels[x, y] > MASK_ON) * 2
        > CHROME_ROW_MIN
    ]
    return min(rows) if rows else height


def oriented(image, key: str):
    """One of the eight ways to lay a picture down, by name."""
    from PIL import Image  # noqa: PLC0415  (see above)

    if key.startswith("flip"):
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        key = key[5:] or "none"
    turn = {
        "r90": Image.Transpose.ROTATE_90,
        "r180": Image.Transpose.ROTATE_180,
        "r270": Image.Transpose.ROTATE_270,
    }.get(key)
    return image.transpose(turn) if turn else image


def oriented_point(
    x: float,
    y: float,
    width: int,
    height: int,
    key: str,
) -> tuple[float, float]:
    """
    Where `oriented` sends one point, so a bar can follow its own picture.

    These four mappings are the arithmetic behind Pillow's transposes and they
    were **checked against Pillow rather than derived on paper** -- a rotation
    named for its direction is exactly the kind of thing that is off by a
    quarter turn in a way that still looks plausible.  `ROTATE_90` is
    counter-clockwise, and the test that fixed each of these is in
    `tests/test_barriers.py`.
    """
    if key.startswith("flip"):
        x = width - 1 - x
        key = key[5:] or "none"
    if key == "none":
        return x, y
    if key == "r90":
        return y, width - 1 - x
    if key == "r180":
        return width - 1 - x, height - 1 - y
    if key == "r270":
        return height - 1 - y, x
    message = f"unknown orientation {key!r}"
    raise ValueError(message)


def radar_silhouette(path: Path):
    """The radar's alpha silhouette: the map's real extent, at 1024."""
    from PIL import Image  # noqa: PLC0415  (see above)

    with Image.open(path) as source:
        source.load()
        alpha = source.convert("RGBA").getchannel("A")
    return alpha.point(lambda a: 255 if a >= sight.ALPHA_FLOOR else 0)


def align(reference: Reference, silhouette) -> barriers.Fit:
    """
    Place a reference frame onto a radar, and say how well and against what.

    Returns the winning orientation with its scale and offset in radar pixels,
    plus the best score any *other* orientation reached.  The second number is
    not decoration: it is the whole argument that this is a measurement, and
    `make_barriers` prints it beside the first.
    """
    from PIL import Image  # noqa: PLC0415  (see above)

    cache = {RADAR_SIZE: silhouette}

    def radar_at(size: int):
        if size not in cache:
            cache[size] = silhouette.resize((size, size), Image.Resampling.NEAREST)
        return cache[size]

    box = silhouette.getbbox()
    ranked = []
    for key in ORIENTATIONS:
        packed = oriented(reference.packed, key)
        score = _scorer(packed, radar_at)
        ranked.append((*_seek(packed, box, score), key))
    ranked.sort(reverse=True)

    (_, scale, tx, ty, key), (runner_iou, *_, runner_key) = ranked[0], ranked[1]
    score = _scorer(oriented(reference.packed, key), radar_at)
    for size, steps in REFINE:
        for step in steps:
            for _ in range(5):
                _, scale, tx, ty = max(
                    (
                        score(scale * (1 + ds), tx + dx, ty + dy, size),
                        scale * (1 + ds),
                        tx + dx,
                        ty + dy,
                    )
                    for ds in (-0.008, -0.003, -0.001, 0.0, 0.001, 0.003, 0.008)
                    for dx in (-step, 0.0, step)
                    for dy in (-step, 0.0, step)
                )
    return barriers.Fit(
        orient=key,
        scale=scale,
        tx=tx,
        ty=ty,
        iou=score(scale, tx, ty, RADAR_SIZE),
        runner_up=runner_key,
        runner_up_iou=runner_iou,
    )


def _scorer(packed, radar_at):
    """
    Overlap between a placed reference frame and the radar, ignoring the UI.

    Intersection over union, with both halves multiplied by the warped *known*
    mask so the control bar's band counts in neither.  Scoring it as void
    instead is what broke the first pass of this: see the module docstring.
    """
    from PIL import Image, ImageChops  # noqa: PLC0415  (see above)

    def score(scale: float, tx: float, ty: float, size: int) -> float:
        radar = radar_at(size)
        k = size / RADAR_SIZE
        inv = 1.0 / (scale * k)
        warped = packed.transform(
            (size, size),
            Image.Transform.AFFINE,
            (inv, 0, -tx * k * inv, 0, inv, -ty * k * inv),
            Image.Resampling.NEAREST,
        )
        floor, known, _ = warped.split()
        floor = floor.point(lambda p: 255 if p > MASK_ON else 0)
        known = known.point(lambda p: 255 if p > MASK_ON else 0)
        both = ImageChops.multiply(ImageChops.multiply(floor, radar), known)
        either = ImageChops.multiply(ImageChops.lighter(floor, radar), known)
        union = either.histogram()[255]
        return both.histogram()[255] / union if union else 0.0

    return score


def _seek(packed, box, score) -> tuple[float, float, float, float]:
    """
    A coarse sweep for one orientation: the best `(iou, scale, tx, ty)` found.

    Seeded from the two bounding boxes -- the reference frame's visible floor
    against the radar's silhouette -- which puts the right answer within a few
    percent, and then swept wide enough around it that a contaminated box
    cannot strand the search.
    """
    visible = packed.getchannel("R").getbbox()
    guess = (
        (box[2] - box[0]) / (visible[2] - visible[0])
        + (box[3] - box[1]) / (visible[3] - visible[1])
    ) / 2
    best = (0.0, guess, 0.0, 0.0)
    for step in range(-4, 5):
        scale = guess * (1 + step * 0.025)
        tx0 = box[0] - scale * visible[0]
        ty0 = box[1] - scale * visible[1]
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                tx, ty = tx0 + dx * 14, ty0 + dy * 14
                found = (score(scale, tx, ty, ORIENT_GRID), scale, tx, ty)
                best = max(best, found)
    return best


def bars(reference: Reference) -> list[tuple[barriers.Side, tuple[int, int, int, int]]]:
    """
    Every barrier on a reference frame, in that frame's own pixels.

    Connected components of each ink, kept only where the component is thin,
    long and solidly filled.  Anything below the control bar is not looked at:
    a bar the UI has clipped would be recorded shorter than it is.
    """
    from PIL import Image  # noqa: PLC0415  (see above)

    image = Image.open(reference.path).convert("RGB")
    found = []
    for side, ink in BARRIER_INK.items():
        mask = _within(image, ink, INK_TOL)
        for box, filled in _components(mask, reference.width, reference.chrome_top):
            x0, y0, x1, y1 = box
            wide, tall = x1 - x0 + 1, y1 - y0 + 1
            thick, length = min(wide, tall), max(wide, tall)
            if not MIN_THICK <= thick <= MAX_THICK or length < MIN_LENGTH:
                continue
            if filled / (wide * tall) < MIN_FILL:
                continue
            found.append((side, box))
    return found


def _components(mask, width: int, height: int):
    """
    Four-connected runs of a mask, as `((x0, y0, x1, y1), pixel count)`.

    Four-connected rather than eight, so two bars meeting at a corner stay two
    bars.  Written out here rather than reached for in a library because
    Pillow has no labeller and a barrier is the only thing in this project that
    has ever needed one.
    """
    pixels = mask.load()
    seen = bytearray(width * height)
    for start_y in range(height):
        for start_x in range(width):
            if pixels[start_x, start_y] <= MASK_ON or seen[start_y * width + start_x]:
                continue
            seen[start_y * width + start_x] = 1
            queue = deque([(start_x, start_y)])
            x0 = x1 = start_x
            y0 = y1 = start_y
            filled = 0
            while queue:
                x, y = queue.popleft()
                filled += 1
                x0, x1 = min(x0, x), max(x1, x)
                y0, y1 = min(y0, y), max(y1, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if not (0 <= nx < width and 0 <= ny < height):
                        continue
                    if pixels[nx, ny] > MASK_ON and not seen[ny * width + nx]:
                        seen[ny * width + nx] = 1
                        queue.append((nx, ny))
            yield (x0, y0, x1, y1), filled


def project(
    box: tuple[int, int, int, int],
    reference: Reference,
    fit: barriers.Fit,
) -> tuple[float, float, float, float]:
    """
    One bar's box, carried from frame pixels into radar uv.

    All four corners go through the orientation and then the scale, and the
    result is re-boxed, rather than the two opposite corners being transformed
    on their own: under a quarter turn the corner that was top-left is not, and
    a rectangle built from the wrong pair comes out inside out.
    """
    x0, y0, x1, y1 = box
    corners = [
        oriented_point(x, y, reference.width, reference.height, fit.orient)
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
    ]
    xs = [fit.scale * x + fit.tx for x, _ in corners]
    ys = [fit.scale * y + fit.ty for _, y in corners]
    return (
        min(xs) / RADAR_SIZE,
        min(ys) / RADAR_SIZE,
        max(xs) / RADAR_SIZE,
        max(ys) / RADAR_SIZE,
    )


def decode(name: str, reference_path: Path, radar_path: Path) -> barriers.MapBarriers:
    """One map, from a reference frame and a radar, to a table row."""
    reference = read_reference(reference_path)
    fit = align(reference, radar_silhouette(radar_path))
    rows = [
        barriers.Barrier(side, *project(box, reference, fit))
        for side, box in bars(reference)
    ]
    rows.sort(key=lambda b: (b.side, round(b.v0, 4), round(b.u0, 4)))
    return barriers.MapBarriers(
        name=name,
        reference=reference_path.as_posix(),
        fit=fit,
        barriers=tuple(rows),
    )


def on_floor(barrier: barriers.Barrier, silhouette, samples: int = 21) -> float:
    """
    How much of a barrier's centreline lands on the radar's playable floor.

    The ground truth for this whole exercise, and the same argument
    `tracks._plants_from` makes for a decoded spike: a barrier closes a
    doorway, a doorway is floor, and a coordinate that came out of a bad fit
    would land in the void a third of the time.  Over the nine reference frames
    all 76 bars score at least 0.90 here.
    """
    x0, y0, x1, y1 = barrier.rect(RADAR_SIZE)
    pixels = silhouette.load()
    hits = 0
    for step in range(samples):
        t = step / (samples - 1)
        if x1 - x0 >= y1 - y0:
            x, y = x0 + t * (x1 - x0), (y0 + y1) / 2
        else:
            x, y = (x0 + x1) / 2, y0 + t * (y1 - y0)
        ix, iy = int(x), int(y)
        if 0 <= ix < RADAR_SIZE and 0 <= iy < RADAR_SIZE and pixels[ix, iy] > MASK_ON:
            hits += 1
    return hits / samples
