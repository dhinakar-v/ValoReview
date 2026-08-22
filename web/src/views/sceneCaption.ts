/**
 * What the 3D scene is, in words, kept where nothing has to import `three`.
 *
 * `Scene3D` is loaded lazily -- the renderer is about a megabyte and the 2D
 * view is the default -- and the caption has to be available whether or not
 * that has happened.  Splitting it out is what stops rendering the sentence
 * from pulling in the thing it is a sentence about.
 *
 * Same register as the sight caption, and required for the same reason: the
 * view states something much weaker than it looks, and the picture cannot say
 * so itself.
 */

export const SCENE_CAPTION =
  "3D (approx) — the ground is Riot's radar image at one flat height, and " +
  "heights are the players' own replicated z at the map's horizontal scale. " +
  "There is no floor, wall or ceiling geometry anywhere in this project: on " +
  "Split a player in heaven and a player in the tunnel beneath sit above the " +
  "same pixel at different heights, and the plane between them is a picture.";
