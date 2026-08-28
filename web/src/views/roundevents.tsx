/**
 * Everything that happened in one round, as one array with two readers.
 *
 * This was `rowsFor` inside `RoundTimeline`, and it moved here the day the
 * transport rail grew a hover tooltip.  The rail and the modal were about to
 * answer the same question -- which agent, on which side, did what, to whom --
 * from two separate walks over `replay.kills`, `.ability_casts`, `.ultimates`
 * and `.spike`, and the second walk would have been free to disagree with the
 * first.  Now a tick and a row are the **same record**: the tooltip renders the
 * modal's own `body`, so a correction to a sentence lands in both places or in
 * neither.
 *
 * That is also what retires an argument this repository used to make out loud.
 * `LayersMenu` held that a 24px canvas cannot carry a legend and the layers
 * menu therefore *was* the legend, "provided the colours agree with what the
 * rail draws" -- a proviso nothing could check.  A mark answers for itself now,
 * and the agreement is structural rather than asserted.
 *
 * What is on each row and where it came from
 * ------------------------------------------
 *   time      real, and shown as time *into the round* rather than into the
 *             match, because a round is what is being read
 *   agent     real -- read off the pawn's archetype, named through Riot's
 *             catalogue
 *   side      generated: `infer` two-colours the kill graph into A and B and
 *             stops, so which of them attacked is assigned, not read
 *   ability   real name for X and C, the internal name read out of the
 *             archetype path for Q and E, which vary by agent
 *   weapon    generated, from `model/synthetic.ts`
 *
 * Two rows the reference has that this does not: **assists**, because
 * `characterDeath` carries a killer, a victim and a time and nothing else; and
 * **orbs**, which are not among the seven event groups at all.
 *
 * First blood is a second row at the same instant rather than a flag on the
 * first, which is the reference's own choice and a good one: it lets the
 * first-kill filter surface the moment in isolation instead of showing every
 * kill with one of them tinted.  The rail drops that duplicate -- it would be a
 * second mark on a millisecond that already has one -- so FIRST BLOOD is the
 * one thing the modal says and a tooltip does not.
 */

import type { AbilityCast, Replay, Round, Weapon } from "../api/types";
import type { Side } from "../model/synthetic";
import { sideOf, weaponArt, weaponInRound } from "../model/synthetic";

/**
 * A metre, in Unreal units.
 *
 * Riot's own arithmetic rather than a convention: their patch note for Sky
 * Smoke reads "Radius increased 410 >>> 415" for an ability the wiki gives
 * as 4.15 m. Mirrors `abilityfacts.UU_PER_METRE`, which is where the
 * argument is written down.
 */
const UU_PER_METRE = 100;

export type Kind = "kill" | "ability" | "ultimate" | "spike" | "first" | "start";

export interface RoundEvent {
  key: string;
  tMs: number;
  kind: Kind;
  side: Side | null;
  /**
   * `planted` / `defused` / `exploded` for a spike row, null for every other
   * kind.
   *
   * The one field here that exists for a single reader.  The modal needs only
   * the words in `SPIKE_WORDS`, but the rail draws the three spike events in
   * three different colours -- gold, green and orange -- and re-deriving which
   * one a row was by matching its rendered text would be a join through a
   * sentence.  It is deliberately not the start of a habit: a rail that wanted
   * a killer's side or an ability's slot should take the side and the body it
   * is already given.
   */
  spikeKind: string | null;
  /** Rendered content. Built here so both readers stay a map over one array. */
  body: React.ReactNode;
}

export const SPIKE_WORDS: Record<string, string> = {
  planted: "Spike planted",
  defused: "Spike defused",
  exploded: "Spike detonated",
};

function Name({ text, side }: { text: string; side: Side | null }) {
  return (
    <span className={side ? `ev-name side-${side.toLowerCase()}` : "ev-name"}>
      {text}
    </span>
  );
}

/**
 * Everything in one round, in time order, with first blood duplicated.
 *
 * `round` is nullable because the rail is: `activeRound` falls back to the
 * first round and then to null, which happens only for a capture `infer` found
 * no rounds in at all.  That case spans the whole file rather than returning
 * nothing -- the rail already draws a full-length scrubber there -- and has no
 * first-blood row, because the first kill of a capture is not one.
 *
 * The window is half-open, `[start_ms, end_ms)`.  The rail's own bound used to
 * be inclusive at the far end, so an event landing exactly on `end_ms` was
 * drawn hard against the right edge of a round it belongs *after*.  One rule,
 * and it is the modal's.
 */
