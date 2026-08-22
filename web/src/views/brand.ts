/**
 * What the product is called.
 *
 * One constant, because the name reaches three surfaces and a name that is
 * three string literals is a name that ends up spelled three ways.  It was
 * `Replay Analyzer` over `Valorant · local captures`, which is a description
 * of the category rather than a name: it says what kind of thing this is and
 * gives a person nothing to call it.
 *
 * `Vantage` is the point you watch a round from, and an analyst's word.  It is
 * one word, so it fits the 40px bar without wrapping, and it is not a Valorant
 * item -- `Spectre` would have been the better pun and the worse name, because
 * a kill feed showing an actual Spectre would then be showing the product's
 * name as a weapon.
 *
 * Title case here and uppercased by `app.css`, which is how every other label
 * in this interface is written: the casing is a typographic decision and lives
 * with the type, not with the string.
 *
 * **There is a second copy, in `index.html`.** The `<title>` and the
 * description meta are static HTML read before any JavaScript runs, so they
 * cannot import this. `public/favicon.svg` duplicates `Wordmark` for the same
 * reason and says so in the same words.
 */
export const PRODUCT_NAME = "Vantage";

/** The line under the wordmark: what it reads, not what it is called. */
export const PRODUCT_TAGLINE = "Valorant \u00b7 local captures";
