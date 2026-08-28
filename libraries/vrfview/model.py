"""
The shapes a replay reduces to, once the container has been parsed.

These are plain records with no behaviour beyond derived properties, and they
deliberately import no decoder and nothing that draws: the whole model and
inference layer has to stay runnable without a display so it can be unit
tested and dumped as text.

What is read from the file and what is not
------------------------------------------
Read directly: event times, event groups, actor net IDs, round numbers, the
map's internal path, the match id, the recording timestamp, the match length,
and the player loadouts -- a subject UUID and an agent UUID per roster slot.

Read too, but only where the build is one `payload_transform` names, and only
through vrfview.tracks: each pawn's agent codename and its position, heading
and pitch over time.  Those are as read as a kill event is -- they come off the
wire, not from a derivation -- but they are not in a plain chunk, so a replay
that was never handed a track set simply has none, and says so in
`Replay.position_source` rather than pretending the match had no positions.

Not in the file, and therefore either absent or marked inferred: player names,
Riot IDs, team assignment, attacker/defender sides, round win-loss results,
health, armour and credits.

The map name and the agent names are external knowledge: they are UUIDs and
asset paths here, and vrfview.names resolves them against Riot's published
content catalogue, recording which source answered.  docs/039f3991_summary.md
section 8 is the authoritative list.  `Player.team` and `Round.winner` are
inferred by vrfview.infer and carry an explicit unknown state rather than a
guess; `Replay.notes` records how each inference was reached and
`Replay.catalog_notes` how each name was looked up, so the UI can show its
working and keep the two kinds of claim apart.

The characterDeath argument order
---------------------------------
`args[1]` is the killer and `args[2]` the victim.  The summary doc originally
had this reversed; under that reading every one of the 15 rounds in the
reference capture contains a player who dies twice, and in round 1 actor 646
dies at 87.3s, dies again at 105.3s, then scores a kill at 114.0s.  Under the
order used here no round has a repeat victim.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

from vrfview import roundrules

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

# Movement arrives at about 100 Hz per pawn, which is two orders more than a
# 60 fps scrubber can show and about 2.4 million samples over a full match.
# vrfview.tracks thins it to this rate on the way in; the loss at a walking
# 300 uu/s is some 30 uu, well under the radius of the dot that draws it.
POSITION_HZ = 10

# Two samples further apart than this are a gap in the record rather than a
# straight line worth drawing, and past MAX_HOLD_MS a lone sample stops
# standing in for the present altogether.  See Track.at.
MAX_INTERPOLATE_MS = 1000
MAX_HOLD_MS = 2000


@dataclass(frozen=True)
class Player:
    """
    One actor net ID that appeared in a kill, with its inferred team.

    `codename` is Riot's internal name for the agent this pawn is -- `Hunter`,
    `Wushu` -- read from the actor's archetype path by vrfview.tracks.  `agent`
    is the public name vrfview.names looks that codename up as.  They are kept
    apart for the same reason `map_path` and `map_name` are: one is in the
    file and the other is a join against a catalogue that may not be there.
    """

    actor_id: int
    team: str = TEAM_UNKNOWN
    label: str = ""
    merged_from: tuple[int, ...] = ()
    codename: str = ""
    agent: str = ""

    @property
    def known_team(self) -> bool:
        return self.team in (TEAM_A, TEAM_B)

    @property
    def display(self) -> str:
        return f"{self.label} #{self.actor_id}" if self.label else f"#{self.actor_id}"

    @property
    def identity(self) -> str:
        """The best name this player has: agent, else codename, else label."""
        return self.agent or self.codename or self.display


@dataclass(frozen=True)
class Loadout:
    """
    One entry of match_metadata.playerLoadouts, as the file states it.

    `subject` and `character_id` are both read straight from the file; `agent`
    is the display name that vrfview.names resolves for `character_id` against
    Riot's content catalogue, and stays empty when no catalogue is available.

    Nothing links a loadout to an actor net ID.  The loadout list is a roster,
    in the file's own order, and attaching any of it to a Player would be an
    invention -- see vrfview.names.
    """

    index: int
    subject: str = ""
    character_id: str = ""
    agent: str = ""

    @property
    def display(self) -> str:
        return self.agent or f"unresolved {self.character_id or '?'}"


@dataclass(frozen=True)
class Position:
    """
    Where one actor was at one instant, in the map's own Unreal units.

    `yaw` and `pitch` are degrees in 0..360, straight from the movement
    record's packed angle dword.  **Positive pitch is looking up**, and that
    is measured rather than assumed: at every kill in the reference library
    the killer's pitch is compared with the true angle to the victim, whose z
    is also known, and it agrees to a median 0.91 degrees while the negated
    reading is four times worse.  Nothing else in the file pins the sign, so
    tests/test_movement.py is where it lives.  Every player sample in the
    library is within 90 degrees of the horizon, so a pitch outside that is a
    bug and not a look.

    There is no interpolation flag: a Position
    handed back by `Track.at` carries the timestamp it was actually measured
    at when it is a held sample, and the requested time when it is an
    interpolation between two, so its own `t_ms` says how fresh it is.
    """

    t_ms: int
    actor_id: int
    x: float
    y: float
    z: float
    yaw: float = 0.0
    pitch: float = 0.0


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def _lerp_angle(a: float, b: float, f: float) -> float:
    """
    Shortest arc, so a heading crossing 0/360 does not spin the long way.

    Used for **both** yaw and pitch.  Pitch is the same kind of quantity --
    degrees in 0..360 off the same packed angle dword -- and a player looking
    a degree above the horizon is at 1.0 while a degree below is at 359.0, so
    interpolating those linearly lands at 180: pointing backwards, at the
    exact moment somebody flicks across the horizon.  Measured over the whole
    reference library: at 2,949 kills the killer's decoded pitch is a median
    0.91 degrees off the true angle to the victim with this, and the linear
    form's 99th percentile error was 159 degrees.  See tests/test_movement.py.

    A note for the TypeScript port: Python's `%` takes the sign of the
    divisor and JavaScript's takes the sign of the dividend, so `(-350 + 180)
    % 360` is 190 here and -170 there.  A naive port makes every crossing of
    0/360 interpolate the long way round, which reads as a rendering glitch
    rather than an arithmetic one.  web/src/model/track.ts routes both
    remainders through a floored `mod`, and tests/golden/track_at.json pins it.
    """
    delta = (b - a + 180.0) % 360.0 - 180.0
    return (a + delta * f) % 360.0


@dataclass(frozen=True)
class Track:
    """
    One actor's whole decoded trajectory, in time order.

    Sampling is not uniform -- the game emits movement in bursts and stops
    emitting for an actor that has nothing to say -- so `at` has to decide
    between three answers, and the two constants above it are where that
    judgement lives.  Interpolating across a long gap would draw a straight
    line through a wall; refusing to hold a position for even a moment would
    make an actor flicker.  So: interpolate across a short gap, hold a lone
    sample briefly, and past that report no position at all rather than a
    stale one dressed as current.
    """

    actor_id: int
    samples: tuple[Position, ...] = ()

    def __len__(self) -> int:
        return len(self.samples)

    @property
    def span_ms(self) -> tuple[int, int]:
        if not self.samples:
            return (0, 0)
        return (self.samples[0].t_ms, self.samples[-1].t_ms)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(min x, max x, min y, max y) -- the extent this actor covered."""
        if not self.samples:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p.x for p in self.samples]
        ys = [p.y for p in self.samples]
        return (min(xs), max(xs), min(ys), max(ys))

    def at(self, t_ms: int) -> Position | None:
        """Where this actor was at `t_ms`, or None if that is not known."""
        if not self.samples:
            return None
        i = bisect_left(self.samples, t_ms, key=lambda p: p.t_ms)
        before = self.samples[i - 1] if i > 0 else None
        after = self.samples[i] if i < len(self.samples) else None
        if after is not None and after.t_ms == t_ms:
            return after
        if (
            before is not None
            and after is not None
            and after.t_ms - before.t_ms <= MAX_INTERPOLATE_MS
        ):
            f = (t_ms - before.t_ms) / (after.t_ms - before.t_ms)
            return Position(
                t_ms=t_ms,
                actor_id=self.actor_id,
                x=_lerp(before.x, after.x, f),
                y=_lerp(before.y, after.y, f),
                z=_lerp(before.z, after.z, f),
                yaw=_lerp_angle(before.yaw, after.yaw, f),
                # An angle, like the yaw beside it, and interpolated as one.
                # It was linear here until the pitch was first measured
                # against the kill geometry; see _lerp_angle.
                pitch=_lerp_angle(before.pitch, after.pitch, f),
            )
        candidates = [p for p in (before, after) if p is not None]
        nearest = min(candidates, key=lambda p: abs(p.t_ms - t_ms))
        if abs(nearest.t_ms - t_ms) <= MAX_HOLD_MS:
            return nearest
        return None


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
    """
    A spike plant, defuse or explode.

    These events carry no actor net ID at all -- `args` is just the type ID --
    so the spike can never be attributed to a **player**.  It can be attributed
    to a **place**, and `location` is that: see below.

    `location` is decoded, where `t_ms` and `kind` are read.  The event chunk
    holds no coordinate; what holds one is the `TimedBomb` actor the plant
    spawns, whose transform `csharpdecode` has always carried and `tracks`
    discarded, because nothing had established those numbers were the spike
    rather than plausible noise.  Measured over the whole reference library:
    274 plants across 21 captures pair one-to-one with a `TimedBomb` spawn
    (0 unpaired, and the spawn count equals the plant count in every capture),
    at a constant +8..15 ms time-base offset; the coordinate is a median 69.5 uu
    from some player's own decoded position at that instant, 94.5% within 100
    uu; and **274 of 274 land inside the radar image's playable silhouette**,
    where a random coordinate lands inside about a third of the time.

    It is `None` on a defuse or an explode, and on a plant in a capture nothing
    has decoded -- a plant with no coordinate is the ordinary state, never an
    origin.  Only the plant is measured: `Bomb_Defuser` actors carry transforms
    too, but nothing has checked them, so nothing reads them.
    """

    t_ms: int
    kind: str
    round_no: int = 0
    location: tuple[float, float, float] | None = None

    @property
    def placed(self) -> bool:
        """Whether this event knows where it happened."""
        return self.location is not None


@dataclass(frozen=True)
class Round:
    """
    One round, bounded by consecutive roundStarted events.

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
    def buy_phase_ms(self) -> int:
        """How long this round spends behind the barrier. See vrfview.roundrules."""
        return roundrules.buy_phase_ms(self.number)

    @property
    def action_start_ms(self) -> int:
        """
        When the barrier drops and the round is playable, looked up not read.

        Clamped to `end_ms`, which is the whole of the special-casing this needs:
        a round shorter than its own buy phase -- a surrender, a recording that
        stops mid-round, a synthetic fixture -- would otherwise place the instant
        the round begins after the instant it ends.  Where the clamp bites this
        equals `end_ms`, and every window in this model is half-open, so the
        marker simply falls outside its own round and nothing draws it.
        """
        return min(self.start_ms + self.buy_phase_ms, self.end_ms)

    @property
    def decided(self) -> bool:
        return self.winner in (TEAM_A, TEAM_B)

    def contains(self, t_ms: int) -> bool:
        return self.start_ms <= t_ms < self.end_ms


@dataclass
class Replay:
    """Everything the viewer needs, from either a .vrf or a dumped JSON."""

    source: str = ""
    match_id: str = ""
    map_path: str = ""
    map_name: str = ""
    map_name_source: str = ""
    length_ms: int = 0
    recorded_utc: str = ""
    build: str = ""
    players: list[Player] = field(default_factory=list)
    rounds: list[Round] = field(default_factory=list)
    kills: list[Kill] = field(default_factory=list)
    ultimates: list[Ultimate] = field(default_factory=list)
    spike: list[SpikeEvent] = field(default_factory=list)
    side_swap_ms: int | None = None
    loadouts: list[Loadout] = field(default_factory=list)
    catalog_source: str = ""
    notes: list[str] = field(default_factory=list)
    catalog_notes: list[str] = field(default_factory=list)
    positions: dict[int, Track] = field(default_factory=dict)
    position_source: str = ""
    # Ability casts, and the tracks of the pawns some of them spawn.  Both
    # arrive with the positions and from the same decode -- see vrfview.tracks
    # and vrfview.abilities -- so a replay that has one normally has the other,
    # and a replay with neither says so in `position_source` rather than
    # implying the match had no abilities in it.
    ability_casts: list = field(default_factory=list)
    ability_tracks: dict[int, Track] = field(default_factory=dict)

    @property
    def has_abilities(self) -> bool:
        return bool(self.ability_casts)

    @property
    def has_positions(self) -> bool:
        """Whether anything in this replay can be drawn at a map coordinate."""
        return any(t.samples for t in self.positions.values())

    def track(self, actor_id: int) -> Track | None:
        return self.positions.get(actor_id)

    def ability_track(self, actor_id: int) -> Track | None:
        return self.ability_tracks.get(actor_id)

    def casts_in(self, round_no: int) -> list:
        return [c for c in self.ability_casts if c.round_no == round_no]

    @property
    def subjects(self) -> list[str]:
        """Player UUIDs from the loadouts, in the file's own order."""
        return [x.subject for x in self.loadouts]

    @property
    def roster(self) -> list[str]:
        """Agent names, where the catalogue resolved them."""
        return [x.agent for x in self.loadouts if x.agent]

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
        """
        Every event instant, sorted -- the step-to-next-event targets.

        A round contributes `action_start_ms` and not `start_ms`: stepping back
        from the first kill should land where the round became playable, not on
        thirty seconds of ten people stood behind a barrier.  It is the same one
        stop per round either way, moved rather than added, so nothing counting
        presses gains an entry.  A round whose clamp bit contributes its `end_ms`,
        which the next round contributes as its own start anyway.
        """
        ts = {k.t_ms for k in self.kills}
        ts |= {u.t_ms for u in self.ultimates}
        ts |= {s.t_ms for s in self.spike}
        ts |= {r.action_start_ms for r in self.rounds}
        ts |= {c.t_ms for c in self.ability_casts}
        return sorted(ts)

    @property
    def score(self) -> tuple[int, int]:
        a = sum(1 for r in self.rounds if r.winner == TEAM_A)
        b = sum(1 for r in self.rounds if r.winner == TEAM_B)
        return a, b
