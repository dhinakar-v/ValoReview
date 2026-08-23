"""
The art cache, resolved to file paths.  The second reader over the manifest.

There used to be a second reader over assets/manifest.json -- `valcatalog`,
which took two name lookups from it and threw the rest away.  It has been
removed, so this is the only reader now, and it takes what it always took: the
PNG
paths, the world-to-image transform and Riot's callout coordinates.  The split
is deliberate -- a name is a claim about the replay, a file path is not, and the
two are cached and reported separately.

Nothing here draws.  Path resolution and the transform arithmetic are plain
data work, so the whole of this module is tested with no art on disk and no
image library loaded -- which is what lets a handler resolve a radar's URL and
transform without opening the PNG behind them.

The joins the manifest supports
-------------------------------
    Replay.map_path              == manifest["maps"][*]["map_url"]
    Loadout.character_id.lower() == manifest["agents"][*]["uuid"].lower()

`asset_path` looks like the map join key and is not: it holds
`ShooterGame/Content/Maps/Ascent/Ascent_PrimaryAsset` where a replay states
`/Game/Maps/Ascent/Ascent`, which is why a map is addressed by display name.

Never build a path from a display name
--------------------------------------
The manifest is keyed by Riot's real display name but the folders are sanitised,
so `agents["KAY/O"]` lives in `agents/KAY_O/`.  Every path here is read out of
the entry's own `files` dict for that reason, and a file the manifest names but
that is not on disk resolves to None -- a half-fetched cache degrades to text
rather than to a broken image.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import envfile

ASSETS_DIR = Path("assets")
MANIFEST_NAME = "manifest.json"

SOURCE_MANIFEST = "valorant-api.com art cache"
SOURCE_NONE = "none"

FETCH_HINT_ENV = "VRF_FETCH_HINT"
CHECKOUT_FETCH_HINT = "runners\\fetch-assets.bat fetch writes one"


def fetch_hint() -> str:
    r"""
    What to do about a missing art cache, in the reader's own terms.

    This sentence reaches a person twice -- on `/api/config` and as the body of
    every 404 from the art mount -- so it has to name something they can
    actually do.  In a checkout that is the runner; in a packaged copy there is
    no `runners\\` directory and naming one would be a plain untruth, so
    whatever launched the app can say what it offers instead.  Read through
    `envfile` for the same reason every other setting here is: the real
    environment first, the nearest `.env` second.
    """
    return envfile.get(FETCH_HINT_ENV) or CHECKOUT_FETCH_HINT


# Keybind -> the slot name valorant-api.com publishes.  Only the two that are
# unambiguous appear; see AgentArt.ability for why Q and E cannot.
SLOT_TO_MANIFEST = {"X": "Ultimate", "C": "Grenade"}

# PNG stores width and height as big-endian uint32 at these offsets: an 8-byte
# signature, then the IHDR chunk's 4-byte length and 4-byte type, then the two.


@dataclass(frozen=True)
class Callout:
    """One named region of a map, at Riot's own world coordinates."""

    name: str
    world_x: float
    world_y: float


@dataclass(frozen=True)
class Transform:
    """
    The four scalars that turn a world coordinate into a fraction of the radar.

    Held as its own type rather than a 4-tuple so `apply` is the only place the
    axis swap is written -- see there for why that matters.
    """

    x_multiplier: float = 0.0
    y_multiplier: float = 0.0
    x_scalar_to_add: float = 0.0
    y_scalar_to_add: float = 0.0

    @property
    def usable(self) -> bool:
        return bool(self.x_multiplier or self.y_multiplier)

    def apply(self, world_x: float, world_y: float) -> tuple[float, float]:
        """
        World coordinate to a (u, v) fraction of minimap.png, both 0..1.

        The x and y inputs are swapped, and this is measured rather than
        assumed: running all 346 callouts in the manifest through the unswapped
        form lands 200 of them inside the image, and through this form 346 of
        346.  The unswapped version does not crash or look obviously broken --
        it produces a plausible wrong answer -- so it is pinned by a test.
        docs/valorant-assets.md, "The coordinate transform - measured".
        """
        u = world_y * self.x_multiplier + self.x_scalar_to_add
        v = world_x * self.y_multiplier + self.y_scalar_to_add
        return u, v


@dataclass(frozen=True)
class MapArt:
    """Every cached file and coordinate for one map."""

    name: str = ""
    codename: str = ""
    map_url: str = ""
    minimap: Path | None = None
    listview: Path | None = None
    splash: Path | None = None
    transform: Transform = field(default_factory=Transform)
    callouts: tuple[Callout, ...] = ()

    @property
    def plottable(self) -> bool:
        """Whether a map reference window has both an image and coordinates."""
        return self.minimap is not None and self.transform.usable

    def to_pixels(
        self,
        callout: Callout,
        width: int,
        height: int,
    ) -> tuple[float, float]:
        """A callout's position in pixels, for an image drawn at this size."""
        u, v = self.transform.apply(callout.world_x, callout.world_y)
        return u * width, v * height


