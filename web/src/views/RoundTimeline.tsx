/**
 * One round, as a list of everything that happened in it.
 *
 * No positions are involved and none are needed: this answers which agent, on
 * which side, did what at what time, and to whom.  That is four of the seven
 * event groups a `.vrf` carries plus the casts `abilities.py` infers from the
 * actors they spawn, and it is available on any capture that parses -- a
 * replay with no decode at all still has kills, rounds and a side swap.
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
 * **orbs**, which are not among the seven event groups at all.  Two of its
 * filters go with them.  A checkbox that can never match anything is worse than
 * its absence -- the same argument that keeps `SIGHT` off a map with no mask.
 *
 * First blood is a second row at the same instant rather than a flag on the
 * first, which is the reference's own choice and a good one: it lets the
 * first-kill filter surface the moment in isolation instead of showing every
 * kill with one of them tinted.
 */

import { useMemo, useState } from "react";

import type { Replay, Round, Weapon } from "../api/types";
import { clockText } from "../model/roundclock";
import type { Side } from "../model/synthetic";
import { sideOf, weaponArt, weaponInRound } from "../model/synthetic";
import { Icon, glyphs } from "./icons";
import { CheckRow, IconButton, Modal } from "./ui";

type Kind = "kill" | "ability" | "ultimate" | "spike" | "first";

interface Row {
  key: string;
  tMs: number;
  kind: Kind;
  side: Side | null;
  /** Rendered content. Built here so the list stays a map over one array. */
  body: React.ReactNode;
}

const FILTERS: Array<{ kind: Kind; label: string; icon: typeof glyphs.kills }> = [
  { kind: "kill", label: "Kills", icon: glyphs.kills },
  { kind: "ability", label: "Abilities", icon: glyphs.utility },
  { kind: "ultimate", label: "Ultimates", icon: glyphs.ultimates },
  { kind: "spike", label: "Spike", icon: glyphs.spike },
  { kind: "first", label: "First Kill", icon: glyphs.firstBlood },
];

