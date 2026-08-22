"""
Tests for positions: the track record, the snapshot, and what names them.

Three kinds of claim are separated here on purpose.

`Track.at` and `codename_for` are pure and pinned by hand-built fixtures: they
encode judgements -- how far a position may be held before it stops standing
for the present, which archetype paths are a player and which are a corpse --
and a judgement is only worth having if it is written down somewhere it can be
argued with.

The inference and naming tests assert what must survive contact with an agent:
that a codename read off the wire is carried through every rebuild of a Player,
that it can refute a reconnect merge the timing alone would have accepted, and
that a loadout still never reaches a player.

`AgainstARealCapture` is the one that would catch a real decoding regression.
It re-runs the ground truth at the level the viewer sees: for every kill in the
window, the killer and the victim must be close enough to have shot each other.
tests/test_movement.py proves the same coordinates against Riot's own spawn
callouts one layer down; this proves the model did not lose them on the way up.
"""

from __future__ import annotations

import math
import unittest
from pathlib import Path

import pytest

from vrfview import tracks
from vrfview.infer import annotate
from vrfview.loader import load
from vrfview.model import (
    MAX_HOLD_MS,
    MAX_INTERPOLATE_MS,
    TEAM_A,
    TEAM_B,
    Kill,
    Player,
    Position,
    Replay,
    Round,
    Track,
)
from vrfview.names import AGENT_CODENAMES, resolve
from vrfview.state import state_at

# A 12.10 capture (Haven), and the 11.11 reference capture, which has no
# transform and must therefore refuse rather than misdecode.  Demos/ is
# gitignored, so both are skipped on a clean checkout.
DEMO_12_10 = Path("Demos/03fcbb4a-0064-4e4d-a209-091cb73ee5b8.vrf")
DEMO_11_11 = Path("Demos/039f3991-5472-4119-bed2-838da0935f60.vrf")

# Rifle range on Haven, generously.  The map is some 10,000 units across, so a
# pair of duellists this close cannot be an accident of decoding.
WEAPON_RANGE = 5000

PAWN = "/Game/Characters/Hunter/Hunter_PC.Default__Hunter_PC_C"
CORPSE = "/Game/Characters/Smonk/Smonk_PostDeath_PC.Default__Smonk_PostDeath_PC_C"
ABILITY = "/Game/Characters/Pine/S0/Ability_E/Pawn_Pine_E_RadEater.Default__X_C"


def at(t_ms, x, y, yaw=0.0, actor_id=1):
    return Position(t_ms=t_ms, actor_id=actor_id, x=x, y=y, z=0.0, yaw=yaw)


def track(*samples, actor_id=1):
    return Track(actor_id=actor_id, samples=tuple(samples))


class TestCodenameFor(unittest.TestCase):
    """Which archetype paths are a player, and which only look like one."""

    def test_a_player_pawn_yields_its_codename(self):
        assert tracks.codename_for(PAWN) == "Hunter"

    def test_a_post_death_pawn_is_not_a_player(self):
        """Same depth, same agent folder, and not somebody who is playing."""
        assert tracks.codename_for(CORPSE) == ""

    def test_an_ability_pawn_is_not_a_player(self):
        assert tracks.codename_for(ABILITY) == ""

    def test_anything_else_is_not_a_player(self):
        for path in ("", "/Game/Weapons/Vandal/Vandal_C", "/Script/Ares.AresPawn"):
            assert tracks.codename_for(path) == ""

    def test_every_codename_it_can_return_has_a_name(self):
        """A codename with no entry in the table would show as a raw path leaf."""
        assert AGENT_CODENAMES["hunter"] == "Sova"
        assert all(k == k.lower() for k in AGENT_CODENAMES)


