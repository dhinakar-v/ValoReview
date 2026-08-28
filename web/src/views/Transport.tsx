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
 * geometry and cannot be drawn into.  Which of those it draws is a layer
 * switch, so a round dense with utility can still be read for its kills.
 *
 * **A mark now carries whose it was, and answers when pointed at.**  Every tick
 * used to differ only in silhouette -- a stem, a triangle, a diamond, a square
 * -- which said what *kind* of event it was and never whose: a cast was drawn
 * in `--text-faint` whether an attacker or a defender made it.  So the side is
 * the ink and the lane, ATK above the rail and DEF below, and the shapes are
 * gone with the argument that justified them (at one pixel wide, colour alone
 * was a hue judgement -- but a lane is not a hue).  The tooltip renders
 * `roundevents.roundEvents`, which is the round timeline's **own** array, so a
 * tick and a row cannot say different things about one event.
 *
 * The kills are the exception and are DOM rather than ink: a skull is the glyph
 * this interface already uses for a kill, and painting one on the canvas would
 * mean a hand-copied outline that could drift from the one in the menu beside
 * it.  Ten spans a round is nothing, and it is what makes the layer testable
 * under jsdom, which gives a canvas no 2D context at all.
 *
 * The tooltip is hover-only and deliberately has no keyboard equivalent here,
 * because it already has one: the round-timeline dialog lists the same array,
 * is reachable by tab and seeks to any row.  A second keyboard path onto a
 * `<canvas>` would be a worse copy of it.
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
  remainingMs,
} from "../model/roundclock";
import { ICON_INLINE, Icon, glyphs } from "./icons";
import { palette, sideColour } from "./images";
import type { LayerKey } from "./playback";
import { seek, setBounds, usePlayback } from "./playback";
import type { Kind, RoundEvent } from "./roundevents";
import { roundEvents } from "./roundevents";
import { RoundStrip } from "./RoundStrip";
import { RoundTimeline } from "./RoundTimeline";
import { SHORTCUTS, useTransportKeys } from "./shortcuts";
import { IconButton, Modal, Segmented, Toggle } from "./ui";

const RAIL_HEIGHT = 40;
/** The rail line's own top edge. It is a centre line: there is a lane either side. */
const RAIL_Y = 20;
const RAIL_W = 2;

/*
  The two lanes, and the two mark lengths in each.

  Length and not weight separates a cast from an ultimate.  They share a lane
  and a colour -- the side owns both -- so the difference has to be a
  silhouette, the way the old shapes were, rather than a second hue judgement
  against a dark ground.  An ultimate fills its lane; a cast is a third of it.
*/
const CAST_LEN = 7;
const ULT_LEN = 16;
/** A mark whose side is unknown straddles the line rather than picking a lane. */
const UNKNOWN_LEN = 5;
const MARK_W = 2;

/** A skull is 14px, centred on the rail line. */
const SKULL_TOP = RAIL_Y + Math.round(RAIL_W / 2) - Math.round(ICON_INLINE / 2);

/** How near the pointer has to be, in CSS pixels, to raise a mark's tooltip. */
const HIT_PX = 6;
/** Kept equal to `.rail-tip`'s width in `app.css`, which is what it clamps. */
const TIP_W = 244;

/*
  Which switch draws which kind. One table, read by the canvas and the hover.

  A kind absent from it is drawn unconditionally, which today is the round-start
  marker: that mark is the round's own structure rather than an overlay on it,
  the way the planted spike on the map is deliberately ungated.  Every kind that
  *is* here has a row in `LayersMenu`'s `EVENT_LAYERS`, which `LayersMenu.test`
  proves by parsing this table -- so a new switch belongs in both or neither.
*/
const LAYER_FOR: Partial<Record<Kind, LayerKey>> = {
  kill: "kills",
  ability: "casts",
  ultimate: "ultimates",
  spike: "spike",
};

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

/**
 * Where a mark sits, given the side that made it.
 *
 * ATK above the rail and DEF below, and a null side -- a cast whose codename
 * two players share, so `abilities.attribute` refused to name a caster --
 * straddles the line in `--team-unknown`.  A lane is a claim about which side
 * acted, and there is nothing to base one on.
 */
