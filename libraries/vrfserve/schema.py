"""
The wire contract, as models.

These describe the *wire*, not the replay.  `vrfview.model` is the domain and
these are what a browser receives, and keeping them apart is what lets the
payload carry things the model does not -- an id, an asset URL, a published
ability name -- without any of that leaking back into `Replay`.

They exist mainly to be derived from.  FastAPI turns them into the OpenAPI
document, and `openapi-typescript` turns that into the browser's types, so the
far end's idea of a kill is generated from this file rather than typed out again
by hand.  `wire.py` builds plain dicts; these validate them, and
`tests/test_vrfserve.py` asserts every builder's output does validate, which is
what stops the dicts and the models drifting apart.

Optional fields are `| None` rather than absent.  A client that has to
distinguish "no art for this agent" from "this key was not sent" is a client
that will eventually get it wrong, so the key is always there and null means
the same thing everywhere: looked for, not found, and the interface should show
nothing rather than a placeholder.
"""

from __future__ import annotations

from pydantic import BaseModel


class DemoRootDoc(BaseModel):
    path: str
    exists: bool
    source: str
    described: str


class DecoderDoc(BaseModel):
    """
    Whether positions can be decoded at all, and by what.

    `found` gates the DECODE button. When it is false, `hint` is the sentence
    naming the command that would fix it -- an interface that offers a button
    which cannot work is worse than one that explains why there is none.
    """

    found: bool
    path: str
    described: str
    hint: str


class ConfigDoc(BaseModel):
    """Where the server is looking, and what it found there."""

    demo_root: DemoRootDoc
    decoder: DecoderDoc
    catalog_source: str
    web_built: bool
    web_hint: str


class PrewarmDoc(BaseModel):
    state: str
    note: str
    done: int
    total: int
    label: str


class CardAgentDoc(BaseModel):
    name: str
    icon_url: str | None


class CardTeamDoc(BaseModel):
    agents: list[CardAgentDoc]
    # `None` where nothing has established which of the two halves `infer`
    # called A, which is every capture that has not been decoded.  See
    # `vrfhome.teamorder`.
    rounds_won: int | None


class CardDoc(BaseModel):
    id: str
    file_name: str
    match_id: str
    map_path: str
    map_name: str
    map_key: str
    listview_url: str | None
    # The instant and the length only: how they are written is the browser's,
    # in the reader's own zone.  See wire.card.
    recorded_utc: str | None
    length_ms: int
    rounds: int
    players: int
    size_bytes: int
    error: str
    readable: bool
    playable: bool
    # Why, when `playable` is false.  See wire.card.
    positions_note: str
    prewarm: PrewarmDoc | None
    # The two teams, read off the loadout roster's own order -- `None` where
    # that split was refused or there is no art to draw it with.
    teams: list[CardTeamDoc] | None
    rounds_undecided: int


class LibraryDoc(BaseModel):
    root: DemoRootDoc
    maps_present: list[str]
    page: int
    page_count: int
    per_page: int
    cards: list[CardDoc]


class LibraryQuery(BaseModel):
    """
    How the match list is asked for.

    A model rather than two parameters because these travel together and
    because FastAPI then documents them as one shape, which is the shape the
    browser's query builder wants.

    Which captures are listed is not among them: only playable ones are, and
    the handler applies that itself rather than accepting a request to do
    otherwise.
    """

    map_name: str = ""
    page: int = 1


class CalloutDoc(BaseModel):
    name: str
    world_x: float
    world_y: float


class TransformDoc(BaseModel):
    """
    The four measured scalars, and the vertical scale derived from them.

    `apply` swaps the axes -- world *y* feeds u -- and the far end must too.
    The unswapped form does not fail, it lands 200 of 346 callouts inside the
    image instead of 346, which looks like a rendering bug rather than a
    transform bug.
    """

    x_multiplier: float
    y_multiplier: float
    x_scalar_to_add: float
    y_scalar_to_add: float
    usable: bool
    vertical_scale: float


class MapDoc(BaseModel):
    """
    One map's pictures and coordinates.  Deliberately carries no match data.

    The map reference is handed no replay in the desktop app by design, because
    it describes the map and not the match -- the same picture for every capture
    on Bind.  This model is how that guarantee survives becoming an endpoint.
    """

    name: str
    codename: str
    map_url: str
    plottable: bool
    minimap_url: str | None
    listview_url: str | None
    splash_url: str | None
    transform: TransformDoc
    callouts: list[CalloutDoc]


