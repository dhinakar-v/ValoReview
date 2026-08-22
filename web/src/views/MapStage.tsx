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
 * The arena
 * ---------
 * When everything is present this is not a panel on a page -- it is the page.
 * The canvas fills the window between a 40px bar and the transport, the two
 * rosters take a fixed gutter each side, and three things float over the canvas
 * itself: the round clock, the kill feed and the hover tooltip.  Those are the
 * only overlapping elements in the interface, and each keeps `--space-4` of
 * clearance from the canvas edge and from its neighbours.
 *
 * `.stage-canvas` holds **exactly one canvas** and `.panel.stage` stays the
 * outer node: `e2e/scene.spec.ts` locates the renderer through the first and
 * `e2e/gallery.spec.ts` screenshots the second.
 *
 * Every control label here is addressed by name from `MapStage.test.tsx` and
 * all three Playwright specs -- 2D, 3D, DECODE POSITIONS, and UTILITY, TRAILS,
 * SIGHT and CALLOUTS inside the layers menu.  The icons beside them are
 * `aria-hidden`, so the accessible names are still exactly those words.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Suspense, lazy, useEffect, useMemo } from "react";

import { api, ApiError } from "../api/client";
import type { Decoder, Replay } from "../api/types";
import { buildModel } from "../model/replay";
import { activeRound } from "../model/roundclock";
import { SIMULATED_LABEL, SIMULATED_NOTE, sideInRound } from "../model/synthetic";
import { useWeapons } from "./catalogue";
import { ClockPill } from "./ClockPill";
import { Icon, Spinner, glyphs } from "./icons";
import { KillToast } from "./KillToast";
import { LayersMenu } from "./LayersMenu";
import { useLiveSnapshot } from "./live";
import { MarkerTip } from "./MarkerTip";
import { MinimapCanvas } from "./MinimapCanvas";
import { RosterPanel } from "./RosterPanel";
import { Failed } from "./Shell";
import { Transport } from "./Transport";
import { Button, Chip, EmptyState, Panel, Segmented } from "./ui";
import { useImages } from "./images";
import { seek, usePlayback, usePlaybackDriver } from "./playback";

// `three` and its two wrappers are about a megabyte of the bundle, and the 2D
// view is the default and is not a stepping stone to this one. Loading the
// scene the first time somebody asks for it means the readable view costs
// nothing for a renderer it never uses.
const Scene3D = lazy(async () => ({ default: (await import("./Scene3D")).Scene3D }));

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
    // than a failure: the layer is unavailable, and the menu says so by not
    // offering it.
    retry: false,
  });

  const decode = useMutation({
    mutationFn: () => api.decode(replay.id),
    // Replace the whole datum, not just the tracks. A decode also gives every
    // pawn its agent codename and every cast the agent that made it, so the
    // roster and the cast table are stale afterwards too.
    onSuccess: (fresh) => {
      client.setQueryData(["replay", replay.id], fresh);
    },
  });

  const model = useMemo(
    () => buildModel(replay, positions.data ?? null),
    [replay, positions.data],
  );
  const radarUrl = art.data?.minimap_url ?? null;
  const radar = useImages([radarUrl]).get(radarUrl ?? "");
  const clock = usePlaybackDriver(replay.length_ms);
  const mode = usePlayback((state) => state.mode);
  const roundNo = usePlayback((state) => state.roundNo);
  const weapons = useWeapons();
  const snap = useLiveSnapshot(model);

  /*
    Open on the first round, not on millisecond zero.

    Round one starts a fraction of a second in -- 63ms on the reference capture
    -- so t=0 is *before* any `roundStarted`, `Snapshot.round` is null, nobody
    is in `alive`, and all ten roster cards render dead with zeroed vitals.
    That is a correct reading of an instant nobody wants to look at.  This
    effect is declared after `usePlaybackDriver` on purpose: the driver's own
    effect resets the playhead on a new capture, and effects in one component
    run in declaration order, so this lands after it rather than under it.
  */
  useEffect(() => {
    const first = replay.rounds[0];
    if (first === undefined) {
      return;
    }
    usePlayback.setState({ roundNo: first.number });
    seek(clock, first.start_ms);
  }, [clock, replay.id, replay.rounds]);

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
  const round = activeRound(replay, roundNo, snap.t_ms);
  const [scoreA, scoreB] = snap.score;

  return (
    <div className="panel stage">
      <div className="stage-head">
        {/*
          No map name here: the bar above already carries it, and two headings
          saying "Ascent" a centimetre apart is chrome pretending to be
          information.
        */}
        {/*
          The one chip here that is not a status: it is a disclaimer, and it
          carries the whole sentence as its title.  Half of what a roster card
          shows is not in a .vrf, and an interface that shows it without saying
          so is making a claim the file cannot support.
        */}
        <Chip tone="warn" icon={glyphs.simulated} title={SIMULATED_NOTE}>
          {SIMULATED_LABEL}
        </Chip>
        <div className="spacer" />
        <Segmented
          label="Which view"
          options={["2D", "3D"] as const}
          value={mode === "3d" ? "3D" : "2D"}
          onChange={(next) => usePlayback.setState({ mode: next === "3D" ? "3d" : "2d" })}
          format={(option) => ({
            label: option,
            icon: option === "2D" ? glyphs.view2d : glyphs.view3d,
          })}
        />
        <LayersMenu hasMask={maskDoc !== null} is3d={mode === "3d"} />
      </div>

      <div className="arena">
        <RosterPanel
          model={model}
          snap={snap}
          team="A"
          side={sideInRound(replay, "A", round)}
          score={scoreA ?? 0}
          weapons={weapons}
          mirrored={false}
        />

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
          <ClockPill round={round} snap={snap} />
          <KillToast model={model} snap={snap} weapons={weapons} />
          <MarkerTip model={model} snap={snap} weapons={weapons} />
        </div>

        <RosterPanel
          model={model}
          snap={snap}
          team="B"
          side={sideInRound(replay, "B", round)}
          score={scoreB ?? 0}
          weapons={weapons}
          mirrored
        />
      </div>

      {/*
        The same two conditions the layers menu uses to decide whether SIGHT
        and CALLOUTS exist at all.  A key is a faster way to press a control,
        so it exists exactly where the control does.
      */}
      <Transport
        replay={replay}
        clock={clock}
        weapons={weapons}
        layers={{ sight: maskDoc !== null, callouts: mode === "3d" }}
      />

      <Captions
        sightCaption={maskDoc?.caption ?? null}
        maskUnavailable={maskUnavailable}
      />
    </div>
  );
}

/**
 * Every claim a layer is making, in words, under the view making it.
 *
 * The sight caption is never held here as a constant, precisely so it cannot
 * drift: the sentence saying what a cone is travels in the same document as the
 * cells it is raycast against, and is rendered verbatim.  The simulated notice
 * beside it is the same idea for the generated numbers, and it is always shown,
 * because those numbers are always on screen.
 *
 * The mark beside each is `aria-hidden`, because one of these sentences is
 * matched exactly by a test and a glyph that joined the text node would change
 * what it is.
 */
function Captions({
  sightCaption,
  maskUnavailable,
}: {
  sightCaption: string | null;
  maskUnavailable: string | null;
}) {
  const showSight = usePlayback((state) => state.layers.sight);
  return (
    <div className="captions">
      <p>
        <Icon glyph={glyphs.simulated} size={12} />
        <span>{SIMULATED_NOTE}</span>
      </p>
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
    </div>
  );
}
