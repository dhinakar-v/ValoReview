# Where the spawn barriers are, and how that was measured

`libraries/vrfview/barriers.json` holds the round-start spawn barriers for nine
maps, 76 bars in all, as axis-aligned rectangles in radar uv. This is the
derivation. It exists because the evidence does not survive a clone:
`features/` is gitignored, so the table and this document are the whole of what
a later reader can check.

## Why this could not be read out of a replay

A barrier is level geometry. The engine raises it for the buy phase and drops
it at round start, and nothing about that reaches a spectator recording: no
actor replicates, no channel opens, and `docs/039f3991_summary.md` §6 lists all
seven event groups a `.vrf` carries with nothing among them that fires when one
appears or goes. Riot does not publish barrier coordinates either — not in
val-content-v1, not in `assets/manifest.json`, which carries a map's radar, its
world transform and its callouts and nothing else about its geometry.

So this is external knowledge, and it sits where `abilityfacts` and
`names.AGENT_CODENAMES` sit. The difference is that those two were transcribed
from published figures and this one had to be **measured**, because there are no
published figures to transcribe.

## What was measured

Nine screenshots of a third-party 2D replay viewer, one per map, each taken at
round 1 with the buy-phase barriers up: Ascent, Breeze, Fracture, Haven, Lotus,
Pearl, Split, Summit, Sunset. That viewer draws the map as a flat wireframe and
draws each barrier as a solid axis-aligned bar six pixels thick, in one of two
colours. Its palette, counted off the frames:

| what | colour | note |
|---|---|---|
| void | `(9, 15, 20)` | outside the playable area |
| floor | `(12, 41, 59)` | 331k–417k pixels a frame |
| site tint | `(13, 78, 84)` | the A/B/C squares |
| strokes | `(29, 255, 231)` | wall outlines |
| attacker barrier | `(244, 67, 54)` | Material Red 500 |
| defender barrier | `(33, 150, 243)` | Material Blue 500 |

The bars are exact flat fills, so extracting them is a colour match. Placing
them is the hard half.

## The problem: those bars are in somebody else's pixels

Nothing states the viewer's scale, its origin, or its rotation, and its
orientation is **not** the radar's — three of the nine maps are Riot's radar
turned a quarter turn and six are not turned at all. The only thing the two
pictures share is the shape of the map, so that is what the transform was
recovered from.

`barrierdecode.align` searches the eight ways a square picture can be laid down
— four rotations, each with and without a mirror — and within each, a scale and
a translation, maximising intersection-over-union between the viewer's own
floor and the **alpha silhouette of Riot's radar**, which `sight` already
establishes as the map's real extent.

The winner is not close:

| map | orientation | IoU | best of the other seven | margin |
|---|---|---|---|---|
| Ascent | r90 | 0.9693 | flip_r90 0.4911 | 1.97× |
| Breeze | none | 0.9807 | flip_r90 0.5490 | 1.79× |
| Fracture | none | 0.9640 | flip 0.5629 | 1.71× |
| Haven | r90 | 0.9738 | flip_r90 0.5199 | 1.87× |
| Lotus | none | 0.9757 | r180 0.4800 | 2.03× |
| Pearl | none | 0.9705 | flip_r270 0.4422 | 2.19× |
| Split | r90 | 0.9768 | flip_r90 0.4627 | 2.11× |
| Summit | none | 0.9698 | flip_r90 0.4379 | 2.21× |
| Sunset | none | 0.9806 | r180 0.5106 | 1.92× |

That gap is the argument that the orientation was **found** rather than
assumed, which is why `Fit` carries both numbers into the committed table
instead of throwing the runner-up away, and why
`tests/test_barriers.py::test_the_orientation_was_found_rather_than_assumed`
keeps it.

## Two things that had to be got right

