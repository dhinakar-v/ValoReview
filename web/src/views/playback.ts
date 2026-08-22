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
import type { Viewport } from "../model/viewport";
import { FIT } from "../model/viewport";

export type ViewMode = "2d" | "3d";

/**
 * The layers a viewer can switch, as one object rather than nine flags.
 *
 * Nine booleans on the store meant nine `usePlayback.setState({ showX: !x })`
 * call sites and nine subscriptions; a menu that renders itself from a table
 * needs the table.  The keys are what `LayersMenu` iterates and what
 * `shortcuts.ts` binds, so adding a layer is one entry here and one row there.
 */
export interface Layers {
  utility: boolean;
  trails: boolean;
  sight: boolean;
  callouts: boolean;
  killMarkers: boolean;
  /** A looked-up radius, drawn dashed. See DEFAULT_LAYERS. */
  abilityRange: boolean;
  casts: boolean;
  kills: boolean;
  ultimates: boolean;
  spike: boolean;
}

export type LayerKey = keyof Layers;

export const DEFAULT_LAYERS: Layers = {
  utility: true,
  /*
    On by default, and for everybody in both views.

    An earlier decision had this off and drawing one wedge for a selected
    player, arguing that ten overlapping wedges say nothing. They say the one
    thing this layer is for -- which parts of the map nobody can see -- and one
    wedge cannot. The overlap is now what carries the answer rather than what
    spoils it: `sightlayer` gives each cone `1/N` of its side's ink and stacks
    coverage additively, so k cones over a point read as exactly `k/N`.

    `MapStage` follows `hasMask` when it mounts, so a map with no radar on
    disk does not come up with a lit switch that draws nothing.
  */
  sight: true,
  // A new feature rather than a port: the desktop minimap drew trails for
  // ability pawns only.
  trails: false,
  callouts: false,
  killMarkers: true,
  /*
    Off, because it is the only thing this canvas draws that nothing decoded.
    A published radius is looked up in `vrfview.abilityfacts` -- community
    research about a game that rebalances every few weeks -- so it is asked
    for deliberately, drawn dashed, and labelled `RANGE (SIM)` on its own row.
  */
  abilityRange: false,
  casts: true,
  kills: true,
  ultimates: true,
  spike: true,
};

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
  /**
   * Where the hovered marker is on the canvas, in CSS pixels.
   *
   * Published by the renderer rather than recomputed by the tooltip: the
   * canvas already has the hit-test coordinate, and a second projection in DOM
   * space would be a copy of the transform that could disagree with the one
   * that drew the marker.
   */
  hoveredAt: { x: number; y: number } | null;
  layers: Layers;
  /** Which round the transport is scoped to; null follows the playhead. */
  roundNo: number | null;
  /** Sides whose markers are hidden, by the funnel in a roster header. */
  hiddenTeams: string[];
  /** Zoom and pan over the radar. `FIT` is the untouched view. */
  viewport: Viewport;
  set: (patch: Partial<PlaybackState>) => void;
  /** Pin a player, or unpin them if they are already pinned. */
  toggleSelected: (actorId: number | null) => void;
  toggleLayer: (key: LayerKey) => void;
  toggleTeam: (team: string) => void;
  resetViewport: () => void;
}

export const usePlayback = create<PlaybackState>((set) => ({
  tMs: 0,
  playing: false,
  speed: 1,
  lengthMs: 0,
  mode: "2d",
  selected: null,
  hovered: null,
  hoveredAt: null,
  layers: { ...DEFAULT_LAYERS },
  roundNo: null,
  hiddenTeams: [],
  viewport: FIT,
  set: (patch) => set(patch),
  toggleSelected: (actorId) =>
    set((state) => ({ selected: state.selected === actorId ? null : actorId })),
  toggleLayer: (key) =>
    set((state) => ({ layers: { ...state.layers, [key]: !state.layers[key] } })),
  toggleTeam: (team) =>
    set((state) => ({
      hiddenTeams: state.hiddenTeams.includes(team)
        ? state.hiddenTeams.filter((name) => name !== team)
        : [...state.hiddenTeams, team],
    })),
  resetViewport: () => set({ viewport: FIT }),
}));

/** Whether a team's markers are being drawn, which two renderers both ask. */
export function teamShown(state: PlaybackState, team: string): boolean {
  return !state.hiddenTeams.includes(team);
}

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
/**
 * The window playback is confined to, or null for the whole capture.
 *
 * Held outside the store because the driver reads it sixty times a second and
 * nothing renders from it: the transport writes it when a round is chosen, and
 * the frame loop is the only reader.
 */
let bounds: { fromMs: number; toMs: number } | null = null;

export function setBounds(next: { fromMs: number; toMs: number } | null): void {
  bounds = next;
}

export function getBounds(): { fromMs: number; toMs: number } | null {
  return bounds;
}

export function usePlaybackDriver(lengthMs: number): PlaybackClock {
  const clock = useRef<PlaybackClock>(undefined as unknown as PlaybackClock);
  if (clock.current === undefined || clock.current.lengthMs !== lengthMs) {
    clock.current = new PlaybackClock(lengthMs, usePlayback.getState().speed);
  }

  useEffect(() => {
    usePlayback.setState({ lengthMs, tMs: 0 });
    clock.current.seek(0);
    // A new capture is a new everything: a viewport zoomed into Ascent's B
    // main is meaningless on Bind, and the store is module-level so it would
    // otherwise survive the navigation.
    usePlayback.setState({
      roundNo: null,
      viewport: FIT,
      hiddenTeams: [],
      selected: null,
      hovered: null,
      hoveredAt: null,
    });
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
      // Playback is scoped to a round, so the end of that round is an end.
      // Enforced here rather than in `PlaybackClock`, which is a byte-for-byte
      // port pinned by `tests/golden/clock.json` in two languages -- a bound it
      // does not have in Python would break that before it broke anything else.
      if (bounds !== null && engine.tMs >= bounds.toMs) {
        engine.seek(bounds.toMs);
        engine.pause();
      }
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
