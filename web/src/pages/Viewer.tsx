/**
 * Page two: one replay.
 *
 * It has two shapes, and which one appears is decided by whether there is a map
 * to look at.
 *
 * **With positions** it is not a document at all.  The arena fills the window
 * -- a 40px bar, the map with a roster down each side, the round strip and the
 * transport -- and nothing scrolls.  That is `MapStage`, which owns the views,
 * the layers, the rosters and the transport; this page owns the bar above it.
 *
 * **Without them** it goes back to being a page: the stage becomes a sentence
 * in a short panel, and the roster and the timeline are tables under it.  A
 * roster flanking a paragraph would be a layout pretending there is something
 * to look at, and the tables are worth reading on a capture nothing can be
 * decoded from -- rounds, kills and the inferences are all still there.
 *
 * The split is also what keeps the frame rate honest.  A snapshot is recomputed
 * many times a second and the tables are not, so the tables only exist on the
 * shape that has no playhead.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Player, Replay, Round } from "../api/types";
import { formatRecorded } from "../model/format";
import { sideOf } from "../model/synthetic";
import { glyphs } from "../views/icons";
import { MapStage } from "../views/MapStage";
import { Failed, Loading, Page } from "../views/Shell";
import { Button, Chip, Panel, TabPanel, Tabs, Toolbar } from "../views/ui";
import type { Tab } from "../views/ui";

function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

/** The colour class for a side, for text that should carry it. */
function sideClass(replay: Replay, team: string): string {
  if (team !== "A" && team !== "B") {
    return "team-unknown";
  }
  return sideOf(replay, team, 0) === "ATK" ? "team-a" : "team-b";
}

/** The same, as a row edge: `.player-row` colours its border, not its text. */
function sideEdge(replay: Replay, team: string): string {
  if (team !== "A" && team !== "B") {
    return "player-row";
  }
  return sideOf(replay, team, 0) === "ATK" ? "player-row is-a" : "player-row is-b";
}

/* -- the document shape --------------------------------------------------- */

function TeamColumn({ replay, team, players }: { replay: Replay; team: string; players: Player[] }) {
  const side = team === "A" || team === "B" ? sideOf(replay, team, 0) : "—";
  return (
    <div className="team-panel">
      <div className="team-title">
        <span className={sideClass(replay, team)}>&#9632;</span>
        {side}
        <div className="spacer" />
        <span className="muted">{players.length}</span>
      </div>
      {players.map((player) => (
        <div className={sideEdge(replay, team)} key={player.actor_id}>
          {player.icon_url ? (
            <img
              className="player-portrait"
              src={player.icon_url}
              alt=""
              width={28}
              height={28}
            />
          ) : (
            <span className="player-portrait" />
          )}
          <span className="player-name">{player.identity}</span>
          <span className="player-id">#{player.actor_id}</span>
        </div>
      ))}
    </div>
  );
}

/** The teams, always in this order, and the order carries no claim. */
function split(replay: Replay): Array<[string, Player[]]> {
  const teams: Array<[string, Player[]]> = [
    ["A", replay.players.filter((p) => p.team === "A")],
    ["B", replay.players.filter((p) => p.team === "B")],
  ];
  const unknown = replay.players.filter((p) => p.team !== "A" && p.team !== "B");
  if (unknown.length > 0) {
    teams.push(["?", unknown]);
  }
  return teams;
}

function Roster({ replay }: { replay: Replay }) {
  return (
    <Panel
      title="Players"
      icon={glyphs.players}
      actions={<Chip>{replay.players.length} in the file</Chip>}
    >
      <div className="team-panels">
        {split(replay).map(([team, players]) => (
          <TeamColumn key={team} replay={replay} team={team} players={players} />
        ))}
      </div>
      <p className="footnote">
        Teams are two groups, inferred by two-colouring the kill graph. Which of
        them attacked is not recoverable &mdash; spike events carry no actor id
        &mdash; so ATK and DEF here are an assignment, not a reading. Health,
        armour and credits are never replicated to a spectator recording.
      </p>
    </Panel>
  );
}

