"""
Ability casts, read out of the archetype paths of the actors a cast spawns.

There is no ability event in a `.vrf`.  `docs/039f3991_summary.md` section 6
lists all seven event groups a full competitive match emits, and the only one
that touches an ability is `characterUltimateUsed` -- one actor id, no target,
no location, not even which ultimate.  Everything below therefore comes from
somewhere else: the replication stream opens an actor channel for each thing an
ability spawns, and that channel names its archetype.

    /Game/Characters/Killjoy/S0/Ability_E/Pawn_Killjoy_E_Turret.Default__..._C
                     ^codename        ^slot ^kind    ^name

So a cast is not *reported* by the file; it is *inferred from the actors it
creates*, and this module is the parser for those paths and nothing else.  It
imports no decoder for the same reason `model` and `state` do
not: path parsing is plain string work and has to stay testable headlessly.
`vrfview.tracks` is the only thing that feeds it, exactly as it is the only
bridge from the replication stream into the model.

Four things that measurement decided, not guesswork
---------------------------------------------------
All four come from decoding three REPLAYDATA blocks of a real 12.10 capture and
listing every archetype seen; the strings in the tests are that census verbatim.

* **`Ability_4` is the C slot.**  Riot numbers it rather than lettering it, so
  the folder is `Ability_4` where the keybind is C.  Q, E and X are themselves.

* **The leaf's token order is not fixed.**  `Ability_Killjoy_E_Turret` and
  `Ability_Q_Smonk_DebuffKnife` both occur, agent and slot swapped.  So the name
  is what remains after removing the kind, the codename and the slot *wherever
  they sit*, rather than what sits at a fixed index.

* **The slot is not always in the leaf.**  `GameObject_Smonk_NewSmoke` carries
  neither slot nor kind hint, and is only an E because of the `Ability_E`
  folder above it.  The folder is the primary source and the leaf the fallback,
  which is what lets `Ability_Wushu_Passive_Glide` -- under `Glide/`, with no
  `Ability_*` folder at all -- still resolve as a passive.

* **One cast spawns several actors, and the `Ability_` one is not the best
  witness.**  Jett's smoke is an `Ability_`, a `Projectile_` and a
  `GameObject_` together.  Killjoy's turret is stranger: measured over a full
  19-round match, every round spawns one `Pawn_Killjoy_E_Turret` and one
  `Ability_Killjoy_E_TurretAttack`, while `Ability_Killjoy_E_Turret` itself
  appears in only two of them -- the rounds a checkpoint re-exported it.  So
  the ability actor is *not* reliably created per use, and naming a cast after
  it reports "Turret Attack" for seventeen rounds out of nineteen.  `casts`
  therefore prefers the pawn, which is the thing the ability actually put in
  the world.

* **Not every spawn is a use.**  Twice in a 19-round capture -- at the opening
  frame and again mid-match -- *thirty-three* ability actors appear on the
  same millisecond, four slots for each of five agents.  Nobody pressed
  thirty-three keys at once: that is the engine replicating the whole world,
  once when the recording starts and again when a checkpoint reseeds it.  Away
  from those two instants the busiest millisecond in the match carries two
  spawns, and both belong to the same agent (Clove dying sets off her own
  post-death pair).  `snapshot_instants` finds them by that signature and
  `casts` drops them -- see there for the cost.

Where a cast is, and where it is not
------------------------------------
Only the `Pawn_` ones ever emit a movement record, because the RPC that
carries positions is `ReceiveRemoteCharacterUpdates` and a thrown projectile
is not a character.  So there is still **no arc**: a projectile has a start
and an end and nothing in between, and nothing here may draw a curve.

What there is now is a start.  The old Python decoder never read the
spawn transform -- it was searched for across 2,700 offset and scale
combinations and not found -- but `csharp/VrfPositions` does, off the channel's
own `ActorSpawned`, and the measurement says those coordinates are real:

  * across the 21 playable captures every one of 210 player pawns has a spawn
    location within 100 uu of its own first movement sample, a median of 0.0
    and a maximum of 91.7 -- and a player's first decoded position is ground
    truth for where they spawned;
  * every one of 18,946 ability actors has one;
  * and 98% to 100% of each kind lands inside the radar image's own playable
    silhouette, where a coordinate drawn at random would land inside about a
    third of the time.  The exception is `Actor_`, 13 instances across the
    library, which land tens of thousands of units off the map -- so an
    unrecognised kind is still not to be trusted, and `AbilityCast.landed`
    refuses one rather than ranking it last.

A smoke therefore has a time, an identity **and a coordinate**.  What no
consumer may supply is the path it took to get there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import pairwise

CHARACTERS_ROOT = ("Game", "Characters")

# `/Game/Characters/<Codename>/<leaf>` -- the shortest path that can name an
# ability.  Anything shorter has no agent folder to read a codename out of.
MIN_PARTS = 5

# The folder that names the slot, and the raw token inside it.
_SLOT_FOLDER = re.compile(r"^Ability_(Q|E|X|4)$")

# Riot's own slot tokens, mapped to the key the player actually presses.  The
# `4` is the whole reason this table exists rather than being the identity.
SLOT_KEYS = {"Q": "Q", "E": "E", "X": "X", "4": "C", "Passive": "Passive"}

PASSIVE = "Passive"
ULTIMATE = "X"
GRENADE = "C"

# The leaf's first token.  `Ability` is the cast itself; the rest are what the
# cast produced.  An unknown prefix is kept verbatim rather than rejected -- a
# new agent should cost an unfamiliar word in one column, not a missing cast.
KIND_ABILITY = "Ability"
KIND_PAWN = "Pawn"
KIND_PROJECTILE = "Projectile"
KIND_GAMEOBJECT = "GameObject"
KIND_EQUIPPABLE = "Equippable"

# Two more things-left-standing, and they are not synonyms of `GameObject_`
# that somebody forgot to normalise -- they are what Riot names them, and they
# are measured to behave the same way.  `Zone_` is Omen's smoke; `Patch_` is
# Gekko's.  See PLACING_KINDS for the numbers.
KIND_ZONE = "Zone"
KIND_PATCH = "Patch"

KIND_ACTOR = "Actor"

# Only these ever move; see the module docstring.
MOVING_KINDS = (KIND_PAWN,)

# Kinds a cast *creates*.  `Equippable_` is excluded because it is loadout,
# not a use.
#
# The placed kinds used to be excluded too, and that was a real guard aimed at
# a real thing -- a smoke still standing when the round rolled over reopens
# with no `Ability_` beside it, and reporting that would put a decision in a
# round nobody made it in.  It was aimed with the wrong instrument.  Excluding
# the *kind* also throws away every ability whose only witness is the thing it
# left behind, which measured over the reference library is 2,223 groups:
# Brimstone's sky smokes (37 of 37 groups), Chamber's traps and headhunter
# (1,073), Cypher's cages, Reyna's dismiss, Breach's fault line.  Brimstone's C
# slot spawns 142 `GameObject_` against 4 `Ability_` library-wide, so his
# smokes simply did not exist.
#
# What separates a leftover from a use is *when*, not what -- see
# ROUND_OPENING_MS, which is where that guard now lives and which also catches
# the 140 re-replicated groups this list was letting through.
CAST_KINDS = (
    KIND_ABILITY,
    KIND_PAWN,
    KIND_PROJECTILE,
    KIND_GAMEOBJECT,
    KIND_ZONE,
    KIND_PATCH,
)

# How far into a round a group has to open before it is a decision somebody
# made rather than the world being handed over again.
#
# At a round boundary the engine reopens whatever is still standing under fresh
# actor ids, and those land within a few milliseconds of the round's own start.
# Measured over the 21 playable captures, as the offset from the round start to
# a group's earliest spawn: **495 groups land in the first 100 ms, then nothing
# at all until 4 seconds** -- the 100-250, 250-500 and 1,000-4,000 ms bands are
# each completely empty, and 500-1,000 holds seven.  So this is a gap between
# two populations rather than a number anybody chose, and it sits in the empty
# band immediately above the spike.
#
# It cannot cost a real cast, because a round opens on a barrier nobody can
# cast through.
ROUND_OPENING_MS = 250

# Which spawn gets to name the cast, best first.  The pawn wins because it is
# the object the ability left in the world and its name is the ability's own;
# the ability actor is second because it is sometimes a sub-actor
# (`..._TurretAttack`) rather than the ability itself.  `Zone_` and `Patch_`
# sit beside `GameObject_` at the back for the same reason it does.
NAMING_KINDS = (
    KIND_PAWN,
    KIND_ABILITY,
    KIND_PROJECTILE,
    KIND_GAMEOBJECT,
    KIND_ZONE,
    KIND_PATCH,
)

# Which spawn gets to say *where* the cast ended up, best first -- and note
# that this is very nearly the reverse of NAMING_KINDS, because the two
# questions have different best witnesses.
#
# Measured over the 21 playable captures as the distance from the placement to
# the caster's own decoded position at that instant, which is the same way the
# first version of this list was settled:
#
#     Pawn                    -- a track, which always outranks a spawn point
#     GameObject   n=2341     median 2,005 uu    98.3% inside the silhouette
#     Zone         n= 288     median 3,533 uu   100.0%
#     Patch        n= 259     median 2,017 uu    99.1%
#     Ability      n= 897     median   259 uu    99.7%
#     Projectile   n=3491     median    42 uu    99.5%
#
# The split is not subtle.  The first four are the thing left standing, out
# where it came to rest; the last two are where the caster was standing when
# they made the decision, and they are here only so the rule reads completely.
# `Projectile_` is a *throw origin* -- 42 uu is inside the caster's own capsule
# -- so ranking it above the placed kinds is what put Omen's smoke a median
# 3,061 uu from the smoke and on top of Omen instead, for every one of 241
# casts.  A kind this list does not name is refused, which is why `Zone_` and
# `Patch_` had to be added rather than left to fall through.
PLACING_KINDS = (
    KIND_PAWN,
    KIND_GAMEOBJECT,
    KIND_ZONE,
    KIND_PATCH,
    KIND_PROJECTILE,
    KIND_ABILITY,
)

NO_POSITION = "no position on wire"

# How many *distinct agents* have to spawn an ability on one exact millisecond
# before that instant is read as the engine re-replicating the world rather
# than as people using abilities.  Two is deliberately allowed: a coordinated
# execute is real, and so is one agent's own ability setting off another.
# Three separate agents on the same millisecond is not a coincidence, it is a
# snapshot -- measured, the real ones peak at two and the snapshots carry five.
SNAPSHOT_CODENAMES = 3

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def humanise(name: str) -> str:
    """
    An internal name as words.

    `RemoteBees_MultiDetonate` becomes `Remote Bees Multi Detonate`.
    Only ever applied to a name **read from the file**.  A published ability
    name is Riot's own text and is shown exactly as published; running it
    through this would quietly rewrite `KAY/O` and friends.
    """
    words = []
    for chunk in name.split("_"):
        if chunk:
            words.extend(_CAMEL.split(chunk))
    return " ".join(w for w in words if w) or name


@dataclass(frozen=True)
class AbilityRef:
    """What one archetype path says about the ability that spawned it."""

    codename: str
    slot: str
    kind: str
    name: str

    @property
    def moves(self) -> bool:
        """Whether this kind of actor ever emits a movement record."""
        return self.kind in MOVING_KINDS

    @property
    def display(self) -> str:
        """`RemoteBees_MultiDetonate` as `Remote Bees Multi Detonate`."""
        return humanise(self.name)


@dataclass(frozen=True)
class Placement:
    """One actor a cast put in the world, at the coordinate it appeared at."""

    actor_id: int
    kind: str
    name: str
    x: float
    y: float
    z: float

    @property
    def display(self) -> str:
        return humanise(self.name)


@dataclass(frozen=True)
class AbilitySpawn:
    """One actor an ability created, at the instant its channel opened."""

    t_ms: int
    actor_id: int
    ref: AbilityRef
    # The archetype path this was parsed from, kept so a sidecar can store the
    # fact rather than the reading of it.  See positionfile.Sidecar.
    path: str = ""
    # Where the channel said this actor appeared, if the decoder read a spawn
    # transform for it.  Optional because a v1 or v2 sidecar predates the
    # measurement and simply has none -- see positionfile.
    location: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class AbilityCast:
    """
    One agent using one slot in one round, and every actor it spawned.

    `spawns` is a count rather than a list of separate casts on purpose.  A
    Killjoy turret opens a fresh `Ability_..._TurretAttack` channel every time
    it fires, and a Jett throws three knives off one ultimate; reporting either
    as repeated casts would be counting actors and calling them decisions.  So
    the earliest `Ability_` spawn for a slot in a round is the cast, and
    everything else that slot spawned in that round is counted beside it.
    """

    t_ms: int
    codename: str
    slot: str
    name: str
    round_no: int = 0
    actor_id: int = 0
    spawns: int = 1
    kinds: tuple[str, ...] = ()
    # Actor ids of the `Pawn_` spawns, which are the only ones with a track.
    pawns: tuple[int, ...] = ()
    agent: str = ""
    # Every actor this cast put in the world that will never move, at the
    # coordinate its channel opened at.  Facts, in spawn order; `landed`
    # below is the reading over them.  Empty for a cast decoded before the
    # spawn transform was measured -- a v1 or v2 sidecar carries none.
    placements: tuple[Placement, ...] = ()

    @property
    def identity(self) -> str:
        """The best name this cast has: the agent if looked up, else the code."""
        return self.agent or self.codename

    @property
    def landed(self) -> Placement | None:
        """
        Where this cast ended up, or None if nothing here can say.

        One cast opens several channels at several places -- the `Ability_`
        at the caster's feet, the `Projectile_` in flight, the `GameObject_`
        where the smoke came to rest -- so "the cast's position" is a choice
        between them and `PLACING_KINDS` is where that choice is written down.
        Taking the first spawn instead would mark every smoke at the thrower,
        which is a plausible wrong answer and therefore the expensive kind.

        A cast with a pawn returns None: the pawn has a track, and a track
        says where the thing is *now* rather than where it started.

        A kind `PLACING_KINDS` does not name is refused rather than ranked
        last.  `Actor_` is the reason: 13 of them across the library, landing
        tens of thousands of units off the map, and an unrecognised kind is
        exactly the case where there is nothing to fall back on.
        """
        if self.pawns:
            return None
        ranked = sorted(
            (p for p in self.placements if p.kind in PLACING_KINDS),
            key=lambda p: PLACING_KINDS.index(p.kind),
        )
        return ranked[0] if ranked else None

    @property
    def display_name(self) -> str:
        """The internal name as words, for the slots the catalogue cannot join."""
        return humanise(self.name)

    @property
    def has_track(self) -> bool:
        return bool(self.pawns)


def parse(archetype_path: str) -> AbilityRef | None:
    """
    One archetype path as an ability reference, or None if it is not one.

    Rejects anything outside `/Game/Characters/`, which is what drops the
    weapons, the pickups, the armour and `/Game/Equippables/Melee/
    Ability_Melee_Base` -- that last one is called Ability and is not one, it
    is the knife every player spawns holding.
    """
    parts = archetype_path.split("/")
    if len(parts) < MIN_PARTS or tuple(parts[1:3]) != CHARACTERS_ROOT:
        return None
    codename = parts[3]
    if not codename:
        return None

    leaf = parts[-1].split(".", 1)[0]
    tokens = [t for t in leaf.split("_") if t]
    if not tokens:
        return None
    kind = tokens[0]

    raw_slot = _slot_from(parts, tokens)
    if raw_slot is None:
        return None

    # Whatever is left once the three things we already know are removed.  Only
    # the first occurrence of each is dropped, so an ability genuinely called
    # `Smonk` or `X` keeps its name.
    rest = list(tokens[1:])
    for token in (codename, raw_slot):
        if token in rest:
            rest.remove(token)
    name = "_".join(rest) or leaf

    return AbilityRef(
        codename=codename,
        slot=SLOT_KEYS[raw_slot],
        kind=kind,
        name=name,
    )


def _slot_from(parts: list[str], tokens: list[str]) -> str | None:
    """The `Ability_*` folder's slot, else a slot token in the leaf."""
    for part in parts:
        found = _SLOT_FOLDER.match(part)
        if found:
            return found.group(1)
    for token in tokens[1:]:
        if token in SLOT_KEYS:
            return token
    return None


