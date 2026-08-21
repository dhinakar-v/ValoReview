"""
Positions, and the one bridge from the replication stream into the model.

Everything else the viewer shows comes out of a plain chunk.  This does not:
it decompresses every REPLAYDATA block, runs the whole vrfnet stack over it,
de-obfuscates each property payload and decodes the movement RPC inside.  That
costs an Oodle DLL and about four minutes on a full match, which is why it is
never done implicitly -- `loader.load` still returns a positionless Replay and
a caller has to ask for this.

Why a separate module
---------------------
`loader` reads the container, `infer` derives, `names` looks up.  This is a
fourth kind of act: it decodes a second, deeper stream out of the same file.
Keeping it apart means `model`, `infer` and `state` still import nothing from
vrfnet, and a replay whose build has no transform loses positions and nothing
else -- `attach` records the refusal in `Replay.position_source` and returns
the replay untouched, for the viewer to say so on screen.

What makes these positions trustworthy
--------------------------------------
Two checks, both run against a full 12.10 capture (2,438s, 27 blocks, 3.09
million moves over 154 actors), neither of which a decoding bug could pass by
luck:

  * at every one of the 190 characterDeath events the killer and the victim
    are within 4,440 Unreal units of each other, most within 2,000 -- that is
    weapon range, and it holds for all 190, so both the coordinates and the
    actor-to-track join are right;
  * a movement sample exists at the exact millisecond of every one of those
    events, which is what says the demo frame clock and the event clock are
    the same clock and no offset is needed.

Identifying player pawns
------------------------
An actor's archetype path names its agent: `/Game/Characters/Hunter/
Hunter_PC.Default__Hunter_PC_C` is Sova.  The path shape alone is not enough
to find the players, though -- the same capture carries `Smonk_PostDeath_PC`
at the same depth and 143 ability pawns below it -- so the codename shape is
only a filter and the real key is intersecting against the actor IDs the event
stream already names.  That intersection is exact: 11 of 11 on the reference
capture, including the reconnect.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from vrf_reader import REPLAYDATA, Oodle, VrfError, VrfFile
from vrfnet.calibrate import load as load_features
from vrfnet.payload_transform import UnsupportedBuildError, transform_for
from vrfnet.session import ReplaySession
from vrfview import abilities, positioncache, positionfile
from vrfview.model import POSITION_HZ, Player, Position, Replay, Track

# The archetype path of a player pawn: /Game/Characters/<Codename>/<Codename>_PC
CHARACTERS_ROOT = ("Game", "Characters")
PAWN_SUFFIX = "_PC"
PAWN_DEPTH = 5

NO_SOURCE_JSON = (
    "positions need the .vrf or a sidecar; a JSON dump alone carries no "
    "replication stream (write one with vrf-to-json --positions)"
)
NOT_REQUESTED = "positions not decoded (not requested)"
NOT_DECODED = (
    "positions not decoded yet; nothing stored for this capture "
    "(press DECODE POSITIONS, or let the match list prepare it)"
)


def codename_for(archetype_path: str) -> str:
    """
    The agent codename in an actor's archetype path, or empty if it is no pawn.

        /Game/Characters/Hunter/Hunter_PC.Default__Hunter_PC_C  ->  Hunter

    The object name has to be exactly the folder name plus `_PC`, which is
    what rejects `Smonk_PostDeath_PC` -- a corpse, at the same depth, under
    the same agent folder.  Ability pawns sit deeper and fail on depth.
    """
    parts = archetype_path.split("/")
    if len(parts) != PAWN_DEPTH or tuple(parts[1:3]) != CHARACTERS_ROOT:
        return ""
    codename = parts[3]
    object_name = parts[4].split(".", 1)[0]
    return codename if object_name == f"{codename}{PAWN_SUFFIX}" else ""


@dataclass(frozen=True)
class Options:
    """
    The knobs on a decode: where Oodle is, how much to read, how finely.

    Bundled rather than passed loose because every one of them is optional and
    a caller normally sets none: `attach(replay, path)` decodes the whole file
    at the default rate, which is what the viewer wants.
    """

    oodle_dll: str | None = None
    blocks: int | None = None
    hz: int = POSITION_HZ
    progress: Callable[[int, int], None] | None = None
    # Whether a stored decode may answer instead of a fresh one.  On by
    # default because re-deriving four minutes of identical arithmetic is
    # never what a caller wanted; off for the tests that have to prove the
    # decoder itself still works.
    cache: bool = True
    # Whether a fresh decode is allowed at all.  Off is how a caller asks the
    # cheap question -- "is this one already done?" -- without risking four
    # minutes on the answer being no.  See `attach_stored`.
    decode: bool = True


@dataclass
class Extraction:
    """Decoded tracks and codenames, with enough counts to describe itself."""

    positions: dict[int, Track] = field(default_factory=dict)
    codenames: dict[int, str] = field(default_factory=dict)
    # Ability actors: every spawn seen, and tracks for the `Pawn_` ones, which
    # are the only kind that ever moves.  See vrfview.abilities.
    spawns: list = field(default_factory=list)
    ability_positions: dict[int, Track] = field(default_factory=dict)
    build: str = ""
    blocks: int = 0
    hz: int = POSITION_HZ
    moves: int = 0
    pawns_seen: int = 0
    # A set, not a counter: an ignored actor turns up again in every block it
    # moves in, and reporting that as a count would multiply it by the length
    # of the match.
    ignored: set[int] = field(default_factory=set)
    refusal: str = ""

    @property
    def samples(self) -> int:
        return sum(len(t) for t in self.positions.values())

    @property
    def described(self) -> str:
        """One provenance line, in the shape Replay.position_source wants."""
        if self.refusal:
            return self.refusal
        if not self.positions:
            return (
                f"{self.build}: {self.blocks} REPLAYDATA blocks decoded but no "
                f"movement matched a player actor"
            )
        extra = ""
        if self.spawns:
            extra = (
                f"; {len(self.spawns)} ability actors, "
                f"{len(self.ability_positions)} of them with a track"
            )
        return (
            f"{self.build}: {self.samples:,} positions for "
            f"{len(self.positions)} player actors at {self.hz} Hz, thinned from "
            f"{self.moves:,} movement records over {self.blocks} REPLAYDATA "
            f"blocks ({len(self.ignored)} non-player actors ignored){extra}"
        )


def extract(
    path: str | Path,
    actor_ids: set[int],
    options: Options | None = None,
) -> Extraction:
    """
    Decode movement for `actor_ids` out of a .vrf.

    `actor_ids` is the event stream's own set of player actors and is the only
    thing that decides who is a player; every other actor that moves -- ability
    pawns, corpses -- is counted and dropped.
    """
    options = options or Options()
    vrf = VrfFile(path)
    out = Extraction(build=vrf.demo.build, hz=options.hz)
    # Ask about the build before anything expensive: the branch is in a plain
    # chunk, so four out of five captures in a library can be refused with no
    # Oodle DLL, no decompression and no wait.
    transform_for(vrf.demo.build)
    oodle = Oodle.discover(options.oodle_dll)
    session = ReplaySession(
        features=load_features(),
        branch=vrf.demo.build,
        collect_movement=True,
    )

    period_ms = max(1, round(1000 / options.hz))
    # actor -> time bucket -> the last position seen in that bucket.  Drained
    # after every block, so a full match holds one block of moves rather than
    # all 3.09 million of them at once.  Ability pawns get their own table so
    # that widening the filter costs the drone and the turret and not all 143
    # other actors that happen to move.
    buckets = _Buckets()

    todo = list(vrf.data_blocks(kinds=(REPLAYDATA,)))
    if options.blocks is not None:
        todo = todo[: options.blocks]
    for i, block in enumerate(todo):
        raw = oodle.decompress(block.blob(vrf.data), block.decompressed_size)
        session.feed_block(raw)
        _drain(session, buckets, actor_ids=actor_ids, period_ms=period_ms, out=out)
        if options.progress is not None:
            options.progress(i + 1, len(todo))
    out.blocks = len(todo)

    out.spawns = abilities.spawns_from(
        session.channels.archetypes,
        session.channels.first_seen,
    )
    out.ability_positions = _tracks_from(buckets.abilities)

    # session.channels.archetypes, not session.channels.channels: the live
    # table has already lost anyone who disconnected, which is exactly the
    # player a reconnect merge most needs a codename for.
    for actor_guid, archetype in session.channels.archetypes.items():
        codename = codename_for(archetype)
        if not codename:
            continue
        out.pawns_seen += 1
        if actor_guid in actor_ids:
            out.codenames[actor_guid] = codename

    out.positions = _tracks_from(buckets.players)
    return out


@dataclass
class _Buckets:
    """
    The two thinning tables one block of movement is drained into.

    Bundled rather than passed loose because they are always handled together
    and always by the same rule: a sample belongs to exactly one of them, and
    which one is the single decision `_drain` exists to make.
    """

    players: dict[int, dict[int, Position]] = field(default_factory=dict)
    abilities: dict[int, dict[int, Position]] = field(default_factory=dict)


def _tracks_from(buckets: dict[int, dict[int, Position]]) -> dict[int, Track]:
    """Thinned buckets back into time-ordered tracks, one per actor."""
    return {
        actor_id: Track(
            actor_id=actor_id,
            samples=tuple(by_tick[t] for t in sorted(by_tick)),
        )
        for actor_id, by_tick in sorted(buckets.items())
    }


def _drain(
    session: ReplaySession,
    buckets: _Buckets,
    *,
    actor_ids: set[int],
    period_ms: int,
    out: Extraction,
) -> None:
    """
    Move one block of samples into the buckets, thinning as they go.

    Three destinations, and the order matters.  `actor_ids` is the event
    stream's own set of players and still outranks everything: a pawn the
    events name is a player even if its archetype reads oddly.  Only what is
    left is offered to the ability parser, and only the kinds that actually
    move are kept -- a `Projectile_` never emits a movement record, so a bucket
    for one would be a promise of an arc that is not in the file.
    """
    for actor_id, samples in session.movement.samples.items():
        if actor_id in actor_ids:
            by_tick = buckets.players.setdefault(actor_id, {})
        elif _is_moving_ability(session, actor_id):
            by_tick = buckets.abilities.setdefault(actor_id, {})
        else:
            out.ignored.add(actor_id)
            continue
        for time_seconds, move in samples:
            out.moves += 1
            t_ms = round(time_seconds * 1000)
            # Last one in a bucket wins: the newest record is the one that
            # describes the instant the bucket stands for.
            by_tick[t_ms // period_ms] = Position(
                t_ms=t_ms,
                actor_id=actor_id,
                x=move.position.x,
                y=move.position.y,
                z=move.position.z,
                yaw=move.yaw,
                pitch=move.pitch,
            )
    session.movement.samples.clear()


def _is_moving_ability(session: ReplaySession, actor_id: int) -> bool:
    """Whether this actor is an ability pawn -- a drone or a turret, not a smoke."""
    path = session.channels.archetypes.get(actor_id)
    if not path:
        return False
    ref = abilities.parse(path)
    return ref is not None and ref.moves


def attach(
    replay: Replay,
    path: str | Path,
    options: Options | None = None,
) -> Replay:
    """
    Decode positions, abilities and codenames into `replay`, in place.

    Never raises for want of positions.  An unsupported build, a missing Oodle
    DLL and a JSON dump with no sidecar all end the same way -- `position_source`
    says which, the model keeps every fact it already had, and the viewer says
    on screen that it has no map to draw.

    Three sources, tried in order, and only the last one costs four minutes:

      1. a sidecar **beside the file**, which is what `vrf-to-json --positions`
         writes and a user may have copied here deliberately;
      2. the machine's own cache (`vrfview.positioncache`), written by a
         previous decode of this same capture;
      3. a real decode -- after which the result is cached, so this is the last
         time this capture costs anything.

    A JSON dump never reaches step 3: it carries no replication stream, so for
    it the sidecar is not an optimisation but the only source there is.
    """
    options = options or Options()
    is_vrf = Path(path).suffix.lower() == ".vrf"
    # Why each source that had a file declined it.  Carried rather than
    # written straight onto the replay because a later source overwrites
    # `position_source`, and "the sidecar is for another match" is the one
    # sentence a user actually needs when nothing else works either.
    refused: list[str] = []

    beside = positionfile.sidecar_path(path)
    if beside.is_file() and _apply_sidecar(replay, beside, refused=refused):
        return replay
    if not is_vrf:
        # A dump has no other source: it carries no replication stream.
        replay.position_source = _no_positions(refused) or NO_SOURCE_JSON
        return replay

    if options.cache:
        cached = positioncache.cache_path(path)
        if cached.is_file() and _apply_sidecar(
            replay,
            cached,
            cached=True,
            refused=refused,
        ):
            return replay

    if not options.decode:
        replay.position_source = _no_positions(refused) or NOT_DECODED
        return replay

    actor_ids = {p.actor_id for p in replay.players}
    try:
        found = extract(path, actor_ids, options)
    except (UnsupportedBuildError, VrfError, OSError) as exc:
        replay.position_source = _no_positions([*refused, str(exc)])
        return replay

    replay.positions = found.positions
    replay.position_source = found.described
    replay.ability_tracks = found.ability_positions
    _name_pawns(replay, found.codenames)
    _name_casts(replay, found.spawns)
    if options.cache:
        positioncache.write(path, sidecar_for(replay, found))
    return replay


def attach_stored(replay: Replay, path: str | Path) -> Replay:
    """
    Attach positions **only** if they are already on disk.  Never decodes.

    This is what makes a prepared capture open instantly instead of opening on
    a button.  It is safe to call on the Tk thread during navigation precisely
    because it cannot become a four-minute decode: the worst case is reading a
    10 MB JSON file, and the ordinary case is that there is nothing to read.
    """
    return attach(replay, path, Options(decode=False))


def sidecar_for(replay: Replay, found: Extraction) -> positionfile.Sidecar:
    """One decode in the shape the sidecar stores it."""
    return positionfile.Sidecar(
        positions=found.positions,
        codenames=found.codenames,
        description=found.described,
        match_id=replay.match_id,
        build=found.build,
        hz=found.hz,
        ability_spawns={s.actor_id: (s.path, s.t_ms) for s in found.spawns},
        ability_tracks=found.ability_positions,
    )


def _no_positions(reasons: list[str]) -> str:
    """Every reason there are no positions, in the order they were met."""
    return f"no positions: {'; '.join(r for r in reasons if r)}" if reasons else ""


def _apply_sidecar(
    replay: Replay,
    side: Path,
    *,
    cached: bool = False,
    refused: list[str],
) -> bool:
    """
    Put one stored decode onto `replay`, or say why it was refused.

    Returns whether the replay now has positions, so the caller can fall
    through to the next source.  A refusal is appended to `refused` rather
    than written onto the replay: a stored decode that silently became a fresh
    one would hide a corrupt cache for as long as the cache existed, but the
    fresh decode is also entitled to set the final message if it works.
    """
    try:
        stored = positionfile.read(side)
    except positionfile.PositionFileError as exc:
        refused.append(str(exc))
        return False
    # A sidecar is a loose file that can be copied next to the wrong dump, and
    # a track drawn for another match would look entirely plausible.  Both
    # sides know the match ID, so refuse rather than draw it.
    if stored.match_id and replay.match_id and stored.match_id != replay.match_id:
        refused.append(
            f"{side.name} holds match {stored.match_id}, not {replay.match_id}",
        )
        return False

    where = "cache" if cached else side.name
    replay.positions = stored.positions
    replay.ability_tracks = stored.ability_tracks
    replay.position_source = f"{stored.description} (read from {where}, not decoded)"
    _name_pawns(replay, stored.codenames)
    # Regrouped rather than read back grouped: the sidecar keeps the spawns,
    # so this replay's own rounds and the current grouping rules both apply,
    # however old the stored decode is.
    _name_casts(
        replay,
        abilities.spawns_from(
            {a: path for a, (path, _t) in stored.ability_spawns.items()},
            {a: t / 1000 for a, (_p, t) in stored.ability_spawns.items()},
        ),
    )
    return True


def _name_casts(replay: Replay, spawns: list) -> None:
    """
    Group ability spawns into casts, in place, using this replay's own rounds.

    Grouping happens here rather than in `extract` because a cast belongs to a
    round, and `extract` decodes a stream and knows nothing about rounds.  The
    agent name is left empty on purpose: it is a catalogue lookup, and
    `vrfview.names` is the one place those are made.
    """
    replay.ability_casts = abilities.casts(spawns, round_of=_round_number(replay))


def _round_number(replay: Replay):
    """`Replay.round_at` as the millisecond -> number callable `casts` wants."""

    def number(t_ms: int) -> int:
        rnd = replay.round_at(t_ms)
        return rnd.number if rnd is not None else 0

    return number


def _name_pawns(replay: Replay, codenames: dict[int, str]) -> None:
    """Fill in each player's codename, in place, keeping any it already had."""
    replay.players = [
        Player(
            actor_id=p.actor_id,
            team=p.team,
            label=p.label,
            merged_from=p.merged_from,
            codename=codenames.get(p.actor_id, p.codename),
            agent=p.agent,
        )
        for p in replay.players
    ]


def save(
    path: str | Path,
    replay: Replay,
    found: Extraction,
) -> Path:
    """Write `found` as the sidecar belonging to a dump at `path`."""
    return positionfile.write(
        positionfile.sidecar_path(path),
        sidecar_for(replay, found),
    )