function Rounds({ replay }: { replay: Replay }) {
  return (
    <div className="scroll-y">
      <table className="rows">
        <thead>
          <tr>
            <th>#</th>
            <th>Start</th>
            <th>Length</th>
            <th>Winner*</th>
            <th>Reason*</th>
            <th>Kills</th>
          </tr>
        </thead>
        <tbody>
          {replay.rounds.map((round: Round) => (
            <tr key={round.number}>
              <td className="numeric">{round.number}</td>
              <td className="numeric muted">{clock(round.start_ms)}</td>
              <td className="numeric muted">{clock(round.duration_ms)}</td>
              <td className={round.decided ? sideClass(replay, round.winner) : "muted"}>
                {round.decided
                  ? sideOf(replay, round.winner, round.start_ms)
                  : "undetermined"}
              </td>
              <td className="muted">{round.reason}</td>
              <td className="numeric muted">
                {replay.kills.filter((k) => k.round_no === round.number).length}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Casts({ replay }: { replay: Replay }) {
  return (
    <>
      <div className="scroll-y">
        <table className="rows">
          <thead>
            <tr>
              <th>Round</th>
              <th>At</th>
              <th>Agent</th>
              <th>Key</th>
              <th>Ability</th>
              <th>Travelled</th>
            </tr>
          </thead>
          <tbody>
            {replay.ability_casts.slice(0, 60).map((cast, index) => (
              <tr key={`${cast.t_ms}-${cast.actor_id}-${index}`}>
                <td className="numeric">{cast.round_no}</td>
                <td className="numeric muted">{clock(cast.t_ms)}</td>
                <td>{cast.identity}</td>
                <td className="numeric">{cast.slot}</td>
                <td>
                  {/* Riot's name where it joins and the name read out of the
                      archetype path otherwise -- never annotated as internal,
                      which was a note to whoever built the decoder. */}
                  {cast.published_name ?? cast.internal_name}
                </td>
                <td className="numeric muted">
                  {cast.travel_uu === null
                    ? cast.travel_note
                    : `${Math.round(cast.travel_uu).toLocaleString()} uu`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="footnote">
        Distance is the measured path length of the pawn's own track. No ability
        publishes a range, radius or damage figure &mdash; not in the replay, and not
        in Riot's catalogue &mdash; so no such number is shown.
      </p>
    </>
  );
}

/** Rounds and casts, which are two readings of one timeline. */
function Timeline({ replay }: { replay: Replay }) {
  const tabs: Tab[] = [
    {
      id: "rounds",
      label: "Rounds",
      icon: glyphs.rounds,
      count: replay.rounds.length,
    },
  ];
  if (replay.has_abilities) {
    tabs.push({
      id: "casts",
      label: "Ability casts",
      icon: glyphs.casts,
      count: replay.ability_casts.length,
    });
  }
  const [active, setActive] = useState("rounds");
  const shown = tabs.some((tab) => tab.id === active) ? active : "rounds";

  return (
    <Panel
      title="Timeline"
      icon={glyphs.rounds}
      actions={
        <Chip tone="a" title="Rounds won">
          {replay.score[0] ?? 0} : {replay.score[1] ?? 0}
        </Chip>
      }
    >
      <Tabs tabs={tabs} active={shown} onChange={setActive} label="Timeline" />
      <TabPanel id={shown}>
        {shown === "rounds" ? <Rounds replay={replay} /> : <Casts replay={replay} />}
        {shown === "rounds" ? (
          <p className="footnote">
            * a winner and a reason are derived, not read. Teams are two-coloured from
            the kill graph, and a round nothing settles stays explicitly undetermined
            rather than being awarded to somebody.
          </p>
        ) : null}
      </TabPanel>
    </Panel>
  );
}

/* -- the page ------------------------------------------------------------- */

export function ViewerPage() {
  const { id = "" } = useParams();
  const query = useQuery({
    queryKey: ["replay", id],
    queryFn: () => api.replay(id),
    enabled: Boolean(id),
  });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });

  const back = (
    <Link to="/">
      <Button label="BACK" icon={glyphs.back} />
    </Link>
  );

  if (query.isPending) {
    return (
      <Page title="Replay" actions={back}>
        <Loading what="the replay" />
      </Page>
    );
  }
  if (query.isError) {
    return (
      <Page title="Replay" actions={back}>
        <Failed error={query.error} />
      </Page>
    );
  }

  const replay = query.data;

  if (!replay.has_positions) {
    return (
      <Page
        title={replay.map_name || replay.map_path}
        actions={
          <Toolbar>
            <Chip icon={glyphs.rounds}>{clock(replay.length_ms)}</Chip>
            {back}
          </Toolbar>
        }
        footer={<span className="mono">{replay.source}</span>}
      >
        <MapStage replay={replay} decoder={config.data?.decoder} />
        <Roster replay={replay} />
        <Timeline replay={replay} />
      </Page>
    );
  }

  /*
    The immersive shape.  `<main id="main" tabIndex={-1}>` rather than `Page`'s
    own: the skip link in `AppFrame` targets that id and needs the element to be
    focusable, because a link that moves only the scroll leaves the focus in the
    bar and the next Tab returns to what it was meant to skip.
  */
  return (
    <>
      <header className="viewer-bar">
        <Link to="/" className="viewer-back">
          <Button label="BACK" icon={glyphs.back} size="sm" />
        </Link>
        <span className="viewer-title">{replay.map_name || replay.map_path}</span>
        {/* Written in the reader's own zone. This was the raw ISO instant,
            microseconds and UTC offset and all. */}
        <span className="viewer-sub">
          {replay.recorded_utc ? formatRecorded(replay.recorded_utc) : replay.match_id}
        </span>
        <div className="spacer" />
      </header>
      <main id="main" className="viewer" tabIndex={-1}>
        <MapStage replay={replay} decoder={config.data?.decoder} />
      </main>
    </>
  );
}
