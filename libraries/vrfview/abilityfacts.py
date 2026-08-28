"""
What is published about an ability, looked up rather than read.

**Nothing in this project's inputs carries these numbers.**  Not the `.vrf`,
not val-content-v1, not `assets/manifest.json` -- `docs/valorant-replay-parser-
features.md` lists ability range, radius, duration and damage among the things
that are out of reach.  What a decode gives is *when* an ability was cast,
*where* each actor it spawned appeared and *when* each of those channels
opened; everything about what the thing then does is external knowledge.

So this is a hand-written table in the shape `names.AGENT_CODENAMES` sets:
offline, consulted at runtime, never fetched, and every figure carrying the
page it came from.  The research is `docs/Valorant Agent Ability Details.md`,
which is in the tree and cites its own sources per agent.

The unit is the Unreal unit and the conversion is **exact rather than
assumed**: Riot's own patch note for Sky Smoke reads "Radius increased 410 >>>
415" for an ability the wiki gives as 4.15 m, so the game's internal number is
centimetres and `UU_PER_METRE` is 100 on Riot's own arithmetic.

Why the key is (codename, slot)
-------------------------------
This table used to have two halves keyed two different ways -- `_FACTS` on
(agent, internal name) and `_SMOKES` on (codename, slot) -- because the
internal name splits: Clove's smoke arrives as `Post Death` 450 times and
`New Smoke` 969 times for the same ability, and Astra's as both `Smoke Zone`
and `Transform Rift Smoke World Targeting`.  The split key was the correction,
and it is now the only key, because the measurement that settles it is
unambiguous.

Over the 23 decoded captures in the reference library, **every (codename,
slot) maps to exactly one real ability**.  The several internal names under a
slot are always sub-actors of one thing: Sova's `Q` yields `Sonar Ping`,
`Reveal Bolt`, `Sonar Bolt` and `Reveal Bolt Signature`, all of them Recon
Bolt; Chamber's `C` yields `E Trap`, `E Slow Large`, `Trap` and `Trap Dart`,
all of them Trademark.  No slot in the library hosts two different abilities.
So the slot is what the archetype path states outright, it cannot split, and
one table can answer for every ability.

The slot is not the keybind, and that is the trap
-------------------------------------------------
`abilities` reads the slot out of the archetype path -- `Ability_Q`,
`Ability_E`, `Ability_4` -- so those letters are Riot's own, but they are
Riot's *internal* letters and they do not track the keys the game binds.
Measured across the reference library: Sova's `C` is Shock Bolt, which the
game binds to Q; his `E` is the Owl Drone, bound to C; his `Q` is the Recon
Bolt, bound to E.  Brimstone, Omen, Phoenix, Raze, Sage and Cypher are all
shuffled the same way.

That is why each entry carries **both**: `slot` is the key, read from the
file, and `keybind` is what the game shows a player, looked up like every
other figure here.  Joining the two by letter is the mistake this note exists
to prevent, and it is also why `art.AgentArt.ability` still refuses to resolve
an icon for Q and E.

Why this is drawn as simulated
------------------------------
These are community measurements of a game that rebalances every few weeks, so
a figure here is right for some patch and this capture may not be that patch --
the replay states its build and this table does not.  And a radius or a
duration is a claim about the world, where everything else the canvas draws is
a coordinate or an instant that was decoded.  So the ring is dashed and its
layer is labelled `MECHANICS (SIM)`, the same token every generated mark on
that canvas already carries.

What is deliberately absent
---------------------------
* **Viper.**  She has zero casts in the reference library, so there is no
  evidence of which internal slot letter each of her abilities occupies -- and
  the paragraph above is exactly why that cannot be guessed from the keybind.
  An agent with no evidence is refused rather than assumed.
* **Walls and lines.**  Sage's Barrier, Phoenix's Blaze and Harbor's Cascade
  block sight and are not circles: a cast gives one point and no orientation
  or length, so a circle drawn for one would block behind the caster and leave
  the far ends open.  They are in the table for their other figures and none
  of them sets `blocks_sight`.
* **Cast ranges.**  Sage's Barrier is cast within 10 m and Cypher's Trapwire
  spans up to 15 m.  Neither is a radius around where the thing landed, and
  drawing one as a ring would turn a reach into an area of effect -- the same
  refusal `travel_uu` already makes on the wire.
* **A default anything.**  An agent, a slot or a figure this table does not
  name returns None, and a caller must draw nothing.  There is no nearest
  match and no default radius: a ring at a made-up size is worse than no ring,
  because the absent one is visibly absent.
"""

from __future__ import annotations

from dataclasses import dataclass

# Riot's own arithmetic: see the module docstring.
UU_PER_METRE = 100.0

_DOC = "docs/Valorant Agent Ability Details.md"


@dataclass(frozen=True)
class Figure:
    """
    One published number and the page it came from.

    A source per *figure* rather than per ability, because one citation
    covering a row of numbers is a citation standing behind numbers it never
    backed.  `AbilityMechanics` below has ten optional fields and they do not
    all come from the same sentence.
    """

    value: float
    source: str


def _fig(value: float, cite: str, what: str) -> Figure:
    """A figure and the sentence that carries it."""
    return Figure(value, f"{cite} -- {what}")


