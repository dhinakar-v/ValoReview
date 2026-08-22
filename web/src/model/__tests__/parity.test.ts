/**
 * The TypeScript model computes what the Python model computed.
 *
 * `tests/golden/` is written by `scripts/make_golden.py` from
 * `libraries/vrfview/` -- the clock, the track lookup, the snapshot, the
 * transform and the sight cone -- and committed.  `tests/test_golden.py`
 * asserts Python still reproduces those files byte for byte; this asserts the
 * port computes the same values from the same inputs.  So a Python change that
 * would break the browser fails in Python's CI first, and regenerating a
 * fixture is a deliberate act that arrives as a diff.
 *
 * Exact equality, never a tolerance
 * ---------------------------------
 * Both languages are IEEE-754 doubles, the operations are identical, and
 * `JSON.parse` recovers exactly the double `json.dumps` wrote.  A tolerance
 * would hide precisely the class of bug these exist for: a `%` that takes the
 * sign of the dividend instead of the divisor is a couple of degrees wrong most
 * of the time and 180 degrees wrong at the moment somebody crosses north.
 * Never `Math.fround`, and never `toBeCloseTo`.
 *
 * What is *not* asserted is byte equality of the JSON.  `json.dumps` and
 * `JSON.stringify` disagree about how to spell a float -- `1.0` against `1`,
 * `1e-05` against `0.00001` -- while both recover the identical double from
 * either spelling, so bytes across the two would be a test of number formatting
 * rather than of the model.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import type { AbilityCast, Kill, Replay, Round, Transform } from "../../api/types";
import { lerpAngle, mod } from "../angles";
import { PlaybackClock, SPEEDS } from "../clock";
import type { PositionsDoc, ReplayModel } from "../replay";
import { buildModel } from "../replay";
import { blocked, cone, decodeMask, forwardUv, march, rayDirections, uvRadius } from "../sight";
import type { SightSettings } from "../sight";
import type { Snapshot } from "../state";
import { stateAt } from "../state";
import type { Position } from "../track";
import { trackAt } from "../track";
import { applyTransform } from "../transform";

// Read off disk rather than imported. `new URL(..., import.meta.url)` is a
// pattern Vite rewrites into an asset reference, and these fixtures live
// outside `web/` on purpose: they are Python's output, committed beside the
// tests that generate them.
const GOLDEN = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "..",
  "tests",
  "golden",
);

function golden<T>(name: string): T {
  return JSON.parse(readFileSync(join(GOLDEN, name), "utf-8")) as T;
}

const REPLAY = golden<Replay>("replay.json");
const POSITIONS = golden<PositionsDoc>("positions.json");
const MODEL: ReplayModel = buildModel(REPLAY, POSITIONS);

/**
 * One Snapshot as the shape `make_golden.snapshot_doc` writes.
 *
 * It lives here rather than in `../state` for the same reason its counterpart
 * lives in the generator rather than in `vrfserve.wire`: the server never sends
 * a snapshot, the browser recomputes one per frame, and this shape exists only
 * to compare two implementations.  Its home is the thing that does the
 * comparing.
 */
function snapshotDoc(snap: Snapshot) {
  const byActor = (mapping: Map<number, Position>) =>
    [...mapping.keys()].sort((a, b) => a - b).map((actor) => mapping.get(actor)!);
  return {
    t_ms: snap.t_ms,
    round: snap.round === null ? null : snap.round.number,
    alive: [...snap.alive].sort((a, b) => a - b),
    dead_since: [...snap.deadSince.keys()]
      .sort((a, b) => a - b)
      .map((actor) => ({ actor_id: actor, t_ms: snap.deadSince.get(actor)! })),
    recent_kills: snap.recentKills.map(([kill, age]: [Kill, number]) => ({
      t_ms: kill.t_ms,
      killer: kill.killer,
      victim: kill.victim,
      round_no: kill.round_no,
      age,
    })),
    recent_ults: snap.recentUlts.map(([actor, age]) => ({ actor_id: actor, age })),
    round_kills: snap.roundKills.map((kill) => ({
      t_ms: kill.t_ms,
      killer: kill.killer,
      victim: kill.victim,
    })),
    ulted_this_round: [...snap.ultedThisRound].sort((a, b) => a - b),
    spike_state: snap.spikeState,
    spike_since_ms: snap.spikeSinceMs,
    kd: [...snap.kd.keys()]
      .sort((a, b) => a - b)
      .map((actor) => ({
        actor_id: actor,
        kills: snap.kd.get(actor)![0],
        deaths: snap.kd.get(actor)![1],
      })),
    score: snap.score,
    positions: byActor(snap.positions),
    death_positions: byActor(snap.deathPositions),
    round_casts: snap.roundCasts.map((cast: AbilityCast) => ({
      t_ms: cast.t_ms,
      actor_id: cast.actor_id,
      codename: cast.codename,
      slot: cast.slot,
    })),
    ability_positions: byActor(snap.abilityPositions),
  };
}

