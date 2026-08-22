/**
 * The chrome every page sits inside, in two forms.
 *
 * The match list is a document: it wants a bar with a mark, a breadcrumb and a
 * bounded column, and it gets one.  The viewer is not a document -- it is one
 * object, a map, and every pixel of chrome around it is a pixel the map does
 * not get.  So on `/replay/:id` the frame goes **immersive**: a 40px bar with
 * a back link and the capture's name, nothing else, and the page below it fills
 * the window with no scroll and no maximum width.
 *
 * Three things that used to live in the bar are gone rather than moved:
 *
 *   * **the decoder light.**  It reported a property of the machine on every
 *     page, including the twenty-odd where nothing could be decoded.  Where it
 *     actually decides something -- the DECODE POSITIONS button in `MapStage`'s
 *     empty state -- the server's own sentence is already shown.
 *   * **the sound toggle**, and the whole `sound` module with it.  It was off
 *     by default, so removing the only control that could turn it on would have
 *     left a module nothing could reach.
 *   * **the wordmark and breadcrumb, on the viewer only.**  Two steps of
 *     breadcrumb over a back arrow is the same navigation twice.
 *
 * `Page` in `Shell.tsx` still owns the per-page title, actions and footer, and
 * the skip link still targets `<main id="main" tabIndex={-1}>` -- a link that
 * moved only the scroll would leave the focus in the bar, and the next Tab
 * would return to what it was meant to skip.
 */

import { Link, Outlet, useLocation } from "react-router-dom";

import { PRODUCT_NAME, PRODUCT_TAGLINE } from "./brand";
import { Wordmark } from "./icons";

/**
 * Where you are, in two steps at most.
 *
 * Deliberately derived from the path rather than from the loaded data: a
 * breadcrumb that waits for a fetch flickers, and one that names the map before
 * the map has been read is asserting something it has not got.
 */
function Crumbs() {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <span className="here">Library</span>
    </nav>
  );
}

export function AppFrame() {
  const { pathname } = useLocation();
  const immersive = pathname.startsWith("/replay/");

  return (
    <div className={immersive ? "app-frame is-immersive" : "app-frame"}>
      {/*
        First in the DOM and visible only when focused.  On the viewer the bar
        carries two controls and the map is the whole page, so reaching it from
        the keyboard should not cost a tour of the chrome.
      */}
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      {immersive ? null : (
        <header className="app-bar">
          <Link to="/" className="brand">
            <Wordmark />
            <span>
              <span className="brand-name">{PRODUCT_NAME}</span>
              <br />
              <span className="brand-sub">{PRODUCT_TAGLINE}</span>
            </span>
          </Link>
          <Crumbs />
          <div className="spacer" />
        </header>
      )}
      <Outlet />
    </div>
  );
}
