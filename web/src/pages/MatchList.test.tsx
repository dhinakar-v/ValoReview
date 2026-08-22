/**
 * The two things the match list must not quietly stop doing.
 *
 * A capture whose build has no payload transform is held back by the default
 * filter, and the footer has to say how many.  A library that shows 21 of 101
 * files without mentioning the other 80 is lying about what is on the disk, and
 * the failure mode is silent -- the page looks perfectly reasonable.
 *
 * Every card carries `result not in file` where the brief asks for a WIN/LOSS
 * badge.  That badge cannot be built: there is no local player in a replay and
 * the teams are A and B by inference.  The sentence is the claim; an empty
 * space where a verdict belongs reads as a bug rather than as an absence.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Card, Library } from "../api/types";
import { MatchListPage } from "./MatchList";

const CARD: Card = {
  id: "abc123",
  file_name: "match.vrf",
  match_id: "m-1",
  map_path: "/Game/Maps/Triad/Triad",
  map_name: "Haven",
  map_key: "Haven",
  listview_url: null,
  recorded_utc: null,
  recorded: "21 Aug 2026 - 18:02",
  length_ms: 1_571_721,
  duration: "26:11",
  rounds: 15,
  players: 10,
  build: "++Ares-Core+release-12.10",
  size_bytes: 49_283_746,
  error: "",
  readable: true,
  positions_available: true,
  positions_note: "positions decode on this build",
  playable: true,
  result: "result not in file",
  prewarm: null,
};

const LIBRARY: Library = {
  root: {
    path: "Demos",
    exists: true,
    source: "default Demos/ (DEMO_PATH is unset)",
    described: "Demos -- default Demos/ (DEMO_PATH is unset)",
  },
  described: "21 of 101 replays in Demos; 80 hidden",
  read: 12,
  cached: 89,
  counts: { total: 101, playable: 21, hidden: 80, failed: 0 },
  maps_present: ["Haven"],
  page: 1,
  page_count: 1,
  per_page: 10,
  cards: [CARD],
};

function show(library: Library = LIBRARY) {
  vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.includes("/api/library")
      ? library
      : {
          demo_root: library.root,
          art: {
            described: "no art cache found",
            empty: true,
            root: "assets",
            source: "none",
            version: "",
            maps: 0,
            agents: 0,
          },
          catalog_source: "",
          web_built: true,
          web_hint: "",
        };
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MatchListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the match list", () => {
  it("counts the captures it is not showing", async () => {
    show();
    expect(await screen.findByText(/80 not shown/)).toBeTruthy();
  });

  it("says the result is not in the file rather than leaving a gap", async () => {
    show();
    expect(await screen.findByText("result not in file")).toBeTruthy();
  });

  it("repeats the scanner's own sentence about where it looked", async () => {
    show();
    expect(await screen.findByText(LIBRARY.described)).toBeTruthy();
  });

  it("names the map where there is no thumbnail, rather than drawing one", async () => {
    const { container } = show();
    expect(await screen.findAllByText("Haven")).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("says where it looked when the library is empty", async () => {
    show({ ...LIBRARY, cards: [], counts: { total: 0, playable: 0, hidden: 0, failed: 0 } });
    expect(await screen.findByText(/No replays in Demos/)).toBeTruthy();
  });
});
