/**
 * What the server sends.
 *
 * **Hand-written, and that is the decision rather than a stopgap.**  It mirrors
 * `libraries/vrfserve/schema.py` and declares only the fields this page reads.
 *
 * There was a `npm run types` that would have generated the full set from the
 * running server's OpenAPI document into `schema.d.ts`, and it is gone: the
 * file it names had never once been generated, so the script and the two
 * paragraphs describing it amounted to a claim that this file was derived when
 * it never has been.  A generated file would also drop every comment below,
 * and those comments are the reason a reader can tell a `codename` from an
 * `agent`.  The pydantic models stay the contract --
 * `tests/test_vrfserve.py::WireBuilders` asserts every dict the server builds
 * validates against them -- so a field that changes shape fails in Python
 * first, which is where it should fail.
 *
 * Two shapes here carry an argument rather than just data, and both are
 * commented where they are declared: a player's `codename` and `agent` are
 * different kinds of claim, and an ability cast has two names because only two
 * of its four slots join to Riot's catalogue.
 */

export interface DemoRoot {
  path: string;
  exists: boolean;
  source: string;
  /** One sentence naming where the replay directory came from. Shown verbatim. */
  described: string;
}

export interface Decoder {
  /** Gates the DECODE button. False means no .NET SDK and no drop-in. */
  found: boolean;
  path: string;
  described: string;
  /** When absent, the sentence naming the command that would fix it. */
  hint: string;
}

export interface Config {
  demo_root: DemoRoot;
  decoder: Decoder;
  catalog_source: string;
  web_built: boolean;
  web_hint: string;
}

export interface Prewarm {
  state: string;
  note: string;
  done: number;
  total: number;
  label: string;
}

export interface CardAgent {
  name: string;
  icon_url: string | null;
}

/**
 * One of a card's two teams.
 *
 * The split is read off the loadout roster's own order and is a measurement --
 * `vrfhome.scan.team_ids` carries the numbers.  It is a *set*-level claim: these
 * five were one team, those five the other.  Nothing joins a roster slot to a
 * player, and nothing here pretends otherwise.
 *
 * `rounds_won` is null until something has established which of the two halves
 * `infer` calls team A, which only a decoded capture can say.  Null means "not
 * attributable", never zero.
 */
export interface CardTeam {
  agents: CardAgent[];
  rounds_won: number | null;
}

export interface Card {
  id: string;
  file_name: string;
  match_id: string;
  map_path: string;
  map_name: string;
  map_key: string;
  listview_url: string | null;
  recorded_utc: string | null;
  length_ms: number;
  rounds: number;
  players: number;
  size_bytes: number;
  /** Non-empty when the file would not parse. The card is shown anyway. */
  error: string;
  readable: boolean;
  playable: boolean;
  /** Why, when `playable` is false: the build has no payload transform. */
  positions_note: string;
  prewarm: Prewarm | null;
  /** Null where the split was refused or there is no art to draw it with. */
  teams: CardTeam[] | null;
  /** Rounds nothing settled, so a short scoreline can say why it is short. */
  rounds_undecided: number;
}

export interface Library {
  root: DemoRoot;
  maps_present: string[];
  page: number;
  page_count: number;
  per_page: number;
  cards: Card[];
}

/**
 * One published ability slot on a player's card.
 *
 * `slot` is Riot's own name -- `Ability1`, `Ability2`, `Grenade`, `Ultimate` --
 * and deliberately not a keybind.  `Grenade` is C and `Ultimate` is X on every
 * agent; `Ability1` and `Ability2` are Q and E in an order that varies by
 * agent, so nothing here may print a key.  The card draws the icons in the
 * order the server sent them and names only what it can.
 */
export interface AbilityIcon {
  slot: string;
  name: string;
  icon_url: string | null;
}

export interface Player {
  actor_id: number;
  team: string;
  known_team: boolean;
  label: string;
  merged_from: number[];
  /** Read off the pawn's own archetype path. */
  codename: string;
  /** Looked up from that codename. Never filled in from the loadout. */
  agent: string;
  identity: string;
  display: string;
  icon_url: string | null;
  portrait_url: string | null;
  role_icon_url: string | null;
  role: string;
  abilities: AbilityIcon[];
}

