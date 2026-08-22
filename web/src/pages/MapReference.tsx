/**
 * Riot's own callouts, on Riot's own radar image.
 *
 * This page is handed a map key and nothing else, and that is the point.  The
 * desktop map reference cannot receive a `Replay` -- `mapref.show` is not given
 * one -- because it describes the map and not the match: the same picture for
 * every capture on Bind.  A route is an easy place to lose that, so the route
 * takes `:key`, the query asks for a map, and nothing on this page has any way
 * to reach a player.  Positions belong on the minimap.
 *
 * The callouts are plotted through `Transform.apply`, which swaps the axes --
 * world *y* feeds u.  That is measured, not assumed: the unswapped form lands
 * 200 of 346 callouts inside the image and this one lands 346, and it does not
 * look broken when it is wrong.  Every point here is drawn by the same
 * arithmetic the minimap will use, which makes this page the cheapest possible
 * check that the transform is right.
 */

import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Transform } from "../api/types";
import { Failed, Loading, Page, Sentence } from "../views/Shell";

/**
 * One world coordinate as a fraction of the radar image, both 0..1.
 *
 * The axis swap is deliberate and is pinned by a test on both sides of the
 * wire.  See `art.Transform.apply` and docs/valorant-assets.md.
 */
export function applyTransform(
  transform: Transform,
  worldX: number,
  worldY: number,
): [u: number, v: number] {
  return [
    worldY * transform.x_multiplier + transform.x_scalar_to_add,
    worldX * transform.y_multiplier + transform.y_scalar_to_add,
  ];
}

export function MapReferencePage() {
  const { key = "" } = useParams();
  const query = useQuery({
    queryKey: ["map", key],
    queryFn: () => api.map(key),
    enabled: Boolean(key),
  });

  const back = (
    <button type="button" onClick={() => window.history.back()}>
      BACK
    </button>
  );

  if (query.isPending) {
    return (
      <Page title="Map" actions={back}>
        <Loading what="the map" />
      </Page>
    );
  }
  if (query.isError) {
    return (
      <Page title="Map" actions={back}>
        <Failed error={query.error} />
      </Page>
    );
  }

  const art = query.data;
  const footer = (
    <>
      <div>
        Riot's own callouts at Riot's own coordinates. This page describes the map,
        never a match &mdash; it is the same picture for every replay on {art.name}.
      </div>
      <div className="mono">
        {art.callouts.length} callouts &middot; {art.map_url}
      </div>
    </>
  );

  return (
    <Page title={art.name || key} actions={back} footer={footer}>
      {!art.minimap_url ? (
        <Sentence>
          No radar image for {art.name || key}.
          <br />
          <Link to="/" className="mono">
            runners\fetch-assets.bat fetch
          </Link>{" "}
          downloads one.
        </Sentence>
      ) : !art.transform.usable ? (
        <Sentence>
          {art.name} has a radar image but no coordinate transform, so its callouts
          cannot be placed on it.
        </Sentence>
      ) : (
        <div
          style={{
            position: "relative",
            width: "min(100%, 720px)",
            aspectRatio: "1 / 1",
            margin: "0 auto",
          }}
        >
          <img
            src={art.minimap_url}
            alt={`${art.name} radar`}
            style={{ width: "100%", height: "100%", display: "block" }}
          />
          {art.callouts.map((callout) => {
            const [u, v] = applyTransform(art.transform, callout.world_x, callout.world_y);
            return (
              <span
                key={`${callout.name}-${callout.world_x}-${callout.world_y}`}
                className="mono"
                style={{
                  position: "absolute",
                  left: `${u * 100}%`,
                  top: `${v * 100}%`,
                  transform: "translate(-50%, -50%)",
                  fontSize: 10,
                  color: "var(--text-primary)",
                  textShadow: "0 0 4px #000, 0 0 2px #000",
                  pointerEvents: "none",
                  whiteSpace: "nowrap",
                }}
              >
                {callout.name}
              </span>
            );
          })}
        </div>
      )}
    </Page>
  );
}
