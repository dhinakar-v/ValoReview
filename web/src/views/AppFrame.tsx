/**
 * The chrome every page sits inside.
 *
 * Each of the three pages used to render its own `Page` and nothing else, so
 * there was no persistent anything -- no mark, no indication of where you were,
 * and no home for a control that belongs to the application rather than to a
 * replay.  This is that bar.
 *
 * Two things live in it, and both are application-wide facts rather than
 * replay-wide ones:
 *
 *   * **the decoder light**, from `api.config`.  Whether a decode is even
 *     possible is a property of the machine, and discovering it one click into
 *     a capture is the confusing state the match list footer already tries to
 *     head off.  The light says it everywhere, and its `title` carries the
 *     server's own sentence rather than a paraphrase.
 *   * **the sound toggle**, which is off until somebody asks.
 *
 * `Page` in `Shell.tsx` is unchanged and still owns the per-page title, actions
 * and footer.  That matters: the page tests render `MatchListPage` and
 * `MapStage` directly, outside the router, so anything this frame adds must be
 * something those pages do not depend on.
 */

import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useLocation } from "react-router-dom";

import { api } from "../api/client";
import { Wordmark, glyphs } from "./icons";
import { play, useSound } from "./sound";
import { IconButton } from "./ui";

/**
 * Where you are, in two steps at most.
 *
 * Deliberately derived from the path rather than from the loaded data: a
 * breadcrumb that waits for a fetch flickers, and a breadcrumb that names the
 * map before the map has been read is asserting something it has not got.
 */
function Crumbs() {
  const { pathname } = useLocation();
  if (pathname.startsWith("/replay/")) {
    return (
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Replays</Link>
        <span className="sep">/</span>
        <span className="here">Viewer</span>
      </nav>
    );
  }
  if (pathname.startsWith("/map/")) {
    return (
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Replays</Link>
        <span className="sep">/</span>
        <span className="here">Map reference</span>
      </nav>
    );
  }
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <span className="here">Library</span>
    </nav>
  );
}

/**
 * The decoder light.
 *
 * Three states and not two: not yet asked is grey, which is a different thing
 * from a decoder that is missing, and colouring it green or red before the
 * answer arrives would be a guess.
 */
function DecoderLight() {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const decoder = config.data?.decoder;
  const tone = decoder === undefined ? "" : decoder.found ? "ok" : "bad";
  const said = decoder?.described ?? decoder?.hint ?? "checking for a decoder…";
  return (
    <span className="status" title={said}>
      <i className={tone ? `dot ${tone}` : "dot"} />
      Decoder
    </span>
  );
}

function SoundToggle() {
  const enabled = useSound((state) => state.enabled);
  const toggle = useSound((state) => state.toggle);
  return (
    <IconButton
      label={enabled ? "Sound on" : "Sound off"}
      icon={enabled ? glyphs.soundOn : glyphs.soundOff}
      pressed={enabled}
      silent
      onClick={() => {
        toggle();
        // After, not before. Turning sound *on* has to be audible or the
        // control gives no evidence it did anything, and `play` is a no-op
        // while the store still says off.
        play(useSound.getState().enabled ? "toggleOn" : "toggleOff");
      }}
    />
  );
}

export function AppFrame() {
  return (
    <div className="app-frame">
      {/*
        First in the DOM and visible only when focused.  The bar carries a
        brand link, a breadcrumb, the decoder light and the sound toggle, and
        on the viewer the page head adds three more -- so reaching the map from
        the keyboard was seven presses on every navigation.
      */}
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="app-bar">
        <Link to="/" className="brand">
          <Wordmark />
          <span>
            <span className="brand-name">Replay Analyzer</span>
            <br />
            <span className="brand-sub">Valorant &middot; local captures</span>
          </span>
        </Link>
        <Crumbs />
        <div className="spacer" />
        <div className="bar-right">
          <DecoderLight />
          <SoundToggle />
        </div>
      </header>
      <Outlet />
    </div>
  );
}
