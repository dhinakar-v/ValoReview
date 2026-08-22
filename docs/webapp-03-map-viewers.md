# Plan 3 — the 2D minimap and the 3D scene

## Context

With Plans 1 and 2 in, the browser can fetch a replay and its decoded tracks.
This is what draws them: a 2D canvas minimap that is a faithful port of the
desktop one, and a 3D scene that shows the elevation the 2D view has always had
to throw away.

`model.Position` carries **x, y, z, yaw and pitch**. The tk minimap uses x, y
and yaw. The z has been decoded and discarded on every frame the desktop viewer
has ever drawn, and on Split or Bind that is the difference between two players
in the same place and one of them standing above the other.

**There is no map geometry in this project — no collision, no navmesh, no
height data.** The 3D scene is the radar image as a ground plane, players at
their real height, and nothing else. No walls, no floors, no extruded elevation
bands. That constraint is not a limitation to work around; it is the thing the
caption has to say.

## Order of work

The 2D view comes first and is not a stepping stone — it stays the default. It
is the readable one, it is a port of code that already works, and getting it
right settles the transform, the snapshot port and the golden fixtures that the
3D view then reuses for free.

## Part A — the model, ported to TypeScript

`state_at` is 0.127 ms on a 199k-sample replay. A round trip is not. These move
to the browser:

| Python | TypeScript |
|---|---|
| `clock.PlaybackClock`, `SPEEDS` | `model/clock.ts` |
| `model.Track.at`, `_lerp`, `_lerp_angle`, `MAX_INTERPOLATE_MS`, `MAX_HOLD_MS` | `model/track.ts` |
| `state.state_at`, `Snapshot` | `model/state.ts` |
| `art.Transform.apply` | `model/transform.ts` (already partly in `MapReference.tsx`) |
| `sight.forward_uv`, `uv_radius`, `cone`, `_march`, `blocked` | `model/sight.ts` |
| `abilities.parse` / `casts` / `spawns_from` | **not ported** — grouping stays server-side |
| `theme.blend` / `ramp` / `ramp_at` | **not ported** — they fake an alpha channel CSS has |

### The one line most likely to be wrong

`_lerp_angle` is:

```python
delta = (b - a + 180.0) % 360.0 - 180.0
return (a + delta * f) % 360.0
```

**Python's `%` takes the sign of the divisor. JavaScript's takes the sign of the
dividend.** `(-350 + 180) % 360` is `190` in Python and `-170` in JavaScript. A
naive port makes every yaw crossing 0/360 interpolate the long way round — a
facing line that spins backwards for a few frames, which reads as a rendering
glitch rather than a maths bug and will be blamed on the canvas.

Route both `%` through `const mod = (a, n) => ((a % n) + n) % n`, and give it a
golden case of its own.

### Keeping the two copies honest

`scripts/make_golden.py` builds a synthetic `Replay` and writes
`tests/golden/`:

| File | Covers |
|---|---|
| `replay.json` | the wire form of that replay |
| `positions.json` | its columnar tracks |
| `track_at.json` | every branch of `Track.at`: exact hit, a gap short enough to interpolate, a gap too long (→ `null`), a hold inside 2000 ms, a hold past it, yaw crossing 0→360 and 360→0, a negative yaw |
| `snapshots.json` | `state_at` at ~40 instants: t=0, t=length, past the end, each round boundary, the exact millisecond of a kill and ±1 ms, inside a gap, across the side swap |
| `transform.json` | the Abyss transform, callouts → uv |
| `cone.json` | a synthetic mask, origins and headings → polygons, including a negative-`u` ray and an empty result |
| `clock.json` | tick/seek/pause/speed sequences |

`tests/test_golden.py` asserts **Python** still reproduces every file byte for
byte; `web/src/model/__tests__/parity.test.ts` asserts **TypeScript** matches the
same files. So a Python change that would break the browser fails in Python CI
first, and regenerating a fixture is a deliberate act with a diff.

Assert **exact** equality, not a tolerance. Both languages are IEEE-754 doubles
and the operations are identical (`a + (b-a)*f`); Python's `json` writes
shortest-round-trip floats and `JSON.parse` recovers the same double. A
tolerance would hide precisely the class of bug this is for. Never `Math.fround`.

