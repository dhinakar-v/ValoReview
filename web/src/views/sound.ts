/**
 * The interface's voice, synthesised rather than sampled, and silent by
 * default.
 *
 * Six short sounds, built from oscillators and gain envelopes.  No audio files
 * and no dependency: a sampled set would be six binaries in the repository
 * whose provenance and licence would have to be tracked the way the fonts' is,
 * in exchange for warmth this interface has no use for.  What it needs is
 * confirmation -- a press landed, a decode finished, a request failed -- and a
 * 20ms envelope says that as well as a recording of a click.
 *
 * Three things here are deliberate and each is pinned by `sound.test.ts`:
 *
 *   * **Off by default.**  An analytics tool that beeps before anybody asked
 *     it to is a defect report.  The toggle is in the app bar and the choice
 *     is remembered in `localStorage`.
 *   * **No `AudioContext` until one is needed.**  It is constructed on the
 *     first sound played *while enabled*, never at import.  jsdom has no
 *     `AudioContext` at all, so constructing eagerly would mean every page
 *     test carried a mock for a feature it never exercises.
 *   * **`prefers-reduced-motion` wins.**  Somebody who has asked for less
 *     motion has asked for less of exactly this, and the stylesheet reads the
 *     same query to zero its transitions.
 *
 * The store is its own rather than a field on `usePlayback`, because
 * `MapStage.test.tsx` writes to that store directly and a sound preference has
 * no business being reset by a test about captions.
 */

import { create } from "zustand";

const STORAGE_KEY = "vrf.sound";

/** Quiet.  These are confirmations, not alerts. */
const MASTER_GAIN = 0.12;

/** Two ticks closer together than this is a stutter, not information. */
const TICK_THROTTLE_MS = 120;

export type Voice =
  | "click"
  | "toggleOn"
  | "toggleOff"
  | "tick"
  | "confirm"
  | "deny"
  | "boundary";

/** One partial: a wave, a pitch sweep, a window in time, and a level. */
type Partial = {
  type: OscillatorType;
  from: number;
  to?: number;
  at: number;
  ms: number;
  gain: number;
};

/**
 * What each voice is made of.
 *
 * Pitch carries the meaning: rising is something arriving, falling is
 * something refused, and the two toggle voices are the same interval read in
 * opposite directions so a toggle sounds like the state it moved to.
 */
const VOICES: Record<Voice, Partial[]> = {
  click: [{ type: "square", from: 1180, to: 880, at: 0, ms: 22, gain: 0.5 }],
  toggleOn: [
    { type: "triangle", from: 660, at: 0, ms: 26, gain: 0.6 },
    { type: "triangle", from: 990, at: 0.026, ms: 42, gain: 0.5 },
  ],
  toggleOff: [
    { type: "triangle", from: 990, at: 0, ms: 26, gain: 0.5 },
    { type: "triangle", from: 660, at: 0.026, ms: 42, gain: 0.45 },
  ],
  tick: [{ type: "sine", from: 2400, at: 0, ms: 12, gain: 0.28 }],
  confirm: [
    { type: "sine", from: 587, at: 0, ms: 70, gain: 0.7 },
    { type: "sine", from: 880, at: 0.06, ms: 120, gain: 0.6 },
  ],
  deny: [{ type: "sawtooth", from: 320, to: 140, at: 0, ms: 150, gain: 0.4 }],
  boundary: [{ type: "sine", from: 440, to: 520, at: 0, ms: 90, gain: 0.35 }],
};

type SoundState = {
  enabled: boolean;
  setEnabled: (on: boolean) => void;
  toggle: () => void;
};

function remembered(): boolean {
  // A private window, a cleared profile or a browser set to block site data
  // all throw or answer nothing, and every one of them means "no preference
  // recorded" -- which is off, the same as a first run.
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) === "on";
  } catch {
    return false;
  }
}

function remember(on: boolean): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, on ? "on" : "off");
  } catch {
    // Nothing to do and nothing worth saying: the toggle still works for this
    // session, it simply will not be there next time.
  }
}

export const useSound = create<SoundState>((set, get) => ({
  enabled: remembered(),
  setEnabled: (on: boolean) => {
    remember(on);
    set({ enabled: on });
  },
  toggle: () => get().setEnabled(!get().enabled),
}));

let context: AudioContext | null = null;
let master: GainNode | null = null;
let lastTickAt = 0;

/** Whether the machine has asked for less of this. */
function reducedMotion(): boolean {
  try {
    return globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
  } catch {
    return false;
  }
}

/**
 * The audio graph, built once and only once somebody has asked for sound.
 *
 * Returns null wherever WebAudio is not available -- jsdom, an older embed, a
 * browser that refused -- because a missing sound costs nothing and a thrown
 * error inside a click handler costs a control.
 */
function graph(): { ctx: AudioContext; out: GainNode } | null {
  if (context !== null && master !== null) {
    // A context created before the first gesture starts suspended; every
    // subsequent press is a gesture, so this is the place to resume.
    if (context.state === "suspended") {
      void context.resume();
    }
    return { ctx: context, out: master };
  }
  const Ctor: typeof AudioContext | undefined =
    globalThis.AudioContext ??
    (globalThis as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (Ctor === undefined) {
    return null;
  }
  try {
    context = new Ctor();
    master = context.createGain();
    master.gain.value = MASTER_GAIN;
    master.connect(context.destination);
    return { ctx: context, out: master };
  } catch {
    context = null;
    master = null;
    return null;
  }
}

/**
 * Play one voice, if sound is on.
 *
 * Never throws.  Every call site is an event handler or an animation frame,
 * and neither is a place where a missing audio device should take the
 * interface with it.
 */
export function play(voice: Voice): void {
  if (!useSound.getState().enabled || reducedMotion()) {
    return;
  }
  if (voice === "tick") {
    // Scrubbing across a dense round crosses dozens of events in a second.
    const now = globalThis.performance?.now() ?? 0;
    if (now - lastTickAt < TICK_THROTTLE_MS) {
      return;
    }
    lastTickAt = now;
  }
  const built = graph();
  if (built === null) {
    return;
  }
  const { ctx, out } = built;
  const t0 = ctx.currentTime;
  for (const part of VOICES[voice]) {
    const osc = ctx.createOscillator();
    const env = ctx.createGain();
    const start = t0 + part.at;
    const end = start + part.ms / 1000;

    osc.type = part.type;
    osc.frequency.setValueAtTime(part.from, start);
    if (part.to !== undefined) {
      // Exponential, because pitch is heard logarithmically and a linear sweep
      // sounds like it slows down at the end.
      osc.frequency.exponentialRampToValueAtTime(part.to, end);
    }

    // A hard start clicks; 4ms of attack does not, and is still instant.
    env.gain.setValueAtTime(0, start);
    env.gain.linearRampToValueAtTime(part.gain, start + 0.004);
    env.gain.exponentialRampToValueAtTime(0.0001, end);

    osc.connect(env);
    env.connect(out);
    osc.start(start);
    osc.stop(end + 0.02);
  }
}

/** Whether a control press should sound, given what it moved to. */
export function playToggle(nowPressed: boolean): void {
  play(nowPressed ? "toggleOn" : "toggleOff");
}

/** Test seam: forget the audio graph and the throttle, keep the preference. */
export function resetAudioForTests(): void {
  context?.close?.();
  context = null;
  master = null;
  lastTickAt = 0;
}
