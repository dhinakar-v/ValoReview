/**
 * The one sound this interface makes: a shot, when the playhead crosses a kill.
 *
 * There was a `sound.ts` before this one -- seven synthesised voices for
 * presses, confirmations and refusals -- and it was deleted, correctly, because
 * it was off by default and the speaker toggle came off the app bar, so nothing
 * left could reach it.  What comes back is deliberately not that module: one
 * voice, with a control on the stage head beside the thing it is about.  A
 * module ships the sounds something plays.
 *
 * **The shot is generated and the crossing is not.**  A `.vrf` holds no fire
 * event, no projectile and no weapon -- `characterDeath` is a millisecond, a
 * killer and a victim -- so what is real here is *when* somebody died, and the
 * bang is this project's illustration of it, exactly as `views/tracers.ts`
 * draws the line and `model/synthetic.ts` fills in the health bar.
 * `SIMULATED_NOTE` says so on the page.
 *
 * Three things are kept from the deleted module because each was right:
 *
 *   * **No `AudioContext` until one is needed.**  It is built on the first
 *     shot played *while enabled*, never at import.  jsdom has no
 *     `AudioContext` at all, so constructing eagerly would mean every page
 *     test carried a mock for a feature it never exercises.
 *   * **Its own store**, rather than a field on `usePlayback`, because
 *     `MapStage.test.tsx` writes to that store directly and a sound preference
 *     has no business being reset by a test about captions.
 *   * **Synthesised, not sampled.**  A recorded gunshot would be a binary in
 *     the repository whose provenance and licence would have to be tracked the
 *     way the fonts' are, and this needs to say "a shot landed", not to sound
 *     like a Vandal.
 *
 * Two things are deliberately different.  It is **on** by default, because a
 * replay tool asked to make gunfire should make gunfire; `"off"` in storage is
 * the only thing that silences it.  And there is no `prefers-reduced-motion`
 * gate: that query is a statement about motion, and the old module honoured it
 * because its voices were feedback on animated controls.  Silencing this for
 * somebody who asked for fewer animations would answer a question they did not
 * ask.
 */

import { useEffect } from "react";
import { create } from "zustand";

import type { ReplayModel } from "../model/replay";
import { usePlayback } from "./playback";
import { FLIGHT_MS } from "./tracers";

const STORAGE_KEY = "vrf.sound";

/** Quiet.  This plays over whatever the reader is actually listening to. */
const MASTER_GAIN = 0.12;

/** Two shots closer together than this would clip into one. */
const SHOT_THROTTLE_MS = 60;

/**
 * How far the playhead may advance in one step and still count as *playing*.
 *
 * A seek, a round change and a dragged scrubber all move the playhead by
 * seconds at a time, and every kill they pass over is a kill nobody watched.
 * Without this bound, jumping to the end of a round fires twenty shots in one
 * frame.
 */
const MAX_ADVANCE_MS = 250;

