/**
 * Every layer switch, behind one button.
 *
 * There were four of them on a toolbar and there are now nine, which is more
 * than a stage head can carry beside a map name without the map getting
 * smaller.  A menu is the answer, and the labels do not change: `UTILITY`,
 * `TRAILS`, `SIGHT` and `CALLOUTS` are addressed by exact accessible name from
 * `MapStage.test.tsx` and all three Playwright specs, so they are an interface
 * other files depend on and stay word for word what they were.  What changed is
 * that a spec has to open the menu first, which `e2e/harness.ts` does.
 *
 * Five of the nine cannot always be used, and they are **shown anyway, saying
 * why**.  `SIGHT` needs a radar mask on disk to raycast against; `CALLOUTS` is
 * placed in the 3D scene, so in 2D -- the default -- the CALLOUTS row was
 * simply absent from a menu that claims to list every layer.  The old rule
 * here read "a control that cannot do anything is worse than an explanation of
 * its absence", and that is still true of an *unexplained* dead control; what
 * it got wrong is that a missing row is not an explanation of anything, it
 * reads as a feature that does not exist.  So the row stays, disabled, with
 * the reason under it.
 *
 * The other three -- `UTILITY`, `KILL MARKERS` and `RANGE (SIM)` -- are the
 * mirror image of CALLOUTS and were caught later: `MinimapCanvas` reads all
 * three and `Scene3D` reads none of them, so in 3D they were enabled, flipped
 * cleanly and drew nothing at all.  That is the worse half of the same fault,
 * because a live control that does nothing reads as broken rather than as
 * absent, and nothing failed: `harness.toggleLayer` asserts the box is enabled
 * and that it flipped, both of which were true the whole time.
 *
 * The keys in `shortcuts.ts` still take the same two booleans, so `S` on a map
 * with no mask does nothing rather than leaving a layer switched on for the
 * next replay opened in the session.
 *
 * They are checkboxes rather than pressed buttons because nine of them in one
 * group is a set of choices, and a reader announces a checkbox's state and the
 * size of its group where nine buttons announce nine unrelated things.
 */

import type { LayerKey } from "./playback";
import { usePlayback } from "./playback";
import { CheckRow, Menu } from "./ui";
import type { Glyph } from "./icons";
import { glyphs } from "./icons";

interface Entry {
  key: LayerKey;
  label: string;
  icon: Glyph;
  hint: string;
  /**
   * Tints the row to match the mark it controls.
   *
   * This menu used to be the rail's whole legend, on the grounds that a 24px
   * canvas can carry neither a key nor a `title` -- with the standing proviso
   * that the colours agree with what the rail draws, which nothing could
   * check.  The rail answers for itself now, by hover, and three of the four
   * marks are drawn in the *side's* colour, so a swatch would name a colour
   * they do not have.  Only the spike keeps one, because the plant really is
   * this colour; its hint carries the other two.
   */
  tone?: "spike";
  /**
   * Which canvases actually read this layer.
   *
   * This is the machine-checkable half of the paragraph above, and it exists
   * because the three inert rows in 3D were not a coding slip -- they were a
   * fact about `Scene3D` that no file stated, so nothing could contradict it.
   * `LayersMenu.test.tsx` walks both canvas sources for `layers.<key>` reads
   * and fails when this disagrees with either, in either direction: a layer
   * declared here and unread there, or read there and undeclared here.  It
   * also asserts that a view a layer is *not* drawn in gets a non-null `why`,
   * which is what keeps the two fields from drifting apart.
   */
  drawnIn: ReadonlyArray<"2d" | "3d">;
  /** Why this switch cannot be used here, or null when it can. */
  why?: (where: { hasMask: boolean; is3d: boolean }) => string | null;
}

