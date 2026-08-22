/**
 * The window is not the only thing listening.
 *
 * These bindings live on the `window` so that they work wherever you are on
 * the page, and that is exactly what makes them able to steal a key from the
 * control that has the focus.  A widget calling `preventDefault` does not stop
 * a window listener -- it runs afterwards regardless -- so the focused element
 * has to be asked first, and this file is the check that it still is.
 *
 * Both cases here were real: Space was taken from every button on the page for
 * as long as a stage was mounted, and an arrow key in the timeline's tab strip
 * changed the tab *and* stepped the playhead.
 */

import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlaybackClock } from "../model/clock";
import { DEFAULT_LAYERS, usePlayback } from "./playback";
import { useTransportKeys } from "./shortcuts";

afterEach(cleanup);

const LENGTH_MS = 60_000;

function Bound({
  clock,
  step,
  seekTo = () => undefined,
  toStart = () => undefined,
  toEnd = () => undefined,
  layers = { sight: true, callouts: true },
}: {
  clock: PlaybackClock;
  step: (direction: 1 | -1) => void;
  seekTo?: (ms: number) => void;
  toStart?: () => void;
  toEnd?: () => void;
  layers?: { sight: boolean; callouts: boolean };
}) {
  useTransportKeys({ clock, step, seekTo, toStart, toEnd, layers });
  return (
    <>
      <button type="button">TRAILS</button>
      <div role="tablist">
        <button type="button" role="tab">
          Rounds
        </button>
      </div>
      <div role="dialog" aria-label="Round Timeline">
        <button type="button">Next round</button>
      </div>
      <p>somewhere that is not a control</p>
    </>
  );
}

describe("a key belongs to whatever has the focus first", () => {
  it("plays on Space when the focus is on nothing in particular", () => {
    const clock = new PlaybackClock(LENGTH_MS);
    render(<Bound clock={clock} step={() => undefined} />);
    fireEvent.keyDown(screen.getByText("somewhere that is not a control"), { key: " " });
    expect(clock.playing).toBe(true);
  });

  it("leaves Space to a focused button, which is how a button is pressed", () => {
    const clock = new PlaybackClock(LENGTH_MS);
    render(<Bound clock={clock} step={() => undefined} />);
    fireEvent.keyDown(screen.getByRole("button", { name: "TRAILS" }), { key: " " });
    expect(clock.playing).toBe(false);
  });

  it("steps on an arrow key outside the tab strip", () => {
    const step = vi.fn();
    render(<Bound clock={new PlaybackClock(LENGTH_MS)} step={step} />);
    fireEvent.keyDown(screen.getByText("somewhere that is not a control"), {
      key: "ArrowRight",
    });
    expect(step).toHaveBeenCalledWith(1);
  });

  it("leaves the arrow keys and Home to a tab strip that navigates with them", () => {
    const step = vi.fn();
    render(<Bound clock={new PlaybackClock(LENGTH_MS)} step={step} />);
    const tab = screen.getByRole("tab");
    fireEvent.keyDown(tab, { key: "ArrowRight" });
    fireEvent.keyDown(tab, { key: "Home" });
    expect(step).not.toHaveBeenCalled();
  });
});

describe("a key exists exactly where the control it presses does", () => {
  it("does not toggle a layer the stage is not offering", () => {
    usePlayback.setState({ layers: { ...DEFAULT_LAYERS, sight: false, callouts: false } });
    render(
      <Bound
        clock={new PlaybackClock(LENGTH_MS)}
        step={() => undefined}
        layers={{ sight: false, callouts: false }}
      />,
    );
    const target = screen.getByText("somewhere that is not a control");
    fireEvent.keyDown(target, { key: "s" });
    fireEvent.keyDown(target, { key: "c" });
    expect(usePlayback.getState().layers.sight).toBe(false);
    expect(usePlayback.getState().layers.callouts).toBe(false);
  });

  it("toggles it where the stage does draw the switch", () => {
    usePlayback.setState({ layers: { ...DEFAULT_LAYERS, sight: false } });
    render(<Bound clock={new PlaybackClock(LENGTH_MS)} step={() => undefined} />);
    fireEvent.keyDown(screen.getByText("somewhere that is not a control"), { key: "s" });
    expect(usePlayback.getState().layers.sight).toBe(true);
    usePlayback.setState({ layers: { ...DEFAULT_LAYERS } });
  });
});

describe("the transport keys press the transport's own buttons", () => {
  /*
    Asserting *which function fired* rather than where the playhead ended up.

    Home and End were `seekTo(0)` and `seekTo(lengthMs)` in a transport that is
    scoped to a round everywhere else, so they landed outside the round the
    rest of the interface was showing.  A test that checked the resulting time
    would pass against any re-implementation that happened to compute the same
    number today; this one only passes while the key and the button are
    literally the same callback.
  */
  it("sends Home to the same function the start button calls", () => {
    const clock = new PlaybackClock(LENGTH_MS);
    const toStart = vi.fn();
    const seekTo = vi.fn();
    render(<Bound clock={clock} step={() => undefined} toStart={toStart} seekTo={seekTo} />);
    fireEvent.keyDown(screen.getByText("somewhere that is not a control"), { key: "Home" });
    expect(toStart).toHaveBeenCalledTimes(1);
    expect(seekTo).not.toHaveBeenCalled();
  });

  it("sends End to the same function the end button calls", () => {
    const clock = new PlaybackClock(LENGTH_MS);
    const toEnd = vi.fn();
    const seekTo = vi.fn();
    render(<Bound clock={clock} step={() => undefined} toEnd={toEnd} seekTo={seekTo} />);
    fireEvent.keyDown(screen.getByText("somewhere that is not a control"), { key: "End" });
    expect(toEnd).toHaveBeenCalledTimes(1);
    expect(seekTo).not.toHaveBeenCalled();
  });

  it("nudges without doing any bounds arithmetic of its own", () => {
    // The clamp belongs to `Transport`, which is the only thing that knows
    // which round is picked. A nudge that clamped here to [0, lengthMs] is how
    // `,` used to walk out of the round it was scoped to.
    const clock = new PlaybackClock(LENGTH_MS);
    clock.seek(500);
    usePlayback.setState({ tMs: 500 });
    const seekTo = vi.fn();
    render(<Bound clock={clock} step={() => undefined} seekTo={seekTo} />);
    fireEvent.keyDown(screen.getByText("somewhere that is not a control"), { key: "," });
    expect(seekTo).toHaveBeenCalledWith(500 - 1000);
  });

  it("leaves every transport key to an open dialog", () => {
    // The round timeline is a role="dialog" mounted inside Transport, and
    // ui.Modal traps focus in it -- so these keys were moving the playhead
    // behind a dialog the reader could not see past.
    const clock = new PlaybackClock(LENGTH_MS);
    const toStart = vi.fn();
    const step = vi.fn();
    render(<Bound clock={clock} step={step} toStart={toStart} />);
    const inside = screen.getByRole("button", { name: "Next round" });
    fireEvent.keyDown(inside, { key: "Home" });
    fireEvent.keyDown(inside, { key: "ArrowRight" });
    fireEvent.keyDown(inside, { key: " " });
    expect(toStart).not.toHaveBeenCalled();
    expect(step).not.toHaveBeenCalled();
    expect(clock.playing).toBe(false);
  });
});