class TestTrackAt(unittest.TestCase):
    """Interpolate over a short gap, hold briefly, then admit to knowing nothing."""

    def test_an_exact_sample_is_returned_unchanged(self):
        sample = at(1000, 10.0, 20.0)
        assert track(at(0, 0.0, 0.0), sample).at(1000) is sample

    def test_a_short_gap_is_interpolated(self):
        got = track(at(0, 0.0, 0.0), at(200, 100.0, 200.0)).at(100)
        assert got.x == pytest.approx(50.0)
        assert got.y == pytest.approx(100.0)
        assert got.t_ms == 100

    def test_interpolated_heading_takes_the_short_way_round(self):
        """350 to 10 degrees is 20 degrees of turn, not 340."""
        got = track(at(0, 0.0, 0.0, yaw=350.0), at(200, 0.0, 0.0, yaw=10.0)).at(100)
        assert got.yaw == pytest.approx(0.0)

    def test_a_long_gap_is_not_interpolated(self):
        """A straight line across a gap this size would run through walls."""
        far = MAX_INTERPOLATE_MS + 1000
        got = track(at(0, 0.0, 0.0), at(far, 9999.0, 9999.0)).at(10)
        assert got.x == 0.0
        assert got.t_ms == 0

    def test_a_lone_sample_is_held_briefly(self):
        got = track(at(0, 5.0, 6.0)).at(MAX_HOLD_MS - 1)
        assert got is not None
        # It reports its own measured time, so a caller can see it is stale.
        assert got.t_ms == 0

    def test_past_the_hold_there_is_no_position(self):
        assert track(at(0, 5.0, 6.0)).at(MAX_HOLD_MS + 1) is None

    def test_before_the_first_sample_is_held_too(self):
        assert track(at(10_000, 5.0, 6.0)).at(9_000) is not None
        assert track(at(10_000, 5.0, 6.0)).at(1_000) is None

    def test_an_empty_track_knows_nothing(self):
        assert Track(actor_id=1).at(0) is None
        assert Track(actor_id=1).bounds == (0.0, 0.0, 0.0, 0.0)
        assert len(Track(actor_id=1)) == 0

    def test_bounds_cover_every_sample(self):
        got = track(at(0, -5.0, 1.0), at(100, 7.0, -3.0)).bounds
        assert got == (-5.0, 7.0, -3.0, 1.0)


def moving_replay():
    """Two players, one kill, and a track each running the length of a round."""
    replay = Replay(source="synthetic", length_ms=10_000)
    replay.kills = [Kill(t_ms=5_000, killer=1, victim=2, round_no=1)]
    replay.players = [Player(actor_id=1, team=TEAM_A), Player(actor_id=2, team=TEAM_B)]
    replay.rounds = [Round(number=1, index=0, start_ms=0, end_ms=10_000)]
    replay.positions = {
        1: track(
            *(at(t, float(t), 0.0, actor_id=1) for t in range(0, 10_001, 100)),
            actor_id=1,
        ),
        # Player 2 stops emitting at the moment they are killed.
        2: track(
            *(at(t, 0.0, float(t), actor_id=2) for t in range(0, 5_001, 100)),
            actor_id=2,
        ),
    }
    return replay


class TestSnapshotPositions(unittest.TestCase):
    """What state_at reports, and what it refuses to keep reporting."""

    def test_a_live_player_is_positioned(self):
        snap = state_at(moving_replay(), 2_500)
        assert snap.positions[1].x == pytest.approx(2_500.0)
        assert snap.positions[2].y == pytest.approx(2_500.0)
        assert snap.has_positions

    def test_a_dead_player_is_pinned_where_they_fell(self):
        snap = state_at(moving_replay(), 8_000)
        assert 2 not in snap.positions
        assert snap.death_positions[2].y == pytest.approx(5_000.0)
        assert snap.position_of(2) is snap.death_positions[2]

    def test_the_death_position_outranks_a_still_live_one(self):
        """Just after the kill both readings exist; the death is the true one."""
        snap = state_at(moving_replay(), 5_000)
        assert 2 not in snap.positions
        assert snap.death_positions[2].y == pytest.approx(5_000.0)

    def test_seeking_backwards_gives_the_same_answer(self):
        replay = moving_replay()
        forward = [state_at(replay, t).positions.get(1) for t in range(0, 9_000, 500)]
        backward = [
            state_at(replay, t).positions.get(1) for t in range(8_500, -1, -500)
        ]
        assert forward == list(reversed(backward))

    def test_a_replay_with_no_tracks_reports_none(self):
        replay = moving_replay()
        replay.positions = {}
        snap = state_at(replay, 2_500)
        assert not snap.has_positions
        assert snap.position_of(1) is None


def named_replay(codenames, character_ids=()):
    """A two-player replay whose pawns stated the given codenames."""
    replay = moving_replay()
    replay.players = [
        Player(actor_id=p.actor_id, team=p.team, label=f"P{p.actor_id}", codename=c)
        for p, c in zip(replay.players, codenames, strict=False)
    ]
    replay.loadouts = list(character_ids)
    return replay


class TestCodenameNames(unittest.TestCase):
    """A codename is looked up, never invented, and the source is always said."""

    def test_the_built_in_table_names_a_pawn(self):
        replay = resolve(named_replay(["Hunter", "Wushu"]))
        assert [p.agent for p in replay.players] == ["Sova", "Jett"]
        assert any("built-in codename table" in n for n in replay.catalog_notes)

    def test_an_unknown_codename_is_reported_not_guessed(self):
        replay = resolve(named_replay(["Nobody", "Wushu"]))
        assert replay.player(1).agent == ""
        assert replay.player(1).identity == "Nobody"
        assert any("in no built-in table" in n for n in replay.catalog_notes)

    def test_a_replay_with_no_codenames_says_nothing_about_agents(self):
        replay = resolve(moving_replay())
        assert not any("archetype codename" in n for n in replay.catalog_notes)


