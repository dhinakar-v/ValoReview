/**
 * The numbers a `.vrf` does not carry, generated in one place.
 *
 * Health, armour, credits, the weapon in somebody's hands and which side was
 * attacking are **not in the file and are not decoded anywhere** -- see
 * `libraries/vrfview/provenance.ABSENT`, which is a constant rather than a
 * derivation precisely so "this capture resolved nothing" stays distinguishable
 * from "the format never carries it".  They are generated here because the
 * interface was asked to show them.
 *
 * Three rules make that survivable, and none of them is decoration:
 *
 *   * **One module.**  Nothing else in `web/src` invents a value.  Deleting
 *     this file and its call sites is the whole rollback when a real decode
 *     lands, and the compiler finds every site.
 *   * **Deterministic.**  A xorshift seeded on the match id, the actor and the
 *     round -- never on a clock or a random -- so the same frame is the same
 *     numbers across reloads, across the 2D and 3D views, and in a screenshot
 *     taken a month apart.  A Playwright suite cannot photograph noise.
 *   * **Driven by real events wherever any exist.**  Health is zero exactly
 *     when `Snapshot.alive` says the player is dead; the economy pays out on
 *     `Round.winner`, which `infer` two-coloured; the side swap happens at the
 *     real `Replay.side_swap_ms`.  What is generated is the shape between those
 *     points, not the points.
 *
 * The page says so, in `SIMULATED_NOTE`, wherever these values are shown.
 */

import type { Replay, Round, Weapon } from "../api/types";
import type { ReplayModel } from "./replay";
import type { Snapshot } from "./state";

export const SIMULATED_NOTE =
  "Health, armour, credits, the weapon held, ability charges and which side " +
  "attacked are not in a .vrf and are not decoded: these are simulated from " +
  "the real kills, rounds, ability casts and side swap. Positions, deaths, " +
  "rounds and ability casts are read.";

/** The short form, for a chip that has no room for the sentence. */
export const SIMULATED_LABEL = "SIMULATED";

export type Side = "ATK" | "DEF";

export interface Vitals {
  /** 0..100. Zero exactly when the snapshot says the player is dead. */
  health: number;
  /** 0..50. Absorbs before health does. */
  armor: number;
  /** Credits left after the round's buy. */
  money: number;
  /** The catalogue name, or null -- which the interface says in words. */
  weapon: string | null;
}

/* -- the generator ------------------------------------------------------- */

/**
 * FNV-1a over a string, then xorshift32 for the stream.
 *
 * Deliberately not `Math.random`, and deliberately not a hash of the wall
 * clock: two components asking for the same player's health on the same frame
 * have to get the same answer, and they do not share a cache.
 */
function seedOf(text: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  // Zero is a fixed point of xorshift, so it can never be the seed.
  return hash === 0 ? 0x9e3779b9 : hash;
}

class Rng {
  private state: number;

  constructor(text: string) {
    this.state = seedOf(text);
  }

  /** 0..1, exclusive of 1. */
  next(): number {
    let x = this.state;
    x ^= x << 13;
    x >>>= 0;
    x ^= x >>> 17;
    x ^= x << 5;
    x >>>= 0;
    this.state = x;
    return x / 0x100000000;
  }

  /** An integer in [low, high]. */
  int(low: number, high: number): number {
    return low + Math.floor(this.next() * (high - low + 1));
  }

  pick<T>(items: readonly T[]): T {
    return items[Math.floor(this.next() * items.length)]!;
  }
}

/* -- sides --------------------------------------------------------------- */

/**
 * Which side a team was on at an instant.
 *
 * `infer` two-colours the kill graph into A and B and stops there -- spike
 * events carry no actor id, so which of them planted is not recoverable.  A is
 * assigned to the attacking half, which is the generated part; **the swap
 * instant is real**, read from the container's `switchTeams` event, so a
 * capture that records one flips at exactly the right millisecond.
 */
