/**
 * The things the map stage must not quietly stop saying.
 *
 * Every one of them fails *silently* if it regresses.  A missing sentence
 * leaves a plausible-looking panel, and a DECODE button that can only refuse
 * looks exactly like one that works until it is pressed.  So each is asserted
 * by name rather than trusted.
 *
 *   * **Where a map cannot be drawn there are words, never a drawing.**  A
 *     diagram in the place a map goes reads as a map however it is captioned,
 *     which is why the desktop schematic was deleted rather than relabelled.
 *   * **A DECODE button appears only where one could work**, and the two ways
 *     it cannot -- a build with no payload transform, and a machine with no
 *     decoder -- get different sentences, because they are fixed by different
 *     things.
 *   * **Every layer switch is offered**, and one that cannot be used here says
 *     why in a node outside its own `<label>`, so the checkbox keeps its name.
 *
 * There is no canvas here.  jsdom has no 2D context and no WebGL, so what is
 * asserted is the sentences and the controls -- the drawing itself is pinned by
 * `tests/golden/` on the arithmetic underneath it.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Decoder, MapArt, Replay, SightMaskDoc } from "../api/types";
import { SIMULATED_NOTE } from "../model/synthetic";
import { MapStage } from "./MapStage";
import { DEFAULT_LAYERS, usePlayback } from "./playback";

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
  players: [],
  rounds: [],
  kills: [],
  ultimates: [],
  spike: [],
  loadouts: [],
  ability_casts: [],
  event_times: [],
  score: [0, 0],
  has_positions: false,
  has_abilities: false,
  positions_available: true,
  positions_note: "positions decode on this build",
  position_source: "positions not decoded yet; nothing stored for this capture",
  catalog_source: "",
  notes: [],
  catalog_notes: [],
};

const ART: MapArt = {
  name: "Haven",
  codename: "Triad",
  map_url: "/Game/Maps/Triad/Triad",
  plottable: true,
  minimap_url: "/assets/maps/Haven/minimap.png",
  listview_url: null,
  splash_url: null,
  transform: {
    x_multiplier: 8.1e-5,
    y_multiplier: -8.1e-5,
    x_scalar_to_add: 0.5,
    y_scalar_to_add: 0.5,
    usable: true,
    vertical_scale: 8.1e-5,
  },
  callouts: [],
};

const MASK: SightMaskDoc = {
  map_key: "Haven",
  size: 2,
  cells: btoa(""),
  open_fraction: 1,
  max_range_uu: 6000,
  fov_degrees: 103,
  ray_step_degrees: 2,
  seed_cells: 2,
  probe_uu: 100,
};

const DECODER: Decoder = { found: true, path: "vrf-positions.dll", described: "", hint: "" };
const NO_DECODER: Decoder = {
  found: false,
  path: "",
  described: "the position decoder is not built",
  hint: "the position decoder is not built; run runners\\build-decoder.bat",
};

function show(
  replay: Partial<Replay> = {},
  decoder: Decoder = DECODER,
  art: MapArt | null = ART,
) {
  vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
    const url = String(input);
    let body: unknown = {};
    let status = 200;
    if (url.includes("/sight")) {
      body = MASK;
    } else if (url.includes("/api/maps/")) {
      if (art === null) {
        status = 404;
        body = { detail: "no art for that map" };
      } else {
        body = art;
      }
    } else if (url.includes("/positions")) {
      body = {
        format: "vrf-positions",
        version: 3,
        match_id: "m-1",
        build: REPLAY.build,
        hz: 10,
        position_source: "a decode",
        codenames: {},
        tracks: {},
        ability_spawns: {},
        ability_tracks: {},
      };
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MapStage replay={{ ...REPLAY, ...replay }} decoder={decoder} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  // Explicit, because `globals: false` means Testing Library never registers
  // its own automatic cleanup -- and without it every render stays in the
  // document and the next `findByText` matches two of everything.
  cleanup();
  vi.unstubAllGlobals();
  // The playback store outlives a render, which is the point of it.
  usePlayback.setState({
    layers: { ...DEFAULT_LAYERS },
    mode: "2d",
    selected: null,
    hovered: null,
    roundNo: null,
  });
});

describe("where a map cannot be drawn", () => {
  it("shows the decoder's own sentence rather than a drawing", async () => {
    const { container } = show();
    expect(await screen.findByText(/No positions decoded/)).toBeTruthy();
    expect(await screen.findByText(REPLAY.position_source)).toBeTruthy();
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("offers no DECODE button for a build that would only refuse", async () => {
    show({
      positions_available: false,
      positions_note: "no payload transform for this build; nothing to draw",
      build: "++Ares-Core+release-11.11",
    });
    expect(await screen.findByText(/no payload transform/)).toBeTruthy();
    expect(screen.queryByText("DECODE POSITIONS")).toBeNull();
  });

  it("names the command instead of a button when there is no decoder", async () => {
    show({}, NO_DECODER);
    expect(await screen.findByText(NO_DECODER.hint)).toBeTruthy();
    expect(screen.queryByText("DECODE POSITIONS")).toBeNull();
  });

  it("offers the button where a decode could actually work", async () => {
    show();
    expect(await screen.findByText("DECODE POSITIONS")).toBeTruthy();
  });

  it("says so when the map is in no art entry at all", async () => {
    // A clean checkout, or `--no-art`: `map_key` is empty, the art query is
    // never enabled, and a disabled query reports pending forever. Without an
    // explicit check the panel sits on "reading" and never says anything.
    const { container } = show({ has_positions: true, map_key: "" });
    expect(await screen.findByText(/No art entry for/)).toBeTruthy();
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("says the radar image is missing rather than drawing something else", async () => {
    const { container } = show({ has_positions: true }, DECODER, {
      ...ART,
      minimap_url: null,
    });
    expect(await screen.findByText(/No radar image for/)).toBeTruthy();
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("says so when a map has a picture but no coordinates", async () => {
    show({ has_positions: true }, DECODER, {
      ...ART,
      transform: { ...ART.transform, usable: false },
    });
    expect(await screen.findByText(/no coordinate transform/)).toBeTruthy();
  });
});

/**
 * Opening the layers menu, which the layer switches now live inside.
 *
 * They used to sit on the stage head as four buttons; there are nine of them
 * now, which is more than a head can carry beside a map name without the map
 * getting smaller.  The labels are unchanged and still exact -- `SIGHT`,
 * `UTILITY`, `TRAILS`, `CALLOUTS` -- so this is one press, not a rewrite of
 * what a spec looks for.  `e2e/harness.ts` has the same helper.
 */
