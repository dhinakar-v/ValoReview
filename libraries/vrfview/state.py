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

Positions do not change that
----------------------------
A track holds tens of thousands of samples, so the from-scratch rule only
survives because `Track.at` is a binary search: ten of them per frame, against
the linear passes over some 150 events that were already there.  Measured on a
fully decoded 12.10 capture -- 199,180 samples over ten players and 190 kills
-- `state_at` costs 0.127 ms, against 0.030 ms for the same replay with its
tracks removed and 16.7 ms of budget at 60 fps.  Nothing is carried between
frames, and seeking backwards stays exactly as correct as playing forward.  Where a player has stopped emitting movement -- which is
what dying looks like on the wire -- `death_positions` holds the last place
they were seen this round, so the scene can leave a body rather than have a
player vanish or, worse, appear to keep walking.
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
    Position,
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
    positions: dict[int, Position] = field(default_factory=dict)
    death_positions: dict[int, Position] = field(default_factory=dict)
    # Ability casts already made in the current round, and where the pawns
    # some of them spawned are now.  Scoped to the round for the same reason
    # `alive` is: a smoke thrown last round is not a fact about this one.
    round_casts: tuple = ()
    ability_positions: dict[int, Position] = field(default_factory=dict)

    @property
    def has_positions(self) -> bool:
        return bool(self.positions or self.death_positions)

    def position_of(self, actor_id: int) -> Position | None:
        """Where an actor is now, or where it fell if it has stopped moving."""
        return self.positions.get(actor_id) or self.death_positions.get(actor_id)

    def kills_of(self, actor_id: int) -> int:
        return self.kd.get(actor_id, (0, 0))[0]

    def deaths_of(self, actor_id: int) -> int:
        return self.kd.get(actor_id, (0, 0))[1]

    def is_alive(self, actor_id: int) -> bool:
        return actor_id in self.alive

    @property
    def has_abilities(self) -> bool:
        return bool(self.round_casts)

    def casts_of(self, codename: str) -> tuple:
        """Casts by one agent this round, in the order they were made."""
        return tuple(c for c in self.round_casts if c.codename == codename)


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


def _positions_at(
    replay: Replay,
    dead_since: dict[int, int],
    t_ms: int,
) -> tuple[dict[int, Position], dict[int, Position]]:
    """
    Where everyone is now, and where the dead were last seen this round.

    A player who died has no live position for long: their pawn stops sending
    movement and `Track.at` goes quiet a couple of seconds later.  Asking the
    track for the death instant instead is exact -- there is a sample at the
    millisecond of every characterDeath in the reference capture -- so the two
    dictionaries never disagree about somebody.
    """
    live: dict[int, Position] = {}
    fallen: dict[int, Position] = {}
    for actor_id, track in replay.positions.items():
        here = track.at(t_ms)
        if here is not None:
            live[actor_id] = here
        died_at = dead_since.get(actor_id)
        if died_at is not None:
            there = track.at(died_at)
            if there is not None:
                fallen[actor_id] = there
    # A death position outranks a live one: the pawn may still be replicating
    # a ragdoll, and it is the moment of the kill the viewer means to mark.
    for actor_id in fallen:
        live.pop(actor_id, None)
    return live, fallen


def _abilities_at(
    replay: Replay,
    rnd: Round | None,
    t_ms: int,
) -> tuple[tuple, dict[int, Position]]:
    """
    The casts made so far this round, and where their pawns are now.

    A cast is kept once the playhead reaches it and never removed before the
    round ends.  Unlike a kill arrow it is not an animation but the record of
    a decision, and a list that empties as you scrub forward would be unable to
    answer what utility has already been spent.

    Pawn positions go through the same `Track.at` as a player's, so an ability
    pawn that has stopped replicating disappears rather than freezing in place.
    There is deliberately no death-position fallback here: a drone is shot down
    and gone, and pinning its last coordinate would leave a marker on the map
    for something that is no longer on it.
    """
    if rnd is None:
        return (), {}
    casts = tuple(
        c for c in replay.ability_casts if rnd.contains(c.t_ms) and c.t_ms <= t_ms
    )
    live: dict[int, Position] = {}
    for cast in casts:
        for actor_id in cast.pawns:
            track = replay.ability_tracks.get(actor_id)
            here = track.at(t_ms) if track is not None else None
            if here is not None:
                live[actor_id] = here
    return casts, live


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

    positions, death_positions = _positions_at(replay, dead_since, t_ms)
    round_casts, ability_positions = _abilities_at(replay, rnd, t_ms)

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
        positions=positions,
        death_positions=death_positions,
        round_casts=round_casts,
        ability_positions=ability_positions,
    )
