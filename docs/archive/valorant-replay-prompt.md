# Valorant Demo Replay System — CustomTkinter App

## Tech Stack & Environment

- **UI Framework:** CustomTkinter (latest)
- **Configuration:** All paths and secrets loaded from `.env` via `python-dotenv`
- **Demo path key in `.env`:** `DEMO_PATH=C:\Users\Dhina\AppData\Local\VALORANT\Saved\Demos\`
- **Canvas rendering:** Tkinter `Canvas` widget for the 2D minimap (inside a CTk frame)
- **Custom icons:** SVG or PNG for every interactive control — no default tkinter button faces

---

## Visual Design — Color Tokens

| Token | Hex | Usage |
|---|---|---|
| `bg-primary` | `#0D0D0D` | App background, panel fill |
| `bg-panel` | `#161616` | Player card rows, sidebar panels |
| `bg-card-hover` | `#1F1F1F` | Hovered player row |
| `accent-red` | `#FF4655` | ATK team color, round dot (active), progress bar |
| `accent-blue` | `#4D9EFF` | DEF team color, round timer dot |
| `text-primary` | `#ECE8E1` | Player names, stats |
| `text-muted` | `#7B7B7B` | Labels, secondary values |
| `border-subtle` | `#2A2A2A` | Panel separators, card borders |
| `tooltip-bg` | `#1A1A1A` | Hover tooltip background (with team-color left border) |

**Typography:**
- Headers / team names: Bold, uppercase, tight tracking — `Tungsten` or fallback `Impact`
- Body / player names: Clean sans-serif — `DIN Next` or fallback `Arial`
- Stats / numbers: Monospaced feel, right-aligned

---

## Page 1 — Home / Match List

- Paginated list of all demo files found at `DEMO_PATH` — 10 per page
- Default sort: ascending by date; toggle to switch descending
- Filter bar at the top: filter by map name or date

**Each match card shows:**
- Map thumbnail (left edge) + map name
- Match result badge: `WIN` (green) / `LOSS` (red) / `DRAW` (grey)
- Date & time formatted as `DD MMM YYYY · HH:MM`
- Match duration (`MM:SS`)
- Clicking a card opens the Replay Viewer

---

## Page 2 — Match Replay Viewer

### Overall Layout

Three-column layout with a bottom control strip:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  ←   [back arrow, top-left]          1:35 🔵 [center, round timer]   ⊞ ≡  │
├──────────────┬────────────────────────────────────┬────────────────────────┤
│  LEFT PANEL  │                                    │  RIGHT PANEL           │
│  T1 🔴 ATK ▼ │                                    │  0  ▼ 🔵 DEF  RRQ     │
│            1 │         2D MINIMAP CANVAS          │                        │
│  [5 player   │                                    │  [5 player rows,       │
│   rows,      │                                    │   mirrored layout]     │
│   ATK team]  │                                    │                        │
├──────────────┴────────────────────────────────────┴────────────────────────┤
│  [1]  2  3  4  5  6  7  8  9  10  11  12  🔄  13  14  ...  26  27  28     │
├────────────────────────────────────────────────────────────────────────────┤
│  ▶  0:04 / 0:39   [BUY PHASE]        ◀◀  ◀   ══════════════  🔊  ⛶  ⋮   │
└────────────────────────────────────────────────────────────────────────────┘
```

---

### Left & Right Player Panels

Each player row structure:

```
[Agent portrait — 60×60px, rounded top clip]
[HP value]  [💠 shield icon]  [Player name]        [ult pts]  [HP bar value]
[weapon icon]  [weapon icon]  [ability icon]  [ability icon]  [ability icon]
[horizontal team-color divider line]
```

- **ATK panel** (left): portraits anchor left, names to the right of portrait
- **DEF panel** (right): portraits anchor right, names to the left of portrait — fully mirrored
- Team score shown in top corner of each panel (`1` for ATK, `0` for DEF)
- Team tag (`T1`, `RRQ`) displayed with an ATK/DEF badge pill in red/blue

---

### Minimap Canvas

- Load the correct map image (e.g., `haven.png`, `ascent.png`) as the canvas background
- Each agent rendered as a **circular portrait icon** (~28px diameter), clipped to a circle
- A **direction indicator line** (4px, team color) extends from the agent circle showing facing direction
- **Teams color-coded:** red for ATK, blue for DEF
- Dead agents: greyscale circle + skull overlay, pinned at death coordinates
- Spike: separate icon that travels with its carrier; pulses red when planted
- Map zone labels (A, B, C) rendered as large grey uppercase text overlaid on the map

**Hover tooltip** — shown when hovering an agent dot:

```
┌──────────────────────────────────────────┐
│ [agent portrait 40px]  PlayerName  ROLE  │   ← ROLE = "Attacker" (red) / "Defender" (blue)
│ Health:   100                            │
│ Armor:    0                              │
│ Money:    💠 0                           │
│ [weapon thumbnail]  Melee                │
└──────────────────────────────────────────┘
```

- Background: `#1A1A1A`
- Left border: 3px solid, team color
- Flat card — no drop shadow
- Dismissed on mouse-leave

---

### Round Selector Strip

Horizontal strip of numbered round dots spanning the full width:

| State | Appearance |
|---|---|
| Current round | Filled red circle, white number |
| Completed round | Dim grey filled circle |
| Upcoming round | Outline only, unfilled |
| Overtime separator | 🔄 icon between regulation and OT rounds |

Clicking any dot jumps to that round's start.

---

### Playback Controls Bar

Left to right across the bottom:

| Element | Detail |
|---|---|
| ▶ / ⏸ | Play / Pause toggle, custom icon |
| `0:04 / 0:39` | Current time / total round duration |
| `BUY PHASE` | Red pill badge, shown during buy phase |
| `◀◀`  `◀` | Rewind 10s / Rewind 5s, custom icons |
| Scrub bar | Full-width seek bar; red filled portion = elapsed |
| `🔊` | Volume control |
| `⛶` | Fullscreen toggle |
| `⋮` | Options menu |

---

## Constraints

- No hardcoded paths anywhere — all from `.env`
- Graceful empty state on the home page if `DEMO_PATH` has no `.demo` files
- Use `canvas.after()` loops for smooth tick-based animation — no `time.sleep()` blocking the UI thread
- All agent, weapon, and map assets must have a fallback placeholder if the file is missing
- `requirements.txt` must list: `customtkinter`, `python-dotenv`, `Pillow`, and any demo parser dependencies
