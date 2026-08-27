/**
 * What a mark on the rail says when you point at it.
 *
 * The rail is a canvas and jsdom gives a canvas no 2D context at all, so the
 * ink is not assertable here and is not the point: `draw` returns at the null
 * context and every mark this file cares about is DOM.  That is one of the
 * reasons the kills are `<span>`s rather than paint -- a skull drawn into the
 * canvas would be invisible to every test that is not a screenshot.
 *
 * Four things, each of which fails quietly if it regresses:
 *
 *   * a tooltip names **who** and **whom**, and says it in round time, which
 *     counts down;
 *   * marks that share a moment come up **together**, because a flurry of
 *     utility is exactly where one tooltip per pixel would be useless;
 *   * it clears when the pointer leaves, or a Playwright screenshot taken with
 *     the pointer parked somewhere else picks up thousands of stray pixels;
 *   * **a switched-off layer raises nothing.**  That last one is the reason
 *     this file exists.  The canvas gated on `layers` and a hover that gated on
 *     nothing would have gone on tooltipping kills with KILLS switched off --
 *     nothing would have thrown, nothing would have looked wrong in a
 *     screenshot, and the switch would simply have been half-connected.
 *
 * There is not one `data-testid` in this repository, so everything below is
 * found by text or by the class the stylesheet already uses.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Replay } from "../api/types";
import { PlaybackClock } from "../model/clock";
import { Transport } from "./Transport";
import { DEFAULT_LAYERS, usePlayback } from "./playback";

/** A round one minute long, starting at zero, so a pixel is an easy fraction. */
const ROUND = {
  number: 1,
  index: 0,
  start_ms: 0,
  end_ms: 60_000,
  duration_ms: 60_000,
  // Round one, so a 45s buy phase: the round-start marker sits three quarters
  // along this rail, and nothing else is put there.
  buy_phase_ms: 45_000,
  action_start_ms: 45_000,
  winner: "A",
  reason: "wipe",
  decided: true,
};

const REPLAY: Replay = {
  id: "abc123",
  source: "Demos/match.vrf",
  match_id: "m-1",
  build: "++Ares-Core+release-12.10",
  recorded_utc: "2026-08-21T18:02:00Z",
  length_ms: 60_000,
  side_swap_ms: null,
  map_path: "/Game/Maps/Triad/Triad",
  map_name: "Haven",
  map_name_source: "built-in table",
  map_key: "Haven",
  players: [
    player(1, "A", "Sova", "Hunter"),
    player(2, "B", "Jett", "Rift"),
  ],
  rounds: [ROUND],
  // 15s in, a quarter of the way along the rail.
  kills: [{ t_ms: 15_000, killer: 1, victim: 2, round_no: 1, is_suicide: false }],
  // 52s in, and deliberately not 45s: that is where the round-start marker
  // lands, and an ultimate sharing the millisecond would make every assertion
  // about either mark an assertion about both.
  ultimates: [{ t_ms: 52_000, actor_id: 2, round_no: 1 }],
  // 30s in, halfway -- with two casts a millisecond apart beside it.
  spike: [{ t_ms: 30_000, kind: "planted", round_no: 1, x: null, y: null, z: null }],
  loadouts: [],
  ability_casts: [cast(30_000, 1, "Hunter", "Sova", "Owl Drone"), cast(30_001, 2, "Rift", "Jett", "Cloudburst")],
  // 45s is the round-start marker, which is what a round contributes now.
  event_times: [15_000, 30_000, 45_000, 52_000],
  score: [1, 0],
  has_positions: false,
  has_abilities: true,
  positions_available: true,
  positions_note: "positions decode on this build",
  position_source: "positions not decoded yet",
  catalog_source: "",
  notes: [],
  catalog_notes: [],
};

function player(actorId: number, team: string, agent: string, codename: string) {
  return {
    actor_id: actorId,
    team,
    known_team: true,
    label: `${team}1`,
    merged_from: [],
    codename,
    agent,
    identity: agent,
    display: agent,
    icon_url: null,
    portrait_url: null,
    role_icon_url: null,
    role: "",
    abilities: [],
  };
}

function cast(tMs: number, caster: number, codename: string, agent: string, name: string) {
  return {
    t_ms: tMs,
    round_no: 1,
    // Deliberately not a player's id: a cast's `actor_id` is the ability
    // actor's, which is the trap `player_actor_id` exists to close.
    actor_id: 900 + caster,
    codename,
    agent,
    identity: agent,
    slot: "Q",
    internal_name: name,
    published_name: null,
    icon_url: null,
    spawns: 1,
    kinds: ["Pawn"],
    pawns: [],
    has_track: false,
    travel_uu: null,
    travel_note: null,
    range_uu: null,
    range_source: null,
    player_actor_id: caster,
    placements: [],
    landed: null,
    smoke_radius_uu: null,
    smoke_duration_ms: null,
    smoke_source: null,
  };
}

const WIDTH = 600;

function show() {
  const view = render(
    <Transport
      replay={REPLAY}
      clock={new PlaybackClock(REPLAY.length_ms, 1)}
      weapons={undefined}
      layers={{ sight: false, callouts: false }}
    />,
  );
  const rail = view.container.querySelector(".rail") as HTMLElement;
  /*
    jsdom lays nothing out, so every box is zero and every mark would land on
    x = 0 together.  The rail measures itself in the handler on purpose -- so a
    hit agrees with where a skull was placed rather than with a stale width --
    which means one stub here is the whole of the fixture.
  */
  rail.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: WIDTH, height: 40, right: WIDTH, bottom: 40, x: 0, y: 0 }) as DOMRect;
  return rail;
}