@dataclass(frozen=True)
class AbilityMechanics:
    """
    What is published about one ability.  Every figure is optional.

    None is the ordinary answer for most fields.  A drone has no radius, a
    smoke has no detection range, and most abilities publish no cooldown at
    all -- so a caller draws each element only where its own figure exists,
    and never falls back to another.
    """

    # Riot's published name for the ability, e.g. "Recon Bolt".  Unlike
    # `AbilityCast.internal_name` this is the text the game shows.
    ability: str
    # The key the **game** binds, which is not the slot this entry is keyed
    # on.  See the module docstring: the two disagree for six of the sixteen
    # agents here, and matching them by letter is the mistake.
    keybind: str
    # The area the thing affects once it is standing, around where it landed.
    radius_uu: Figure | None = None
    # How far it notices somebody -- a trap's search, a bot's hunt, a bolt's
    # scan.  A separate field from `radius_uu` and drawn as a separate ring,
    # because a trigger range and an area of effect are different claims and
    # Chamber's Trademark publishes both: a 10 m search and a 6 m slow.
    detection_radius_uu: Figure | None = None
    # The channel before the thing leaves the caster's hands.
    windup_ms: Figure | None = None
    # After it has landed and before it does anything: an arm time, a fuse.
    activation_delay_ms: Figure | None = None
    # How long it then stands, or how long its effect lasts.
    duration_ms: Figure | None = None
    cooldown_ms: Figure | None = None
    charges: Figure | None = None
    # What it takes to shoot it down, where it is a thing that can be shot.
    deployable_hp: Figure | None = None
    # Whether this ability's own placements *are* a wall, or None -- which is
    # the answer for every ability but one.
    #
    # `"segments"` and nothing else.  Sage's Barrier Orb opens a channel per
    # segment at one instant and each carries its own spawn transform, so the
    # line, its length and its orientation are all read out of the capture.
    #
    # **There were two other values and they were wrong.**  `"along_facing"`
    # and `"across_facing"` were going to draw Phoenix's Blaze, Harbor's High
    # Tide and Vyse's Shear from the caster's decoded yaw at a looked-up
    # length, and two separate findings killed the idea rather than the
    # figures:
    #
    #   * Blaze and High Tide **have no length**.  Each casts a steerable
    #     missile that leaves a path on the ground, and the wall rises from the
    #     caster and spreads along that path until it runs out or meets
    #     geometry -- so the shape is a polyline of a length that differs every
    #     cast, and there is no figure to look up because there is no number.
    #   * Shear is placed **on vertical terrain**, perpendicular to the ground,
    #     so its axis is a property of the wall Vyse was looking at rather than
    #     of the direction her body faced.
    #
    # And the orientation was weak even where the idea held: on Sage's wall,
    # the one whose axis *is* decoded, the caster's yaw is within 15 degrees of
    # parallel for 66.4% of 125 casts and within 15 degrees of *perpendicular*
    # for 28.8%, because a player can rotate that one as they place it.  So
    # there is one wall in this table and it is the measured one.
    wall: str | None = None
    # Where the shape above comes from.  A kind is a claim about the game like
    # any figure here, and a bare enum with no citation is what this file
    # refuses everywhere else.
    wall_source: str = ""
    # Whether this ability leaves something standing until it is destroyed,
    # triggered or the round ends.
    #
    # A separate question from `duration_ms`, and conflating the two was an
    # error worth naming.  A Trademark publishes a 4-second slow and a Turret
    # publishes no duration at all, but neither number is how long the thing is
    # *on the map*: the trap waits until somebody walks past it and the turret
    # stands until it is shot.  Read as a lifetime, the first would have swept
    # a trap off the map four seconds after it was placed, and the second would
    # have left a flash hanging in the air for the rest of the round.
    #
    # So `duration_ms` means how long the effect lasts, this means whether the
    # thing itself is still there, and an ability with neither is a *moment* --
    # a flash pops, a dart detonates -- which a view shows briefly and then
    # lets go.  See `castlayer` for what each of the three does.
    persists: bool = False
    # Whether the thing dies with the player who left it there.
    #
    # Only meaningful beside `persists`, and a narrower claim than it: a
    # Trademark and a Rendezvous anchor are removed the moment Chamber dies,
    # and so are Cypher's Trapwire and Spycam, which is a published rule of the
    # game joined to a death the capture states outright.  Killjoy's utility is
    # deliberately **not** flagged: hers is disabled while she is far from it
    # and destroyed only by damage, so it survives her.
    #
    # The join is made where the snapshot is -- `castlayer.castsAt` -- and
    # never in `abilitiesAt`, which keeps a round's full record on purpose and
    # is parity-pinned in two languages.
    destroyed_on_caster_death: bool = False
    # Whether this ability looks at the map: a drone, a camera.
    #
    # A pawn with this set gets the same view cone a living player gets, from
    # its own decoded position and yaw.  It is not a figure because it is not a
    # measurement -- it is which abilities have a camera on them.
    sees: bool = False
    # Whether this ability occludes sight.  `smoke_for` below is the only
    # reader and it refuses unless the radius and the duration are *both*
    # published, so a True here with a missing figure occludes nothing.  That
    # is deliberate rather than an oversight: Clove's Ruse is a round smoke and
    # nobody publishes its radius, and saying so is better than either
    # inventing one or pretending the ability does not block sight.
    blocks_sight: bool = False


@dataclass(frozen=True)
class SmokeFacts:
    """A placement that blocks sight: how wide, how long, and on whose word."""

    radius_uu: float
    duration_ms: int
    source: str

    @property
    def radius_m(self) -> float:
        return self.radius_uu / UU_PER_METRE

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000.0


_WIKI = "valorant.fandom.com/wiki"

# The Weird Gloop VALORANT wiki, and it is the better source rather than merely
# the reachable one: every row of its stats tables is tagged with how the value
# was established -- *Game files*, a named patch note, or *estimated and
# manually tested* -- so a figure taken from it can say which of those it is.
# `valorant.fandom.com` answers 402 from this machine and `liquipedia.net`
# answers 403, which is why the figures already here cite pages nobody could
# re-open.  A missing row on this wiki is also evidence: its tables are
# thorough, so an ability with no radius there probably has no reliable public
# figure at all, and stays ringless.
_GLOOP = "wiki.playvalorant.com/en-us"

# Per-agent citations.  Each names the research file in this tree and the page
# that file cites for that agent, so a reader can reach the figure in two hops
# and can tell which agent's numbers moved when the wiki does.
_ASTRA = f"{_DOC} (Astra), {_WIKI}/Astra"
_BREACH = f"{_DOC} (Breach), {_WIKI}/Breach"
_BRIMSTONE = f"{_DOC} (Brimstone), {_WIKI}/Brimstone"
_CHAMBER = f"{_DOC} (Chamber), {_WIKI}/Chamber"
_CLOVE = f"{_DOC} (Clove), {_WIKI}/Clove"
_CYPHER = f"{_DOC} (Cypher), liquipedia.net/valorant/Cypher"
_FADE = f"{_DOC} (Fade), {_WIKI}/Fade"
_JETT = f"{_DOC} (Jett), {_WIKI}/Jett"
_KILLJOY = f"{_DOC} (Killjoy), {_WIKI}/Killjoy"
_OMEN = f"{_DOC} (Omen), {_WIKI}/Omen"
_PHOENIX = f"{_DOC} (Phoenix), {_WIKI}/Phoenix"
_RAZE = f"{_DOC} (Raze), {_WIKI}/Raze"
_REYNA = f"{_DOC} (Reyna), {_WIKI}/Reyna"
_SAGE = f"{_DOC} (Sage), liquipedia.net/valorant/Sage"
_SKYE = f"{_DOC} (Skye), {_WIKI}/Skye"
_SOVA = f"{_DOC} (Sova), {_WIKI}/Sova"

