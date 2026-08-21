"""
Everything the viewer shows that the file does not actually say.

The .vrf gives anonymous actor net IDs, event times and round numbers.  It does
not give teams, round results, attacker/defender sides, or any link from an
actor ID to a player.  This module derives what can be derived honestly, and
records an explicit unknown everywhere it cannot.  Every derivation appends a
line to `Replay.notes`, which the UI surfaces in its provenance panel.

Teams -- exact, not heuristic
-----------------------------
Kills are almost never same-team, so the kill graph should be bipartite, and on
the reference capture it is: 0 same-team kills out of 108, and exactly one 5v5
split, confirmed unique by exhaustive search over all 126 candidate splits.
Two-colouring by breadth-first search reproduces that split in O(V+E) and,
unlike the exhaustive search, does not assume ten players or a 5v5.  An odd
cycle -- a genuine same-team kill -- makes the graph non-bipartite, and is
reported as such rather than resolved by majority vote.

Reconnects
----------
Four of 25 surveyed demos carry eleven actor IDs, not ten: ten in the usual
500-1500 band plus one much higher (25604, 28268).  Their activity spans are
disjoint -- in 4f1f51bc, actor 1058 runs 66-889s and 25604 runs 1079-2769s --
which is a player who dropped and rejoined under a new actor ID.  Merging is
attempted only when a team has more members than its opponent, only between
same-team actors whose spans do not overlap, and only when the result is
balanced.  Ambiguity is left unmerged and noted.

Round outcomes
--------------
The first terminal condition inside a round window wins it.  A team losing all
of its players is decisive.  A defuse or an explode is recorded as the reason
but leaves the winner unknown, because spike events carry no actor ID at all,
so which side planted is not recoverable.  On the reference capture this gives
11 wipes, one defuse, one explode and two rounds left undetermined -- and those
two stay undetermined rather than being filled in.
"""

from __future__ import annotations

from collections import deque

from vrfview.model import (
    TEAM_A,
    TEAM_B,
    TEAM_UNKNOWN,
    WIN_DEFUSE,
    WIN_EXPLODE,
    WIN_UNDETERMINED,
    WIN_WIPE,
    Kill,
    Player,
    Replay,
    Round,
    Ultimate,
)


def annotate(replay: Replay) -> Replay:
    """Fill in teams, reconnect merges, round numbers and round outcomes."""
    _assign_teams(replay)
    _merge_reconnects(replay)
    _label_players(replay)
    _assign_round_numbers(replay)
    _assign_outcomes(replay)
    return replay


# --- teams ---------------------------------------------------------------


def _adjacency(kills: list[Kill]) -> dict[int, set[int]]:
    """Undirected kill graph, self-kills dropped.

    The reference capture has one self-kill (actor 852), which is a fall or a
    suicide rather than a same-team kill and carries no team information.
    """
    adj: dict[int, set[int]] = {}
    for k in kills:
        adj.setdefault(k.killer, set())
        adj.setdefault(k.victim, set())
        if k.killer == k.victim:
            continue
        adj[k.killer].add(k.victim)
        adj[k.victim].add(k.killer)
    return adj


def two_colour(
    adj: dict[int, set[int]],
) -> tuple[list[tuple[set[int], set[int]]], bool]:
    """Two-colour each connected component; report whether all are bipartite."""
    colour: dict[int, int] = {}
    components: list[tuple[set[int], set[int]]] = []
    bipartite = True
    for root in sorted(adj):
        if root in colour:
            continue
        colour[root] = 0
        side0, side1 = {root}, set()
        queue = deque([root])
        while queue:
            node = queue.popleft()
            for peer in adj[node]:
                if peer not in colour:
                    colour[peer] = 1 - colour[node]
                    (side0 if colour[peer] == 0 else side1).add(peer)
                    queue.append(peer)
                elif colour[peer] == colour[node]:
                    bipartite = False
        components.append((side0, side1))
    return components, bipartite