@dataclass(frozen=True)
class AbilityArt:
    """One published ability slot: Riot's name for it, and its icon."""

    slot: str = ""
    name: str = ""
    icon: Path | None = None


@dataclass(frozen=True)
class WeaponArt:
    """
    One weapon's two cached icons.

    Nothing in a `.vrf` says which weapon anybody is holding -- the property
    payload carries it and no decoder here reads it -- so this resolves art for
    a *name*, and whoever supplies the name is responsible for saying where it
    came from.  Keeping the resolution here anyway is the same split the rest of
    this module makes: a file path is not a claim about the replay.
    """

    name: str = ""
    uuid: str = ""
    category: str = ""
    cost: int | None = None
    icon: Path | None = None
    killfeed: Path | None = None


@dataclass(frozen=True)
class AgentArt:
    """Every cached file for one agent, plus its role badge and its abilities."""

    name: str = ""
    uuid: str = ""
    role: str = ""
    icon: Path | None = None
    killfeed: Path | None = None
    portrait: Path | None = None
    role_icon: Path | None = None
    # Keyed by Riot's own slot name -- Ability1, Ability2, Grenade, Ultimate,
    # Passive -- and not by keybind, because the manifest does not publish one.
    # `ability` below is the only place that gap is reasoned about.
    abilities: dict[str, AbilityArt] = field(default_factory=dict)

    def ability(self, key: str) -> AbilityArt | None:
        """
        The published ability for a keybind read off a replay, where one joins.

        Two of the four join and two do not, and this is the whole reason the
        method exists rather than a dict lookup at the call site.
        `Ultimate` is X and `Grenade` is C on every agent, so those are exact.
        `Ability1` and `Ability2` are Q and E **in an order that varies by
        agent** (docs/valorant-assets.md), so there is no way to tell which is
        which, and returning either would be a coin flip wearing a display
        name.  Q and E therefore resolve to nothing here, and the caller shows
        the internal name it read out of the replication stream instead -- a
        fact from the file, which needs no lookup to be true.

        **This was re-examined when `abilityfacts` was written, and it stands.**
        The obvious repair is a sourced table naming each agent's Q and E, and
        two measurements say it would be a guess wearing a citation.  The
        archetype path's letters are Riot's *internal* ones and do not track
        the keybinds the game currently displays: the decode calls Sova's Recon
        Bolt `Q` where the game binds it to E, and Brimstone's Stim Beacon `E`
        where the game binds it to C.  And matching the decoded internal names
        against these display names agrees on 3 of the 40 (agent, slot) pairs
        the reference library produces -- one of which is wrong.  So
        `abilityfacts` is keyed on (agent, internal name) and carries no slot
        map, and this method goes on refusing.
        """
        slot = SLOT_TO_MANIFEST.get(key)
        return self.abilities.get(slot) if slot else None


