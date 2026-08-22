/**
 * The map, in whichever of its two forms, or the sentence that replaces it.
 *
 * Three things can be missing and each gets words rather than a drawing:
 *
 *   * **the decode** -- an unsupported build, an unbuilt decoder, or simply a
 *     capture nobody has decoded yet.  `position_source` is prose written by
 *     `tracks.attach`, which never raises for want of positions, and it is
 *     shown verbatim;
 *   * **the radar image** -- a missing or partial `assets/`, which costs
 *     pictures and changes nothing the interface claims;
 *   * **the transform** -- a map with a radar and no coordinates, which cannot
 *     place anything on it.
 *
 * None of them is a placeholder drawing.  A diagram in the place a map goes
 * reads as a map however it is captioned, which is why the schematic was
 * removed from the desktop viewer and why nothing like it comes back here.
 *
 * The 2D view is the default and is not a stepping stone to the 3D one.  It is
 * the readable one; the scene beside it exists to show the one thing a top-down
 * projection cannot, which is who is standing above whom.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Suspense, lazy, useMemo } from "react";

import { api, ApiError } from "../api/client";
import type { Decoder, Replay } from "../api/types";
import { buildModel } from "../model/replay";
import { MinimapCanvas } from "./MinimapCanvas";
import { SCENE_CAPTION } from "./sceneCaption";
import { Failed, Sentence } from "./Shell";
import { Transport } from "./Transport";
import { useImages } from "./images";
import { usePlayback, usePlaybackDriver } from "./playback";

// `three` and its two wrappers are about a megabyte of the bundle, and the 2D
// view is the default and is not a stepping stone to this one. Loading the
// scene the first time somebody asks for it means the readable view costs
// nothing for a renderer it never uses -- and `SCENE_CAPTION` lives in its own
// module so rendering the sentence does not pull in the thing it describes.
const Scene3D = lazy(async () => ({ default: (await import("./Scene3D")).Scene3D }));

/**
 * The map stage: two views over one snapshot, and the words under both.
 *
 * The sight caption is never held here as a constant, precisely so it cannot
 * drift: the sentence saying what a cone is travels in the same document as the
 * cells it is raycast against, so nothing can draw a wedge without having been
 * handed it.
 */
export function MapStage({
  replay,
  decoder,
}: {
  replay: Replay;
  decoder: Decoder | undefined;
}) {
  const client = useQueryClient();

  const positions = useQuery({
    queryKey: ["positions", replay.id],
    queryFn: () => api.positions(replay.id),
    enabled: replay.has_positions,
  });
  const art = useQuery({
    queryKey: ["map", replay.map_key],
    queryFn: () => api.map(replay.map_key),
    enabled: Boolean(replay.map_key),
  });
  const mask = useQuery({
    queryKey: ["sight", replay.map_key],
    queryFn: () => api.sight(replay.map_key),
    enabled: Boolean(replay.map_key),
    // A map with no radar image on disk is a 404, which is an answer rather
    // than a failure: the layer is unavailable, and the toggle says so.
    retry: false,
  });

  const decode = useMutation({
    mutationFn: () => api.decode(replay.id),
    // Replace the whole datum, not just the tracks. A decode also gives every
    // pawn its agent codename and every cast the agent that made it, so the
    // roster and the cast table are stale afterwards too -- the desktop viewer
    // has to rebuild its body and its transport bar by hand for this reason.
    onSuccess: (fresh) => client.setQueryData(["replay", replay.id], fresh),
  });

  const model = useMemo(
    () => buildModel(replay, positions.data ?? null),
    [replay, positions.data],
  );
  const radarUrl = art.data?.minimap_url ?? null;
  const radar = useImages([radarUrl]).get(radarUrl ?? "");
  const clock = usePlaybackDriver(replay.length_ms);
  const mode = usePlayback((state) => state.mode);

  if (!replay.has_positions) {
    return (
      <div className="panel stage">
        <h2>Map</h2>
        <Sentence>
          No positions decoded for this capture.
          <br />
          <span className="mono">{replay.position_source || "not requested"}</span>
        </Sentence>
        {/*
          A button only where one can work, and there are two ways it cannot.
          A build with no payload transform will refuse whatever is pressed --
          `positions_available` is the same membership test against the
          decoder's own table that the match list makes -- and a machine with
          no decoder has nothing to press at all. Each gets its own sentence,
          because they are fixed by different things.
        */}
        {!replay.positions_available ? (
          <p className="muted" style={{ textAlign: "center", fontSize: 12 }}>
            {replay.positions_note} ({replay.build})
          </p>
        ) : decoder?.found ? (
          <div className="toolbar" style={{ paddingTop: 12, justifyContent: "center" }}>
            <button
              type="button"
              onClick={() => decode.mutate()}
              disabled={decode.isPending}
            >
              {decode.isPending ? "DECODING…" : "DECODE POSITIONS"}
            </button>
            <span className="muted">about four seconds</span>
          </div>
        ) : (
          <p className="muted" style={{ textAlign: "center", fontSize: 12 }}>
            {decoder?.hint ?? "checking for a decoder…"}
          </p>
        )}
        {decode.isError ? <Failed error={decode.error} /> : null}
      </div>
    );
  }

  // A replay whose map is in no art entry has an empty `map_key`, so the art
  // query is never enabled -- and a disabled query reports `pending` forever.
  // Checking it before the loading line is what stops a clean checkout, or
  // `--no-art`, sitting on "reading" rather than saying what is missing.
  if (!replay.map_key) {
    return (
      <div className="panel stage">
        <h2>Map</h2>
        <Sentence>
          No art entry for {replay.map_name || replay.map_path}, so there is no
          radar image to draw the decoded positions on.
          <br />
          <span className="mono">runners\fetch-assets.bat fetch</span> downloads one.
        </Sentence>
      </div>
    );
  }

  if (art.isPending || positions.isPending) {
    return (
      <div className="panel stage">
        <h2>Map</h2>
        <p className="muted">Reading the decoded tracks…</p>
      </div>
    );
  }

  if (!art.data || !radarUrl) {
    return (
      <div className="panel stage">
        <h2>Map</h2>
        <Sentence>
          No radar image for {replay.map_name || replay.map_path}.
          <br />
          <span className="mono">runners\fetch-assets.bat fetch</span> downloads one.
        </Sentence>
      </div>
    );
  }

  if (!art.data.transform.usable) {
    return (
      <div className="panel stage">
        <h2>Map</h2>
        <Sentence>
          {art.data.name} has a radar image but no coordinate transform, so nothing
          decoded out of this capture can be placed on it.
        </Sentence>
      </div>
    );
  }

  const maskDoc = mask.data ?? null;
  const maskUnavailable =
    mask.isError && mask.error instanceof ApiError ? mask.error.message : null;

  return (
    <div className="panel stage">
      <div className="stage-head">
        <h2>
          {art.data.name} <span className="muted">&middot; positions decoded</span>
        </h2>
        <div className="spacer" />
        <Layers hasMask={maskDoc !== null} is3d={mode === "3d"} />
      </div>

      <div className="stage-canvas">
        {mode === "2d" ? (
          <MinimapCanvas model={model} art={art.data} radar={radar} mask={maskDoc} />
        ) : (
          <Suspense fallback={<p className="muted">Loading the renderer…</p>}>
            <Scene3D model={model} art={art.data} radar={radar} mask={maskDoc} />
          </Suspense>
        )}
      </div>

      <Transport replay={replay} clock={clock} />

      <Captions
        is3d={mode === "3d"}
        sightCaption={maskDoc?.caption ?? null}
        maskUnavailable={maskUnavailable}
        positionSource={model.positionSource}
      />
    </div>
  );
}

