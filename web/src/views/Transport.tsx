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
 * this project spends its docstrings avoiding -- and the keyboard bindings call
 * this file's own `step` for the same reason.
 *
 * Two things here are addressed by the Playwright suite and must not move:
 * `title="Back to the start"` and `title="Next event"` are how a spec presses
 * them, and `.clock-readout` is asserted to have exactly `M:SS / M:SS` as its
 * text -- so no icon and no extra word may go inside that span.
 */

import { Fragment, useCallback, useEffect, useRef, useState } from "react";

import type { Replay } from "../api/types";
import type { PlaybackClock } from "../model/clock";
import { SPEEDS } from "../model/clock";
import { Icon, glyphs } from "./icons";
import { palette, teamColour } from "./images";
import { seek, usePlayback } from "./playback";
import { SHORTCUTS, useTransportKeys } from "./shortcuts";
import { play } from "./sound";
import { IconButton, Segmented } from "./ui";

const STRIP_HEIGHT = 56;
const BAND_HEIGHT = 10;
/** Where the round band sits, leaving room for its numbers underneath. */
const BAND_TOP = 6;

export function Transport({
  replay,
  clock,
  layers,
}: {
  replay: Replay;
  clock: PlaybackClock;
  /** Which layer switches the stage is drawing, so the keys match them. */
  layers: { sight: boolean; callouts: boolean };
}) {
  const playing = usePlayback((state) => state.playing);
  const speed = usePlayback((state) => state.speed);
  const tMs = usePlayback((state) => state.tMs);
  const [showKeys, setShowKeys] = useState(false);

  // `tMs` is read from the store rather than closed over, which is what keeps
  // this callback stable.  This component re-renders on every animation frame
  // while playing, and a `step` that changed identity each time tore down and
  // rebuilt the window keydown listener sixty times a second -- the value read
  // is the same one either way.
  const step = useCallback(
    (direction: 1 | -1) => {
      const now = usePlayback.getState().tMs;
      const times = replay.event_times;
      const found =
        direction > 0
          ? times.find((t) => t > now)
          : [...times].reverse().find((t) => t < now);
      seek(clock, found ?? (direction > 0 ? replay.length_ms : 0));
      play("tick");
    },
    [clock, replay.event_times, replay.length_ms],
  );

  const seekTo = useCallback((ms: number) => seek(clock, ms), [clock]);

  // The keys do exactly what the buttons do, by calling the same functions.
  useTransportKeys({ clock, step, seekTo, lengthMs: replay.length_ms, layers });

  const toggle = () => {
    // `PlaybackClock.play` from the end starts again at zero, which is the
    // clock's own rule rather than one re-decided here.
    clock.toggle();
    usePlayback.setState({ playing: clock.playing, tMs: clock.tMs });
    play("click");
  };

  return (
    <div className="transport">
      <Strip replay={replay} clock={clock} />
      <div className="legend">
        <span className="team-unknown">
          <i /> round band
        </span>
        <span>
          <i /> ability cast
        </span>
        <span style={{ color: "var(--text-primary)" }}>
          <i /> kill
        </span>
        <span style={{ color: "var(--ult)" }}>
          <i /> ultimate
        </span>
        <span style={{ color: "var(--accent-b)" }}>
          <i /> spike
        </span>
      </div>
      <div className="transport-bar">
        <IconButton
          label="Back to the start"
          icon={glyphs.toStart}
          variant="default"
          onClick={() => seek(clock, 0)}
        />
        <IconButton
          label="Previous event"
          icon={glyphs.prevEvent}
          variant="default"
          onClick={() => step(-1)}
        />
        <button type="button" className="primary" onClick={toggle}>
          <Icon glyph={playing ? glyphs.pause : glyphs.play} />
          <span>{playing ? "PAUSE" : "PLAY"}</span>
        </button>
        <IconButton
          label="Next event"
          icon={glyphs.nextEvent}
          variant="default"
          onClick={() => step(1)}
        />
        <IconButton
          label="To the end"
          icon={glyphs.toEnd}
          variant="default"
          onClick={() => seek(clock, replay.length_ms)}
        />
        {/* Exactly two clocks and nothing else: a Playwright spec asserts this
            span's whole text is `M:SS / M:SS`. */}
        <span className="mono clock-readout">
          {clockText(tMs)} / {clockText(replay.length_ms)}
        </span>
        <div className="spacer" />
        <Segmented
          label="Playback speed"
          options={SPEEDS}
          value={speed}
          onChange={(next) => usePlayback.setState({ speed: next })}
          format={(value) => ({ label: `${value}×` })}
        />
        <IconButton
          label="Keyboard shortcuts"
          icon={glyphs.keys}
          pressed={showKeys}
          onClick={() => setShowKeys((on) => !on)}
        />
      </div>
      {showKeys ? (
        <div className="legend" style={{ paddingBottom: "var(--space-3)" }}>
          <div className="shortcuts">
            {SHORTCUTS.map((entry) => (
              <Fragment key={entry.keys}>
                <span className="kbd">{entry.keys}</span>
                <span>{entry.does}</span>
              </Fragment>
            ))}
          </div>
        </div>
      ) : null}
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
        const span = Math.max(1, right - left - 1);
        context.fillStyle = round.decided
          ? teamColour(colours, round.winner)
          : colours.unknown!;
        context.globalAlpha = round.decided ? 0.5 : 0.22;
        roundedRect(context, left, BAND_TOP, span, BAND_HEIGHT, 2);
        context.fill();
        context.globalAlpha = 1;
        context.fillStyle = colours.faint!;
        context.font = "9px system-ui, sans-serif";
        context.textAlign = "left";
        context.fillText(String(round.number), left + 2, BAND_TOP + BAND_HEIGHT + 10);
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
      // A head on the playhead, so the current instant is findable on a strip
      // carrying three thousand tick marks.
      context.fillStyle = colours.text!;
      context.beginPath();
      context.moveTo(playhead - 4, 0);
      context.lineTo(playhead + 4, 0);
      context.lineTo(playhead, 5);
      context.closePath();
      context.fill();
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
      onMouseDown={(event) => {
        play("click");
        scrub(event);
      }}
      onMouseMove={(event) => {
        if (event.buttons === 1) {
          scrub(event);
        }
      }}
    />
  );
}

/** A rectangle with soft corners, which `roundRect` gives where it exists. */
function roundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  context.beginPath();
  if (typeof context.roundRect === "function") {
    context.roundRect(x, y, width, height, radius);
    return;
  }
  context.rect(x, y, width, height);
}

export function clockText(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}