export function sideOf(replay: Replay, team: string, tMs: number): Side {
  const swapped = replay.side_swap_ms !== null && tMs >= replay.side_swap_ms;
  const attacking = swapped ? "B" : "A";
  return team === attacking ? "ATK" : "DEF";
}

/** The side each team is on for a whole round, taken at the round's start. */
export function sideInRound(replay: Replay, team: string, round: Round | null): Side {
  return sideOf(replay, team, round ? round.start_ms : 0);
}

/* -- the economy --------------------------------------------------------- */

const PISTOL_CREDITS = 800;
const MAX_CREDITS = 9000;
const WIN_REWARD = 3000;
/** Riot's loss bonus ladder, which climbs with consecutive losses. */
const LOSS_LADDER = [1900, 2400, 2900] as const;

/** Weapon names as the catalogue publishes them, grouped by what they cost. */
const TIERS = [
  { floor: 0, weapons: ["Classic"] },
  { floor: 500, weapons: ["Shorty", "Frenzy", "Ghost"] },
  { floor: 1000, weapons: ["Sheriff", "Stinger", "Bucky"] },
  { floor: 1600, weapons: ["Spectre", "Bulldog", "Judge"] },
  { floor: 2200, weapons: ["Guardian", "Marshal", "Ares"] },
  { floor: 2900, weapons: ["Vandal", "Phantom", "Outlaw"] },
  { floor: 4700, weapons: ["Operator", "Odin"] },
] as const;

const ARMOR_FULL = 50;
const ARMOR_LIGHT = 25;
const ARMOR_UNIT_COST = 20;
const SAVE_BANK = 3900;
const SAVE_CHANCE = 0.25;
const UNARMED_CHANCE = 0.06;

interface RoundEconomy {
  /** Credits in hand when the round started. */
  bank: number;
  /** What was spent, so the card can show the leftover. */
  spend: number;
  armor: number;
  weapon: string | null;
}

/** The first round of the second half, or null where nothing swapped. */
function firstOfSecondHalf(replay: Replay): number | null {
  if (replay.side_swap_ms === null) {
    return null;
  }
  const swap = replay.side_swap_ms;
  return replay.rounds.find((round) => round.start_ms >= swap)?.number ?? null;
}

/**
 * One player's whole economy, round by round, from the real round outcomes.
 *
 * Computed forward over the match rather than sampled per round, because a bank
 * balance is cumulative: a card showing 4,300 credits in round nine has to
 * follow from what rounds one to eight paid out, or the number changes every
 * time the playhead crosses a boundary.
 */
function economy(replay: Replay, actorId: number, team: string): RoundEconomy[] {
  const rng = new Rng(`${replay.match_id}:${actorId}:economy`);
  const secondHalf = firstOfSecondHalf(replay);
  const out: RoundEconomy[] = [];
  let bank = PISTOL_CREDITS;
  let losses = 0;

  for (const round of replay.rounds) {
    // A pistol round is a pistol round on both sides of the swap: the first of
    // each half starts everybody at the floor.
    if (round.number === 1 || round.number === secondHalf) {
      bank = PISTOL_CREDITS;
      losses = 0;
    }

    const affordable = [...TIERS].reverse().find((tier) => tier.floor <= bank) ?? TIERS[0];
    // Not everybody buys to the ceiling, and a save round is a real thing: a
    // roster where all five always hold the same rifle reads as a mock.
    const saving = bank < SAVE_BANK && rng.next() < SAVE_CHANCE;
    const chosen = saving ? TIERS[0] : affordable;
    const weapon = rng.next() < UNARMED_CHANCE ? null : rng.pick(chosen.weapons);
    const cost = weapon === null ? 0 : chosen.floor;
    const left = bank - cost;
    let armor = 0;
    if (!saving && left >= ARMOR_FULL * ARMOR_UNIT_COST) {
      armor = ARMOR_FULL;
    } else if (!saving && left >= ARMOR_LIGHT * ARMOR_UNIT_COST) {
      armor = ARMOR_LIGHT;
    }
    const spend = Math.min(bank, cost + armor * ARMOR_UNIT_COST);

    out.push({ bank, spend, armor, weapon });

    // The payout, from the round's own inferred winner.  An undetermined round
    // pays nobody and leaves the ladder alone: `infer` left an explicit unknown
    // and this must not quietly resolve it.
    bank -= spend;
    if (round.decided && round.winner === team) {
      bank += WIN_REWARD;
      losses = 0;
    } else if (round.decided) {
      bank += LOSS_LADDER[Math.min(losses, LOSS_LADDER.length - 1)]!;
      losses += 1;
    }
    bank = Math.min(MAX_CREDITS, bank);
  }
  return out;
}

