/**
 * Playback state, shared by the transport bar, the minimap and the 3D scene.
 *
 * The clock itself is not in the store.  `PlaybackClock` is a mutable object
 * advanced by explicit deltas, and putting it behind an immutable store would
 * mean either cloning it sixty times a second or lying about when it changed.
 * It lives in a ref inside the driver below; what the store holds is the
 * *published* playhead and the handful of flags the interface actually
 * switches on.
 *
 * Why a store at all
 * ------------------
 * Three components need the same instant and are not each other's children:
 * the canvas, the scene and the transport.  Lifting it into the page would
 * re-render the roster, the round table and the provenance panel on every
 * frame; a store lets each one subscribe to the field it reads.
 *
 * The canvas and the scene deliberately do **not** subscribe to `tMs` at all.
 * They read it out of `usePlayback.getState()` inside their own animation
 * frame, so a frame costs a draw rather than a React reconciliation.  Only the
 * clock readout and the scrubber thumb re-render per frame, and both are one
 * element.
 */

import { useEffect, useRef } from "react";
import { create } from "zustand";

import { PlaybackClock } from "../model/clock";

export type ViewMode = "2d" | "3d";

export interface PlaybackState {
  tMs: number;
  playing: boolean;
  speed: number;
  lengthMs: number;
  mode: ViewMode;
  /** The player whose cone is drawn, pinned by a click. Null draws none. */
  selected: number | null;
  /** Hovered, which previews a cone without pinning it. */
  hovered: number | null;
  showSight: boolean;
  showAbilities: boolean;
  showTrails: boolean;
  showCallouts: boolean;
  set: (patch: Partial<PlaybackState>) => void;
  /** Pin a player, or unpin them if they are already pinned. */
  toggleSelected: (actorId: number | null) => void;
}

export const usePlayback = create<PlaybackState>((set) => ({
  tMs: 0,
  playing: false,
  speed: 1,
  lengthMs: 0,
  mode: "2d",
  selected: null,
  hovered: null,
  // Off by default, and asked for deliberately: the claim is weak enough --
  // a radar silhouette, not collision -- that it should be a choice, and ten
  // overlapping wedges say nothing anyway.
  showSight: false,
  showAbilities: true,
  // A new feature rather than a port: the desktop minimap drew trails for
  // ability pawns only.
  showTrails: false,
  showCallouts: false,
  set: (patch) => set(patch),
  toggleSelected: (actorId) =>
    set((state) => ({ selected: state.selected === actorId ? null : actorId })),
}));

/** The pinned player if there is one, else whoever the mouse is over. */
export function selectedActor(state: PlaybackState): number | null {
  return state.selected ?? state.hovered;
}

/**
 * Drive the clock from `requestAnimationFrame`, and publish the playhead.
 *
 * The wall-time reference is refreshed every frame whether or not the clock is
 * running, which is what makes a pause exact: no time accumulates across it and
 * resuming does not jump.  `PlaybackClock.tick` is handed the delta and decides
 * what to do with it, so the speed multiplier is exact rather than a frame-rate
 * approximation -- and the same code, given the same deltas, is what
 * `tests/golden/clock.json` pins in both languages.
 */
export function usePlaybackDriver(lengthMs: number): PlaybackClock {
  const clock = useRef<PlaybackClock>(undefined as unknown as PlaybackClock);
  if (clock.current === undefined || clock.current.lengthMs !== lengthMs) {
    clock.current = new PlaybackClock(lengthMs, usePlayback.getState().speed);
  }

  useEffect(() => {
    usePlayback.setState({ lengthMs, tMs: 0 });
    clock.current.seek(0);
  }, [lengthMs]);

  useEffect(() => {
    let frame = 0;
    let last = performance.now();
    const step = (now: number) => {
      const delta = now - last;
      last = now;
      const engine = clock.current;
      const state = usePlayback.getState();
      // The store is the interface's intent and the clock is the mechanism;
      // this is the one place they are reconciled, once per frame.
      engine.playing = state.playing;
      engine.setSpeed(state.speed);
      engine.tick(delta);
      if (engine.tMs !== state.tMs || engine.playing !== state.playing) {
        usePlayback.setState({ tMs: engine.tMs, playing: engine.playing });
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, []);

  return clock.current;
}

/** Seek both the clock and the published playhead, in that order. */
export function seek(clock: PlaybackClock, ms: number): void {
  clock.seek(ms);
  usePlayback.setState({ tMs: clock.tMs });
}
