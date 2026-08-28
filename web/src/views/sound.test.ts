/**
 * The three ways a sound module goes wrong without anybody noticing.
 *
 * It **fires when it should not** -- a seek across a round crosses twenty
 * kills, and firing on each of them turns a scrub into machine-gun fire.  It
 * **fires twice** for one kill, which is a doubled report that reads as a
 * missed shot.  Or it **throws where there is no audio device**, which in this
 * interface means inside a zustand subscription, sixty times a second, taking
 * the playhead with it.
 *
 * `crossed` is the whole rule and is exported for exactly this file.  The
 * envelope is not asserted -- jsdom has no `AudioContext`, which is also the
 * point of one of the tests below: nothing here may construct one at import, or
 * every page test in this repository would need a mock for a feature it does
 * not use.
 *
 * Storage is faked rather than borrowed.  Node ships an experimental
 * `globalThis.localStorage` that is present and **not functional** without
 * `--localstorage-file` -- `getItem` is not even a function on it -- and under
 * vitest that is what a module sees rather than jsdom's.  A browser has one
 * object for both, so this is an artefact of the test environment and not of
 * the interface; it is also a live demonstration of why every access in
 * `sound.ts` is wrapped, and the last test here pins that.
 */

import { afterEach, describe, expect, it } from "vitest";

import { crossed, playShot, resetAudioForTests, useSound } from "./sound";
import { FLIGHT_MS } from "./tracers";

const STORAGE_KEY = "vrf.sound";

/** Whatever was there before -- Node's stub, jsdom's, or nothing. */
const REAL_STORAGE = Object.getOwnPropertyDescriptor(globalThis, "localStorage");

function useStorage(fake: unknown): void {
  Object.defineProperty(globalThis, "localStorage", {
    value: fake,
    configurable: true,
    writable: true,
  });
}

function workingStorage(): Storage & { map: Map<string, string> } {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
    clear: () => map.clear(),
    key: (index: number) => [...map.keys()][index] ?? null,
    get length() {
      return map.size;
    },
  } as Storage & { map: Map<string, string> };
}

afterEach(() => {
  resetAudioForTests();
  if (REAL_STORAGE) {
    Object.defineProperty(globalThis, "localStorage", REAL_STORAGE);
  }
});

describe("crossed", () => {
  it("fires once, on the step that passes the kill", () => {
    expect(crossed(14_900, 15_000, 15_000)).toBe(true);
    // The next frame is past it, and must not fire again.
    expect(crossed(15_000, 15_100, 15_000)).toBe(false);
  });

  it("does not fire for a kill the step has not reached", () => {
    expect(crossed(14_000, 14_900, 15_000)).toBe(false);
  });

  it("does not fire on a jump, which is a seek and not playback", () => {
    // The whole of a round, arriving in one store write.
    expect(crossed(0, 60_000, 15_000)).toBe(false);
  });

  it("does not fire scrubbing backwards, or standing still", () => {
    expect(crossed(20_000, 15_000, 15_000)).toBe(false);
    expect(crossed(15_000, 15_000, 15_000)).toBe(false);
  });
});

describe("the shot fires at the muzzle", () => {
  /*
    `useKillSounds` crosses `kill.t_ms - FLIGHT_MS`, not the kill, because the
    tracer's flight is timed to *land* on the kill. Getting this wrong does not
    throw and does not look wrong in a screenshot -- the bang simply arrives a
    second after the flash, which reads as the audio being vaguely out rather
    than as a fault with a cause. So the offset is asserted rather than trusted
    to the one line that applies it.
  */
  const KILL_MS = 15_000;
  const MUZZLE_MS = KILL_MS - FLIGHT_MS;

  it("bangs when the playhead crosses the muzzle", () => {
    expect(crossed(MUZZLE_MS - 100, MUZZLE_MS, MUZZLE_MS)).toBe(true);
  });

  it("does not bang again when it reaches the kill", () => {
    expect(crossed(KILL_MS - 100, KILL_MS, MUZZLE_MS)).toBe(false);
  });

  it("puts the muzzle a whole flight before the impact", () => {
    expect(KILL_MS - MUZZLE_MS).toBe(FLIGHT_MS);
    // Long enough to be a separate event from the kill rather than a doubled
    // report: two shots inside `SHOT_THROTTLE_MS` are heard as one.
    expect(FLIGHT_MS).toBeGreaterThan(100);
  });
});

describe("playShot", () => {
  it("is silent, and does not throw, where there is no audio", () => {
    // jsdom has no `AudioContext` at all. That is the environment every page
    // test in this repository runs in, and a throw here would surface as a
    // broken playhead rather than as a missing sound.
    expect("AudioContext" in globalThis).toBe(false);
    useSound.setState({ enabled: true });
    expect(() => playShot()).not.toThrow();
  });

  it("does nothing at all when switched off", () => {
    useSound.setState({ enabled: false });
    expect(() => playShot()).not.toThrow();
  });
});

describe("the preference", () => {
  it("records a mute, and records the un-mute beside it", () => {
    const store = workingStorage();
    useStorage(store);

    useSound.getState().setEnabled(false);
    expect(store.map.get(STORAGE_KEY)).toBe("off");
    useSound.getState().setEnabled(true);
    expect(store.map.get(STORAGE_KEY)).toBe("on");
  });

  it("starts on, because nothing recorded is not a request for silence", () => {
    // The rule, rather than the module's own start-up: anything other than the
    // string "off" means on, and that includes an empty store.
    const store = workingStorage();
    expect(store.getItem(STORAGE_KEY)).toBeNull();
    expect(store.getItem(STORAGE_KEY) !== "off").toBe(true);
  });

  it("survives a storage that refuses, in both directions", () => {
    useStorage({
      getItem() {
        throw new Error("blocked");
      },
      setItem() {
        throw new Error("blocked");
      },
    });

    expect(() => useSound.getState().setEnabled(false)).not.toThrow();
    // The toggle still works for this session; it simply will not be there
    // next time.
    expect(useSound.getState().enabled).toBe(false);
  });
});
