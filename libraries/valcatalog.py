"""
Riot's content catalogue, reduced to the two joins a replay actually needs.

A .vrf states its map as an internal asset path, its agents as UUIDs and -- in
the replication stream, where vrfview.tracks reads it -- each pawn's agent as
an internal codename.  All three are opaque, and all three resolve against
Riot's published catalogue:

    /Game/Maps/Infinity/Infinity          -> Abyss
    41fb69c1-4189-7b37-f117-bcaf1e96f1bf  -> Astra
    Hunter                                -> Sova

Only the third comes with a caveat: `developerName` is a valorant-api.com
field and has no equivalent in val-content-v1, so the codename join exists in
a fetch_assets manifest and nowhere else.

docs/valorant-api.md confirmed both joins live on 2026-08-21: the map path is
exactly `ContentItemDto.assetPath` in val-content-v1, and all ten `characterId`
values in the reference capture resolve against the `characters` collection.

Cache first, network never unless asked
---------------------------------------
`load` reads a cached catalogue and returns an empty one when there is none, so
the viewer runs offline, with no API key, on a clean checkout.  `refresh` is the
only function here that opens a socket.  Two cache shapes are understood: a
val-content-v1 response saved by `refresh`, and the assets/manifest.json that
fetch_assets.py already writes from valorant-api.com -- which needs no key at
all and is very likely to be present already.

Two joins that look right and are not
-------------------------------------
The catalogue returns agent UUIDs uppercase while replays store them lowercase,
so both sides are lowered before joining; without that, nothing matches.  And in
the fetch_assets manifest the field to join on is `map_url`
(`/Game/Maps/Infinity/Infinity`), *not* `asset_path`, which holds a different
notation entirely (`ShooterGame/Content/Maps/Infinity/Infinity_PrimaryAsset`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import valapi

ASSETS_DIR = Path("assets")
MANIFEST_NAME = "manifest.json"

SOURCE_CONTENT = "val-content-v1"
SOURCE_MANIFEST = "valorant-api.com manifest"
SOURCE_NONE = "none"


@dataclass(frozen=True)
class Catalog:
    """Map asset path and agent UUID lookups, plus where they came from."""

    maps: dict[str, str] = field(default_factory=dict)
    agents: dict[str, str] = field(default_factory=dict)
    version: str = ""
    source: str = SOURCE_NONE
    path: str = ""
    codenames: dict[str, str] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        """Whether this catalogue can answer anything at all."""
        return not self.maps and not self.agents and not self.codenames

    @property
    def described(self) -> str:
        """One line naming the source, for provenance output."""
        if self.empty:
            return "no catalogue cached; names fall back to the built-in table"
        version = f" {self.version}" if self.version else ""
        where = f" ({self.path})" if self.path else ""
        return (
            f"{self.source}{version}{where}: "
            f"{len(self.maps)} maps, {len(self.agents)} agents"
        )

    def map_name(self, asset_path: str) -> str | None:
        return self.maps.get(asset_path) if asset_path else None

    def agent_name(self, uuid: str) -> str | None:
        return self.agents.get(uuid.lower()) if uuid else None

    def agent_for_codename(self, codename: str) -> str | None:
        """Public name for an internal codename: `Hunter` -> `Sova`."""
        return self.codenames.get(codename.lower()) if codename else None


def from_contents(doc: dict, path: str = "") -> Catalog:
    """
    Build from a val-content-v1 response.

    `assetPath` is populated for maps and game modes only, and even in `maps` it
    is 26 of 27 entries -- the placeholder "Null UI Data!" has none -- so the
    guard is load-bearing rather than defensive habit.
    """
    maps = {
        entry["assetPath"]: entry.get("name") or ""
        for entry in doc.get("maps") or []
        if entry.get("assetPath")
    }
    agents = {
        entry["id"].lower(): entry.get("name") or ""
        for entry in doc.get("characters") or []
        if entry.get("id")
    }
    return Catalog(maps, agents, str(doc.get("version") or ""), SOURCE_CONTENT, path)


def from_manifest(doc: dict, path: str = "") -> Catalog:
    """
    Build from the assets/manifest.json that fetch_assets.py writes.

    That manifest is keyed by display name, so both joins are inversions of it,
    and the map key is `map_url` -- see the module docstring.
    """
    maps = {
        entry["map_url"]: name
        for name, entry in (doc.get("maps") or {}).items()
        if entry.get("map_url")
    }
    agents = {
        entry["uuid"].lower(): name
        for name, entry in (doc.get("agents") or {}).items()
        if entry.get("uuid")
    }
    # A manifest written before fetch_assets recorded developer names has no
    # codenames at all, and that is the ordinary state of an existing cache:
    # the join is simply unavailable until the next refresh, and names.py
    # falls back to its built-in table and says so.
    codenames = {
        entry["developer_name"].lower(): name
        for name, entry in (doc.get("agents") or {}).items()
        if entry.get("developer_name")
    }
    version = str((doc.get("version") or {}).get("branch") or "")
    return Catalog(maps, agents, version, SOURCE_MANIFEST, path, codenames)


def from_document(doc: dict, path: str = "") -> Catalog:
    """Read either cache shape, told apart by the keys they use."""
    maps = doc.get("maps")
    if "characters" in doc or isinstance(maps, list):
        return from_contents(doc, path)
    if "agents" in doc or isinstance(maps, dict):
        return from_manifest(doc, path)
    msg = f"{path or 'document'} is neither a val-content-v1 response nor a manifest"
    raise ValueError(msg)


def cache_path(locale: str = valapi.DEFAULT_LOCALE, assets: Path = ASSETS_DIR) -> Path:
    """Where `refresh` writes, and where `load` looks first."""
    return Path(assets) / f"content-{locale}.json"


def candidates(
    path: str | Path | None = None,
    locale: str = valapi.DEFAULT_LOCALE,
    assets: Path = ASSETS_DIR,
) -> list[Path]:
    """Cache files in precedence order: explicit, refreshed, then fetch-assets."""
    if path is not None:
        return [Path(path)]
    return [cache_path(locale, assets), Path(assets) / MANIFEST_NAME]


def load(
    path: str | Path | None = None,
    locale: str = valapi.DEFAULT_LOCALE,
    assets: Path = ASSETS_DIR,
) -> Catalog:
    """
    First readable cache, or an empty catalogue.

    A missing cache is not an error -- it is the ordinary state of a clean
    checkout, and the caller falls back to the built-in codename table.  An
    explicit path that cannot be read *is* an error, because the user asked for
    that file by name.
    """
    for candidate in candidates(path, locale, assets):
        try:
            doc = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            if path is not None:
                raise
            continue
        return from_document(doc, str(candidate))
    return Catalog()


def refresh(
    shard: str = valapi.DEFAULT_SHARD,
    locale: str = valapi.DEFAULT_LOCALE,
    assets: Path = ASSETS_DIR,
    key: str | None = None,
) -> Catalog:
    """
    Fetch val-content-v1 and cache it. The only networked call in this module.

    The catalogue changes on patch boundaries and is the largest body in the
    API surface, so this is a per-patch chore, not a per-run one.
    """
    doc = valapi.contents(shard, locale, key)
    destination = cache_path(locale, assets)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Written compactly: a localised catalogue is already 1.7 MB and nothing
    # reads this file by eye.
    destination.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return from_contents(doc, str(destination))