def spawns_from(
    archetypes: dict[int, str],
    first_seen: dict[int, float],
    locations: dict[int, tuple[float, float, float]] | None = None,
) -> list[AbilitySpawn]:
    """
    Every ability actor in a decoded session, in the order it appeared.

    `archetypes` and `first_seen` are the decoder's two
    history tables, both keyed by actor net GUID and both deliberately
    surviving a checkpoint reset.  An actor with no recorded time is skipped
    rather than placed at zero: a cast at the wrong instant is worse than one
    that is missing, because the timeline would show it in the wrong round.

    `locations` is optional and stays optional: a sidecar written before the
    spawn transform was measured has none, and a cast with no coordinate is
    the state this whole module lived in until then.
    """
    locations = locations or {}
    out = []
    for actor_id, path in archetypes.items():
        ref = parse(path)
        if ref is None:
            continue
        seen = first_seen.get(actor_id)
        if seen is None:
            continue
        out.append(
            AbilitySpawn(
                t_ms=round(seen * 1000),
                actor_id=actor_id,
                ref=ref,
                path=path,
                location=locations.get(actor_id),
            ),
        )
    out.sort(key=lambda s: (s.t_ms, s.actor_id))
    return out


def casts(
    spawns: list[AbilitySpawn],
    round_of=None,
    codenames: dict[str, str] | None = None,
    opened_at=None,
) -> list[AbilityCast]:
    """
    Group spawns into one cast per agent, slot and round.

    `round_of` is a callable taking milliseconds and returning a round number
    (`Replay.round_at` wrapped by the caller); without one everything lands in
    round 0, which is what a replay with no rounds deserves.  `codenames` maps
    a codename to a public agent name where one resolved.  `opened_at` takes
    milliseconds and returns the start of the round containing them, and is
    what the leftover guard below needs; without one that guard is skipped and
    a round boundary will hand back a handful of casts nobody made.

    A group is a cast if something in it was *created by the act* --
    `CAST_KINDS` -- **and** it did not open in the first `ROUND_OPENING_MS` of
    its round.  The second half is the leftover guard: a smoke still standing
    when the round ended reopens under a fresh actor id a few milliseconds into
    the next round, and reporting that would put a decision in a round nobody
    made it in.  It used to be done by excluding `GameObject_` from
    `CAST_KINDS`, which threw away every ability whose only witness is what it
    left behind -- see that constant for what that cost.

    The cast's instant is the earliest of those creations, and its name comes
    from whichever spawn `NAMING_KINDS` ranks highest.  Both are answers to the
    same measured problem: the `Ability_` actor is not reliably respawned per
    use, so it is neither the earliest nor the best-named witness.  See the
    module docstring for the counts that settled it.

    World snapshots are dropped whole.  That does cost any real cast that
    happened to land on the same millisecond as a checkpoint -- a handful of
    instants in a match -- and that is the right way round: losing one cast is
    a gap, while keeping the instant would add thirty-three that nobody made.
    """
    codenames = codenames or {}
    snapshots = snapshot_instants(spawns)
    grouped: dict[tuple[str, str, int], list[AbilitySpawn]] = {}
    for spawn in spawns:
        if spawn.t_ms in snapshots:
            continue
        rnd = round_of(spawn.t_ms) if round_of is not None else 0
        grouped.setdefault((spawn.ref.codename, spawn.ref.slot, rnd), []).append(spawn)

    out = []
    for (codename, slot, rnd), group in grouped.items():
        made = [s for s in group if s.ref.kind in CAST_KINDS]
        if not made:
            continue
        first = min(made, key=lambda s: s.t_ms)
        if _is_handover(group, opened_at):
            continue
        namer = _namer(group)
        out.append(
            AbilityCast(
                t_ms=first.t_ms,
                codename=codename,
                slot=slot,
                name=namer.ref.name,
                round_no=rnd,
                actor_id=first.actor_id,
                spawns=len(group),
                kinds=tuple(sorted({s.ref.kind for s in group})),
                pawns=tuple(s.actor_id for s in group if s.ref.moves),
                agent=codenames.get(codename, ""),
                placements=_placements(group),
            ),
        )
    out.sort(key=lambda c: (c.t_ms, c.codename, c.slot))
    return out


