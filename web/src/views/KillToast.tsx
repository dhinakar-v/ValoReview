/**
 * Kills, top right, for as long as they are recent.
 *
 * `Snapshot.recent_kills` has existed since the model was ported and nothing
 * drew it: it is every kill inside the last 2.5 s paired with a fade fraction,
 * computed from scratch per snapshot like everything else in `stateAt`, so it
 * is as correct scrubbing backwards as playing forwards.  This is that list.
 *
 * Killer, victim and time are read from `characterDeath` -- and note the
 * argument order, `args[1]` is the killer and `args[2]` the victim, which the
 * summary doc had reversed for a while and which `test_killer_victim_order_is_
 * not_reversed` now pins.  The **weapon is generated**: nothing decoded says
 * what anybody was holding, so the icon between the two names comes from
 * `model/synthetic.ts` and the page says so.
 *
 * Names are short here -- the label and the agent, not the full identity --
 * because the reference frames show `iZu`, not `T1 iZu`, and a feed is read at
 * a glance or not at all.
 */

import type { Player, Weapon } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { Snapshot } from "../model/state";
import { sideOf, weaponArt, weaponInRound } from "../model/synthetic";
import { Icon, glyphs } from "./icons";

function shortName(player: Player | undefined): string {
  if (player === undefined) {
    return "unknown";
  }
  return player.agent || player.codename || player.label;
}

export function KillToast({
  model,
  snap,
  weapons,
}: {
  model: ReplayModel;
  snap: Snapshot;
  weapons: Weapon[] | undefined;
}) {
  if (snap.recentKills.length === 0) {
    return null;
  }
  const replay = model.replay;
  return (
    <div className="killfeed" aria-live="off">
      {[...snap.recentKills]
        .sort((a, b) => b[0].t_ms - a[0].t_ms)
        .map(([kill, age]) => {
          const killer = replay.players.find((p) => p.actor_id === kill.killer);
          const victim = replay.players.find((p) => p.actor_id === kill.victim);
          const gun = weaponArt(
            weapons,
            weaponInRound(replay, kill.killer, kill.round_no),
          );
          const side = killer ? sideOf(replay, killer.team, kill.t_ms) : "ATK";
          return (
            <div
              className="kill-chip"
              key={`${kill.t_ms}-${kill.killer}-${kill.victim}`}
              // The fade is the model's own age fraction rather than a CSS
              // animation, so a paused playhead holds a chip still instead of
              // dissolving one that is still true.
              style={{ opacity: 1 - age * age }}
            >
              {killer?.icon_url ? (
                <img className="kill-portrait" src={killer.icon_url} alt="" />
              ) : null}
              <span className={`kill-name side-${side.toLowerCase()}`}>
                {shortName(killer)}
              </span>
              {kill.is_suicide ? (
                <span className="kill-glyph">
                  <Icon glyph={glyphs.kills} size={13} />
                </span>
              ) : gun?.killfeed_url ? (
                <img className="kill-weapon" src={gun.killfeed_url} alt="" />
              ) : (
                <span className="kill-glyph">
                  <Icon glyph={glyphs.kills} size={13} />
                </span>
              )}
              <span className="kill-name is-victim">{shortName(victim)}</span>
            </div>
          );
        })}
    </div>
  );
}
