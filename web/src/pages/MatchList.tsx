/**
 * Page one: every capture the scanner found.
 *
 * Two things on this page are load-bearing and neither is decoration.
 *
 * A card that cannot show positions is **held back, not dropped**.  Its build
 * has no payload transform, so there is nothing to draw and no schematic to
 * fall back to -- but the footer counts it and one button shows it, because a
 * library that quietly displays 21 of 101 files is lying about what is on the
 * disk.  The tiles across the top say the same numbers a second time, which is
 * the point: the count you have to read a footer to find is a count nobody
 * reads.
 *
 * Every card says `result not in file` where a WIN/LOSS badge would go.  That
 * badge cannot be built: a replay has no local player, and the teams are A and
 * B by inference from the kill graph.  Showing the sentence is the difference
 * between "we could not work this out" and a blank space that reads as a bug.
 *
 * There are no filters here beyond the two the server offers.  `playable_only`,
 * `map_name` and `page` are what `/api/library` takes; a search box filtering
 * the page in the browser would report "3 results" out of a library of 101 and
 * be wrong in a way that looks right.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Card } from "../api/types";
import { glyphs } from "../views/icons";
import { Failed, Loading, Page } from "../views/Shell";
import { Button, Chip, EmptyState, Field, IconButton, Segmented, StatTile, Toolbar } from "../views/ui";

function Thumbnail({ card }: { card: Card }) {
  if (!card.listview_url) {
    // No art cache, or no picture for this map. It costs a thumbnail and
    // changes nothing the card states -- and it is a *word*, not a stand-in
    // drawing, which a test over the whole page pins by asserting there is no
    // <img> at all in this state.
    return <div className="card-thumb absent">{card.map_name || "no map art"}</div>;
  }
  // The dimensions restate the box `.card-thumb` already reserves rather than
  // the file's own 456x100 -- `object-fit: cover` is what reconciles the two,
  // and what these attributes are for is holding the row's height before the
  // picture arrives.
  return (
    <img
      className="card-thumb"
      src={card.listview_url}
      alt=""
      loading="lazy"
      width={200}
      height={52}
    />
  );
}

/** The prewarm chip's tone, which is `vrfhome/prewarm.py`'s own four states. */
function prewarmTone(state: string): "ok" | "warn" | "bad" | "neutral" {
  if (state === "READY") return "ok";
  if (state === "FAILED") return "bad";
  if (state === "QUEUED" || state === "PREPARING") return "warn";
  return "neutral";
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
        <Chip>{card.result}</Chip>
        <Chip tone={card.positions_available ? "ok" : "neutral"}>
          {card.positions_available ? "positions" : "no transform"}
        </Chip>
        {card.prewarm ? (
          <Chip tone={prewarmTone(card.prewarm.state)} dot>
            {card.prewarm.label}
          </Chip>
        ) : null}
      </div>
    </>
  );

  // The left edge repeats what the chips say, in the one place the eye lands
  // first on a list of a hundred rows.
  const edge = !card.readable ? "card unreadable" : card.positions_available ? "card playable" : "card";

  // An unreadable capture is still shown -- carrying its error -- but there is
  // nothing behind it to open.
  if (!card.readable) {
    return <div className={edge}>{body}</div>;
  }
  return (
    <Link className={edge} to={`/replay/${card.id}`}>
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
    <Toolbar>
      <Segmented
        label="Which captures to list"
        options={["playable", "all"] as const}
        value={playableOnly ? "playable" : "all"}
        onChange={(next) => {
          setPlayableOnly(next === "playable");
          setPage(1);
        }}
        format={(option) =>
          option === "playable"
            ? { label: "PLAYABLE ONLY", icon: glyphs.filter }
            : { label: "SHOW ALL", icon: glyphs.noFile }
        }
      />
      <Button
        label="RESCAN"
        icon={glyphs.rescan}
        busy={query.isFetching}
        onClick={() => void query.refetch()}
      />
    </Toolbar>
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
      {/*
        Whether a decode is even possible, beside where the art came from. A
        library full of playable captures and no built decoder is a confusing
        state to discover one click later.
      */}
      {config.data ? (
        <div className={config.data.decoder.found ? "" : "error"}>
          {config.data.decoder.described}
        </div>
      ) : null}
    </>
  );

  return (
    <Page title="Replays" actions={actions} footer={footer}>
      <div className="stat-grid">
        <StatTile label="In the library" value={library.counts.total} icon={glyphs.noFile} />
        <StatTile
          label="With positions"
          value={library.counts.playable}
          icon={glyphs.ok}
          tone="ok"
          note="a payload transform exists for the build"
        />
        <StatTile
          label="Held back"
          value={library.counts.hidden}
          icon={glyphs.filter}
          note="counted, never dropped"
        />
        <StatTile
          label="Unreadable"
          value={library.counts.failed}
          icon={glyphs.bad}
          tone={library.counts.failed > 0 ? "bad" : undefined}
          note="shown with the error"
        />
      </div>

      {library.maps_present.length > 0 ? (
        <Toolbar>
          <Field icon={glyphs.mapPin} label="Filter by map">
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
          </Field>
          <span className="muted">
            {library.counts.total} in the library, {library.counts.playable} with positions
            {library.counts.failed > 0 ? `, ${library.counts.failed} unreadable` : ""}
          </span>
        </Toolbar>
      ) : null}

      {library.cards.length === 0 ? (
        <EmptyState icon={glyphs.noFile}>
          {library.root.exists
            ? `No replays in ${library.root.path}.`
            : `${library.root.path} does not exist.`}
          <br />
          <span className="mono">{library.root.described}</span>
        </EmptyState>
      ) : (
        <div className="cards">
          {library.cards.map((card) => (
            <CardRow key={card.id} card={card} />
          ))}
        </div>
      )}

      {library.page_count > 1 ? (
        <Toolbar>
          <IconButton
            label="Previous page"
            icon={glyphs.pagePrev}
            variant="default"
            disabled={page <= 1}
            onClick={() => setPage((n) => n - 1)}
          />
          <span className="muted numeric">
            page {library.page} of {library.page_count}
          </span>
          <IconButton
            label="Next page"
            icon={glyphs.pageNext}
            variant="default"
            disabled={page >= library.page_count}
            onClick={() => setPage((n) => n + 1)}
          />
        </Toolbar>
      ) : null}
    </Page>
  );
}