async function openLayers() {
  fireEvent.click(await screen.findByRole("button", { name: "LAYERS" }));
}

describe("the layers menu", () => {
  it("offers every layer it has, by the exact names other files address", async () => {
    show({ has_positions: true });
    await openLayers();
    expect(await screen.findByText("SIGHT")).toBeTruthy();
    expect(screen.getByText("UTILITY")).toBeTruthy();
    expect(screen.getByText("TRAILS")).toBeTruthy();
  });

  /*
    CALLOUTS is placed in the 3D scene, so in 2D -- the default -- it cannot do
    anything.  It used to be dropped from the list, which is what the UI review
    reported: a layer the interface documents was simply not on the surface the
    user was looking at, and a missing row reads as a missing feature.
  */
  it("still offers CALLOUTS in 2D, and says why it cannot be used", async () => {
    show({ has_positions: true });
    await openLayers();
    expect(await screen.findByText("CALLOUTS")).toBeTruthy();
    expect(screen.getByText(/3D only/)).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: "CALLOUTS" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  /*
    The reason is rendered outside the `<label>`, because a `<label>` names the
    control it wraps by its text content -- so a reason inside it would rename
    this checkbox from `CALLOUTS` to `CALLOUTS 3D only ...` and break every
    role-and-name lookup in the suite.  That is what this asserts.
  */
  it("keeps a disabled row's accessible name to the label alone", async () => {
    show({ has_positions: true });
    await openLayers();
    expect(await screen.findByRole("checkbox", { name: "CALLOUTS" })).toBeTruthy();
  });
});

describe("the sight layer", () => {
  it("is offered as a switch", async () => {
    show({ has_positions: true });
    await openLayers();
    expect(await screen.findByRole("checkbox", { name: "SIGHT" })).toBeTruthy();
  });

  it("draws the cone without anybody being picked first", () => {
    /*
      What the layer being on by default is *for*, and it is now true of both
      canvases: the 2D one drew for one selected player once and the 3D scene
      went on doing so long after, so switching view silently dropped nine
      cones. Neither reads `selected` or `hovered` any more -- the switch is
      the only control -- and this is the standing check that a fresh replay
      needs no click to show them.
    */
    show({ has_positions: true });
    expect(usePlayback.getState().layers.sight).toBe(true);
    expect(usePlayback.getState().selected).toBeNull();
    expect(usePlayback.getState().hovered).toBeNull();
  });
});

describe("the simulated notice", () => {
  /*
    Half of what a roster card shows -- health, armour, credits, the weapon,
    and ATK/DEF itself -- is not in a `.vrf` and is generated by
    `model/synthetic.ts`.  The sentence saying so is not conditional and is not
    a tooltip: it is on the page whenever those numbers are, for the same
    reason the layer switches say why they cannot be used.
  */
  it("always says which numbers are generated", async () => {
    show({ has_positions: true });
    expect(await screen.findByText(SIMULATED_NOTE)).toBeTruthy();
  });
});
