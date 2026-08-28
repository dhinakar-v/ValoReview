/**
 * What an ability is doing at an instant, and the four times it must say nothing.
 *
 * Every failure this pins is silent.  A phase boundary that is off by one
 * draws a ring for an ability that has expired, or hides one that is still
 * standing; a default duration makes every ability disappear on the same
 * schedule whether or not anybody published one; a flight drawn before its
 * projectile left the hand puts a mark on ground the thing has not reached.
 * None of them throws, and a screenshot of any of them looks like a map with
 * ability markers on it.
 *
 * The last test here is the one that is not about drawing at all: that this
 * module never reports a *player*.  It is the machine-checkable form of the
 * rule the module docstring states, and it exists because the tempting next
 * feature -- ringing everybody inside a flash -- is a confident sentence about
 * named people resting on none of the evidence it appears to.
 */

import { describe, expect, it } from "vitest";

import type { AbilityCast, Flight, Placement, Replay } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { Snapshot } from "../model/state";
import { EXPIRE_MS, castsAt, lifeOf, phaseOf } from "./castlayer";

function placement(over: Partial<Placement> = {}): Placement {
  return {
    t_ms: 10_000,
    actor_id: 900,
    kind: "GameObject",
    name: "Smoke",
    display: "Smoke",
    x: 1000,
    y: 2000,
    z: 0,
    ...over,
  };
}

function flight(over: Partial<Flight> = {}): Flight {
  return {
    start_ms: 9_000,
    end_ms: 10_000,
    duration_ms: 1_000,
    from_actor_id: 899,
    from_x: 0,
    from_y: 0,
    from_z: 0,
    to_actor_id: 900,
    to_x: 1000,
    to_y: 2000,
    to_z: 0,
    ...over,
  };
}

/** One cast, with whatever the test needs published about it. */
function cast(over: Partial<AbilityCast> = {}): AbilityCast {
  return {
    t_ms: 9_000,
    round_no: 1,
    actor_id: 800,
    codename: "Wraith",
    agent: "Omen",
    identity: "Omen",
    slot: "C",
    internal_name: "Smoke",
    published_name: null,
    icon_url: null,
    spawns: 2,
    kinds: ["Projectile", "GameObject"],
    pawns: [],
    has_track: false,
    travel_uu: null,
    travel_note: null,
    range_uu: 410,
    range_source: "a page",
    player_actor_id: 1,
    placements: [placement()],
    landed: placement(),
    smoke_radius_uu: null,
    smoke_duration_ms: null,
    smoke_source: null,
    mechanics: null,
    flights: [],
    walls: [],
    ...over,
  };
}

const MECHANICS = {
  ability: "Dark Cover",
  keybind: "E",
  radius_uu: 410,
  radius_source: "a page",
  detection_radius_uu: null,
  detection_radius_source: null,
  windup_ms: null,
  windup_source: null,
  activation_delay_ms: null,
  activation_delay_source: null,
  duration_ms: 15_000,
  duration_source: "a page",
  cooldown_ms: null,
  cooldown_source: null,
  charges: null,
  charges_source: null,
  deployable_hp: null,
  deployable_hp_source: null,
  wall: null,
  wall_source: null,
  wall_length_uu: null,
  wall_length_source: null,
  persists: false,
  destroyed_on_caster_death: false,
  sees: false,
  blocks_sight: true,
};

function model(): ReplayModel {
  return {
    replay: {
      players: [{ actor_id: 1, team: "A" }],
      side_swap_ms: null,
    } as unknown as Replay,
  } as unknown as ReplayModel;
}

function snapshot(tMs: number, casts: AbilityCast[], dead?: number[]): Snapshot {
  const alive = new Set([1]);
  for (const actorId of dead ?? []) {
    alive.delete(actorId);
  }
  return { t_ms: tMs, roundCasts: casts, alive } as unknown as Snapshot;
}