class TestInferenceWithAgents(unittest.TestCase):
    """What knowing the agents buys the inference layer."""

    def test_a_codename_survives_labelling(self):
        replay = annotate(named_replay(["Hunter", "Wushu"]))
        assert {p.codename for p in replay.players} == {"Hunter", "Wushu"}
        assert all(p.label for p in replay.players)

    def test_duplicate_agents_within_a_team_are_reported(self):
        replay = named_replay(["Hunter", "Wushu"])
        replay.players = [
            Player(actor_id=1, team=TEAM_A, codename="Hunter"),
            Player(actor_id=2, team=TEAM_A, codename="Hunter"),
        ]
        replay.kills = []
        annotate(replay)
        assert any("disagrees with the agents" in n for n in replay.notes)

    def test_distinct_agents_corroborate_the_split(self):
        replay = annotate(named_replay(["Hunter", "Wushu"]))
        assert any("corroborated by the agents" in n for n in replay.notes)


class TestReconnectMerge(unittest.TestCase):
    """A codename can refute a pairing that the timing alone would accept."""

    def reconnect(self, codenames):
        """
        Team A holds three actors, exactly one pair of which never overlaps.

        Actor 1 spans the whole match deliberately, so it overlaps both of the
        others and only (3, 5) is a candidate pairing.  With more than one
        candidate the merge declines on ambiguity and never reaches the
        codename check this class is about.
        """
        replay = Replay(source="synthetic", length_ms=10_000)
        replay.kills = [
            Kill(t_ms=100, killer=1, victim=2),
            Kill(t_ms=200, killer=3, victim=2),
            Kill(t_ms=4_000, killer=3, victim=2),
            Kill(t_ms=5_000, killer=5, victim=2),
            Kill(t_ms=8_000, killer=5, victim=2),
            Kill(t_ms=9_000, killer=1, victim=2),
        ]
        replay.rounds = [Round(number=1, index=0, start_ms=0, end_ms=10_000)]
        replay.players = [
            Player(actor_id=a, codename=c)
            for a, c in zip((1, 2, 3, 5), codenames, strict=True)
        ]
        replay.positions = {
            3: track(at(200, 1.0, 1.0, actor_id=3), actor_id=3),
            5: track(at(5_000, 2.0, 2.0, actor_id=5), actor_id=5),
        }
        return replay

    def test_matching_codenames_corroborate_the_merge(self):
        replay = annotate(self.reconnect(["Hunter", "Wushu", "Clay", "Clay"]))
        assert any("both pawns are Clay" in n for n in replay.notes)
        assert len(replay.players) == 3

    def test_a_codename_mismatch_refuses_the_merge(self):
        replay = annotate(self.reconnect(["Hunter", "Wushu", "Clay", "Pine"]))
        assert any("were left unmerged" in n for n in replay.notes)
        assert len(replay.players) == 4

    def test_a_merge_joins_the_two_tracks(self):
        replay = annotate(self.reconnect(["Hunter", "Wushu", "Clay", "Clay"]))
        kept = replay.positions[3]
        assert len(kept) == 2
        assert [p.t_ms for p in kept.samples] == [200, 5_000]
        # Every sample now belongs to the actor that survived.
        assert {p.actor_id for p in kept.samples} == {3}
        assert 5 not in replay.positions


class TestAttachRefusals(unittest.TestCase):
    """Every way of having no positions ends in a sentence, not an exception."""

    def test_a_json_dump_has_no_replication_stream(self):
        replay = tracks.attach(Replay(source="x"), "out/whatever.json")
        assert replay.position_source == tracks.NO_SOURCE_JSON
        assert not replay.has_positions

    def test_a_missing_file_is_reported_not_raised(self):
        replay = tracks.attach(Replay(source="x"), "Demos/no-such-file.vrf")
        assert replay.position_source.startswith("no positions:")
        assert not replay.has_positions


@pytest.mark.skipif(not DEMO_11_11.exists(), reason="needs the 11.11 capture")
class TestUnsupportedBuild(unittest.TestCase):
    def test_an_unsupported_build_refuses_and_names_itself(self):
        """Never a nearest-version fallback: that is the one unrecoverable bug."""
        replay = tracks.attach(annotate(load(DEMO_11_11)), DEMO_11_11)
        assert not replay.has_positions
        assert "release-11.11" in replay.position_source
        assert "release-12.10" in replay.position_source
        assert all(not p.codename for p in replay.players)


