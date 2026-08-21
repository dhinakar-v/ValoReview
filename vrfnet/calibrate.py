"""
Resolve the engine version gates empirically.

The EEngineNetworkVersionHistory thresholds for build ++Ares-Core+release-11.11
are not public, so rather than hard-code a guess this sweeps every candidate
layout in vrfnet.versions.candidate_features() over real packets and scores
each by how many packets' bunch loops land exactly on at_end().

Why the score discriminates
---------------------------
A bunch header is a dense run of single bits and variable-width integers with
no padding and no sentinel.  Read one bit too many or too few and the length
field lands on the wrong bits, so the payload skip overshoots and the next
header starts in the middle of the previous bunch.  A wrong layout therefore
does not degrade gracefully -- it collapses within a bunch or two.  The
correct layout is the one that consumes whole packets exactly, repeatedly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from vrfnet.datachannel import score_features
from vrfnet.versions import Features, candidate_features

CALIBRATION_FILE = "vrfnet/calibrated.json"


# Candidates scoring within this of the winner are treated as tied: the
# capture does not exercise whatever distinguishes them.
TIE_EPSILON = 0.005


@dataclass
class Calibration:
    """The winning layout, how clearly it won, and what it could not settle."""

    features: Features
    rate: float
    runner_up_rate: float
    packets: int
    bunches: int
    undetermined: list = field(default_factory=list)

    @property
    def margin(self) -> float:
        return self.rate - self.runner_up_rate

    @property
    def is_decisive(self) -> bool:
        """A real result, not a coin flip between two similar layouts."""
        return self.rate >= 0.99 and self.margin >= 0.10

    def summary(self) -> str:
        verdict = "decisive" if self.is_decisive else "INCONCLUSIVE"
        lines = [
            f"{self.rate:.4%} clean over {self.packets:,} packets "
            f"({self.bunches:,} bunches)",
            f"next distinct layout {self.runner_up_rate:.4%}, "
            f"margin {self.margin:.4%} -- {verdict}",
            f"  {self.features.describe()}",
        ]
        if self.undetermined:
            lines.append(
                "  not settled by this capture (branch never taken): "
                + ", ".join(self.undetermined)
            )
        return "\n".join(lines)


def undetermined_gates(scores, epsilon: float = TIE_EPSILON) -> list[str]:
    """Gates the capture cannot distinguish.

    A gate guarding a branch the replay never takes -- a close reason that is
    always Destroyed, a partial-bunch flag never set -- leaves its candidates
    scoring within noise of each other.  Those are not rival answers, they are
    questions this capture does not answer, and saying so is more useful than
    picking one and calling it measured.
    """
    best = scores[0]
    near = [s.features for s in scores if s.rate >= best.rate - epsilon]
    return [
        name
        for name in best.features.as_dict()
        if len({getattr(f, name) for f in near}) > 1
    ]


def calibrate(packets, limit: int | None = None,
              epsilon: float = TIE_EPSILON) -> tuple[Calibration, list]:
    """Score every candidate; return the winner and the full ranking."""
    scores = [score_features(packets, f, limit=limit) for f in candidate_features()]
    scores.sort(key=lambda s: (-s.rate, -s.bunches))
    best = scores[0]
    unsettled = undetermined_gates(scores, epsilon)

    # Measure the margin against the best candidate that is genuinely a rival,
    # not one that merely differs on a gate this capture never exercises.
    runner = next((s for s in scores if s.rate < best.rate - epsilon), None)
    return (
        Calibration(
            features=best.features,
            rate=best.rate,
            runner_up_rate=runner.rate if runner else 0.0,
            packets=best.total,
            bunches=best.bunches,
            undetermined=unsettled,
        ),
        scores,
    )


def save(calibration: Calibration, path: str = CALIBRATION_FILE) -> None:
    payload = {
        "features": calibration.features.as_dict(),
        "rate": calibration.rate,
        "runner_up_rate": calibration.runner_up_rate,
        "packets": calibration.packets,
        "bunches": calibration.bunches,
        "undetermined": calibration.undetermined,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def load(path: str = CALIBRATION_FILE) -> Features:
    """Load the calibrated layout, falling back to the modern defaults."""
    try:
        with open(path, encoding="utf-8") as fh:
            return Features(**json.load(fh)["features"])
    except (OSError, KeyError, TypeError, ValueError):
        return Features()