function Layers({ hasMask, is3d }: { hasMask: boolean; is3d: boolean }) {
  const state = usePlayback();
  return (
    <div className="toolbar" style={{ padding: 0 }}>
      <button
        type="button"
        aria-pressed={!is3d}
        onClick={() => usePlayback.setState({ mode: "2d" })}
      >
        2D
      </button>
      <button
        type="button"
        aria-pressed={is3d}
        onClick={() => usePlayback.setState({ mode: "3d" })}
      >
        3D
      </button>
      <span className="rule" />
      <button
        type="button"
        aria-pressed={state.showAbilities}
        onClick={() => usePlayback.setState({ showAbilities: !state.showAbilities })}
      >
        UTILITY
      </button>
      <button
        type="button"
        aria-pressed={state.showTrails}
        onClick={() => usePlayback.setState({ showTrails: !state.showTrails })}
      >
        TRAILS
      </button>
      {/*
        The sight toggle exists only where there is a mask to raycast against.
        A control that cannot do anything is worse than an explanation of its
        absence, and the caption below says which.
      */}
      {hasMask ? (
        <button
          type="button"
          aria-pressed={state.showSight}
          onClick={() => usePlayback.setState({ showSight: !state.showSight })}
        >
          SIGHT
        </button>
      ) : null}
      {is3d ? (
        <button
          type="button"
          aria-pressed={state.showCallouts}
          onClick={() => usePlayback.setState({ showCallouts: !state.showCallouts })}
          title="Riot's own callouts, to check the scene against the minimap"
        >
          CALLOUTS
        </button>
      ) : null}
    </div>
  );
}

/**
 * Every claim the view is making, in words, under the view making it.
 *
 * The sight caption is the server's own text and is rendered verbatim; the 3D
 * caption is this file's, and both are here for the same reason -- each view
 * states something weaker than it looks, and the picture cannot say so itself.
 */
function Captions({
  is3d,
  sightCaption,
  maskUnavailable,
  positionSource,
}: {
  is3d: boolean;
  sightCaption: string | null;
  maskUnavailable: string | null;
  positionSource: string;
}) {
  const showSight = usePlayback((state) => state.showSight);
  return (
    <div className="captions">
      {is3d ? <p className="muted">{SCENE_CAPTION}</p> : null}
      {showSight && sightCaption ? <p className="muted">{sightCaption}</p> : null}
      {maskUnavailable ? <p className="muted">{maskUnavailable}</p> : null}
      <p className="mono muted">{positionSource}</p>
    </div>
  );
}