describe("mod", () => {
  it("takes the sign of the divisor, the way Python's % does", () => {
    // The line the whole file is here for. JavaScript's own % answers -170.
    expect(mod(-350 + 180, 360)).toBe(190);
    expect(mod(-1, 360)).toBe(359);
    expect(mod(361, 360)).toBe(1);
  });

  it("interpolates a heading the short way across zero", () => {
    expect(lerpAngle(350, 10, 0.5)).toBe(0);
    expect(lerpAngle(10, 350, 0.5)).toBe(0);
    expect(lerpAngle(359, 1, 0.5)).toBe(0);
  });
});

describe("trackAt", () => {
  interface TrackCase {
    actor_id: number;
    t_ms: number;
    why: string;
    at: Position | null;
  }
  const fixture = golden<{
    max_interpolate_ms: number;
    max_hold_ms: number;
    cases: TrackCase[];
  }>("track_at.json");

  it("reaches every branch the fixture was written for", () => {
    // The fixture is only worth comparing against if it still contains the
    // refusal: a set of cases that always answers would let a port that always
    // guesses a coordinate pass every one of them.
    expect(fixture.cases.some((entry) => entry.at === null)).toBe(true);
  });

  for (const entry of fixture.cases) {
    it(`${entry.actor_id} at ${entry.t_ms}: ${entry.why}`, () => {
      const got = trackAt(MODEL.positions.get(entry.actor_id), entry.t_ms);
      expect(got).toEqual(entry.at);
    });
  }
});

describe("stateAt", () => {
  const fixture = golden<{
    kill_fade_ms: number;
    ult_fade_ms: number;
    snapshots: Array<ReturnType<typeof snapshotDoc>>;
  }>("snapshots.json");

  it("has enough instants to be worth comparing", () => {
    expect(fixture.snapshots.length).toBeGreaterThanOrEqual(40);
  });

  for (const wanted of fixture.snapshots) {
    it(`matches Python at ${wanted.t_ms} ms`, () => {
      const got = stateAt(MODEL, wanted.t_ms, fixture.kill_fade_ms, fixture.ult_fade_ms);
      expect(snapshotDoc(got)).toEqual(wanted);
    });
  }

  it("clamps past the end rather than refusing", () => {
    const past = stateAt(MODEL, REPLAY.length_ms + 5000);
    expect(past.t_ms).toBe(REPLAY.length_ms);
  });

  it("computes the same snapshot forwards and backwards", () => {
    // The property the from-scratch rule exists for: nothing accumulates, so
    // scrubbing backwards across a round boundary is exactly as correct as
    // playing forward to the same instant.
    const boundary = REPLAY.rounds[1]!.start_ms + 5000;
    const forwards = snapshotDoc(stateAt(MODEL, boundary));
    stateAt(MODEL, REPLAY.length_ms);
    stateAt(MODEL, 0);
    expect(snapshotDoc(stateAt(MODEL, boundary))).toEqual(forwards);
  });
});

describe("applyTransform", () => {
  const fixture = golden<{
    transform: Transform;
    points: Array<{ world_x: number; world_y: number; why: string; uv: [number, number] }>;
    callouts: Array<{ name: string; world_x: number; world_y: number; uv: [number, number] }>;
  }>("transform.json");

  for (const point of [...fixture.points, ...fixture.callouts]) {
    const label = "why" in point ? point.why : point.name;
    it(`${label}`, () => {
      expect(applyTransform(fixture.transform, point.world_x, point.world_y)).toEqual(
        point.uv,
      );
    });
  }
});

