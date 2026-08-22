/**
 * Keys for the transport, because scrubbing with a mouse is not analysis.
 *
 * Every binding here does exactly what a control on the page already does, and
 * calls the same function to do it.  That is the rule: a key is a faster way to
 * press a button, never a second implementation of what the button meant.  A
 * shortcut that seeks by its own arithmetic would drift from `Replay.event_times`
 * the first time the server's list changed.
 *
 * Nothing fires while the focus is in a text field or a select, and nothing
 * fires with a modifier held -- Ctrl+F is the browser's, not this page's.
 */

import { useEffect } from "react";

import type { PlaybackClock } from "../model/clock";
import { SPEEDS } from "../model/clock";
import { usePlayback } from "./playback";

/** What each key does, in the order the hint panel lists them. */
export const SHORTCUTS: ReadonlyArray<{ keys: string; does: string }> = [
  { keys: "Space", does: "play or pause" },
  { keys: "← →", does: "step to the previous or next event" },
  { keys: ", .", does: "nudge one second back or forward" },
  { keys: "Home End", does: "to the start, to the end" },
  { keys: "1 … 6", does: "playback speed" },
  { keys: "V", does: "switch between the 2D map and the 3D scene" },
  { keys: "U T S C", does: "utility, trails, sight, callouts" },
  { keys: "K", does: "kill markers" },
  { keys: "[ ]", does: "previous or next round" },
  { keys: "R", does: "reset the zoom" },
];

/** A nudge is a second, which is the smallest step worth a key. */
const NUDGE_MS = 1000;

function editing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return (
    tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || target.isContentEditable
  );
}

/**
 * Whether whatever has the focus already owns this key.
 *
 * These bindings are on the `window`, which is the whole point -- they work
 * wherever you are on the page -- and it is also the trap: a widget that
 * handles a key and calls `preventDefault` does not stop this listener, which
 * runs afterwards regardless.  So the focused element is asked first.
 *
 * Two claims are real here and both were bugs:
 *
 *   * **Space presses a focused `<button>`.**  Taking it left Enter as the only
 *     way to work UTILITY, TRAILS, SIGHT, CALLOUTS and the sound toggle
 *     from the keyboard -- every button on the page, for as long as a stage was
 *     mounted.
 *   * **A tablist moves with the arrow keys and Home/End.**  The timeline's
 *     strip is one, so ArrowRight in it changed the tab *and* stepped the
 *     playhead, and Home jumped to Rounds *and* seeked to zero.
 */
function ownsKey(target: EventTarget | null, key: string): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (key === " ") {
    return Boolean(target.closest('button, a[href], [role="button"]'));
  }
  if (key === "ArrowLeft" || key === "ArrowRight" || key === "Home" || key === "End") {
    return Boolean(target.closest('[role="tablist"]'));
  }
  return false;
}

/**
 * Bind the transport keys for as long as a stage is on screen.
 *
 * `step` and `seek` are passed in rather than rebuilt, so the keys and the
 * buttons cannot disagree about what "next event" means.
 */
export function useTransportKeys({
  clock,
  step,
  seekTo,
  lengthMs,
  stepRound,
  layers,
}: {
  clock: PlaybackClock;
  step: (direction: 1 | -1) => void;
  seekTo: (ms: number) => void;
  lengthMs: number;
  /** Step a round at a time, which is what `[` and `]` do. */
  stepRound?: (direction: 1 | -1) => void;
  /**
   * Which layer switches exist on the toolbar right now.
   *
   * `MapStage` draws SIGHT only where there is a mask to raycast against and
   * CALLOUTS only in 3D, on the argument that a control which cannot do
   * anything is worse than an explanation of its absence.  A key that toggled
   * them anyway would be exactly that control, invisibly: `S` on a map with no
   * mask toggled the layer with no effect and no caption, and the store is
   * module-level, so the next replay opened in the same session came up with
   * the layer already on.
   */
  layers: { sight: boolean; callouts: boolean };
}): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        editing(event.target) ||
        ownsKey(event.target, event.key)
      ) {
        return;
      }
      const state = usePlayback.getState();
      const set = usePlayback.setState;

      switch (event.key) {
        case " ":
          clock.toggle();
          set({ playing: clock.playing, tMs: clock.tMs });
          break;
        case "ArrowRight":
          step(1);
          break;
        case "ArrowLeft":
          step(-1);
          break;
        case ".":
          seekTo(Math.min(lengthMs, state.tMs + NUDGE_MS));
          break;
        case ",":
          seekTo(Math.max(0, state.tMs - NUDGE_MS));
          break;
        case "Home":
          seekTo(0);
          break;
        case "End":
          seekTo(lengthMs);
          break;
        case "v":
        case "V":
          set({ mode: state.mode === "2d" ? "3d" : "2d" });
          break;
        case "u":
        case "U":
          state.toggleLayer("utility");
          break;
        case "t":
        case "T":
          state.toggleLayer("trails");
          break;
        case "k":
        case "K":
          state.toggleLayer("killMarkers");
          break;
        case "r":
        case "R":
          state.resetViewport();
          break;
        case "[":
          stepRound?.(-1);
          break;
        case "]":
          stepRound?.(1);
          break;
        case "s":
        case "S":
          if (!layers.sight) {
            return;
          }
          state.toggleLayer("sight");
          break;
        case "c":
        case "C":
          if (!layers.callouts) {
            return;
          }
          state.toggleLayer("callouts");
          break;
        default: {
          // 1..6 pick a speed by position in the model's own list, so adding a
          // speed there adds a key here and nowhere else.
          const index = Number.parseInt(event.key, 10) - 1;
          const speed = Number.isNaN(index) ? undefined : SPEEDS[index];
          if (speed === undefined) {
            return;
          }
          set({ speed });
          break;
        }
      }
      event.preventDefault();
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clock, step, seekTo, lengthMs, stepRound, layers.sight, layers.callouts]);
}