class SightDoc(BaseModel):
    """
    One map's playable silhouette, thresholded in Python.

    `cells` is base64 of one byte per cell, row-major, 1 open and 0 blocked --
    `sight.SightMap.cells` unchanged, so the browser's `blocked` is a literal
    port rather than a second implementation.  The constants below are sent
    for the same reason: `sight.py` is where they are decided.
    """

    map_key: str
    size: int
    cells: str
    open_fraction: float
    max_range_uu: float
    fov_degrees: float
    ray_step_degrees: float
    seed_cells: int
    probe_uu: float


class AbilityIconDoc(BaseModel):
    """
    One published ability slot on a player's card.

    `slot` is Riot's own name -- `Ability1`, `Ability2`, `Grenade`, `Ultimate`,
    `Passive` -- and deliberately not a keybind.  `Grenade` is C and `Ultimate`
    is X on every agent, but `Ability1` and `Ability2` are Q and E in an order
    that varies by agent, so naming a keybind here would be a coin flip wearing
    a label.  A card renders these in manifest order and says nothing about
    which key presses them; `art.AgentArt.ability` is where that reasoning
    lives.
    """

    slot: str
    name: str
    icon_url: str | None = None


class WeaponDoc(BaseModel):
    """
    One weapon's art, by display name.

    Nothing in a `.vrf` says which weapon anybody is holding -- the property
    payload carries it and nothing here decodes it -- so this is a catalogue,
    not a claim.  Whoever names a weapon owns saying where the name came from.
    """

    name: str
    category: str = ""
    cost: int | None = None
    icon_url: str | None = None
    killfeed_url: str | None = None


class WeaponsDoc(BaseModel):
    source: str
    weapons: list[WeaponDoc]


class PlayerDoc(BaseModel):
    actor_id: int
    team: str
    known_team: bool
    label: str
    merged_from: list[int]
    # Read off the pawn's own archetype path.
    codename: str
    # Looked up from that codename.  Never filled from the loadout.
    agent: str
    identity: str
    display: str
    icon_url: str | None = None
    portrait_url: str | None = None
    role_icon_url: str | None = None
    role: str = ""
    abilities: list[AbilityIconDoc] = []


class LoadoutDoc(BaseModel):
    index: int
    subject: str
    character_id: str
    agent: str
    display: str
    icon_url: str | None


class RoundDoc(BaseModel):
    """
    One round, buy phase included.

    `start_ms` is when `roundStarted` fired, which is the start of
    the buy phase; `action_start_ms` is when the barrier drops and the round
    becomes playable, which is looked up rather than read -- see
    `vrfview.roundrules` for the rule and the measurement behind it.
    """

    number: int
    index: int
    start_ms: int
    end_ms: int
    duration_ms: int
    buy_phase_ms: int
    action_start_ms: int
    winner: str
    reason: str
    decided: bool


class KillDoc(BaseModel):
    t_ms: int
    killer: int
    victim: int
    round_no: int
    is_suicide: bool


class UltimateDoc(BaseModel):
    t_ms: int
    actor_id: int
    round_no: int


class SpikeDoc(BaseModel):
    t_ms: int
    kind: str
    round_no: int
    # Decoded, where t_ms and kind are read: a spikePlanted event carries no
    # arguments, and the coordinate comes from the TimedBomb actor the plant
    # spawns.  See vrfview.tracks._plants_from for the measurement that
    # established these are the plant and not an actor that appears nearby.
    x: float | None = None
    y: float | None = None
    z: float | None = None


