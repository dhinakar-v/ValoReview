# UI feedback

A review pass over the browser interface. Every item below comes from a screenshot in
`images/` — the file name is the note that was written against it — plus four defects
reported separately in text. This is what the interface looked like to somebody using
it, grouped by kind, with each item naming the screenshot it came from so the evidence
and the complaint stay together.

---

## 1. Broken behaviour

These four were reported in text rather than against a screenshot. They are behaviour
faults rather than appearance ones, and they come first because a wrong pixel is a
smaller problem than a control that does nothing.

**1.1 `Home` and `End` are broken.**
The two keys that should jump the playhead to the start and the end do not land where
they should. Playback is scoped to a round everywhere else in this interface — the rail
spans the round, the countdown counts the round down, the step keys walk the round's
events — so `Home` and `End` need to mean *this round's* start and end, and agree with
the transport buttons sitting beside them.

**1.2 SIGHT and CALLOUTS are broken.**
Both layers are advertised and neither delivers. In the layers menu screenshot
(`it is not layer, its is menu button…`) SIGHT is present but unchecked, and CALLOUTS
does not appear in the list at all — so a layer the interface documents is not offered
on the surface the user is looking at. Whatever the reason for a layer being
unavailable, the absence has to be explained where the switch would have been; a
missing row reads as a missing feature.

**1.3 Kill markers are broken.**
The KILL MARKERS layer is on by default and what it produces cannot be read. See also
**3.4** — the mark itself is the wrong drawing — but the reported fault is that the
layer does not do its job, not merely that it is ugly.

**1.4 The active spike location is missing.**
The interface knows the spike's *state* — planted, defused, exploded — and shows it on
the timeline, but it never shows *where*. On a plant the map should carry the spike at
its real coordinate, and once it is down that is the single most important thing on the
screen. Right now the one object the whole round is played around is invisible.

---

## 2. Product identity

**2.1 The application needs a real name.** — `application_name.png`
The header reads `REPLAY ANALYZER` over `VALORANT · LOCAL CAPTURES`. That is a
description of the category, not a name. Pick something ownable and set the wordmark,
the browser tab and the window title from it.

---

## 3. Wrong icons and wrong marks

The rule that keeps recurring: an icon has to mean the thing it sits next to. Four of
these are metaphor errors, not style preferences.

**3.1 The attack symbol is wrong.** — `attack symbol wrong.png`
`ATK` is badged with a shield. A shield is the defender's mark; the attacker's is not.
Using it for ATK inverts the game's own iconography, which every player reads instantly.

**3.2 The hide symbol is wrong.** — `hide symbol wrong.png`
The control that hides a team's markers on the map uses a filter/sort glyph — three
descending bars. It does not filter anything; it shows and hides. That is an eye and a
struck-through eye, and the icon should flip with the state so the current state is
visible without hovering for the tooltip.

**3.3 The reset icon is useless.** — `useless reset icon.png`
The glyph sitting to the right of `0:41 / 1:20` reads as neither reset nor loop and
earns no space next to the clock. Either give it a label and a shape that says what it
does, or take it off the bar.

**3.4 The death icon is bad.** — `death icon is bad.png`
Where a player died, the map draws a small cross inside a circle in the team colour. At
map scale it collapses into a fuzzy blue smudge that reads as a marker for something
alive rather than a death. It needs a distinct silhouette that cannot be mistaken for a
player, and it must stay distinguishable from the player markers at every zoom level.

**3.5 Events want their own coloured icons.** — `custom colored icons for events.png`
The event ticks on the strip are undifferentiated marks. A kill, an ability cast, an
ultimate and a spike event should each be recognisable by shape *and* colour, so the
strip can be read at a glance instead of decoded by hovering.

---

## 4. Labels and text that should not be there

**4.1 No labels on the map — icons only, plus range.**
— `no need for labels for agent or abilities. Use strictly asset icons. And range.png`
The map writes `Cypher` above the player and `Q Possessable Camera` beside the placed
camera. Both should be the asset icon alone: the agent portrait already identifies the
player, and the ability icon already identifies the ability. Text at map scale is
clutter and it collides with the map's own geometry. What the ability marker *does*
need is a range indication — the reach of the placed thing, drawn on the map rather
than spelled out in words.

**4.2 Remove the internal comment.** — `remove internal comment.png`
Rows in the round timeline read `Cypher used Possessable Camera (internal)` and
`Sova used Reveal Bolt (internal)`. `(internal)` is a note to whoever built the decoder;
it means nothing to a person watching a replay. Show the published name where there is
one and the internal name plainly where there is not, but never annotate it as internal
on screen.

**4.3 Abilities in the sidebar do not disappear when used.**
— `abilities in the sidebar is not disappearing when used. like for cypher camera.png`
Cypher's four ability icons stay fully lit on the roster card after the camera has been
placed — the screenshot shows the camera on the map and the icon still shown as
available. A used charge has to come off the card, and remaining charges have to be
visible, or the card is stating something the map contradicts.

