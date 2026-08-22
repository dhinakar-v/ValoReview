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
import type { Side, SlotState, Vitals } from "../model/synthetic";
import { slotStateAt, vitalsAt, weaponArt } from "../model/synthetic";
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
        {/* The spike for the attackers and the shield for the defenders.
            Both were the shield, which is the defender's mark and reads as
            exactly backwards on ATK. */}
        <span className="roster-side">
          <Icon glyph={side === "ATK" ? glyphs.atk : glyphs.def} />
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
          {/* The glyph flips with the state, so which sides are hidden is
              readable across the whole page without hovering either one. */}
          <Icon glyph={hidden ? glyphs.hidden : glyphs.shown} />
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
            slots={
              new Map(
                player.abilities.map((ability) => [
                  ability.slot,
                  slotStateAt(model, snap, player.actor_id, ability.slot),
                ]),
              )
            }
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
/**
 * Where the hover card should sit for a roster card, in canvas coordinates.
 *
 * `MarkerTip` is positioned inside `.stage-canvas`, and a roster card is in a
 * different column of the arena, so this is a deliberate translation rather
 * than a lookup: vertically the card's own middle, horizontally the canvas
 * edge on this roster's side, both clamped to stay inside the canvas.
 *
 * Returns null when there is no canvas -- the document-shaped page for a
 * capture with no positions has rosters and no stage -- and `MarkerTip` then
 * parks itself as it always did.
 */
function tipAnchor(card: HTMLElement): { x: number; y: number } | null {
  const canvas = document.querySelector(".stage-canvas");
  if (canvas === null) {
    return null;
  }
  const stage = canvas.getBoundingClientRect();
  if (stage.width === 0 || stage.height === 0) {
    return null;
  }
  const box = card.getBoundingClientRect();
  const onTheLeft = box.left < stage.left;
  const x = onTheLeft ? TIP_EDGE_PX : stage.width - TIP_WIDTH_PX - TIP_EDGE_PX;
  const middle = box.top + box.height / 2 - stage.top;
  const y = Math.max(
    TIP_EDGE_PX,
    Math.min(stage.height - TIP_HEIGHT_PX - TIP_EDGE_PX, middle - TIP_HEIGHT_PX / 2),
  );
  return { x: Math.max(0, x), y: Math.max(0, y) };
}

/*
 * The tip's own box, restated here because it is drawn by CSS and read by
 * arithmetic.  `MarkerTip` cannot be measured before it exists, and measuring
 * it after would move it on the frame after it appeared.
 */
const TIP_WIDTH_PX = 212;
const TIP_HEIGHT_PX = 180;
const TIP_EDGE_PX = 12;

export function PlayerCard({
  player,
  vitals,
  alive,
  weapons,
  slots,
}: {
  player: Player;
  vitals: Vitals;
  alive: boolean;
  weapons: Weapon[] | undefined;
  /**
   * Per-slot charge state, computed by the parent because it has the snapshot.
   *
   * Deliberately **not** a field on `Snapshot`: that record is serialised
   * field-for-field against `tests/golden/` by `parity.test.ts`, so a new
   * member needs a Python counterpart, a regenerated golden and a
   * `make-golden --check` pass in two languages -- for a card decoration.
   */
  slots?: Map<string, SlotState>;
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
      /*
        Hovering a card raises the same tooltip a marker does, and it has to
        appear *beside the card*.  This used to set `hovered` and not
        `hoveredAt`, so `MarkerTip` fell back to parking itself in the stage's
        bottom-left corner -- hundreds of pixels from the avatar being pointed
        at, across the whole map and back.

        The tip is a child of `.stage-canvas`, which keeps the viewer's
        `overflow: hidden` safe, so the coordinate is worked out in the
        canvas's own frame: the card's vertical middle, and horizontally
        whichever edge of the canvas this roster is against.  `tipAnchor`
        clamps both, so a card at the very top or bottom of a tall roster still
        raises a tip that is entirely on screen.
      */
      onMouseEnter={(event) =>
        usePlayback.setState({
          hovered: player.actor_id,
          hoveredAt: tipAnchor(event.currentTarget),
        })
      }
      // Both, or the tip freezes at the last card's position and the next
      // marker hover inherits it.
      onMouseLeave={() => usePlayback.setState({ hovered: null, hoveredAt: null })}
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
            {player.abilities.map((ability) => {
              const state = slots?.get(ability.slot);
              if (!ability.icon_url) {
                return null;
              }
              /*
                A used charge is *marked*, never removed.

                Removing the icon would state exhaustion, and the model cannot
                say that: a cast groups every use of a slot in a round into one
                record, so it knows the slot was used and never how often.  Dim
                and desaturate say "unavailable"; the rule under it is what
                reads as "spent" at fourteen pixels, where a strikethrough is
                invisible.  Both states occupy the same box, because a card
                that changes length four times a round is worse than the fault.
              */
              const spent = state?.used ?? false;
              const why = spent
                ? state?.usedIsReal
                  ? `${ability.name} — used this round`
                  : `${ability.name} — simulated as used this round`
                : ability.name;
              return (
                <span
                  key={ability.slot}
                  className={spent ? "ability-slot is-used" : "ability-slot"}
                >
                  <img className="ability-icon" src={ability.icon_url} alt="" title={why} />
                  {state && state.charges > 1 ? (
                    <b className="ability-charges">{state.left}</b>
                  ) : null}
                </span>
              );
            })}
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