class AbilityMechanicsDoc(BaseModel):
    """
    What is published about one ability, and where each figure came from.

    None of this is read from the capture and none of it is measured: it is
    looked up in `vrfview.abilityfacts`, which is community research about a
    game that rebalances every few weeks.  Every figure is optional and a null
    must be drawn as nothing -- there is no default radius and no default
    duration, because a ring at a made-up size is worse than no ring.

    A source travels beside every figure rather than one per ability, since a
    single citation covering ten numbers stands behind numbers it never
    backed.

    `keybind` is the key the **game** binds.  `AbilityCast.slot` is the letter
    the archetype path states, and the two disagree for six of the sixteen
    agents in the table -- Sova's slot `C` is the Shock Bolt the game binds to
    Q.  Both travel; nothing may join them by letter.
    """

    ability: str
    keybind: str
    radius_uu: float | None = None
    radius_source: str | None = None
    # A trigger range rather than an area of effect, and drawn as a separate
    # ring for that reason: Chamber's Trademark publishes both a 10 m search
    # and a 6 m slow, and they are different claims.
    detection_radius_uu: float | None = None
    detection_radius_source: str | None = None
    windup_ms: float | None = None
    windup_source: str | None = None
    activation_delay_ms: float | None = None
    activation_delay_source: str | None = None
    duration_ms: float | None = None
    duration_source: str | None = None
    cooldown_ms: float | None = None
    cooldown_source: str | None = None
    charges: float | None = None
    charges_source: str | None = None
    deployable_hp: float | None = None
    deployable_hp_source: str | None = None
    # Whether this ability's own placements are a wall: `"segments"`, or null
    # for everything else.  Sage's Barrier Orb is the only one, and its whole
    # line is decoded -- see `AbilityCastDoc.walls`, which carries it.
    wall: str | None = None
    wall_source: str | None = None
    # Whether the thing stands until destroyed, triggered or the round ends --
    # a different question from `duration_ms`, which is how long its effect
    # lasts. An ability with neither is a moment: a flash pops, a dart
    # detonates. See `vrfview.abilityfacts.AbilityMechanics.persists`.
    persists: bool = False
    # Whether the thing goes when the player who left it there dies.  Narrower
    # than `persists` and meaningful only beside it: Chamber's Trademark and
    # Rendezvous and Cypher's Trapwire and Spycam are removed on his death, and
    # Killjoy's utility is not.  A published rule, joined to a decoded death.
    destroyed_on_caster_death: bool = False
    # Whether the ability looks at the map: a drone, a camera.  A pawn with
    # this set gets the view cone a living player gets, from its own decoded
    # position and yaw.
    sees: bool = False
    blocks_sight: bool = False


class FlightDoc(BaseModel):
    """
    One throw: two decoded coordinates and the decoded interval between them.

    Both ends are placements, so both the where and the when were read out of
    the capture.  What is **not** here is the path: only `Pawn_` actors emit
    movement, so nothing states where a thrown thing was halfway, and a client
    draws a straight line and labels it as one.
    """

    start_ms: int
    end_ms: int
    duration_ms: int
    from_actor_id: int
    from_x: float
    from_y: float
    from_z: float
    to_actor_id: int
    to_x: float
    to_y: float
    to_z: float


class WallDoc(BaseModel):
    """
    A wall, as the two ends of the line its own segment actors describe.

    Entirely decoded, unlike every other extent an ability has here: Sage's
    Barrier Orb opens one channel per segment at one instant and each carries
    its own spawn transform, so the line, its length and its orientation are
    all read.  Nothing about this is looked up, which is why it travels as
    geometry -- a client that had only a length would have to decide the
    direction, and deciding it is the thing that could not be done.

    Unreal units, in the same frame as a `Position` and a `PlacementDoc`.
    """

    t_ms: int
    segments: int
    x1: float
    y1: float
    x2: float
    y2: float
    length_uu: float


class PlacementDoc(BaseModel):
    """
    One actor a cast put in the world, at the coordinate it appeared at.

    Unreal units, in the same frame as a `Position`, so it goes through the
    map transform exactly as a player does.

    `t_ms` is the instant its channel opened, and *never moving* is exactly
    what makes that instant worth carrying rather than a reason to drop it.
    Anything that moves has a track, and its position is a question about now;
    this thing has one position for ever, so the only thing left to know about
    it in time is when it arrived -- which is what says how long the throw that
    delivered it took, and how long it has been standing since.
    """

    t_ms: int
    actor_id: int
    kind: str
    name: str
    display: str
    x: float
    y: float
    z: float


