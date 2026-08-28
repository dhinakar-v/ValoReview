/**
 * The planted spike's mark, drawn rather than fetched.
 *
 * **Nobody publishes a spike.**  `assets/` holds Riot's agents, maps, roles and
 * the twenty weapons `fetch_assets` knows how to ask for; a case-insensitive
 * search of `assets/manifest.json` for `spike` or `bomb` returns nothing, and
 * the content API has no entry for one.  So the alternative to drawing it here
 * was the bare triangle this replaces -- a shape with no meaning of its own,
 * standing in for the one object a round is about.
 *
 * It is an **original mark** and not a trace of Riot's icon, for the reason
 * `THIRD_PARTY.md` exists: a traced asset is somebody else's artwork with its
 * provenance filed off, and this repository tracks the licence of four fonts
 * and a decoder rather than pretend otherwise.  What it borrows is the shape
 * language a reader already has -- an upward triangle around a hexagonal core --
 * which is a description of the object, not a copy of a drawing of it.
 *
 * Path data in a `.ts` rather than an `.svg` file, which is deliberate twice
 * over: the canvas needs a `Path2D` and cannot use a file, and an `.svg` in
 * this tree is XML where a doubled hyphen inside a comment is a *fatal* parse
 * error -- the house prose style once shipped a favicon that rendered as
 * nothing at all, which is why `tests/test_svg.py` exists.  A string has no
 * such trap.
 *
 * **The mark must stay filled and must stay the size it was.**
 * `e2e/minimap.spec.ts` finds the plant by counting `--spike-armed` pixels
 * within 26 px of the coordinate the model gives, and requires both more than
 * twenty of them and that they are the largest connected amber patch on the
 * canvas -- the map's own warm noise runs to a 14-pixel run.  So the body is
 * one closed filled subpath and the core is painted in the *canvas* colour
 * over it rather than cut out of it, which keeps every amber pixel in one
 * region and keeps the count close to the solid triangle's.
 */

/** The glyph's own box: everything below is in a 24x24 square around (12, 12). */
const BOX = 24;
const HALF_BOX = BOX / 2;

/**
 * The outer body: an upward triangle with its corners taken off.
 *
 * The clipped corners are what stop it reading as the plain triangle it
 * replaces at the sizes this is actually drawn at, and they are the object's
 * own silhouette rather than decoration.
 */
const BODY =
  "M12 1 L16.5 5 L22 15 L20 22 L4 22 L2 15 L7.5 5 Z";

/** The hexagonal core, painted in the canvas colour so the amber stays whole. */
const CORE = "M12 7.5 L16 10 L16 15 L12 17.5 L8 15 L8 10 Z";

/** The lit centre, back in the mark's own colour: a spike is armed or it is not. */
const PIP = "M12 10.5 L14 11.75 L14 14.25 L12 15.5 L10 14.25 L10 11.75 Z";

function scaled(d: string, x: number, y: number, half: number): Path2D {
  const path = new Path2D();
  const unit = half / HALF_BOX;
  // `DOMMatrix` rather than hand-multiplied coordinates, so the three subpaths
  // above stay readable as the drawing they are. Both it and `Path2D` are
  // browser-only; jsdom never reaches this code, because it gives the canvas no
  // 2D context and every caller is behind that.
  path.addPath(
    new Path2D(d),
    new DOMMatrix().translate(x - half, y - half).scale(unit, unit),
  );
  return path;
}

/** The filled body, centred on `(x, y)` at the given half-height. */
export function spikeBody(x: number, y: number, half: number): Path2D {
  return scaled(BODY, x, y, half);
}

/** The core, to be painted over the body in the canvas colour. */
export function spikeCore(x: number, y: number, half: number): Path2D {
  return scaled(CORE, x, y, half);
}

/** The lit centre, back in the mark's own colour. */
export function spikePip(x: number, y: number, half: number): Path2D {
  return scaled(PIP, x, y, half);
}
