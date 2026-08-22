/**
 * What the match list must not quietly stop doing.
 *
 * A capture that will not parse is still shown, carrying its error, rather than
 * being dropped from the list -- a library that silently omits a file is lying
 * about what is on the disk, and the failure mode is silent: the page looks
 * perfectly reasonable.
 *
 * Where there is no thumbnail the card names the map in *words*.  A stand-in
 * drawing in the place a picture goes reads as the picture however it is
 * captioned, which is why the assertion here is that there is no `<img>` at all
 * in that state.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Card, Library } from "../api/types";
import { NO_DATE } from "../model/format";
import { MatchListPage } from "./MatchList";

const CARD: Card = {
  id: "abc123",
  file_name: "match.vrf",
  match_id: "m-1",
  map_path: "/Game/Maps/Triad/Triad",
  map_name: "Haven",
  map_key: "Haven",
  listview_url: null,
  // The instant and the length, never a pre-formatted rendering: the browser
  // writes both, in the reader's own zone.  See `model/format.ts`.
  recorded_utc: "2026-08-21T18:02:00+00:00",
  length_ms: 1_571_721,
  rounds: 15,
  players: 10,
  size_bytes: 49_283_746,
  error: "",
  readable: true,
  playable: true,
  prewarm: null,
};

const LIBRARY: Library = {
  root: {
    path: "Demos",
    exists: true,
    source: "default Demos/ (DEMO_PATH is unset)",
    described: "Demos -- default Demos/ (DEMO_PATH is unset)",
  },
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
          decoder: {
            found: false,
            path: "",
            described: "the position decoder is not built",
            hint: "the position decoder is not built; run build-decoder.bat",
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
  it("names the map where there is no thumbnail, rather than drawing one", async () => {
    const { container } = show();
    expect(await screen.findAllByText("Haven")).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows a capture that would not parse, carrying its error", async () => {
    show({
      ...LIBRARY,
      cards: [{ ...CARD, readable: false, error: "unexpected chunk type 7" }],
    });
    expect(await screen.findByText("unexpected chunk type 7")).toBeTruthy();
  });

  it("says where it looked when the library is empty", async () => {
    show({ ...LIBRARY, cards: [] });
    expect(await screen.findByText(/No replays in Demos/)).toBeTruthy();
  });

  /*
    The four card facts used to be one run-on string the server had formatted,
    at one weight, on a line that clipped -- so the round count was the first
    thing to vanish and nothing said which number was which.  Labelled and
    separate now, and the date is written by the browser in the reader's zone
    rather than by `strftime` in UTC on the server.
  */
  it("labels each card fact and writes the length itself", async () => {
    show();
    // All of them, because the fixture library holds more than one card.
    expect(await screen.findAllByText("26:11")).toBeTruthy();
    expect(screen.getAllByText("rounds").length).toBeGreaterThan(0);
    expect(screen.getAllByText("players").length).toBeGreaterThan(0);
    expect(screen.getAllByText("15").length).toBeGreaterThan(0);
  });

  it("says so plainly where the container carried no date", async () => {
    show({ ...LIBRARY, cards: [{ ...CARD, recorded_utc: null }] });
    expect(await screen.findByText(NO_DATE)).toBeTruthy();
  });
});
