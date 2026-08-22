/**
 * Page two: one replay.
 *
 * This is the Phase 2 shape -- everything the file states, everything inferred
 * from it, and the provenance panel -- with no map yet.  The minimap, the 3D
 * scene, the timeline and playback arrive on top of the same document; nothing
 * here is scaffolding to be thrown away.
 *
 * Where the map will go, there is a sentence.  That is not a placeholder: it is
 * what goes there permanently whenever a capture has no decode or its map has
 * no radar image.  A drawing in the place a map belongs reads as a map however
 * it is captioned, so the two things that can be missing each get words.
 */

import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Player, Replay, Round } from "../api/types";
import { Provenance } from "../views/Provenance";
import { Failed, Loading, Page, Sentence } from "../views/Shell";

function teamClass(team: string): string {
  if (team === "A") return "team-a";
  if (team === "B") return "team-b";
  return "team-unknown";
}

function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
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
    <div className="panel">
      <h2>Players</h2>
      <table className="rows">
        <thead>
          <tr>
            <th>Team*</th>
            <th>Agent</th>
            <th>Actor</th>
            {/* Never replicated to a spectator recording. The dashes are the
                honest value, and the footnote below says why. */}
            <th>HP</th>
            <th>Armour</th>
            <th>Credits</th>
          </tr>
        </thead>
        <tbody>
          {teams.flatMap(([team, players]) =>
            players.map((player) => (
              <tr key={player.actor_id}>
                <td className={teamClass(team)}>{player.label || team}</td>
                <td>
                  {player.icon_url ? (
                    <img
                      src={player.icon_url}
                      alt=""
                      width={18}
                      height={18}
                      style={{ verticalAlign: "middle", marginRight: 6 }}
                    />
                  ) : null}
                  {player.identity}
                </td>
                <td className="numeric muted">#{player.actor_id}</td>
                <td className="muted">--</td>
                <td className="muted">--</td>
                <td className="muted">--</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
      <p className="muted" style={{ fontSize: 11, marginBottom: 0 }}>
        * teams are A and B, inferred by two-colouring the kill graph. Which side
        attacked is not recoverable: spike events carry no actor id. Health, armour
        and credits are never replicated to a spectator recording.
      </p>
    </div>
  );
}

function Rounds({ replay }: { replay: Replay }) {
  return (
    <div className="panel">
      <h2>
        Rounds &mdash; {replay.score[0] ?? 0} : {replay.score[1] ?? 0}
      </h2>
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
  if (!replay.has_abilities) {
    return null;
  }
  return (
    <div className="panel">
      <h2>Ability casts</h2>
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
      <p className="muted" style={{ fontSize: 11, marginBottom: 0 }}>
        Distance is the measured path length of the pawn's own track. No ability
        publishes a range, radius or damage figure &mdash; not in the replay, and not
        in Riot's catalogue &mdash; so no such number is shown.
      </p>
    </div>
  );
}

function Scene({ replay }: { replay: Replay }) {
  // Where the minimap goes. Two things can be absent and each says which.
  if (!replay.has_positions) {
    return (
      <div className="panel">
        <h2>Map</h2>
        <Sentence>
          No positions decoded for this capture.
          <br />
          <span className="mono">{replay.position_source || "not requested"}</span>
        </Sentence>
      </div>
    );
  }
  return (
    <div className="panel">
      <h2>Map</h2>
      <Sentence>
        Positions are decoded &mdash; the minimap and the 3D scene are not built yet.
        <br />
        <span className="mono">{replay.position_source}</span>
      </Sentence>
    </div>
  );
}

export function ViewerPage() {
  const { id = "" } = useParams();
  const query = useQuery({
    queryKey: ["replay", id],
    queryFn: () => api.replay(id),
    enabled: Boolean(id),
  });

  const back = (
    <Link to="/">
      <button type="button">BACK</button>
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
    <div className="toolbar" style={{ paddingBottom: 0 }}>
      {replay.map_key ? (
        <Link to={`/map/${encodeURIComponent(replay.map_key)}`}>
          <button type="button">MAP</button>
        </Link>
      ) : null}
      {back}
    </div>
  );

  return (
    <Page
      title={`${replay.map_name || replay.map_path} — ${clock(replay.length_ms)}`}
      actions={actions}
      footer={<span className="mono">{replay.source}</span>}
    >
      <div className="viewer-grid">
        <div>
          <Scene replay={replay} />
          <Roster replay={replay} />
          <Rounds replay={replay} />
          <Casts replay={replay} />
        </div>
        <div className="panel">
          <h2>Provenance</h2>
          <Provenance sections={replay.provenance} />
        </div>
      </div>
    </Page>
  );
}