---

## 5. Layout, spacing and placement

**5.1 The layers control is a menu button, and it belongs with the playback controls.**
— `it is not layer, its is menu button. It should be along with playback controls.png`
It is labelled `LAYERS` and sits on the stage head beside `2D` / `3D`, but what it is,
is a menu button. Move it down to the playback control row where the rest of the
viewer's controls live, so everything that changes what is being watched is in one
place.

**5.2 No gap in the dropdown.** — `no gap in dropdown.png`
There is dead vertical space between the `REPLAYS` heading and the map dropdown, and
again between the dropdown and the first card. Close it up.

**5.3 No gap in the pagination.** — `no gap in pagination.png`
The same problem at the other end of the list: the `page 1 of 3` control floats a long
way below the last card. It should sit tight under the list it pages.

**5.4 The popout tooltip should be near the avatar.**
— `popout tool tip should be near the avatar.png`
Hovering Cypher's card at the top-left of the roster pops the detail card in the
bottom-right of the stage, hundreds of pixels away, forcing the eye to cross the whole
screen and back. The popout should be anchored to whatever was hovered — beside the
avatar, on the side that keeps it on screen.

---

## 6. Styling

**6.1 A better dropdown.** — `better dropdown.png`
The map filter is an unstyled native `<select>`: it opens as a white-on-black OS list
with a system highlight and a scrollbar that belong to nothing else on the page. It
needs to be the interface's own control — same surface, same type, same spacing, and a
hover state that matches everything else.

**6.2 No need for the green highlight.** — `no need for green high light.png`
Every card in the replay list carries a green accent bar down its left edge. It
signifies nothing — every card has it — and green is not in this interface's palette, so
it fights the team colours on every thumbnail. Remove it, or make it carry an actual
distinction.

**6.3 Better-looking round tabs.** — `better looking round tabs.png`
The round strip is bare numbers 1–19 with a red or blue rule under each and one flat
blue block for the selected round. It reads as a debug control. The selected round needs
a real selected state, the win/loss colour needs to be legible at that size, and the
half-time swap marker needs to be clearer than an icon squeezed between two numbers.

---

## 7. Formatting

**7.1 A more readable date and time in the viewer header.**
— `better date time format which is more readable.png`
The viewer header shows `2026-05-28T02:27:37.075000+00:00` next to `ASCENT`. That is a
raw machine timestamp, milliseconds and UTC offset included. Show a human date and time
in the viewer's local zone.

**7.2 Better timing on the replay cards.** — `better timing.png`
Cards read `06 Jun 2026 - 02:00 · 31:08 · 21 round…` — three different quantities run
together on one line at the same weight, and the round count is cut off. Separate what
they are, label them, and make sure the line fits its column.

**7.3 The clock is counting the wrong way.**
— `clock should be ticking down, here its reverse.png`
Times in the round timeline count *up* from the round start — `0:20`, `0:23`, `0:45`,
`1:14`. A Valorant round clock counts **down**. Every time shown against a round event
should be time remaining, so it matches what a player saw when it happened.

---

## Index

| Screenshot | Item |
|---|---|
| *(reported in text)* | 1.1 `Home` / `End` broken |
| *(reported in text)* | 1.2 SIGHT and CALLOUTS broken |
| *(reported in text)* | 1.3 Kill markers broken |
| *(reported in text)* | 1.4 Active spike location missing |
| `application_name.png` | 2.1 Needs a real product name |
| `attack symbol wrong.png` | 3.1 Shield used for ATK |
| `hide symbol wrong.png` | 3.2 Filter glyph used for hide |
| `useless reset icon.png` | 3.3 Unreadable glyph beside the clock |
| `death icon is bad.png` | 3.4 Death mark unreadable at map scale |
| `custom colored icons for events.png` | 3.5 Event ticks need shape and colour |
| `no need for labels for agent or abilities. Use strictly asset icons. And range.png` | 4.1 Icons only on the map, plus range |
| `remove internal comment.png` | 4.2 Drop the `(internal)` annotation |
| `abilities in the sidebar is not disappearing when used. like for cypher camera.png` | 4.3 Used ability charges not consumed |
| `it is not layer, its is menu button. It should be along with playback controls.png` | 5.1 LAYERS is a menu button, move it |
| `no gap in dropdown.png` | 5.2 Dead space around the map filter |
| `no gap in pagination.png` | 5.3 Dead space above the pager |
| `popout tool tip should be near the avatar.png` | 5.4 Anchor the popout to the hover |
| `better dropdown.png` | 6.1 Native `<select>` needs styling |
| `no need for green high light.png` | 6.2 Meaningless green accent bar |
| `better looking round tabs.png` | 6.3 Round strip reads as a debug control |
| `better date time format which is more readable.png` | 7.1 Raw ISO timestamp in the header |
| `better timing.png` | 7.2 Card metadata run together and clipped |
| `clock should be ticking down, here its reverse.png` | 7.3 Round times count up, not down |
