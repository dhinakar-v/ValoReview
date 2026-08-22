# Reference UI — VALORANT replay viewer (extracted from `images/`)

Six frames of a browser-based VALORANT replay/VOD analysis tool, captured from one
session: **T1 (ATK) vs RRQ (DEF)**, map **Haven**, **Round 1**, clock running
1:35 → 1:06. Everything below is read off the pixels. Where a fact is inferred
rather than printed on screen it is marked _(inferred)_.

| File | Clock | What it shows |
|---|---|---|
| `1234_038.jpg` | 1:35 | Default state — whole-map fit, both rosters, transport bar |
| `1234_141.jpg` | 1:25 | Same view zoomed in ~2.5x, map panned under the floating panels |
| `1234_226.jpg` | — | **Round Timeline** modal open over a blurred app |
| `1234_275.jpg` | 1:08 | Marker **hover tooltip** (RRQ Kushy) at high zoom |
| `1234_285.jpg` | 1:07 | Same marker, enlarged, tooltip dismissed (hover-out / selected) |
| `1234_297.jpg` | 1:06 | **Kill feed** top-right, a dead player's card greyed out, paused |

---

## 1. Screen anatomy

A single full-bleed dark page. The map is the background layer and everything
else floats over it as rounded, bordered panels — confirmed by `141`/`275`,
where the zoomed map runs *underneath* the roster panels and out to the window
edge.

```
+--------------------------------------------------------------------------+
| <-                        (clock) 1:35              [kbd] [gear] / feed   |
|                                                                          |
| +-- T1  ATK  Y      1 -+        ( MAP STAGE )       +- 0  Y  DEF  RRQ -+ |
| | [] 100c T1 iZu   (0)100 |    grey top-down radar  | 100(0)  c100  [] | |
| | [] 50 c T1 BuZz  (0)100 |    A / B / C callouts   | 100(0)  c50   [] | |
| | [] 0  c T1 stax  (0)100 |    player markers       | 100(0)  c0    [] | |
| | [] 0  c T1 Meteor(0)100 |    orbs / spike         | 100(0)  c0    [] | |
| | [] 0  c T1 DH   (25)100 |                         | 100(0)  c0    [] | |
| +-------------------------+                         +------------------+ |
|                                                                          |
|             1 2 3 4 5 6 7 8 9 10 11 12  (swap)  13 ... 28   round strip   |
| [Ascent|Sunset|Haven]  || <<  ======------  >>  loop  list  [pen][gear]   |
+--------------------------------------------------------------------------+
```

Layout facts worth keeping:

- **Rosters flank the map, mirrored.** Left panel reads portrait → economy →
  name → abilities → weapon, left-to-right; the right panel is the exact mirror
  (weapon → abilities → name → economy → portrait). Nothing in the right panel
  is left-aligned except the score.
- **Panels are vertically centred**, not top-anchored, and do not stretch: five
  cards is the whole height.
- The **clock pill is centred over the map**, not in a bar — a floating rounded
  chip with a clock glyph.
- The **map fits by default and is free to zoom/pan** (`038` vs `141`/`275`).
  Callout letters (`A`, `B`, `C`) scale with the map rather than staying
  constant-size.

---

## 2. Team panel

### Header row

| Left panel | Right panel |
|---|---|
| `T1` · shield `ATK` red badge · funnel filter · `1` (score, right-aligned, large) | `0` (score, left-aligned, large) · funnel filter · shield `DEF` blue badge · `RRQ` |

- Side badge is a shield glyph + `ATK`/`DEF`, uppercase, tinted-background pill —
  red for attack, blue for defence.
- The funnel is a per-team filter control (filters what that team draws on the
  map — _inferred_, never shown open).
- Score is the largest number on the page outside the clock.

### Player card

Each card carries **seven** pieces of data:

1. **Portrait** — square agent art, full-bleed to the card's outer edge.
2. **Credits** — number + credits glyph, sitting *beside the name*: `100`, `50`, `0`.
3. **Name** — `T1 iZu`, `RRQ Monyet` — the team tag is part of the string.
4. **Ultimate points** — a circled number at the far end: `(0)`, `(25)` (25 on
   T1 DH and RRQ crazyguy).
5. **Health** — plain number beside the ult circle: `100`, and `79` for RRQ
   crazyguy in `275`/`285` after taking damage.
