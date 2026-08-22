"""
Positions, and the one bridge from the replication stream into the model.

Everything else the viewer shows comes out of a plain chunk.  This does not:
it decompresses every REPLAYDATA block, de-obfuscates each property payload and
decodes the movement RPC inside.  That work now happens in `csharp/VrfPositions`
rather than in Python, because the same decode is about four seconds there and
about four minutes here -- see `vrfview.csharpdecode` for why, and for what did
*not* change.  It still needs a built decoder, so it is still never done
implicitly: `loader.load` returns a positionless Replay and a caller asks.

Why a separate module
---------------------
`loader` reads the container, `infer` derives, `names` looks up.  This is a
fourth kind of act: it decodes a second, deeper stream out of the same file.
Keeping it apart means `model`, `infer` and `state` import no decoder at all,
and a replay whose build has no transform loses positions and
nothing else -- `attach` records the refusal in `Replay.position_source` and
returns the replay untouched, for the viewer to say so on screen.

What makes these positions trustworthy
--------------------------------------
Three checks against a full 12.10 capture (2,438s, 27 blocks, 3,069,141 moves
over 154 actors), none of which a decoding bug could pass by luck.  The first
two were established against the Python decoder and re-run against this one:

  * at every one of the 190 characterDeath events the killer and the victim
    are within 4,440 Unreal units of each other, most within 2,000 -- that is
    weapon range, and it holds for all 190, so both the coordinates and the
    actor-to-track join are right;
  * a movement sample exists at the exact millisecond of every one of those
    events, which is what says the demo frame clock and the event clock are
    the same clock and no offset is needed;
  * and this decode was checked once against a second one, written in a
    different language from a different source, which agreed on all 10,544
    samples of the stored 12.10 decode to the last bit of x, y, z, yaw and
    pitch.  That second decoder was `vrfnet`, and it has been removed: it was
    2,400 lines maintained to re-run a check that had already passed, and
    what remains of the package is the build table below.

Two more were added when the pitch and the spawn transform were first read
rather than carried: at 2,949 kills across the whole library the killer's
pitch agrees with the true angle to the victim to a median of 0.91 degrees,
and every one of 210 player pawns spawns within 100 uu of its own first
movement sample.  Both live in tests/test_positions.py, and unlike the
cross-check they still run.

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
from dataclasses import dataclass, field, replace
from pathlib import Path

from vrf_reader import REPLAYDATA, VrfError, VrfFile
from vrfnet.payload_transform import UnsupportedBuildError, transform_for
from vrfview import abilities, csharpdecode, positioncache, positionfile
from vrfview.model import POSITION_HZ, Replay, SpikeEvent, Track

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


SPIKE_ARCHETYPE = "/Game/GameModes/Bomb/TimedBomb"

# How far a TimedBomb spawn may sit from its spikePlanted event and still be
# that plant.  The decoder's clock runs 8..15 ms ahead of the event stream's
# across the whole library -- a constant time-base offset, not jitter -- so
# this is generous by two orders of magnitude and exists only so that a
# capture whose clocks genuinely disagree pairs nothing rather than pairing
# the wrong round.
PLANT_PAIR_MS = 250


def _plants_from(
    archetypes: dict[int, str],
    first_seen: dict[int, float],
    spawn_locations: dict[int, tuple[float, float, float]],
) -> list[tuple[int, float, float, float]]:
    """
    Where each spike was planted, from the actor the plant spawns.

    A `spikePlanted` event carries no arguments at all, so for a long time this
    coordinate was assumed not to exist.  It does: planting spawns a
    `/Game/GameModes/Bomb/TimedBomb` actor, and `csharpdecode` has carried
    every actor's spawn transform since it was written -- `spawns_from` simply
    kept the ones under `/Game/Characters/` and dropped the rest.

    What settled that these are the plant rather than plausible noise is the
    same kind of check the ability spawns had to pass, using only data already
    in hand.  Over the 21 playable captures in the reference library:

      * 274 plant events and 274 TimedBomb spawns, pairing one-to-one with
        none left over, and the two counts equal in **every** capture;
      * a constant +8..15 ms offset, median 8 -- the decoder's own time base,
        the same offset the first actors of the match are seen at;
      * the coordinate a median 69.5 uu from some player's own decoded
        position at that instant (94.5% within 100 uu), which is what "planted
        at the planter's feet" looks like through a 10 Hz thinning; and
      * **274 of 274 inside the radar image's playable silhouette**, where a
        random coordinate lands inside about a third of the time.

    `tests/test_positions.py` is the standing check.  Only the plant is read.
    `Bomb_Defuser` actors carry transforms too and nothing has measured them,
    so nothing here looks at them -- an unmeasured coordinate drawn on a map is
    indistinguishable from a decoded one, which is the whole reason this
    function has a docstring this long.
    """
    plants: list[tuple[int, float, float, float]] = []
    for actor_guid, archetype in archetypes.items():
        if not archetype.startswith(SPIKE_ARCHETYPE):
            continue
        location = spawn_locations.get(actor_guid)
        seen = first_seen.get(actor_guid)
        if location is None or seen is None:
            continue
        plants.append((round(seen * 1000.0), location[0], location[1], location[2]))
    plants.sort()
    return plants


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
    The knobs on a decode: which decoder to run, how finely, and what may answer.

    Bundled rather than passed loose because every one of them is optional and
    a caller normally sets none: `attach(replay, path)` decodes the whole file
    at the default rate, which is what the viewer wants.

    There is no `blocks` knob any more.  It existed to make a four-minute
    decode testable in twelve seconds; a whole match now takes about four, and
    the decoder reads the stream in one pass rather than block by block, so a
    partial decode is neither cheap to ask for nor useful to have.
    """

    parser_exe: str | None = None
    hz: int = POSITION_HZ
    progress: Callable[[int, int], None] | None = None
    # Whether a stored decode may answer instead of a fresh one.  On by
    # default because re-deriving identical arithmetic is never what a caller
    # wanted; off for the tests that have to prove the decoder still works.
    cache: bool = True
    # Whether a fresh decode is allowed at all.  Off is how a caller asks the
    # cheap question -- "is this one already done?" -- without spawning a
    # decoder to find out the answer is no.  See `attach_stored`.
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
    # Where each spike was planted: (t_ms, x, y, z), one per `TimedBomb` spawn.
    # See SPIKE_ARCHETYPE and _plants_from for why these are the plant and not
    # merely an actor that happens to spawn nearby.
    plants: list[tuple[int, float, float, float]] = field(default_factory=list)
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
            located = sum(1 for s in self.spawns if s.location is not None)
            extra = (
                f"; {len(self.spawns)} ability actors, "
                f"{len(self.ability_positions)} of them with a track and "
                f"{located} with a spawn coordinate"
            )
        if self.plants:
            extra += f"; {len(self.plants)} spike plants located"
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
    # decoder, no decompression and no wait.  The decoder supports exactly the
    # branches this table names, which is why the table is still the authority.
    transform_for(vrf.demo.build)

    if options.progress is not None:
        options.progress(0, 1)
    decoded = csharpdecode.run(
        path,
        hz=options.hz,
        explicit=options.parser_exe,
    )
    if options.progress is not None:
        options.progress(1, 1)

    out.moves = decoded.moves
    # Counted off the plain chunk table rather than reported by the decoder:
    # the number belongs in the provenance line and costs nothing to read here.
    out.blocks = sum(1 for _ in vrf.data_blocks(kinds=(REPLAYDATA,)))

    out.spawns = abilities.spawns_from(
        decoded.archetypes,
        decoded.first_seen,
        decoded.spawn_locations,
    )
    out.plants = _plants_from(
        decoded.archetypes,
        decoded.first_seen,
        decoded.spawn_locations,
    )
    _sort(decoded, actor_ids=actor_ids, out=out)

    # decoded.archetypes carries every actor that ever opened a channel, not
    # only the ones still open at the end -- which is exactly the player a
    # reconnect merge most needs a codename for.
    for actor_guid, archetype in decoded.archetypes.items():
        codename = codename_for(archetype)
        if not codename:
            continue
        out.pawns_seen += 1
        if actor_guid in actor_ids:
            out.codenames[actor_guid] = codename

    return out


