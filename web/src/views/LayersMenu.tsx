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
 * Two of the nine cannot always be used, and they are **shown anyway, saying
 * why**.  `SIGHT` needs a radar mask on disk to raycast against and `CALLOUTS`
 * is placed in the 3D scene, so in 2D -- the default -- the CALLOUTS row was
 * simply absent from a menu that claims to list every layer.  The old rule
 * here read "a control that cannot do anything is worse than an explanation of
 * its absence", and that is still true of an *unexplained* dead control; what
 * it got wrong is that a missing row is not an explanation of anything, it
 * reads as a feature that does not exist.  So the row stays, disabled, with
 * the reason under it.
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
import { glyphs } from "./icons";
import type { ComponentType, SVGProps } from "react";

type Glyph = ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;

interface Entry {
  key: LayerKey;
  label: string;
  icon: Glyph;
  hint: string;
  /**
   * Tints the row to match the mark it controls.
   *
   * The rail is a 24px canvas, so it cannot carry a legend of its own and a
   * tick cannot carry a `title`.  This menu already lists the four event kinds
   * with a glyph and a sentence each, so it *is* the legend -- provided the
   * colours agree with what the rail draws.
   */
  tone?: "kill" | "cast" | "ult" | "spike";
  /** Why this switch cannot be used here, or null when it can. */
  why?: (where: { hasMask: boolean; is3d: boolean }) => string | null;
}

/** What the map draws. */
const MAP_LAYERS: Entry[] = [
  {
    key: "utility",
    label: "UTILITY",
    icon: glyphs.utility,
    hint: "Ability pawns and where a placed cast came to rest",
  },
  {
    key: "trails",
    label: "TRAILS",
    icon: glyphs.trails,
    hint: "Where each player has just been, split where the record goes quiet",
  },
  {
    key: "killMarkers",
    label: "KILL MARKERS",
    icon: glyphs.killMarkers,
    hint: "Where each player died this round; off shows only the living",
  },
  {
    key: "abilityRange",
    // The word is in the label on purpose: a row reading `RANGE` claims a
    // measurement, and this is the one layer here nothing decoded.
    label: "RANGE (SIM)",
    icon: glyphs.zoom,
    hint: "A published radius for a placed ability -- looked up, not decoded",
  },
  {
    key: "sight",
    label: "SIGHT",
    icon: glyphs.sight,
    hint: "The selected player's approximate view cone",
    // The mask, and only the mask: `Scene3D` draws the wedge too, so this is
    // not a 2D-only layer.  The caption's "2D only" is about the
    // approximation being flat, not about which view you are in.
    why: ({ hasMask }) =>
      hasMask ? null : "No radar mask on disk for this map, and SIGHT raycasts one.",
  },
  {
    key: "callouts",
    label: "CALLOUTS",
    icon: glyphs.callouts,
    hint: "Riot's own callouts, to check the scene against the minimap",
    why: ({ is3d }) =>
      is3d ? null : "3D only: the callouts are placed in the scene, not on the radar.",
  },
];

/** What the timeline strip marks. */
const EVENT_LAYERS: Entry[] = [
  {
    key: "kills",
    label: "KILLS",
    icon: glyphs.kills,
    hint: "A triangle per kill",
    tone: "kill",
  },
  {
    key: "casts",
    label: "ABILITY CASTS",
    icon: glyphs.casts,
    hint: "A bare stem per inferred ability cast",
    tone: "cast",
  },
  {
    key: "ultimates",
    label: "ULTIMATES",
    icon: glyphs.ultimates,
    hint: "A diamond per characterUltimateUsed event",
    tone: "ult",
  },
  {
    key: "spike",
    label: "SPIKE",
    icon: glyphs.spike,
    hint: "A square per plant, defuse and detonation",
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
