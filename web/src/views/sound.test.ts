/**
 * The three promises the sound module makes, none of which is about a sound.
 *
 * jsdom has no WebAudio at all, which is exactly why these are worth pinning:
 * every one of the guarantees below is the reason nothing in this file's own
 * test needs an `AudioContext` mock, and the day one is needed is the day one
 * of them was quietly dropped.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { play, resetAudioForTests, useSound } from "./sound";

/** An `AudioParam` with the four methods the envelopes actually call. */
function param() {
  return {
    value: 0,
    setValueAtTime: () => undefined,
    linearRampToValueAtTime: () => undefined,
    exponentialRampToValueAtTime: () => undefined,
  };
}

/**
 * A `localStorage` that works.
 *
 * jsdom's own is unreliable under this runner -- it warns about
 * `--localstorage-file` and hands back an object without `getItem` -- and
 * these tests are about what the module does with storage, not about which
 * storage jsdom managed to build.
 */
function memoryStorage() {
  const held = new Map<string, string>();
  return {
    getItem: (key: string) => held.get(key) ?? null,
    setItem: (key: string, value: string) => void held.set(key, value),
    removeItem: (key: string) => void held.delete(key),
    clear: () => held.clear(),
  };
}

/** A stand-in for the constructor, counting how often it was reached. */
function countingContext() {
  const made = { count: 0 };
  class Fake {
    state = "running";
    currentTime = 0;
    destination = {};
    constructor() {
      made.count += 1;
    }
    createGain() {
      return { gain: param(), connect: () => undefined };
    }
    createOscillator() {
      return {
        type: "sine",
        frequency: param(),
        connect: () => undefined,
        start: () => undefined,
        stop: () => undefined,
      };
    }
    close() {
      return Promise.resolve();
    }
  }
  return { made, Fake };
}

beforeEach(() => {
  resetAudioForTests();
  useSound.setState({ enabled: false });
  vi.stubGlobal("localStorage", memoryStorage());
});

afterEach(() => {
  resetAudioForTests();
  vi.unstubAllGlobals();
});

describe("the preference", () => {
  it("is off until somebody asks for it", () => {
    // An analytics tool that beeps before it was asked to is a defect report,
    // not a feature. There is no first-run sound.
    expect(useSound.getState().enabled).toBe(false);
  });

  it("is remembered, so the choice survives a reload", () => {
    useSound.getState().setEnabled(true);
    expect(globalThis.localStorage.getItem("vrf.sound")).toBe("on");
    expect(useSound.getState().enabled).toBe(true);
    useSound.getState().setEnabled(false);
    expect(globalThis.localStorage.getItem("vrf.sound")).toBe("off");
  });

  it("treats storage that refuses as no preference recorded", () => {
    // A private window, a cleared profile, a browser blocking site data: all
    // three throw, and all three mean the same thing as a first run.
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    });
    // The setter must not take the interface down with it.
    expect(() => useSound.getState().setEnabled(true)).not.toThrow();
    expect(useSound.getState().enabled).toBe(true);
  });
});

describe("the audio graph", () => {
  it("is not built while sound is off", () => {
    const { made, Fake } = countingContext();
    vi.stubGlobal("AudioContext", Fake);
    play("click");
    play("confirm");
    expect(made.count).toBe(0);
  });

  it("is built once, on the first sound played while enabled", () => {
    const { made, Fake } = countingContext();
    vi.stubGlobal("AudioContext", Fake);
    useSound.setState({ enabled: true });
    play("click");
    play("click");
    play("confirm");
    expect(made.count).toBe(1);
  });

  it("stays silent when the machine has asked for less motion", () => {
    // The stylesheet zeroes its transitions on the same query, and a sound is
    // the one thing here that can be dropped without changing what anything
    // says.
    const { made, Fake } = countingContext();
    vi.stubGlobal("AudioContext", Fake);
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
    }));
    useSound.setState({ enabled: true });
    play("click");
    expect(made.count).toBe(0);
  });

  it("does not throw where there is no WebAudio at all", () => {
    // jsdom, an old embed, a browser that refused. A missing sound costs
    // nothing; an exception inside a click handler costs a control.
    vi.stubGlobal("AudioContext", undefined);
    vi.stubGlobal("webkitAudioContext", undefined);
    useSound.setState({ enabled: true });
    expect(() => play("deny")).not.toThrow();
  });
});