describe("the flight, whose clock is decoded", () => {
  const thrown = cast({ flights: [flight()] });

  it("draws nothing before the projectile leaves the hand", () => {
    // Not merely early: a mark at the landing point during the flight is a
    // thing shown on ground it has not reached yet.
    expect(phaseOf(thrown, placement(), 8_999)).toBeNull();
  });

  it("is in the air across its own decoded interval", () => {
    const midway = phaseOf(thrown, placement(), 9_500);
    expect(midway?.kind).toBe("flight");
    expect(midway).toMatchObject({ progress: 0.5 });
  });

  it("moves in a straight line and nowhere else", () => {
    // The one invention in this module, pinned so a later "nicer" arc has to
    // argue with a test: halfway through the flight the mark is exactly
    // halfway between two decoded coordinates.
    const midway = phaseOf(thrown, placement(), 9_500);
    expect(midway).toMatchObject({ at: { x: 500, y: 1000 } });
  });

  it("has landed by the instant its landing channel opened", () => {
    // Half-open at the far end: at `end_ms` the thing is on the ground, which
    // is the same millisecond `place.t_ms` names.
    expect(phaseOf(thrown, placement(), 10_000)?.kind).not.toBe("flight");
  });

  it("is not drawn at all for a cast with no paired throw", () => {
    // Most casts. `flights` refuses to pair unless the counts match, and a
    // refusal must read as "no line" rather than as a line to somewhere.
    expect(phaseOf(cast(), placement(), 9_500)).toBeNull();
    expect(phaseOf(cast(), placement(), 10_500)?.kind).toBe("placed");
  });
});

describe("the arming delay, which is looked up", () => {
  const armed = cast({
    mechanics: { ...MECHANICS, activation_delay_ms: 2_000 },
  });

  it("arms from the instant it landed, not from the cast", () => {
    expect(phaseOf(armed, placement(), 10_000)?.kind).toBe("arming");
    expect(phaseOf(armed, placement(), 11_999)?.kind).toBe("arming");
  });

  it("is active the millisecond the arm time is up", () => {
    expect(phaseOf(armed, placement(), 12_000)?.kind).toBe("active");
  });

  it("is skipped entirely where no arm time is published", () => {
    // Not defaulted to some small number: an ability nobody says arms slowly
    // is drawn as doing its job the moment it lands.
    expect(phaseOf(cast({ mechanics: MECHANICS }), placement(), 10_000)?.kind).toBe("active");
  });

  it("pushes the expiry out by exactly the arm time", () => {
    // The lifetime runs from armed, not from landed, so a slow-arming trap
    // stands for its full published life.
    expect(phaseOf(armed, placement(), 26_999)).not.toBeNull();
    expect(phaseOf(armed, placement(), 27_000)).toBeNull();
  });
});

describe("the lifetime, and the refusal to invent one", () => {
  const standing = cast({ mechanics: MECHANICS });

  it("is active from the moment it lands", () => {
    expect(phaseOf(standing, placement(), 10_000)?.kind).toBe("active");
  });

  it("fades over the last EXPIRE_MS and not before", () => {
    expect(phaseOf(standing, placement(), 24_399)?.kind).toBe("active");
    expect(phaseOf(standing, placement(), 24_400)?.kind).toBe("expiring");
  });

  it("is gone the instant its published lifetime is up", () => {
    expect(phaseOf(standing, placement(), 24_999)).not.toBeNull();
    expect(phaseOf(standing, placement(), 25_000)).toBeNull();
  });

  it("fades to nothing rather than snapping", () => {
    const nearly = phaseOf(standing, placement(), 24_999);
    expect(nearly).toMatchObject({ kind: "expiring" });
    expect((nearly as { alpha: number }).alpha).toBeLessThan(0.05);
  });

  it("stands for ever where nobody published a lifetime", () => {
    /*
      The refusal that matters most. Sixteen agents of twenty-nine are in the
      table and most of their abilities have no published duration, so the
      ordinary answer is "no clock" -- and that has to keep today's static
      mark for the rest of the round rather than borrow another ability's
      number and disappear on somebody else's schedule.
    */
    expect(lifeOf(cast())).toBeNull();
    expect(phaseOf(cast(), placement(), 10_000)?.kind).toBe("placed");
    expect(phaseOf(cast(), placement(), 999_999)?.kind).toBe("placed");
  });
});

describe("which casts are drawn at all", () => {
  it("skips a cast whose pawn has a real track", () => {
    /*
      A drone and a Boom Bot move, and their own samples say where they are at
      each instant. A ring at the spawn point beside a moving marker is a
      second, staler answer to the same question -- the same rule
      `abilities._placements` keeps in Python.
    */
    const drone = cast({ pawns: [42], has_track: true, mechanics: MECHANICS });
    expect(castsAt(model(), snapshot(10_000, [drone]))).toHaveLength(0);
  });

  it("skips a throw origin, which is not a place anything stands", () => {
    // A `Projectile_` opens inside the caster's own capsule.
    const thrown = cast({ placements: [placement({ kind: "Projectile" })] });
    expect(castsAt(model(), snapshot(10_000, [thrown]))).toHaveLength(0);
  });

  it("draws each of several placements on its own clock", () => {
    /*
      One cast is one agent, one slot, one round, so Brimstone dropping three
      smokes is a single `AbilityCast`. They land at different instants and
      must expire at different instants -- ageing them all from `cast.t_ms`
      was the bug this whole field was added to fix.
    */
    const several = cast({
      mechanics: MECHANICS,
      placements: [
        placement({ actor_id: 900, t_ms: 10_000 }),
        placement({ actor_id: 901, t_ms: 20_000 }),
      ],
    });
    const later = castsAt(model(), snapshot(26_000, [several]));
    expect(later).toHaveLength(1);
    expect(later[0]!.place?.actor_id).toBe(901);
  });

  it("gives no side where the caster could not be attributed", () => {
    // `abilities.attribute` refuses a codename two players share, and a lane
    // or a colour would be a claim about which side cast it.
    const orphan = cast({ player_actor_id: null, mechanics: MECHANICS });
    expect(castsAt(model(), snapshot(10_000, [orphan]))[0]!.side).toBeNull();
  });
});

