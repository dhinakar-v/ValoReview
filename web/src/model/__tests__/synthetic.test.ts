/**
 * The generated numbers, and the three properties that make them survivable.
 *
 * Health, armour, credits, the weapon held and which side attacked are not in a
 * `.vrf` and are not decoded anywhere; this module invents them because the
 * interface was asked to show them.  What keeps that from becoming a lie the
 * page cannot walk back is that it is confined to one module, that it is
 * deterministic, and that it defers to a real event wherever one exists.
 *
 * Each of those is asserted here, because each fails silently: a
 * non-deterministic generator only shows up as a screenshot suite that will not
 * settle, and a dead player reading 74 health only shows up as a bug report
 * against the decoder.
 */

import { describe, expect, it } from "vitest";

import type { Player, Replay, Round } from "../../api/types";
import type { ReplayModel } from "../replay";
import { stateAt } from "../state";
import { sideOf, slotStateAt, vitalsAt, weaponArt, weaponInRound } from "../synthetic";

function player(actorId: number, team: string): Player {
  return {
    actor_id: actorId,
    team,
    known_team: true,
    label: `${team}${actorId}`,
    merged_from: [],
    codename: "Hunter",
    agent: "Sova",
    identity: "Sova",
    display: `${team}1 #${actorId}`,
    icon_url: null,
    portrait_url: null,
    role_icon_url: null,
    role: "Initiator",
    abilities: [],
  };
}

const buyMs = (number: number) => ([1, 13, 25].includes(number) ? 45_000 : 30_000);

function round(number: number, startMs: number, winner: string): Round {
  return {
    number,
    index: number - 1,
    start_ms: startMs,
    end_ms: startMs + 60_000,
    duration_ms: 60_000,
    buy_phase_ms: buyMs(number),
    action_start_ms: startMs + buyMs(number),
    winner,
    reason: winner === "?" ? "undetermined" : "wipe",
    decided: winner !== "?",
  };
}

const REPLAY: Replay = {
  id: "id",
  source: "Demos/x.vrf",
  match_id: "match-1",
  build: "++Ares-Core+release-12.10",
  recorded_utc: "",
  length_ms: 300_000,
  side_swap_ms: 180_000,
  map_path: "/Game/Maps/Triad/Triad",
  map_name: "Haven",
  map_name_source: "",
  map_key: "Haven",
  players: [player(10, "A"), player(20, "B")],
  rounds: [
    round(1, 0, "A"),
    round(2, 60_000, "B"),
    round(3, 120_000, "?"),
    round(4, 180_000, "A"),
  ],
  kills: [{ t_ms: 30_000, killer: 10, victim: 20, round_no: 1, is_suicide: false }],
  ultimates: [],
  spike: [],
  loadouts: [],
  ability_casts: [],
  event_times: [30_000],
  score: [1, 1],
  has_positions: false,
  has_abilities: false,
  positions_available: true,
  positions_note: "",
  position_source: "",
  catalog_source: "",
  notes: [],
  catalog_notes: [],
};

const MODEL: ReplayModel = {
  replay: REPLAY,
  positions: new Map(),
  abilityTracks: new Map(),
};

describe("determinism", () => {
  it("gives the same answer twice for the same instant", () => {
    const snap = stateAt(MODEL, 20_000);
    expect(vitalsAt(MODEL, snap, 10)).toEqual(vitalsAt(MODEL, snap, 10));
  });

  it("gives the same answer for a snapshot rebuilt from scratch", () => {
    // The two canvases and the roster each compute their own snapshot; a
    // generator keyed on anything but the ids would have them disagree.
    const first = vitalsAt(MODEL, stateAt(MODEL, 20_000), 10);
    const second = vitalsAt(MODEL, stateAt(MODEL, 20_000), 10);
    expect(first).toEqual(second);
  });

  it("does not give two players the same economy", () => {
    const snap = stateAt(MODEL, 20_000);
    const a = vitalsAt(MODEL, snap, 10);
    const b = vitalsAt(MODEL, snap, 20);
    expect([a.money, a.weapon]).not.toEqual([b.money, b.weapon]);
  });
});

describe("what is read rather than generated", () => {
  it("is zero health exactly when the event stream says the player is dead", () => {
    // The kill at 30s is real; everything about the victim after it follows.
    const before = vitalsAt(MODEL, stateAt(MODEL, 29_000), 20);
    const after = vitalsAt(MODEL, stateAt(MODEL, 31_000), 20);
    expect(before.health).toBeGreaterThan(0);
    expect(after.health).toBe(0);
    expect(after.armor).toBe(0);
    expect(after.weapon).toBeNull();
  });

  it("never reads zero health for somebody who is alive", () => {
    for (let t = 0; t < 240_000; t += 1_000) {
      const snap = stateAt(MODEL, t);
      for (const entry of REPLAY.players) {
        if (snap.alive.has(entry.actor_id)) {
          expect(vitalsAt(MODEL, snap, entry.actor_id).health).toBeGreaterThan(0);
        }
      }
    }
  });

  it("swaps sides at the instant the container recorded", () => {
    expect(sideOf(REPLAY, "A", 0)).toBe("ATK");
    expect(sideOf(REPLAY, "B", 0)).toBe("DEF");
    expect(sideOf(REPLAY, "A", REPLAY.side_swap_ms! - 1)).toBe("ATK");
    expect(sideOf(REPLAY, "A", REPLAY.side_swap_ms!)).toBe("DEF");
    expect(sideOf(REPLAY, "B", REPLAY.side_swap_ms!)).toBe("ATK");
  });

  it("assigns no side where nothing swapped", () => {
    const never: Replay = { ...REPLAY, side_swap_ms: null };
    expect(sideOf(never, "A", never.length_ms)).toBe("ATK");
  });
});