`tests/golden/` is committed — it is synthetic and needs no `.vrf`, unlike
`Demos/`, `out/`, `assets/` and `.cache/`.

`state.py` and `model.py` thereby acquire an honest new role: they are the
reference implementation the fixtures are generated from, even once no Python
path renders a frame.

## Part B — the 2D minimap

`<MinimapCanvas>`: one `<canvas>`, `ResizeObserver`, DPR-scaled. Direct ports of
`_place_image` (square side `min(w,h) - 2*MARGIN`, centred), `to_pixels`,
`uv_to_pixels`, and the draw order — sight wash → ability trails → ability pawns
→ dead → alive → facing.

Rules carried over verbatim, each because it fails plausibly rather than loudly:

- **Where `Track.at` returns null, draw nothing.** Never a last-known position
  dressed as current.
- **Facing lines never do trigonometry in screen space.** Build a `Position` 100
  uu ahead along the yaw, push both through `to_pixels`, subtract, renormalise.
  Screen-space trig puts every cone 90° out because the transform swaps axes and
  either multiplier may be negative — and it looks entirely plausible.
- `stipple="gray25"` becomes `globalAlpha`. The stipple existed because a Tk
  canvas has no alpha; so did `theme.blend`. Both go.
- **Sight**: the server sends the thresholded 256×256 bitmask from
  `SightMap.from_path` (`GRID` and `ALPHA_FLOOR` stay authoritative in Python,
  and the browser's downscale filter is not Pillow's, so building it client-side
  would make exact parity untestable). 65 KB per map, once. `blocked` uses
  `Math.floor`, not `| 0` — truncation toward zero wraps a ray off the left edge
  into column 0. An empty `cone()` means **draw nothing**, never a fallback
  circle. `sight.CAPTION` renders verbatim.

New endpoint: `GET /api/maps/{key}/sight` → `{size, cells (base64), open_fraction,
caption, max_range_uu, fov_degrees, ray_step_degrees, seed_cells}`. The caption
travels **with** the mask so nothing can draw a cone without having been handed
the sentence saying what it is a cone of.

## Part C — the 3D scene

`<Scene3D>` on react-three-fiber, a second view mode over the same `Snapshot`.

### Coordinates

Scene units *are* uv units, so the ground is a 1×1 quad in XZ:

```
u, v     = applyTransform(transform, x, y)   // the same swapped transform
sceneY   = (z - zRef) * transform.vertical_scale
```

`vertical_scale` is already served by `/api/maps/{key}` — it is the average
`sight.uv_radius` takes, `(|xm| + |ym|) / 2`, which converts an Unreal unit into
a fraction of the radar. Using it means elevation is at the map's own horizontal
scale: a figure derived from a measured transform, not one tuned until it looked
right. `zRef` is the minimum z over all player samples, computed once on load.

### Two traps

**Build the ground plane as an explicit `BufferGeometry`** — four vertices, four
UVs, in the XZ plane — *not* `<Plane rotation-x={-Math.PI/2}>`. The rotation
sign, `PlaneGeometry`'s bottom-left UV origin, `texture.flipY`, and the
transform's own axis swap compound into four independent ways to end up mirrored,
each of which looks fine until two maps are compared. Fifteen lines of explicit
geometry removes the whole class. Set `flipY = false`, `colorSpace = SRGBColorSpace`.

**Verify the orientation, do not assert it.** `mapref` already proves the
transform lands 346/346 callouts inside the image. Add a debug-flagged
`<Callouts>` layer that drops a labelled marker at every callout's scene
position; if the 3D scene agrees with the 2D minimap on all of them, the
orientation is right.

### Markers and trails

A short capsule in the team colour, a billboarded agent icon above it, and a thin
stem down to the plane — so a player above the ground reads as *elevated* rather
than as misplaced. Facing uses the same probe trick: `forwardUv(...)` →
`normalize(new Vector3(du, 0, dv))` → `lookAt`. No scene-space yaw arithmetic.

