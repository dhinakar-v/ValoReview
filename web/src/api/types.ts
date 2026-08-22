/**
 * What the server sends.
 *
 * Hand-written for now and kept deliberately thin, mirroring
 * `libraries/vrfserve/schema.py`.  `npm run types` regenerates the full set
 * from the running server's OpenAPI document into `schema.d.ts`; until a route
 * settles it is cheaper to declare only the fields this page reads than to
 * regenerate on every backend edit.
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

export interface Card {
  id: string;
  file_name: string;
  match_id: string;
  map_path: string;
  map_name: string;
  map_key: string;
  listview_url: string | null;
  recorded_utc: string | null;
  recorded: string;
  length_ms: number;
  duration: string;
  rounds: number;
  players: number;
  size_bytes: number;
  /** Non-empty when the file would not parse. The card is shown anyway. */
  error: string;
  readable: boolean;
  playable: boolean;
  prewarm: Prewarm | null;
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
  start_ms: number;
  end_ms: number;
  duration_ms: number;
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
}

export interface Placement {
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
  /** Every non-moving actor this cast spawned, at the point it appeared. */
  placements: Placement[];
  /**
   * Which of them says where the cast ended up. Null for a cast whose pawn has
   * a track -- the track outranks a spawn point -- and for one decoded before
   * the spawn transform was read, which is every v1 and v2 sidecar.
   */
  landed: Placement | null;
}

export interface SightMaskDoc {
  map_key: string;
  size: number;
  /** Base64, one byte per cell, row-major, 1 open. Thresholded in Python. */
  cells: string;
  open_fraction: number;
  /**
   * What a cone drawn from this is, in words. It travels with the cells so
   * nothing can render a wedge without having been handed the sentence.
   */
  caption: string;
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
