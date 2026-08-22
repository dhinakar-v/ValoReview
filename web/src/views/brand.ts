/**
 * What the product is called.
 *
 * One constant, because the name reaches three surfaces and a name that is
 * three string literals is a name that ends up spelled three ways.  It was
 * `Replay Analyzer` over `Valorant - local captures`, which is a description
 * of the category rather than a name, and then `Vantage`, which was a name but
 * not this one's: nothing in it said Valorant, so a person who had the window
 * open had to already know what it read.
 *
 * `ValoReview` says both halves out loud -- the game and the act.  The
 * capital R is load-bearing: `Valoreview` reads as one unparsed word, and the
 * medial capital is what makes the seam visible at the 11px this interface is
 * full of.  It is one word, so it fits the 40px immersive bar without
 * wrapping, and it is not a Valorant item -- `Spectre` would have been the
 * better pun and the worse name, because a kill feed showing an actual Spectre
 * would then be showing the product's name as a weapon.
 *
 * Title case here and uppercased by `app.css`, which is how every other label
 * in this interface is written: the casing is a typographic decision and lives
 * with the type, not with the string.  The medial capital survives that,
 * because `text-transform: uppercase` does not change where a letter is.
 *
 * **There is a second copy, in `index.html`.** The `<title>` and the
 * description meta are static HTML read before any JavaScript runs, so they
 * cannot import this. `public/favicon.svg` duplicates `Wordmark` for the same
 * reason and says so in the same words.
 */
export const PRODUCT_NAME = "ValoReview";

/** The line under the wordmark: what it reads, not what it is called. */
export const PRODUCT_TAGLINE = "Valorant \u00b7 local captures";