/**
 * One weapon's art, by display name.
 *
 * A catalogue and not a claim: nothing decoded from a `.vrf` says who is
 * holding what, so whoever names a weapon owns saying where the name came
 * from.  Today that is `model/synthetic.ts`, and the page says so.
 */
export interface Weapon {
  name: string;
  category: string;
  cost: number | null;
  icon_url: string | null;
  /** The flat silhouette Riot draws between a killer and a victim. */
  killfeed_url: string | null;
}

export interface Weapons {
  source: string;
  weapons: Weapon[];
}

export interface Loadout {
  index: number;
  subject: string;
  character_id: string;
  agent: string;
  display: string;
  icon_url: string | null;
}

export interface Round {
  number: number;
  index: number;
  /** When `roundStarted` fired, which is the start of the buy phase. */
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  buy_phase_ms: number;
  /**
   * When the barrier drops and the round becomes playable.
   *
   * Looked up rather than read -- nothing in a capture states a buy phase --
   * and computed once in `vrfview.roundrules` so the browser does no arithmetic
   * of its own.  Clamped to `end_ms`, where it means the round was shorter than
   * its own buy phase and there is no such instant in it.
   */
  action_start_ms: number;
  winner: string;
  reason: string;
  decided: boolean;
}

export interface Kill {
  t_ms: number;
  killer: number;
  victim: number;
  round_no: number;
  is_suicide: boolean;
}

export interface Ultimate {
  t_ms: number;
  actor_id: number;
  round_no: number;
}

export interface SpikeEvent {
  t_ms: number;
  kind: string;
  round_no: number;
  /**
   * Where it was planted, in Unreal units, or null.
   *
   * Decoded, where `t_ms` and `kind` are read: a `spikePlanted` event carries
   * no arguments at all, and the coordinate comes from the `TimedBomb` actor
   * the plant spawns.  Null on a defuse, on an explode, and on any plant in a
   * capture nothing has decoded -- three absences that all mean "draw nothing
   * here".  See `vrfview.tracks._plants_from` for the measurement that settled
   * these are the plant and not an actor that happens to appear nearby.
   */
  x: number | null;
  y: number | null;
  z: number | null;
}

export interface Placement {
  /**
   * When this actor's channel opened.
   *
   * Never moving is what makes one instant worth carrying: anything that moves
   * has a track and its position is a question about now, where this has one
   * position for ever. So the only thing left to know about it in time is when
   * it arrived -- which is how long the throw that delivered it took, and how
   * long it has been standing since. Both were decoded.
   */
  t_ms: number;
  actor_id: number;
  kind: string;
  name: string;
  display: string;
  /** Unreal units, the same frame as a Position: it goes through the transform. */
  x: number;
  y: number;
  z: number;
}