def _is_handover(group: list[AbilitySpawn], opened_at) -> bool:
    """
    Whether this group is the world being handed over rather than a decision.

    The group's *earliest* spawn is the one asked about, not its earliest
    `CAST_KINDS` spawn: what reopens at a boundary is everything still standing,
    and the question is when this agent's slot first said anything at all.

    With no `opened_at` there is nothing to compare against and the answer is
    no -- a replay with no rounds has no boundaries to be handed over at.
    """
    if opened_at is None:
        return False
    earliest = min(s.t_ms for s in group)
    start = opened_at(earliest)
    return start is not None and earliest - start < ROUND_OPENING_MS


def _placements(group: list[AbilitySpawn]) -> tuple[Placement, ...]:
    """
    Every spawn in a cast that has a coordinate and will never have a track.

    A `Pawn_` is excluded because it moves: its own samples say where it is at
    each instant, and a spawn point beside them would be a second, staler
    answer to the same question.  Everything else in a cast is created once
    and stays put, so the point its channel opened at is the only position it
    will ever have -- and, since the transform was measured, a real one.
    """
    return tuple(
        Placement(
            actor_id=spawn.actor_id,
            kind=spawn.ref.kind,
            name=spawn.ref.name,
            x=spawn.location[0],
            y=spawn.location[1],
            z=spawn.location[2],
        )
        for spawn in group
        if spawn.location is not None and not spawn.ref.moves
    )


