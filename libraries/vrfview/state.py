"""
What the match looks like at one instant.

`state_at` is recomputed from scratch on every frame; there is no incremental
cache and no notion of "playing forward".  That is affordable because a match
is only about 150 events -- measured at 0.014 ms per call against the reference
capture, against a 16.7 ms budget at 60 fps -- and it buys the property that
makes replay UIs hard otherwise: seeking backwards, dragging the scrubber and
jumping between rounds are all exactly as correct as playing forward, because
nothing accumulates.

Alive state is scoped to the round.  Everyone is alive at a round boundary,
which is what the file implies: there is no respawn event, and no player dies
twice inside a single round window once the characterDeath arguments are read
in the right order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vrfview.model import (
    SPIKE_DEFUSED,
    SPIKE_EXPLODED,
    SPIKE_NONE,
    SPIKE_PLANTED,
    TEAM_A,
    TEAM_B,
    Kill,
    Replay,
    Round,
)

# How long a kill arrow and an ultimate pulse stay on screen, in playback ms.
KILL_FADE_MS = 2500
ULT_FADE_MS = 1500

_SPIKE_STATE = {
    "planted": SPIKE_PLANTED,
    "defused": SPIKE_DEFUSED,
    "exploded": SPIKE_EXPLODED,
}


@dataclass(frozen=True)
class Snapshot:
    """The complete drawable state at `t_ms`."""

    t_ms: int
    round: Round | None = None
    alive: frozenset[int] = frozenset()
    dead_since: dict[int, int] = field(default_factory=dict)
    recent_kills: tuple[tuple[Kill, float], ...] = ()
    recent_ults: tuple[tuple[int, float], ...] = ()
    round_kills: tuple[Kill, ...] = ()
    ulted_this_round: frozenset[int] = frozenset()
    spike_state: str = SPIKE_NONE
    spike_since_ms: int | None = None
    kd: dict[int, tuple[int, int]] = field(default_factory=dict)
    score: tuple[int, int] = (0, 0)

    def kills_of(self, actor_id: int) -> int:
        return self.kd.get(actor_id, (0, 0))[0]

    def deaths_of(self, actor_id: int) -> int:
        return self.kd.get(actor_id, (0, 0))[1]

    def is_alive(self, actor_id: int) -> bool:
        return actor_id in self.alive


def _kd_at(replay: Replay, t_ms: int) -> dict[int, tuple[int, int]]:
    """Running (kills, deaths) per actor over the whole match up to `t_ms`."""
    kd: dict[int, tuple[int, int]] = {p.actor_id: (0, 0) for p in replay.players}
    for k in replay.kills:
        if k.t_ms > t_ms:
            break
        if not k.is_suicide and k.killer in kd:
            kills, deaths = kd[k.killer]
            kd[k.killer] = (kills + 1, deaths)
        if k.victim in kd:
            kills, deaths = kd[k.victim]
            kd[k.victim] = (kills, deaths + 1)
    return kd


def _deaths_this_round(
    replay: Replay,
    rnd: Round | None,
    t_ms: int,
) -> tuple[dict[int, int], list[Kill]]:
    """When each victim died in the current round, and the kills that did it."""
    dead_since: dict[int, int] = {}
    round_kills: list[Kill] = []
    if rnd is None:
        return dead_since, round_kills
    for k in replay.kills:
        if k.t_ms > t_ms:
            break
        if rnd.contains(k.t_ms):
            dead_since.setdefault(k.victim, k.t_ms)
            round_kills.append(k)
    return dead_since, round_kills


def _spike_at(
    replay: Replay,
    rnd: Round | None,
    t_ms: int,
) -> tuple[str, int | None]:
    """The last spike event inside the current round wins; nothing carries over."""
    if rnd is None:
        return SPIKE_NONE, None
    state, since = SPIKE_NONE, None
    for sp in replay.spike:
        if sp.t_ms > t_ms:
            break
        if rnd.contains(sp.t_ms):
            state = _SPIKE_STATE.get(sp.kind, SPIKE_NONE)
            since = sp.t_ms
    return state, since


def state_at(
    replay: Replay,
    t_ms: int,
    kill_fade_ms: int = KILL_FADE_MS,
    ult_fade_ms: int = ULT_FADE_MS,
) -> Snapshot:
    """Everything drawable at `t_ms`, computed from scratch."""
    t_ms = max(0, min(int(t_ms), replay.length_ms))
    rnd = replay.round_at(t_ms)

    kd = _kd_at(replay, t_ms)
    dead_since, round_kills = _deaths_this_round(replay, rnd, t_ms)
    alive = frozenset(
        p.actor_id for p in replay.players if p.actor_id not in dead_since
    )

    recent_kills = tuple(
        (k, (t_ms - k.t_ms) / kill_fade_ms)
        for k in replay.kills
        if 0 <= t_ms - k.t_ms < kill_fade_ms
    )
    recent_ults = tuple(
        (u.actor_id, (t_ms - u.t_ms) / ult_fade_ms)
        for u in replay.ultimates
        if 0 <= t_ms - u.t_ms < ult_fade_ms
    )

    ulted_this_round = frozenset(
        u.actor_id
        for u in replay.ultimates
        if u.t_ms <= t_ms and rnd is not None and rnd.contains(u.t_ms)
    )

    spike_state, spike_since = _spike_at(replay, rnd, t_ms)

    score_a = sum(1 for r in replay.rounds if r.winner == TEAM_A and r.end_ms <= t_ms)
    score_b = sum(1 for r in replay.rounds if r.winner == TEAM_B and r.end_ms <= t_ms)

    return Snapshot(
        t_ms=t_ms,
        round=rnd,
        alive=alive,
        dead_since=dead_since,
        recent_kills=recent_kills,
        recent_ults=recent_ults,
        round_kills=tuple(round_kills),
        ulted_this_round=ulted_this_round,
        spike_state=spike_state,
        spike_since_ms=spike_since,
        kd=kd,
        score=(score_a, score_b),
    )
