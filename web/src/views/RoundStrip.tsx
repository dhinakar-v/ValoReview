/**
 * Every round as a chip, and the whole match's history in one row.
 *
 * A chip is the unit of navigation here, because a round is the unit of
 * analysis: the old strip was one twenty-six minute axis, which gave round four
 * about forty pixels and made "watch round four" a drag rather than a click.
 *
 * The underline under each chip is the round's **inferred** winner.  `infer`
 * two-colours the kill graph and awards a round on the first terminal condition
 * inside its window; a defuse and a detonation leave the winner explicitly
 * unknown, because spike events carry no actor id and there is nothing to
 * attribute them to.  Those chips get the neutral colour and must keep it --
 * quietly resolving them here would put a claim on screen that the model
 * refused to make.
 *
 * The reference's strip is a fixed 28 chips: twelve, a swap, twelve, four
 * overtime slots.  This one is `replay.rounds.length`, because a recording is
 * as long as it is -- the reference capture holds fifteen -- and drawing empty
 * slots for rounds that were never recorded would invent a match structure.
 * The swap marker between the halves *is* drawn, and it is real: it comes from
 * `Replay.side_swap_ms`, the container's own `switchTeams` event.
 */

import type { Replay, Round } from "../api/types";
import { Icon, glyphs } from "./icons";

function toneOf(round: Round): string {
  if (!round.decided) {
    return "is-open";
  }
  return round.winner === "A" ? "is-a" : round.winner === "B" ? "is-b" : "is-open";
}

export function RoundStrip({
  replay,
  active,
  onPick,
}: {
  replay: Replay;
  active: Round | null;
  onPick: (round: Round) => void;
}) {
  const swap = replay.side_swap_ms;
  return (
    <div className="round-strip" role="group" aria-label="Rounds">
      {replay.rounds.map((round, index) => {
        const previous = replay.rounds[index - 1];
        // The marker goes between the last round of one half and the first of
        // the next, which is wherever `switchTeams` fell.
        const swapsHere =
          swap !== null &&
          previous !== undefined &&
          previous.start_ms < swap &&
          round.start_ms >= swap;
        return (
          <span className="round-slot" key={round.number}>
            {swapsHere ? (
              // A rule and a word, not a glyph wedged between two numbers,
              // where it read as a third kind of round.
              <span className="round-swap" title="Halftime side swap">
                <Icon glyph={glyphs.swap} size={12} />
                HALF
              </span>
            ) : null}
            <button
              type="button"
              className={`round-chip ${toneOf(round)}${
                active?.number === round.number ? " is-active" : ""
              }`}
              aria-pressed={active?.number === round.number}
              title={
                round.decided
                  ? `Round ${round.number} — ${round.winner} won by ${round.reason}`
                  : `Round ${round.number} — no winner could be derived`
              }
              onClick={() => onPick(round)}
            >
              {round.number}
            </button>
          </span>
        );
      })}
    </div>
  );
}