/* -- damage -------------------------------------------------------------- */

interface Hit {
  atMs: number;
  amount: number;
}

const MAX_HITS = 2;
const MIN_DAMAGE = 15;
const MAX_DAMAGE = 65;
const FULL_HEALTH = 100;

/**
 * The damage a player takes during a round, before whatever killed them.
 *
 * Seeded per actor per round and sorted, so health only ever falls while the
 * round runs -- a card whose health went back up would read as a bug in the
 * decode rather than as a fiction.
 */
function damage(replay: Replay, actorId: number, round: Round): Hit[] {
  const rng = new Rng(`${replay.match_id}:${actorId}:${round.number}:damage`);
  const count = rng.int(0, MAX_HITS);
  const hits: Hit[] = [];
  for (let i = 0; i < count; i += 1) {
    hits.push({
      atMs: round.start_ms + rng.int(0, Math.max(1, round.duration_ms - 1)),
      amount: rng.int(MIN_DAMAGE, MAX_DAMAGE),
    });
  }
  return hits.sort((a, b) => a.atMs - b.atMs);
}

/* -- the reading --------------------------------------------------------- */

const CACHE = new WeakMap<Replay, Map<number, RoundEconomy[]>>();

function economyFor(replay: Replay, actorId: number, team: string): RoundEconomy[] {
  let byActor = CACHE.get(replay);
  if (byActor === undefined) {
    byActor = new Map();
    CACHE.set(replay, byActor);
  }
  let found = byActor.get(actorId);
  if (found === undefined) {
    found = economy(replay, actorId, team);
    byActor.set(actorId, found);
  }
  return found;
}

const EMPTY: Vitals = { health: 0, armor: 0, money: 0, weapon: null };

/**
 * One player's card numbers at the snapshot's instant.
 *
 * Dead is not generated: `Snapshot.alive` is computed from the real
 * `characterDeath` events, so a dead player reads zero health, zero armour and
 * no weapon, and the card desaturates on the same fact.
 */
export function vitalsAt(model: ReplayModel, snap: Snapshot, actorId: number): Vitals {
  const replay = model.replay;
  const player = replay.players.find((p) => p.actor_id === actorId);
  if (player === undefined || snap.round === null) {
    return EMPTY;
  }
  const index = replay.rounds.indexOf(snap.round);
  const economics = economyFor(replay, actorId, player.team)[index];
  if (economics === undefined) {
    return EMPTY;
  }
  const money = Math.max(0, economics.bank - economics.spend);
  if (!snap.alive.has(actorId)) {
    return { health: 0, armor: 0, money, weapon: null };
  }

  let health = FULL_HEALTH;
  let armor = economics.armor;
  for (const hit of damage(replay, actorId, snap.round)) {
    if (hit.atMs > snap.t_ms) {
      break;
    }
    const absorbed = Math.min(armor, Math.round(hit.amount / 2));
    armor -= absorbed;
    health -= hit.amount - absorbed;
  }
  return {
    // Alive means alive: the floor is 1, because zero health on a player the
    // event stream says is standing is the one contradiction this must not put
    // on screen.
    health: Math.max(1, health),
    armor: Math.max(0, armor),
    money,
    weapon: economics.weapon,
  };
}