export function roundEvents(
  replay: Replay,
  round: Round | null,
  weapons: Weapon[] | undefined,
): RoundEvent[] {
  const inRound = (t: number) =>
    round === null || (t >= round.start_ms && t < round.end_ms);
  // The agent, not the inferred group: this interface says ATK and DEF, and a
  // row already carries its side as a coloured left edge and a coloured name.
  const nameOf = (actorId: number) => {
    const player = replay.players.find((p) => p.actor_id === actorId);
    if (player === undefined) {
      return `#${actorId}`;
    }
    return player.agent || player.codename || player.label;
  };
  const sideAt = (actorId: number, tMs: number): Side | null => {
    const player = replay.players.find((p) => p.actor_id === actorId);
    return player ? sideOf(replay, player.team, tMs) : null;
  };

  const rows: RoundEvent[] = [];

  const kills = replay.kills.filter((kill) => inRound(kill.t_ms));
  for (const kill of kills) {
    const gun = weaponArt(weapons, weaponInRound(replay, kill.killer, kill.round_no));
    const side = sideAt(kill.killer, kill.t_ms);
    const body = (
      <>
        <Name text={nameOf(kill.killer)} side={side} />
        {gun?.killfeed_url ? (
          <img className="ev-weapon" src={gun.killfeed_url} alt="killed" />
        ) : (
          <span className="ev-arrow">killed</span>
        )}
        <Name text={nameOf(kill.victim)} side={sideAt(kill.victim, kill.t_ms)} />
      </>
    );
    rows.push({
      key: `kill-${kill.t_ms}-${kill.victim}`,
      tMs: kill.t_ms,
      kind: "kill",
      side,
      spikeKind: null,
      body,
    });
  }

  // The round's own first kill, repeated as its own tagged row.
  const first =
    round === null
      ? null
      : kills.reduce<(typeof kills)[number] | null>(
          (earliest, kill) =>
            earliest === null || kill.t_ms < earliest.t_ms ? kill : earliest,
          null,
        );
  if (first !== null) {
    rows.push({
      key: `first-${first.t_ms}`,
      tMs: first.t_ms,
      kind: "first",
      side: sideAt(first.killer, first.t_ms),
      spikeKind: null,
      body: (
        <>
          <Name text={nameOf(first.killer)} side={sideAt(first.killer, first.t_ms)} />
          <span className="ev-arrow">killed</span>
          <Name text={nameOf(first.victim)} side={sideAt(first.victim, first.t_ms)} />
          <span className="ev-tag">FIRST BLOOD</span>
        </>
      ),
    });
  }

  for (const cast of replay.ability_casts.filter((c) => inRound(c.t_ms))) {
    /*
      The **caster**, not `cast.actor_id`.

      `actor_id` on a cast is the first ability actor it spawned, and no player
      has that id -- so this resolved nobody and every ability row here was
      drawn with no side: no coloured edge, and invisible to the Attackers and
      Defenders filters two panels away.  Nothing failed, which is why it
      lasted.  `player_actor_id` is the join `abilities.attribute` makes, and
      it is null where two players share the agent rather than guessing one.

      That null now has to be drawn as well as listed.  The rail gives it the
      rail line itself in `--team-unknown` rather than a lane, because a lane
      is a claim about which side cast it.
    */
    const side = cast.player_actor_id === null ? null : sideAt(cast.player_actor_id, cast.t_ms);
    rows.push({
      key: `cast-${cast.t_ms}-${cast.actor_id}-${cast.internal_name}`,
      tMs: cast.t_ms,
      kind: "ability",
      side,
      spikeKind: null,
      body: (
        <>
          <Name text={cast.identity || nameOf(cast.actor_id)} side={side} />
          <span className="ev-verb">used</span>
          {cast.icon_url ? <img className="ev-ability" src={cast.icon_url} alt="" /> : null}
          {/* The published name where there is one and the name read out of
              the archetype path where there is not -- but never annotated as
              internal.  "(internal)" was a note to whoever built the decoder;
              to somebody watching a replay it labels the ability as a piece of
              plumbing rather than naming it. */}
          <span className="ev-thing">
            {cast.mechanics?.ability ?? cast.published_name ?? cast.internal_name}
          </span>
          {castFigures(cast)}
        </>
      ),
    });
  }

  for (const ult of replay.ultimates.filter((u) => inRound(u.t_ms))) {
    const side = sideAt(ult.actor_id, ult.t_ms);
    rows.push({
      key: `ult-${ult.t_ms}-${ult.actor_id}`,
      tMs: ult.t_ms,
      kind: "ultimate",
      side,
      spikeKind: null,
      body: (
        <>
          <Name text={nameOf(ult.actor_id)} side={side} />
          <span className="ev-verb">used their ultimate</span>
        </>
      ),
    });
  }

  /*
    The round's own beginning.

    `round.start_ms` is when `roundStarted` fired, which is the start of the buy
    phase; `action_start_ms` is when the barrier drops, and it is the moment a
    reader means by "the round".  It is skipped where the two are equal, which
    is `roundrules`' clamp saying the round was shorter than its own buy phase
    and there is no such instant inside it.
  */
  if (round !== null && round.action_start_ms > round.start_ms) {
    rows.push({
      key: `start-${round.action_start_ms}`,
      tMs: round.action_start_ms,
      kind: "start",
      // Sideless, like the spike: it is the round beginning, not somebody acting.
      side: null,
      spikeKind: null,
      body: <span className="ev-thing">Round starts</span>,
    });
  }

  for (const event of replay.spike.filter((s) => inRound(s.t_ms))) {
    rows.push({
      key: `spike-${event.t_ms}-${event.kind}`,
      tMs: event.t_ms,
      kind: "spike",
      // Deliberately null: a spike event carries no actor id, so it cannot be
      // attributed to a side and must not be coloured as though it could.
      side: null,
      spikeKind: event.kind,
      body: <span className="ev-thing">{SPIKE_WORDS[event.kind] ?? event.kind}</span>,
    });
  }

  // Ties broken by kind, not by key: a kill and its first-blood twin share a
  // millisecond, and sorting by key alphabetically put `first-` above `kill-`
  // so the round opened with a tag for an event that had not been listed yet.
  const rank: Record<Kind, number> = {
    // Ahead of everything: where anything shares the millisecond, the round
    // beginning is the line to read first.
    start: -1,
    spike: 0,
    ability: 1,
    ultimate: 2,
    kill: 3,
    first: 4,
  };
  return rows.sort((a, b) => a.tMs - b.tMs || rank[a.kind] - rank[b.kind]);
}

