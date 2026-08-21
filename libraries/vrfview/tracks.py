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
the replay untouched, because a schematic view of a match is still a view.

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
from vrfview import positionfile
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


@dataclass
class Extraction:
    """Decoded tracks and codenames, with enough counts to describe itself."""

    positions: dict[int, Track] = field(default_factory=dict)
    codenames: dict[int, str] = field(default_factory=dict)
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
        return (
            f"{self.build}: {self.samples:,} positions for "
            f"{len(self.positions)} player actors at {self.hz} Hz, thinned from "
            f"{self.moves:,} movement records over {self.blocks} REPLAYDATA "
            f"blocks ({len(self.ignored)} non-player actors ignored)"
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
    # all 3.09 million of them at once.
    buckets: dict[int, dict[int, Position]] = {}

    todo = list(vrf.data_blocks(kinds=(REPLAYDATA,)))
    if options.blocks is not None:
        todo = todo[: options.blocks]
    for i, block in enumerate(todo):
        raw = oodle.decompress(block.blob(vrf.data), block.decompressed_size)
        session.feed_block(raw)
        _drain(session, buckets, actor_ids, period_ms, out)
        if options.progress is not None:
            options.progress(i + 1, len(todo))
    out.blocks = len(todo)

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

    out.positions = {
        actor_id: Track(
            actor_id=actor_id,
            samples=tuple(by_tick[t] for t in sorted(by_tick)),
        )
        for actor_id, by_tick in sorted(buckets.items())
    }
    return out


def _drain(
    session: ReplaySession,
    buckets: dict[int, dict[int, Position]],
    actor_ids: set[int],
    period_ms: int,
    out: Extraction,
) -> None:
    """Move one block of samples into the buckets, thinning as they go."""
    for actor_id, samples in session.movement.samples.items():
        if actor_id not in actor_ids:
            out.ignored.add(actor_id)
            continue
        by_tick = buckets.setdefault(actor_id, {})
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


def attach(
    replay: Replay,
    path: str | Path,
    options: Options | None = None,
) -> Replay:
    """
    Decode positions and codenames into `replay`, in place.

    Never raises for want of positions.  An unsupported build, a missing Oodle
    DLL and a JSON dump with no sidecar all end the same way -- `position_source`
    says which, the model keeps every fact it already had, and the viewer falls
    back to the schematic it drew before any of this existed.

    A JSON dump is not decoded: it carries no replication stream.  It is read
    from the sidecar `vrf-to-json --positions` writes beside it, if there is
    one, which is the whole reason that flag exists -- the DLL is needed once,
    on the machine that dumped, and never again.
    """
    if Path(path).suffix.lower() != ".vrf":
        return _from_sidecar(replay, path)

    actor_ids = {p.actor_id for p in replay.players}
    try:
        found = extract(path, actor_ids, options)
    except (UnsupportedBuildError, VrfError, OSError) as exc:
        replay.position_source = f"no positions: {exc}"
        return replay

    replay.positions = found.positions
    replay.position_source = found.described
    _name_pawns(replay, found.codenames)
    return replay


def _from_sidecar(replay: Replay, path: str | Path) -> Replay:
    """Read positions written earlier, or say why there are none."""
    side = positionfile.sidecar_path(path)
    if not side.is_file():
        replay.position_source = NO_SOURCE_JSON
        return replay
    try:
        stored = positionfile.read(side)
    except positionfile.PositionFileError as exc:
        replay.position_source = f"no positions: {exc}"
        return replay
    # A sidecar is a loose file that can be copied next to the wrong dump, and
    # a track drawn for another match would look entirely plausible.  Both
    # sides know the match ID, so refuse rather than draw it.
    if stored.match_id and replay.match_id and stored.match_id != replay.match_id:
        replay.position_source = (
            f"no positions: {side.name} holds match {stored.match_id}, "
            f"not {replay.match_id}"
        )
        return replay

    replay.positions = stored.positions
    replay.position_source = (
        f"{stored.description} (read from {side.name}, not decoded)"
    )
    _name_pawns(replay, stored.codenames)
    return replay


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
        positionfile.Sidecar(
            positions=found.positions,
            codenames=found.codenames,
            description=found.described,
            match_id=replay.match_id,
            build=found.build,
            hz=found.hz,
        ),
    )
