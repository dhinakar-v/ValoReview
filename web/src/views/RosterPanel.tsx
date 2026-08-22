/**
 * A side's five players, down one edge of the map.
 *
 * This is the desktop viewer's layout (`vrfview/panels.py` draws two mirrored
 * team columns flanking the centre canvas) with the reference frames' card
 * anatomy: portrait flush to the outer edge, then credits above the name, then
 * the ability row, with armour and health at the inner end and the weapon
 * silhouette beside them.  The right-hand panel is the exact mirror, so the two
 * portraits sit against the two window edges and everything reads inward
 * toward the map.
 *
 * Which half of each card is real is worth knowing before changing anything:
 *
 *   read      the agent, the portrait, the ability icons, whether the player
 *             is alive, the score in the header
 *   generated health, armour, credits, the weapon, and ATK/DEF itself
 *
 * The generated half all comes from `model/synthetic.ts` and nowhere else, and
 * the page carries `SIMULATED_NOTE` wherever these numbers appear.  A `.vrf`
 * replicates none of it to a spectator recording -- see `provenance.ABSENT`.
 *
 * A card is not a button and does not select: hovering one raises the same
 * tooltip a marker does, because the roster and the map are two views of the
 * same ten people and pointing at either should say the same thing.
 */

import type { Player, Weapon } from "../api/types";
import type { ReplayModel } from "../model/replay";
import type { Snapshot } from "../model/state";
import type { Side, Vitals } from "../model/synthetic";
import { vitalsAt, weaponArt } from "../model/synthetic";
import { Icon, glyphs } from "./icons";
import { usePlayback } from "./playback";

/** The mirrored pair of panels, so a page cannot draw one without the other. */
export function RosterPanel({
  model,
  snap,
  team,
  side,
  score,
  weapons,
  mirrored,
}: {
  model: ReplayModel;
  snap: Snapshot;
  team: string;
  side: Side;
  score: number;
  weapons: Weapon[] | undefined;
  /** The right-hand panel, which is the left one read the other way round. */
  mirrored: boolean;
}) {
  const players = model.replay.players.filter((player) => player.team === team);
  const hidden = usePlayback((state) => state.hiddenTeams.includes(team));
  const toggleTeam = usePlayback((state) => state.toggleTeam);

  return (
    <aside
      className={`roster${mirrored ? " is-mirrored" : ""} side-${side.toLowerCase()}`}
      aria-label={`${side} roster`}
    >
      <header className="roster-head">
        <span className="roster-side">
          <Icon glyph={glyphs.side} />
          {side}
        </span>
        <button
          type="button"
          className={hidden ? "roster-filter is-off" : "roster-filter"}
          aria-pressed={hidden}
          // Named for what pressing it does, not for what it is: "Filter" tells
          // a screen-reader user the control's category and nothing about the
          // effect, and this one hides five markers.
          aria-label={`${hidden ? "Show" : "Hide"} ${side} on the map`}
          title={`${hidden ? "Show" : "Hide"} ${side} on the map`}
          onClick={() => toggleTeam(team)}
        >
          <Icon glyph={glyphs.filter} />
        </button>
        <span className="roster-score numeric">{score}</span>
      </header>

      <div className="roster-cards">
        {players.map((player) => (
          <PlayerCard
            key={player.actor_id}
            player={player}
            vitals={vitalsAt(model, snap, player.actor_id)}
            alive={snap.alive.has(player.actor_id)}
            weapons={weapons}
          />
        ))}
      </div>
    </aside>
  );
}

/**
 * One player.
 *
 * `is-dead` desaturates the whole card rather than blanking fields: the
 * reference greys the portrait, drops the name and glyphs to about a third and
 * dims the accent, which reads as *this player is out* where an empty card
 * reads as *this player is missing*.
 */
export function PlayerCard({
  player,
  vitals,
  alive,
  weapons,
}: {
  player: Player;
  vitals: Vitals;
  alive: boolean;
  weapons: Weapon[] | undefined;
}) {
  const hovered = usePlayback((state) => state.hovered === player.actor_id);
  const selected = usePlayback((state) => state.selected === player.actor_id);
  const gun = weaponArt(weapons, vitals.weapon);

  const classes = ["player-card"];
  if (!alive) {
    classes.push("is-dead");
  }
  if (hovered || selected) {
    classes.push("is-lit");
  }

  return (
    <article
      className={classes.join(" ")}
      onMouseEnter={() => usePlayback.setState({ hovered: player.actor_id })}
      onMouseLeave={() => usePlayback.setState({ hovered: null })}
    >
      {/*
        `icon_url` and not `portrait_url`.  Riot publishes both: `fullPortrait`
        is a full-body render two thousand pixels tall, and `displayIcon` is the
        square agent art.  A full body cropped into a card is a dark smear of
        legs -- which is what this was until it was looked at -- while the icon
        is the agent's face at the size a card actually has.
      */}
      {player.icon_url ? (
        <img className="card-portrait" src={player.icon_url} alt="" />
      ) : (
        <span className="card-portrait is-absent" />
      )}

      <div className="card-body">
        <div className="card-top">
          <span className="card-credits numeric" title="Credits (simulated)">
            <Icon glyph={glyphs.credits} size={11} />
            {vitals.money}
          </span>
          <div className="spacer" />
          <span className="card-armor numeric" title="Armour (simulated)">
            {vitals.armor}
          </span>
          <span className="card-health numeric" title="Health (simulated)">
            {vitals.health}
          </span>
        </div>

        {/*
          The agent, and no A1 / B2 beside it.  That label is the only identity
          a `.vrf` carries and it is still what `Player.label` holds, but it
          names the *inferred group*, and this interface says ATK and DEF -- in
          the header above these five cards, once, rather than on every row.
          The actor id is in the hover card for anyone who needs it.
        */}
        <div className="card-name">
          <span className="card-agent">{player.agent || player.codename || "unknown"}</span>
        </div>

        <div className="card-bottom">
          <span className="card-abilities">
            {/*
              Riot's own slot order, and no keybind anywhere.  `Grenade` is C
              and `Ultimate` is X on every agent, but `Ability1` and `Ability2`
              are Q and E in an order that varies -- so the icons are shown and
              the key is not named.  `art.AgentArt.ability` is where that
              refusal lives.
            */}
            {player.abilities.map((ability) =>
              ability.icon_url ? (
                <img
                  key={ability.slot}
                  className="ability-icon"
                  src={ability.icon_url}
                  alt=""
                  title={ability.name}
                />
              ) : null,
            )}
          </span>
          <div className="spacer" />
          {gun?.icon_url ? (
            <img className="card-weapon" src={gun.icon_url} alt="" title={gun.name} />
          ) : vitals.weapon ? (
            <span className="card-weapon is-text">{vitals.weapon}</span>
          ) : null}
        </div>
      </div>

      <span className="card-accent" />
    </article>
  );
}
