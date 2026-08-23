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
`payload_transform.SUPPORTED_BRANCHES`, which is the table `vrfview.tracks`
gates on, so the indicator and the refusal cannot disagree.  Both mirror what
`csharp/VrfPositions` supports; adding a build means adding it in both places.  It is now load-bearing rather than decorative: the list shows
`playable` by default, because opening a capture that will never produce a map
is a dead end and the schematic that used to soften it is gone.  The ones held
back are counted and one button away, never silently dropped.

Who played, and how the two teams are told apart
-----------------------------------------------
A card also names its ten agents, and that costs no decoder either: every
loadout slot in the match metadata carries an agent UUID, and the asset
manifest publishes one per agent.  Which five were a *team* is not stated
anywhere, and `team_ids` reads it off the roster's own order on measured
evidence rather than on faith -- the numbers are in its docstring, and
`tests/test_positions.py::LoadoutSplitIsTheRealTeamSplit` re-runs them.

The scoreline beside those agents is `infer`'s, so it is derived rather than
read, it is routinely short of the round count -- `rounds_undecided` says by
how much -- and it can only be put beside the right five faces once something
has established which half `infer` called team A.  Nothing here can: that
needs a decode.  See `vrfhome.teamorder`, and note that this is a different
claim from the badge below, which no amount of decoding would fix.

A file that fails to parse is a card too
----------------------------------------
A truncated or non-`.vrf` file in the library becomes a card carrying its
error, not an exception and not a silent omission: a match list that quietly
drops two of a hundred files is worse than one that says which two and why.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import vrfcache
import vrfconfig
from vrf_reader import VrfError, VrfFile
from vrfnet.payload_transform import SUPPORTED_BRANCHES
from vrfview import infer
from vrfview.loader import load_vrf, map_name_for

# The badge the brief demands and the file cannot support.  A constant rather
# than a literal in the UI, so there is exactly one place saying it.
RESULT_NOT_IN_FILE = "result not in file"

POSITIONS_AVAILABLE = "positions decode on this build"
POSITIONS_UNAVAILABLE = "no payload transform for this build; nothing to draw"


def positions_available(build: str) -> bool:
    """
    Whether a decode can work on this build at all, before anything is tried.

    A membership test against `payload_transform.SUPPORTED_BRANCHES`, the same
    table `tracks.extract` gates on, so this cannot drift from what a decode
    will refuse.
    Here rather than on `MatchCard` because two interfaces ask it about two
    different things -- a card asks whether to show a capture, and a viewer
    asks whether to offer a DECODE button -- and a control that can only ever
    refuse is worse than an explanation of its absence.
    """
    return build in SUPPORTED_BRANCHES


def positions_note(build: str) -> str:
    """The sentence that goes with the answer above."""
    return POSITIONS_AVAILABLE if positions_available(build) else POSITIONS_UNAVAILABLE


# What the footer says about the captures that will not draw on a map.  It was
# `{n} hidden` while the match list filtered them away; they are listed now, so
# the sentence counts a limitation rather than an omission.
NO_POSITIONS_NOTE = "{n} without positions - no payload transform for their build"

# A cached card holds the *resolved* map name rather than the path it came
# from, so it outlives a change to loader.MAP_NAMES: bump this whenever that
# table learns a codename, or every already-scanned capture keeps reporting
# the raw leaf the table used to fall back to.
CACHE_VERSION = 3
CACHE_FILENAME = "match-scan.json"

# Distinguishes "the caller said nothing" from "the caller said None", which
# already means *disable the cache* and has two callers relying on it
# (scripts/vrf_app.py --no-cache, vrfserve.library.rescan).
_UNSET = object()


