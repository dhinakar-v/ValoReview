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


class ArtDoc(BaseModel):
    described: str
    empty: bool
    root: str
    source: str
    version: str
    maps: int
    agents: int


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
    art: ArtDoc
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


class CardDoc(BaseModel):
    id: str
    file_name: str
    match_id: str
    map_path: str
    map_name: str
    map_key: str
    listview_url: str | None
    recorded_utc: str | None
    recorded: str
    length_ms: int
    duration: str
    rounds: int
    players: int
    build: str
    size_bytes: int
    error: str
    readable: bool
    positions_available: bool
    positions_note: str
    playable: bool
    # Always `scan.RESULT_NOT_IN_FILE`.  Sent rather than omitted so the card
    # shows the sentence instead of a gap where a verdict should be.
    result: str
    prewarm: PrewarmDoc | None


class LibraryCounts(BaseModel):
    total: int
    playable: int
    hidden: int
    failed: int


class LibraryDoc(BaseModel):
    root: DemoRootDoc
    described: str
    read: int
    cached: int
    counts: LibraryCounts
    maps_present: list[str]
    page: int
    page_count: int
    per_page: int
    cards: list[CardDoc]


class LibraryQuery(BaseModel):
    """
    How the match list is asked for.

    A model rather than six parameters because these travel together and
    because FastAPI then documents them as one shape, which is the shape the
    browser's query builder wants.

    `playable_only` defaults on: a capture whose build has no payload transform
    cannot show a position, and there is no schematic to fall back to.  The
    rest are counted in the response and one request away, never dropped.
    """

    refresh: bool = False
    playable_only: bool = True
    map_name: str = ""
    date: str = ""
    page: int = 1
    descending: bool = False


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


class MapSummary(BaseModel):
    name: str
    codename: str
    map_url: str
    plottable: bool
    listview_url: str | None
    minimap_url: str | None
    callout_count: int


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


class LoadoutDoc(BaseModel):
    index: int
    subject: str
    character_id: str
    agent: str
    display: str
    icon_url: str | None


class RoundDoc(BaseModel):
    number: int
    index: int
    start_ms: int
    end_ms: int
    duration_ms: int
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


class ProvenanceEntry(BaseModel):
    label: str
    value: str
    bare: bool


class ProvenanceSection(BaseModel):
    title: str
    label_width: int
    entries: list[ProvenanceEntry]


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
    # Prose from the decoder, shown verbatim: `tracks.attach` never raises for
    # want of positions, it says what happened here.
    position_source: str
    catalog_source: str
    # Derived here.
    notes: list[str]
    # Looked up elsewhere.  A different kind of claim, kept in a different list.
    catalog_notes: list[str]
    provenance: list[ProvenanceSection]


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
