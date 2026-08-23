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
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Card, CardTeam, Library } from "../api/types";
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
  positions_note: "positions decode on this build",
  prewarm: null,
  // Deliberately null, and the "no <img>" assertion below depends on it: this
  // fixture is the *no picture anywhere* state, so a roster here would be
  // testing a different card.  The team strip has its own cases further down.
  teams: null,
  rounds_undecided: 0,
};

/** Five agents, named the way the manifest names them. */
function team(names: string[], roundsWon: number | null): CardTeam {
  return {
    agents: names.map((name) => ({
      name,
      icon_url: `/assets/agents/${name}/icon.png`,
    })),
    rounds_won: roundsWon,
  };
}

const ATTACKERS = ["Astra", "Killjoy", "Waylay", "Sova", "Reyna"];
const DEFENDERS = ["Brimstone", "Chamber", "Raze", "Jett", "Omen"];

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
  per_page: 7,
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
  // Explicit, because `globals: false` means Testing Library registers no
  // automatic cleanup -- and the pending-state test below returns *before* its
  // query settles, so without this its tree stays mounted and the next
  // `findAllByText` matches two of everything.  `MapStage.test.tsx` has
  // carried the same line for the same reason.
  cleanup();
  vi.unstubAllGlobals();
});

describe("the match list", () => {
  it("names the map where there is no thumbnail, rather than drawing one", async () => {
    const { container } = show();
    expect(await screen.findAllByText("Haven")).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  /*
    The loading state is a shape rather than a sentence -- but it must not be a
    shape anything else addresses.  `a.card` is how three Playwright specs open
    a capture and `a.card.playable` is what the harness clicks, so a placeholder
    answering either would be clicked, and `[data-enter]` is what
    `docshots.spec.ts` waits on for full opacity: a skeleton node carrying it
    would never arrive and the wait would hang rather than fail.  There is no
    `<img>` either, for the reason at the top of this file.
  */
  it("holds the shape of the list while it is arriving, without pretending to be one", () => {
    // Synchronous: the fetch stub resolves, but not before this render returns.
    const { container } = show();
    expect(container.querySelector(".skel-card")).toBeTruthy();
    expect(container.querySelector("a.card")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[data-enter]")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("the replay library");
  });

  it("shows a capture that would not parse, carrying its error", async () => {
    show({
      ...LIBRARY,
      cards: [{ ...CARD, readable: false, error: "unexpected chunk type 7" }],
    });
    expect(await screen.findByText("unexpected chunk type 7")).toBeTruthy();
  });

  /*
    A capture on a build with no payload transform reaches this page now, and
    the row has to say so itself: the list used to be filtered to playable, so
    the only thing that could report an undrawable capture was the footer's
    count of what had been held back.  The chip carries the scanner's own
    sentence as its `title` rather than restating it, so there is one place the
    reason is written.
  */
  it("says a capture cannot be drawn, and still lets it be opened", async () => {
    const { container } = show({
      ...LIBRARY,
      cards: [
        {
          ...CARD,
          playable: false,
          positions_note: "no payload transform for this build; nothing to draw",
        },
      ],
    });
    const chip = await screen.findByText("NO POSITIONS");
    expect(chip.getAttribute("title")).toContain("no payload transform");
    // Still a link: the map, the rounds and the kill feed are all readable.
    expect(container.querySelector("a.card")).toBeTruthy();
    // But not the one the Playwright harness opens when it wants positions.
    expect(container.querySelector("a.card.playable")).toBeNull();
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

  /*
    The team strip.

    Three separate claims reach this component and only two of them are always
    available, so each case below is one of them failing independently of the
    others.  The one that matters most is the third: a score is attributable
    only where a decode has said which half of the roster `infer` calls team A,
    and a number drawn against the wrong five agents is the one mistake here
    that would look entirely correct on screen.
  */
  it("draws both teams' agents on a card that has them", async () => {
    const { container } = show({
      ...LIBRARY,
      cards: [{ ...CARD, teams: [team(ATTACKERS, 13), team(DEFENDERS, 9)] }],
    });
    expect(await screen.findByTitle("Astra")).toBeTruthy();
    expect(container.querySelectorAll(".match-agent")).toHaveLength(10);
    // One row per team, and the colour is the team rather than a side: which
    // team attacked is not recoverable. See vrfview/theme.py.
    expect(container.querySelector(".match-team.is-a")).toBeTruthy();
    expect(container.querySelector(".match-team.is-b")).toBeTruthy();
    expect(screen.getByText("13")).toBeTruthy();
    expect(screen.getByText("9")).toBeTruthy();
  });

  it("draws the agents but no number where the score is not attributable", async () => {
    const { container } = show({
      ...LIBRARY,
      cards: [{ ...CARD, teams: [team(ATTACKERS, null), team(DEFENDERS, null)] }],
    });
    await screen.findByTitle("Astra");
    // The portraits are a fact about every readable capture; the score is not.
    expect(container.querySelectorAll(".match-agent")).toHaveLength(10);
    for (const cell of container.querySelectorAll(".match-score")) {
      expect(cell.textContent).toBe("");
    }
  });

  it("says how many rounds nothing settled, beside a short scoreline", async () => {
    show({
      ...LIBRARY,
      cards: [
        {
          ...CARD,
          rounds: 24,
          rounds_undecided: 2,
          teams: [team(ATTACKERS, 13), team(DEFENDERS, 9)],
        },
      ],
    });
    // 13 + 9 is 22 of 24, and the card has to account for the other two or it
    // reads as a result rather than as a partial one.
    expect(await screen.findByText("+2 undecided")).toBeTruthy();
  });

  it("keeps the shortfall off a card that could not attribute a score", async () => {
    show({
      ...LIBRARY,
      cards: [
        {
          ...CARD,
          rounds_undecided: 2,
          teams: [team(ATTACKERS, null), team(DEFENDERS, null)],
        },
      ],
    });
    await screen.findAllByText("Haven");
    // Nothing to be short *of*: an undecided count beside no scoreline reads
    // as a fault in the card rather than as a limit of the file.
    expect(screen.queryByText("+2 undecided")).toBeNull();
  });

  it("draws no strip at all where the roster could not be split", async () => {
    const { container } = show({ ...LIBRARY, cards: [{ ...CARD, teams: null }] });
    await screen.findAllByText("Haven");
    expect(container.querySelector(".match-teams")).toBeNull();
  });
});