function lane(side: string | null, length: number): { top: number; height: number } {
  if (side === "ATK") return { top: RAIL_Y - length, height: length };
  if (side === "DEF") return { top: RAIL_Y + RAIL_W, height: length };
  return { top: RAIL_Y - UNKNOWN_LEN, height: RAIL_W + UNKNOWN_LEN * 2 };
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
      seek(clock, next.action_start_ms);
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

    `toStart` is the barrier drop and not `start_ms`, which is the same instant
    the round strip and `[` / `]` land on.  The rail still spans from `start_ms`
    and so does `setBounds`, so the buy phase remains reachable by dragging --
    it is not where the transport puts you, only somewhere it lets you go.
  */
  const toStart = useCallback(
    () => seek(clock, round?.action_start_ms ?? 0),
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

        <Rail replay={replay} round={round} weapons={weapons} clock={clock} />

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

      {/*
        The key list is a dialog, not a drawer.

        It used to unfold *under* the bar, which pushed the whole transport up
        and left ten rows of hint text spread across a two-thousand-pixel
        window -- a legend as wide as the map it was explaining, with the
        stage's own caption stranded below it.  It is a reference somebody
        reads once and dismisses, which is what `ui.Modal` is for, and `fit`
        because ten rows is ten rows however wide the window is.
      */}
      {showKeys ? (
        <Modal title="Keyboard Shortcuts" size="fit" onClose={() => setShowKeys(false)}>
          <dl className="shortcuts">
            {SHORTCUTS.map((entry) => (
              <Fragment key={entry.keys}>
                <dt>
                  <span className="kbd">{entry.keys}</span>
                </dt>
                <dd>{entry.does}</dd>
              </Fragment>
            ))}
          </dl>
        </Modal>
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
 * fifteen-second window and each is one line rather than one element.  The
 * kills are the exception, and the file docstring says why.
 */
function Rail({
  replay,
  round,
  weapons,
  clock,
}: {
  replay: Replay;
  round: Round | null;
  /**
   * The weapon catalogue, threaded in for one reason: a kill's tooltip row
   * carries the killfeed silhouette of the gun, and that gun is **generated**
   * by `model/synthetic.ts` -- nothing decoded says who was holding what.  It
   * is the same row the round timeline shows, under the same SIMULATED chip.
   */
  weapons: Weapon[] | undefined;
  clock: PlaybackClock;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [hit, setHit] = useState<{ left: number; events: RoundEvent[] } | null>(null);
  const fromMs = round?.start_ms ?? 0;
  const spanMs = round?.duration_ms ?? replay.length_ms;

  /*
    One array, drawn and hit-tested and listed.

    `layers` is read as a subscription rather than through `getState()` inside
    `draw`, which is the whole of the fix for a fault that would otherwise have
    shipped silently: the canvas gated on the switches, and a hover that gated
    on nothing would have gone on tooltipping kills with KILLS switched off.
    The store hands back the same object until something is toggled, so this
    costs no extra render.
  */
  const layers = usePlayback((state) => state.layers);
  const shown = useMemo(
    () =>
      roundEvents(replay, round, weapons).filter(
        // The first-blood duplicate is dropped: it is a second mark on a
        // millisecond that already has one, and the tag it carries is the
        // modal's own way of surfacing that moment in a filtered list.
        (event) => {
          if (event.kind === "first") {
            return false;
          }
          const key = LAYER_FOR[event.kind];
          return key === undefined || layers[key];
        },
      ),
    [layers, replay, round, weapons],
  );

  /** A time as a fraction of the rail, which is how the skulls are placed. */
  const pctOf = useCallback(
    (ms: number) => Math.max(0, Math.min(100, ((ms - fromMs) / spanMs) * 100)),
    [fromMs, spanMs],
  );

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

      context.fillStyle = colours.border!;
      context.fillRect(0, RAIL_Y, width, RAIL_W);

      /*
        A mark is a filled rectangle on whole pixels, not a stroked line.

        The old tick stroked at `Math.round(x) + 0.5` with `lineWidth: 1`,
        which is the right half-pixel trick for a one-pixel stroke and the
        wrong one for anything wider: at two pixels the same offset paints a
        blurred three-pixel band.  `fillRect` has no such rule.
      */
      const mark = (
        ms: number,
        colour: string,
        top: number,
        markHeight: number,
        markWidth: number,
      ) => {
        context.fillStyle = colour;
        context.fillRect(
          Math.round(at(ms)) - Math.floor(markWidth / 2),
          top,
          markWidth,
          markHeight,
        );
      };

      /*
        The round's own beginning, drawn under everything else.

        Full height like the spike, because it is sideless -- there is no lane
        for an instant nobody caused.  `--text-muted` and not an event colour:
        it has to be unreadable as a spike (gold, green, orange), as a side (red,
        blue), as an unattributed mark (`--team-unknown`) and as the hover ring
        (magenta), and grey is what is left once this mark is about the round
        rather than about anybody in it.  First in the order, so anything landing
        on the same millisecond keeps the pixel.
      */
      for (const event of shown) {
        if (event.kind === "start") {
          mark(event.tMs, colours.muted!, 0, RAIL_HEIGHT, MARK_W);
        }
      }

      // Densest first and rarest last, so a spike that lands on the same
      // millisecond as a cast is the one still visible.
      for (const event of shown) {
        if (event.kind === "ability") {
          const box = lane(event.side, CAST_LEN);
          mark(event.tMs, sideColour(colours, event.side ?? ""), box.top, box.height, 1);
        }
      }
      for (const event of shown) {
        if (event.kind === "ultimate") {
          const box = lane(event.side, ULT_LEN);
          mark(
            event.tMs,
            sideColour(colours, event.side ?? ""),
            box.top,
            box.height,
            MARK_W,
          );
        }
      }
      for (const event of shown) {
        if (event.kind === "spike") {
          /*
            Full height, and coloured by what happened rather than by a side.
            These marks were once drawn in `--team-b` -- the defender's colour
            -- and a spike event carries no actor id at all, which is exactly
            the attribution `roundevents` states in words must never be made.
          */
          mark(
            event.tMs,
            spikeColour(colours, event.spikeKind ?? "planted"),
            0,
            RAIL_HEIGHT,
            MARK_W,
          );
        }
      }

      const playhead = Math.max(0, Math.min(width, at(usePlayback.getState().tMs)));
      context.fillStyle = colours.a!;
      context.fillRect(0, RAIL_Y, playhead, RAIL_W);
      context.beginPath();
      // Four and not five: the knob sits on a centre line with a lane either
      // side of it now, and every pixel of its radius is a pixel of somebody
      // else's mark that it covers as it passes.
      context.arc(playhead, RAIL_Y + RAIL_W / 2, 4, 0, Math.PI * 2);
      context.fillStyle = colours.text!;
      context.fill();
    },
    [fromMs, shown, spanMs],
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

  /*
    The kills, memoised as one element.

    `Transport` subscribes to the playhead, so this component re-renders sixty
    times a second while playing.  A stable element identity is what lets React
    skip the whole subtree on a frame that changed nothing about it.
  */
  const skulls = useMemo(
    () => (
      <div className="rail-kills">
        {shown
          .filter((event) => event.kind === "kill")
          .map((event) => (
            <span
              key={event.key}
              className={
                event.side ? `rail-skull side-${event.side.toLowerCase()}` : "rail-skull"
              }
              style={{ left: `${pctOf(event.tMs)}%`, top: SKULL_TOP }}
            >
              <Icon glyph={glyphs.kills} />
            </span>
          ))}
      </div>
    ),
    [pctOf, shown],
  );

  const scrub = (event: React.MouseEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const fraction = (event.clientX - rect.left) / rect.width;
    seek(clock, fromMs + fraction * spanMs);
  };

  /*
    What the pointer is over: the **nearest** mark, and then everything within
    `HIT_PX` of *that mark*, rather than everything within `HIT_PX` of the
    cursor.

    The difference matters twice.  A cursor-centred window changes membership
    on every pixel of a sweep, so a dense flurry reshuffles its own tooltip as
    the pointer crosses it; and it has no anchor, so there is nothing to pin
    the tooltip to but the cursor.  A mark-centred one holds still while the
    pointer stays nearest the same mark, which is what "the events at this
    moment" means.
  */
  const hover = (event: React.MouseEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0 || spanMs <= 0) {
      setHit(null);
      return;
    }
    // The unrounded position and the measured box, so a hit agrees with where
    // a skull was placed rather than with where a tick was rounded to.
    const at = (ms: number) => ((ms - fromMs) / spanMs) * rect.width;
    const x = event.clientX - rect.left;
    let nearest: RoundEvent | null = null;
    let best = Infinity;
    for (const candidate of shown) {
      const distance = Math.abs(at(candidate.tMs) - x);
      if (distance < best) {
        best = distance;
        nearest = candidate;
      }
    }
    if (nearest === null || best > HIT_PX) {
      setHit(null);
      return;
    }
    const anchor = at(nearest.tMs);
    const events = shown.filter(
      (candidate) => Math.abs(at(candidate.tMs) - anchor) <= HIT_PX,
    );
    const left = Math.max(TIP_W / 2, Math.min(rect.width - TIP_W / 2, anchor));
    setHit((previous) => {
      // Only where the set actually changed: a mousemove is a render otherwise.
      const same =
        previous !== null &&
        previous.left === left &&
        previous.events.length === events.length &&
        previous.events.every((row, index) => row.key === events[index]!.key);
      return same ? previous : { left, events };
    });
  };

  return (
    <div
      className="rail"
      onMouseDown={(event) => {
        /*
          Cleared on the way into a scrub as well as on the way out of the rail.

          `.scrim` sits below `--z-tooltip`, so a tooltip left standing would
          paint over an open dialog; and `e2e/harness.ts` parks the pointer
          before every screenshot precisely because a live tooltip is thousands
          of pixels of legitimate difference.
        */
        setHit(null);
        scrub(event);
      }}
      onMouseMove={(event) => {
        if (event.buttons === 1) {
          setHit(null);
          scrub(event);
          return;
        }
        hover(event);
      }}
      onMouseLeave={() => setHit(null)}
    >
      <canvas ref={canvasRef} className="strip" style={{ height: RAIL_HEIGHT }} />
      {skulls}
      {hit !== null ? (
        <div className="rail-tip" style={{ left: hit.left, transform: "translateX(-50%)" }}>
          {hit.events.map((event) => (
            <div className="ev-row" key={event.key}>
              {/* Time **remaining**, the same as every other clock here: a
                  Valorant round counts down, and elapsed-into-the-round is a
                  number nobody in the match could have read off their screen. */}
              <span className="ev-time numeric">
                {round === null
                  ? clockText(event.tMs)
                  : clockText(remainingMs(round, event.tMs))}
              </span>
              <span className="ev-body">{event.body}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export { clockText };
