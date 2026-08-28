"""
How long a round's buy phase lasts, which is external knowledge and measured.

Nothing in a `.vrf` states a buy phase.  No actor replicates a spawn barrier and
no event group fires when one drops -- `vrfview.barriers` says so at length, and
`docs/039f3991_summary.md` section 6 lists the seven groups that do fire.  What a
capture holds is `roundStarted`, and `roundStarted` fires at the *start* of the
buy phase: a round therefore opens with ten players stood in spawn behind a
barrier, and the instant the round actually begins is thirty or forty-five
seconds later with nothing naming it.

So this is a published rule of the game, in the shape `abilityfacts` and
`names.AGENT_CODENAMES` set for knowledge that is looked up rather than read --
except that this one is also *checked*, because there is ground truth available
for it: **nobody can act through a barrier**, so the first kill or spike plant in
a round is a lower bound on when that round's barrier dropped.

Measured over all 103 captures in the reference library, 2,176 rounds carrying a
kill or a plant:

    round        n     earliest action    median
    1          103          46.6 s        58.8 s
    13         102          46.7 s        56.2 s
    25          14          49.9 s        63.1 s
    26-30       30          32.3 s        ~40 s
    all others 1927         31.2 s        41.0 s

Forty-five seconds on rounds 1, 13 and 25 and thirty everywhere else has **zero
violations over those 2,176 rounds**, at a minimum margin of 1.24 s.  The two
populations are two seconds and fifteen seconds clear of their respective floors
and never cross.  `tests/test_rounds.py` re-runs the whole figure.

Note what that measurement settles about overtime, because it is not what one
would guess: only the *first* overtime round gets the long buy.  Round 26 is the
round that disproves the alternative outright -- its earliest action anywhere in
the library is 34.9 s, which no 45 s buy phase can produce.  The long buy belongs
to the three moments the whole economy resets: the match, half time, overtime.

Keyed on the round **number** and deliberately not on `Replay.side_swap_ms`.
`loader` keeps the last `switchTeams` event it sees, and in overtime the sides
swap every round -- so on a 26-round capture `side_swap_ms` names round 26 rather
than half time.  A round's number comes from `roundStarted.metadata`, which is
the file's own numbering and correct even where the recording begins late.

What would retire all of this is a decode.  `csharp/parser` carries Riot's own
`EAresGamePhase` with `RoundStarting` and `InRound` in it, and reaching those
would mean decoder work, a decode-format bump and a re-decode of the library --
at which point the barrier drop would be read rather than looked up, and this
module would become a fallback for captures that predate the change.
"""

from __future__ import annotations

BUY_PHASE_MS = 30_000
"""The buy phase every ordinary round opens with."""

LONG_BUY_MS = 45_000
"""The buy phase the three economy resets open with."""

LONG_BUY_ROUNDS = (1, 13, 25)
"""Match start, half time and overtime start -- and no other overtime round."""


def buy_phase_ms(number: int) -> int:
    """How long round `number` spends behind the barrier."""
    return LONG_BUY_MS if number in LONG_BUY_ROUNDS else BUY_PHASE_MS
