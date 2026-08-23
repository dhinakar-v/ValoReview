/**
 * One round, as a list of everything that happened in it.
 *
 * No positions are involved and none are needed: this answers which agent, on
 * which side, did what at what time, and to whom.  That is four of the seven
 * event groups a `.vrf` carries plus the casts `abilities.py` infers from the
 * actors they spawn, and it is available on any capture that parses -- a
 * replay with no decode at all still has kills, rounds and a side swap.
 *
 * The rows themselves are built by `roundevents.roundEvents`, which used to be
 * a `rowsFor` in this file and moved out when the transport rail grew a hover
 * tooltip.  Both now read one array, so a tick and a row cannot say different
 * things about the same event.  What is real and what is generated per column,
 * and why assists and orbs are absent, is written down there.
 *
 * This file is what is left: the filters, the modal, and the row's own chrome.
 * Two of the reference's filters are missing along with the rows they would
 * match -- a checkbox that can never match anything is worse than its absence,
 * the same argument that keeps `SIGHT` off a map with no mask.
 */

import { useMemo, useState } from "react";

import type { Replay, Round, Weapon } from "../api/types";
import { clockText, remainingMs } from "../model/roundclock";
import type { Side } from "../model/synthetic";
import { Icon, glyphs } from "./icons";
import type { Kind } from "./roundevents";
import { roundEvents } from "./roundevents";
import { CheckRow, IconButton, Modal } from "./ui";

const FILTERS: Array<{ kind: Kind; label: string; icon: typeof glyphs.kills }> = [
  { kind: "kill", label: "Kills", icon: glyphs.kills },
  { kind: "ability", label: "Abilities", icon: glyphs.utility },
  { kind: "ultimate", label: "Ultimates", icon: glyphs.ultimates },
  { kind: "spike", label: "Spike", icon: glyphs.spike },
  { kind: "first", label: "First Kill", icon: glyphs.firstBlood },
];


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
    () => roundEvents(replay, round, weapons),
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
                {/*
                  Time **remaining**, not elapsed.  A Valorant round clock
                  counts down, so this is what a player saw when it happened;
                  counting up from the round start was a number nobody in the
                  match could have read off their own screen.

                  Two rows in the last second both showing 0:00 is correct and
                  is not to be rounded away: `clockText` truncates on purpose,
                  because a countdown reading 1:40 through the first half of a
                  1:39.6 round has already lied about a whole second.
                */}
                <span className="ev-time numeric">
                  {clockText(remainingMs(round, row.tMs))}
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
          {/* The same two marks the roster headers carry, and for the same
              reason: the shield is the defender's, so both sides wearing it
              made ATK read as backwards in the one place the two are listed
              side by side. */}
          <CheckRow
            label="Attackers"
            icon={glyphs.atk}
            tone="a"
            checked={sides.includes("ATK")}
            onChange={() => toggle(sides, "ATK", setSides)}
          />
          <CheckRow
            label="Defenders"
            icon={glyphs.def}
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