describe("sight", () => {
  const fixture = golden<{
    fov_degrees: number;
    ray_step_degrees: number;
    seed_cells: number;
    probe_uu: number;
    mask: { size: number; cells: string; open_fraction: number };
    blocked: Array<{ u: number; v: number; why: string; blocked: boolean }>;
    uv_radius: Array<{ distance_uu: number; radius: number }>;
    forward_uv: Array<{
      world_x: number;
      world_y: number;
      yaw: number;
      why: string;
      forward: [number, number];
    }>;
    cones: Array<{
      origin: [number, number];
      forward: [number, number];
      radius: number;
      why: string;
      rays: Array<[number, number]>;
      polygon: Array<[number, number]>;
    }>;
    smoke_cones: Array<{
      origin: [number, number];
      forward: [number, number];
      radius: number;
      why: string;
      occluders: Array<{ u: number; v: number; radius: number }>;
      rays: Array<[number, number]>;
      polygon: Array<[number, number]>;
    }>;
  }>("cone.json");

  const transform = golden<{ transform: Transform }>("transform.json").transform;
  const mask = decodeMask(fixture.mask.size, fixture.mask.cells);
  const settings: SightSettings = {
    max_range_uu: 0,
    fov_degrees: fixture.fov_degrees,
    ray_step_degrees: fixture.ray_step_degrees,
    seed_cells: fixture.seed_cells,
    probe_uu: fixture.probe_uu,
  };

  it("decodes the mask the server thresholded", () => {
    expect(mask.cells.length).toBe(mask.size * mask.size);
  });

  for (const entry of fixture.blocked) {
    it(`blocked at (${entry.u}, ${entry.v}): ${entry.why}`, () => {
      expect(blocked(mask, entry.u, entry.v)).toBe(entry.blocked);
    });
  }

  for (const entry of fixture.uv_radius) {
    it(`${entry.distance_uu} uu as a fraction of the radar`, () => {
      expect(uvRadius(transform, entry.distance_uu)).toBe(entry.radius);
    });
  }

  /**
   * The one bound in the suite, and the only place one is honest.
   *
   * `atan2`, `cos` and `sin` are specified as approximate in *both* languages:
   * CPython calls the platform libm and V8 ships its own, and they differ in
   * the last bit or two.  Nothing else in this model touches one, so nothing
   * else needs this.  1e-12 is some ten thousand ulps at this magnitude and
   * still catches every failure that actually matters here -- a cone rotated
   * ninety degrees by uv-space trigonometry, a flipped sign, a wrong field of
   * view, a wrong ray step.
   */
  const ULP_BOUND = 1e-12;
  const nearly = (got: number[], want: number[], what: string) => {
    expect(got.length, what).toBe(want.length);
    got.forEach((value, i) => {
      expect(Math.abs(value - want[i]!), `${what}[${i}]`).toBeLessThanOrEqual(ULP_BOUND);
    });
  };

  for (const entry of fixture.forward_uv) {
    it(`heading: ${entry.why}`, () => {
      const got = forwardUv(
        transform,
        entry.world_x,
        entry.world_y,
        entry.yaw,
        fixture.probe_uu,
      );
      nearly([...got], entry.forward, entry.why);
      // And exactly a unit vector, which is the property the probe is for.
      expect(Math.abs(Math.hypot(...got) - 1)).toBeLessThanOrEqual(ULP_BOUND);
    });
  }

  for (const entry of fixture.cones) {
    it(`cone: ${entry.why}`, () => {
      const got = cone(mask, entry.origin, entry.forward, entry.radius, settings);
      // The shape is exact: how many rays, and whether there is a cone at all.
      expect(got.length).toBe(entry.polygon.length);
      got.forEach((point, i) => nearly([...point], entry.polygon[i]!, `${entry.why}[${i}]`));
    });

    it(`cone, marched along Python's own rays: ${entry.why}`, () => {
      // Handed the directions Python used, every remaining step is plain
      // arithmetic -- multiply, add, floor, compare -- so this is exact, and
      // it is what actually pins the occlusion: which cell stopped which ray.
      expect(rayDirections(entry.forward, settings).length).toBe(entry.rays.length);
      if (entry.polygon.length === 0) {
        // A cone with no radius still has rays; it simply draws none of them.
        return;
      }
      entry.rays.forEach((ray, i) => {
        expect(march(mask, entry.origin, ray, entry.radius, settings.seed_cells)).toEqual(
          entry.polygon[i + 1],
        );
      });
    });
  }

  for (const entry of fixture.smoke_cones) {
    it(`smoke cone: ${entry.why}`, () => {
      const got = cone(
        mask,
        entry.origin,
        entry.forward,
        entry.radius,
        settings,
        entry.occluders,
      );
      expect(got.length).toBe(entry.polygon.length);
      got.forEach((point, i) => nearly([...point], entry.polygon[i]!, `${entry.why}[${i}]`));
    });

    it(`smoke cone marches Python's own rays exactly: ${entry.why}`, () => {
      // The same split the plain cones make. A direction comes out of atan2
      // and is compared within a bound; everything a direction is then put
      // through -- including the circle test, which is multiply and compare
      // and nothing else -- is compared to the bit.
      entry.rays.forEach((ray, i) => {
        expect(
          march(
            mask,
            entry.origin,
            ray,
            entry.radius,
            settings.seed_cells,
            entry.occluders,
          ),
        ).toEqual(entry.polygon[i + 1]);
      });
    });
  }

  it("takes no occluders as the same answer as before there were any", () => {
    // The default argument has to be inert, or every existing call site --
    // and every one of the six fixtures above -- quietly changed meaning.
    const entry = fixture.cones.find((c) => c.polygon.length > 0)!;
    expect(cone(mask, entry.origin, entry.forward, entry.radius, settings, [])).toEqual(
      cone(mask, entry.origin, entry.forward, entry.radius, settings),
    );
  });

  it("draws nothing rather than a circle when there is no heading", () => {
    expect(cone(mask, [0.5, 0.5], [0, 0], 0.5, settings)).toEqual([]);
  });
});