# Four agents the research file does not cover, kept from the table this one
# replaces.  Their radii were researched when the range ring was written and
# there is no reason to drop them for being outside one document's scope.
_DEADLOCK = f"{_WIKI}/GravNet"
_GEKKO = f"{_WIKI}/Mosh_Pit"
_HARBOR = f"{_WIKI}/Cove"
_VYSE = f"{_WIKI}/Razorvine"

# Riot's own patch note, and the one first-party figure in this file.  It is
# also what fixes the unit for every other figure here -- see the docstring.
_SKY_SMOKE = "Riot patch note, Sky Smoke: Radius increased 410 >>> 415"


# Keyed by (codename, slot) -- exactly what the archetype path states.  The
# codename is spelled as the path spells it, including `AggroBot`.
_MECHANICS: dict[tuple[str, str], AbilityMechanics] = {
    # -- Astra (Rift) ----------------------------------------------------
    ("Rift", "C"): AbilityMechanics(
        ability="Gravity Well",
        keybind="C",
        windup_ms=_fig(1250.0, _ASTRA, "windup 1.25 s"),
        duration_ms=_fig(2000.0, _ASTRA, "pull duration 2.0 s"),
        cooldown_ms=_fig(60000.0, _ASTRA, "cooldown 60 s"),
    ),
    ("Rift", "Q"): AbilityMechanics(
        ability="Nova Pulse",
        keybind="Q",
        windup_ms=_fig(1000.0, _ASTRA, "windup 1.0 s"),
        cooldown_ms=_fig(60000.0, _ASTRA, "cooldown 60 s"),
    ),
    ("Rift", "E"): AbilityMechanics(
        ability="Nebula",
        keybind="E",
        radius_uu=_fig(475.0, _ASTRA, "smoke radius 4.75 m"),
        # 14.25 s, and the table this file replaces said 15.0 s.  The research
        # file is the first source in this tree to state it.
        duration_ms=_fig(14250.0, _ASTRA, "active duration 14.25 s"),
        cooldown_ms=_fig(35000.0, _ASTRA, "cooldown 35 s"),
        blocks_sight=True,
    ),
    ("Rift", "X"): AbilityMechanics(
        ability="Cosmic Divide",
        keybind="X",
        duration_ms=_fig(21000.0, _ASTRA, "wall duration 21.0 s"),
    ),
    # -- Breach ----------------------------------------------------------
    ("Breach", "C"): AbilityMechanics(
        ability="Aftershock",
        keybind="C",
        # Riot's own patch note, which makes this one of the two first-party
        # figures in the file: v3.0 reads "Explosion radius increased 260 >>>
        # 300", and 300 uu is 3 m on the same arithmetic Sky Smoke fixes.
        #
        # **The shape is a cylinder and the ring is the smaller claim.**  The
        # blast is projected in front of the wall it was cast through, about
        # 10 m long by this radius, so a circle at the detonation point covers
        # a real part of it and overstates nothing -- where a 3 m ring drawn as
        # if it were the whole ability would understate the length.  The length
        # is not written here because no first-party figure states it.
        radius_uu=_fig(
            300.0,
            "Riot patch note v3.0, Aftershock: Explosion radius increased 260 >>> 300",
            "blast radius 3.0 m; the blast is a cylinder about 10 m long and this is its radius",
        ),
        charges=_fig(1.0, _BREACH, "max charges 1"),
    ),
    ("Breach", "Q"): AbilityMechanics(
        ability="Flashpoint",
        keybind="Q",
        charges=_fig(2.0, _BREACH, "max charges 2"),
    ),
    ("Breach", "E"): AbilityMechanics(
        ability="Fault Line",
        keybind="E",
        windup_ms=_fig(1100.0, _BREACH, "windup delay 1.1 s"),
        duration_ms=_fig(2500.0, _BREACH, "concuss debuff 2.5 s"),
        cooldown_ms=_fig(60000.0, _BREACH, "cooldown 60 s"),
        charges=_fig(1.0, _BREACH, "max charges 1"),
    ),
    ("Breach", "X"): AbilityMechanics(ability="Rolling Thunder", keybind="X"),
    # -- Brimstone (Sarge) -----------------------------------------------
    # The slot letters are shuffled against the keybinds here: `C` is the
    # signature Sky Smoke the game binds to E, and `E` is the Stim Beacon it
    # binds to C.  See the module docstring.
    ("Sarge", "C"): AbilityMechanics(
        ability="Sky Smoke",
        keybind="E",
        radius_uu=_fig(415.0, _SKY_SMOKE, "smoke radius 415 uu"),
        duration_ms=_fig(19250.0, _BRIMSTONE, "active duration 19.25 s"),
        charges=_fig(3.0, _BRIMSTONE, "max charges 3"),
        blocks_sight=True,
    ),
    ("Sarge", "E"): AbilityMechanics(
        ability="Stim Beacon",
        keybind="C",
        duration_ms=_fig(12000.0, _BRIMSTONE, "field duration 12.0 s"),
        charges=_fig(1.0, _BRIMSTONE, "max charges 1"),
    ),
    ("Sarge", "Q"): AbilityMechanics(
        ability="Incendiary",
        keybind="Q",
        radius_uu=_fig(450.0, f"{_WIKI}/Incendiary", "fire zone radius 4.5 m"),
        duration_ms=_fig(7000.0, _BRIMSTONE, "burn duration 7.0 s"),
        charges=_fig(1.0, _BRIMSTONE, "max charges 1"),
    ),
    ("Sarge", "X"): AbilityMechanics(
        ability="Orbital Strike",
        keybind="X",
        windup_ms=_fig(2000.0, _BRIMSTONE, "windup 2.0 s"),
        duration_ms=_fig(3000.0, _BRIMSTONE, "active duration 3.0 s"),
    ),
    # -- Chamber (Deadeye) -----------------------------------------------
    ("Deadeye", "C"): AbilityMechanics(
        ability="Trademark",
        persists=True,
        destroyed_on_caster_death=True,
        keybind="C",
        radius_uu=_fig(600.0, _CHAMBER, "slow radius 6 m"),
        detection_radius_uu=_fig(1000.0, _CHAMBER, "search radius 10 m"),
        activation_delay_ms=_fig(2000.0, _CHAMBER, "arm time 2.0 s"),
        duration_ms=_fig(4000.0, _CHAMBER, "50% slow for 4.0 s"),
        cooldown_ms=_fig(30000.0, _CHAMBER, "recall cooldown 30 s"),
        charges=_fig(1.0, _CHAMBER, "max charges 1"),
        deployable_hp=_fig(20.0, _CHAMBER, "deployable 20 HP"),
    ),
    ("Deadeye", "Q"): AbilityMechanics(
        ability="Headhunter",
        keybind="Q",
        charges=_fig(8.0, _CHAMBER, "max capacity 8 bullets"),
    ),
    ("Deadeye", "E"): AbilityMechanics(
        ability="Rendezvous",
        persists=True,
        destroyed_on_caster_death=True,
        keybind="E",
        detection_radius_uu=_fig(1800.0, _CHAMBER, "teleport radius 18 m"),
        cooldown_ms=_fig(30000.0, _CHAMBER, "cooldown 30 s on use or recall"),
        charges=_fig(1.0, _CHAMBER, "one anchor"),
        deployable_hp=_fig(50.0, _CHAMBER, "anchor 50 HP"),
    ),
    ("Deadeye", "X"): AbilityMechanics(
        ability="Tour De Force",
        keybind="X",
        windup_ms=_fig(2300.0, _CHAMBER, "windup 2.3 s"),
        duration_ms=_fig(4000.0, _CHAMBER, "50% slow field for 4.0 s"),
        charges=_fig(5.0, _CHAMBER, "capacity 5 bullets"),
    ),
    # -- Clove (Smonk) ---------------------------------------------------
    ("Smonk", "C"): AbilityMechanics(
        ability="Pick-me-up",
        keybind="C",
        windup_ms=_fig(700.0, _CLOVE, "windup 0.7 s"),
        duration_ms=_fig(10000.0, _CLOVE, "health buff 10.0 s"),
        charges=_fig(1.0, _CLOVE, "max charges 1"),
    ),
    ("Smonk", "Q"): AbilityMechanics(
        ability="Meddle",
        keybind="Q",
        radius_uu=_fig(400.0, _CLOVE, "radius 4.0 m"),
        activation_delay_ms=_fig(750.0, _CLOVE, "0.75 s after ground contact"),
        duration_ms=_fig(5000.0, _CLOVE, "active duration 5.0 s"),
        charges=_fig(1.0, _CLOVE, "max charges 1"),
    ),
    ("Smonk", "E"): AbilityMechanics(
        ability="Ruse",
        keybind="E",
        # The gap this table carried longest, and it is closed by a source
        # rather than by resemblance.  It had no radius at all -- 365 casts,
        # the most-used ability in the reference library, drawing no ring and
        # occluding nothing -- and the tempting fix was to give it Omen's 410,
        # which is not a citation but a similarity.  The Weird Gloop wiki
        # publishes 4.0 m tagged *Game files*, so it stands on its own figure.
        radius_uu=_fig(400.0, f"{_GLOOP}/Ruse", "radius 4.0 m, tagged Game files"),
        windup_ms=_fig(1000.0, _CLOVE, "deployment 1.0 s"),
        # The research file contradicts itself here: its summary table gives
        # Ruse (Alive) as 14.25 s and its own Clove section gives 14.0 s.  The
        # section wins because it is the more specific of the two, and the
        # disagreement is written down rather than silently resolved.
        #
        # The 6.0 s post-death duration is deliberately not carried.  Joining
        # it would mean deciding per cast whether Clove was alive, and the
        # tempting join -- the internal name, which arrives as `Post Death`
        # 450 times and `New Smoke` 969 -- is a hypothesis nobody has scored
        # against `Snapshot.alive`.  One duration that is right most of the
        # time beats two applied on a guess.
        duration_ms=_fig(
            14000.0,
            _CLOVE,
            "active duration 14.0 s while alive; the summary table of the same "
            "file says 14.25 s and the 6.0 s post-death figure is not applied",
        ),
        cooldown_ms=_fig(40000.0, _CLOVE, "cooldown 40 s"),
        charges=_fig(2.0, _CLOVE, "max charges 2"),
        blocks_sight=True,
    ),
    ("Smonk", "X"): AbilityMechanics(
        ability="Not Dead Yet",
        keybind="X",
        windup_ms=_fig(1500.0, _CLOVE, "revive channel 1.5 s"),
        duration_ms=_fig(10000.0, _CLOVE, "elimination window 10.0 s"),
    ),
    # -- Cypher (Gumshoe) ------------------------------------------------
    ("Gumshoe", "C"): AbilityMechanics(
        ability="Cyber Cage",
        persists=True,
        keybind="Q",
        radius_uu=_fig(372.0, f"{_WIKI}/Cyber_Cage", "cylinder radius 3.72 m"),
        duration_ms=_fig(7000.0, _CYPHER, "active duration 7.0 s"),
        charges=_fig(2.0, _CYPHER, "max charges 2"),
        # Not `blocks_sight`, and the reason is the clock rather than the
        # shape: a Cyber Cage is thrown hidden and activated remotely, so the
        # instant it starts occluding is a decision nothing here decodes.  A
        # round smoke blocks from the moment it lands; this does not.
    ),
    ("Gumshoe", "E"): AbilityMechanics(
        ability="Trapwire",
        persists=True,
        destroyed_on_caster_death=True,
        keybind="C",
        activation_delay_ms=_fig(500.0, _CYPHER, "0.5 s reveal fade-in"),
        charges=_fig(2.0, _CYPHER, "max charges 2"),
        deployable_hp=_fig(20.0, _CYPHER, "deployable 20 HP"),
    ),
    ("Gumshoe", "Q"): AbilityMechanics(
        ability="Spycam",
        persists=True,
        destroyed_on_caster_death=True,
        keybind="E",
        cooldown_ms=_fig(45000.0, _CYPHER, "destruction cooldown 45 s"),
        charges=_fig(1.0, _CYPHER, "max charges 1"),
    ),
    ("Gumshoe", "X"): AbilityMechanics(
        ability="Neural Theft",
        keybind="X",
        detection_radius_uu=_fig(1800.0, _CYPHER, "maximum range 18 m"),
        activation_delay_ms=_fig(4000.0, _CYPHER, "4.0 s between the two scans"),
    ),
    # -- Fade (BountyHunter) ---------------------------------------------
    ("BountyHunter", "C"): AbilityMechanics(
        ability="Prowler",
        keybind="C",
        duration_ms=_fig(2500.0, _FADE, "duration 2.5 s"),
        charges=_fig(2.0, _FADE, "max charges 2"),
        deployable_hp=_fig(60.0, _FADE, "creature 60 HP"),
    ),
    ("BountyHunter", "Q"): AbilityMechanics(
        ability="Seize",
        keybind="Q",
        duration_ms=_fig(4500.0, _FADE, "tether duration 4.5 s"),
        charges=_fig(1.0, _FADE, "max charges 1"),
    ),
    ("BountyHunter", "E"): AbilityMechanics(
        ability="Haunt",
        keybind="E",
        duration_ms=_fig(1500.0, _FADE, "spotting duration 1.5 s"),
        cooldown_ms=_fig(60000.0, _FADE, "cooldown 60 s"),
        charges=_fig(1.0, _FADE, "max charges 1"),
        deployable_hp=_fig(1.0, _FADE, "watcher 1 HP"),
    ),
    ("BountyHunter", "X"): AbilityMechanics(ability="Nightfall", keybind="X"),
    # -- Jett (Wushu) ----------------------------------------------------
    ("Wushu", "C"): AbilityMechanics(
        ability="Cloudburst",
        keybind="C",
        radius_uu=_fig(335.0, f"{_WIKI}/Cloudburst", "smoke radius 3.35 m"),
        # 2.5 s, and the table this file replaces said 4.5 s.
        duration_ms=_fig(2500.0, _JETT, "active duration 2.5 s"),
        charges=_fig(2.0, _JETT, "max charges 2"),
        blocks_sight=True,
    ),
    ("Wushu", "Q"): AbilityMechanics(
        ability="Updraft",
        keybind="Q",
        windup_ms=_fig(600.0, _JETT, "windup delay 0.6 s"),
        charges=_fig(1.0, _JETT, "max charges 1"),
    ),
    ("Wushu", "E"): AbilityMechanics(
        ability="Tailwind",
        keybind="E",
        activation_delay_ms=_fig(1000.0, _JETT, "activation delay 1.0 s"),
        duration_ms=_fig(7500.0, _JETT, "priming window 7.5 s"),
        charges=_fig(1.0, _JETT, "max charges 1"),
    ),
    ("Wushu", "X"): AbilityMechanics(
        ability="Blade Storm",
        keybind="X",
        charges=_fig(5.0, _JETT, "5 throwing knives"),
    ),
    # -- Killjoy ---------------------------------------------------------
    ("Killjoy", "C"): AbilityMechanics(
        ability="Nanoswarm",
        persists=True,
        keybind="C",
        radius_uu=_fig(450.0, f"{_WIKI}/Nanoswarm", "damage radius 4.5 m"),
        duration_ms=_fig(4000.0, _KILLJOY, "active duration 4.0 s"),
        charges=_fig(2.0, _KILLJOY, "max charges 2"),
        deployable_hp=_fig(20.0, _KILLJOY, "deployable 20 HP"),
    ),
    ("Killjoy", "Q"): AbilityMechanics(
        ability="Alarmbot",
        persists=True,
        keybind="Q",
        detection_radius_uu=_fig(
            550.0,
            f"{_WIKI}/Alarmbot",
            "detects enemies at 5.5 m",
        ),
        duration_ms=_fig(4000.0, _KILLJOY, "vulnerable debuff 4.0 s"),
        cooldown_ms=_fig(20000.0, _KILLJOY, "recall cooldown 20 s"),
        charges=_fig(1.0, _KILLJOY, "max charges 1"),
        deployable_hp=_fig(20.0, _KILLJOY, "deployable 20 HP"),
    ),
    ("Killjoy", "E"): AbilityMechanics(
        ability="Turret",
        persists=True,
        keybind="E",
        cooldown_ms=_fig(20000.0, _KILLJOY, "recall cooldown 20 s"),
        charges=_fig(1.0, _KILLJOY, "max charges 1"),
        deployable_hp=_fig(100.0, _KILLJOY, "deployable 100 HP"),
    ),
    ("Killjoy", "X"): AbilityMechanics(
        ability="Lockdown",
        persists=True,
        keybind="X",
        windup_ms=_fig(13000.0, _KILLJOY, "windup delay 13.0 s"),
        duration_ms=_fig(8000.0, _KILLJOY, "detain 8.0 s"),
        deployable_hp=_fig(200.0, _KILLJOY, "deployable 200 HP"),
    ),
    # -- Omen (Wraith) ---------------------------------------------------
    ("Wraith", "C"): AbilityMechanics(
        ability="Dark Cover",
        keybind="E",
        radius_uu=_fig(410.0, f"{_WIKI}/Dark_Cover", "smoke radius 4.1 m"),
        duration_ms=_fig(15000.0, _OMEN, "active duration 15.0 s"),
        cooldown_ms=_fig(40000.0, _OMEN, "cooldown 40 s"),
        charges=_fig(2.0, _OMEN, "max charges 2"),
        blocks_sight=True,
    ),
    ("Wraith", "E"): AbilityMechanics(
        ability="Shrouded Step",
        keybind="C",
        windup_ms=_fig(1000.0, _OMEN, "channel time about 1.0 s"),
        charges=_fig(2.0, _OMEN, "max charges 2"),
    ),
    ("Wraith", "Q"): AbilityMechanics(
        ability="Paranoia",
        keybind="Q",
        duration_ms=_fig(2000.0, _OMEN, "nearsight and deafen 2.0 s"),
        charges=_fig(1.0, _OMEN, "max charges 1"),
    ),
    ("Wraith", "X"): AbilityMechanics(
        ability="From the Shadows",
        keybind="X",
        windup_ms=_fig(4000.0, _OMEN, "channel time 4.0 s"),
    ),
    # -- Phoenix ---------------------------------------------------------
    ("Phoenix", "C"): AbilityMechanics(
        ability="Hot Hands",
        keybind="E",
        radius_uu=_fig(450.0, f"{_WIKI}/Hot_Hands", "fire zone radius 4.5 m"),
        charges=_fig(1.0, _PHOENIX, "max charges 1"),
    ),
    ("Phoenix", "Q"): AbilityMechanics(
        ability="Blaze",
        keybind="C",
        duration_ms=_fig(8000.0, _PHOENIX, "duration about 8.0 s"),
        charges=_fig(1.0, _PHOENIX, "max charges 1"),
    ),
    ("Phoenix", "E"): AbilityMechanics(
        ability="Curveball",
        keybind="Q",
        charges=_fig(2.0, _PHOENIX, "max charges 2"),
    ),
    ("Phoenix", "X"): AbilityMechanics(
        ability="Run it Back",
        keybind="X",
        duration_ms=_fig(10000.0, _PHOENIX, "duration about 10.0 s"),
    ),
    # -- Raze (Clay) -----------------------------------------------------
    ("Clay", "C"): AbilityMechanics(
        ability="Paint Shells",
        keybind="E",
        charges=_fig(1.0, _RAZE, "max charges 1, recharges on 2 kills"),
    ),
    ("Clay", "Q"): AbilityMechanics(
        ability="Blast Pack",
        keybind="Q",
        charges=_fig(2.0, _RAZE, "max charges 2"),
    ),
    ("Clay", "E"): AbilityMechanics(
        ability="Boom Bot",
        keybind="C",
        charges=_fig(1.0, _RAZE, "max charges 1"),
        deployable_hp=_fig(60.0, _RAZE, "bot 60 HP"),
    ),
    ("Clay", "X"): AbilityMechanics(ability="Showstopper", keybind="X"),
    # -- Reyna (Vampire) -------------------------------------------------
    ("Vampire", "C"): AbilityMechanics(
        ability="Leer",
        keybind="C",
        charges=_fig(2.0, _REYNA, "max charges 2"),
        deployable_hp=_fig(100.0, _REYNA, "eye 100 HP"),
    ),
    ("Vampire", "Q"): AbilityMechanics(
        ability="Devour",
        keybind="Q",
        charges=_fig(2.0, _REYNA, "max charges 2, shared with Dismiss"),
    ),
    ("Vampire", "E"): AbilityMechanics(
        ability="Dismiss",
        keybind="E",
        duration_ms=_fig(2000.0, _REYNA, "intangible for 2.0 s"),
        charges=_fig(2.0, _REYNA, "max charges 2, shared with Devour"),
    ),
    ("Vampire", "X"): AbilityMechanics(
        ability="Empress",
        keybind="X",
        duration_ms=_fig(30000.0, _REYNA, "duration about 30 s, resets on kill"),
    ),
    # -- Sage (Thorne) ---------------------------------------------------
    ("Thorne", "C"): AbilityMechanics(
        ability="Slow Orb",
        keybind="Q",
        duration_ms=_fig(7000.0, _SAGE, "active duration 7.0 s"),
        charges=_fig(2.0, _SAGE, "max charges 2"),
    ),
    ("Thorne", "Q"): AbilityMechanics(
        ability="Healing Orb",
        keybind="E",
        duration_ms=_fig(5000.0, _SAGE, "heals over 5.0 s"),
        cooldown_ms=_fig(45000.0, _SAGE, "cooldown 45 s"),
    ),
    ("Thorne", "E"): AbilityMechanics(
        ability="Barrier Orb",
        wall="segments",
        wall_source=(
            "measured over 125 casts in .cache/positions -- four "
            "Wall_Segment_Fortifying actors per barrier, exactly collinear "
            "(max perpendicular deviation 0.0 uu), 260 uu apart, spanning "
            "780 uu; the wall is drawn from those coordinates and no length "
            "is looked up"
        ),
        keybind="C",
        # A wall, so no radius and no `blocks_sight` -- see the docstring.
        activation_delay_ms=_fig(3300.0, _SAGE, "fortifies after 3.3 s"),
        duration_ms=_fig(40000.0, _SAGE, "max duration 40.0 s"),
        charges=_fig(1.0, _SAGE, "max charges 1"),
        deployable_hp=_fig(400.0, _SAGE, "segment 400 HP, fortifying to 800"),
    ),
    ("Thorne", "X"): AbilityMechanics(ability="Resurrection", keybind="X"),
    # -- Skye (Guide) ----------------------------------------------------
    ("Guide", "C"): AbilityMechanics(ability="Regrowth", keybind="C"),
    ("Guide", "Q"): AbilityMechanics(
        ability="Trailblazer",
        keybind="Q",
        duration_ms=_fig(6000.0, _SKYE, "duration 6.0 s"),
        charges=_fig(1.0, _SKYE, "max charges 1"),
        deployable_hp=_fig(80.0, _SKYE, "creature 80 HP"),
    ),
    ("Guide", "E"): AbilityMechanics(
        ability="Guiding Light",
        keybind="E",
        charges=_fig(1.0, _SKYE, "max charges 1"),
    ),
    ("Guide", "X"): AbilityMechanics(
        ability="Seekers",
        keybind="X",
        charges=_fig(3.0, _SKYE, "3 seekers"),
    ),
    # -- Sova (Hunter) ---------------------------------------------------
    ("Hunter", "C"): AbilityMechanics(
        ability="Shock Bolt",
        keybind="Q",
        # The **outer** radius, which is where the damage stops rather than
        # where it is worst: the bolt does 75 at the centre and 1 at this edge.
        # A single ring can only be one of the two and the outer is the honest
        # one -- a ring at the inner radius would claim the ability stops where
        # it merely weakens.
        radius_uu=_fig(
            400.0,
            f"{_GLOOP}/Shock_Bolt",
            "outer radius 4.0 m (inner 1.5 m), tagged Game files",
        ),
        charges=_fig(2.0, _SOVA, "max charges 2"),
    ),
    ("Hunter", "Q"): AbilityMechanics(
        ability="Recon Bolt",
        keybind="E",
        # A *scan* radius rather than an area of effect: the bolt reveals
        # inside it and does nothing to anybody.  The table this file replaces
        # carried it as `radius_uu`, which drew a 30 m area-of-effect ring
        # around a thing that has no effect at all.
        detection_radius_uu=_fig(3000.0, f"{_WIKI}/Recon_Bolt", "scanning radius 30 m"),
        duration_ms=_fig(3200.0, _SOVA, "3.2 s, two sonar pulses 1.6 s apart"),
        cooldown_ms=_fig(60000.0, _SOVA, "cooldown 60 s"),
        charges=_fig(1.0, _SOVA, "max charges 1"),
        deployable_hp=_fig(20.0, _SOVA, "deployable 20 HP"),
    ),
    ("Hunter", "E"): AbilityMechanics(
        ability="Owl Drone",
        sees=True,
        keybind="C",
        duration_ms=_fig(7000.0, _SOVA, "flight uptime 7.0 s"),
        charges=_fig(1.0, _SOVA, "max charges 1"),
        deployable_hp=_fig(100.0, _SOVA, "drone 100 HP"),
    ),
    ("Hunter", "X"): AbilityMechanics(
        ability="Hunter's Fury",
        keybind="X",
        duration_ms=_fig(6000.0, _SOVA, "cast window 6.0 s"),
        charges=_fig(3.0, _SOVA, "3 energy blasts"),
    ),
    # -- Four agents the research file does not cover --------------------
    ("Cable", "C"): AbilityMechanics(
        ability="GravNet",
        keybind="C",
        radius_uu=_fig(650.0, _DEADLOCK, "radius 6.5 m"),
        charges=_fig(1.0, _DEADLOCK, "max charges 1"),
    ),
    ("AggroBot", "C"): AbilityMechanics(
        ability="Mosh Pit",
        keybind="C",
        radius_uu=_fig(620.0, _GEKKO, "outer radius 6.2 m, inner 5.5 m"),
        charges=_fig(1.0, _GEKKO, "max charges 1"),
    ),
    ("Mage", "E"): AbilityMechanics(
        ability="Cove",
        keybind="E",
        radius_uu=_fig(460.0, _HARBOR, "radius 4.6 m"),
        duration_ms=_fig(15000.0, _HARBOR, "active duration 15.0 s"),
        charges=_fig(1.0, _HARBOR, "max charges 1"),
        blocks_sight=True,
    ),
    ("Nox", "C"): AbilityMechanics(
        ability="Razorvine",
        persists=True,
        keybind="C",
        radius_uu=_fig(625.0, _VYSE, "radius 6.25 m"),
        charges=_fig(2.0, _VYSE, "max charges 2"),
    ),
    # -- Named but not measured ------------------------------------------
    #
    # Every entry below carries an ability name and a keybind and no figure at
    # all, and that is the whole point of it.  The name is what joins to Riot's
    # published catalogue in `art.AgentArt.ability_named`, so an agent missing
    # from this table has no picture for any of its marks and the canvas used
    # to print the archetype's own slot letter instead -- an `E` that is not
    # the key the player pressed, over an ability nobody can identify from it.
    #
    # The evidence for which published ability sits in which internal slot is
    # the decode's own internal name, quoted beside each entry.  Where the
    # internal name settles three of an agent's four slots the fourth is what
    # is left, which is a bijection rather than a guess:
    # `tests/test_abilityfacts.py` asserts exactly that.
    #
    # No figure is invented to go with a name.  An ability here draws its icon
    # and no ring, which is what it drew before and is visibly absent.
    # -- Deadlock (Cable), C is above ------------------------------------
    ("Cable", "Q"): AbilityMechanics(ability="Sonic Sensor", keybind="Q"),
    ("Cable", "E"): AbilityMechanics(ability="Barrier Mesh", keybind="E"),
    ("Cable", "X"): AbilityMechanics(ability="Annihilation", keybind="X"),
    # -- Gekko (AggroBot), C is above ------------------------------------
    ("AggroBot", "Q"): AbilityMechanics(ability="Wingman", keybind="Q"),
    ("AggroBot", "E"): AbilityMechanics(ability="Dizzy", keybind="E"),
    ("AggroBot", "X"): AbilityMechanics(ability="Thrash", keybind="X"),
    # -- Harbor (Mage), E is above ---------------------------------------
    ("Mage", "C"): AbilityMechanics(ability="Storm Surge", keybind="C"),
    ("Mage", "Q"): AbilityMechanics(
        ability="High Tide",
        keybind="Q",
    ),
    ("Mage", "X"): AbilityMechanics(ability="Reckoning", keybind="X"),
    # -- Iso (Sequoia) ----------------------------------------------------
    ("Sequoia", "C"): AbilityMechanics(ability="Contingency", keybind="C"),
    ("Sequoia", "Q"): AbilityMechanics(ability="Undercut", keybind="Q"),
    ("Sequoia", "E"): AbilityMechanics(ability="Double Tap", keybind="E"),
    ("Sequoia", "X"): AbilityMechanics(ability="Kill Contract", keybind="X"),
    # -- KAY/O (Grenadier) ------------------------------------------------
    #
    # Shuffled, like Brimstone: the internal `C` is the flash the game binds to
    # Q and the internal `Q` is the grenade it binds to C.  Naming these two by
    # letter would put the frag's icon on every flash in the library.
    ("Grenadier", "C"): AbilityMechanics(ability="FLASH/drive", keybind="Q"),
    ("Grenadier", "Q"): AbilityMechanics(ability="FRAG/ment", keybind="C"),
    ("Grenadier", "E"): AbilityMechanics(ability="ZERO/point", keybind="E"),
    ("Grenadier", "X"): AbilityMechanics(ability="NULL/cmd", keybind="X"),
    # -- Neon (Sprinter) ---------------------------------------------------
    ("Sprinter", "C"): AbilityMechanics(ability="Fast Lane", keybind="C"),
    ("Sprinter", "Q"): AbilityMechanics(ability="Relay Bolt", keybind="Q"),
    ("Sprinter", "E"): AbilityMechanics(ability="High Gear", keybind="E"),
    ("Sprinter", "X"): AbilityMechanics(ability="Overdrive", keybind="X"),
    # -- Tejo (Cashew) -----------------------------------------------------
    ("Cashew", "C"): AbilityMechanics(
        ability="Stealth Drone",
        keybind="C",
        sees=True,
    ),
    ("Cashew", "Q"): AbilityMechanics(ability="Special Delivery", keybind="Q"),
    ("Cashew", "E"): AbilityMechanics(ability="Guided Salvo", keybind="E"),
    ("Cashew", "X"): AbilityMechanics(ability="Armageddon", keybind="X"),
    # -- Vyse (Nox), C is above --------------------------------------------
    ("Nox", "Q"): AbilityMechanics(
        ability="Shear",
        keybind="Q",
    ),
    ("Nox", "E"): AbilityMechanics(ability="Arc Rose", keybind="E"),
    ("Nox", "X"): AbilityMechanics(ability="Steel Garden", keybind="X"),
    # -- Waylay (Terra) ----------------------------------------------------
    ("Terra", "C"): AbilityMechanics(ability="Saturate", keybind="C"),
    ("Terra", "Q"): AbilityMechanics(ability="Lightspeed", keybind="Q"),
    ("Terra", "E"): AbilityMechanics(ability="Refract", keybind="E"),
    ("Terra", "X"): AbilityMechanics(ability="Convergent Paths", keybind="X"),
    # -- Yoru (Stealth) ----------------------------------------------------
    ("Stealth", "C"): AbilityMechanics(ability="FAKEOUT", keybind="C"),
    ("Stealth", "Q"): AbilityMechanics(ability="BLINDSIDE", keybind="Q"),
    ("Stealth", "E"): AbilityMechanics(ability="GATECRASH", keybind="E"),
    ("Stealth", "X"): AbilityMechanics(
        ability="DIMENSIONAL DRIFT",
        keybind="X",
    ),
    # -- Miks and Veto, named by what each ability does --------------------
    #
    # These two were the only agents the internal names could not settle on
    # their own -- `Thumper Heal` against M-pulse, Waveform and Harmonize is
    # three ways round, and so is `Rad Eater` against Chokehold, Interceptor
    # and Crosscut -- so they went out as a question rather than a guess and
    # came back answered by what each ability *is*: M-pulse alt-fires between a
    # concuss and a heal, which is exactly the two internal names under `C`;
    # Waveform is an instantly-deployed smoke, which is the 187 casts under
    # `E`; Harmonize spawns nothing, which is why its slot has no placed-object
    # name at all; Crosscut is a placed vortex you look at to teleport, which
    # is `Usable Teleport`; and Interceptor eats utility, which is `Rad Eater`.
    #
    # The keybinds here are the ordinary ones for each ability's manifest slot,
    # and they are the weakest field in these entries -- Riot's `Ability1` and
    # `Ability2` are not reliably Q and E, which is the whole reason `keybind`
    # exists as a looked-up field.  Nothing joins on them; they are shown to a
    # reader.  See `docs/ability-figures-resolved.md` for the whole exchange.
    ("Iris", "C"): AbilityMechanics(ability="M-pulse", keybind="C"),
    # A smoke, and it is the second-most-cast ability in the library at 187 --
    # but no radius and no duration are published for it anywhere, so it does
    # not set `blocks_sight`: `smoke_for` would refuse it either way and a flag
    # standing over two missing figures reads as a smoke that failed to draw.
    ("Iris", "E"): AbilityMechanics(ability="Waveform", keybind="E"),
    ("Iris", "Q"): AbilityMechanics(ability="Harmonize", keybind="Q"),
    ("Iris", "X"): AbilityMechanics(ability="Bassquake", keybind="X"),
    ("Pine", "C"): AbilityMechanics(
        ability="Crosscut",
        keybind="C",
        # A teleport *reach* and not an area of effect, which is why it is here
        # rather than in `radius_uu`: it is the distance from which the vortex
        # can be looked at and used, structurally the same claim as Chamber's
        # Rendezvous 18 m, and drawing one as an area would turn a reach into
        # something the ability does to the ground.
        detection_radius_uu=_fig(
            2400.0,
            f"{_GLOOP}/Crosscut",
            "teleport radius 24 m",
        ),
    ),
    ("Pine", "Q"): AbilityMechanics(ability="Chokehold", keybind="Q"),
    ("Pine", "E"): AbilityMechanics(ability="Interceptor", keybind="E"),
    ("Pine", "X"): AbilityMechanics(ability="Evolution", keybind="X"),
}


