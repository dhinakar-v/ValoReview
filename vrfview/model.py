"""
The shapes a replay reduces to, once the container has been parsed.

These are plain records with no behaviour beyond derived properties, and they
deliberately import nothing from vrfnet or tkinter: the whole model and
inference layer has to stay runnable without a display so it can be unit
tested and dumped as text.

What is read from the file and what is not
------------------------------------------
Read directly: event times, event groups, actor net IDs, round numbers, the
map's internal path, the recording timestamp and the match length.

Not in the file, and therefore either absent or marked inferred: player names,
Riot IDs, team assignment, attacker/defender sides, round win-loss results,
agent identity per actor, and every kind of position.  docs/039f3991_summary.md
section 8 is the authoritative list.  `Player.team` and `Round.winner` are
inferred by vrfview.infer and carry an explicit unknown state rather than a
guess; `Replay.notes` records how each inference was reached so the UI can show
its working.

The characterDeath argument order
---------------------------------
`args[1]` is the killer and `args[2]` the victim.  The summary doc originally
had this reversed; under that reading every one of the 15 rounds in the
reference capture contains a player who dies twice, and in round 1 actor 646
dies at 87.3s, dies again at 105.3s, then scores a kill at 114.0s.  Under the
order used here no round has a repeat victim.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TEAM_A = "A"
TEAM_B = "B"
TEAM_UNKNOWN = "?"

WIN_WIPE = "wipe"
WIN_DEFUSE = "defuse"
WIN_EXPLODE = "explode"
WIN_UNDETERMINED = "undetermined"

SPIKE_NONE = "none"
SPIKE_PLANTED = "planted"
SPIKE_DEFUSED = "defused"
SPIKE_EXPLODED = "exploded"


@dataclass(frozen=True)
class Player:
    """One actor net ID that appeared in a kill, with its inferred team."""

    actor_id: int
    team: str = TEAM_UNKNOWN
    label: str = ""
    merged_from: tuple[int, ...] = ()

    @property
    def known_team(self) -> bool:
        return self.team in (TEAM_A, TEAM_B)

    @property
    def display(self) -> str:
        return f"{self.label} #{self.actor_id}" if self.label else f"#{self.actor_id}"


@dataclass(frozen=True)
class Kill:
    """A characterDeath event, killer and victim as actor net IDs."""

    t_ms: int
    killer: int
    victim: int
    round_no: int = 0

    @property
    def is_suicide(self) -> bool:
        return self.killer == self.victim


@dataclass(frozen=True)
class Ultimate:
    """A characterUltimateUsed event.  Carries one actor net ID."""

    t_ms: int
    actor_id: int
    round_no: int = 0


@dataclass(frozen=True)
class SpikeEvent:
    """A spike plant, defuse or explode.

    These events carry no actor net ID at all -- `args` is just the type ID --
    so the spike can never be attributed to a player or to a site.
    """

    t_ms: int
    kind: str
    round_no: int = 0


@dataclass(frozen=True)
class Round:
    """One round, bounded by consecutive roundStarted events.

    `number` is 1-based for display; `index` is the 0-based value the file puts
    in `roundStarted.metadata`.  `winner` is inferred and may be unknown.
    """

    number: int
    index: int
    start_ms: int
    end_ms: int
    winner: str = TEAM_UNKNOWN
    reason: str = WIN_UNDETERMINED

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def decided(self) -> bool:
        return self.winner in (TEAM_A, TEAM_B)

    def contains(self, t_ms: int) -> bool:
        return self.start_ms <= t_ms < self.end_ms


@dataclass
class Replay:
    """Everything the viewer needs, from either a .vrf or a dumped JSON."""

    source: str = ""
    map_path: str = ""
    map_name: str = ""
    length_ms: int = 0
    recorded_utc: str = ""
    build: str = ""
    players: list[Player] = field(default_factory=list)
    rounds: list[Round] = field(default_factory=list)
    kills: list[Kill] = field(default_factory=list)
    ultimates: list[Ultimate] = field(default_factory=list)
    spike: list[SpikeEvent] = field(default_factory=list)
    side_swap_ms: int | None = None
    subjects: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def player(self, actor_id: int) -> Player | None:
        for p in self.players:
            if p.actor_id == actor_id:
                return p
        return None

    def team(self, name: str) -> list[Player]:
        return [p for p in self.players if p.team == name]

    def round_at(self, t_ms: int) -> Round | None:
        for r in self.rounds:
            if r.contains(t_ms):
                return r
        return self.rounds[-1] if self.rounds and t_ms >= self.length_ms else None

    @property
    def event_times(self) -> list[int]:
        """Every event instant, sorted -- the step-to-next-event targets."""
        ts = {k.t_ms for k in self.kills}
        ts |= {u.t_ms for u in self.ultimates}
        ts |= {s.t_ms for s in self.spike}
        ts |= {r.start_ms for r in self.rounds}
        return sorted(ts)

    @property
    def score(self) -> tuple[int, int]:
        a = sum(1 for r in self.rounds if r.winner == TEAM_A)
        b = sum(1 for r in self.rounds if r.winner == TEAM_B)
        return a, b
