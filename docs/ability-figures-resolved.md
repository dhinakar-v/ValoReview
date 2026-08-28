# Figures asked for, and what came back

28 August 2026 · **resolved and applied**

This began as a queue of every number the ability layer needed and did not have, sent out rather
than guessed at. It is kept because the answers are the provenance for what is now in
`libraries/vrfview/abilityfacts.py`, and because three of them corrected a premise rather than a
figure -- which is the part a table of numbers cannot record.

**What was written into the table:** Clove's Ruse 4.0 m, Sova's Shock Bolt 4.0 m outer, Breach's
Aftershock 3.0 m from Riot's own patch note, Veto's Crosscut 24 m as a teleport *reach* rather than
an area, and all six of the Miks and Veto slot names. **What was struck:** Sage's Slow Orb, whose
radius nobody publishes and whose community figures predate a 30% resize. **What was retired
entirely:** the facing-derived wall -- see section B, which killed the code as well as the figure.
Everything still marked *not confirmed* below draws no ring, which is the current behaviour and is
visibly absent rather than quietly wrong.

`libraries/vrfview/abilityfacts.py` is a hand-written table of published ability figures, and the
rule it keeps is that a figure enters it only with a source. This document is the queue: every
number the ability layer needs and does not have, with what I would write and where I would say it
came from. **Nothing here is in the table yet.** Confirm, correct or strike each line and the
confirmed ones get written, each as a `Figure(value, source)` whose source string carries the
citation and, where the figure is community-measured rather than published by Riot, says so in the
same sentence.

The cast counts are from the 23 decoded captures in `.cache/positions/`, so they are how often the
mark is actually on screen in this library. "Places something" means the cast spawns a
`GameObject`, `Zone` or `Patch` — the kinds that get a mark on the radar.

Confidence column:

- **published** — a figure in `docs/Valorant Agent Ability Details.md` or on the page it cites.
- **community** — widely quoted on the wiki/Liquipedia but not reachable from this machine
  (`valorant.fandom.com` answers 402 here and `liquipedia.net` answers 403), so I am writing it
  from memory and it needs your eye.
- **none** — I have no figure at all. Either supply one or the ability keeps drawing no ring,
  which is the current behaviour and is visibly absent rather than quietly wrong.

---

## Resolution pass — 28 August 2026

The `yours` columns below are filled from `wiki.playvalorant.com` (the Weird Gloop VALORANT wiki),
which **is** reachable even though `valorant.fandom.com` and `liquipedia.net` are not. It is the
better source regardless: every row of its stats tables is tagged with how the value was
established — *Game files*, a specific patch note, or *estimated and manually tested*. Figures
carrying a game-files or patch-note tag can go in as **published**.

Where that wiki has no figure, I have written *not confirmed* rather than guessing. Its stats
tables are otherwise thorough, so a missing radius is decent evidence that no reliable public
figure exists, not that I failed to find it. Those abilities should stay ringless on the current
`none` behaviour.

Three results change more than a number:

- **Aftershock is a cylinder, not a sphere**, and its radius is 3 m — not 5 m.
- **Blaze and High Tide have no fixed length.** Section B's premise does not hold for either.
- **Shear is not drawn along the caster's facing.** It is placed on vertical terrain.

---

## A. Area of effect — `radius_uu`

The unit is the Unreal unit; a metre is 100 uu on Riot's own arithmetic (the Sky Smoke patch note).
Write metres in the "yours" column and I will convert.