def _assign_teams(replay: Replay) -> None:
    adj = _adjacency(replay.kills)
    if not adj:
        replay.notes.append("no kills recorded; teams cannot be inferred")
        return

    components, bipartite = two_colour(adj)
    if not bipartite:
        replay.notes.append(
            "kill graph is not bipartite (a same-team kill exists); "
            "teams left unknown rather than guessed"
        )
        return

    # Join components by dropping the larger side of each into the smaller
    # team so far.  With one component -- the normal case -- this is a no-op.
    group_a: set[int] = set()
    group_b: set[int] = set()
    for side0, side1 in sorted(components, key=lambda c: -(len(c[0]) + len(c[1]))):
        big, small = (side0, side1) if len(side0) >= len(side1) else (side1, side0)
        if len(group_a) <= len(group_b):
            group_a |= big
            group_b |= small
        else:
            group_b |= big
            group_a |= small

    # Name the group holding the lowest actor ID "A", so runs are reproducible.
    if group_b and (not group_a or min(group_b) < min(group_a)):
        group_a, group_b = group_b, group_a

    replay.players = [
        Player(
            actor_id=p.actor_id,
            team=TEAM_A if p.actor_id in group_a else
            (TEAM_B if p.actor_id in group_b else TEAM_UNKNOWN),
            merged_from=p.merged_from,
        )
        for p in replay.players
    ]

    same_team = sum(
        1
        for k in replay.kills
        if not k.is_suicide
        and _team_of(replay, k.killer) == _team_of(replay, k.victim)
    )
    replay.notes.append(
        f"teams inferred by two-colouring the kill graph: "
        f"{len(group_a)}v{len(group_b)}, {same_team} same-team kills "
        f"in {len(replay.kills)}"
    )
    if len(components) > 1:
        replay.notes.append(
            f"kill graph had {len(components)} disconnected components; "
            "the join between them is a balance heuristic, not evidence"
        )


def _team_of(replay: Replay, actor_id: int) -> str:
    p = replay.player(actor_id)
    return p.team if p else TEAM_UNKNOWN


# --- reconnects ----------------------------------------------------------


def _spans(replay: Replay) -> dict[int, tuple[int, int]]:
    span: dict[int, tuple[int, int]] = {}
    for k in replay.kills:
        for a in (k.killer, k.victim):
            lo, hi = span.get(a, (k.t_ms, k.t_ms))
            span[a] = (min(lo, k.t_ms), max(hi, k.t_ms))
    for u in replay.ultimates:
        lo, hi = span.get(u.actor_id, (u.t_ms, u.t_ms))
        span[u.actor_id] = (min(lo, u.t_ms), max(hi, u.t_ms))
    return span


def _merge_reconnects(replay: Replay) -> None:
    """Fold a rejoined actor back into the one it replaced, when unambiguous."""
    a, b = len(replay.team(TEAM_A)), len(replay.team(TEAM_B))
    if a == b or not a or not b:
        return

    over = TEAM_A if a > b else TEAM_B
    span = _spans(replay)
    members = [p.actor_id for p in replay.team(over)]
    candidates = [
        (x, y)
        for i, x in enumerate(members)
        for y in members[i + 1:]
        if x in span and y in span and _disjoint(span[x], span[y])
    ]
    if len(candidates) != 1:
        replay.notes.append(
            f"team {over} has {max(a, b)} actor IDs against {min(a, b)}; "
            f"{len(candidates)} reconnect pairings fit, so none was applied"
        )
        return

    x, y = candidates[0]
    keep, drop = (x, y) if span[x][0] <= span[y][0] else (y, x)
    _rewrite_actor(replay, drop, keep)
    replay.notes.append(
        f"actor {drop} merged into {keep} as a reconnect: their activity spans "
        f"({span[drop][0] / 1000:.0f}-{span[drop][1] / 1000:.0f}s and "
        f"{span[keep][0] / 1000:.0f}-{span[keep][1] / 1000:.0f}s) do not overlap"
    )


def _disjoint(one: tuple[int, int], other: tuple[int, int]) -> bool:
    return one[1] < other[0] or other[1] < one[0]


