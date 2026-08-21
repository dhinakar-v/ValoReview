"""
Tests for the parts of the app that can be checked without a screen.

The widgets themselves are not tested here -- constructing them needs a display
and proves little -- but three things underneath them can drift silently and
are worth pinning:

  * the icon names the generator writes and the names the bar asks for have to
    be the same set, or a button quietly loses its glyph;
  * the image cache's sizing and masking are arithmetic on a PIL image and need
    no toolkit at all;
  * the provenance panel is the page that states what is known and how, so a
    claim that has stopped being true there is worse than no panel.  It used to
    say positions do not exist.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

import make_icons
from vrfview import icons, images
from vrfview.model import Player, Replay, Round
from vrfview.viewer import provenance_text


class IconNames(unittest.TestCase):
    def test_the_generator_draws_exactly_what_the_app_asks_for(self):
        assert set(make_icons.GLYPHS) == set(icons.NAMES)

    def test_every_glyph_has_a_text_fallback(self):
        assert all(icons.FALLBACK[name] for name in icons.NAMES)

    def test_a_missing_glyph_is_none_rather_than_a_path_that_is_not_there(self):
        with TemporaryDirectory() as tmp:
            assert icons.path_for("play", Path(tmp)) is None

    def test_written_glyphs_are_square_and_readable(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "icons"
            written = make_icons.write_all(root)
            assert len(written) == len(icons.NAMES)
            for path in written:
                with Image.open(path) as image:
                    assert image.size == (make_icons.SIZE, make_icons.SIZE)
                    assert image.mode == "RGBA"
            assert icons.path_for("play", Path(tmp)) == root / "play.png"


class Sizing(unittest.TestCase):
    def test_fit_keeps_the_aspect_ratio(self):
        assert images._fit((456, 100), 228) == (228, 50)
        assert images._fit((1024, 1024), 46) == (46, 46)

    def test_fit_upscales_too_now_that_pillow_resamples(self):
        """The old integer subsample could only shrink; this need not."""
        assert images._fit((32, 32), 64) == (64, 64)

    def test_fit_survives_a_degenerate_size(self):
        assert images._fit((0, 0), 20) == (20, 20)

    def test_a_circular_mask_clears_the_corners_and_keeps_the_middle(self):
        square = Image.new("RGBA", (40, 40), (255, 0, 0, 255))
        masked = images.shape(square, images.CIRCLE)
        assert masked.getpixel((0, 0))[3] == 0
        assert masked.getpixel((20, 20))[3] == 255

    def test_square_is_the_image_itself(self):
        square = Image.new("RGBA", (8, 8), (1, 2, 3, 255))
        assert images.shape(square, images.SQUARE) is square


def _replay() -> Replay:
    replay = Replay(
        source="x.vrf",
        match_id="m-1",
        map_path="/Game/Maps/Triad/Triad",
        map_name="Haven",
        length_ms=60_000,
        build="++Ares-Core+release-12.10",
    )
    replay.rounds = [Round(number=1, index=0, start_ms=0, end_ms=60_000)]
    replay.players = [
        Player(actor_id=1, team="A", label="A1", codename="Hunter", agent="Sova"),
        Player(actor_id=2, team="B", label="B1"),
    ]
    return replay


class Provenance(unittest.TestCase):
    def test_it_reports_the_position_source_verbatim(self):
        replay = _replay()
        replay.position_source = "12.10: 199,180 positions for 10 player actors"
        assert replay.position_source in provenance_text(replay)

    def test_it_says_which_actors_stated_their_own_agent(self):
        text = provenance_text(_replay())
        assert "1 of 2 actors state their own agent" in text
        assert "Sova" in text

    def test_an_undecoded_replay_says_so_without_claiming_positions_are_absent(self):
        text = provenance_text(_replay())
        assert "not requested" in text
        # The line this panel used to carry, and which the decode falsified.
        assert "the 2D scene is schematic, not a map" not in text

    def test_the_three_absent_numbers_are_named(self):
        text = provenance_text(_replay())
        assert "health, armour, credits" in text
        assert "player names / Riot IDs" in text
