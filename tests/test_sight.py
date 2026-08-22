"""
The sight approximation: a raycast over what the radar image draws.

Everything here runs against a synthetic image, so there is no art cache, no
display and no map involved.  The point is not that the cone is *right* -- it
is an approximation and the interface says so -- but that it is right about the
two things a wrong one would be plausible about: which way the player is
looking, and where the picture stops it.

The synthetic images are painted in Riot's own colours.  They used to paint
playable cells pure white, which was fine while alpha was the whole occluder
and became a fixture that was *entirely wall* the moment the white ink started
blocking -- so a floor cell is now the exact (118, 118, 118) every published
radar uses, and W is the ink.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from vrfview import sight
from vrfview.art import Transform

# The identity-ish transform used by most tests: world x and y map straight
# onto v and u over a 0..1000 world.  Note the swap -- `Transform.apply` puts
# world *y* into u, which is measured and not a typo.  See art.Transform.
PLAIN = Transform(
    x_multiplier=0.001,
    y_multiplier=0.001,
    x_scalar_to_add=0.0,
    y_scalar_to_add=0.0,
)


# Riot's own values, so a fixture cannot drift from the art the thresholds
# were measured against.  See vrfview/walls.py for the measurement.
FLOOR = (118, 118, 118, 255)
INK = (255, 255, 255, 255)
VOID = (0, 0, 0, 0)
# An upper elevation tier and Bind's teleporter teal.  Both sit inside the
# floor band and must stay open: the first is a walkable storey, and the
# second is the one saturated colour anywhere on a radar.
TIER = (152, 152, 152, 255)
TELEPORTER = (26, 163, 132, 255)

PAINT = {"#": FLOOR, "W": INK, ".": VOID, "^": TIER, "T": TELEPORTER}


def image(rows: list[str], *, scale: int = 1) -> Image.Image:
    """
    A tiny RGBA image from an ASCII map: `#` floor, `W` wall ink, `.` void.

    Void is alpha 0, which is exactly how Riot's radars mark everything
    outside the map -- 57% to 72% of every published minimap.png -- and the
    floor is the exact grey that is 69% to 79% of every opaque pixel.

    `scale` paints each character as a square block, so a fixture can be
    written at the size it is read at *or* at a multiple of it.  The second
    case is the one that matters: the real thing is a 1024 image read onto a
    256 grid, and a wall line is thinner than a cell.
    """
    size = len(rows) * scale
    out = Image.new("RGBA", (size, size), VOID)
    pixels = out.load()
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            for dy in range(scale):
                for dx in range(scale):
                    pixels[x * scale + dx, y * scale + dy] = PAINT[cell]
    return out


ALL_OPEN = ["########"] * 8
# A wall down the middle column, drawn the way the void is: as a hole in the
# silhouette.  Riot draws both -- a hole where the map ends, a white line where
# a wall stands on the floor -- and INKED below is the other one.
SPLIT = [
    "###.####",
    "###.####",
    "###.####",
    "###.####",
    "###.####",
    "###.####",
    "###.####",
    "###.####",
]


# The same wall, drawn the way Riot actually draws an interior one: a white
# line standing on floor that continues on both sides of it.  Under an
# alpha-only occluder this image is entirely open.
INKED = [
    "###W####",
    "###W####",
    "###W####",
    "###W####",
    "###W####",
    "###W####",
    "###W####",
    "###W####",
]


class TestSightMap(unittest.TestCase):
    def test_transparent_cells_are_blocked_and_opaque_ones_are_not(self):
        found = sight.SightMap.from_image(image(SPLIT), size=8)
        assert not found.blocked(0.1, 0.5)
        assert found.blocked(0.44, 0.5)
        assert not found.blocked(0.9, 0.5)

    def test_outside_the_image_is_blocked(self):
        found = sight.SightMap.from_image(image(ALL_OPEN), size=8)
        assert found.blocked(-0.1, 0.5)
        assert found.blocked(1.5, 0.5)
        assert found.blocked(0.5, -0.01)

    def test_an_image_with_no_alpha_is_entirely_open(self):
        """
        A radar saved as RGB is a picture we cannot derive occlusion from.

        Open is the safer wrong answer: an unbounded cone reads as the
        approximation it is, where a cone stopping at the player's feet reads
        as a bug in the positions.
        """
        flat = Image.new("RGB", (8, 8), (10, 10, 10))
        assert sight.SightMap.from_image(flat, size=8).open_fraction == 1.0

    def test_open_fraction_measures_the_playable_area(self):
        found = sight.SightMap.from_image(image(SPLIT), size=8)
        assert round(found.open_fraction, 3) == 0.875

    def test_a_drawn_wall_blocks_although_the_silhouette_is_unbroken(self):
        """
        The whole point of reading the ink: this image has no hole in it.

        Every pixel of INKED is opaque, so an occluder built from alpha alone
        calls it entirely open and a cone crosses the wall as if it were not
        there.  That was true of every interior wall on every map.
        """
        found = sight.SightMap.from_image(image(INKED), size=8)
        assert found.blocked(0.44, 0.5)
        assert not found.blocked(0.1, 0.5)
        assert not found.blocked(0.9, 0.5)
        assert round(found.open_fraction, 3) == 0.875

    def test_the_same_line_painted_floor_grey_blocks_nothing(self):
        """The rule is the ink, not the column: repaint it and the wall goes."""
        floored = [row.replace("W", "#") for row in INKED]
        found = sight.SightMap.from_image(image(floored), size=8)
        assert found.open_fraction == 1.0

    def test_a_wall_thinner_than_a_cell_survives_the_downsample(self):
        """
        The regression that would fail silently rather than loudly.

        A radar is 1024 wide and read onto a 256 grid, so a two-pixel wall is
        half a cell.  Downsample first and threshold after -- which is what the
        alpha half does -- and the line averages into the floor band and is
        simply gone: the mask comes back entirely open and nothing anywhere
        reports a problem.  `walls.wall_cells` thresholds at full resolution
        and pools down, so the line still arrives as a cell.
        """
        fine = image(INKED, scale=4)
        assert fine.size == (32, 32)
        found = sight.SightMap.from_image(fine, size=8)
        assert found.blocked(0.44, 0.5)
        assert not found.blocked(0.1, 0.5)

    def test_an_upper_tier_and_a_teleporter_stay_open(self):
        """
        Everything between the floor grey and the ink is still floor.

        The elevation tiers are the population the threshold has to clear
        without touching, and Bind's teleporter teal is the one saturated
        colour anywhere on a radar -- a threshold reading a channel rather
        than a luminance would close both.
        """
        mixed = ["#^T#####"] * 8
        found = sight.SightMap.from_image(image(mixed), size=8)
        assert found.open_fraction == 1.0


class TestForward(unittest.TestCase):
    def test_the_heading_survives_the_transform_axis_swap(self):
        """
        Yaw 0 is +x in the world, and the transform puts world x into *v*.

        So a player looking along yaw 0 must produce a heading straight down
        the image, not to the right.  Computing this with trigonometry in uv
        space gives (1, 0) -- plausible, and ninety degrees wrong.
        """
        du, dv = sight.forward_uv(PLAIN, 500.0, 500.0, 0.0)
        assert round(du, 6) == 0.0
        assert round(dv, 6) == 1.0

    def test_yaw_ninety_points_along_the_other_axis(self):
        du, dv = sight.forward_uv(PLAIN, 500.0, 500.0, 90.0)
        assert round(du, 6) == 1.0
        assert round(dv, 6) == 0.0

    def test_a_negative_multiplier_flips_the_heading(self):
        """Either multiplier may be negative; the probe handles it, maths did not."""
        flipped = Transform(x_multiplier=0.001, y_multiplier=-0.001)
        _, dv = sight.forward_uv(flipped, 500.0, 500.0, 0.0)
        assert round(dv, 6) == -1.0

    def test_a_degenerate_transform_yields_no_heading(self):
        assert sight.forward_uv(Transform(), 1.0, 1.0, 45.0) == (0.0, 0.0)


class TestCone(unittest.TestCase):
    def test_a_ray_stops_at_the_wall(self):
        """
        Looking straight at the wall four cells away, nothing reaches past it.

        The wall is column 3 of 8, so u = 0.375; every returned point must sit
        short of it.
        """
        found = sight.cone(
            sight.SightMap.from_image(image(SPLIT), size=8),
            origin=(0.05, 0.5),
            forward=(1.0, 0.0),
            radius=1.0,
            fov_degrees=10.0,
        )
        assert len(found) > sight.SEED_CELLS
        for u, _v in found[1:]:
            assert u < 0.5

    def test_an_open_map_lets_a_ray_run_to_its_radius(self):
        found = sight.cone(
            sight.SightMap.from_image(image(ALL_OPEN), size=8),
            origin=(0.5, 0.5),
            forward=(1.0, 0.0),
            radius=0.25,
            fov_degrees=1.0,
        )
        assert round(max(u for u, _v in found), 2) == 0.75

    def test_the_apex_is_the_player(self):
        found = sight.cone(
            sight.SightMap.from_image(image(ALL_OPEN), size=8),
            origin=(0.4, 0.6),
            forward=(1.0, 0.0),
            radius=0.2,
        )
        assert found[0] == (0.4, 0.6)

    def test_a_wider_field_of_view_casts_more_rays(self):
        args = {
            "sight": sight.SightMap.from_image(image(ALL_OPEN), size=8),
            "origin": (0.5, 0.5),
            "forward": (1.0, 0.0),
            "radius": 0.2,
        }
        assert len(sight.cone(**args, fov_degrees=100.0)) > len(
            sight.cone(**args, fov_degrees=20.0),
        )

    def test_no_heading_and_no_radius_both_draw_nothing(self):
        """An empty polygon means draw nothing -- never fall back to a circle."""
        found = sight.SightMap.from_image(image(ALL_OPEN), size=8)
        assert sight.cone(found, (0.5, 0.5), (0.0, 0.0), 0.2) == ()
        assert sight.cone(found, (0.5, 0.5), (1.0, 0.0), 0.0) == ()

    def test_a_player_standing_on_a_void_cell_still_gets_a_cone(self):
        """
        Against a wall or in a doorway, the origin often reads as blocked.

        Refusing there would blink the cone off at exactly the moments it is
        worth looking at, so the first few steps ignore the mask.
        """
        found = sight.cone(
            sight.SightMap.from_image(image(SPLIT), size=8),
            origin=(0.44, 0.5),
            forward=(1.0, 0.0),
            radius=0.4,
            fov_degrees=5.0,
        )
        assert len(found) > 1
        assert any(u > 0.44 for u, _v in found[1:])


class TestRadius(unittest.TestCase):
    def test_a_world_distance_becomes_a_fraction_of_the_radar(self):
        assert sight.uv_radius(PLAIN, 500.0) == 0.5

    def test_the_sign_of_a_multiplier_does_not_shrink_the_reach(self):
        flipped = Transform(x_multiplier=-0.001, y_multiplier=-0.001)
        assert sight.uv_radius(flipped, 500.0) == 0.5


class TestCache(unittest.TestCase):
    class FakeImages:
        """Stands in for ImageCache: the same `source` contract and nothing else."""

        def __init__(self, answer):
            self.answer = answer
            self.calls = 0

        def source(self, path):  # noqa: ARG002 - matches ImageCache.source
            self.calls += 1
            return self.answer

    def test_one_read_per_radar_however_often_it_is_asked_for(self):
        images = self.FakeImages(image(ALL_OPEN))
        cache = sight.SightCache(images)
        first = cache.get("minimap.png")
        assert cache.get("minimap.png") is first
        assert images.calls == 1

    def test_a_missing_radar_is_none_rather_than_an_error(self):
        cache = sight.SightCache(self.FakeImages(None))
        assert cache.get("nope.png") is None
        assert cache.get(None) is None


class FromPath(unittest.TestCase):
    """
    A mask can be built from a radar file without an image cache.

    That existed only because the viewer had one; a server or a test would be
    constructing an `ImageCache` purely to open a PNG, and the decision about
    what counts as open belongs beside `ALPHA_FLOOR` rather than beside a
    widget.
    """

    def test_it_reads_a_png_and_thresholds_its_alpha(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "minimap.png"
            image = Image.new("RGBA", (8, 8), VOID)
            for x in range(4):
                for y in range(8):
                    image.putpixel((x, y), FLOOR)
            image.save(path)
            built = sight.SightMap.from_path(path, size=8)
            assert built is not None
            assert built.open_fraction == 0.5
            assert not built.blocked(0.25, 0.5)
            assert built.blocked(0.75, 0.5)

    def test_a_file_that_is_not_an_image_is_none_rather_than_a_traceback(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "minimap.png"
            path.write_text("not a png", encoding="utf-8")
            assert sight.SightMap.from_path(path) is None

    def test_a_missing_file_is_none(self):
        with TemporaryDirectory() as tmp:
            assert sight.SightMap.from_path(Path(tmp) / "absent.png") is None

    def test_no_path_at_all_is_none(self):
        assert sight.SightMap.from_path(None) is None

    def test_the_cache_reads_the_file_itself_when_given_no_supplier(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "minimap.png"
            Image.new("RGBA", (8, 8), FLOOR).save(path)
            cache = sight.SightCache()
            first = cache.get(path)
            assert first is not None
            # Kept, not rebuilt: the same object comes back.
            assert cache.get(path) is first


class Caption(unittest.TestCase):
    def test_the_sentence_lives_with_the_raycaster(self):
        """
        Anything handed a mask is handed the sentence that says what it is.

        The caption used to belong to the one view that drew a cone, which
        meant a second view could draw one and quietly leave off what it was
        a cone of.
        """
        assert "not collision" in sight.CAPTION
        assert "2D only" in sight.CAPTION

    def test_it_admits_what_the_white_ink_is_not(self):
        """
        The ink outlines low boxes and ledges, and a reader has to be told.

        A cone that stops at a crate is the approximation working as designed,
        and is indistinguishable from a bug unless the caption says so.
        """
        assert "lines drawn on it" in sight.CAPTION
        assert "see over" in sight.CAPTION
