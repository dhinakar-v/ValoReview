# The `assets/` Art Cache

**Date:** 2026-08-21
**Source:** [valorant-api.com](https://valorant-api.com) `/v1`, media from `media.valorant-api.com`
**Game version at fetch:** `13.04.00.5304478`, branch `release-13.04`, built `2026-08-13T23:37:05Z`
**Code:** `scripts/fetch_assets.py`, driven by `runners\fetch-assets.bat`; tests in `tests/test_fetch_assets.py`

`assets/` is a **local cache, gitignored** (`.gitignore:225`). A clean checkout has
none of it; run the fetcher to fill it. The art is Riot Games' intellectual property —
this repo downloads it for local use and redistributes nothing.

---

## Headline

263 PNGs and a manifest, 85 MB, covering every map with a radar image, the full agent
roster and every ability icon that exists.

| Group | Entries | Files | Size |
|---|---|---|---|
| `maps/` | 18 | 54 | 50.9 MB |
| `agents/` | 29 | 205 | 33.3 MB |
| `roles/` | 4 | 4 | 0.03 MB |
| `manifest.json` | — | 1 | 157 KB |

The manifest is the part that is hard to reconstruct later. It carries each map's
world-to-image transform and its callout geometry, neither of which is recoverable from
the images alone.

Fetch it:

```
runners\fetch-assets.bat list         plan only, writes nothing
runners\fetch-assets.bat fetch        263 files into assets/
```

---

## Why valorant-api.com and not valoplant.gg

The original ask was to pull this art off valoplant.gg. That site is a Next.js app
redistributing Riot's media with no asset API: getting art out means scraping JS bundles
for CDN URLs and re-deriving names from markup, which breaks on every redeploy and yields
no metadata at all. valorant-api.com serves the **same official Riot media**,
unauthenticated, keyed by the same UUIDs Riot uses, and returns the coordinate transforms
as JSON. No API key is needed — this is unrelated to the official Riot developer API
documented in `valorant-api.md`, which needs the `RIOT_API` key in `.env`.

---

## Layout

```
assets/
  manifest.json
  maps/<PublicName>/
    minimap.png            1024x1024   top-down radar (the API's displayIcon)
    splash.png             1920x1080   loading-screen art (Breeze, Corrode, Lotus,
                                       Summit ship 3840x2160)
    listview.png            456x100    menu strip
  agents/<AgentName>/
    icon.png               1024x1024   square bust (Neon ships 512x512)
    portrait.png           2048x1860   full-body art
    killfeed.png            256x128    killfeed cutout (Breach, Jett ship 128x64)
    abilities/
      ability1.png          128x128
      ability2.png          128x128
      grenade.png           128x128    the C / signature slot
      ultimate.png          128x128
      passive.png                      only Astra and Jett have one
                                       (Veto's four are 512x512; Jett's passive 1024x1024)
  roles/
    Controller.png          128x128
    Duelist.png
    Initiator.png
    Sentinel.png
```

Folder names are sanitised by `safe_name()`: anything outside `[A-Za-z0-9-_.]` becomes an
underscore, runs collapse, edges are trimmed. In practice this only bites two names —
**`KAY/O` is stored as `agents/KAY_O/`**, and would-be `Basic Training` as
`Basic_Training`. The manifest is keyed by the *real* display name, so `manifest["agents"]["KAY/O"]`
is the lookup and the sanitised path is a value inside it. Never build a path by hand;
read it from the manifest.

`splash.png` is 49 of the 51 MB under `maps/`. `--only maps` still pulls it — there is no
minimap-only flag today.

---

## `manifest.json`

Written on every `fetch`, and **merged** rather than replaced, so a partial run
(`--only maps`) does not wipe the other groups' entries.

```jsonc
{
  "generated_utc": "2026-08-21T15:35:14Z",
  "source": "https://valorant-api.com/v1",
  "note": "official Riot art, cached locally via valorant-api.com",

  "maps":   { "<displayName>": { ... } },
  "agents": { "<displayName>": { ... } },
  "roles":  { "<displayName>": { "uuid": ..., "file": "roles/Duelist.png" } },

  "version": {            // /v1/version verbatim, so a refetch is diffable
    "manifestId": "DC06A1C774F5BCFD",
    "branch": "release-13.04",
    "version": "13.04.00.5304478",
    "engineVersion": "5.3.2.0",
    "buildDate": "2026-08-13T23:37:05Z"
  }
}
```

### A map entry

```jsonc
"Ascent": {
  "uuid": "7eaecc1b-4337-bbf6-6ab9-04b8f06b3319",
  "codename": "Ascent",                              // internal name, or null
  "map_url": "/Game/Maps/Ascent/Ascent",
  "asset_path": "ShooterGame/Content/Maps/Ascent/Ascent",
  "transform": {                                     // see below
    "x_multiplier": 7e-05,   "y_multiplier": -7e-05,
    "x_scalar_to_add": 0.813895, "y_scalar_to_add": 0.573242
  },
  "files": { "minimap.png": "maps/Ascent/minimap.png", ... },
  "callouts": [
    { "regionName": "Tree", "superRegion": "ECalloutSuperRegion::A",
      "superRegionName": "A",
      "location": { "x": 3980.9062, "y": -5938.758, "z": 400.00003 },
      "scale3D": null, "rotation": null }
  ]
}
```

`codename` is the **internal Unreal name**, recovered by inverting `MAP_NAMES` in
`libraries/vrfview/loader.py:45`. It is the join key back to a replay: a decoded `.vrf`
reports `Replay.map_path` (e.g. `.../Duality`), whose leaf is the codename, which selects
the asset folder. `null` means the viewer's table has no entry for that map — see
[Coverage](#coverage).

### An agent entry

```jsonc
"Jett": {
  "uuid": "add6443a-41bd-e414-f6ad-e58d267f4e95",
  "role": "Duelist",
  "files": { "icon.png": "agents/Jett/icon.png", ... },
  "abilities": {
    "Ability1": { "display_name": "Updraft",     "file": "agents/Jett/abilities/ability1.png" },
    "Ability2": { "display_name": "Tailwind",    "file": "..." },
    "Grenade":  { "display_name": "Cloudburst",  "file": "..." },
    "Ultimate": { "display_name": "Blade Storm", "file": "..." }
  }
}
```

A callout's full name is `superRegionName + " " + regionName` — the Ascent entry above
is "A Tree", not "Tree". `superRegion` is the raw enum; `superRegionName` is the display
half.

Slot names are Riot's, not the keybinds: `Grenade` is the C ability, `Ability1` / `Ability2`
are Q and E in some order that varies by agent. Read `display_name` rather than assuming.

---

## The coordinate transform — measured

Each map carries four scalars that convert a world coordinate to a fraction of the radar
image. **The x and y inputs are swapped**, which is the one thing that is easy to get
wrong and silently produces a plausible-looking wrong answer:

```python
u = world_y * x_multiplier + x_scalar_to_add  # 0..1 across minimap.png
v = world_x * y_multiplier + y_scalar_to_add  # 0..1 down  minimap.png
px = (u * 1024, v * 1024)  # minimap.png is 1024x1024
```

The swap is not a guess. Running all 346 callouts in the manifest through both forms:

| Form | Callouts landing inside the image |
|---|---|
| `u = x*xMul + xAdd`, `v = y*yMul + yAdd` | 200 / 346 (57.8%) |
| **`u = y*xMul + xAdd`, `v = x*yMul + yAdd`** | **346 / 346 (100.0%)** |

Cross-checked visually against `maps/Ascent/minimap.png`, whose two spike sites are the
only olive-coloured regions in the image:

| Callout | Computed px | On the image |
|---|---|---|
| A Site | (358, 146) | the upper olive square |
| B Site | (292, 755) | the lower olive square |
| Mid Courtyard | (505, 499) | dead centre |
| Attacker Side Spawn | (837, 583) | the right-hand lobe |
| Defender Side Spawn | (135, 444) | the left-hand lobe |

Reproduce it:

```
uv run python -c "import json,pathlib; m=json.loads(pathlib.Path('assets/manifest.json').read_text()); e=m['maps']['Ascent']; t=e['transform']; [print(c['regionName'], round(c['location']['y']*t['x_multiplier']+t['x_scalar_to_add'],3), round(c['location']['x']*t['y_multiplier']+t['y_scalar_to_add'],3)) for c in e['callouts']]"
```

`libraries/vrfview/art.py` is what consumes these numbers — `Transform.apply` is the only
place the formula is written, and `MapArt.to_pixels` is what the map reference window
(`vrfview/mapref.py`, the **Map** button) draws with. `TestArt.test_the_transform_swaps_x_and_y`
pins the swap against the measured `A Site` pixel above, so the plausible wrong answer
cannot come back silently.

**What they are still not used for is players.** The transform maps *Riot's* callouts, which
describe the map; the replay itself carries no position at all, because the property payloads
that would are undecoded (`vrf-decoding-findings.md`, "The premise that did not hold"). So the
2D scene stays schematic — `libraries/vrfview/layout.py` places nodes by layout, not position
— and the map reference is a separate window that is handed no `Replay` at all, which is why
it cannot accidentally plot one.

---

## Coverage

### Maps — 18 with a radar image

Maps whose `displayIcon` is null are dropped rather than written as empty folders: the two
Range variants, Basic Training and the five Skirmish placeholders. That leaves:

| Map | Codename | Callouts |
|---|---|---|
| Abyss | Infinity | 23 |
| Ascent | Ascent | 22 |
| Bind | Duality | 24 |
| Breeze | Foxtrot | 23 |
| Corrode | Rook | 21 |
| District | — | 13 |
| Drift | — | 11 |
| Fracture | Canyon | 22 |
| Glitch | — | 0 |
| Haven | Triad | 21 |
| Icebox | Port | 25 |
| Kasbah | — | 22 |
| Lotus | Jam | 28 |
| Pearl | Pitt | 26 |
| Piazza | — | 0 |
| Split | Bonsai | 24 |
| Summit | — | 24 |
| Sunset | Juliett | 17 |

The six with no codename — District, Drift, Glitch, Kasbah, Piazza, Summit — are absent
from the viewer's `MAP_NAMES`. Five are team-deathmatch arenas, which no `.vrf` in `Demos/`
uses; `Summit` is the one worth watching. The fetcher prints them on stderr on every run,
so the table going stale after a Riot release is self-announcing rather than silent.

Glitch and Piazza ship zero callouts upstream. That is Riot's data, not a fetch failure.

### Agents — 29, the full playable roster

Astra, Breach, Brimstone, Chamber, Clove, Cypher, Deadlock, Fade, Gekko, Harbor, Iso,
Jett, KAY/O, Killjoy, Miks, Neon, Omen, Phoenix, Raze, Reyna, Sage, Skye, Sova, Tejo,
Veto, Viper, Vyse, Waylay, Yoru.

Seven Controllers, seven Initiators, seven Sentinels, eight Duelists.

Ability icon coverage: `Ability1`, `Ability2`, `Grenade` and `Ultimate` are present for all
29. **`Passive` exists for only Astra and Jett** — the other 27 declare a passive with a
null icon upstream, and an ability with no icon is not art to cache, so no file is written.
Code reading `abilities["Passive"]` must tolerate its absence.

The fetcher requests `?isPlayableCharacter=true`. Against today's roster that is a no-op —
both forms return 29 — but it is the documented guard against the unreleased and duplicate
entries the endpoint has carried in the past.

---

## Refreshing after a game update

```
runners\fetch-assets.bat fetch                  # skips existing files; only new art downloads
runners\fetch-assets.bat fetch --force          # re-download everything (85 MB)
runners\fetch-assets.bat fetch --only agents    # one group; maps | agents | roles, repeatable
```

A run is resumable: existing files are skipped, so an interrupted fetch picks up where it
stopped. Diff `manifest.json`'s `version.version` against the previous value to see whether
a refresh actually changed anything. A new agent or map appears as new files plus, for a
map, a stderr note that `MAP_NAMES` needs an entry.

Other flags: `--out DIR` (default `assets`), `--jobs N` (default 4 concurrent downloads).

---

## Caveats

- **Ownership.** Riot Games owns this art. valorant-api.com is unofficial and unendorsed.
  `assets/` is gitignored precisely so none of it enters the repository.
- **No image processing.** The project is stdlib-only, so there is no Pillow and nothing
  here resizes, crops or recolours. Tk 8.6 can display these PNGs via `PhotoImage` but can
  only scale by integer factors — a viewer wanting arbitrary sizes needs a real image
  library, which would be a new dependency and a separate decision. The viewer lives within
  that: `art.subsample_for` reads each file's real IHDR and picks a whole-number factor, which
  is why a 1024×1024 icon and Neon's 512×512 one both land on a 64 px tile.
- **`portrait.png` is 2048x1860.** Twenty MB across the roster, and far larger than any
  on-screen use. Prefer `icon.png`, or `killfeed.png` for a row.
- **The manifest records what the API said at fetch time**, not what the game contains now.
  `generated_utc` and `version` are there to make that checkable.
- Callout `scale3D` and `rotation` are null for every region on every map upstream; only
  `location` is populated.

---

## Related

- `scripts/fetch_assets.py` — the fetcher; module docstring covers the design.
- `libraries/vrfview/art.py` — the consumer: manifest → file paths, and the transform.
- `libraries/vrfview/roster.py`, `mapref.py` — the two places the art is drawn.
- `libraries/vrfview/loader.py:45` — `MAP_NAMES`, the codename table this inverts.
- `docs/valorant-api.md` — the *official* Riot developer API (needs `RIOT_API` in `.env`);
  unrelated to the asset API used here, but the route to per-match player positions.
- `docs/vrf-decoding-findings.md` — why no positions exist offline yet.
- `docs/replay-viewer-20260821-2004-handoff.md:45` — the decision to keep the viewer
  schematic rather than a minimap.
