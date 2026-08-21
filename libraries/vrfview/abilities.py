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
imports no tkinter and no vrfnet for the same reason `model` and `state` do
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

What this cannot say
--------------------
Where the ability went.  `vrfnet.actors.read_new_actor` stops after the
archetype GUID, because the spawn transform was searched for across 2,700
offset and scale combinations and is not there; and of every ability archetype
in the census, only the `Pawn_` ones ever emit a movement record, because the
RPC that carries positions is `ReceiveRemoteCharacterUpdates` and a thrown
projectile is not a character.  A smoke therefore has a time and an identity
and **no coordinate**, and no consumer may supply one.
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

KIND_ACTOR = "Actor"

# Only these ever move; see the module docstring.
MOVING_KINDS = (KIND_PAWN,)

# Kinds a cast *creates*.  A `GameObject_` is excluded on purpose: a smoke
# still standing when the round rolled over reopens with no cast beside it,
# and treating that as a fresh use would put a decision in a round nobody made
# it in.  `Equippable_` is excluded because it is loadout, not a use.
CAST_KINDS = (KIND_ABILITY, KIND_PAWN, KIND_PROJECTILE)

# Which spawn gets to name the cast, best first.  The pawn wins because it is
# the object the ability left in the world and its name is the ability's own;
# the ability actor is second because it is sometimes a sub-actor
# (`..._TurretAttack`) rather than the ability itself.
NAMING_KINDS = (KIND_PAWN, KIND_ABILITY, KIND_PROJECTILE, KIND_GAMEOBJECT)

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
class AbilitySpawn:
    """One actor an ability created, at the instant its channel opened."""

    t_ms: int
    actor_id: int
    ref: AbilityRef
    # The archetype path this was parsed from, kept so a sidecar can store the
    # fact rather than the reading of it.  See positionfile.Sidecar.
    path: str = ""


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

    @property
    def identity(self) -> str:
        """The best name this cast has: the agent if looked up, else the code."""
        return self.agent or self.codename

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
) -> list[AbilitySpawn]:
    """
    Every ability actor in a decoded session, in the order it appeared.

    `archetypes` and `first_seen` are `vrfnet.actors.ChannelTable`'s two
    history tables, both keyed by actor net GUID and both deliberately
    surviving a checkpoint reset.  An actor with no recorded time is skipped
    rather than placed at zero: a cast at the wrong instant is worse than one
    that is missing, because the timeline would show it in the wrong round.
    """
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
            ),
        )
    out.sort(key=lambda s: (s.t_ms, s.actor_id))
    return out


def casts(
    spawns: list[AbilitySpawn],
    round_of=None,
    codenames: dict[str, str] | None = None,
) -> list[AbilityCast]:
    """
    Group spawns into one cast per agent, slot and round.

    `round_of` is a callable taking milliseconds and returning a round number
    (`Replay.round_at` wrapped by the caller); without one everything lands in
    round 0, which is what a replay with no rounds deserves.  `codenames` maps
    a codename to a public agent name where one resolved.

    A group is a cast only if something in it was *created by the act* --
    `CAST_KINDS`.  A stray `GameObject_` on its own is a leftover from before
    the window, a smoke still standing when the round ended, and reporting it
    as a fresh cast would put a decision in a round nobody made it in.

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
            ),
        )
    out.sort(key=lambda c: (c.t_ms, c.codename, c.slot))
    return out


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