def _sort(
    decoded: csharpdecode.Decoded,
    *,
    actor_ids: set[int],
    out: Extraction,
) -> None:
    """
    Send each decoded actor to players, to abilities, or to the floor.

    The same three destinations, and the same order, the block-at-a-time drain
    used before: `actor_ids` is the event stream's own set of players and still
    outranks everything, so a pawn the events name is a player even if its
    archetype reads oddly.  Only what is left is offered to the ability parser,
    and only the kinds that actually move are kept -- a `Projectile_` never
    emits a movement record, so a track for one would promise an arc that is
    not in the file.

    The thinning itself already happened, in the decoder, by the identical rule
    (bucket by `t_ms // period`, last record in a bucket wins).
    """
    players: dict[int, Track] = {}
    ability: dict[int, Track] = {}
    for actor_id, samples in sorted(decoded.samples.items()):
        if actor_id in actor_ids:
            target = players
        elif _is_moving_ability(decoded.archetypes, actor_id):
            target = ability
        else:
            out.ignored.add(actor_id)
            continue
        target[actor_id] = Track(actor_id=actor_id, samples=tuple(samples))
    out.positions = players
    out.ability_positions = ability


def _is_moving_ability(archetypes: dict[int, str], actor_id: int) -> bool:
    """Whether this actor is an ability pawn -- a drone or a turret, not a smoke."""
    path = archetypes.get(actor_id)
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

    Never raises for want of positions.  An unsupported build, a decoder that
    was never built and a JSON dump with no sidecar all end the same way --
    `position_source` says which, the model keeps every fact it already had,
    and the viewer says on screen that it has no map to draw.

    Three sources, tried in order, and only the last one runs a decoder:

      1. a sidecar **beside the file**, which is what `vrf-to-json --positions`
         writes and a user may have copied here deliberately;
      2. the machine's own cache (`vrfview.positioncache`), written by a
         previous decode of this same capture;
      3. a real decode -- after which the result is cached, so this is the last
         time this capture costs anything.  The cache mattered more when this
         step took four minutes; it still earns its keep, because reading 700
         KB of JSON beats spawning a process and re-deriving 3 million moves.

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
        cached = positioncache.entry(path)
        if cached is not None and _apply_sidecar(
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
    except (
        UnsupportedBuildError,
        csharpdecode.DecodeError,
        VrfError,
        OSError,
    ) as exc:
        replay.position_source = _no_positions([*refused, str(exc)])
        return replay

    replay.positions = found.positions
    replay.position_source = found.described
    replay.ability_tracks = found.ability_positions
    _name_pawns(replay, found.codenames)
    _name_casts(replay, found.spawns)
    _place_spike(replay, found.plants)
    if options.cache:
        positioncache.write(path, sidecar_for(replay, found))
    return replay


def attach_stored(replay: Replay, path: str | Path) -> Replay:
    """
    Attach positions **only** if they are already on disk.  Never decodes.

    This is what makes a prepared capture open instantly instead of opening on
    a button.  It is safe to call on the Tk thread during navigation precisely
    because it cannot become a decode at all: the worst case is reading a
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
        ability_spawns={s.actor_id: (s.path, s.t_ms, s.location) for s in found.spawns},
        ability_tracks=found.ability_positions,
        plants=found.plants,
    )


def sidecar_of(replay: Replay) -> positionfile.Sidecar:
    """
    Whatever positions a replay is already carrying, in the stored shape.

    `sidecar_for` needs an `Extraction`, which exists only in the moments after
    a decode.  A replay that came back from the cache has its tracks and
    nothing else, so anything that wants to hand those on -- a server serving
    them to a browser, a caller writing a second copy -- needs this instead.

    **This is not a lossless sidecar and must not be written as one.**  A
    sidecar stores raw ability spawns, and `_apply_sidecar` regroups them into
    casts on every load precisely so the grouping rules can improve without
    invalidating a cached decode.  That means the raw spawns are gone by the
    time a `Replay` exists: a cast knows its own actor, slot and codename, but
    not the archetype path it was read from.  So `ability_spawns` is empty
    here, deliberately, and a round trip through this would silently drop the
    ability grouping of every future load.

    Nothing is invented to fill the gap.  What this does carry is what the
    replay genuinely states: the tracks, the codenames its pawns declared, and
    the sentence the decoder wrote about itself.
    """
    return positionfile.Sidecar(
        positions=replay.positions,
        codenames={p.actor_id: p.codename for p in replay.players if p.codename},
        description=replay.position_source,
        match_id=replay.match_id,
        build=replay.build,
        hz=POSITION_HZ,
        # Not reconstructible from a loaded replay; see the docstring.
        ability_spawns={},
        ability_tracks=replay.ability_tracks,
        # The plants *are* reconstructible, and the asymmetry is the point: a
        # cast's archetype path is consumed by the grouping and gone, whereas a
        # plant's coordinate lands on the event itself and stays there.  So
        # this half of a round trip is lossless where the ability half is not.
        plants=_plants_of(replay),
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
            {a: path for a, (path, _t, _xyz) in stored.ability_spawns.items()},
            {a: t / 1000 for a, (_p, t, _xyz) in stored.ability_spawns.items()},
            {
                a: xyz
                for a, (_p, _t, xyz) in stored.ability_spawns.items()
                if xyz is not None
            },
        ),
    )
    # Re-paired rather than read back paired, for the reason the casts are
    # regrouped: which event a coordinate belongs to is a reading, and a v3
    # cache simply has no plants to re-pair.
    _place_spike(replay, stored.plants)
    return True


def _place_spike(replay: Replay, plants: list[tuple[int, float, float, float]]) -> None:
    """
    Give each plant event the coordinate the plant actor spawned at, in place.

    Paired by time and nothing else, because there is nothing else to pair on:
    a `spikePlanted` event carries no arguments.  The pairing is safe anyway --
    a round holds at most one plant, and the two clocks differ by a constant
    8..15 ms across the whole library, so `PLANT_PAIR_MS` is three orders of
    magnitude clear of a round boundary.  A plant with no spawn within that
    window keeps `location=None` and is drawn nowhere; it never falls back to
    the nearest one it can find.

    `replace`, not a fresh `SpikeEvent` listing every field, for the reason
    `_name_pawns` gives: rebuilding a frozen record by hand silently drops any
    field added to it since.
    """
    if not plants or not replay.spike:
        return
    unused = sorted(plants)
    placed: list[SpikeEvent] = []
    for event in replay.spike:
        if event.kind != "planted" or not unused:
            placed.append(event)
            continue
        best = min(unused, key=lambda plant: abs(plant[0] - event.t_ms))
        if abs(best[0] - event.t_ms) > PLANT_PAIR_MS:
            placed.append(event)
            continue
        # Consumed, so two plants in one capture can never share a coordinate.
        unused.remove(best)
        placed.append(replace(event, location=(best[1], best[2], best[3])))
    replay.spike = placed


def _plants_of(replay: Replay) -> list[tuple[int, float, float, float]]:
    """The plant coordinates a replay is already carrying, in the stored shape."""
    return [
        (event.t_ms, *event.location)
        for event in replay.spike
        if event.location is not None
    ]


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
    """
    Fill in each player's codename, in place, keeping any it already had.

    `replace`, not a fresh `Player` listing every field: this fills in one
    field, and rebuilding a frozen record by hand silently drops any field
    added to it since.  `names.resolve` did exactly that to an ability cast's
    coordinates, which were decoded, stored and read back correctly and then
    lost on the way past.
    """
    replay.players = [
        replace(p, codename=codenames.get(p.actor_id, p.codename))
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