@dataclass(frozen=True)
class ArtCache:
    """
    Resolved art for one assets/ directory, plus where it came from.

    An absent cache is the ordinary state of a clean
    checkout, so it is represented as an empty value with a readable `described`
    rather than as an exception.
    """

    root: Path = ASSETS_DIR
    source: str = SOURCE_NONE
    version: str = ""
    maps: dict[str, MapArt] = field(default_factory=dict)
    agents: dict[str, AgentArt] = field(default_factory=dict)
    # Keyed by display name, because a weapon has no other join: no replay
    # field, no UUID on the wire, nothing but the name a caller hands over.
    weapons: dict[str, WeaponArt] = field(default_factory=dict)
    reason: str = ""

    @property
    def empty(self) -> bool:
        return not self.maps and not self.agents

    @property
    def described(self) -> str:
        """
        One line naming the source, for provenance output.

        An empty cache reports `reason` verbatim, so a deliberate --no-art
        reads as a choice and a missing directory reads as an omission with the
        command that fixes it.  Telling someone to fetch art they have just
        turned off is how a provenance line loses its authority.
        """
        if self.empty:
            return self.reason or f"no art cache found; {fetch_hint()}"
        version = f" {self.version}" if self.version else ""
        return (
            f"{self.source}{version} ({self.root}): "
            f"{len(self.maps)} maps, {len(self.agents)} agents, "
            f"{len(self.weapons)} weapons"
        )

    def map_art(self, map_path: str) -> MapArt | None:
        """
        Art for a replay's internal map path.

        The primary key is `map_url`, an exact match.  The codename fallback
        covers a manifest fetched before vrfview.loader.MAP_NAMES learned that
        map: fetch_assets writes `codename: null` for those, so the leaf of the
        replay's own path is the only thing left to match on.
        """
        if not map_path:
            return None
        found = self.maps.get(map_path)
        if found is not None:
            return found
        leaf = map_path.rstrip("/").rsplit("/", 1)[-1]
        for entry in self.maps.values():
            if entry.codename and entry.codename == leaf:
                return entry
        return None

    def map_art_by_name(self, name: str) -> MapArt | None:
        """
        Art for a map named rather than identified by its internal path.

        `maps` is keyed by `map_url` because that is what a replay states and
        the only exact join there is.  A URL cannot carry one, though --
        `/Game/Maps/Infinity/Infinity` has three slashes in it, and percent
        encoding them back does not survive the server decoding the path --
        so the web interface addresses a map by the manifest's own display
        name, which is unique in it by construction and is a single segment.

        Exact, not case-folded: both sides come from the same manifest, and a
        near-match would be a different map with a plausible name.
        """
        if not name:
            return None
        for entry in self.maps.values():
            if entry.name == name:
                return entry
        return None

    def weapon_art(self, name: str) -> WeaponArt | None:
        """
        Art for a weapon named rather than identified.

        Case-folded, unlike `map_art_by_name` and `agent_art_by_name`: both of
        those join two halves of the same published catalogue, where an exact
        match is the stronger check.  A weapon name arrives from a caller
        instead, so folding is the difference between resolving `Vandal` and
        resolving nothing.
        """
        if not name:
            return None
        wanted = name.lower()
        for entry in self.weapons.values():
            if entry.name.lower() == wanted:
                return entry
        return None

    def agent_art(self, uuid: str) -> AgentArt | None:
        """Art for an agent UUID.  Both sides are lowered; the manifest varies."""
        return self.agents.get(uuid.lower()) if uuid else None

    def agent_name(self, uuid: str) -> str:
        """
        The published display name for an agent UUID, or `""`.

        The plain-chunk half of the catalogue join: a loadout slot carries a
        UUID and nothing else, and this is what turns it into the same name a
        decoded pawn's codename resolves to.  Both sides come from the one
        published catalogue, which is what makes comparing them exact.
        """
        found = self.agent_art(uuid)
        return found.name if found is not None else ""

    def agent_art_by_name(self, name: str) -> AgentArt | None:
        """
        Art for an agent named rather than identified by UUID.

        `agent_art` keys on the UUID, which is what a loadout slot carries.  A
        `Player` has no UUID -- its agent is *read* from the pawn's archetype
        codename and named through the catalogue -- so the only join left is
        the display name, and it is exact on both sides because both come from
        the same published catalogue.
        """
        if not name:
            return None
        wanted = name.lower()
        for entry in self.agents.values():
            if entry.name.lower() == wanted:
                return entry
        return None


def _resolve(root: Path, files: dict, name: str) -> Path | None:
    """One entry from a manifest `files` dict, if it is actually on disk."""
    relative = files.get(name)
    if not relative:
        return None
    path = root / str(relative)
    return path if path.is_file() else None


def _callouts(entries: list) -> tuple[Callout, ...]:
    """
    The callouts of one map, named the way Riot displays them.

    A region's full name is its super-region plus its own -- "A Tree", not
    "Tree".  Glitch and Piazza ship none at all upstream, which is Riot's data
    and not a fetch failure, so an empty tuple is a valid answer.
    """
    out = []
    for entry in entries or []:
        location = entry.get("location") or {}
        if "x" not in location or "y" not in location:
            continue
        region = str(entry.get("regionName") or "")
        super_region = str(entry.get("superRegionName") or "")
        name = f"{super_region} {region}".strip()
        if not name:
            continue
        out.append(Callout(name, float(location["x"]), float(location["y"])))
    return tuple(out)


def _map_art(root: Path, name: str, entry: dict) -> MapArt:
    files = entry.get("files") or {}
    raw = entry.get("transform") or {}
    return MapArt(
        name=name,
        codename=str(entry.get("codename") or ""),
        map_url=str(entry.get("map_url") or ""),
        minimap=_resolve(root, files, "minimap.png"),
        listview=_resolve(root, files, "listview.png"),
        splash=_resolve(root, files, "splash.png"),
        transform=Transform(
            float(raw.get("x_multiplier") or 0.0),
            float(raw.get("y_multiplier") or 0.0),
            float(raw.get("x_scalar_to_add") or 0.0),
            float(raw.get("y_scalar_to_add") or 0.0),
        ),
        callouts=_callouts(entry.get("callouts") or []),
    )


