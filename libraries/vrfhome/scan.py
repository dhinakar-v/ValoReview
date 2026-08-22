"""
Describe a library of `.vrf` files, cheaply and without decompressing anything.

Every field a match card shows -- map, date, duration, round count, build --
lives in a plain chunk, so scanning a library needs no Oodle DLL and no
network.  What it does need is to read each file once: the chunk table is
walked from the container header to the end of the file, and the roundStarted
events are scattered through it, so there is no header-only shortcut.  That is
about 0.04 s for a 47 MB capture, so a hundred of them is a few seconds cold
and nothing at all warm, because the results are cached by
`(path, mtime, size)` and a replay never changes after it is written.

What a card may and may not say
-------------------------------
The brief asks each card for a `WIN` / `LOSS` badge.  **It cannot be built.**
There is no local player in the file and the two teams are `A` and `B` by
inference, not by side, so any badge would be a coin flip dressed as a fact.
`RESULT_NOT_IN_FILE` is what the card shows instead, and the UI states it
rather than leaving an empty space that reads as "nobody won".

What the card *can* say, and what the brief never thought to ask for, is
whether this capture's build has a payload transform -- that is, whether the
viewer can draw it at all.  It costs one string comparison against
`payload_transform.SUPPORTED_BRANCHES`, which is the same table the decoder
itself consults, so the indicator cannot drift away from what the decode will
actually do.  It is now load-bearing rather than decorative: the list shows
`playable` by default, because opening a capture that will never produce a map
is a dead end and the schematic that used to soften it is gone.  The ones held
back are counted and one button away, never silently dropped.

A file that fails to parse is a card too
----------------------------------------
A truncated or non-`.vrf` file in the library becomes a card carrying its
error, not an exception and not a silent omission: a match list that quietly
drops two of a hundred files is worse than one that says which two and why.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import vrfconfig
from vrf_reader import VrfError, VrfFile
from vrfnet.payload_transform import SUPPORTED_BRANCHES
from vrfview.loader import map_name_for

# The badge the brief demands and the file cannot support.  A constant rather
# than a literal in the UI, so there is exactly one place saying it.
RESULT_NOT_IN_FILE = "result not in file"

POSITIONS_AVAILABLE = "positions decode on this build"
POSITIONS_UNAVAILABLE = "no payload transform for this build; nothing to draw"

# What the footer says about the captures the default filter holds back.
HIDDEN_NOTE = "{n} hidden - no payload transform for their build"

CACHE_VERSION = 1
DEFAULT_CACHE = Path("out") / "match-scan.json"

PER_PAGE = 10


@dataclass(frozen=True)
class MatchCard:
    """One replay, as much as the plain chunks state about it."""

    path: Path
    match_id: str = ""
    map_path: str = ""
    map_name: str = ""
    recorded_utc: datetime | None = None
    length_ms: int = 0
    rounds: int = 0
    players: int = 0
    build: str = ""
    size_bytes: int = 0
    error: str = ""

    @property
    def file_name(self) -> str:
        return self.path.name

    @property
    def readable(self) -> bool:
        return not self.error

    @property
    def positions_available(self) -> bool:
        """Whether the viewer will draw this one on a real map."""
        return self.build in SUPPORTED_BRANCHES

    @property
    def playable(self) -> bool:
        """Whether opening this card can lead anywhere: readable and decodable."""
        return self.readable and self.positions_available

    @property
    def positions_note(self) -> str:
        return (
            POSITIONS_AVAILABLE if self.positions_available else POSITIONS_UNAVAILABLE
        )

    @property
    def duration(self) -> str:
        """MM:SS, as the brief's card asks for it."""
        seconds = self.length_ms // 1000
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @property
    def recorded(self) -> str:
        """`DD MMM YYYY - HH:MM`, or a plain unknown when the header had none."""
        if self.recorded_utc is None:
            return "date not in file"
        return self.recorded_utc.strftime("%d %b %Y - %H:%M")

    @property
    def result(self) -> str:
        """Always RESULT_NOT_IN_FILE.  See the module docstring."""
        return RESULT_NOT_IN_FILE


