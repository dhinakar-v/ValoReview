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
  { keys: "Home End", does: "to this round's start, to its end" },
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
 *     way to work UTILITY, TRAILS, SIGHT, CALLOUTS and the mute from the
 *     keyboard -- every button on the page, for as long as a stage was
 *     mounted.
 *   * **A tablist moves with the arrow keys and Home/End.**  The timeline's
 *     strip is one, so ArrowRight in it changed the tab *and* stepped the
 *     playhead, and Home jumped to Rounds *and* seeked to zero.
 */
function ownsKey(target: EventTarget | null, key: string): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  /*
    A modal owns the page for as long as it is open.

    The round timeline is a `role="dialog"` mounted *inside* `Transport`, and
    `ui.Modal` traps the focus in it -- so every transport key fired while it
    was open, moving the playhead behind a dialog the user was reading, with
    the round stepper focused.  Before the per-key checks, so it covers Space
    as well: the stepper's own buttons need it.
  */
  if (target.closest('[role="dialog"]')) {
    return true;
  }
  if (key === " ") {
    return Boolean(target.closest('button, a[href], [role="button"]'));
  }
  if (key === "ArrowLeft" || key === "ArrowRight" || key === "Home" || key === "End") {
    /*
      A standing guard rather than a description of a live collision.  The
      round strip is `role="group"` with plain buttons -- it promises no arrow
      behaviour, so Home over the chips correctly reaches the transport -- and
      the one real tablist, the viewer's section strip, only mounts on the
      branch that has no positions and therefore no transport beside it.  It
      costs a line and it re-admits a known bug the day either changes.
    */
    return Boolean(target.closest('[role="tablist"]'));
  }
  /*
    A listbox owns its own arrows, Home and End.  The map filter is a
    `role="combobox"` over a `role="listbox"` rather than a native `<select>`,
    and `editing()` recognises a `SELECT` by tag name -- which a div with a
    role is not.
  */
  return Boolean(target.closest('[role="listbox"], [role="combobox"]'));
}

/**
 * Bind the transport keys for as long as a stage is on screen.
 *
 * Every callback here is the *same reference* the matching button is wired to,
 * which is what makes "a key is a faster way to press a button" structurally
 * true rather than a comment somebody has to keep honouring.
 *
 * `Home` and `End` are why this signature changed.  They used to be `seekTo(0)`
 * and `seekTo(lengthMs)` -- the only two absolute-time bindings left in a
 * transport that is scoped to a round everywhere else.  `End` appeared to work
 * only because the frame loop clamps to the round a tick later; `Home` landed
 * *before* the round, where the chip strip still says round 4 while the model
 * renders nobody alive and the readout reads 0:00.  So the hook no longer
 * knows the capture's length at all: with `lengthMs` gone there is nothing
 * left to compute an absolute seek *from*, and the bug cannot come back.
 */
export function useTransportKeys({
  clock,
  step,
  seekTo,
  toStart,
  toEnd,
  stepRound,
  layers,
}: {
  clock: PlaybackClock;
  step: (direction: 1 | -1) => void;
  /** Seek, clamped to the round by the caller -- see `Transport`. */
  seekTo: (ms: number) => void;
  /** Exactly what "Back to the start" does. */
  toStart: () => void;
  /** Exactly what "To the end" does. */
  toEnd: () => void;
  /** Step a round at a time, which is what `[` and `]` do. */
  stepRound?: (direction: 1 | -1) => void;
  /**
   * Which layer switches can do anything right now.
   *
   * SIGHT needs a radar mask on disk to raycast against and CALLOUTS is placed
   * in the 3D scene.  The *rows* are always shown -- disabled, carrying the
   * reason, because a missing row reads as a missing feature -- but a key has
   * no row to carry a reason, so a key that toggled them anyway would be the
   * unexplained dead control the menu no longer has: `S` on a map with no mask
   * flipped the layer with no effect and no caption, and the store is
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
        // No arithmetic of their own: `seekTo` clamps, and it is the only
        // thing here that knows which round the transport is scoped to.  These
        // used to clamp to [0, lengthMs], which let `,` at a round's first
        // millisecond walk the playhead into the previous round while the rail
        // and the countdown stayed on this one.
        case ".":
          seekTo(state.tMs + NUDGE_MS);
          break;
        case ",":
          seekTo(state.tMs - NUDGE_MS);
          break;
        case "Home":
          toStart();
          break;
        case "End":
          toEnd();
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
  }, [clock, step, seekTo, toStart, toEnd, stepRound, layers.sight, layers.callouts]);
}