export interface AbilityCast {
  t_ms: number;
  round_no: number;
  actor_id: number;
  codename: string;
  agent: string;
  identity: string;
  slot: string;
  /** Read from the archetype path. Always present. */
  internal_name: string;
  /** Riot's, and only for X and C: Q and E vary by agent, so this is null there. */
  published_name: string | null;
  icon_url: string | null;
  spawns: number;
  kinds: string[];
  pawns: number[];
  has_track: boolean;
  /** Measured path length. Null, never zero, where no pawn moved. */
  travel_uu: number | null;
  travel_note: string | null;
  /**
   * A published radius in Unreal units, or null.
   *
   * Neither read nor measured: looked up in `vrfview.abilityfacts`, which is
   * community research about the game rather than anything this capture
   * states.  `travel_uu` beside it is the opposite kind of number -- a path
   * length a pawn actually covered -- and the two must never be conflated: a
   * distance travelled drawn as a circle becomes an area of effect.
   *
   * Null for the many abilities nobody publishes a radius for, and drawn
   * dashed under a layer labelled `RANGE (SIM)` when it is not.
   */
  range_uu: number | null;
  range_source: string | null;
  /**
   * The caster's actor id, or null where the codename is shared.
   *
   * `actor_id` above is the **ability actor's** id, not the caster's, which is
   * a trap this field exists to close: `sideAt(cast.actor_id, ...)` resolved
   * nobody, so every ability row in the round timeline was silently sideless.
   * Filled by `abilities.attribute()`, which refuses an ambiguous codename
   * rather than picking the first player holding it.
   */
  player_actor_id: number | null;
  /** Every non-moving actor this cast spawned, at the point it appeared. */
  placements: Placement[];
  /**
   * Which of them says where the cast ended up. Null for a cast whose pawn has
   * a track -- the track outranks a spawn point -- and for one decoded before
   * the spawn transform was read, which is every v1 and v2 sidecar.
   */
  landed: Placement | null;
  /**
   * A round smoke: how wide it is, how long it stands, and on whose word.
   *
   * Null for everything that is not one, which is most casts -- a molly has a
   * radius and does not block sight, and a wall blocks sight and is not a
   * circle. Looked up in `vrfview.abilityfacts` on (codename, slot), so it is
   * *simulated* exactly the way `range_uu` is, and `smoke_source` carries the
   * word it is taken on. `sightlayer.smokesAt` turns these into `Occluder`s
   * and stops sight rays inside them while the cast is younger than
   * `smoke_duration_ms`.
   */
  smoke_radius_uu: number | null;
  smoke_duration_ms: number | null;
  smoke_source: string | null;
  /**
   * Everything published about this ability, or null where nothing is.
   *
   * Looked up in `vrfview.abilityfacts` on (codename, slot), so every figure
   * here is *simulated* in exactly the way `range_uu` is -- community research
   * about a game that rebalances every few weeks. Each figure carries its own
   * source, because one citation covering ten numbers stands behind numbers it
   * never backed.
   */
  mechanics: AbilityMechanics | null;
  /**
   * Every throw in this cast whose two ends are both decoded.
   *
   * Empty for most casts, and that is the answer rather than a gap: a cast is
   * one agent, one slot, one round, so pairing k throw origins to j landings is
   * a guess as soon as the two disagree, and most casts disagree. See
   * `abilities.AbilityCast.flights` for all four refusals and the measurement
   * behind each.
   */
  flights: Flight[];
  /**
   * Every wall this cast built out of its own segment actors.
   *
   * Empty for all but Sage's Barrier Orb, which is the one ability in the
   * library that opens a channel per segment -- so its line, its length and
   * its orientation are decoded rather than looked up, and it is drawn solid
   * where a facing-derived wall is dashed.
   */
  walls: Wall[];
}

/** A wall, as the two ends of the line its own segment actors describe. */
export interface Wall {
  t_ms: number;
  segments: number;
  /** Unreal units, the same frame as a Position. */
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  length_uu: number;
}

/**
 * One throw: two decoded coordinates and the decoded interval between them.
 *
 * A `Projectile_` channel opens where the caster is standing and a placed
 * channel opens where the thing came to rest, and `Placement.t_ms` says when
 * each of them did. So a throw is entirely decoded except for one thing: the
 * path. Only `Pawn_` actors emit movement, so nothing states where a thrown
 * thing was halfway, and **no consumer may draw a curve**. A straight dashed
 * line between two decoded points is the same claim a kill tracer makes.
 */
export interface Flight {
  start_ms: number;
  end_ms: number;
  /** Always positive: a non-positive span is refused rather than built. */
  duration_ms: number;
  from_actor_id: number;
  from_x: number;
  from_y: number;
  from_z: number;
  to_actor_id: number;
  to_x: number;
  to_y: number;
  to_z: number;
}

/**
 * What is published about one ability, and where each figure came from.
 *
 * None of this is read from the capture and none of it is measured. Every
 * figure is optional and a null must be drawn as **nothing** -- there is no
 * default radius and no default duration, because a ring at a made-up size is
 * worse than no ring: the absent one is visibly absent.
 */
