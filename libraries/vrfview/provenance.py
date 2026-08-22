"""
Every claim the interface makes, and where each one came from.

Structured rather than one block of text, because more than one interface has
to render it now.  `sections` returns the facts as data; `describe` reproduces
the plain-text block the viewer has always shown, character for character, so
moving the account out of the viewer changed none of its wording.

The split into sections is the whole point of the module, and it is the same
distinction the rest of the package keeps: read from the file, decoded from the
replication stream, looked up in Riot's catalogue, inferred here, or absent
altogether.  A reader who cannot tell those apart cannot tell what the viewer
knows from what it worked out, so the headings stay rather than merging into
one list of equally true-sounding statements.

`ABSENT` is a constant and not derived from a replay on purpose.  Every one of
its entries is a fact about the format rather than about a capture -- no replay
carries player names, and none ever will -- so deriving them would make a
capture that happened to resolve nothing indistinguishable from the format not
carrying the thing at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vrf_reader import _fmt_ms
from vrfview import art as art_mod

if TYPE_CHECKING:
    from vrfview.art import ArtCache
    from vrfview.model import Replay

# Where a value starts, counting from the left margin: two spaces of indent and
# then a label field.  The absent section gets a wider one because its labels
# are short sentences rather than field names.
INDENT = 2
LABEL_WIDTH = 18
ABSENT_LABEL_WIDTH = 26

READ = "READ FROM THE FILE"
DECODED = "DECODED FROM THE REPLICATION STREAM"
CATALOGUE = "RESOLVED AGAINST RIOT'S CONTENT CATALOGUE"
ART = "ART CACHE (pictures only; it names nothing and infers nothing)"
INFERRED = "INFERRED (marked * in the interface)"
NOT_IN_FILE = "NOT IN THE FILE"

MAPREF_NOTE = "the map reference window plots Riot's callouts, never players"


@dataclass(frozen=True)
class Entry:
    """One fact.  An empty `label` is a bare line, which is what a note is."""

    label: str
    value: str

    @property
    def bare(self) -> bool:
        return not self.label


@dataclass(frozen=True)
class Section:
    """One provenance heading and the facts filed under it."""

    title: str
    entries: tuple[Entry, ...] = ()
    label_width: int = LABEL_WIDTH

    @property
    def described(self) -> str:
        return "\n".join(self.lines)

    @property
    def lines(self) -> list[str]:
        """Plain text for this section, continuations under the value column."""
        out = [self.title]
        margin = " " * INDENT
        under = " " * (INDENT + self.label_width)
        for entry in self.entries:
            if entry.bare:
                out.append(f"{margin}{entry.value}")
                continue
            head, *rest = entry.value.split("\n")
            out.append(f"{margin}{entry.label:<{self.label_width}}{head}")
            out += [f"{under}{line}" for line in rest]
        return out


@dataclass(frozen=True)
class Provenance:
    """The whole account, section by section."""

    sections: tuple[Section, ...] = ()

    @property
    def described(self) -> str:
        return "\n\n".join(s.described for s in self.sections)

    def section(self, title: str) -> Section | None:
        for s in self.sections:
            if s.title == title:
                return s
        return None


# Facts about the format, not about any capture.  See the module docstring.
ABSENT: tuple[Entry, ...] = (
    Entry(
        "player names / Riot IDs",
        "absent; they need val-match-v1, which a\n"
        "personal development key cannot reach",
    ),
    Entry(
        "health, armour, credits",
        "never replicated to a spectator recording;\n"
        "the player rows show -- rather than a number",
    ),
    Entry(
        "attacker / defender",
        "spike events carry no actor id, so which\n"
        "side planted is not recoverable, and the two\n"
        "colours mean team A and team B",
    ),
    Entry("weapon held", "in the property payload but not yet decoded"),
    Entry(
        "where an ability landed",
        "ability actors state what they are and when,\n"
        "but not where: the spawn transform is not at\n"
        "any fixed offset, and only the pawn kinds --\n"
        "a drone, a turret -- ever send a movement\n"
        "record.  A smoke has a time and no coordinate",
    ),
    Entry(
        "ability damage / radius",
        "no ability carries a range, radius or damage\n"
        "figure in the replay or in Riot's catalogue",
    ),
)


def ability_summary(replay: Replay) -> str:
    """What the ability decode found, or that it found nothing."""
    if not replay.ability_casts:
        return "not decoded; no ability actor was read"
    with_track = sum(1 for c in replay.ability_casts if c.has_track)
    slots = sorted({c.slot for c in replay.ability_casts})
    return (
        f"{len(replay.ability_casts)} casts across slots {', '.join(slots)}; "
        f"{with_track} spawned a pawn with a decoded path"
    )


def codename_summary(replay: Replay) -> str:
    """How many pawns stated their own agent, and which agents those were."""
    named = [p for p in replay.players if p.codename]
    if not named:
        return "not decoded; no pawn archetype was read"
    return (
        f"{len(named)} of {len(replay.players)} actors state their own agent "
        f"({', '.join(sorted({p.identity for p in named}))})"
    )


def _read(replay: Replay) -> Section:
    swap = _fmt_ms(replay.side_swap_ms) if replay.side_swap_ms else "not recorded"
    return Section(
        READ,
        (
            Entry("replay", replay.source),
            Entry("match id", replay.match_id or "not recorded"),
            Entry("recorded (UTC)", replay.recorded_utc),
            Entry("build", replay.build),
            Entry("duration", _fmt_ms(replay.length_ms)),
            Entry("map (internal)", replay.map_path),
            Entry("rounds", f"{len(replay.rounds)}, from roundStarted events"),
            Entry(
                "kills",
                f"{len(replay.kills)}, characterDeath: args[1] killer, args[2] victim",
            ),
            Entry("ultimates", f"{len(replay.ultimates)}, characterUltimateUsed"),
            Entry(
                "spike events",
                f"{len(replay.spike)}, timestamps only - the events carry no actor id",
            ),
            Entry("side swap", swap),
            Entry(
                "agent UUIDs",
                f"{len(replay.loadouts)} loadout slots, agent ids only",
            ),
        ),
    )


def _decoded(replay: Replay) -> Section:
    return Section(
        DECODED,
        (
            Entry("positions", replay.position_source or "not requested"),
            Entry("agent per actor", codename_summary(replay)),
            Entry("ability casts", ability_summary(replay)),
        ),
    )


def _catalogue(replay: Replay) -> Section:
    entries = [
        Entry("catalogue", replay.catalog_source),
        Entry("map name", f"{replay.map_name}, from the {replay.map_name_source}"),
        Entry("agents (roster)", ", ".join(replay.roster) or "unresolved"),
    ]
    entries += [Entry("", note) for note in replay.catalog_notes]
    return Section(CATALOGUE, tuple(entries))


def _art(replay: Replay, art: ArtCache | None) -> Section:
    cache = art if art is not None else art_mod.ArtCache()
    covered = art_mod.coverage(
        cache,
        replay.map_path,
        [x.character_id for x in replay.loadouts],
    )
    entries = [Entry("", line) for line in covered]
    entries.append(Entry("", MAPREF_NOTE))
    return Section(ART, tuple(entries))


def sections(replay: Replay, art: ArtCache | None = None) -> Provenance:
    """Every claim the interface makes, filed under where it came from."""
    return Provenance(
        (
            _read(replay),
            _decoded(replay),
            _catalogue(replay),
            _art(replay, art),
            Section(INFERRED, tuple(Entry("", note) for note in replay.notes)),
            Section(NOT_IN_FILE, ABSENT, ABSENT_LABEL_WIDTH),
        ),
    )


def describe(replay: Replay, art: ArtCache | None = None) -> str:
    """The same account as one plain-text block."""
    return sections(replay, art).described
