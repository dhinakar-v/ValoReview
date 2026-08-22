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
 * The mark above each sentence is a picture of *absence* -- a crossed-out
 * frame, a file with a question on it -- which is the claim being made rather
 * than a stand-in for the thing that is not there.
 *
 * The 2D view is the default and is not a stepping stone to the 3D one.  It is
 * the readable one; the scene beside it exists to show the one thing a top-down
 * projection cannot, which is who is standing above whom.
 *
 * Every control label in this file is addressed by name from
 * `MapStage.test.tsx` and all three Playwright specs -- 2D, 3D, UTILITY,
 * TRAILS, SIGHT, CALLOUTS, DECODE POSITIONS.  The icons beside them are
 * `aria-hidden`, so the accessible names are still exactly those words.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Suspense, lazy, useMemo } from "react";

import { api, ApiError } from "../api/client";
import type { Decoder, Replay } from "../api/types";
import { buildModel } from "../model/replay";
import { Icon, Spinner, glyphs } from "./icons";
import { MinimapCanvas } from "./MinimapCanvas";
import { SCENE_CAPTION } from "./sceneCaption";
import { Failed } from "./Shell";
import { play } from "./sound";
import { Transport } from "./Transport";
import { Button, Chip, EmptyState, Panel, Segmented, Toggle, Toolbar } from "./ui";
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
    onSuccess: (fresh) => {
      client.setQueryData(["replay", replay.id], fresh);
      play("confirm");
    },
    onError: () => play("deny"),
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
      <Panel title="Map" icon={glyphs.map} className="stage">
        <EmptyState icon={glyphs.noFile}>
          No positions decoded for this capture.
          <br />
          <span className="mono">{replay.position_source || "not requested"}</span>
        </EmptyState>
        {/*
          A button only where one can work, and there are two ways it cannot.
          A build with no payload transform will refuse whatever is pressed --
          `positions_available` is the same membership test against the
          decoder's own table that the match list makes -- and a machine with
          no decoder has nothing to press at all. Each gets its own sentence,
          because they are fixed by different things.
        */}
        {/*
          A decode takes about four seconds and says nothing while it runs
          except by changing this button's own words, so the region is live:
          without it the only report of either outcome is a repaint, and the
          failure is a sentence that appears in silence.  `polite` rather than
          `assertive` -- it is the result of something the user just pressed,
          not an interruption.
        */}
        <div aria-live="polite" aria-busy={decode.isPending}>
          {!replay.positions_available ? (
            <p className="footnote" style={{ textAlign: "center" }}>
              {replay.positions_note} ({replay.build})
            </p>
          ) : decoder?.found ? (
            <div className="toolbar" style={{ paddingTop: 12, justifyContent: "center" }}>
              <Button
                label={decode.isPending ? "DECODING…" : "DECODE POSITIONS"}
                icon={glyphs.decode}
                variant="primary"
                busy={decode.isPending}
                onClick={() => decode.mutate()}
              />
              <span className="muted">about four seconds</span>
            </div>
          ) : (
            <p className="footnote" style={{ textAlign: "center" }}>
              {decoder?.hint ?? "checking for a decoder…"}
            </p>
          )}
          {decode.isError ? <Failed error={decode.error} /> : null}
        </div>
      </Panel>
    );
  }

  // A replay whose map is in no art entry has an empty `map_key`, so the art
  // query is never enabled -- and a disabled query reports `pending` forever.
  // Checking it before the loading line is what stops a clean checkout, or
  // `--no-art`, sitting on "reading" rather than saying what is missing.
  if (!replay.map_key) {
    return (
      <Panel title="Map" icon={glyphs.map} className="stage">
        <EmptyState icon={glyphs.noArt}>
          No art entry for {replay.map_name || replay.map_path}, so there is no
          radar image to draw the decoded positions on.
          <br />
          <span className="mono">runners\fetch-assets.bat fetch</span> downloads one.
        </EmptyState>
      </Panel>
    );
  }

  if (art.isPending || positions.isPending) {
    return (
      <Panel title="Map" icon={glyphs.map} className="stage">
        <p className="muted">
          <Spinner /> Reading the decoded tracks…
        </p>
      </Panel>
    );
  }

  if (!art.data || !radarUrl) {
    return (
      <Panel title="Map" icon={glyphs.map} className="stage">
        <EmptyState icon={glyphs.noArt}>
          No radar image for {replay.map_name || replay.map_path}.
          <br />
          <span className="mono">runners\fetch-assets.bat fetch</span> downloads one.
        </EmptyState>
      </Panel>
    );
  }

  if (!art.data.transform.usable) {
    return (
      <Panel title="Map" icon={glyphs.map} className="stage">
        <EmptyState icon={glyphs.mapPin}>
          {art.data.name} has a radar image but no coordinate transform, so nothing
          decoded out of this capture can be placed on it.
        </EmptyState>
      </Panel>
    );
  }

  const maskDoc = mask.data ?? null;
  const maskUnavailable =
    mask.isError && mask.error instanceof ApiError ? mask.error.message : null;

  return (
    <div className="panel stage">
      <div className="stage-head">
        <h2>{art.data.name}</h2>
        <Chip tone="ok" icon={glyphs.ok}>
          positions decoded
        </Chip>
        <div className="spacer" />
        <Layers hasMask={maskDoc !== null} is3d={mode === "3d"} />
      </div>

      <div className="stage-canvas">
        {mode === "2d" ? (
          <MinimapCanvas model={model} art={art.data} radar={radar} mask={maskDoc} />
        ) : (
          <Suspense
            fallback={
              <p className="stage-loading">
                <Spinner /> Loading the renderer…
              </p>
            }
          >
            <Scene3D model={model} art={art.data} radar={radar} mask={maskDoc} />
          </Suspense>
        )}
      </div>

      {/*
        The same two conditions the toolbar above uses to decide whether to
        draw SIGHT and CALLOUTS at all.  A key is a faster way to press a
        control, so it exists exactly where the control does.
      */}
      <Transport
        replay={replay}
        clock={clock}
        layers={{ sight: maskDoc !== null, callouts: mode === "3d" }}
      />

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
    <Toolbar>
      <Segmented
        label="Which view"
        options={["2D", "3D"] as const}
        value={is3d ? "3D" : "2D"}
        onChange={(next) => usePlayback.setState({ mode: next === "3D" ? "3d" : "2d" })}
        format={(option) => ({
          label: option,
          icon: option === "2D" ? glyphs.view2d : glyphs.view3d,
        })}
      />
      <span className="rule" />
      <Toggle
        label="UTILITY"
        icon={glyphs.utility}
        pressed={state.showAbilities}
        onChange={() => usePlayback.setState({ showAbilities: !state.showAbilities })}
      />
      <Toggle
        label="TRAILS"
        icon={glyphs.trails}
        pressed={state.showTrails}
        onChange={() => usePlayback.setState({ showTrails: !state.showTrails })}
      />
      {/*
        The sight toggle exists only where there is a mask to raycast against.
        A control that cannot do anything is worse than an explanation of its
        absence, and the caption below says which.
      */}
      {hasMask ? (
        <Toggle
          label="SIGHT"
          icon={glyphs.sight}
          pressed={state.showSight}
          onChange={() => usePlayback.setState({ showSight: !state.showSight })}
        />
      ) : null}
      {is3d ? (
        <Toggle
          label="CALLOUTS"
          icon={glyphs.callouts}
          pressed={state.showCallouts}
          onChange={() => usePlayback.setState({ showCallouts: !state.showCallouts })}
          title="Riot's own callouts, to check the scene against the minimap"
        />
      ) : null}
    </Toolbar>
  );
}

/**
 * Every claim the view is making, in words, under the view making it.
 *
 * The sight caption is the server's own text and is rendered verbatim; the 3D
 * caption is this file's, and both are here for the same reason -- each view
 * states something weaker than it looks, and the picture cannot say so itself.
 *
 * The mark beside each is `aria-hidden`, because two of these sentences are
 * matched exactly by tests and a glyph that joined the text node would change
 * what they are.
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
      {is3d ? (
        <p>
          <Icon glyph={glyphs.view3d} size={12} />
          <span>{SCENE_CAPTION}</span>
        </p>
      ) : null}
      {showSight && sightCaption ? (
        <p>
          <Icon glyph={glyphs.sight} size={12} />
          <span>{sightCaption}</span>
        </p>
      ) : null}
      {maskUnavailable ? (
        <p>
          <Icon glyph={glyphs.noArt} size={12} />
          <span>{maskUnavailable}</span>
        </p>
      ) : null}
      <p className="mono">
        <Icon glyph={glyphs.decode} size={12} />
        <span>{positionSource}</span>
      </p>
    </div>
  );
}
