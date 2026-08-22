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

import type { ReactNode } from "react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Replay, Round, Weapon } from "../api/types";
import type { PlaybackClock } from "../model/clock";
import { SPEEDS } from "../model/clock";
import {
  activeRound,
  clampToRound,
  clockText,
  elapsedMs,
  eventTimesIn,
} from "../model/roundclock";
import { Icon, glyphs } from "./icons";
import { palette } from "./images";
import { seek, setBounds, usePlayback } from "./playback";
import { RoundStrip } from "./RoundStrip";
import { RoundTimeline } from "./RoundTimeline";
import { SHORTCUTS, useTransportKeys } from "./shortcuts";
import { IconButton, Segmented, Toggle } from "./ui";

const RAIL_HEIGHT = 24;
/** Where the rail itself sits, leaving the event ticks the room above it. */
const RAIL_Y = 17;

/** Half-width of a tick's head, in CSS pixels. */
const HEAD = 3;

/** The shapes a tick head can take, one per kind of event. */
type Head = "triangle" | "diamond" | "square";

/**
 * A spike tick's colour, by what the event was.
 *
 * `--spike-armed`, `--spike-safe` and `--spike-boom` have been in the palette
 * since it was written and nothing had ever read them; the rail drew every
 * spike event in the defender's blue instead, which attributes a sideless
 * event to a side.
 */
function spikeColour(colours: Record<string, string>, kind: string): string {
  if (kind === "defused") return colours.spikeSafe!;
  if (kind === "exploded") return colours.spikeBoom!;
  return colours.spikeArmed!;
}

export function Transport({
  replay,
  clock,
  weapons,
  layers,
  children,
}: {
  replay: Replay;
  clock: PlaybackClock;
  weapons: Weapon[] | undefined;
  /** Which layer switches the stage is drawing, so the keys match them. */
  layers: { sight: boolean; callouts: boolean };
  /**
   * Anything the stage wants in the control row, which today is the layers
   * menu.  Passed in rather than imported so this component keeps knowing
   * nothing about layers beyond the two booleans the keys need -- `MapStage`
   * owns which of them are available, and it is the one holding the mask.
   */
  children?: ReactNode;
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

  /*
    Every seek goes through the round.

    `clampToRound` had been sitting unused in `roundclock` while the frame loop
    clamped only the *upper* edge -- so a nudge backwards at a round's first
    millisecond walked the playhead into the previous round with the rail, the
    countdown and the chip strip all still scoped to this one.  Clamping here
    puts the bound in the one place that knows which round is picked, which is
    also what lets the keys stop doing arithmetic of their own.
  */
  const seekTo = useCallback(
    (ms: number) =>
      seek(
        clock,
        round === null
          ? Math.max(0, Math.min(replay.length_ms, ms))
          : clampToRound(round, ms),
      ),
    [clock, replay.length_ms, round],
  );

  /*
    The two ends of the round, hoisted so the buttons and the keys are the same
    reference rather than two expressions that happen to agree today.  This is
    the fix for Home and End: they were absolute seeks in a round-scoped
    transport, and now they simply are these.
  */
  const toStart = useCallback(
    () => seek(clock, round?.start_ms ?? 0),
    [clock, round],
  );
  const toEnd = useCallback(
    () => seek(clock, round?.end_ms ?? replay.length_ms),
    [clock, replay.length_ms, round],
  );

  // The keys do exactly what the buttons do, by calling the same functions.
  useTransportKeys({
    clock,
    step,
    seekTo,
    toStart,
    toEnd,
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
          onClick={toStart}
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
          onClick={toEnd}
        />

        <Rail replay={replay} round={round} clock={clock} />

        {/* Exactly two clocks and nothing else: a Playwright spec asserts this
            span's whole text is `M:SS / M:SS`. */}
        <span className="mono clock-readout">
          {round === null ? clockText(tMs) : clockText(elapsedMs(round, tMs))} /{" "}
          {round === null ? clockText(replay.length_ms) : clockText(round.duration_ms)}
        </span>

        <Segmented
          label="Playback speed"
          options={SPEEDS}
          value={speed}
          onChange={(next) => usePlayback.setState({ speed: next })}
          format={(value) => ({ label: `${value}×` })}
        />
        {/*
          LOOP carries its word.

          As a bare `Repeat` glyph jammed against the clock it read as neither
          a reset nor a loop -- the UI review called it "useless" and could not
          tell what it did -- which is the house rule catching up with a
          control that had quietly broken it: an icon sits beside a label, and
          `IconButton` is the sole exception for glyphs whose meaning is not in
          dispute.  It also moves off the clock's shoulder, so the readout is
          flanked by the rail and the speed control instead.
        */}
        <Toggle
          label="LOOP"
          icon={glyphs.loop}
          pressed={looping}
          title="Replay this round when it reaches the end"
          onChange={() => setLooping((on) => !on)}
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
        {children}
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

      /*
        A tick is a stem and a head, and the head says what kind of event it is.

        Every mark used to be a bare 1px line, differing only in colour and in
        how far up it started -- so the strip could be read by hovering and no
        other way.  Now each kind has a silhouette as well: a stem alone, a
        downward triangle, a diamond, a square.  Shape *and* colour, because at
        one pixel wide colour alone is a hue judgement against a dark ground.

        The heads are drawn at the top of the stem rather than on the rail, so
        a dense round of casts stays a comb rather than a solid bar.
      */
      const tick = (ms: number, colour: string, top: number, head?: Head) => {
        if (!inRound(ms)) {
          return;
        }
        const x = Math.round(at(ms)) + 0.5;
        context.strokeStyle = colour;
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(x, top + (head === undefined ? 0 : HEAD));
        context.lineTo(x, RAIL_Y);
        context.stroke();
        if (head === undefined) {
          return;
        }
        context.fillStyle = colour;
        context.beginPath();
        if (head === "triangle") {
          context.moveTo(x - HEAD, top);
          context.lineTo(x + HEAD, top);
          context.lineTo(x, top + HEAD);
        } else if (head === "diamond") {
          context.moveTo(x, top);
          context.lineTo(x + HEAD, top + HEAD);
          context.lineTo(x, top + HEAD * 2);
          context.lineTo(x - HEAD, top + HEAD);
        } else {
          context.rect(x - HEAD, top, HEAD * 2, HEAD * 2);
        }
        context.closePath();
        context.fill();
      };

      // Densest first and rarest last, so a spike that lands on the same
      // millisecond as a cast is the one still visible.
      if (layers.casts) {
        for (const cast of replay.ability_casts) {
          tick(cast.t_ms, colours.faint!, 12);
        }
      }
      if (layers.kills) {
        for (const kill of replay.kills) {
          tick(kill.t_ms, colours.text!, 4, "triangle");
        }
      }
      if (layers.ultimates) {
        for (const ult of replay.ultimates) {
          tick(ult.t_ms, colours.ult!, 0, "diamond");
        }
      }
      if (layers.spike) {
        for (const event of replay.spike) {
          /*
            Coloured by what happened, not by a side.  These ticks were drawn
            in `--team-b` -- the defender colour -- and a spike event carries
            no actor id at all, which is exactly the attribution
            `RoundTimeline` states in words must never be made.  The three
            spike colours already existed in the palette and nothing was using
            them.
          */
          tick(event.t_ms, spikeColour(colours, event.kind), 0, "square");
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