6. **Ability row** — four monochrome outline glyphs, one per equipped ability,
   in the agent's own slot order.
7. **Weapon** — a white weapon silhouette at the card's inner edge.

State variations observed:

- **No weapon** → the weapon silhouette is simply absent (T1 iZu in `275`; the
  tooltip for RRQ Kushy spells it out: *"No Weapon Equipped"*).
- **Dead** (`297`, RRQ crazyguy) → the whole card desaturates: portrait goes
  greyscale, name and ability glyphs drop to roughly 35% opacity, health reads
  `0`, the ult circle empties, and the accent underline dims.
- **Accent underline** — a full-width 2px bar under each card, red for ATK and
  blue for DEF. It is a team accent, not a health bar (it stays full width at
  79 HP).

Weapon glyphs change between frames for the same player (T1 Meteor holds a rifle
at 1:35 and a knife at 1:25; T1 DH a rifle then a pistol) — the row is **live
per-tick state**, re-read every frame, not a round-start loadout.

---

## 3. Map stage

- **Radar art is monochrome schematic**, not Riot's textured minimap: mid-grey
  playable polygons, thin white wall strokes, near-black/maroon void.
- **Site callouts** are large white letters set into the site polygon.
- **Player marker** = circular agent portrait, a 2px team-coloured ring, and a
  **view-direction pointer** — a triangular tail on the ring showing yaw.
  Markers hold a constant screen size at fit zoom and scale with the map when
  zoomed.
- **Hover/selected marker** enlarges to roughly 3x (`275`, `285`) and keeps its
  direction pointer.
