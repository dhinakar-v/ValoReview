"""
What settled the buy phase, and the standing check that keeps it settled.

`vrfview.roundrules` says a round spends thirty seconds behind a spawn barrier,
or forty-five on rounds 1, 13 and 25.  Nothing in a `.vrf` states that: no actor
replicates a barrier and no event group fires when one drops, so the figure is
external knowledge in the shape `abilityfacts` sets.

Unlike `abilityfacts`, though, it can be *scored*, and this is that scoring.
The ground truth is the same kind this project uses everywhere else -- a fact
about the world that no bug could invent: **nobody can act through a barrier**,
so the first kill or spike plant in a round is a lower bound on when that round's
barrier dropped.  A rule claiming a longer buy phase than the file's own first
kill allows is refuted outright by that kill.

There is no upper bound available at all, and that is worth being plain about:
nothing forces a round's first event to happen the instant the barrier drops,
so this can prove a buy phase is not too long and can never prove it is not too
short.  What carries the other half is the *gap between two populations* -- the
long-buy rounds' earliest action is 46.6 s and the ordinary rounds' is 31.2 s,
and neither is anywhere near the other's floor.  A 30 s rule everywhere would
pass the assertion below and lose that separation, which is why the margins are
asserted per class rather than only in aggregate.

Like `tests/test_positions.py` this is not a unit test: it reads the whole
reference library and is skipped where there is none.
"""

from __future__ import annotations

import statistics
import unittest
from pathlib import Path

import vrfconfig
from vrfview import loader, roundrules

DEMOS = vrfconfig.demo_root().path


# Every round with a kill or a plant, over the 103-capture reference library.
# Asserted rather than merely reported: a rule change that stops covering the
# library -- a new long-buy round, a capture format nobody had scored -- should
# fail here rather than quietly measure less.
SCORED_ROUNDS = 2176

# The tightest a real round has ever come to its own barrier drop, in ms.  The
# floor is deliberately generous against it: what this defends is the sign, not
# the value, and a genuinely different game version should read as a violation
# rather than as a shrinking margin.
MIN_MARGIN_MS = 1_238
MARGIN_FLOOR_MS = 500

# How far clear of the *other* class's buy phase each class measures.  This is
# the half of the argument the violation count cannot make: an ordinary round's
# earliest action is 31.2 s, so a 45 s rule for it is refuted; a long-buy round's
# is 46.6 s, which no 30 s rule would ever have predicted.
LONG_BUY_FLOOR_MS = 46_000
SHORT_BUY_CEILING_MS = 40_000


def _captures() -> list[Path]:
    if not DEMOS.is_dir():
        return []
    return sorted(DEMOS.glob("*.vrf"))


@unittest.skipUnless(_captures(), f"no captures in {DEMOS}")
class TheBuyPhaseEndsBeforeAnybodyActs(unittest.TestCase):
    """
    Score `roundrules` against every round in the library that has an action.

    One pass, three claims: nobody acts before their barrier drops, the margin
    by which that holds is not vanishing, and the two buy phases are two
    populations rather than one with a fitted threshold.
    """

    @staticmethod
    def _load(path: Path):
        """
        A capture that will not parse is skipped, not a failure.

        `vrfhome.scan` makes a card carrying the error rather than omitting the
        file, and the same reasoning applies to a measurement: a library holding
        one unreadable capture has not disproved anything about buy phases.  The
        count assertion is what stops that becoming a silent shrinking sample.
        """
        try:
            return loader.load(str(path))
        except Exception as exc:  # noqa: BLE001 - see the docstring
            print(f"skipped {path.name}: {exc}")
            return None

    @classmethod
    def setUpClass(cls) -> None:
        cls.margins: list[tuple[Path, int, int]] = []
        cls.long_buy: list[int] = []
        cls.short_buy: list[int] = []
        for path in _captures():
            replay = cls._load(path)
            if replay is None:
                continue
            for rnd in replay.rounds:
                acted = [k.t_ms for k in replay.kills if rnd.contains(k.t_ms)]
                acted += [
                    s.t_ms
                    for s in replay.spike
                    if s.kind == "planted" and rnd.contains(s.t_ms)
                ]
                if not acted:
                    continue
                first = min(acted) - rnd.start_ms
                cls.margins.append((path, rnd.number, first - rnd.buy_phase_ms))
                if rnd.number in roundrules.LONG_BUY_ROUNDS:
                    cls.long_buy.append(first)
                else:
                    cls.short_buy.append(first)

    def test_nobody_acts_before_the_barrier_drops(self) -> None:
        early = [(p.name, n, m) for p, n, m in self.margins if m < 0]
        assert early == [], (
            f"{len(early)} rounds acted inside their buy phase: {early[:5]}"
        )

    def test_the_whole_library_was_scored(self) -> None:
        assert len(self.margins) == SCORED_ROUNDS

    def test_the_margin_has_not_closed(self) -> None:
        tightest = min(m for _, _, m in self.margins)
        assert tightest >= MARGIN_FLOOR_MS, f"tightest margin {tightest} ms"
        assert tightest == MIN_MARGIN_MS, f"tightest margin moved to {tightest} ms"

    def test_the_two_buy_phases_are_two_populations(self) -> None:
        """
        The half the violation count cannot make.

        A 30 s rule everywhere would pass every assertion above -- it under-claims,
        and under-claiming is never refuted by a kill.  What refutes it is that no
        round 1, 13 or 25 in the library has ever seen an action before 46 s, which
        is sixteen seconds after a 30 s barrier would have dropped.
        """
        assert min(self.long_buy) >= LONG_BUY_FLOOR_MS
        assert min(self.short_buy) <= SHORT_BUY_CEILING_MS
        assert statistics.median(self.long_buy) > statistics.median(self.short_buy)


class TheMarkerIsInsideItsOwnRound(unittest.TestCase):
    """`Round.action_start_ms` is clamped, and the clamp is the only special case."""

    def _round(self, number: int, start: int, end: int):
        from vrfview.model import Round

        return Round(number=number, index=number - 1, start_ms=start, end_ms=end)

    def test_an_ordinary_round_gets_thirty_seconds(self) -> None:
        rnd = self._round(4, 100_000, 240_000)
        assert rnd.buy_phase_ms == roundrules.BUY_PHASE_MS
        assert rnd.action_start_ms == 130_000

    def test_the_three_resets_get_forty_five(self) -> None:
        for number in roundrules.LONG_BUY_ROUNDS:
            rnd = self._round(number, 0, 200_000)
            assert rnd.buy_phase_ms == roundrules.LONG_BUY_MS
            assert rnd.action_start_ms == 45_000

    def test_a_round_shorter_than_its_buy_phase_has_no_such_instant(self) -> None:
        rnd = self._round(7, 0, 12_000)
        assert rnd.action_start_ms == rnd.end_ms
        assert not rnd.contains(rnd.action_start_ms)