def snapshot_instants(spawns: list[AbilitySpawn]) -> set[int]:
    """
    The milliseconds on which the engine re-replicated the world.

    Found by how many *distinct agents* spawn an ability at once, not by how
    many actors do: one agent can legitimately create several at the same
    instant, and on the reference capture the busiest genuine millisecond
    carries two spawns from one agent while each snapshot carries thirty-three
    across five.  Counting agents is what separates those without needing to
    know when the checkpoints were.
    """
    by_instant: dict[int, set[str]] = {}
    for spawn in spawns:
        by_instant.setdefault(spawn.t_ms, set()).add(spawn.ref.codename)
    return {t for t, agents in by_instant.items() if len(agents) >= SNAPSHOT_CODENAMES}


def _namer(group: list[AbilitySpawn]) -> AbilitySpawn:
    """
    The spawn a cast takes its name from: best kind first, earliest to break ties.

    Within one kind the shortest name wins, because a sub-actor extends its
    ability's name rather than replacing it -- `Turret` and `TurretAttack` are
    the same ability, and the shorter of the two is the one a reader means.
    """
    ranked = sorted(
        group,
        key=lambda s: (
            NAMING_KINDS.index(s.ref.kind)
            if s.ref.kind in NAMING_KINDS
            else len(
                NAMING_KINDS,
            ),
            len(s.ref.name),
            s.t_ms,
        ),
    )
    return ranked[0]