export interface AbilityMechanics {
  /** Riot's published name, e.g. "Recon Bolt". */
  ability: string;
  /**
   * The key the *game* binds, which is **not** `AbilityCast.slot`.
   *
   * The slot is Riot's internal letter, read from the archetype path, and the
   * two disagree for six of the sixteen agents in the table -- Sova's slot `C`
   * is the Shock Bolt the game binds to Q. Both travel; nothing may join them
   * by letter.
   */
  keybind: string;
  radius_uu: number | null;
  radius_source: string | null;
  /**
   * A trigger range rather than an area of effect, and drawn as its own ring
   * for that reason: Chamber's Trademark publishes both a 10 m search and a
   * 6 m slow, and they are different claims about different things.
   */
  detection_radius_uu: number | null;
  detection_radius_source: string | null;
  windup_ms: number | null;
  windup_source: string | null;
  activation_delay_ms: number | null;
  activation_delay_source: string | null;
  duration_ms: number | null;
  duration_source: string | null;
  cooldown_ms: number | null;
  cooldown_source: string | null;
  charges: number | null;
  charges_source: string | null;
  deployable_hp: number | null;
  deployable_hp_source: string | null;
  /**
   * Whether this ability's own placements are a wall: `"segments"`, or null
   * for everything else.
   *
   * Sage's Barrier Orb is the only one: it opens a channel per segment and the
   * whole line is decoded, so it is drawn solid like every other stroke on
   * this canvas around something that was read out of the capture.
   *
   * There were two other values, for a wall drawn along the caster's facing at
   * a looked-up length, and the premise was wrong twice over. Phoenix's Blaze
   * and Harbor's High Tide follow a steerable missile's path and rise along
   * it, so each cast is a polyline of a different length and there is no
   * figure to look up; and Vyse's Shear is placed on vertical terrain, so its
   * axis belongs to the wall she was looking at rather than to the way her
   * body faced. The yaw was a weak predictor regardless -- on the one wall
   * whose axis is decoded it is parallel 66.4% of the time and perpendicular
   * 28.8%, because a player can rotate that one while placing it.
   */
  wall: string | null;
  wall_source: string | null;
  /**
   * Whether the thing stands until destroyed, triggered or the round ends.
   *
   * A different question from `duration_ms`, which is how long its *effect*
   * lasts. A Trademark publishes a 4-second slow and waits on the floor all
   * round; a Turret publishes no duration and stands until it is shot. An
   * ability with neither is a moment -- a flash pops, a dart detonates.
   */
  persists: boolean;
  /**
   * Whether the thing goes when the player who left it there dies.
   *
   * Narrower than `persists` and meaningful only beside it: Chamber's
   * Trademark and Rendezvous and Cypher's Trapwire and Spycam are removed the
   * moment their owner dies, and Killjoy's utility is not. A published rule of
   * the game, joined to a death the capture states outright.
   */
  destroyed_on_caster_death: boolean;
  /** Whether the ability looks at the map: a drone, a camera. */
  sees: boolean;
  blocks_sight: boolean;
}

export interface SightMaskDoc {
  map_key: string;
  size: number;
  /** Base64, one byte per cell, row-major, 1 open. Thresholded in Python. */
  cells: string;
  open_fraction: number;
  max_range_uu: number;
  fov_degrees: number;
  ray_step_degrees: number;
  seed_cells: number;
  probe_uu: number;
}

export interface Replay {
  id: string;
  source: string;
  match_id: string;
  build: string;
  recorded_utc: string;
  length_ms: number;
  side_swap_ms: number | null;
  map_path: string;
  map_name: string;
  map_name_source: string;
  map_key: string;
  players: Player[];
  rounds: Round[];
  kills: Kill[];
  ultimates: Ultimate[];
  spike: SpikeEvent[];
  loadouts: Loadout[];
  ability_casts: AbilityCast[];
  event_times: number[];
  score: number[];
  has_positions: boolean;
  has_abilities: boolean;
  /**
   * Whether a decode could work at all on this build -- a different question
   * from whether one has happened. It gates the DECODE button: a control that
   * can only ever refuse is worse than an explanation of its absence.
   */
  positions_available: boolean;
  positions_note: string;
  /** Prose from the decoder. Shown verbatim; it never raises for want of positions. */
  position_source: string;
  catalog_source: string;
  /** Derived here. */
  notes: string[];
  /** Looked up elsewhere. A different kind of claim, kept in a different list. */
  catalog_notes: string[];
}

export interface Callout {
  name: string;
  world_x: number;
  world_y: number;
}

export interface Transform {
  x_multiplier: number;
  y_multiplier: number;
  x_scalar_to_add: number;
  y_scalar_to_add: number;
  usable: boolean;
  /** Unreal units to a fraction of the radar; the 3D scene's vertical scale. */
  vertical_scale: number;
}

export interface MapArt {
  name: string;
  codename: string;
  map_url: string;
  plottable: boolean;
  minimap_url: string | null;
  listview_url: string | null;
  splash_url: string | null;
  transform: Transform;
  callouts: Callout[];
}

export interface LibraryQuery {
  map_name?: string;
  page?: number;
}
