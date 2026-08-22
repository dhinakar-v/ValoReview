/**
 * What one player is, raised by pointing at them.
 *
 * Anchored to the hovered marker on the canvas -- `MinimapCanvas` publishes the
 * hit-test coordinate it already has, rather than this file re-projecting the
 * world position, because two projections of the same point are two chances to
 * disagree about where a marker is.  Hovering the player's roster card raises
 * the same tooltip, pinned beside their card instead; the roster and the map
 * are two views of the same ten people and pointing at either should say the
 * same thing.
 *
 * Three of the rows are generated (`model/synthetic.ts`) and three are read.
 * The read ones are worth having and the reference has none of them: the actor
 * net id, which is the only identity a `.vrf` actually carries, and the running
 * kills and deaths, which come from the real `characterDeath` events.
 *
 * `No Weapon Equipped` is a sentence and not a blank, which is the reference's
 * own choice and the right one: an empty row reads as a field that failed to
 * load.
 */

import type { Weapon } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { Snapshot } from "../model/state";
import { sideOf, vitalsAt, weaponArt } from "../model/synthetic";
import { usePlayback } from "./playback";

export function MarkerTip({
  model,
  snap,
  weapons,
}: {
  model: ReplayModel;
  snap: Snapshot;
  weapons: Weapon[] | undefined;
}) {
  const actorId = usePlayback((state) => state.hovered);
  const at = usePlayback((state) => state.hoveredAt);
  if (actorId === null) {
    return null;
  }
  const player = model.replay.players.find((p) => p.actor_id === actorId);
  if (player === undefined) {
    return null;
  }

  const vitals = vitalsAt(model, snap, actorId);
  const alive = snap.alive.has(actorId);
  const side = sideOf(model.replay, player.team, snap.t_ms);
  const gun = weaponArt(weapons, vitals.weapon);
  const [kills, deaths] = snap.kd.get(actorId) ?? [0, 0];

  /*
    `hoveredAt` is where the tip goes, already worked out by whoever raised it.

    A roster card now supplies one too -- `RosterPanel.tipAnchor` translates
    the card's own box into this canvas's frame -- so the parked corner is only
    for a page that has rosters and no stage to anchor to.  Each source applies
    its own offset, because they need different ones: a marker's is pushed
    clear of the marker, and a roster's is already an edge.  Guessing which was
    which from the value would break for a marker near the left edge.
  */
  const anchored = at !== null;
  const style = anchored ? { left: `${at.x}px`, top: `${at.y}px` } : undefined;

  return (
    <div className={anchored ? "marker-tip" : "marker-tip is-parked"} style={style}>
      <div className="tip-head">
        {player.icon_url ? (
          <img className="tip-portrait" src={player.icon_url} alt="" />
        ) : null}
        <span className="tip-name">
          {player.agent || player.codename || player.label}
        </span>
        <span className={`tip-side side-${side.toLowerCase()}`}>{side}</span>
      </div>

      <dl className="tip-rows">
        <div>
          <dt>Health</dt>
          <dd className="numeric">{alive ? vitals.health : 0}</dd>
        </div>
        <div>
          <dt>Armor</dt>
          <dd className="numeric">{alive ? vitals.armor : 0}</dd>
        </div>
        <div>
          <dt>Money</dt>
          <dd className="numeric">{vitals.money}</dd>
        </div>
      </dl>

      <div className="tip-weapon">
        {gun?.icon_url ? (
          <>
            <img src={gun.icon_url} alt="" />
            <span>{gun.name}</span>
          </>
        ) : (
          <span>{vitals.weapon ?? "No Weapon Equipped"}</span>
        )}
      </div>

      {/* The half a `.vrf` really does state. */}
      <div className="tip-read">
        <span className="numeric">
          {kills} / {deaths}
        </span>
        <span className="mono">#{player.actor_id}</span>
      </div>
    </div>
  );
}