def _abilities(root: Path, entry: dict) -> dict[str, AbilityArt]:
    """
    One agent's ability slots, as fetch_assets writes them.

    The icon path comes out of the entry's own `file` key rather than being
    built from the slot or the agent name -- the same rule every other path
    here follows, and for the same reason: the folders are sanitised and
    `KAY/O` does not live in `agents/KAY/O/`.
    """
    out = {}
    for slot, raw in (entry.get("abilities") or {}).items():
        if not isinstance(raw, dict):
            continue
        out[slot] = AbilityArt(
            slot=slot,
            name=str(raw.get("display_name") or ""),
            icon=_resolve(root, {"icon": raw.get("file") or ""}, "icon"),
        )
    return out


def _weapon_art(root: Path, name: str, entry: dict) -> WeaponArt:
    files = entry.get("files") or {}
    raw_cost = entry.get("cost")
    return WeaponArt(
        name=name,
        uuid=str(entry.get("uuid") or "").lower(),
        category=str(entry.get("category") or ""),
        # None rather than 0: the melee slot is not purchasable, which is a
        # different statement from costing nothing.
        cost=int(raw_cost) if isinstance(raw_cost, int | float) else None,
        icon=_resolve(root, files, "icon.png"),
        killfeed=_resolve(root, files, "killfeed.png"),
    )


def _agent_art(root: Path, name: str, entry: dict, roles: dict) -> AgentArt:
    files = entry.get("files") or {}
    role = str(entry.get("role") or "")
    role_files = {"role": (roles.get(role) or {}).get("file") or ""}
    return AgentArt(
        name=name,
        uuid=str(entry.get("uuid") or "").lower(),
        role=role,
        icon=_resolve(root, files, "icon.png"),
        killfeed=_resolve(root, files, "killfeed.png"),
        portrait=_resolve(root, files, "portrait.png"),
        role_icon=_resolve(root, role_files, "role"),
        abilities=_abilities(root, entry),
    )


def from_manifest(doc: dict, root: Path = ASSETS_DIR) -> ArtCache:
    """Build from the manifest fetch_assets.py writes, keyed for the joins."""
    root = Path(root)
    roles = doc.get("roles") or {}
    maps = {}
    for name, entry in (doc.get("maps") or {}).items():
        art = _map_art(root, name, entry)
        if art.map_url:
            maps[art.map_url] = art
    agents = {}
    for name, entry in (doc.get("agents") or {}).items():
        art = _agent_art(root, name, entry, roles)
        if art.uuid:
            agents[art.uuid] = art
    weapons = {}
    for name, entry in (doc.get("weapons") or {}).items():
        art = _weapon_art(root, name, entry)
        if art.name:
            weapons[art.name] = art
    version = str((doc.get("version") or {}).get("version") or "")
    return ArtCache(root, SOURCE_MANIFEST, version, maps, agents, weapons)


def manifest_path(root: Path = ASSETS_DIR) -> Path:
    """The one file this module reads."""
    return Path(root) / MANIFEST_NAME


def load(root: Path | str | None = None) -> ArtCache:
    """
    Read an assets/ directory, or return an empty cache saying why not.

    This never raises, even for an explicitly named
    directory.  Missing art costs the viewer a band and a button; missing names
    would change what the interface claims.  The path tried is recorded in
    `reason` either way, so a mistyped --assets is visible in the provenance
    panel rather than silent.
    """
    root = Path(root) if root is not None else ASSETS_DIR
    path = manifest_path(root)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return ArtCache(root, reason=f"no art cache at {path}; {fetch_hint()}")
    except ValueError:
        return ArtCache(root, reason=f"{path} is not readable JSON; {fetch_hint()}")
    if not isinstance(doc, dict) or not (doc.get("maps") or doc.get("agents")):
        return ArtCache(root, reason=f"{path} names no maps or agents; {fetch_hint()}")
    return from_manifest(doc, root)


def coverage(cache: ArtCache, map_path: str, uuids: list[str]) -> list[str]:
    """
    Provenance lines for what a given replay actually resolved.

    Reported as its own list rather than appended to Replay.catalog_notes: those
    record how a *name* was arrived at, and which PNG happened to be on disk is
    a different kind of statement about a different cache.
    """
    if cache.empty:
        return [cache.described]
    lines = [cache.described]
    art = cache.map_art(map_path)
    if art is None:
        lines.append(f"map {map_path!r} is in no art entry; no map art shown")
    else:
        have = [
            n for n, p in (("minimap", art.minimap), ("listview", art.listview)) if p
        ]
        lines.append(
            f"map art for {art.name}: {', '.join(have) or 'no files on disk'}, "
            f"{len(art.callouts)} callouts",
        )
    found = sum(1 for u in uuids if (cache.agent_art(u) or AgentArt()).icon)
    lines.append(f"agent icons: {found}/{len(uuids)} loadout slots resolved to a file")
    return lines