/**
 * The weapon a kill was made with, by round rather than by snapshot.
 *
 * The kill feed and the round timeline both need this, and the timeline lists a
 * whole round at once with no snapshot to read.  Same table, same seed, same
 * answer as the card is showing.
 */
export function weaponInRound(
  replay: Replay,
  actorId: number,
  roundNo: number,
): string | null {
  const player = replay.players.find((p) => p.actor_id === actorId);
  if (player === undefined) {
    return null;
  }
  const index = replay.rounds.findIndex((round) => round.number === roundNo);
  if (index < 0) {
    return null;
  }
  return economyFor(replay, actorId, player.team)[index]?.weapon ?? null;
}

/** Look one up in the catalogue the server sent, by name. */
export function weaponArt(
  weapons: Weapon[] | undefined,
  name: string | null,
): Weapon | null {
  if (!name || weapons === undefined) {
    return null;
  }
  return weapons.find((weapon) => weapon.name === name) ?? null;
}

/* -- ability charges ------------------------------------------------------ */

/**
 * What a roster card can say about one ability slot this round.
 *
 * The review asked for used charges to come off the card and for the remainder
 * to be visible.  Two halves of that are not in a `.vrf` and one is:
 *
 *   * **Used** is real for two slots and only two.  The ultimate comes from
 *     `Snapshot.ultedThisRound`, which is a `characterUltimateUsed` event
 *     carrying the player's own actor id -- exact, no join.  `Grenade` joins to
 *     a cast whose keybind is `C`.  `Ability1` and `Ability2` are Q and E in an
 *     order that varies by agent, and Riot's own archetype letters do not track
 *     the game's current keybinds either (`vrfview.abilityfacts` has the
 *     measurement), so which of the two a `Q` cast spent is **not knowable**
 *     and is generated.
 *   * **How many charges there were** is nowhere in the replay, the manifest or
 *     val-content-v1.  Generated.
 *   * **How many are left** is worse than absent: `AbilityCast` groups every
 *     use of a slot in a round into one record on purpose, so the model can say
 *     "this was used at some point this round" and can never say how often.
 *     The remainder is therefore generated too, and never claims exhaustion
 *     from a real cast.
 *
 * Deterministic on the match, the actor, the round and the slot -- never on a
 * clock, because the Playwright suite photographs this.
 */
export interface SlotState {
  /** Charges the card shows, generated. Always at least one. */
  charges: number;
  /** Charges still available, generated except where `usedIsReal`. */
  left: number;
  /** Whether a real event says this slot was used this round. */
  used: boolean;
  /** Whether `used` came from the file rather than from the generator. */
  usedIsReal: boolean;
}

/** Riot's slot names, in the order `wire.ABILITY_ORDER` sends them. */
const REAL_SLOT_FOR: Record<string, string> = { Grenade: "C", Ultimate: "X" };

export function slotStateAt(
  model: ReplayModel,
  snap: Snapshot,
  actorId: number,
  slot: string,
): SlotState {
  const round = snap.round?.number ?? 0;
  const rng = new Rng(`${model.replay.match_id}:${actorId}:${round}:${slot}:charges`);
  // One or two, the way most of the game's basic abilities go. The ultimate is
  // one thing you either have or do not.
  const charges = slot === "Ultimate" ? 1 : rng.int(1, 2);

  const keybind = REAL_SLOT_FOR[slot];
  let used = false;
  let usedIsReal = false;
  if (slot === "Ultimate") {
    used = snap.ultedThisRound.has(actorId);
    usedIsReal = true;
  } else if (keybind !== undefined) {
    used = snap.roundCasts.some(
      (cast) => cast.player_actor_id === actorId && cast.slot === keybind,
    );
    usedIsReal = true;
  } else {
    // Q and E: something was cast, but not which of the two icons it was.
    const cast = snap.roundCasts.some(
      (entry) => entry.player_actor_id === actorId && (entry.slot === "Q" || entry.slot === "E"),
    );
    used = cast && rng.next() < 0.5;
  }

  return { charges, left: used ? Math.max(0, charges - 1) : charges, used, usedIsReal };
}
