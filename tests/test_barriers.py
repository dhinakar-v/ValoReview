"""
The barrier table is a measurement, and these are the things that would rot it.

`libraries/vrfview/barriers.json` holds nine maps' round-start spawn barriers
in radar uv.  It was read off screenshots of another replay viewer that nobody
publishes coordinates for -- `docs/map-barriers.md` is the derivation -- and the
screenshots are gitignored, so this file and the table beside it are the whole
of what a later reader can check.

Three of these need no `assets/` and run everywhere: the table parses, every
placement beat its runner-up by a wide margin, and the orientation arithmetic
agrees with Pillow's own transposes.  The last one is the ground truth and
needs the radars: a barrier closes a doorway, a doorway is floor, so every bar
in the table has to land on the radar's playable silhouette.  A fit that
drifted would put bars in the void and that is the check that would catch it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pytest

import make_barriers
from vrfview import barrierdecode, barriers

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "assets" / "maps"
REFERENCES = REPO / "features" / "map-barriers"


class TheCommittedTable(unittest.TestCase):
    def setUp(self):
        self.table = barriers.load()

    def test_it_names_the_maps_it_was_derived_from(self):
        assert self.table, "the barrier table is empty"
        for name, entry in self.table.items():
            assert entry.name == name
            assert entry.reference.startswith("features/map-barriers/")

    def test_every_barrier_is_a_box_inside_the_radar(self):
        for entry in self.table.values():
            for barrier in entry.barriers:
                for value in (barrier.u0, barrier.v0, barrier.u1, barrier.v1):
                    assert 0.0 <= value <= 1.0, (
                        f"{entry.name}: {value} is off the radar"
                    )
                assert barrier.u0 < barrier.u1, f"{entry.name}: empty box"
                assert barrier.v0 < barrier.v1, f"{entry.name}: empty box"

    def test_every_map_carries_both_sides(self):
        """
        A frame showing one side's barriers only would be a frame taken after
        the buy phase, and half a reading is the failure mode that looks like a
        finding.
        """
        for entry in self.table.values():
            for side in barriers.SIDES:
                assert entry.side(side), f"{entry.name} records no {side} barriers"

    def test_the_orientation_was_found_rather_than_assumed(self):
        """
        The whole placement rests on one orientation beating the other seven.
        Measured, the nine span 1.71x to 2.21x; anything near 1.0 would mean
        the map's own silhouette does not distinguish the eight, and the bars
        could be a quarter turn out while still looking plausible.
        """
        for entry in self.table.values():
            assert entry.fit.margin >= make_barriers.MARGIN_FLOOR, (
                f"{entry.name}: {entry.fit.orient} at {entry.fit.iou:.4f} barely beat "
                f"{entry.fit.runner_up} at {entry.fit.runner_up_iou:.4f}"
            )

    def test_a_thin_bar_survives_being_drawn_small(self):
        """
        A barrier is about five radar pixels thick.  Rounded rather than
        floored to a minimum, the thin axis vanishes below about 400px and the
        bar would be missing from the picture rather than drawn thin.
        """
        for entry in self.table.values():
            for barrier in entry.barriers:
                x0, y0, x1, y1 = barrier.rect(256)
                assert x1 > x0, f"{entry.name}: a bar collapsed across at 256"
                assert y1 > y0, f"{entry.name}: a bar collapsed down at 256"


class TheFileFormat(unittest.TestCase):
    def test_it_round_trips(self):
        table = barriers.load()
        written = REPO / "tests" / "_barriers_roundtrip.json"
        try:
            written.write_text(barriers.dumps(table), encoding="utf-8")
            assert barriers.load(written) == table
        finally:
            written.unlink(missing_ok=True)

    def test_a_missing_table_is_an_error_and_not_an_empty_one(self):
        """
        "no barriers anywhere" and "the table did not load" render identically,
        so the caller has to be told which one happened.
        """
        with pytest.raises(barriers.ConfigError):
            barriers.load(REPO / "tests" / "no-such-barriers.json")

    def test_an_older_version_is_refused(self):
        written = REPO / "tests" / "_barriers_version.json"
        try:
            written.write_text(json.dumps({"version": 0, "maps": {}}), encoding="utf-8")
            with pytest.raises(barriers.ConfigError):
                barriers.load(written)
        finally:
            written.unlink(missing_ok=True)


class TheOrientationArithmetic(unittest.TestCase):
    """
    `oriented_point` has to agree with `oriented`, and the way to know is to
    ask Pillow rather than to reason about which way a rotation turns.  A
    quarter turn the wrong way puts every barrier somewhere plausible on the
    map, which is exactly the class of error this project refuses to ship.
    """

    def test_it_sends_a_pixel_where_pillow_does(self):
        from PIL import Image

        width, height = 7, 4
        for key in barrierdecode.ORIENTATIONS:
            for x, y in ((0, 0), (5, 1), (6, 3), (2, 2)):
                frame = Image.new("L", (width, height), 0)
                frame.putpixel((x, y), 255)
                turned = barrierdecode.oriented(frame, key)
                box = turned.getbbox()
                found = barrierdecode.oriented_point(x, y, width, height, key)
                assert found == (box[0], box[1]), (
                    f"{key}: ({x},{y}) computed {found}, Pillow put it at "
                    f"({box[0]},{box[1]})"
                )

    def test_a_quarter_turn_swaps_the_axes(self):
        for key in ("r90", "r270", "flip_r90", "flip_r270"):
            from PIL import Image

            assert barrierdecode.oriented(Image.new("L", (7, 4)), key).size == (4, 7)


@unittest.skipUnless(ASSETS.is_dir(), "needs the radars from fetch-assets")
class EveryBarrierLandsOnTheMap(unittest.TestCase):
    """
    The ground truth, and the same argument `tracks._plants_from` makes for a
    decoded spike plant: a barrier closes a doorway, so its coordinate is on
    playable floor.  Riot's radar states that floor as its alpha channel, the
    barrier came from a completely different picture, and a placement that was
    a few percent out would put bars in the void -- where a random coordinate
    would land about a third of the time.

    Measured over the nine maps: 76 of 76 bars, worst centreline coverage 0.90.
    """

    def test_all_of_them(self):
        table = barriers.load()
        checked = 0
        worst = (1.0, "")
        for entry in table.values():
            radar = ASSETS / entry.name / "minimap.png"
            if not radar.is_file():
                continue
            silhouette = barrierdecode.radar_silhouette(radar)
            for barrier in entry.barriers:
                share = barrierdecode.on_floor(barrier, silhouette)
                worst = min(worst, (share, entry.name))
                assert share >= make_barriers.FLOOR_SHARE, (
                    f"{entry.name}: a {barrier.side} bar is {share:.0%} on the floor"
                )
                checked += 1
        assert checked, "no radar on disk for any recorded map"
        assert worst[0] >= 0.85, f"worst bar is {worst[0]:.2f} on {worst[1]}"


@unittest.skipUnless(REFERENCES.is_dir(), "needs the reference frames")
class TheDecodeStillReproducesTheTable(unittest.TestCase):
    """
    The screenshots are gitignored, so this runs only where they are.  Where
    they are, it is the check that the table was not hand-edited away from what
    the pictures say -- or, when it was, that the edit is deliberate.
    """

    def test_one_map_comes_back_the_same(self):
        table = barriers.load()
        name = next(iter(sorted(table)))
        radar = ASSETS / name / "minimap.png"
        if not radar.is_file():
            self.skipTest(f"no radar for {name}")
        frame = REFERENCES / f"{name.casefold()}.png"
        if not frame.is_file():
            self.skipTest(f"no reference frame for {name}")
        found = barrierdecode.decode(name, frame, radar)
        assert len(found.barriers) == len(table[name].barriers)
        assert found.fit.orient == table[name].fit.orient
        for a, b in zip(found.barriers, table[name].barriers, strict=True):
            assert a.side == b.side
            assert abs(a.u0 - b.u0) < 0.01, f"{name}: a bar moved"
            assert abs(a.v0 - b.v0) < 0.01, f"{name}: a bar moved"
