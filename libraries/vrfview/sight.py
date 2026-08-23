"""
An approximate sight cone, raycast against what the radar image draws.

This project has no collision data.  There is no navmesh and no height
information anywhere in `assets/` -- a map entry is a radar PNG, four transform
scalars and a list of point callouts, and that is the entire spatial model.  A
true line of sight is therefore not implementable here, and this module does
not claim to be one.

What it does have is two readings off the picture.  Every `minimap.png` Riot
publishes is RGBA, and the area outside the playable space is *fully
transparent*: 57% of Abyss, 67% of Ascent, 72% of Bind, 60% of Breeze.  And
inside that silhouette Riot draws the map's lines -- walls, but also doorframes,
crates and ledges -- which `walls.py` reads back.  Both are real data about the
map, published by Riot, so marching a ray until it leaves the silhouette or
crosses a drawn line gives an occluder that is measured rather than invented.

**The two halves are not equally good and the difference is measured.**  Scored
against the only ground truth there is -- at every `characterDeath` the killer
could see the victim -- the silhouette alone wrongly closes 1.05% of 3,128 real
sightlines and the drawn lines take that to 38.17%, because Riot already
encodes opaque geometry *as* the silhouette and the lines on top of the floor
are largely things you can see over.  `walls.py` carries the whole table.  The
lines are in the occluder because a cone that stops at interior structure was
asked for and is the more useful picture; what they are not is more accurate.

So the contract is narrow, and whatever draws this is drawing an
approximation:

  * transparent means outside the rendered radar, which is *usually* wall or
    void and is not the same claim as "opaque geometry blocks vision";
  * the drawn lines are not only wall: they also outline low boxes, ledges you
    can see over and the circular objective markers, so a cone stops short of
    things a bullet would not;
  * it is two-dimensional, so it cannot know about heaven, tunnels, or a box
    you can see over -- Bind's teleporters read as solid, Split's heaven reads
    as the floor beneath it;
  * a doorway narrower than the working grid closes.

`GET /api/maps/{key}/sight` sends the mask and the constants that produced it
as one document: `GRID` and `ALPHA_FLOOR` decide what "open" means and a
browser downscale is not Pillow's, so one authority answers it once.  The
geometry here is plain arithmetic over a bitmask and is tested against a
synthetic image with no display and no art cache.

Everything is in uv space
-------------------------
`art.Transform.apply` turns a world coordinate into a (u, v) fraction of the
radar image, and the alpha channel is indexed by exactly that fraction, so uv
is the one space where the picture and the positions already agree.  Angles,
however, are *not* computed in it: `forward_uv` takes a second world point one
metre ahead and pushes it through the same transform, because the transform
swaps the axes and either multiplier may be negative.  Doing the trigonometry
in uv space directly puts every cone ninety degrees out, which looks entirely
plausible on screen -- the same trap `minimap._draw_facing` documents.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from vrfview import walls

# The working grid.  The radar is 1024x1024; a quarter of that is one cell per
# ~3 screen pixels at the size the minimap actually draws, which is finer than
# the dots on top of it and cheap enough to build on every map change.
GRID = 256

# Below this the pixel is treated as void.  Riot's radars are almost entirely
# 0 or 255 -- 41% to 99% of every image is one of the two -- so the exact
# threshold is not load-bearing; it only decides the antialiased rim.
ALPHA_FLOOR = 8

# Valorant's default horizontal field of view.
FOV_DEGREES = 103.0

# One ray per this many degrees.  At 103 degrees that is 52 rays, which is
# smooth at the size the cone is drawn and costs nothing at 30 fps.
RAY_STEP_DEGREES = 2.0

# How far a ray travels before giving up, in Unreal units.  Roughly the
# diagonal of a Valorant map, so the cone is bounded by walls in practice and
# by this only when it is looking down an open lane.
MAX_RANGE_UU = 6000.0

# A player standing on the rim of the silhouette -- against a wall, in a
# doorway -- sits on a transparent cell often enough that refusing there would
# blink the cone off exactly when it matters.  The first few steps of every ray
# therefore ignore the mask.
SEED_CELLS = 2

# How far ahead the heading probe is placed, in Unreal units.  Any distance
# works; the direction is renormalised.  Matches minimap.FACING_PROBE_UU.
PROBE_UU = 100.0


@dataclass(frozen=True)
class Occluder:
    """
    A round smoke standing in the world, in uv space.

    In uv rather than world units because that is the space the ray is already
    marched in, and converting once per smoke per frame beats converting once
    per step.  `radius` is `uv_radius(transform, smoke_radius_uu)`.

    It carries no time.  Whether a smoke is still standing is decided before
    one of these is built -- by the caller that knows the clock -- so the
    raycaster stays a pure function of geometry, the way the mask is.
    """

    u: float
    v: float
    radius: float


@dataclass(frozen=True)
class SightMap:
    """
    One map's open space, as a square bitmask: the silhouette, less its lines.

    There is deliberately one bitmask and not two.  A drawn line and the void
    are the same claim to everything downstream -- `blocked` is the only
    question the raycaster ever asks -- so folding the lines in here means the
    wire format, the schema, the TypeScript port and its parity fixtures all
    carry on unchanged, and nothing has to learn a second kind of occluder.
    """

    size: int
    # Row-major, one byte per cell: 1 open, 0 blocked.
    cells: bytes

    @classmethod
    def from_image(cls, image, size: int = GRID) -> SightMap:
        """
        Build from a PIL image: the alpha silhouette, less the drawn lines.

        The two halves are read at different resolutions on purpose.  Alpha is
        downsampled first and thresholded after, which is what it has always
        done and what the browser's pixel suite has been drawn against.  The
        lines cannot survive that order -- a two-pixel line bicubic-resized to
        a quarter scale averages back into the floor and disappears -- so
        `walls.wall_cells` thresholds at full resolution and pools down.

        An image with no alpha is entirely open rather than entirely blocked:
        a radar saved as RGB is a picture we cannot derive occlusion from, and
        an unbounded cone is visibly an approximation where a cone that stops
        at the player's feet reads as a bug.  It may still have lines drawn on
        it, and those are still read.
        """
        rgba = image.convert("RGBA")
        alpha = rgba.resize((size, size)).getchannel("A").tobytes()
        drawn = walls.wall_cells(rgba, size, alpha_floor=ALPHA_FLOOR)
        cells = bytes(
            1 if a >= ALPHA_FLOOR and not w else 0
            for a, w in zip(alpha, drawn, strict=True)
        )
        return cls(size=size, cells=cells)

    @classmethod
    def from_path(cls, path, size: int = GRID) -> SightMap | None:
        """
        Build from a radar file, or None if it cannot be read.

        Here rather than in a caller because the alpha channel is the whole
        occluder model: whatever opens the PNG decides what `blocked` means,
        and that decision belongs beside `ALPHA_FLOOR`.  Pillow is imported in
        the body so the module keeps importing with no image library present --
        every other entry point on this class is pure arithmetic over `cells`.
        """
        if path is None:
            return None
        from PIL import Image  # noqa: PLC0415  (see the docstring)

        try:
            with Image.open(path) as image:
                return cls.from_image(image, size)
        except (OSError, ValueError):
            return None

    @property
    def open_fraction(self) -> float:
        return sum(self.cells) / len(self.cells) if self.cells else 0.0

    def blocked(self, u: float, v: float) -> bool:
        """
        Whether the cell at this uv fraction is outside the playable area.

        `floor`, not `int`: `int` truncates toward zero, so `int(-0.8)` is 0
        and a ray leaving the left or top edge would silently reappear in
        column or row zero instead of stopping.  On a map whose spawn sits
        near an edge that is a cone wrapping onto the far side of the image.
        """
        col = math.floor(u * self.size)
        row = math.floor(v * self.size)
        if not (0 <= col < self.size and 0 <= row < self.size):
            return True
        return not self.cells[row * self.size + col]


def forward_uv(transform, x: float, y: float, yaw: float) -> tuple[float, float]:
    """
    A unit heading in uv space, via a probe point rather than trigonometry.

    See the module docstring: the transform swaps x and y and either multiplier
    may be negative, so the only form immune to both is to move in world space
    and transform the result.
    """
    radians = math.radians(yaw)
    u0, v0 = transform.apply(x, y)
    u1, v1 = transform.apply(
        x + PROBE_UU * math.cos(radians),
        y + PROBE_UU * math.sin(radians),
    )
    du, dv = u1 - u0, v1 - v0
    # `sqrt`, not `hypot`, and that is about the TypeScript port rather than
    # about accuracy.  Both languages have a `hypot` and both specify it as
    # approximate -- CPython's is a correctly-rounded algorithm and V8's is a
    # different one -- so two implementations that each used it would be free
    # to disagree in the last bit, and a last-bit difference in a heading can
    # stop a marched ray one cell earlier.  `sqrt` is exactly specified in
    # IEEE-754 and agrees by construction.  There is no overflow to protect
    # against here: these are uv fractions, of order 1e-4.
    length = math.sqrt(du * du + dv * dv)
    if length <= 0:
        return (0.0, 0.0)
    return (du / length, dv / length)


def uv_radius(transform, distance_uu: float) -> float:
    """
    A world distance as a fraction of the radar's side.

    The two multipliers differ slightly on some maps because the radar is not
    exactly square in world terms, so this averages them: the cone's reach is
    a bound on an approximation, not a measurement anybody reads off.
    """
    scale = (abs(transform.x_multiplier) + abs(transform.y_multiplier)) / 2
    return abs(distance_uu) * scale


def cone(  # noqa: PLR0913 - see the docstring
    sight: SightMap,
    origin: tuple[float, float],
    forward: tuple[float, float],
    radius: float,
    *,
    fov_degrees: float = FOV_DEGREES,
    occluders: tuple[Occluder, ...] = (),
) -> tuple[tuple[float, float], ...]:
    """
    The visible wedge as a uv polygon, apex first.

    Returns the origin followed by one point per ray, so the result can go
    straight into a canvas polygon.  An empty result means there was nothing to
    draw -- no heading, or no radius -- and the caller should draw nothing
    rather than fall back to a circle.

    `occluders` are the round smokes standing at this instant.  They are a
    separate argument from the mask and not folded into it, because the mask is
    one document per map that the browser fetches once, and a smoke is a fact
    about one millisecond of one round.

    Six arguments, and the obvious tidy -- bundling the settings into an object
    the way the TypeScript port does -- is the one thing that must not happen
    here.  `tests/golden/` compares the two implementations call for call, and
    the fixture writes `fov_degrees` as a scalar beside the mask; a Python
    signature that took a bag while the port took five names would make the two
    stop being readable against each other, which is the only reason the port
    is trustworthy.
    """
    if radius <= 0:
        return ()
    rays = ray_directions(forward, fov_degrees=fov_degrees)
    if not rays:
        return ()
    return (
        origin,
        *(_march(sight, origin, ray, radius, occluders) for ray in rays),
    )


def ray_directions(
    forward: tuple[float, float],
    *,
    fov_degrees: float = FOV_DEGREES,
) -> tuple[tuple[float, float], ...]:
    """
    The unit direction of every ray in a cone, before any of them is marched.

    Split out of `cone` so the two halves can be checked separately, which they
    have to be: these are the only values in the whole model that come out of a
    libm `cos`, `sin` and `atan2`, and *both* languages specify those as
    approximate.  Everything downstream of here is exact arithmetic and is
    compared exactly; these are compared to within a bound and with their unit
    length asserted.  See web/src/model/__tests__/parity.test.ts.
    """
    du, dv = forward
    if du == 0.0 and dv == 0.0:
        return ()
    base = math.atan2(dv, du)
    half = math.radians(fov_degrees) / 2
    step = math.radians(RAY_STEP_DEGREES)
    count = max(2, int(math.radians(fov_degrees) / step) + 1)
    out = []
    for i in range(count):
        angle = base - half + (2 * half) * (i / (count - 1))
        out.append((math.cos(angle), math.sin(angle)))
    return tuple(out)


def _march(
    sight: SightMap,
    origin: tuple[float, float],
    direction: tuple[float, float],
    radius: float,
    occluders: tuple[Occluder, ...] = (),
) -> tuple[float, float]:
    """One ray, to the first blocked cell or to `radius`, whichever comes first."""
    u0, v0 = origin
    du, dv = direction
    cell = 1.0 / sight.size
    steps = max(1, int(radius / cell))
    for i in range(1, steps + 1):
        travelled = i * cell
        u = u0 + du * travelled
        v = v0 + dv * travelled
        if i > SEED_CELLS and (sight.blocked(u, v) or _inside(occluders, u, v)):
            # Stop on the last open cell, not inside the wall, so the polygon
            # traces the silhouette rather than overlapping it.
            back = (i - 1) * cell
            return (u0 + du * back, v0 + dv * back)
    return (u0 + du * radius, v0 + dv * radius)


def _inside(occluders: tuple[Occluder, ...], u: float, v: float) -> bool:
    """
    Whether this step has walked into a smoke.

    Squared distance, and that is about the TypeScript port rather than about
    speed.  `hypot` is *approximate by specification* in both languages and
    `sqrt` would be a needless rounding besides -- multiply, subtract and
    compare are exactly specified in IEEE-754, so the two implementations agree
    by construction and `tests/golden/cone.json` can compare them to the bit.
    """
    for smoke in occluders:
        du = u - smoke.u
        dv = v - smoke.v
        if du * du + dv * dv <= smoke.radius * smoke.radius:
            return True
    return False


class SightCache:
    """
    One `SightMap` per radar image, built on demand and kept.

    Keyed by path: a viewer shows one map for its whole life, so this is really
    a lazily-built single entry, but the app outlives a viewer and reopening a
    second replay on the same map should not re-read the PNG.
    """

    def __init__(self, images=None) -> None:
        # An image supplier is optional: a Tk viewer already has one and its
        # cache is worth sharing, and anything else -- a server, a test --
        # would only be constructing one to open a file that `from_path`
        # opens by itself.
        self.images = images
        self._maps: dict[str, SightMap | None] = {}

    def get(self, path) -> SightMap | None:
        """The silhouette for one radar file, or None if it cannot be read."""
        if path is None:
            return None
        key = str(path)
        if key not in self._maps:
            self._maps[key] = self._build(path)
        return self._maps[key]

    def _build(self, path) -> SightMap | None:
        if self.images is None:
            return SightMap.from_path(path)
        source = self.images.source(path)
        return None if source is None else SightMap.from_image(source)