/** Point at a moment, the way the rail maps one. */
function pointAt(rail: HTMLElement, tMs: number, offsetPx = 0) {
  const x = (tMs / REPLAY.length_ms) * WIDTH + offsetPx;
  fireEvent.mouseMove(rail, { clientX: x, clientY: 20, buttons: 0 });
}

function tip() {
  return document.querySelector(".rail-tip");
}

describe("the rail's marks", () => {
  beforeEach(() => {
    usePlayback.setState({ layers: { ...DEFAULT_LAYERS }, roundNo: 1, tMs: 0 });
  });
  afterEach(cleanup);

  it("draws one skull per kill, in the killer's side", () => {
    const rail = show();
    const skulls = rail.querySelectorAll(".rail-skull");
    expect(skulls.length).toBe(REPLAY.kills.length);
    // Sova is on team A with no swap recorded, so the killer attacked.
    expect(skulls[0]!.className).toContain("side-atk");
    // Placed as a percentage of the rail, which is the same linear map the
    // canvas applies -- 15s of 60s is a quarter along.
    expect((skulls[0] as HTMLElement).style.left).toBe("25%");
  });

  it("says who killed whom, in time remaining", () => {
    const rail = show();
    pointAt(rail, 15_000);
    const raised = tip();
    expect(raised).not.toBeNull();
    expect(raised!.textContent).toContain("Sova");
    expect(raised!.textContent).toContain("killed");
    expect(raised!.textContent).toContain("Jett");
    // 15s into a 60s round leaves 45 -- a countdown, not an elapsed clock.
    expect(raised!.textContent).toContain("0:45");
  });

  it("names the caster and the ability, not the ability actor", () => {
    const rail = show();
    pointAt(rail, 30_000);
    // `identity` comes from the cast; a row that had resolved `actor_id`
    // instead would read `#901`, which is the fault this join closed.
    expect(tip()!.textContent).toContain("Owl Drone");
    expect(tip()!.textContent).not.toContain("#901");
  });

  it("raises every mark that shares a moment", () => {
    const rail = show();
    pointAt(rail, 30_000);
    const rows = tip()!.querySelectorAll(".ev-row");
    // The plant and both casts: one millisecond apart is one pixel apart at
    // any rail width anybody has.
    expect(rows.length).toBe(3);
    expect(tip()!.textContent).toContain("Spike planted");
    expect(tip()!.textContent).toContain("Cloudburst");
  });

  it("says nothing where there is no mark", () => {
    const rail = show();
    pointAt(rail, 5_000);
    expect(tip()).toBeNull();
  });

  it("clears when the pointer leaves", () => {
    const rail = show();
    pointAt(rail, 15_000);
    expect(tip()).not.toBeNull();
    fireEvent.mouseLeave(rail);
    expect(tip()).toBeNull();
  });

  it("clears when a scrub starts", () => {
    const rail = show();
    pointAt(rail, 15_000);
    fireEvent.mouseDown(rail, { clientX: 150, clientY: 20, buttons: 1 });
    expect(tip()).toBeNull();
  });

  /*
    The one that would have shipped.

    A layer switch has to reach the hover as well as the ink, or it is
    half-connected in a way no screenshot and no type error can show.
  */
  it("raises nothing for a layer that is switched off", () => {
    usePlayback.setState({ layers: { ...DEFAULT_LAYERS, kills: false } });
    const rail = show();
    expect(rail.querySelectorAll(".rail-skull").length).toBe(0);
    pointAt(rail, 15_000);
    expect(tip()).toBeNull();
    // And the marks that are still switched on are untouched.
    pointAt(rail, 52_000);
    expect(tip()!.textContent).toContain("ultimate");
  });

  /*
    The round's own beginning.

    `start_ms` is when `roundStarted` fired, which is the start of the buy
    phase -- thirty or forty-five seconds of ten people stood behind a barrier.
    The mark is at the barrier drop, and there is deliberately no mark at
    `start_ms`: a rail with a tick at both would be claiming two beginnings.
  */
  it("marks where the round starts and says so", () => {
    const rail = show();
    pointAt(rail, 45_000);
    expect(tip()!.textContent).toContain("Round starts");
  });

  it("puts no mark on the buy phase's own start", () => {
    const rail = show();
    pointAt(rail, 0);
    expect(tip()).toBeNull();
  });

  /*
    The marker has no layer switch, which is the whole reason to assert it here:
    it is the round's structure rather than an overlay on it, so turning every
    switch off must leave it drawn.  `LayersMenu.test` proves the other half --
    that `LAYER_FOR` names no switch for it.
  */
  it("survives every layer being switched off", () => {
    usePlayback.setState({
      layers: {
        ...DEFAULT_LAYERS,
        kills: false,
        casts: false,
        ultimates: false,
        spike: false,
      },
    });
    const rail = show();
    pointAt(rail, 45_000);
    expect(tip()!.textContent).toContain("Round starts");
  });

  it("keeps the clock readout to two clocks and nothing else", () => {
    show();
    // Pinned by `e2e/minimap.spec.ts`, which asserts this text exactly.
    expect(screen.getByText("0:00 / 1:00")).toBeTruthy();
  });
});
