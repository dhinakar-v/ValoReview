/**
 * The round strip and the transport bar.
 *
 * Both are scoped to a round, which is the change that matters here.  The strip
 * used to be one canvas spanning the whole capture with a round band drawn
 * across it: the right model of the *file* and the wrong model of the *task*,
 * because nobody watches twenty-six minutes end to end, and round four got
 * about forty pixels of scrubber.  Now the chips pick a round and everything
 * below them -- the rail, the countdown, the step keys, the loop -- works
 * inside it.
 *
 * The rail is still a canvas rather than an `<input type="range">`, and for the
 * same reason it always was: it draws every kill, ultimate, spike event and
 * ability cast in the round along one axis, and a themed widget owns its own
 * geometry and cannot be drawn into.  Which of those it draws is now a layer
 * switch, so a round dense with utility can still be read for its kills.
 *
 * Scrubbing is a seek, and a seek is exact.  `stateAt` accumulates nothing, so
 * dragging backwards across a round boundary is exactly as correct as playing
 * forward to the same instant.
 *
 * Step-to-event uses `Replay.event_times`, which the server already computes,
 * filtered to the round.  A second implementation of that list in another
 * language is exactly the drift this project spends its docstrings avoiding --
 * and the keyboard bindings call this file's own `step` for the same reason.
 *
 * Three things here are addressed by the Playwright suite and must not move:
 * `title="Back to the start"` and `title="Next event"` are how a spec presses
 * them, and `.clock-readout` is asserted to have exactly `M:SS / M:SS` as its
 * text -- so no icon and no extra word may go inside that span.
 */

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Replay, Round, Weapon } from "../api/types";
import type { PlaybackClock } from "../model/clock";
import { SPEEDS } from "../model/clock";
import { activeRound, clockText, elapsedMs, eventTimesIn } from "../model/roundclock";
import { Icon, glyphs } from "./icons";
import { palette } from "./images";
import { seek, setBounds, usePlayback } from "./playback";
import { RoundStrip } from "./RoundStrip";
import { RoundTimeline } from "./RoundTimeline";
import { SHORTCUTS, useTransportKeys } from "./shortcuts";
import { IconButton, Segmented } from "./ui";

const RAIL_HEIGHT = 24;
/** Where the rail itself sits, leaving the event ticks the room above it. */
const RAIL_Y = 17;

export function Transport({
  replay,
  clock,
  weapons,
  layers,
}: {
  replay: Replay;
  clock: PlaybackClock;
  weapons: Weapon[] | undefined;
  /** Which layer switches the stage is drawing, so the keys match them. */
  layers: { sight: boolean; callouts: boolean };
}) {
  const playing = usePlayback((state) => state.playing);
  const speed = usePlayback((state) => state.speed);
  const tMs = usePlayback((state) => state.tMs);
  const roundNo = usePlayback((state) => state.roundNo);
  const [showKeys, setShowKeys] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [looping, setLooping] = useState(false);

  const round = activeRound(replay, roundNo, tMs);

  /*
    The window the driver enforces.  Written from here rather than held in the
    store because the frame loop is its only reader: publishing it would
    re-render this bar sixty times a second to hand back a number it already
    had.
  */
  useEffect(() => {
    setBounds(round === null ? null : { fromMs: round.start_ms, toMs: round.end_ms });
    return () => setBounds(null);
  }, [round]);

  const pick = useCallback(
    (next: Round) => {
      usePlayback.setState({ roundNo: next.number });
      seek(clock, next.start_ms);
    },
    [clock],
  );

  const stepRound = useCallback(
    (direction: 1 | -1) => {
      const index = replay.rounds.findIndex((entry) => entry.number === round?.number);
      const next = replay.rounds[index + direction];
      if (next !== undefined) {
        pick(next);
      }
    },
    [pick, replay.rounds, round],
  );

  // `tMs` is read from the store rather than closed over, which is what keeps
  // this callback stable.  This component re-renders on every animation frame
  // while playing, and a `step` that changed identity each time tore down and
  // rebuilt the window keydown listener sixty times a second -- the value read
  // is the same one either way.
  const times = useMemo(() => eventTimesIn(replay, round), [replay, round]);
  const step = useCallback(
    (direction: 1 | -1) => {
      const now = usePlayback.getState().tMs;
      const found =
        direction > 0
          ? times.find((t) => t > now)
          : [...times].reverse().find((t) => t < now);
      const edge =
        direction > 0 ? (round?.end_ms ?? replay.length_ms) : (round?.start_ms ?? 0);
      seek(clock, found ?? edge);
    },
    [clock, replay.length_ms, round, times],
  );

  const seekTo = useCallback((ms: number) => seek(clock, ms), [clock]);

  // The keys do exactly what the buttons do, by calling the same functions.
  useTransportKeys({
    clock,
    step,
    seekTo,
    lengthMs: replay.length_ms,
    stepRound,
    layers,
  });

  /*
    Looping is a rule the transport applies, not a mode the clock has: when the
    playhead reaches the end of the round it goes back to that round's start.
    `PlaybackClock` is a byte-for-byte port pinned by `tests/golden/clock.json`
    in two languages, so a loop flag inside it would break parity before it
    played anything twice.
  */
  useEffect(() => {
    if (!looping || round === null || tMs < round.end_ms - 1) {
      return;
    }
    seek(clock, round.start_ms);
    clock.play();
    usePlayback.setState({ playing: true });
  }, [clock, looping, round, tMs]);

  const toggle = () => {
    // From the end of a round, play starts that round again rather than the
    // capture: the transport is scoped, so its idea of "again" is too.
    if (round !== null && !clock.playing && tMs >= round.end_ms - 1) {
      seek(clock, round.start_ms);
    }
    clock.toggle();
    usePlayback.setState({ playing: clock.playing, tMs: clock.tMs });
  };

  return (
    <div className="transport">
      <RoundStrip replay={replay} active={round} onPick={pick} />

      <div className="transport-bar">
        <IconButton
          label="Back to the start"
          icon={glyphs.toStart}
          variant="default"
          onClick={() => seek(clock, round?.start_ms ?? 0)}
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
          onClick={() => seek(clock, round?.end_ms ?? replay.length_ms)}
        />

        <Rail replay={replay} round={round} clock={clock} />

        {/* Exactly two clocks and nothing else: a Playwright spec asserts this
            span's whole text is `M:SS / M:SS`. */}
        <span className="mono clock-readout">
          {round === null ? clockText(tMs) : clockText(elapsedMs(round, tMs))} /{" "}
          {round === null ? clockText(replay.length_ms) : clockText(round.duration_ms)}
        </span>

        <IconButton
          label="Loop this round"
          icon={glyphs.loop}
          pressed={looping}
          onClick={() => setLooping((on) => !on)}
        />
        <Segmented
          label="Playback speed"
          options={SPEEDS}
          value={speed}
          onChange={(next) => usePlayback.setState({ speed: next })}
          format={(value) => ({ label: `${value}×` })}
        />
        <IconButton
          label="Round timeline"
          icon={glyphs.timeline}
          pressed={showTimeline}
          onClick={() => setShowTimeline(true)}
        />
        <IconButton
          label="Keyboard shortcuts"
          icon={glyphs.keys}
          pressed={showKeys}
          onClick={() => setShowKeys((on) => !on)}
        />
      </div>

      {showKeys ? (
        <div className="shortcuts">
          {SHORTCUTS.map((entry) => (
            <Fragment key={entry.keys}>
              <span className="kbd">{entry.keys}</span>
              <span>{entry.does}</span>
            </Fragment>
          ))}
        </div>
      ) : null}

      {showTimeline && round !== null ? (
        <RoundTimeline
          replay={replay}
          round={round}
          weapons={weapons}
          onPick={pick}
          onSeek={(ms) => seek(clock, ms)}
          onClose={() => setShowTimeline(false)}
        />
      ) : null}
    </div>
  );
}