| Ability | casts | proposed | confidence | note | yours |
|---|---:|---:|---|---|---|
| Clove — Ruse | 365 | 4.1 m | community | the biggest gap in the library. Same figure as Omen's Dark Cover, which is a resemblance and not a source — this is the one I would most like corrected. Once it lands, `smoke_for` starts answering and the SIGHT layer occludes on it with no further change | **4.0 m — published.** wiki.playvalorant.com/en-us/Ruse, Radius row, tagged *Game files*. Write it as published and drop the Dark Cover reasoning from the source string entirely — Ruse now stands on its own citation |
| Sova — Shock Bolt | 156 | 5.0 m | community | outer splash; damage scales 75 → 1 from the centre | **1.5 m inner / 4.0 m outer — published.** …/Shock_Bolt, Radii row, *Game files*. The 5.0 m is too big. The 75 → 1 falloff is confirmed separately (max 75 from patch v4.08, min 1 estimated) |
| Sage — Slow Orb | 64 | 4.5 m | community | the slow field, not the throw | **Strike.** The stats table carries equip, unequip, windup, slow amount and duration — and no radius. Note also that v1.07 reduced the zone size by 30%, so any community figure predating that is stale by an unknown factor. Leave ringless |
| Breach — Aftershock | 56 | 5.0 m | community | one radius for all three pulses | **3.0 m, and it is a cylinder ~10 m long, not a sphere.** Riot patch note v3.0: "Explosion radius increased 260 >>> 300" = 300 uu = 3 m, so this is *published*, from Riot. The wiki describes a cylindrical AoE projected in front of the wall; Mobalytics gives 10 m length / 3 m radius. Also **two** pulses, not three — v7.04 cut ticks 3 → 2 and raised damage 60 → 80. A 3 m ring at the detonation point is defensible; a 10 × 3 m capsule along the caster's facing would be truer |
| Astra — Gravity Well | 1 | 5.25 m | community | | Not confirmed. No figure on the wiki |
| Astra — Nova Pulse | 1 | 5.25 m | community | | Not confirmed. The page says only that it concusses agents within its radius, without giving one |
| Brimstone — Orbital Strike | 2 | 5.0 m | community | | Not confirmed |
| Brimstone — Stim Beacon | 7 | 8.0 m | community | the buff field | Not confirmed. The wiki notes enemies cannot see the field's radius at all, which is probably why no measured figure circulates |
| Raze — Blast Pack | 88 | 6.5 m | community | damage/displacement radius | Not confirmed. The inner/outer falloff structure is confirmed; no numbers are published |
| Fade — Seize | 34 | 4.5 m | community | the tether pool | Not confirmed |
| Fade — Haunt | 76 | — | none | the watcher reveals by line of sight, not by radius. I would leave this ringless | Agreed. Nothing found to contradict it |
| Killjoy — Lockdown | 8 | 12.0 m | community | the detain radius; the wiki calls it "large" and I am not sure of the number | Not confirmed — your doubt was well placed. Worth carrying forward when a figure does arrive: the AoE is a **sphere centred on the planted device**, extending above and below ground, so a flat ring overstates coverage wherever the terrain slopes or drops |
| Skye — Regrowth | 27 | — | none | heals by line of sight, not radius | Agreed |
| Reyna — Leer | 260 | — | none | a directional eye; a circle would be wrong | Agreed |
| Cypher — Trapwire | 55 | — | none | a line up to 15 m between two points, and only one point is decoded | Agreed |
| Omen — Paranoia | 61 | — | none | a wall-piercing projectile, not an area | Agreed |
| Sova — Recon Bolt | 246 | — | keeps its 30 m as **detection**, not as an effect. The ring is being made legible instead — a faint fill and a stronger dash — so the scan reads as an area | | Agreed |

Abilities that place something, have no radius, and I believe genuinely have no area to draw:
Chamber's Rendezvous (its 18 m is a teleport reach, already carried as `detection_radius_uu`),
Reyna's Devour, Phoenix's Run it Back, Cypher's Spycam and Neural Theft, Breach's Rolling Thunder,
Fade's Nightfall, Astra's Cosmic Divide, Skye's Guiding Light. Say if you disagree with any.

> **Addition to that list.** Veto's Crosscut has a **24 m teleport radius** — structurally the same
> thing as Chamber's Rendezvous 18 m. It wants a `detection_radius_uu` entry rather than nothing.

## B. Wall length — `wall_length_uu`

Sage's Barrier Orb needs **no figure**: it spawns four segment actors at real decoded coordinates
and the wall is measured from them (125 of 126 barriers, exactly collinear, 1,040 uu end to end).
These three place one point and no orientation, so they are drawn along the caster's decoded facing
at cast time and need a published length.

> **This premise does not hold for Blaze or High Tide.** Neither is a fixed-length wall. Both cast a
> steerable missile that leaves a path on the ground beneath it; the wall then rises from the
> *caster's* location and spreads along that path until it reaches the end, and terminates early on
> geometry. So the length varies per cast, and the shape is a polyline, not a segment. There is no
> single published figure to write because there is no single length.

