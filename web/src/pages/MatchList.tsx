/**
 * Page one: every playable capture the scanner found.
 *
 * The list is filtered to captures whose build has a payload transform, and
 * that filter lives on the server rather than here.  A build without one has no
 * positions to decode and there is no schematic to fall back to, so there is
 * nothing behind such a card to open.
 *
 * There are no filters here beyond the two the server offers.  `map_name` and
 * `page` are what `/api/library` takes; a search box filtering the page in the
 * browser would report "3 results" out of a library of a hundred and be wrong
 * in a way that looks right.
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Card } from "../api/types";
import { glyphs } from "../views/icons";
import { Failed, Loading, Page } from "../views/Shell";
import { Chip, EmptyState, Field, IconButton, Toolbar } from "../views/ui";

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

/**
 * Reveal a row as it comes into view, and do nothing at all where it cannot.
 *
 * The order here is the whole point.  A row renders visible; this hook then
 * checks that `IntersectionObserver` exists and that the element is real, and
 * only *then* marks it pending -- so anywhere the observer is missing (jsdom,
 * which runs three tests over this list) every card simply stays visible.  A
 * stylesheet that hid rows up front would have hidden them permanently there,
 * and `findAllByText("Haven")` would race an animation that never starts.
 *
 * `IntersectionObserver` and not a scroll listener: this page is one route
 * away from a viewer running a canvas at 60fps, and a scroll handler that
 * reflows a hundred rows is the kind of cost that shows up as jank somewhere
 * else entirely.
 */
function useReveal(index: number) {
  const ref = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (node === null || typeof IntersectionObserver === "undefined") {
      return;
    }
    // Anything already on screen at mount is in view by the time the observer
    // first fires, so this reads as a stagger on load and as a single reveal
    // on scroll -- which is the behaviour wanted in both cases.
    node.style.setProperty("--enter-delay", `${Math.min(index, 8) * 45}ms`);
    node.dataset.enter = "pending";

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            (entry.target as HTMLElement).dataset.enter = "in";
            observer.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -40px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [index]);

  return ref;
}

function CardRow({ card, index }: { card: Card; index: number }) {
  const reveal = useReveal(index);
  const body = (
    <>
      <Thumbnail card={card} />
      <div className="card-facts">
        <span className="card-map display">{card.map_name || card.map_path || "unknown map"}</span>
        <span className="card-line">
          {card.recorded} &middot; {card.duration} &middot; {card.rounds} rounds &middot;{" "}
          {card.players} players
        </span>
        {card.error ? <span className="card-line error">{card.error}</span> : null}
      </div>
      <div className="card-badges">
        {card.prewarm ? (
          <Chip tone={prewarmTone(card.prewarm.state)} dot>
            {card.prewarm.label}
          </Chip>
        ) : null}
      </div>
    </>
  );

  // The left edge says whether there is anything behind the row, in the one
  // place the eye lands first on a list of a hundred.
  const edge = card.readable ? "card playable" : "card unreadable";

  // An unreadable capture is still shown -- carrying its error -- but there is
  // nothing behind it to open.
  if (!card.readable) {
    return (
      <div className={edge} ref={reveal as React.Ref<HTMLDivElement>}>
        {body}
      </div>
    );
  }
  return (
    <Link
      className={edge}
      to={`/replay/${card.id}`}
      ref={reveal as React.Ref<HTMLAnchorElement>}
    >
      {body}
    </Link>
  );
}

export function MatchListPage() {
  const [mapName, setMapName] = useState("");
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: ["library", mapName, page],
    queryFn: () => api.library({ map_name: mapName, page }),
  });

  if (query.isPending) {
    return (
      <Page title="Replays">
        <Loading what="the replay library" />
      </Page>
    );
  }
  if (query.isError) {
    return (
      <Page title="Replays">
        <Failed error={query.error} />
      </Page>
    );
  }

  const library = query.data;

  return (
    <Page title="Replays">
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
          {library.cards.map((card, index) => (
            <CardRow key={card.id} card={card} index={index} />
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
