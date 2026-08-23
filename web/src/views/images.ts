/**
 * Loading the pictures a canvas needs, and never blocking on them.
 *
 * Art is a picture and never a claim.  A radar that has not loaded, an agent
 * icon the manifest predates and an `assets/` directory that was never fetched
 * all cost the same thing -- a portrait becomes a dot, a map becomes a sentence
 * -- and change nothing the interface states.  So this resolves to whatever
 * arrived and re-renders; it never throws and never waits.
 */

import { useEffect, useState } from "react";

/**
 * Decoded images for a set of URLs, keyed by URL.
 *
 * A URL that fails is simply absent from the map, which is the same state as
 * one that has not arrived yet -- and both are states every caller already has
 * to draw, because a fresh checkout has no `assets/` at all.
 */
export function useImages(urls: Array<string | null | undefined>): Map<string, HTMLImageElement> {
  const key = urls.filter(Boolean).sort().join("\n");
  const [loaded, setLoaded] = useState<Map<string, HTMLImageElement>>(new Map());

  useEffect(() => {
    let live = true;
    const wanted = key ? key.split("\n") : [];
    if (wanted.length === 0) {
      setLoaded(new Map());
      return () => {
        live = false;
      };
    }
    const found = new Map<string, HTMLImageElement>();
    let outstanding = wanted.length;
    const done = () => {
      outstanding -= 1;
      if (outstanding === 0 && live) {
        setLoaded(found);
      }
    };
    for (const url of wanted) {
      const image = new Image();
      image.onload = () => {
        found.set(url, image);
        done();
      };
      image.onerror = done;
      image.src = url;
    }
    return () => {
      live = false;
    };
  }, [key]);

  return loaded;
}

/**
 * The palette, read out of the stylesheet rather than repeated here.
 *
 * `web/src/theme.generated.css` is written by `scripts/make_theme.py` from
 * `libraries/vrfview/theme.py`, and there is to be no hex value anywhere else.
 * A canvas cannot use a custom property directly, so this resolves them once
 * against a live element.
 *
 * The second argument to `read` is the only exception, and it is a hazard
 * worth naming: a fallback fires silently when a property is missing, so a
 * renamed token does not break the canvas -- it quietly draws in last
 * season's colours.  Keep these equal to the generated file.
 */
export function palette(element: HTMLElement): Record<string, string> {
  const style = getComputedStyle(element);
  const read = (name: string, fallback: string) =>
    style.getPropertyValue(name).trim() || fallback;
  return {
    a: read("--team-a", "#ff4655"),
    b: read("--team-b", "#3e8bff"),
    unknown: read("--team-unknown", "#8a90a2"),
    text: read("--text-primary", "#e8eaed"),
    muted: read("--text-muted", "#a2a9b4"),
    faint: read("--text-faint", "#6b7280"),
    background: read("--app-bg", "#0a0b0d"),
    canvas: read("--canvas-bg", "#08090b"),
    border: read("--border", "#262b34"),
    line: read("--line-strong", "#333a45"),
    panel: read("--panel", "#101216"),
    accent: read("--accent", "#7c8cff"),
    ult: read("--ult", "#ffd166"),
    spikeArmed: read("--spike-armed", "#ff9f45"),
    spikeSafe: read("--spike-safe", "#3ecf8e"),
    spikeBoom: read("--spike-boom", "#ff7043"),
    hover: read("--marker-hover", "#e935ff"),
  };
}

export function teamColour(colours: Record<string, string>, team: string): string {
  if (team === "A") return colours.a!;
  if (team === "B") return colours.b!;
  return colours.unknown!;
}

/**
 * A marker's colour, which follows the **side** rather than the team.
 *
 * `--team-a` is Valorant's attacker red and `--team-b` its defender blue, and
 * every surface in the interface derives from the same two: a roster header, a
 * card accent, a kill-feed name, a timeline row and a map marker.  Deriving
 * them from the *team* instead would be equally consistent right up to the
 * halftime swap, at which point the cards would change side and the markers
 * would not.
 *
 * Which side a team was on is the generated part -- `infer` two-colours the
 * kill graph and stops -- but the instant it changes is real, so a marker
 * changes colour at exactly the millisecond `switchTeams` fired.
 */
export function sideColour(colours: Record<string, string>, side: string): string {
  if (side === "ATK") return colours.a!;
  if (side === "DEF") return colours.b!;
  return colours.unknown!;
}