describe("the economy", () => {
  it("never goes negative", () => {
    for (const entry of REPLAY.rounds) {
      const snap = stateAt(MODEL, entry.start_ms + 1_000);
      for (const who of REPLAY.players) {
        expect(vitalsAt(MODEL, snap, who.actor_id).money).toBeGreaterThanOrEqual(0);
      }
    }
  });

  it("starts both halves at the pistol-round floor", () => {
    // Round 4 is the first after the swap, so its bank is the floor again --
    // whatever rounds one to three paid out.
    const first = vitalsAt(MODEL, stateAt(MODEL, 1_000), 10);
    const second = vitalsAt(MODEL, stateAt(MODEL, 181_000), 10);
    expect(first.money).toBeLessThanOrEqual(800);
    expect(second.money).toBeLessThanOrEqual(800);
  });

  it("holds one weapon for a whole round", () => {
    const early = vitalsAt(MODEL, stateAt(MODEL, 1_000), 10).weapon;
    const late = vitalsAt(MODEL, stateAt(MODEL, 50_000), 10).weapon;
    expect(early).toBe(late);
    // And the kill feed asks the same question a different way.
    expect(weaponInRound(REPLAY, 10, 1)).toBe(early);
  });

  it("has nothing to say about an actor that is not in the file", () => {
    expect(weaponInRound(REPLAY, 999, 1)).toBeNull();
    expect(weaponInRound(REPLAY, 10, 99)).toBeNull();
  });
});

describe("weapon art", () => {
  const CATALOGUE = [
    {
      name: "Vandal",
      category: "Rifle",
      cost: 2900,
      icon_url: "/assets/weapons/Vandal/icon.png",
      killfeed_url: "/assets/weapons/Vandal/killfeed.png",
    },
  ];

  it("resolves a name to the catalogue entry", () => {
    expect(weaponArt(CATALOGUE, "Vandal")?.icon_url).toBe(
      "/assets/weapons/Vandal/icon.png",
    );
  });

  it("returns nothing rather than guessing", () => {
    expect(weaponArt(CATALOGUE, "Phantom")).toBeNull();
    expect(weaponArt(CATALOGUE, null)).toBeNull();
    // A checkout with no `assets/weapons/` -- the caller falls back to text.
    expect(weaponArt(undefined, "Vandal")).toBeNull();
  });
});

/*
 * The card's ability row: which half of it is read and which half is invented.
 *
 * This is the property that fails silently.  A generated "used" mark that
 * happened to look plausible is indistinguishable on screen from a decoded
 * one, so what has to be pinned is not the values but the **provenance**:
 * `usedIsReal` true exactly where a real event says so, and the ultimate
 * following `characterUltimateUsed` rather than the generator.
 */
describe("ability charges", () => {
  const ULTED: Replay = {
    ...REPLAY,
    ultimates: [{ t_ms: 10_000, actor_id: 10, round_no: 1 }],
  };
  const WITH_ULT: ReplayModel = { ...MODEL, replay: ULTED };

  it("reads the ultimate from the event rather than generating it", () => {
    const snap = stateAt(WITH_ULT, 20_000);
    const used = slotStateAt(WITH_ULT, snap, 10, "Ultimate");
    const notUsed = slotStateAt(WITH_ULT, snap, 20, "Ultimate");
    expect(used.used).toBe(true);
    expect(used.usedIsReal).toBe(true);
    expect(notUsed.used).toBe(false);
    expect(notUsed.usedIsReal).toBe(true);
  });

  it("says plainly that Q and E are not read", () => {
    // Ability1 and Ability2 are Q and E in an order that varies by agent, and
    // Riot's own archetype letters do not track today's keybinds either -- so
    // which icon a Q cast spent is generated, and must admit it.
    const snap = stateAt(MODEL, 20_000);
    expect(slotStateAt(MODEL, snap, 10, "Ability1").usedIsReal).toBe(false);
    expect(slotStateAt(MODEL, snap, 10, "Ability2").usedIsReal).toBe(false);
  });

  it("never shows a charge count below zero or above what it generated", () => {
    const snap = stateAt(WITH_ULT, 20_000);
    for (const slot of ["Ability1", "Ability2", "Grenade", "Ultimate"]) {
      const state = slotStateAt(WITH_ULT, snap, 10, slot);
      expect(state.charges).toBeGreaterThanOrEqual(1);
      expect(state.left).toBeGreaterThanOrEqual(0);
      expect(state.left).toBeLessThanOrEqual(state.charges);
    }
  });

  it("is deterministic, because a Playwright suite photographs it", () => {
    const snap = stateAt(MODEL, 20_000);
    expect(slotStateAt(MODEL, snap, 10, "Ability1")).toEqual(
      slotStateAt(MODEL, snap, 10, "Ability1"),
    );
  });
});