@dataclass(frozen=True)
class Attribution:
    """Which player each codename belongs to, and where that was impossible."""

    by_codename: dict[str, int] = field(default_factory=dict)
    ambiguous: tuple[str, ...] = ()

    @property
    def note(self) -> str:
        if not self.ambiguous:
            return ""
        return (
            f"ability casts for {', '.join(self.ambiguous)} are unattributed: "
            f"more than one player is that agent, and the archetype path names "
            f"the agent rather than the actor"
        )


def attribute(players) -> Attribution:
    """
    Codename -> actor id, for the codenames exactly one player holds.

    An ability actor's path names its *agent*, not its caster, so this is the
    only join available.  In a normal match it is exact, because no two players
    on a team pick the same agent -- but a mode that allows duplicates would
    make it a coin flip, so a shared codename is refused and said out loud
    rather than resolved to whichever player was found first.
    """
    seen: dict[str, list[int]] = {}
    for player in players:
        if player.codename:
            seen.setdefault(player.codename, []).append(player.actor_id)
    return Attribution(
        by_codename={k: v[0] for k, v in seen.items() if len(v) == 1},
        ambiguous=tuple(sorted(k for k, v in seen.items() if len(v) > 1)),
    )


def travel(track) -> float:
    """
    How far an ability pawn actually went, in Unreal units.

    The measured path length of its own samples, not a published range: no
    ability range exists in Riot's content catalogue, in the manifest, or in
    the replay, so the only honest number here is the one the track states.
    A pawn that never moved returns 0.0, which is the true answer for a turret.
    """
    total = 0.0
    samples = getattr(track, "samples", ())
    for before, after in pairwise(samples):
        total += ((after.x - before.x) ** 2 + (after.y - before.y) ** 2) ** 0.5
    return total
