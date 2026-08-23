/**
 * The round clock, in the row across the top of the stage.
 *
 * It floated over the middle of the map until a capture on a radar whose
 * playable area runs to the top of its own image showed what that cost: the
 * pill sat on the map, over the markers and callouts up there.  An overlay is
 * worth having only where there is nothing under it worth reading, and the
 * stage head already had room beside the view switch, so this is a cell in it.
 *
 * It counts **down**, because that is the number a player was looking at, and
 * an analysis tool that shows elapsed time makes the viewer do the subtraction
 * on every observation.
 *
 * What it counts down from is the round's own recorded length, not 1:40.  A
 * real round is a fixed timer plus a spike timer; what a capture holds is when
 * `roundStarted` fired and when the next one did, and those differ -- a buy
 * phase is inside the first, a pause inside another.  A fixed 1:40 would be a
 * clock the file does not carry.
 *
 * The spike state comes with it where there is one, because after a plant the
 * round clock stops being the thing that matters.  `Snapshot.spike_state` is
 * read from real `spikePlanted` / `spikeDefused` / `spikeExploded` events; what
 * it cannot say is *who* planted or *where*, since those events carry no actor
 * id -- so this shows the state and never a name.
 */

import type { Round } from "../api/types";
import { clockText, remainingMs } from "../model/roundclock";
import type { Snapshot } from "../model/state";
import { SPIKE_DEFUSED, SPIKE_EXPLODED, SPIKE_PLANTED } from "../model/state";
import { Icon, glyphs } from "./icons";

const SPIKE_WORDS: Record<string, string> = {
  [SPIKE_PLANTED]: "SPIKE DOWN",
  [SPIKE_DEFUSED]: "DEFUSED",
  [SPIKE_EXPLODED]: "DETONATED",
};

export function ClockPill({
  round,
  snap,
}: {
  round: Round | null;
  snap: Snapshot;
}) {
  if (round === null) {
    return null;
  }
  const spike = SPIKE_WORDS[snap.spikeState];
  return (
    <div className="clock-pill">
      <span className="pill-round">R{round.number}</span>
      <span className="pill-time numeric">
        <Icon glyph={glyphs.clock} size={13} />
        {clockText(remainingMs(round, snap.t_ms))}
      </span>
      {spike ? <span className={`pill-spike is-${snap.spikeState}`}>{spike}</span> : null}
    </div>
  );
}