def _rewrite_actor(replay: Replay, drop: int, keep: int) -> None:
    replay.kills = [
        Kill(
            t_ms=k.t_ms,
            killer=keep if k.killer == drop else k.killer,
            victim=keep if k.victim == drop else k.victim,
            round_no=k.round_no,
        )
        for k in replay.kills
    ]
    replay.ultimates = [
        Ultimate(
            t_ms=u.t_ms,
            actor_id=keep if u.actor_id == drop else u.actor_id,
            round_no=u.round_no,
        )
        for u in replay.ultimates
    ]
    replay.players = [
        Player(
            actor_id=p.actor_id,
            team=p.team,
            label=p.label,
            merged_from=p.merged_from + (drop,) if p.actor_id == keep
            else p.merged_from,
        )
        for p in replay.players
        if p.actor_id != drop
    ]


def _label_players(replay: Replay) -> None:
    """Positional labels only -- A1..A5 -- never an invented agent name."""
    counters = {TEAM_A: 0, TEAM_B: 0, TEAM_UNKNOWN: 0}
    labelled = []
    for p in sorted(replay.players, key=lambda q: (q.team, q.actor_id)):
        counters[p.team] += 1
        prefix = p.team if p.team != TEAM_UNKNOWN else "U"
        labelled.append(
            Player(
                actor_id=p.actor_id,
                team=p.team,
                label=f"{prefix}{counters[p.team]}",
                merged_from=p.merged_from,
            )
        )
    replay.players = labelled


# --- rounds --------------------------------------------------------------


def _round_index_at(replay: Replay, t_ms: int) -> int:
    for r in replay.rounds:
        if r.contains(t_ms):
            return r.number
    return replay.rounds[-1].number if replay.rounds else 0


def _assign_round_numbers(replay: Replay) -> None:
    replay.kills = [
        Kill(k.t_ms, k.killer, k.victim, _round_index_at(replay, k.t_ms))
        for k in replay.kills
    ]
    replay.ultimates = [
        Ultimate(u.t_ms, u.actor_id, _round_index_at(replay, u.t_ms))
        for u in replay.ultimates
    ]
    replay.spike = [
        type(s)(s.t_ms, s.kind, _round_index_at(replay, s.t_ms)) for s in replay.spike
    ]


def _assign_outcomes(replay: Replay) -> None:
    sizes = {TEAM_A: len(replay.team(TEAM_A)), TEAM_B: len(replay.team(TEAM_B))}
    if not sizes[TEAM_A] or not sizes[TEAM_B]:
        replay.notes.append("teams unknown, so no round outcome can be inferred")
        return

    decided = []
    for i, rnd in enumerate(replay.rounds):
        winner, reason = _outcome(replay, rnd, sizes)
        decided.append(
            Round(
                number=rnd.number,
                index=rnd.index,
                start_ms=rnd.start_ms,
                end_ms=rnd.end_ms,
                winner=winner,
                reason=reason,
            )
        )
    replay.rounds = decided

    tally: dict[str, int] = {}
    for r in replay.rounds:
        tally[r.reason] = tally.get(r.reason, 0) + 1
    shape = ", ".join(f"{v} {k}" for k, v in sorted(tally.items()))
    replay.notes.append(f"round outcomes inferred ({shape})")


def _outcome(replay: Replay, rnd: Round, sizes: dict[str, int]) -> tuple[str, str]:
    """First terminal condition inside the round window decides it."""
    events: list[tuple[int, str, object]] = []
    events += [(k.t_ms, "kill", k) for k in replay.kills if rnd.contains(k.t_ms)]
    events += [(s.t_ms, "spike", s) for s in replay.spike if rnd.contains(s.t_ms)]
    events.sort(key=lambda e: e[0])

    dead: dict[str, set[int]] = {TEAM_A: set(), TEAM_B: set()}
    for _, kind, item in events:
        if kind == "kill":
            team = _team_of(replay, item.victim)
            if team in dead:
                dead[team].add(item.victim)
                if len(dead[team]) >= sizes[team]:
                    return (TEAM_B if team == TEAM_A else TEAM_A), WIN_WIPE
        elif item.kind == "defused":
            return TEAM_UNKNOWN, WIN_DEFUSE
        elif item.kind == "exploded":
            return TEAM_UNKNOWN, WIN_EXPLODE
    return TEAM_UNKNOWN, WIN_UNDETERMINED
