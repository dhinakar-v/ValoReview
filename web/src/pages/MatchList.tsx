/**
 * Page one: every capture the scanner found.
 *
 * Two things on this page are load-bearing and neither is decoration.
 *
 * A card that cannot show positions is **held back, not dropped**.  Its build
 * has no payload transform, so there is nothing to draw and no schematic to
 * fall back to -- but the footer counts it and one button shows it, because a
 * library that quietly displays 21 of 101 files is lying about what is on the
 * disk.
 *
 * Every card says `result not in file` where a WIN/LOSS badge would go.  That
 * badge cannot be built: a replay has no local player, and the teams are A and
 * B by inference from the kill graph.  Showing the sentence is the difference
 * between "we could not work this out" and a blank space that reads as a bug.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Card } from "../api/types";
import { Failed, Loading, Page, Sentence } from "../views/Shell";

function Thumbnail({ card }: { card: Card }) {
  if (!card.listview_url) {
    // No art cache, or no picture for this map. It costs a thumbnail and
    // changes nothing the card states.
    return <div className="card-thumb absent">{card.map_name || "no map art"}</div>;
  }
  return <img className="card-thumb" src={card.listview_url} alt="" loading="lazy" />;
}

function CardRow({ card }: { card: Card }) {
  const body = (
    <>
      <Thumbnail card={card} />
      <div className="card-facts">
        <span className="card-map display">{card.map_name || card.map_path || "unknown map"}</span>
        <span className="card-line">
          {card.recorded} &middot; {card.duration} &middot; {card.rounds} rounds &middot;{" "}
          {card.players} players
        </span>
        <span className="card-line mono">{card.build || "build not in file"}</span>
        {card.error ? <span className="card-line error">{card.error}</span> : null}
      </div>
      <div className="card-badges">
        <span className="chip">{card.result}</span>
        <span className={card.positions_available ? "chip ok" : "chip"}>
          {card.positions_available ? "positions" : "no transform"}
        </span>
        {card.prewarm ? (
          <span className={card.prewarm.state === "READY" ? "chip ok" : "chip"}>
            {card.prewarm.label}
          </span>
        ) : null}
      </div>
    </>
  );

  // An unreadable capture is still shown -- carrying its error -- but there is
  // nothing behind it to open.
  if (!card.readable) {
    return <div className="card">{body}</div>;
  }
  return (
    <Link className="card" to={`/replay/${card.id}`}>
      {body}
    </Link>
  );
}

export function MatchListPage() {
  const [playableOnly, setPlayableOnly] = useState(true);
  const [mapName, setMapName] = useState("");
  const [page, setPage] = useState(1);

  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const query = useQuery({
    queryKey: ["library", playableOnly, mapName, page],
    queryFn: () => api.library({ playable_only: playableOnly, map_name: mapName, page }),
  });

  const actions = (
    <div className="toolbar" style={{ paddingBottom: 0 }}>
      <button
        type="button"
        aria-pressed={!playableOnly}
        onClick={() => {
          setPlayableOnly((on) => !on);
          setPage(1);
        }}
      >
        {playableOnly ? "SHOW ALL" : "PLAYABLE ONLY"}
      </button>
      <button type="button" onClick={() => query.refetch()} disabled={query.isFetching}>
        RESCAN
      </button>
    </div>
  );

  if (query.isPending) {
    return (
      <Page title="Replays" actions={actions}>
        <Loading what="the replay library" />
      </Page>
    );
  }
  if (query.isError) {
    return (
      <Page title="Replays" actions={actions}>
        <Failed error={query.error} />
      </Page>
    );
  }

  const library = query.data;
  const footer = (
    <>
      <div>{library.described}</div>
      {library.counts.hidden > 0 && playableOnly ? (
        <div>
          {library.counts.hidden} not shown &mdash; no payload transform for their build,
          so there are no positions to draw. SHOW ALL lists them.
        </div>
      ) : null}
      {config.data ? <div>{config.data.art.described}</div> : null}
    </>
  );

  return (
    <Page title="Replays" actions={actions} footer={footer}>
      {library.maps_present.length > 0 ? (
        <div className="toolbar">
          <select
            value={mapName}
            onChange={(event) => {
              setMapName(event.target.value);
              setPage(1);
            }}
          >
            <option value="">every map</option>
            {library.maps_present.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <span className="muted">
            {library.counts.total} in the library, {library.counts.playable} with positions
            {library.counts.failed > 0 ? `, ${library.counts.failed} unreadable` : ""}
          </span>
        </div>
      ) : null}

      {library.cards.length === 0 ? (
        <Sentence>
          {library.root.exists
            ? `No replays in ${library.root.path}.`
            : `${library.root.path} does not exist.`}
          <br />
          <span className="mono">{library.root.described}</span>
        </Sentence>
      ) : (
        <div className="cards">
          {library.cards.map((card) => (
            <CardRow key={card.id} card={card} />
          ))}
        </div>
      )}

      {library.page_count > 1 ? (
        <div className="toolbar" style={{ paddingTop: 12 }}>
          <button type="button" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>
            PREVIOUS
          </button>
          <span className="muted numeric">
            page {library.page} of {library.page_count}
          </span>
          <button
            type="button"
            disabled={page >= library.page_count}
            onClick={() => setPage((n) => n + 1)}
          >
            NEXT
          </button>
        </div>
      ) : null}
    </Page>
  );
}