/**
 * What is known about the ability beside the name of it, and on whose word.
 *
 * Two different kinds of number sit here and the row has to keep them apart,
 * because they are the difference between a reading and a citation:
 *
 *   * the **flight** is decoded at both ends -- a projectile channel opened
 *     where the caster stood and a placed channel opened where the thing came
 *     to rest, and the capture states both instants. It carries no marking.
 *   * the **radius** and the **lifetime** are looked up in
 *     `vrfview.abilityfacts`, which is community research about a game that
 *     rebalances every few weeks. Each is drawn as a `.ev-figure`, which is
 *     the row's dashed-ring equivalent, and each carries its own source in a
 *     `title` so the page can be asked where the number came from.
 *
 * Every clause is refusable and most casts show none of them. A figure the
 * table does not publish is simply absent -- there is no "about" and no
 * nearest-ability fallback.
 *
 * Nothing here names a player and a damage figure in one sentence. A published
 * debuff is a property of the ability; saying it happened *to* somebody would
 * be a claim the file does not support.
 */
function castFigures(cast: AbilityCast) {
  const facts = cast.mechanics;
  const thrown = cast.flights.length === 1 ? cast.flights[0] : undefined;
  if (!facts && !thrown) {
    return null;
  }
  return (
    <>
      {thrown ? (
        <span className="ev-decoded">thrown {(thrown.duration_ms / 1000).toFixed(1)}s</span>
      ) : null}
      {facts?.radius_uu !== null && facts?.radius_uu !== undefined ? (
        <span className="ev-figure" title={facts.radius_source ?? undefined}>
          {(facts.radius_uu / UU_PER_METRE).toFixed(1)}m
        </span>
      ) : null}
      {facts?.duration_ms !== null && facts?.duration_ms !== undefined ? (
        <span className="ev-figure" title={facts.duration_source ?? undefined}>
          lasts {(facts.duration_ms / 1000).toFixed(1)}s
        </span>
      ) : null}
    </>
  );
}