# What the 12.10 capture's own pawns say they are: actor net ID -> codename,
# and the public name each codename resolves to.  Measured, not chosen.
KNOWN_CODENAMES = {
    548: "Hunter",
    642: "Wushu",
    742: "Smonk",
    842: "Vampire",
    976: "Sequoia",
    1074: "Killjoy",
    1172: "Vampire",
    1272: "Smonk",
    1370: "Pine",
    1466: "Hunter",
}
KNOWN_AGENTS = {
    548: "Sova",
    642: "Jett",
    742: "Clove",
    842: "Reyna",
    976: "Iso",
    1074: "Killjoy",
    1172: "Reyna",
    1272: "Clove",
    1370: "Veto",
    1466: "Sova",
}


@pytest.mark.skipif(not DEMO_12_10.exists(), reason="needs the 12.10 capture")
class AgainstARealCapture(unittest.TestCase):
    replay: Replay

    @classmethod
    def setUpClass(cls):
        replay = load(DEMO_12_10)
        # The whole match, because the whole match is about four seconds now.
        # This used to decode two blocks to stay under a four-minute wait, and
        # the tests below were written against that window -- which is why some
        # of them still tolerate a player whose track does not span the file.
        tracks.attach(replay, DEMO_12_10, tracks.Options(cache=False))
        cls.replay = resolve(annotate(replay))

    def covered(self, actor_id, t_ms):
        """Whether this actor's own track spans `t_ms`."""
        found = self.replay.track(actor_id)
        return found is not None and found.span_ms[0] <= t_ms <= found.span_ms[1]

    def test_every_player_gets_a_track_and_an_agent(self):
        for player in self.replay.players:
            if player.actor_id not in self.replay.positions:
                continue  # a reconnect whose second life is past this window
            assert player.codename, f"{player.display} has no codename"
            assert player.agent, f"{player.display} has no agent"

    def test_only_players_get_tracks(self):
        """Ability pawns and corpses move too; none may reach the model."""
        actors = {p.actor_id for p in self.replay.players}
        assert set(self.replay.positions) <= actors

    def test_killer_and_victim_are_within_weapon_range(self):
        """
        The ground truth, at the level the viewer reads it.

        Nothing in the decode knows what a kill is, so agreement between the
        event stream and the coordinates is evidence and not a tautology.
        """
        checked = 0
        for kill in self.replay.kills:
            if kill.is_suicide:
                continue
            if not (
                self.covered(kill.killer, kill.t_ms)
                and self.covered(kill.victim, kill.t_ms)
            ):
                continue
            snap = state_at(self.replay, kill.t_ms)
            killer = snap.position_of(kill.killer)
            victim = snap.position_of(kill.victim)
            # Inside the covered window every player has samples, so a missing
            # position is itself the failure and not a reason to skip.
            assert killer is not None, f"no position for killer at {kill.t_ms}"
            assert victim is not None, f"no position for victim at {kill.t_ms}"
            checked += 1
            apart = math.dist(
                (killer.x, killer.y, killer.z),
                (victim.x, victim.y, victim.z),
            )
            assert apart < WEAPON_RANGE, (
                f"kill at {kill.t_ms} puts {kill.killer} and {kill.victim} "
                f"{apart:.0f} units apart"
            )
        assert checked >= 5, f"only {checked} kills fell inside the decoded window"

    def test_the_two_teams_start_apart(self):
        """Attackers and defenders spawn at opposite ends; the split says so."""
        snap = state_at(self.replay, self.replay.rounds[0].start_ms + 1_000)
        centres = []
        for team in (TEAM_A, TEAM_B):
            ys = [
                snap.positions[p.actor_id].y
                for p in self.replay.team(team)
                if p.actor_id in snap.positions
            ]
            assert len(ys) >= 4, f"team {team} has {len(ys)} positioned players"
            centres.append(sum(ys) / len(ys))
        assert abs(centres[0] - centres[1]) > 5_000

    def test_the_provenance_line_says_what_was_decoded(self):
        assert "release-12.10" in self.replay.position_source
        assert "positions for" in self.replay.position_source

    def test_every_pawn_states_the_same_agent_it_stated_before(self):
        """
        The actor -> codename join, pinned to what this capture actually says.

        A codename is *read* from the pawn's archetype path, so this is a
        regression test on the decode itself and not on a lookup table: if the
        archetype resolution, the GUID cache or the channel-to-actor join
        drifts, one of these ten changes and nothing else in the suite would
        notice. Actor 1370 is the reconnect, and its second life states the
        same agent as its first.
        """
        got = {p.actor_id: p.codename for p in self.replay.players}
        assert got == KNOWN_CODENAMES

    def test_the_codenames_name_the_ten_agents(self):
        """And the lookup on top of them, which is what a panel shows."""
        got = {p.actor_id: p.agent for p in self.replay.players}
        assert got == KNOWN_AGENTS