Trails: precompute one `Float32Array` per actor in scene coordinates on load;
per frame set `drawRange` over the window `[t - trailMs, t]` rather than
rebuilding geometry.

**Split the polyline at gaps longer than `MAX_INTERPOLATE_MS`.** `Track.at`
refuses to interpolate across a long gap precisely because it would draw a
straight line through a wall — and `minimap._draw_pawn_trail` then joins every
sample in its window regardless. That is an existing inconsistency in the
desktop viewer. Fix it in both ports and say so in the commit.

Player trails are a **new feature**, not a port — the tk minimap drew them for
ability pawns only. Toggleable layer, default off, same gap rule.

Sight stays a flat polygon on the ground plane. It is a 2D claim about a
silhouette; extruding it into a frustum would be inventing geometry.

### The caption this view needs

Same register as the sight caption, and required for the same reason: *the
ground is Riot's radar image at one flat height; heights are the players' own
replicated z at the map's horizontal scale; there is no floor, wall or ceiling
geometry anywhere in this project.* On Split a player in heaven and a player in
the tunnel beneath sit above the same pixel at different heights, and the plane
between them is a picture, not a floor.

## Part D — two things the C# decoder may have unlocked

Both are **measurements to run first**, not features to build. Each would be a
plausible wrong answer if taken on trust.

### Ability spawn coordinates

`csharp/VrfPositions` captures `spawned.Location` per actor; `csharpdecode.read`
parses it into `Decoded.spawn_locations`. **Nothing consumes it**, and CLAUDE.md
still says "the spawn transform is not decoded at all, so a smoke has a time and
no coordinate."

If those values are right, that sentence stops being true and a smoke gets a
place on the map for the first time.

The check is cheap and decisive, and uses only data already in hand: **for every
player pawn, `spawn_locations[actor]` should sit at or very near that actor's
first movement sample.** A player's first decoded position is ground truth for
where they spawned. Run it across the reference library.

- Holds → thread `spawn_locations` through `Extraction` into `AbilityCast`, add
  it to the sidecar as version 3 (v1 and v2 still readable, as they already are),
  draw non-moving abilities at their spawn point, and rewrite the CLAUDE.md
  sentence with the measurement beside it.
- Does not hold → draw nothing, and add the negative result to
  `docs/039f3991_summary.md` §8 so the next person does not re-derive it.

Until it is settled, `AbilityCast` keeps `NO_POSITION`.

### Pitch

`Position.pitch` is decoded and **has never been rendered by anything**. Nothing
in this project pins whether 350° is looking up or looking down. Rendering a
pitched view direction on an unverified sign is exactly the plausible wrong
answer this codebase refuses.

The measurement is the same family as the existing "killer and victim within
4,440 uu" check: at each `characterDeath`, the killer's pitch should point
roughly at the victim, and both z values are known. It belongs in
`tests/test_movement.py`.

**Ship yaw-only facing until that passes.** Yaw is already validated by the
cone work; pitch is not.

## Dependencies

`three`, `@react-three/fiber`, `@react-three/drei`, `zustand`. Each gets a row in
`web/README.md`'s table saying what it buys, which is the substitute this project
uses for the "only when the stdlib lacks it" rule that cannot be applied
literally on npm.

## Verification

Beyond the golden fixtures and `npm test`:

1. **The ground-truth check that catches a wrong transform**: at every
   `characterDeath`, killer and victim are within weapon range of each other on
   the minimap. `clean_packet_rate` cannot see this layer and will read 99.98%
   while every coordinate is wrong.
2. Scrub backwards across a round boundary: score, alive set and K/D identical to
   playing forward to the same instant, because `state_at` accumulates nothing.
3. Toggle 2D → 3D: the same ten players at the same uv positions, now at their
   decoded heights. On Split, heaven should read as above.
4. Sight on: cones point where players face. A 90° error means the trig went into
   uv space instead of through the probe.
5. Delete `assets/`: the map becomes a sentence, the sight layer becomes
   unavailable, and every claim the interface states is unchanged.
6. An 11.11 capture: a sentence, no drawing, in both view modes.