describe("what this module must never say", () => {
  it("reports no player anywhere in its answer", () => {
    /*
      The rule, made checkable. Nothing here may take a radius and a set of
      positions and report who was inside: position is 10 Hz and interpolated,
      the sight approximation already wrongly closes a third of real
      sightlines, and whether somebody was facing a flash is not in the file
      at all. A published debuff is a property of the ability and is shown as
      one.

      Checked by walking the returned structure rather than by reading the
      source, so a field added later is caught whatever it is called.
    */
    const drawn = castsAt(model(), snapshot(10_000, [cast({ mechanics: MECHANICS })]));
    expect(drawn).toHaveLength(1);
    const keys = Object.keys(drawn[0]!);
    for (const banned of ["players", "affected", "caught", "hit", "blinded"]) {
      expect(keys).not.toContain(banned);
    }
    // The one actor id it carries is the *caster's own cast*, never a target.
    expect(drawn[0]!.cast.player_actor_id).toBe(1);
  });

  it("carries a trigger range separately from an area of effect", () => {
    /*
      Chamber's Trademark searches ten metres and slows six. One ring for both
      would merge a question about who it notices with a claim about what it
      does to them.
    */
    const trap = cast({
      mechanics: { ...MECHANICS, radius_uu: 600, detection_radius_uu: 1000 },
    });
    const drawn = castsAt(model(), snapshot(10_000, [trap]))[0]!;
    expect(drawn.radiusUu).toBe(600);
    expect(drawn.detectionUu).toBe(1000);
  });

  it("carries null rather than a default where nothing is published", () => {
    const drawn = castsAt(model(), snapshot(10_000, [cast()]))[0]!;
    expect(drawn.radiusUu).toBeNull();
    expect(drawn.detectionUu).toBeNull();
  });
});

describe("EXPIRE_MS", () => {
  it("is short enough to sit inside the shortest published lifetime", () => {
    // Jett's Cloudburst is 2.5 s, the shortest in the table. A fade longer
    // than the ability would mean a smoke that was expiring before it existed.
    expect(EXPIRE_MS).toBeLessThan(2_500);
  });
});

describe("the mark going away, which is what a reader actually asked for", () => {
  /*
    `MinimapCanvas` draws the static diamond only while `phaseOf` still returns
    something, so these three cases are the whole of that behaviour. Without
    them a placed ability appears when it is cast and stays until the round
    ends: a smoke that went out twenty seconds ago sits beside one that has
    just landed, and by the end of a round every utility anybody used is on the
    map at once, claiming a dozen things are standing that are not.
  */
  const smoke = cast({ mechanics: MECHANICS, flights: [flight()] });

  it("is not on the map before the throw leaves the hand", () => {
    expect(phaseOf(smoke, placement(), 8_999)).toBeNull();
  });

  it("is on the map while it stands", () => {
    expect(phaseOf(smoke, placement(), 20_000)).not.toBeNull();
  });

  it("is off the map once its published lifetime is over", () => {
    // 10,000 landed + 15,000 published = 25,000.
    expect(phaseOf(smoke, placement(), 25_001)).toBeNull();
  });
});

