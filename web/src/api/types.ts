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

export interface ArtSummary {
  described: string;
  empty: boolean;
  root: string;
  source: string;
  version: string;
  maps: number;
  agents: number;
}

export interface Config {
  demo_root: DemoRoot;
  art: ArtSummary;
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
  build: string;
  size_bytes: number;
  /** Non-empty when the file would not parse. The card is shown anyway. */
  error: string;
  readable: boolean;
  positions_available: boolean;
  positions_note: string;
  playable: boolean;
  /**
   * Always "result not in file". A replay has no local player and teams are A
   * and B by inference, so the WIN/LOSS badge cannot be built and the card
   * says so rather than leaving a gap where a verdict should be.
   */
  result: string;
  prewarm: Prewarm | null;
}

export interface LibraryCounts {
  total: number;
  playable: number;
  /** Held back by the default filter, counted here rather than dropped. */
  hidden: number;
  failed: number;
}

export interface Library {
  root: DemoRoot;
  described: string;
  read: number;
  cached: number;
  counts: LibraryCounts;
  maps_present: string[];
  page: number;
  page_count: number;
  per_page: number;
  cards: Card[];
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
}

export interface ProvenanceEntry {
  label: string;
  value: string;
  bare: boolean;
}

export interface ProvenanceSection {
  title: string;
  label_width: number;
  entries: ProvenanceEntry[];
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
  /** Prose from the decoder. Shown verbatim; it never raises for want of positions. */
  position_source: string;
  catalog_source: string;
  /** Derived here. */
  notes: string[];
  /** Looked up elsewhere. A different kind of claim, kept in a different list. */
  catalog_notes: string[];
  provenance: ProvenanceSection[];
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

export interface MapSummary {
  name: string;
  codename: string;
  map_url: string;
  plottable: boolean;
  listview_url: string | null;
  minimap_url: string | null;
  callout_count: number;
}

export interface LibraryQuery {
  refresh?: boolean;
  playable_only?: boolean;
  map_name?: string;
  date?: string;
  page?: number;
  descending?: boolean;
}