**The control bar is occluded, not empty.** The viewer draws a transport bar
across the bottom of every frame and on several maps the map continues behind
it. The first pass scored that region as void and it was wrong in two ways at
once: the fit is pulled several pixels on every map, and on Pearl a stray wide
row inside the map was mistaken for the bar, half the frame was erased, and the
best placement came out at 0.48 — indistinguishable from a map that simply
would not align. The bar's own band is now carried through the search as a
*known* mask and excluded from **both** halves of the ratio, so those pixels
count for neither side.

Finding that band is itself a small trap. The bar is drawn in `(16, 25, 39)`,
but so is the background of a player's name pill up at spawn, and the bar's own
buttons are a different colour and break it into two runs. So the search is
confined to the bottom fifth of the frame and takes the topmost qualifying row
rather than the top of a contiguous run — taking the run instead reads as a bar
eighty pixels shorter than it is and scores a slab of UI as map.

**A bar is a shape, not just a colour.** The same two flat colours are also the
ring around a player's portrait at spawn and the tick marks on the scrub bar,
and both survive a colour match cleanly. They do not survive a shape test: a
barrier is 3–9 pixels on its short axis, at least 18 on its long one, and at
least 75% of its own bounding box. Across the nine frames that keeps 76 bars
and no portrait.

## Which colour is which side

Red is attack and blue is defence, and **Fracture is the proof**. It is the one
map in the set with two attacker spawns at opposite corners, and it is the only
map whose barriers are not a simple top/bottom split: the red bars sit at the
north-east and south-west spawn exits and the blue bars ring the middle around
both sites. No other assignment produces that pattern. On the other eight maps
red is consistently the spawn further from both sites, which is the attacker's.

This also agrees with the palette this project already carries — `theme.TEAM_COLOURS`
is Valorant's attacker red and defender blue — so `barriers.INK` reads the
colours off `theme` rather than restating them, and the generated PNG cannot
drift from the markers the browser draws.

The table keys on **side**, never on team. Which team is attacking swaps at
half time and the barrier does not move.

## The ground truth

The same kind of check the decoded spike plant and the ability spawns get: a
barrier closes a doorway, and a doorway is playable floor. Riot's radar states
that floor as its alpha channel, the barriers came from a completely different
picture by a completely different program, and a placement that was a few
percent out would put bars in the void — where a random coordinate on these
radars lands about a third of the time.

**76 of 76 bars land on the floor.** 73 of them are fully on it; one bar on
Fracture and one on Split score 0.95, and the worst in the set is a defender
bar on Haven at 0.90.
`tests/test_barriers.py::EveryBarrierLandsOnTheMap` is the standing check.

## What this cannot see, and what is not claimed

**Nine maps of eighteen.** Abyss, Bind, Corrode, District, Drift, Glitch,
Icebox, Kasbah and Piazza have no reference frame, so they have no row. They
are *absent*, not empty: `make-barriers` names them on every run, because "no
barriers recorded" and "this map has no barriers" are different claims and the
second one would be false.

**A bar behind the control bar is not in the table.** Fracture is the visible
case — the frame shows a bar clipped to eleven pixels at the control bar's top
edge and the shape filter drops it, which is why Fracture records two attacker
barriers where the map has more. Recording a bar whose length was set by a
piece of UI would be worse than recording nothing. The remedy is another
screenshot; `barriers.json` is hand-editable in the meantime, and a hand-added
row is checked by the same ground truth as a measured one.

**A barrier here is a rectangle, and a rectangle is what was drawn.** Every bar
in every frame is axis-aligned. If a diagonal one ever turns up, the honest
move is to widen `Barrier` to a polygon, not to fit a box round it and let the
box read as measured.

**Nothing in the app reads these files back yet.** `assets/maps/<Map>/barriers.png`
is a picture, in the sense `walls.png` is: for a person to look at, and for
whatever draws barriers next to build on. The table is the durable artefact.

## Re-running it

```
runners\make-barriers.bat --decode --overlay
```

Rebuilds the table from `features/map-barriers/`, writes
`assets/maps/<Map>/barriers.png` and a composite over the radar to check the
placement by eye. About five seconds a map. Without `--decode` it draws the
committed table and needs no screenshots. `git diff` on `barriers.json` is the
review.