describe("a moment, a thing that stands, and something nobody has written down", () => {
  /*
    Three outcomes from two published facts, and the split is the whole reason
    `persists` exists as a field separate from `duration_ms`. Conflating them
    got both ends wrong at once: read as a lifetime, Trademark's 4-second slow
    would sweep the trap off the floor four seconds after it was placed, and
    the Turret's absent duration left a flash hanging on the map all round.
  */
  const flash = cast({
    codename: "Breach",
    slot: "Q",
    mechanics: { ...MECHANICS, ability: "Flashpoint", duration_ms: null, radius_uu: null },
  });
  const turret = cast({
    codename: "Killjoy",
    slot: "E",
    mechanics: { ...MECHANICS, ability: "Turret", duration_ms: null, persists: true },
  });

  it("lets a flash go, because nothing was left standing", () => {
    expect(phaseOf(flash, placement(), 10_000)?.kind).toBe("active");
    expect(phaseOf(flash, placement(), 11_999)).not.toBeNull();
    expect(phaseOf(flash, placement(), 12_001)).toBeNull();
  });

  it("keeps a turret, because it stands until it is shot", () => {
    // Its `duration_ms` is null here, but even a published one would be the
    // effect rather than the lifetime and must not end the mark.
    expect(phaseOf(turret, placement(), 999_999)?.kind).toBe("placed");
  });

  it("keeps a trap whose only published duration is its debuff", () => {
    const trademark = cast({
      mechanics: {
        ...MECHANICS,
        ability: "Trademark",
        duration_ms: 4_000,
        persists: true,
      },
    });
    // Four seconds is the slow it applies, not how long it waits on the floor.
    expect(phaseOf(trademark, placement(), 30_000)?.kind).toBe("placed");
  });

  it("keeps an ability the table says nothing about at all", () => {
    /*
      The rule the whole table keeps: no figure, change nothing. Thirteen
      agents of twenty-nine are unnamed, and sweeping their marks off after two
      seconds would be a claim made from an absence rather than from evidence.
      Only a *named* ability with no lifetime and no persistence is a moment,
      because that combination is positive knowledge.
    */
    expect(phaseOf(cast({ mechanics: null }), placement(), 999_999)?.kind).toBe("placed");
  });
});

describe("a wall", () => {
  const segments = {
    t_ms: 10_000,
    segments: 4,
    x1: 0,
    y1: 0,
    x2: 1040,
    y2: 0,
    length_uu: 1040,
  };

  it("is drawn from its own decoded ends where it has them", () => {
    const barrier = cast({
      mechanics: { ...MECHANICS, wall: "segments", duration_ms: 40_000 },
      walls: [segments],
      player_actor_id: 1,
    });
    const drawn = castsAt(model(), snapshot(12_000, [barrier]));
    const wall = drawn.find((entry) => entry.phase.kind === "wall");
    expect(wall?.phase).toMatchObject({
      kind: "wall",
      from: { x: 0, y: 0 },
      to: { x: 1040, y: 0 },
    });
  });

  it("goes when its published lifetime is up", () => {
    const barrier = cast({
      mechanics: { ...MECHANICS, wall: "segments", duration_ms: 40_000 },
      walls: [segments],
      player_actor_id: 1,
    });
    const drawn = castsAt(model(), snapshot(51_000, [barrier]));
    expect(drawn.some((entry) => entry.phase.kind === "wall")).toBe(false);
  });

  it("is not drawn for an ability whose placements are not a wall", () => {
    // Every wall but Sage's. Phoenix's Blaze and Harbor's High Tide follow a
    // steerable missile and have no length to look up; Vyse's Shear is placed
    // on vertical terrain rather than along the way she faced. None of them
    // states geometry, so none of them draws any.
    const blaze = cast({
      mechanics: { ...MECHANICS, wall: null },
      player_actor_id: 1,
      placements: [placement()],
      walls: [segments],
    });
    const drawn = castsAt(model(), snapshot(10_000, [blaze]));
    expect(drawn.some((entry) => entry.phase.kind === "wall")).toBe(false);
  });
});

describe("a thing that dies with its caster", () => {
  const trap = cast({
    player_actor_id: 1,
    mechanics: {
      ...MECHANICS,
      duration_ms: null,
      persists: true,
      destroyed_on_caster_death: true,
    },
  });

  it("stands while its owner is alive", () => {
    expect(castsAt(model(), snapshot(20_000, [trap]))).toHaveLength(1);
  });

  it("goes the moment its owner is dead", () => {
    expect(castsAt(model(), snapshot(20_000, [trap], [1]))).toHaveLength(0);
  });

  it("stands for an ability that does not carry the rule", () => {
    // Killjoy's, and this is the assertion that matters: her utility is
    // disabled at range and destroyed by damage, never by her death, so a
    // future reading of `persists` as this flag has to argue with a test.
    const turret = cast({
      player_actor_id: 1,
      mechanics: { ...MECHANICS, duration_ms: null, persists: true },
    });
    expect(castsAt(model(), snapshot(20_000, [turret], [1]))).toHaveLength(1);
  });

  it("stands where nothing can say whose it is", () => {
    const orphan = cast({
      player_actor_id: null,
      mechanics: {
        ...MECHANICS,
        duration_ms: null,
        persists: true,
        destroyed_on_caster_death: true,
      },
    });
    expect(castsAt(model(), snapshot(20_000, [orphan], [1]))).toHaveLength(1);
  });
});