| Ability | casts | proposed | confidence | yours |
|---|---:|---:|---|---|
| Phoenix — Blaze | 104 | 10.0 m | community | No single length exists — see above. One (weak) source puts the range at 5–24 m depending on cast and obstruction; I would not write that figure. If a ring is drawn at all, draw the maximum and have the layer hint say the real wall is usually shorter |
| Harbor — High Tide | 13 | 15.0 m | community | it is steerable, so a straight line is an approximation even with the right length | Same mechanic as Blaze — the note understates it. The *length* is variable too, not just the shape |
| Vyse — Shear | 35 | 8.0 m | community | | Length not confirmed. Separately, check the placement model: Shear is placed on **vertical terrain** and only accepts a wall perpendicular to the ground, so drawing it along Vyse's decoded facing is wrong whenever she placed it at an angle to her body |

## C. Which published ability sits in which internal slot

The archetype path states an internal letter that is not the keybind, so each slot has to be named
by matching the decode's own internal name against Riot's published names for that agent. Most are
unambiguous and I will write them without asking — Waylay's `C Time Slow Grenade` is Saturate,
Iso's `Fragile Missile` is Undercut, KAY/O's `Semtex Basic` is FRAG/ment, and so on. **Two agents I
cannot call**, and a wrong name here puts the wrong icon on the map, which is exactly the bug this
work is fixing:

**Both are resolved. All six slots can be written.**

| Agent | internal slot | internal name | published names available | yours |
|---|---|---|---|---|
| Miks | C | `Thumper Heal`, `Thumper Concuss` | M-pulse, Waveform, Harmonize | **M-pulse.** Alt-fire toggles between Concuss and Healing outputs before the device is thrown — your two internal names are the two modes of one ability |
| Miks | E | `Smoke` (187 casts) | M-pulse, Waveform, Harmonize | **Waveform.** An instant-deploy smoke placed through a map targeter. Consistent with the 187 casts |
| Miks | Q | — | M-pulse, Waveform, Harmonize | **Harmonize.** A shared Combat Stim on Miks and a targeted ally, refreshing on kills. Nothing is spawned, which is why the slot has no internal placed-object name |
| Veto | C | `Usable Teleport` | Chokehold, Interceptor, Crosscut | **Crosscut.** C equips a vortex, fire places it on the ground, and looking at it from within range teleports you there |
| Veto | Q | `Trap Grenade` | Chokehold, Interceptor, Crosscut | **Chokehold.** Equip a fragment, fire to throw, deploys on impact into a trap that holds, deafens and decays |
| Veto | E | `Rad Eater` | Chokehold, Interceptor, Crosscut | **Interceptor.** His signature — free, 40 s recharge — and it destroys utility that would bounce off a player or be destroyed by gunfire. "Rad Eater" reads as the radivore consuming utility |

(Miks' `X` is `Sonic Wave` → Bassquake and Veto's `X` is Evolution; both are certain and will be
written.) Until a slot is named it carries no icon, and the marker is drawn with nothing inside it
rather than with a letter. — **Both confirmed.**

## D. A drone's field of view

`sight.FOV_DEGREES` is 103, which is a player's. Sova's Owl Drone and Tejo's Stealth Drone are
getting the same view cone a living player gets — their position and yaw are decoded and real — but
a drone camera is not a player's eye.

| Figure | proposed | confidence | yours |
|---|---:|---|---|
| Owl Drone FOV | 103° (the player figure) | none | No published drone-specific figure exists. Every FOV source concerns the player camera, locked at 103°. Keep the fallback |
| Stealth Drone FOV | 103° (the player figure) | none | Same. No figure |

If neither is confirmed the cone is drawn at the player FOV and the layer's own hint says so.
— **Neither is confirmed. The hint stays.**

---

## Summary of what changed

| | |
|---|---|
| Corrected downward | Ruse 4.1 → **4.0 m**; Shock Bolt 5.0 → **4.0 m outer / 1.5 m inner** |
| Corrected and reshaped | Aftershock 5.0 m sphere → **3.0 m radius, ~10 m cylinder**, two pulses not three |
| Struck | Slow Orb — no published radius, and pre-v1.07 figures are stale |
| Resolved in full | Section C — all six Miks and Veto slots |
| Premise challenged | Section B — Blaze and High Tide have no fixed length; Shear is not drawn along caster facing |
| Still unconfirmed | Gravity Well, Nova Pulse, Orbital Strike, Stim Beacon, Blast Pack, Seize, Lockdown; both drone FOVs |
| New | Veto Crosscut 24 m teleport reach → `detection_radius_uu` |