/** Whether sound was switched off last time.  Anything else means on. */
function remembered(): boolean {
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) !== "off";
  } catch {
    // A private window, a cleared profile, storage blocked outright: no
    // preference was recorded, which is on, the same as a first run.
    return true;
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

interface SoundState {
  enabled: boolean;
  setEnabled: (on: boolean) => void;
  toggle: () => void;
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
let noise: AudioBuffer | null = null;
let lastShotAt = 0;

/**
 * The audio graph, built once and only once somebody has asked for sound.
 *
 * Returns null wherever WebAudio is not available -- jsdom, an older embed, a
 * browser that refused -- because a missing sound costs nothing and a thrown
 * error inside an animation frame costs the interface.
 */
function graph(): { ctx: AudioContext; out: GainNode } | null {
  if (context !== null && master !== null) {
    // A context created before the first gesture starts suspended.  Playback
    // begins with a press, so by the time a shot is due there has been one.
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

/** How long the burst lasts.  A gunshot is a transient, not a note. */
const SHOT_MS = 130;

/**
 * White noise, generated once and reused.
 *
 * A shot is broadband -- an oscillator of any shape is a pitch, and a pitched
 * bang reads as a beep.  Half a second is longer than any burst needs and is
 * built on the first shot rather than at import, for the same reason the
 * context is.
 */
function noiseBuffer(ctx: AudioContext): AudioBuffer {
  if (noise !== null && noise.sampleRate === ctx.sampleRate) {
    return noise;
  }
  const frames = Math.floor(ctx.sampleRate / 2);
  const buffer = ctx.createBuffer(1, frames, ctx.sampleRate);
  const samples = buffer.getChannelData(0);
  for (let i = 0; i < frames; i += 1) {
    samples[i] = Math.random() * 2 - 1;
  }
  noise = buffer;
  return buffer;
}

/**
 * One shot.  Never throws.
 *
 * Two layers, which is what separates a gunshot from a hiss: a filtered noise
 * burst that opens bright and closes down over its own length, and a low sine
 * under it that gives the report a body.  Both decay exponentially, because
 * loudness is heard logarithmically and a linear fade sounds like a fade.
 */
export function playShot(): void {
  if (!useSound.getState().enabled) {
    return;
  }
  const now = globalThis.performance?.now() ?? 0;
  if (now - lastShotAt < SHOT_THROTTLE_MS) {
    return;
  }
  const built = graph();
  if (built === null) {
    return;
  }
  lastShotAt = now;
  const { ctx, out } = built;
  const start = ctx.currentTime;
  const end = start + SHOT_MS / 1000;

  const crack = ctx.createBufferSource();
  crack.buffer = noiseBuffer(ctx);
  const tone = ctx.createBiquadFilter();
  tone.type = "lowpass";
  tone.frequency.setValueAtTime(7000, start);
  tone.frequency.exponentialRampToValueAtTime(700, end);
  const crackEnv = ctx.createGain();
  crackEnv.gain.setValueAtTime(0, start);
  // 2ms of attack rather than none: a discontinuity at full amplitude is its
  // own click, on top of the one being synthesised.
  crackEnv.gain.linearRampToValueAtTime(1, start + 0.002);
  crackEnv.gain.exponentialRampToValueAtTime(0.0001, end);
  crack.connect(tone);
  tone.connect(crackEnv);
  crackEnv.connect(out);
  crack.start(start);
  crack.stop(end + 0.02);

  const thump = ctx.createOscillator();
  thump.type = "sine";
  thump.frequency.setValueAtTime(160, start);
  thump.frequency.exponentialRampToValueAtTime(50, end);
  const thumpEnv = ctx.createGain();
  thumpEnv.gain.setValueAtTime(0, start);
  thumpEnv.gain.linearRampToValueAtTime(0.7, start + 0.004);
  thumpEnv.gain.exponentialRampToValueAtTime(0.0001, end);
  thump.connect(thumpEnv);
  thumpEnv.connect(out);
  thump.start(start);
  thump.stop(end + 0.02);
}

/**
 * Whether a step of the playhead crossed this kill, and was a step rather than
 * a jump.
 *
 * Exported for its test: it is the whole rule, and the three ways it can be
 * wrong -- firing twice, firing while scrubbing, firing twenty times on a seek
 * -- are all silent faults inside a hook.
 */
export function crossed(fromMs: number, toMs: number, killMs: number): boolean {
  return toMs > fromMs && toMs - fromMs <= MAX_ADVANCE_MS && killMs > fromMs && killMs <= toMs;
}

/**
 * Fire a shot whenever playback carries the playhead over a kill.
 *
 * A store **subscription** and not a `tMs` selector: a selector would
 * re-render `MapStage` sixty times a second to make no visual change, and
 * `useLiveSnapshot`'s 200ms quantisation -- which is what the DOM reads -- is
 * audible lag on a gunshot.  `subscribe` runs on every store write with the
 * previous state in hand, which is exactly the edge this needs, and is the one
 * piece of edge detection in the interface; everything else recomputes from
 * scratch.
 *
 * Called once, from `MapStage`, rather than from either canvas: a canvas is
 * mounted per view, so the same kill would bang once in 2D, once in 3D, and
 * twice across the frame a reader switched between them.
 */
export function useKillSounds(model: ReplayModel): void {
  useEffect(
    () =>
      usePlayback.subscribe((state, previous) => {
        if (!state.playing) {
          return;
        }
        for (const kill of model.replay.kills) {
          /*
            The muzzle, not the impact.

            `views/tracers.ts` runs the bullet's flight so that it *lands* on
            the kill, which puts the shot that fired it a whole `FLIGHT_MS`
            earlier. Banging on `kill.t_ms` would put the report that far after
            the muzzle flash a reader is watching -- which does not read as a
            bug, it reads as the sound being vaguely out, and that is exactly
            the kind of fault nobody files.
          */
          if (crossed(previous.tMs, state.tMs, kill.t_ms - FLIGHT_MS)) {
            playShot();
          }
        }
      }),
    [model],
  );
}

/** Test seam: forget the audio graph and the throttle, keep the preference. */
export function resetAudioForTests(): void {
  context?.close?.();
  context = null;
  master = null;
  noise = null;
  lastShotAt = 0;
}