@dataclass
class ScanResult:
    """The cards, plus enough about the scan itself for the page to explain."""

    cards: list[MatchCard] = field(default_factory=list)
    root: vrfconfig.DemoRoot | None = None
    read: int = 0
    cached: int = 0

    @property
    def failed(self) -> list[MatchCard]:
        return [c for c in self.cards if not c.readable]

    @property
    def playable(self) -> list[MatchCard]:
        """The captures the viewer can actually draw -- the list's default."""
        return [c for c in self.cards if c.playable]

    @property
    def hidden(self) -> list[MatchCard]:
        """Everything the default filter holds back, counted rather than dropped."""
        return [c for c in self.cards if not c.playable]

    @property
    def described(self) -> str:
        """One line the home page can show verbatim."""
        where = self.root.described if self.root is not None else "no directory"
        if not self.cards:
            return f"no replays in {where}"
        bad = len(self.failed)
        note = f", {bad} unreadable" if bad else ""
        held = len(self.hidden)
        back = f"; {HIDDEN_NOTE.format(n=held)}" if held else ""
        return (
            f"{len(self.playable)} of {len(self.cards)} replays in {where} "
            f"({self.read} read, {self.cached} from cache{note}){back}"
        )


def read_card(path: str | Path) -> MatchCard:
    """One file's card.  Never raises: a bad file becomes a card with an error."""
    src = Path(path)
    try:
        size = src.stat().st_size
    except OSError as exc:
        return MatchCard(path=src, error=str(exc))
    try:
        vrf = VrfFile(src)
    except (VrfError, OSError) as exc:
        return MatchCard(path=src, size_bytes=size, error=str(exc))

    map_path = vrf.demo.maps[0] if vrf.demo.maps else ""
    name, _ = map_name_for(map_path)
    return MatchCard(
        path=src,
        match_id=vrf.header.friendly_name,
        map_path=map_path,
        map_name=name,
        recorded_utc=vrf.header.recorded_utc,
        length_ms=vrf.header.length_ms,
        rounds=sum(1 for e in vrf.events() if e.group == "roundStarted"),
        players=len(vrf.players()),
        build=vrf.demo.build,
        size_bytes=size,
    )


class Cache:
    """
    Cards keyed by `(path, mtime, size)`, so a rescan re-reads only what moved.

    A replay is written once and never edited, which is what makes this safe:
    the key changes if the file does, and a stale entry cannot outlive the
    bytes it describes.  Anything unreadable or of the wrong version is simply
    ignored -- a cache is an optimisation, so a corrupt one costs a rescan and
    nothing else.
    """

    def __init__(self, path: str | Path | None = DEFAULT_CACHE):
        self.path = Path(path) if path is not None else None
        self.entries: dict[str, dict] = {}
        self.dirty = False
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(doc, dict) and doc.get("version") == CACHE_VERSION:
            self.entries = doc.get("entries") or {}

    def save(self) -> None:
        if self.path is None or not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"version": CACHE_VERSION, "entries": self.entries}
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        self.dirty = False

    def get(self, path: Path) -> MatchCard | None:
        entry = self.entries.get(_key(path))
        return None if entry is None else _from_entry(path, entry)

    def put(self, card: MatchCard) -> None:
        self.entries[_key(card.path)] = _to_entry(card)
        self.dirty = True


