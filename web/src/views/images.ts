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
 */
export function palette(element: HTMLElement): Record<string, string> {
  const style = getComputedStyle(element);
  const read = (name: string, fallback: string) =>
    style.getPropertyValue(name).trim() || fallback;
  return {
    a: read("--team-a", "#4d9eff"),
    b: read("--team-b", "#ff4655"),
    unknown: read("--team-unknown", "#8a90a2"),
    text: read("--text-primary", "#ece8e1"),
    muted: read("--text-muted", "#7b7b7b"),
    background: read("--app-bg", "#0d0d0d"),
    border: read("--border", "#2a2a2a"),
    ult: read("--ult", "#ffd166"),
  };
}

export function teamColour(colours: Record<string, string>, team: string): string {
  if (team === "A") return colours.a!;
  if (team === "B") return colours.b!;
  return colours.unknown!;
}