describe("PlaybackClock", () => {
  interface Step {
    op: string;
    arg: number | null;
    why: string;
    moved: number | null;
    t_ms: number;
    playing: boolean;
    speed: number;
    at_end: boolean;
  }
  const fixture = golden<{ length_ms: number; speeds: number[]; steps: Step[] }>(
    "clock.json",
  );

  it("offers the same speeds", () => {
    expect([...SPEEDS]).toEqual(fixture.speeds);
  });

  it("replays the whole scripted session identically", () => {
    const clock = new PlaybackClock(fixture.length_ms);
    for (const step of fixture.steps) {
      let moved: number | null = null;
      switch (step.op) {
        case "tick":
          moved = clock.tick(step.arg!);
          break;
        case "seek":
          clock.seek(step.arg!);
          break;
        case "nudge":
          clock.nudge(step.arg!);
          break;
        case "set_speed":
          clock.setSpeed(step.arg!);
          break;
        case "play":
          clock.play();
          break;
        case "pause":
          clock.pause();
          break;
        case "toggle":
          clock.toggle();
          break;
        case "state":
          break;
        default:
          throw new Error(`unknown op in the fixture: ${step.op}`);
      }
      expect({
        op: step.op,
        moved,
        t_ms: clock.tMs,
        playing: clock.playing,
        speed: clock.speed,
        at_end: clock.atEnd,
      }).toEqual({
        op: step.op,
        moved: step.moved,
        t_ms: step.t_ms,
        playing: step.playing,
        speed: step.speed,
        at_end: step.at_end,
      });
    }
  });
});

describe("the replay document", () => {
  it("carries a cast that landed somewhere and one that did not", () => {
    // The measurement in Plan 3 part D: a smoke has a coordinate now, and a
    // cast whose pawn has a track deliberately does not -- the track outranks
    // the spawn point.
    const landed = REPLAY.ability_casts.filter((cast) => cast.landed !== null);
    const tracked = REPLAY.ability_casts.filter((cast) => cast.pawns.length > 0);
    expect(landed.length).toBeGreaterThan(0);
    expect(tracked.length).toBeGreaterThan(0);
    expect(tracked.every((cast) => cast.landed === null)).toBe(true);
  });

  it("marks a smoke where it came to rest and not where it was thrown", () => {
    const smoke = REPLAY.ability_casts.find(
      (cast: AbilityCast) => cast.landed !== null && cast.placements.length > 1,
    );
    expect(smoke).toBeDefined();
    const chosen = smoke!.landed!;
    const others = smoke!.placements.filter((p) => p.actor_id !== chosen.actor_id);
    expect(others.length).toBeGreaterThan(0);
    expect(others.some((p) => Math.hypot(p.x - chosen.x, p.y - chosen.y) > 1000)).toBe(
      true,
    );
  });

  it("orders rounds so a boundary kill belongs to the round it opens", () => {
    const starts = new Map(REPLAY.rounds.map((r: Round) => [r.start_ms, r.number]));
    const boundary = REPLAY.kills.find((kill: Kill) => starts.has(kill.t_ms));
    expect(boundary).toBeDefined();
    const snap = stateAt(MODEL, boundary!.t_ms);
    expect(snap.round?.number).toBe(starts.get(boundary!.t_ms));
  });
});
