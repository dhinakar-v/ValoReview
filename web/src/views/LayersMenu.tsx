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
 * Two of the nine are conditional and that is deliberate: `SIGHT` exists only
 * where there is a mask to raycast against and `CALLOUTS` only in the 3D scene.
 * A control that cannot do anything is worse than an explanation of its
 * absence -- and the keys in `shortcuts.ts` take the same two booleans for the
 * same reason, so `S` on a map with no mask does nothing rather than leaving a
 * layer switched on for the next replay opened in the session.
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
    hint: "Where in this round each player died",
  },
  {
    key: "sight",
    label: "SIGHT",
    icon: glyphs.sight,
    hint: "The selected player's approximate view cone",
  },
  {
    key: "callouts",
    label: "CALLOUTS",
    icon: glyphs.callouts,
    hint: "Riot's own callouts, to check the scene against the minimap",
  },
];

/** What the timeline strip marks. */
const EVENT_LAYERS: Entry[] = [
  { key: "kills", label: "KILLS", icon: glyphs.kills, hint: "A tick per kill" },
  {
    key: "casts",
    label: "ABILITY CASTS",
    icon: glyphs.casts,
    hint: "A tick per inferred ability cast",
  },
  {
    key: "ultimates",
    label: "ULTIMATES",
    icon: glyphs.ultimates,
    hint: "A tick per characterUltimateUsed event",
  },
  {
    key: "spike",
    label: "SPIKE",
    icon: glyphs.spike,
    hint: "Plant, defuse and detonation",
  },
];

export function LayersMenu({ hasMask, is3d }: { hasMask: boolean; is3d: boolean }) {
  const layers = usePlayback((state) => state.layers);
  const toggleLayer = usePlayback((state) => state.toggleLayer);

  const shown = MAP_LAYERS.filter((entry) => {
    if (entry.key === "sight") {
      return hasMask;
    }
    if (entry.key === "callouts") {
      return is3d;
    }
    return true;
  });

  return (
    <Menu label="LAYERS" icon={glyphs.layers} title="Which layers the stage draws">
      <p className="menu-title">Map</p>
      {shown.map((entry) => (
        <CheckRow
          key={entry.key}
          label={entry.label}
          icon={entry.icon}
          title={entry.hint}
          checked={layers[entry.key]}
          onChange={() => toggleLayer(entry.key)}
        />
      ))}
      <p className="menu-title">Timeline</p>
      {EVENT_LAYERS.map((entry) => (
        <CheckRow
          key={entry.key}
          label={entry.label}
          icon={entry.icon}
          title={entry.hint}
          checked={layers[entry.key]}
          onChange={() => toggleLayer(entry.key)}
        />
      ))}
    </Menu>
  );
}