def default_cache_path() -> Path | None:
    """
    Where the scan caches itself, or None if there is nowhere to.

    This used to be `Path("out") / "match-scan.json"`, which was relative to
    the *working directory*: running the app from anywhere but the repo root
    silently addressed a different cache and rescanned the whole library.
    `vrfcache` resolves the cache directory instead -- `VRF_CACHE_ROOT` when an
    installer named one, the checkout's own `.cache/` otherwise -- so every
    entry point agrees.  Resolved per call rather than at import, because a
    module-level constant would freeze the root before a test could move it.
    """
    root = vrfcache.root_or_none()
    return None if root is None else root / CACHE_FILENAME


PER_PAGE = 7


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
    # The two teams' agent UUIDs, in the file's own order -- see `team_ids`.
    # `((), ())` where the split was refused, which is the only other value.
    agent_ids: tuple[tuple[str, ...], tuple[str, ...]] = ((), ())
    # Rounds won by `infer`'s team A and team B, or None where the kill graph
    # gave no teams at all.  A and B are labels, never sides.
    score: tuple[int, int] | None = None
    # Rounds nothing settled.  A defuse or an explode records the reason but
    # leaves the winner unknown, so a score routinely falls short of `rounds`
    # and a reader has to be told by how much.
    rounds_undecided: int = 0

    @property
    def file_name(self) -> str:
        return self.path.name

    @property
    def readable(self) -> bool:
        return not self.error

    @property
    def positions_available(self) -> bool:
        """Whether the viewer will draw this one on a real map."""
        return positions_available(self.build)

    @property
    def playable(self) -> bool:
        """Whether opening this card can lead anywhere: readable and decodable."""
        return self.readable and self.positions_available

    @property
    def positions_note(self) -> str:
        return positions_note(self.build)

    # There were a `duration` and a `recorded` here, formatting `length_ms` and
    # `recorded_utc` into `MM:SS` and `DD MMM YYYY - HH:MM` for a card to print
    # directly.  They are gone: the browser is the only reader, it already had
    # to format `recorded_utc` for the viewer header, and two formatters over
    # one field is how the match list and the viewer came to write the same
    # instant two different ways.  `web/src/model/format.ts` owns it now, and
    # can write the reader's own zone -- which a `strftime` in UTC here cannot.

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
    def without_positions(self) -> list[MatchCard]:
        """
        The captures that will open but not draw on a map.

        This was `hidden`, back when the match list filtered them off the page.
        Nothing is held back now, so the name would have been the last thing
        still saying otherwise.
        """
        return [c for c in self.cards if not c.playable]

    @property
    def described(self) -> str:
        """
        One line the home page can show verbatim.

        It used to open `{playable} of {total} replays` and close with a count
        of what was `hidden`, which was true while the match list filtered to
        playable captures.  It does not any more, so both halves were claims
        the page disproved on the same screen -- `0 of 2 replays ... 2 hidden`
        printed above a list showing two.  The count is now what is listed, and
        the undecodable ones are still counted rather than passed over,
        because a capture with no positions is a real limitation of the
        library and not merely an absence.
        """
        where = self.root.described if self.root is not None else "no directory"
        if not self.cards:
            return f"no replays in {where}"
        bad = len(self.failed)
        note = f", {bad} unreadable" if bad else ""
        held = len(self.without_positions)
        back = f"; {NO_POSITIONS_NOTE.format(n=held)}" if held else ""
        return (
            f"{len(self.cards)} replays in {where} "
            f"({self.read} read, {self.cached} from cache{note}){back}"
        )


# How many players a match has, and therefore how long each half of the loadout
# roster is.  A capture that does not hold exactly this many slots is refused
# rather than split down the middle of whatever it does hold.
TEAM_SIZE = 5
ROSTER_SIZE = TEAM_SIZE * 2


