/**
 * Page two: one replay.
 *
 * Everything the file states, everything inferred from it, everything looked
 * up -- and, where a capture has been decoded, the map it happened on.  The
 * map is `MapStage`, which owns the two views, the layers and the transport;
 * this page owns the tables around it.
 *
 * The split is deliberate.  A snapshot is recomputed sixty times a second and
 * the roster is not, so the playhead lives in a store the canvas reads inside
 * its own animation frame rather than in state this page would re-render from.
 *
 * The roster is two mirrored columns rather than one table because that is what
 * the teams are: two of them, inferred, with nothing ranking one above the
 * other.  A single table sorted by team implies an order the data has not got.
 * Rounds and casts share one tabbed panel because they are both timelines over
 * the same match, and stacking all three tables made a page nobody scrolled to
 * the bottom of.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Player, Replay, Round } from "../api/types";
import { glyphs } from "../views/icons";
import { MapStage } from "../views/MapStage";
import { Failed, Loading, Page } from "../views/Shell";
import { Button, Chip, Panel, TabPanel, Tabs, Toolbar } from "../views/ui";
import type { Tab } from "../views/ui";

function teamClass(team: string): string {
  if (team === "A") return "team-a";
  if (team === "B") return "team-b";
  return "team-unknown";
}

function teamEdge(team: string): string {
  if (team === "A") return "player-row is-a";
  if (team === "B") return "player-row is-b";
  return "player-row";
}

function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

function TeamColumn({ team, players }: { team: string; players: Player[] }) {
  return (
    <div className="team-panel">
      <div className="team-title">
        <span className={teamClass(team)}>&#9632;</span>
        Team {team}
        <div className="spacer" />
        <span className="muted">{players.length}</span>
      </div>
      {players.map((player) => (
        <div className={teamEdge(team)} key={player.actor_id}>
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

function Roster({ replay }: { replay: Replay }) {
  const teams: Array<[string, Player[]]> = [
    ["A", replay.players.filter((p) => p.team === "A")],
    ["B", replay.players.filter((p) => p.team === "B")],
  ];
  const unknown = replay.players.filter((p) => p.team !== "A" && p.team !== "B");
  if (unknown.length > 0) {
    teams.push(["?", unknown]);
  }
  return (
    <Panel
      title="Players"
      icon={glyphs.players}
      actions={<Chip>{replay.players.length} in the file</Chip>}
    >
      <div className="team-panels">
        {teams.map(([team, players]) => (
          <TeamColumn key={team} team={team} players={players} />
        ))}
      </div>
      <p className="footnote">
        Teams are A and B, inferred by two-colouring the kill graph. Which side
        attacked is not recoverable: spike events carry no actor id. Health, armour
        and credits are never replicated to a spectator recording, so they are not
        shown at all rather than shown as zero.
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
              <td className={round.decided ? teamClass(round.winner) : "muted"}>
                {round.decided ? round.winner : "undetermined"}
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
                  {/* Riot's name where it joins -- X and C only -- and the name
                      read out of the archetype path otherwise. Q and E vary by
                      agent, so preferring one would be a coin flip. */}
                  {cast.published_name ?? cast.internal_name}
                  {cast.published_name ? null : <span className="muted"> (internal)</span>}
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
        <Chip tone="a" title="Rounds won, team A to team B">
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
  const actions = (
    <Toolbar>
      <Chip icon={glyphs.rounds}>{clock(replay.length_ms)}</Chip>
      {back}
    </Toolbar>
  );

  return (
    <Page
      title={replay.map_name || replay.map_path}
      actions={actions}
      footer={<span className="mono">{replay.source}</span>}
    >
      <MapStage replay={replay} decoder={config.data?.decoder} />
      <Roster replay={replay} />
      <Timeline replay={replay} />
    </Page>
  );
}
