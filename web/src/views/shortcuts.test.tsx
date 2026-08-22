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
  layers = { sight: true, callouts: true },
}: {
  clock: PlaybackClock;
  step: (direction: 1 | -1) => void;
  layers?: { sight: boolean; callouts: boolean };
}) {
  useTransportKeys({ clock, step, seekTo: () => undefined, lengthMs: LENGTH_MS, layers });
  return (
    <>
      <button type="button">TRAILS</button>
      <div role="tablist">
        <button type="button" role="tab">
          Rounds
        </button>
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
