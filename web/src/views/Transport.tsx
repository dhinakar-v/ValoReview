/**
 * The timeline strip and the transport bar.
 *
 * The strip is a canvas rather than a row of divs for the same reason the
 * desktop one is: it draws a round band, every kill, every ultimate, every
 * spike event and every ability cast along one axis, and a themed widget owns
 * its own geometry and cannot be drawn into.
 *
 * Scrubbing is a seek, and a seek is exact.  `state_at` accumulates nothing, so
 * dragging backwards across a round boundary is exactly as correct as playing
 * forward to the same instant -- which is why the strip can jump anywhere
 * without the interface having to catch up.
 *
 * Step-to-event uses `Replay.event_times`, which the server already computes:
 * every kill, ultimate, spike event, round start and ability cast, sorted.  A
 * second implementation of that list in another language is exactly the drift
 * this project spends its docstrings avoiding.
 */

import { useCallback, useEffect, useRef } from "react";

import type { Replay } from "../api/types";
import type { PlaybackClock } from "../model/clock";
import { SPEEDS } from "../model/clock";
import { palette, teamColour } from "./images";
import { seek, usePlayback } from "./playback";

const STRIP_HEIGHT = 46;
const BAND_HEIGHT = 8;

export function Transport({ replay, clock }: { replay: Replay; clock: PlaybackClock }) {
  const playing = usePlayback((state) => state.playing);
  const speed = usePlayback((state) => state.speed);
  const tMs = usePlayback((state) => state.tMs);

  const step = (direction: 1 | -1) => {
    const times = replay.event_times;
    const found =
      direction > 0
        ? times.find((t) => t > tMs)
        : [...times].reverse().find((t) => t < tMs);
    seek(clock, found ?? (direction > 0 ? replay.length_ms : 0));
  };

  return (
    <div className="transport">
      <Strip replay={replay} clock={clock} />
      <div className="transport-bar">
        <button type="button" onClick={() => seek(clock, 0)} title="Back to the start">
          |&lt;
        </button>
        <button type="button" onClick={() => step(-1)} title="Previous event">
          &lt;&lt;
        </button>
        <button
          type="button"
          onClick={() => {
            // `play` from the end starts again at zero, which is the clock's
            // own rule rather than one re-decided here.
            clock.toggle();
            usePlayback.setState({ playing: clock.playing, tMs: clock.tMs });
          }}
        >
          {playing ? "PAUSE" : "PLAY"}
        </button>
        <button type="button" onClick={() => step(1)} title="Next event">
          &gt;&gt;
        </button>
        <button
          type="button"
          onClick={() => seek(clock, replay.length_ms)}
          title="To the end"
        >
          &gt;|
        </button>
        <span className="mono clock-readout">
          {clockText(tMs)} / {clockText(replay.length_ms)}
        </span>
        <div className="spacer" />
        {SPEEDS.map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={speed === value}
            onClick={() => usePlayback.setState({ speed: value })}
          >
            {value}&times;
          </button>
        ))}
      </div>
    </div>
  );
}

function Strip({ replay, clock }: { replay: Replay; clock: PlaybackClock }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const draw = useCallback(
    (canvas: HTMLCanvasElement) => {
      const context = canvas.getContext("2d");
      if (context === null || replay.length_ms <= 0) {
        return;
      }
      const colours = palette(canvas);
      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth;
      const height = STRIP_HEIGHT;
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);

      const at = (ms: number) => (ms / replay.length_ms) * width;

      // The round band. A decided round is its winner's colour; an undecided
      // one is the neutral grey, because `infer` leaves an explicit unknown
      // rather than guessing and this must not quietly resolve it.
      for (const round of replay.rounds) {
        const left = at(round.start_ms);
        const right = at(round.end_ms);
        context.fillStyle = round.decided
          ? teamColour(colours, round.winner)
          : colours.unknown!;
        context.globalAlpha = round.decided ? 0.45 : 0.25;
        context.fillRect(left, 4, Math.max(1, right - left - 1), BAND_HEIGHT);
        context.globalAlpha = 1;
        context.fillStyle = colours.muted!;
        context.font = "9px system-ui, sans-serif";
        context.textAlign = "left";
        context.fillText(String(round.number), left + 2, 4 + BAND_HEIGHT + 10);
      }

      const tick = (ms: number, colour: string, top: number, bottom: number) => {
        const x = at(ms);
        context.strokeStyle = colour;
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(x + 0.5, top);
        context.lineTo(x + 0.5, bottom);
        context.stroke();
      };

      for (const cast of replay.ability_casts) {
        tick(cast.t_ms, colours.muted!, height - 10, height - 4);
      }
      for (const kill of replay.kills) {
        tick(kill.t_ms, colours.text!, height - 20, height - 8);
      }
      for (const ult of replay.ultimates) {
        tick(ult.t_ms, colours.ult!, height - 26, height - 14);
      }
      for (const event of replay.spike) {
        tick(event.t_ms, colours.b!, height - 30, height - 18);
      }

      const playhead = at(usePlayback.getState().tMs);
      context.strokeStyle = colours.text!;
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(playhead, 0);
      context.lineTo(playhead, height);
      context.stroke();
    },
    [replay],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    let frame = 0;
    const loop = () => {
      draw(canvas);
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [draw]);

  const scrub = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const fraction = (event.clientX - rect.left) / rect.width;
    seek(clock, fraction * replay.length_ms);
  };

  return (
    <canvas
      ref={canvasRef}
      className="strip"
      style={{ height: STRIP_HEIGHT }}
      onMouseDown={scrub}
      onMouseMove={(event) => {
        if (event.buttons === 1) {
          scrub(event);
        }
      }}
    />
  );
}

export function clockText(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}