/**
 * The scrubber: a rail across one round, with that round's events on it.
 *
 * Drawn rather than laid out, because there can be a hundred marks in a
 * fifteen-second window and each is one line rather than one element.
 */
function Rail({
  replay,
  round,
  clock,
}: {
  replay: Replay;
  round: Round | null;
  clock: PlaybackClock;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fromMs = round?.start_ms ?? 0;
  const spanMs = round?.duration_ms ?? replay.length_ms;

  const draw = useCallback(
    (canvas: HTMLCanvasElement) => {
      const context = canvas.getContext("2d");
      if (context === null || spanMs <= 0) {
        return;
      }
      const colours = palette(canvas);
      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth;
      const height = RAIL_HEIGHT;
      if (
        canvas.width !== Math.round(width * dpr) ||
        canvas.height !== Math.round(height * dpr)
      ) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);

      const at = (ms: number) => ((ms - fromMs) / spanMs) * width;
      const inRound = (ms: number) => ms >= fromMs && ms <= fromMs + spanMs;
      const layers = usePlayback.getState().layers;

      context.fillStyle = colours.border!;
      context.fillRect(0, RAIL_Y, width, 2);

      const tick = (ms: number, colour: string, top: number) => {
        if (!inRound(ms)) {
          return;
        }
        const x = at(ms);
        context.strokeStyle = colour;
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(x + 0.5, top);
        context.lineTo(x + 0.5, RAIL_Y);
        context.stroke();
      };

      if (layers.casts) {
        for (const cast of replay.ability_casts) {
          tick(cast.t_ms, colours.muted!, 11);
        }
      }
      if (layers.kills) {
        for (const kill of replay.kills) {
          tick(kill.t_ms, colours.text!, 5);
        }
      }
      if (layers.ultimates) {
        for (const ult of replay.ultimates) {
          tick(ult.t_ms, colours.ult!, 0);
        }
      }
      if (layers.spike) {
        for (const event of replay.spike) {
          tick(event.t_ms, colours.b!, 0);
        }
      }

      const playhead = Math.max(0, Math.min(width, at(usePlayback.getState().tMs)));
      context.fillStyle = colours.a!;
      context.fillRect(0, RAIL_Y, playhead, 2);
      context.beginPath();
      context.arc(playhead, RAIL_Y + 1, 5, 0, Math.PI * 2);
      context.fillStyle = colours.text!;
      context.fill();
    },
    [fromMs, replay, spanMs],
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
    seek(clock, fromMs + fraction * spanMs);
  };

  return (
    <canvas
      ref={canvasRef}
      className="strip"
      style={{ height: RAIL_HEIGHT }}
      onMouseDown={scrub}
      onMouseMove={(event) => {
        if (event.buttons === 1) {
          scrub(event);
        }
      }}
    />
  );
}

export { clockText };