/** What the map draws. */
export const MAP_LAYERS: Entry[] = [
  {
    key: "utility",
    label: "UTILITY",
    icon: glyphs.utility,
    hint: "Ability pawns and where a placed cast came to rest",
    drawnIn: ["2d"],
    // `Scene3D` reads `trails`, `sight` and `callouts` and no others, so this
    // row, KILL MARKERS and RANGE (SIM) were enabled in 3D and drew nothing --
    // the same fault CALLOUTS had in 2D, and a worse one: a missing row reads
    // as a feature that does not exist, but an *enabled* row that does nothing
    // reads as a broken one.  It also slipped past `harness.toggleLayer`, which
    // asserts the box is enabled and actually flipped and would go on passing.
    why: ({ is3d }) =>
      is3d ? "2D only: the ability marks are drawn on the radar, not in the scene." : null,
  },
  {
    key: "trails",
    label: "TRAILS",
    icon: glyphs.trails,
    hint: "Where each player has just been, split where the record goes quiet",
    drawnIn: ["2d", "3d"],
  },
  {
    key: "killMarkers",
    label: "KILL MARKERS",
    icon: glyphs.killMarkers,
    hint: "Where each player died this round; off shows only the living",
    drawnIn: ["2d"],
    why: ({ is3d }) =>
      is3d ? "2D only: the death marks are drawn on the radar, not in the scene." : null,
  },
  {
    key: "tracers",
    // `(SIM)` for the same reason `RANGE (SIM)` carries it, and about a
    // narrower thing: both ends of this line are decoded -- two players, two
    // places, one real millisecond -- and the line between them is not. A
    // `.vrf` holds no shot at all.
    label: "TRACERS (SIM)",
    icon: glyphs.tracers,
    hint: "The fatal shot, killer to victim -- a line drawn between two decoded positions",
    drawnIn: ["2d", "3d"],
  },
  {
    key: "castMechanics",
    // `(SIM)` covers both halves of what this draws, which have different
    // standing and are deliberately not split into two switches. The throw is
    // decoded at both ends and in its timing -- only the straight line between
    // them is invented, exactly as for TRACERS. The rings and the countdown are
    // looked up in community research, exactly as for RANGE. One ability, one
    // story, one switch, everything dashed.
    label: "MECHANICS (SIM)",
    icon: glyphs.utility,
    hint: "A thrown ability crossing to where it landed, then arming, standing and expiring",
    drawnIn: ["2d"],
    why: ({ is3d }) =>
      is3d ? "2D only: the ability mechanics are drawn on the radar, not in the scene." : null,
  },
  {
    key: "abilityRange",
    // The word is in the label on purpose: a row reading `RANGE` claims a
    // measurement, and this is the one layer here nothing decoded.
    label: "RANGE (SIM)",
    icon: glyphs.zoom,
    hint: "A published radius for a placed ability -- looked up, not decoded",
    drawnIn: ["2d"],
    why: ({ is3d }) =>
      is3d ? "2D only: the range ring is drawn on the radar, not in the scene." : null,
  },
  {
    key: "sight",
    label: "SIGHT",
    icon: glyphs.sight,
    hint: "Every living player's approximate view cone",
    drawnIn: ["2d", "3d"],
    // The mask, and only the mask.  Both canvases draw the same cones from the
    // same `sightlayer` functions now, so there is no view in which this row is
    // inert -- only a map with no radar on disk to raycast against.
    why: ({ hasMask }) =>
      hasMask ? null : "No radar mask on disk for this map, and SIGHT raycasts one.",
  },
  {
    key: "callouts",
    label: "CALLOUTS",
    icon: glyphs.callouts,
    hint: "Riot's own callouts, to check the scene against the minimap",
    drawnIn: ["3d"],
    why: ({ is3d }) =>
      is3d ? null : "3D only: the callouts are placed in the scene, not on the radar.",
  },
];

/** What the timeline strip marks. */
export const EVENT_LAYERS: Entry[] = [
  {
    key: "kills",
    label: "KILLS",
    icon: glyphs.kills,
    hint: "A skull on the rail per kill, in the killer's colour",
    drawnIn: [],
  },
  {
    key: "casts",
    label: "ABILITY CASTS",
    icon: glyphs.casts,
    hint: "A tick per inferred cast: above the rail for ATK, below for DEF",
    drawnIn: [],
  },
  {
    key: "ultimates",
    label: "ULTIMATES",
    icon: glyphs.ultimates,
    hint: "A taller tick in the same lane, per characterUltimateUsed event",
    drawnIn: [],
  },
  {
    key: "spike",
    label: "SPIKE",
    icon: glyphs.spike,
    hint: "A full-height line: gold to plant, green to defuse, orange to detonate",
    drawnIn: [],
    tone: "spike",
  },
];

export function LayersMenu({ hasMask, is3d }: { hasMask: boolean; is3d: boolean }) {
  const layers = usePlayback((state) => state.layers);
  const toggleLayer = usePlayback((state) => state.toggleLayer);

  return (
    <Menu
      label="LAYERS"
      icon={glyphs.layers}
      drop="up"
      title="Which layers the stage draws"
    >
      <p className="menu-title">Map</p>
      {MAP_LAYERS.map((entry) => {
        const why = entry.why?.({ hasMask, is3d }) ?? null;
        return (
          <CheckRow
            key={entry.key}
            label={entry.label}
            icon={entry.icon}
            title={why ?? entry.hint}
            checked={layers[entry.key]}
            disabled={why !== null}
            reason={why ?? undefined}
            onChange={() => toggleLayer(entry.key)}
          />
        );
      })}
      <p className="menu-title">Timeline</p>
      {EVENT_LAYERS.map((entry) => (
        <CheckRow
          key={entry.key}
          label={entry.label}
          icon={entry.icon}
          tone={entry.tone}
          title={entry.hint}
          checked={layers[entry.key]}
          onChange={() => toggleLayer(entry.key)}
        />
      ))}
    </Menu>
  );
}