- **Ultimate orbs** — white ring/donut icons at fixed map positions (two on
  Haven, matching the timeline's "started capturing ultimate orb").
- **Spike** — a solid grey dot that moves frame to frame _(inferred; it travels
  with the attacking cluster and the timeline logs "started planting")_.
- **Death markers** — in `297` the bottom cluster shows markers carrying a small
  crosshair/skull overlay where the kill landed.

### Marker tooltip (`275`)

Anchored to the right of the marker; dark card, rounded, elevated:

```
+--------------------------------+
| []  RRQ Kushy      [ Defender ]|   <- side chip, blue for DEF
|--------------------------------|
| Health:                    100 |
| Armor:                       0 |
| Money:                       0 |
|--------------------------------|
| No Weapon Equipped             |
+--------------------------------+
```

This is the authoritative key to the card numbers: **health, armor, money** are
three separate fields, and the empty-weapon case is a *sentence*, not a blank.

---

## 4. Kill feed (`297`)

Top-right, occupying the icon buttons' space: a single raised chip —

`[portrait] iZu   (weapon glyph)   crazyguy`

Killer name is tinted with the killer's team colour (red), victim in white/grey,
and the weapon used is the connector glyph rather than a text label. Names are
**short form** here (`iZu`, not `T1 iZu`), unlike the roster and the timeline.

---

## 5. Round Timeline modal (`226`)

Opened by the list button in the transport bar. The app behind it is dimmed
**and blurred**; the modal is centred, rounded, with a heavy drop shadow.

**Header:** `Round Timeline` · `< Round 1 >` stepper · `X` close.
**Legend row:** shield `T1 (ATK)` red, shield `RRQ (DEF)` blue.

### Event list (left, scrollable, custom thin scrollbar)

Row grammar: `MM:SS` · type glyph · sentence with inline coloured names and
inline ability/weapon icons. Each row has a **left accent border in the acting
team's colour**. The hovered row gets a lighter fill (`1:07 T1 iZu used High Gear`).

Every event in the frame, verbatim:

| Time | Glyph | Text |
|---|---|---|
| 1:09 | — | `T1 DH used Paranoia` |
| 1:09 | — | `T1 stax used Shock Bolt` |
| 1:09 | orb | `RRQ Kushy started capturing ultimate orb` |
| 1:09 | — | `RRQ crazyguy used Dark Cover` |
| 1:08 | — | `RRQ Monyet used Relay Bolt` |
| 1:07 | orb | `RRQ Kushy captured ultimate orb` |
| 1:07 | — | `RRQ crazyguy used Paranoia` |
| 1:07 | — | `T1 iZu used High Gear` |
| 1:06 | skull | `T1 iZu -> RRQ crazyguy` |
| 1:06 | blood | `T1 iZu -> RRQ crazyguy  FIRST BLOOD` |
| 1:04 | skull | `RRQ Monyet -> T1 iZu (assisted by RRQ Xffero)` |
| 1:03 | skull | `T1 BuZz -> RRQ Monyet (assisted by T1 DH)` |
| 1:01 | skull | `RRQ Xffero -> T1 stax (assisted by RRQ crazyguy)` |
| 1:01 | — | `T1 DH used Dark Cover` |
| 1:01 | skull | `RRQ Xffero -> T1 DH` |
| 0:58 | skull | `T1 BuZz -> RRQ Xffero` |
| 0:56 | bomb | `T1 BuZz started planting` |

Notes on the grammar:

- A kill renders as `killer -> victim` where **the arrow is the weapon icon**.
- **First blood is a second, separate row** at the same timestamp as the kill —
  duplicated deliberately, with a red-tinted row background and a `FIRST BLOOD`
  tag, so the first-kill filter can surface it in isolation.
- Assists are a parenthetical; names stay colour-coded.
- Orb capture is two events: `started capturing` then `captured`.
- Ability rows carry the ability's own icon inline before its name.

### Filter rail (right)

```
Event Types
  [x] skull   Kills
  [x] bolt    Abilities
  [x] bomb    Spike
  [x] orb     Orbs
  [x] clock   Timeouts
  [x] blood   First Kill/Death
Team Filter
  [x] shield  Attackers      <- row outlined in red
  [x] shield  Defenders      <- row outlined in blue
```

Checkboxes are blue-filled with a white check. Event-type rows carry a plain
border; the two team rows are outlined in their team colour while active.
`Timeouts` is a category this round never fires.

---

## 6. Bottom bar

### Round strip

`1 2 3 4 5 6 7 8 9 10 11 12  (swap)  13 14 ... 28`

- 12 + 12 + 4 = **28 chips** — the two regulation halves plus overtime slots.
- The circular-arrows glyph between 12 and 13 is the **halftime side swap**.
- Every chip carries a **2px underline in the winning team's colour** — red or
  blue — so the whole match's round history reads at a glance. Rounds not yet
  played show a dim/neutral underline.
- The current round is a **filled red rounded square** (`1`).

### Transport

`pause/play` · `rewind` · scrubber · `fast-forward` · `loop` · `list`

- Scrubber: thin rail, **red filled progress**, a subtle round handle at the
  playhead, spanning nearly the full width.
- Pause icon in the playing frames, play icon in `297` — the frame with the kill
  feed is paused.
- `loop` replays the round; `list` opens the Round Timeline modal.

### Corners

- **Bottom-left:** map pills `Ascent | Sunset | Haven` — the maps of the series,
  Haven active as a filled red pill. A map-of-series switcher, not a map picker.
- **Bottom-right:** four icon buttons — annotate/edit, view settings, save
  (clip/bookmark), draw. They sit in a raised, bezelled group.
- **Top-right:** keyboard-shortcuts help and settings.
- **Top-left:** back arrow to the match list.

---

## 7. Visual language

| Token | Value (sampled) | Used for |
|---|---|---|
| Page background | `#08080A` – `#0B0B0D` | everything behind the map |
| Map void | `#1A0E10` (near-black maroon) | non-playable space |
| Map floor | `#6E6E72` | playable polygons |
| Map strokes | `#D8D8DC`, hairline | walls, boxes, doors |
| Panel surface | `#111114` – `#151518` | roster cards, modal, tooltip |
| Panel border | ~`#26262B`, 1px | every enclosure |
| ATK / red | ~`#FF4655` | T1, attacker rows, progress, active pill |
| DEF / blue | ~`#3E8BFF` | RRQ, defender rows, checkboxes |
| Text primary | `#F2F2F4` | names, numbers |
| Text muted | `#8A8A93` | labels, unplayed round numbers |
| Orb accent | amber `#F0B429` | ultimate-orb events |

- There is a **soft red radial glow behind the map** at fit zoom (`038`, `297`)
  — a vignette keyed to the attacking side, not a flat background.
- Type: uppercase condensed for tags and badges (`ATK`, `DEF`, `FIRST BLOOD`),
  regular sans for names and sentences, **tabular figures** for clock, health
  and credits (they stay column-aligned across cards).
- Corner radii: ~4px on chips, ~8px on cards, ~12px on the modal.
- Icons are **monochrome line glyphs at one consistent weight**; the only colour
  in the icon set is the team tint on shields and the amber orb.

---

## 8. Feature list (what the tool does)

**Playback**
- Play/pause, step back/forward, scrub, loop.
- Round-accurate seeking via the 28-chip round strip.
- Round-win colouring on every chip, so match history is always visible.
- Half-time swap marker in the strip.
- Series-level map switching (Ascent / Sunset / Haven).

**Map**
- Top-down schematic radar with site callouts.
- Per-player markers with portrait, team ring and **view direction**.
- Free zoom and pan; markers and labels scale with the map.
- Ultimate orbs, spike and death locations drawn as first-class map objects.
- Hover a marker → tooltip with health / armor / money / weapon and a side chip.

**Rosters**
- Both teams flanking the map, mirrored, with live per-tick state: health,
  armor, credits, ultimate points, ability set, current weapon.
- Death greys the entire card.
- Per-team filter control in each header.
- Live score in each header.

**Events**
- Kill-feed chip on kills (killer, weapon glyph, victim).
- Round Timeline modal: full chronological event log for the selected round,
  round-stepper navigation, team-coloured rows.
- Event types: kills, abilities (named, with icons), spike plant, ultimate-orb
  capture (start + complete), timeouts, first kill/death.
- Assists rendered inline; first blood called out as its own tagged row.
- Filters by event type (6 toggles) and by team (2 toggles).

**Session tools**
- Annotate / draw over the map, view settings, save (clip or bookmark),
  keyboard-shortcut help.

---

## 9. Match data present in the frames

- **Teams:** T1 (attackers, red) vs RRQ (defenders, blue). Score `1 – 0`.
- **Map:** Haven (three sites A/B/C). The series also has Ascent and Sunset.
- **Round:** 1, clock 1:35 → 1:06.
- **T1 roster:** iZu, BuZz, stax, Meteor, DH.
- **RRQ roster:** Monyet, Jemkin, crazyguy, Kushy, Xffero.
- **Agents** _(inferred from portraits plus the ability names in the timeline;
  the UI never prints an agent name)_ — the two comps mirror each other: Neon
  (iZu / Monyet — *High Gear*, *Relay Bolt*), Yoru (BuZz / Jemkin — mask glyph),
  Sova (stax / Kushy — *Shock Bolt*, drone glyph), Cypher (Meteor / Xffero —
  camera and tripwire glyphs), Omen (DH / crazyguy — *Paranoia*, *Dark Cover*).
- **Economy at 1:35:** pistol round — T1 100/50/0/0/0, RRQ 100/50/0/0/0.
- **Ult points:** T1 DH 25, RRQ crazyguy 25, everyone else 0.
- **Round 1 story from the timeline:** utility trade at 1:09–1:07, iZu takes
  first blood on crazyguy at 1:06, Monyet trades iZu, BuZz trades Monyet,
  Xffero doubles onto stax and DH, BuZz answers on Xffero, and BuZz starts the
  plant at 0:56 — T1 win the round, matching the `1 – 0` score.

---

## 10. Gaps against this repository

Things the reference UI shows that a `.vrf` **cannot currently supply** here —
worth stating before any of it is treated as a spec:

- **Real player names and team tags.** `val-match-v1` is 403 without a
  production key; the replay carries no roster names.
- **Which side attacked.** `infer` two-colours the kill graph into A and B; the
  `ATK`/`DEF` badges, the red/blue assignment and the halftime swap marker all
  assume knowledge the file does not state.
- **Health, armor, credits, ultimate points.** None of these are decoded today;
  the tooltip and card numbers have no source.
- **Round-win colouring and the round strip.** Round outcomes are inferred, not
  read; the 28-chip strip presumes a full regulation + OT structure.
- **Series/map switching.** One `.vrf` is one map; a series is not a thing the
  container describes.
- **Weapon per tick and the kill-feed weapon glyph.** The killfeed arrow being a
  weapon icon needs weapon identity at kill time.
- **Ultimate orbs and spike position.** Orb capture events are not among the
  seven event groups in `docs/039f3991_summary.md` §6.

What *is* already covered: map geometry and callouts, per-player position and
view direction, ability casts inferred from spawned actors (with names for X and
C only), kill/death events with killer, victim and timestamp, and round
boundaries.
