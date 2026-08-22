/**
 * A snapshot for the parts of the page that are made of DOM.
 *
 * The two canvases read `usePlayback.getState()` inside their own animation
 * frame and never subscribe to `tMs`, because a frame there costs ten binary
 * searches rather than a React pass.  The roster, the kill toast and the hover
 * tooltip cannot do that -- they are elements, and an element changes by being
 * re-rendered.
 *
 * Subscribing them to `tMs` directly would re-render ten cards sixty times a
 * second to move a number that changes four times a second.  So the playhead is
 * quantised first and the subscription is to the quantised value: React is only
 * told about a change when there is one worth drawing.  `stateAt` accumulates
 * nothing, so a coarse read is exactly as correct as a fine one -- it is simply
 * a different instant, at most one step behind.
 *
 * The step is 200 ms because that is roughly the fastest a health number is
 * legible at, not because it is a round figure; a kill toast fading over 2.5 s
 * has twelve frames at that rate, which is enough for the fade to read as one.
 */

import { useMemo } from "react";

import type { ReplayModel } from "../model/replay";
import type { Snapshot } from "../model/state";
import { stateAt } from "../model/state";
import { usePlayback } from "./playback";

export const LIVE_STEP_MS = 200;

/** The playhead, quantised, so a subscriber re-renders five times a second. */
export function useCoarseTime(stepMs: number = LIVE_STEP_MS): number {
  return usePlayback((state) => Math.floor(state.tMs / stepMs) * stepMs);
}

/**
 * A snapshot, recomputed when the quantised playhead moves.
 *
 * The quantised value decides **when** to recompute; the snapshot is taken at
 * the real playhead.  Taking it at the quantised value instead moves the
 * instant *backwards* by up to a step, and a step is enough to fall out of a
 * round: round one starts 63ms into the reference capture, `floor(63 / 200)` is
 * zero, and zero is before any `roundStarted` -- so `Snapshot.round` came back
 * null, `alive` came back empty, and all ten roster cards opened reading zero
 * health with no weapon. A correct reading of an instant nobody asked about.
 */
export function useLiveSnapshot(
  model: ReplayModel,
  stepMs: number = LIVE_STEP_MS,
): Snapshot {
  const tick = useCoarseTime(stepMs);
  return useMemo(
    () => stateAt(model, usePlayback.getState().tMs),
    // The tick is the dependency and is deliberately not read in the body:
    // it is what says a recompute is due, and the playhead is what says of
    // when.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [model, tick],
  );
}