const SPIKE_WORDS: Record<string, string> = {
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

/** Everything in one round, in time order, with first blood duplicated. */
function rowsFor(replay: Replay, round: Round, weapons: Weapon[] | undefined): Row[] {
  const inRound = (t: number) => t >= round.start_ms && t < round.end_ms;
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

  const rows: Row[] = [];

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
      body,
    });
  }

  // The round's own first kill, repeated as its own tagged row.
  const first = kills.reduce<(typeof kills)[number] | null>(
    (earliest, kill) => (earliest === null || kill.t_ms < earliest.t_ms ? kill : earliest),
    null,
  );
  if (first !== null) {
    rows.push({
      key: `first-${first.t_ms}`,
      tMs: first.t_ms,
      kind: "first",
      side: sideAt(first.killer, first.t_ms),
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
    const side = sideAt(cast.actor_id, cast.t_ms);
    rows.push({
      key: `cast-${cast.t_ms}-${cast.actor_id}-${cast.internal_name}`,
      tMs: cast.t_ms,
      kind: "ability",
      side,
      body: (
        <>
          <Name text={cast.identity || nameOf(cast.actor_id)} side={side} />
          <span className="ev-verb">used</span>
          {cast.icon_url ? <img className="ev-ability" src={cast.icon_url} alt="" /> : null}
          <span className="ev-thing">
            {cast.published_name ?? cast.internal_name}
            {cast.published_name ? null : <span className="muted"> (internal)</span>}
          </span>
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
      body: (
        <>
          <Name text={nameOf(ult.actor_id)} side={side} />
          <span className="ev-verb">used their ultimate</span>
        </>
      ),
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
      body: <span className="ev-thing">{SPIKE_WORDS[event.kind] ?? event.kind}</span>,
    });
  }

  // Ties broken by kind, not by key: a kill and its first-blood twin share a
  // millisecond, and sorting by key alphabetically put `first-` above `kill-`
  // so the round opened with a tag for an event that had not been listed yet.
  const rank: Record<Kind, number> = {
    spike: 0,
    ability: 1,
    ultimate: 2,
    kill: 3,
    first: 4,
  };
  return rows.sort((a, b) => a.tMs - b.tMs || rank[a.kind] - rank[b.kind]);
}

export function RoundTimeline({
  replay,
  round,
  weapons,
  onPick,
  onSeek,
  onClose,
}: {
  replay: Replay;
  round: Round;
  weapons: Weapon[] | undefined;
  onPick: (round: Round) => void;
  onSeek: (tMs: number) => void;
  onClose: () => void;
}) {
  const [kinds, setKinds] = useState<Kind[]>([
    "kill",
    "ability",
    "ultimate",
    "spike",
    "first",
  ]);
  const [sides, setSides] = useState<Side[]>(["ATK", "DEF"]);

  const rows = useMemo(
    () => rowsFor(replay, round, weapons),
    [replay, round, weapons],
  );
  const shown = rows.filter(
    (row) => kinds.includes(row.kind) && (row.side === null || sides.includes(row.side)),
  );

  const index = replay.rounds.findIndex((r) => r.number === round.number);
  const step = (direction: 1 | -1) => {
    const next = replay.rounds[index + direction];
    if (next !== undefined) {
      onPick(next);
    }
  };

  const toggle = <T,>(list: T[], value: T, set: (next: T[]) => void) =>
    set(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);

  return (
    <Modal
      title="Round Timeline"
      onClose={onClose}
      actions={
        <div className="round-step">
          <IconButton
            label="Previous round"
            icon={glyphs.pagePrev}
            disabled={index <= 0}
            onClick={() => step(-1)}
          />
          <span className="round-step-label">Round {round.number}</span>
          <IconButton
            label="Next round"
            icon={glyphs.pageNext}
            disabled={index >= replay.rounds.length - 1}
            onClick={() => step(1)}
          />
        </div>
      }
    >
      <div className="timeline-body">
        <ol className="event-list">
          {shown.map((row) => (
            <li
              key={row.key}
              className={`event-row is-${row.kind}${
                row.side ? ` side-${row.side.toLowerCase()}` : ""
              }`}
            >
              <button type="button" onClick={() => onSeek(row.tMs)}>
                <span className="ev-time numeric">
                  {clockText(row.tMs - round.start_ms)}
                </span>
                <span className="ev-glyph">
                  <Icon
                    glyph={
                      row.kind === "kill"
                        ? glyphs.kills
                        : row.kind === "first"
                          ? glyphs.firstBlood
                          : row.kind === "spike"
                            ? glyphs.spike
                            : row.kind === "ultimate"
                              ? glyphs.ultimates
                              : glyphs.utility
                    }
                  />
                </span>
                <span className="ev-body">{row.body}</span>
              </button>
            </li>
          ))}
          {shown.length === 0 ? (
            <li className="event-empty">
              <p className="sentence">
                Nothing in round {round.number} matches these filters.
              </p>
            </li>
          ) : null}
        </ol>

        <div className="event-filters">
          <p className="menu-title">Event Types</p>
          {FILTERS.map((filter) => (
            <CheckRow
              key={filter.kind}
              label={filter.label}
              icon={filter.icon}
              checked={kinds.includes(filter.kind)}
              onChange={() => toggle(kinds, filter.kind, setKinds)}
            />
          ))}
          <p className="menu-title">Side</p>
          <CheckRow
            label="Attackers"
            icon={glyphs.side}
            tone="a"
            checked={sides.includes("ATK")}
            onChange={() => toggle(sides, "ATK", setSides)}
          />
          <CheckRow
            label="Defenders"
            icon={glyphs.side}
            tone="b"
            checked={sides.includes("DEF")}
            onChange={() => toggle(sides, "DEF", setSides)}
          />
          <p className="footnote">
            Assists and ultimate orbs are not in the file: a death event carries
            a killer, a victim and a time, and an orb capture is not one of the
            seven event groups at all.
          </p>
        </div>
      </div>
    </Modal>
  );
}