def mechanics_for(codename: str, slot: str) -> AbilityMechanics | None:
    """
    What is published about the ability in this agent's slot, or None.

    None is the ordinary answer and must stay drawable as nothing.  This table
    does not pretend to be complete: it covers sixteen agents, an agent
    released after it was written is a miss rather than an error, and Viper is
    a deliberate refusal because the library carries no evidence of which
    internal slot letter each of her abilities occupies.
    """
    if not codename or not slot:
        return None
    return _MECHANICS.get((codename, slot))


def smoke_for(codename: str, slot: str) -> SmokeFacts | None:
    """
    What occludes sight for this agent's slot, or None if nothing here can say.

    Three things have to hold: the ability blocks sight, its radius is
    published, and so is its duration.  Where any of them is missing this
    refuses -- notably for Clove's Ruse, which is a round smoke whose radius
    nobody publishes.  A caller draws and occludes nothing rather than reaching
    for a default: a smoke of a made-up size standing for a made-up length of
    time is the plausible wrong answer, and the whole of `tests/test_positions`
    exists because of those.

    A wall is refused a step earlier, by never setting `blocks_sight`: a cast
    gives one point and no orientation, so a circle drawn for one would block
    behind the caster.
    """
    found = mechanics_for(codename, slot)
    if found is None or not found.blocks_sight:
        return None
    if found.radius_uu is None or found.duration_ms is None:
        return None
    return SmokeFacts(
        radius_uu=found.radius_uu.value,
        duration_ms=int(found.duration_ms.value),
        source=f"{found.radius_uu.source}; {found.duration_ms.source}",
    )
