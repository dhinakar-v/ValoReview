"""
Which of the two loadout halves is `infer`'s team A, once something can tell.

`vrfhome.scan.team_ids` establishes *that* the loadout roster's first five and
last five are the two teams -- measured 103 of 103 against duplicated agents and
23 of 23 against the kill graph.  It cannot establish **which** of them `infer`
calls A, and neither can anything else that reads only plain chunks: `infer`
names the group holding the lowest actor net ID "A" (see `infer._assign_teams`),
and that has nothing to do with the order a capture lists its loadouts in.
Measured over the captures with a cached decode it came out 12 to 10 -- a coin
flip, which is exactly the kind of answer this project refuses to print.

So the scoreline cannot be attached to a row from the plain chunks alone, and a
score printed against the wrong five agents is worse than no score: it looks
right.  What *can* answer is a decode, because a decoded pawn states its own
agent codename -- and once a capture has been decoded the answer is one letter,
which is what this file keeps.

Why a cache and not a recomputation
-----------------------------------
The answer lives inside a 10-15 MB position sidecar, and the match list draws a
page of ten cards per request.  Reading a sidecar per row would put hundreds of
milliseconds into a list that is otherwise 0.03 s warm, to learn one letter that
can never change for a given capture.

Everything here degrades to "no entry"
--------------------------------------
No project root, an unwritable directory, a corrupt file or a version bump all
end as "nothing known", and a card with nothing known simply shows its agents
without a scoreline.  That is the same posture as every other cache in this
project: an optimisation whose absence costs information the page then declines
to state, never an exception.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import vrfcache

CACHE_FILENAME = "team-order.json"

# Bump when the meaning of a stored letter changes.  It records which team
# `infer` gave the loadout roster's *first* half, so a change to either the
# split rule or the two-colouring invalidates every entry.
CACHE_VERSION = 1

TEAM_A = "A"
TEAM_B = "B"
TEAM_SIZE = 5


def cache_path() -> Path:
    """Where the letters live.  Raises `NoProjectRootError` if nowhere."""
    return vrfcache.root() / CACHE_FILENAME


def load() -> dict[str, str]:
    """Every letter known, keyed by match id.  Empty when there is nothing."""
    try:
        path = cache_path()
    except vrfcache.NoProjectRootError:
        return {}
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(doc, dict) or doc.get("version") != CACHE_VERSION:
        return {}
    entries = doc.get("entries")
    if not isinstance(entries, dict):
        return {}
    return {str(k): str(v) for k, v in entries.items() if v in (TEAM_A, TEAM_B)}


def record(match_id: str, team: str) -> None:
    """Remember one answer.  A failure to write costs the next run a lookup."""
    if not match_id or team not in (TEAM_A, TEAM_B):
        return
    entries = load()
    if entries.get(match_id) == team:
        return
    entries[match_id] = team
    with contextlib.suppress(OSError, vrfcache.NoProjectRootError):
        path = cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"version": CACHE_VERSION, "entries": entries}
        path.write_text(json.dumps(doc), encoding="utf-8")


def first_half_team(replay, agent_ids, names_for) -> str:
    """
    Which team a decoded replay says the loadout's first half was, or `""`.

    `names_for` turns an agent UUID into the display name the catalogue
    publishes for it -- `ArtCache.agent_art` -- so both sides of the comparison
    are display names out of the same published catalogue.  That is the exact
    join `art.agent_art_by_name` already relies on, and it is the only one
    available: a `Player`'s agent is *read* from its pawn's archetype codename
    and named through the catalogue, and it never carries a UUID.

    Refuses -- returns `""` -- unless both teams name five agents and one half
    matches one team exactly.  A partial decode, a capture where two players
    share an agent within a team, or any disagreement leaves the score
    unattributed rather than attached to a guess.
    """
    first, second = agent_ids
    if len(first) != TEAM_SIZE or len(second) != TEAM_SIZE:
        return ""
    by_team = {TEAM_A: set(), TEAM_B: set()}
    for player in replay.players:
        if player.team in by_team and player.agent:
            by_team[player.team].add(player.agent)
    if any(len(v) != TEAM_SIZE for v in by_team.values()):
        return ""
    front = {names_for(uuid) for uuid in first}
    back = {names_for(uuid) for uuid in second}
    if len(front) != TEAM_SIZE or len(back) != TEAM_SIZE:
        return ""
    if front == by_team[TEAM_A] and back == by_team[TEAM_B]:
        return TEAM_A
    if front == by_team[TEAM_B] and back == by_team[TEAM_A]:
        return TEAM_B
    return ""