def team_ids(loadouts) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    The two teams' agent UUIDs, read off the loadout roster's own order.

    **This is a measurement, not an assumption.**  Nothing in the metadata says
    "team", and `names` is right that a loadout slot cannot be joined to an
    actor net ID -- but the weaker, set-level claim that the first five slots
    are one team and the last five the other was checked two independent ways
    over the whole reference library:

      * 95 of the 103 captures carry a duplicated agent, i.e. the same agent on
        both teams.  A *random* 5/5 split would keep every duplicate out of its
        own half in about 45 of the 103; the file's own order does it in
        **103 of 103**.
      * On the 23 captures with a cached decode -- the only ones where a second
        opinion exists -- the two halves equal `infer`'s bipartite two-colouring
        of the kill graph **exactly, 23 of 23, with no disagreement**.

    `tests/test_vrfhome.py` keeps both figures honest.  What this does *not*
    license is naming which half is `infer`'s A and which is B: that ordering is
    a coin flip (measured 12 to 10), so a score cannot be attached to a row
    here.  See `vrfhome.teamorder`.

    An agent appearing twice inside one half would mean the order is not what
    this claims, so that capture is refused outright rather than split anyway.
    """
    ids = [str(entry.get("characterId") or "") for entry in loadouts]
    if len(ids) != ROSTER_SIZE or not all(ids):
        return ((), ())
    first, second = tuple(ids[:TEAM_SIZE]), tuple(ids[TEAM_SIZE:])
    if len(set(first)) != TEAM_SIZE or len(set(second)) != TEAM_SIZE:
        return ((), ())
    return (first, second)


def _derived(vrf: VrfFile, path: Path):
    """
    The teams and the scoreline, or empty values where they cannot be had.

    Best-effort on purpose.  `loader` raises for a capture with no rounds at
    all, and `infer` leaves teams unknown where the kill graph is not
    bipartite; neither makes the *file* unreadable, so a failure here costs the
    card its scoreline and never its error field.  `load_vrf` rather than
    `load` because the caller already read these 47 MB once.
    """
    empty = ((), ()), None, 0
    try:
        replay = infer.annotate(load_vrf(vrf, source=path))
    except Exception:  # noqa: BLE001 - read_card promises never to raise
        # Deliberately total.  `read_card` is documented never to raise and
        # `scan` has no guard of its own around it, so a surprise in here --
        # `loader` refusing a capture with no rounds, anything else -- must
        # cost this card its scoreline rather than the whole match list.
        return empty
    ids = team_ids(vrf.players())
    a, b = replay.score
    # Teams are unknown when nothing scores at all -- an empty score and an
    # honest 0-0 are different claims, and only the second may be printed.
    scored = any(p.team in ("A", "B") for p in replay.players)
    score = (a, b) if scored else None
    undecided = sum(1 for r in replay.rounds if not r.decided)
    return ids, score, undecided


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
    agent_ids, score, undecided = _derived(vrf, src)
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
        agent_ids=agent_ids,
        score=score,
        rounds_undecided=undecided,
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

    def __init__(self, path: str | Path | None = _UNSET):
        if path is _UNSET:
            path = default_cache_path()
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
        # Same rule as the two caches beside it: one that cannot be written
        # costs a rescan next run and nothing else, so a read-only directory
        # must not take the match list down with it.
        with contextlib.suppress(OSError):
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
        "agent_ids": [list(card.agent_ids[0]), list(card.agent_ids[1])],
        "score": list(card.score) if card.score is not None else None,
        "rounds_undecided": card.rounds_undecided,
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
        agent_ids=_entry_agent_ids(entry.get("agent_ids")),
        score=_entry_score(entry.get("score")),
        rounds_undecided=int(entry.get("rounds_undecided") or 0),
    )


def _entry_agent_ids(raw) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Rehydrate the split, refusing anything that is not two whole teams."""
    if not isinstance(raw, list) or len(raw) != 2:  # noqa: PLR2004
        return ((), ())
    halves = []
    for half in raw:
        if not isinstance(half, list) or len(half) != TEAM_SIZE:
            return ((), ())
        halves.append(tuple(str(x) for x in half))
    return (halves[0], halves[1])


def _entry_score(raw) -> tuple[int, int] | None:
    """`None` and `(0, 0)` are different claims, so the absent case survives."""
    if not isinstance(raw, list) or len(raw) != 2:  # noqa: PLR2004
        return None
    try:
        return (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return None