def scan(
    root: str | None = None,
    cache: Cache | None = None,
    progress=None,
) -> ScanResult:
    """
    Every `.vrf` under the replay directory, described.

    `root` overrides `DEMO_PATH` the way a command-line flag does; the
    directory that answered travels back on the result, because "no replays"
    and "no replays *here*" are different things to tell a user.
    """
    demo_root = vrfconfig.demo_root(root)
    out = ScanResult(root=demo_root)
    cache = Cache() if cache is None else cache
    paths = vrfconfig.replays(root)
    for i, path in enumerate(paths):
        card = cache.get(path)
        if card is None:
            card = read_card(path)
            cache.put(card)
            out.read += 1
        else:
            out.cached += 1
        out.cards.append(card)
        if progress is not None:
            progress(i + 1, len(paths))
    cache.save()
    return out


# --------------------------------------------------------------------------
# arranging what was scanned -- all pure, all testable without a display
# --------------------------------------------------------------------------
def sort_cards(cards: list[MatchCard], *, descending: bool = False) -> list[MatchCard]:
    """
    By date, the brief's default being ascending.

    A card with no date sorts to the end either way rather than to the epoch:
    an unknown recording time is not "the oldest match in the library".
    """
    dated = [c for c in cards if c.recorded_utc is not None]
    undated = [c for c in cards if c.recorded_utc is None]
    dated.sort(key=lambda c: (c.recorded_utc, c.file_name), reverse=descending)
    undated.sort(key=lambda c: c.file_name)
    return dated + undated


def filter_cards(
    cards: list[MatchCard],
    map_name: str = "",
    date: str = "",
) -> list[MatchCard]:
    """
    The brief's filter bar: by map name, by date, or both.

    Both are substring matches on what the card displays -- `date` against the
    ISO day, so `2026-08` is a month and `2026-08-22` a day -- because the
    filter bar is one text box and a user typing `hav` means Haven.
    """
    out = list(cards)
    if map_name:
        needle = map_name.strip().lower()
        out = [c for c in out if needle in c.map_name.lower()]
    if date:
        needle = date.strip()
        out = [
            c
            for c in out
            if c.recorded_utc is not None
            and needle in c.recorded_utc.date().isoformat()
        ]
    return out


def page_count(cards: list[MatchCard], per_page: int = PER_PAGE) -> int:
    """At least one page, so an empty library still has a page to show."""
    return max(1, -(-len(cards) // max(1, per_page)))


def page(cards: list[MatchCard], number: int = 1, per_page: int = PER_PAGE) -> list:
    """One page, 1-based, clamped -- paging past the end shows the last page."""
    total = page_count(cards, per_page)
    index = min(max(1, number), total) - 1
    return cards[index * per_page : (index + 1) * per_page]


def maps_present(cards: list[MatchCard]) -> list[str]:
    """The map names in the library, for the filter bar's own menu."""
    return sorted({c.map_name for c in cards if c.map_name})


# --------------------------------------------------------------------------
def _key(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return str(path.resolve())
    return f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"


def _to_entry(card: MatchCard) -> dict:
    return {
        "match_id": card.match_id,
        "map_path": card.map_path,
        "map_name": card.map_name,
        "recorded_utc": card.recorded_utc.isoformat() if card.recorded_utc else None,
        "length_ms": card.length_ms,
        "rounds": card.rounds,
        "players": card.players,
        "build": card.build,
        "size_bytes": card.size_bytes,
        "error": card.error,
    }


def _from_entry(path: Path, entry: dict) -> MatchCard:
    raw = entry.get("recorded_utc")
    try:
        recorded = datetime.fromisoformat(raw) if raw else None
    except ValueError:
        recorded = None
    return MatchCard(
        path=path,
        match_id=str(entry.get("match_id") or ""),
        map_path=str(entry.get("map_path") or ""),
        map_name=str(entry.get("map_name") or ""),
        recorded_utc=recorded,
        length_ms=int(entry.get("length_ms") or 0),
        rounds=int(entry.get("rounds") or 0),
        players=int(entry.get("players") or 0),
        build=str(entry.get("build") or ""),
        size_bytes=int(entry.get("size_bytes") or 0),
        error=str(entry.get("error") or ""),
    )
