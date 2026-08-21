"""
Download Valorant map, agent and ability art into a local assets/ cache.

Why not valoplant.gg
--------------------
The art on valoplant.gg is Riot's, redistributed by a Next.js app that exposes
no asset API.  Pulling from it means scraping JS bundles for CDN URLs and
re-deriving names from markup, which breaks on every redeploy and yields no
metadata.  valorant-api.com serves the same official media from
media.valorant-api.com, unauthenticated, keyed by the same UUIDs Riot uses, and
hands back the map coordinate transforms as well.

Those transforms are why a manifest is written rather than just files.  Each map
carries xMultiplier / yMultiplier / xScalarToAdd / yScalarToAdd, the only
published route from a world coordinate to a pixel on the radar image:
`fraction = x * xMultiplier + xScalarToAdd`, in [0, 1] of the image.  Nothing in
this repo decodes positions today -- the viewer is deliberately schematic -- but
the numbers cost nothing to keep and cannot be reconstructed later.

Usage
-----
  python fetch_assets.py list                 what would be fetched, no writes
  python fetch_assets.py fetch                everything, into assets/
  python fetch_assets.py fetch --only maps    just the maps

Files that already exist are skipped, so an interrupted run resumes; --force
overwrites.  The art is Riot Games' intellectual property; this is a local
cache, not a redistribution.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from vrfview.loader import MAP_NAMES

API = "https://valorant-api.com/v1"
USER_AGENT = "val-replay-analyzer/0.1 (local asset cache)"
TIMEOUT_S = 30
RETRIES = 3
BACKOFF_S = 1.5

COMMANDS = ("list", "fetch")
GROUPS = ("maps", "agents", "roles")

# (JSON field on the API object, file name written inside the entry's folder).
MAP_FILES = (
    ("displayIcon", "minimap.png"),
    ("splash", "splash.png"),
    ("listViewIcon", "listview.png"),
)
AGENT_FILES = (
    ("displayIcon", "icon.png"),
    ("fullPortrait", "portrait.png"),
    ("killfeedPortrait", "killfeed.png"),
)

# Public map name -> internal codename: the inverse of the viewer's table, so a
# decoded replay's map_path leaf resolves straight to an asset folder.
CODENAMES = {public: internal for internal, public in MAP_NAMES.items()}


@dataclass(frozen=True)
class Download:
    """One remote file and where it lands, relative to the output directory."""

    url: str
    path: str


# --- naming and planning ---------------------------------------------------
# Nothing in this section touches the network: the plan_* functions take decoded
# JSON and return what to fetch, which is what makes them testable offline.


def safe_name(name: str) -> str:
    """A folder name that survives every filesystem; KAY/O becomes KAY_O."""
    out = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in name.strip())
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "unnamed"


def _files_for(
    entry: dict,
    fields: tuple[tuple[str, str], ...],
    folder: str,
) -> list[Download]:
    """Pair each populated image field with its destination inside `folder`."""
    return [
        Download(entry[field], f"{folder}/{filename}")
        for field, filename in fields
        if entry.get(field)
    ]


def _by_filename(files: list[Download]) -> dict:
    return {d.path.rsplit("/", 1)[-1]: d.path for d in files}


def plan_maps(maps: list[dict]) -> tuple[list[Download], dict, list[str]]:
    """
    Downloads, manifest fragment and warnings for the maps endpoint.

    Maps with a null displayIcon have no radar image at all -- the Range, Basic
    Training and the Skirmish placeholders -- and are dropped rather than
    written out as empty folders.
    """
    downloads: list[Download] = []
    manifest: dict = {}
    unknown: list[str] = []

    for entry in sorted(maps, key=lambda m: m.get("displayName") or ""):
        name = entry.get("displayName") or ""
        if not name or not entry.get("displayIcon"):
            continue
        folder = f"maps/{safe_name(name)}"
        files = _files_for(entry, MAP_FILES, folder)
        downloads.extend(files)
        if name not in CODENAMES:
            unknown.append(name)
        manifest[name] = {
            "uuid": entry.get("uuid"),
            "codename": CODENAMES.get(name),
            "map_url": entry.get("mapUrl"),
            "asset_path": entry.get("assetPath"),
            "transform": {
                "x_multiplier": entry.get("xMultiplier"),
                "y_multiplier": entry.get("yMultiplier"),
                "x_scalar_to_add": entry.get("xScalarToAdd"),
                "y_scalar_to_add": entry.get("yScalarToAdd"),
            },
            "files": _by_filename(files),
            "callouts": entry.get("callouts") or [],
        }

    warnings = []
    if unknown:
        warnings.append(
            "not in the viewer's MAP_NAMES table (deathmatch maps, or a new "
            f"release the table has not caught up with): {', '.join(unknown)}",
        )
    return downloads, manifest, warnings


def plan_agents(agents: list[dict]) -> tuple[list[Download], dict]:
    """
    Downloads and manifest fragment for the agents endpoint.

    Ability slots whose displayIcon is null -- most Passive slots -- are
    dropped; an ability with no icon is not art to cache.
    """
    downloads: list[Download] = []
    manifest: dict = {}

    for entry in sorted(agents, key=lambda a: a.get("displayName") or ""):
        name = entry.get("displayName") or ""
        if not name:
            continue
        folder = f"agents/{safe_name(name)}"
        files = _files_for(entry, AGENT_FILES, folder)
        downloads.extend(files)

        abilities: dict = {}
        for ability in entry.get("abilities") or []:
            slot, icon = ability.get("slot") or "", ability.get("displayIcon")
            if not slot or not icon:
                continue
            path = f"{folder}/abilities/{safe_name(slot).lower()}.png"
            downloads.append(Download(icon, path))
            abilities[slot] = {
                "display_name": ability.get("displayName"),
                "file": path,
            }

        role = entry.get("role") or {}
        manifest[name] = {
            "uuid": entry.get("uuid"),
            # Riot's internal name for the agent -- Hunter for Sova, Wushu for
            # Jett.  It is the only join from a pawn's archetype path in the
            # replication stream to a public agent name, and this endpoint is
            # the only place it is published: val-content-v1 has no equivalent
            # field.  See valcatalog and vrfview.names.
            "developer_name": entry.get("developerName"),
            "role": role.get("displayName"),
            "files": _by_filename(files),
            "abilities": abilities,
        }
    return downloads, manifest


def plan_roles(agents: list[dict]) -> tuple[list[Download], dict]:
    """One icon per distinct agent role, deduplicated across the roster."""
    downloads: list[Download] = []
    manifest: dict = {}
    for entry in agents:
        role = entry.get("role") or {}
        name, icon = role.get("displayName") or "", role.get("displayIcon")
        if not name or not icon or name in manifest:
            continue
        path = f"roles/{safe_name(name)}.png"
        downloads.append(Download(icon, path))
        manifest[name] = {"uuid": role.get("uuid"), "file": path}
    return downloads, manifest


# --- network ---------------------------------------------------------------


def _check_url(url: str) -> None:
    """Reject anything that is not plain https before it reaches urlopen."""
    if not url.startswith("https://"):
        msg = f"refusing non-https url: {url!r}"
        raise ValueError(msg)


def _fetch(url: str) -> bytes:
    """GET a URL, retrying transient failures with a widening backoff."""
    _check_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 < RETRIES:
                time.sleep(BACKOFF_S * (attempt + 1))
    msg = f"{url} failed after {RETRIES} attempts: {last}"
    raise OSError(msg)


def get_json(path: str) -> dict | list | None:
    """Decode one valorant-api.com endpoint, returning its `data` payload."""
    body = json.loads(_fetch(f"{API}{path}").decode("utf-8"))
    return body.get("data")


# --- driving ---------------------------------------------------------------


def collect(groups: tuple[str, ...]) -> tuple[list[Download], dict, list[str]]:
    """Resolve the endpoints the chosen groups need and plan every file."""
    downloads: list[Download] = []
    warnings: list[str] = []
    manifest: dict = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": API,
        "note": "official Riot art, cached locally via valorant-api.com",
    }

    if "maps" in groups:
        found, manifest["maps"], warnings = plan_maps(get_json("/maps") or [])
        downloads.extend(found)

    if "agents" in groups or "roles" in groups:
        # isPlayableCharacter is a no-op against today's roster -- both forms
        # return 29 -- but it is the documented guard against the unreleased
        # and duplicate entries the endpoint has carried before.
        agents = get_json("/agents?isPlayableCharacter=true") or []
        if "agents" in groups:
            found, manifest["agents"] = plan_agents(agents)
            downloads.extend(found)
        if "roles" in groups:
            found, manifest["roles"] = plan_roles(agents)
            downloads.extend(found)

    manifest["version"] = get_json("/version") or {}
    return downloads, manifest, warnings


def _save(item: Download, out: Path, *, force: bool) -> bool:
    """Write one file; True if it was fetched, False if it was already there."""
    dest = out / item.path
    if dest.exists() and not force:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_fetch(item.url))
    return True


def download(items: list[Download], out: Path, *, force: bool, jobs: int) -> int:
    """Fetch every planned file, reporting progress; return the fetched count."""
    total, done, fetched = len(items), 0, 0
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = pool.map(lambda i: _save(i, out, force=force), items)
        for item, was_fetched in zip(items, results, strict=True):
            done += 1
            fetched += int(was_fetched)
            verb = "get " if was_fetched else "skip"
            print(f"  [{done:>3}/{total}] {verb} {item.path}", file=sys.stderr)
    return fetched


def _report(manifest: dict, groups: tuple[str, ...], warnings: list[str]) -> None:
    counts = ", ".join(
        f"{len(manifest.get(group) or {})} {group}"
        for group in groups
        if group in manifest
    )
    print(f"({counts})", file=sys.stderr)
    for warning in warnings:
        print(f"note: {warning}", file=sys.stderr)


def cmd_list(args: argparse.Namespace) -> int:
    """Print every file that a fetch would write, and touch nothing."""
    downloads, manifest, warnings = collect(args.only)
    for item in downloads:
        print(item.path)
    print(f"\n{len(downloads)} files", file=sys.stderr)
    _report(manifest, args.only, warnings)
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """Download the planned files and rewrite the manifest."""
    out = Path(args.out)
    downloads, manifest, warnings = collect(args.only)
    print(f"{len(downloads)} files -> {out}", file=sys.stderr)

    fetched = download(downloads, out, force=args.force, jobs=args.jobs)

    manifest_path = out / "manifest.json"
    merged: dict = {}
    if manifest_path.exists():
        merged = json.loads(manifest_path.read_text(encoding="utf-8"))
    # A partial run (--only maps) must not wipe the other groups' entries.
    merged.update(manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(
        f"\n{fetched} downloaded, {len(downloads) - fetched} already present\n"
        f"manifest -> {manifest_path}",
        file=sys.stderr,
    )
    _report(manifest, args.only, warnings)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", default="fetch", choices=COMMANDS)
    parser.add_argument("--out", default="assets", help="output directory")
    parser.add_argument(
        "--only",
        action="append",
        choices=GROUPS,
        help="limit to one group; repeatable (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download files that already exist",
    )
    parser.add_argument("--jobs", type=int, default=4, help="concurrent downloads")
    args = parser.parse_args(argv)
    args.only = tuple(args.only) if args.only else GROUPS

    try:
        return cmd_list(args) if args.command == "list" else cmd_fetch(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