class AbilityCastDoc(BaseModel):
    """
    One cast, with both names, because only two of the four slots join.

    `published_name` is Riot's and resolves for X and C only; `internal_name` is
    read from the archetype path and is always there.  Q and E vary by agent, so
    a single name field would let a client prefer a coin flip.
    """

    t_ms: int
    round_no: int
    actor_id: int
    codename: str
    # The caster, or null where two players share the agent.  `actor_id` above
    # is the ability actor's id and no player has it, which is what left every
    # ability row in the round timeline sideless.  See wire.ability_cast.
    player_actor_id: int | None = None
    agent: str
    identity: str
    slot: str
    internal_name: str
    published_name: str | None
    icon_url: str | None
    spawns: int
    kinds: list[str]
    pawns: list[int]
    has_track: bool
    # Measured path length of the pawn's own track. Null, never zero, where no
    # pawn moved: no ability publishes a range anywhere.
    travel_uu: float | None
    travel_note: str | None
    # Looked up in `vrfview.abilityfacts`, not read and not measured: no
    # ability's radius is published by Riot, by val-content-v1 or by the
    # manifest.  `range_source` names where the figure came from, and the
    # browser draws it dashed under a layer labelled `RANGE (SIM)`.
    range_uu: float | None = None
    range_source: str | None = None
    # A round smoke, looked up in `vrfview.abilityfacts` on (codename, slot).
    # Null for everything that is not one, which is most casts: a molly and a
    # flash have a radius and do not block sight, and a wall blocks sight and
    # is not a circle.  The browser stops a sight ray inside this radius while
    # the cast is younger than this duration -- so it is *simulated* in exactly
    # the way `range_uu` is: a looked-up radius and a looked-up lifetime, and
    # `abilityfacts` carries a source string for each.
    smoke_radius_uu: float | None = None
    smoke_duration_ms: int | None = None
    smoke_source: str | None = None
    # Everything published about this ability, or null where nothing is.
    # Looked up in `vrfview.abilityfacts` on (codename, slot), so every figure
    # here is *simulated* in exactly the way `range_uu` is, and each carries
    # its own source string.
    mechanics: AbilityMechanicsDoc | None = None
    # Every non-moving actor this cast spawned, at the coordinate its channel
    # opened at.
    placements: list[PlacementDoc]
    # Which of them says where the cast ended up.  Null for a cast whose pawn
    # has a track, and for one decoded before the spawn transform was read.
    landed: PlacementDoc | None
    # Every throw in this cast whose two ends are both decoded.  Empty for
    # most casts: see `abilities.AbilityCast.flights` for the four refusals
    # and the measurement behind each.
    flights: list[FlightDoc] = []
    # Every wall this cast built out of its own segment actors, decoded end to
    # end.  Empty for all but Sage's Barrier Orb, which is the one ability in
    # the library that opens a channel per segment.
    walls: list[WallDoc] = []


class ReplayDoc(BaseModel):
    """Everything about one replay except the position samples."""

    id: str
    source: str
    match_id: str
    build: str
    recorded_utc: str
    length_ms: int
    side_swap_ms: int | None
    map_path: str
    map_name: str
    map_name_source: str
    map_key: str
    players: list[PlayerDoc]
    rounds: list[RoundDoc]
    kills: list[KillDoc]
    ultimates: list[UltimateDoc]
    spike: list[SpikeDoc]
    loadouts: list[LoadoutDoc]
    ability_casts: list[AbilityCastDoc]
    event_times: list[int]
    score: list[int]
    has_positions: bool
    has_abilities: bool
    # Whether a decode could work at all, which is not the same question as
    # whether one has happened. The same membership test `scan` makes against
    # the decoder's own table, so a card and a replay cannot disagree.
    positions_available: bool
    positions_note: str
    # Prose from the decoder, shown verbatim: `tracks.attach` never raises for
    # want of positions, it says what happened here.
    position_source: str
    catalog_source: str
    # Derived here.
    notes: list[str]
    # Looked up elsewhere.  A different kind of claim, kept in a different list.
    catalog_notes: list[str]


class ColumnsDoc(BaseModel):
    t: list[int]
    x: list[float]
    y: list[float]
    z: list[float]
    yaw: list[float]
    pitch: list[float]


class PositionsDoc(BaseModel):
    """
    `vrfview.positionfile`'s own document, served unchanged.

    The only place in this contract with string-keyed maps rather than records
    carrying an actor id, because this shape is already on disk with readers.
    One builder feeds the sidecar, the machine cache and this response.
    """

    format: str
    version: int
    match_id: str
    build: str
    hz: int
    position_source: str
    codenames: dict[str, str]
    tracks: dict[str, ColumnsDoc]
    ability_spawns: dict[str, list]
    ability_tracks: dict[str, ColumnsDoc]
    # `[t_ms, x, y, z]` per plant.  This was missing while the route sent it,
    # which nothing noticed for the same reason the route sent it unchecked:
    # the handler returns pre-serialised bytes, so no response ever passed
    # through this model.  Declaring it on the route is what makes the OpenAPI
    # document describe the endpoint at all; `TestPositionsDocIsTheDocument`
    # is what keeps this list equal to what `to_document` actually writes.
    spike_plants: list[tuple[int, float, float, float]]
