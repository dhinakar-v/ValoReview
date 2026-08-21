"""
Tests for the asset downloader's planning layer.

Nothing here opens a socket.  fetch_assets keeps every naming, filtering and
manifest decision in the pure plan_* functions and confines urllib to _fetch,
so the whole interesting half is exercised from small inline fixtures.  A test
that needed the real API would fail on a new Riot release rather than on a bug,
which is the wrong thing to pin.
"""

from __future__ import annotations

import unittest

import pytest

from fetch_assets import (
    CODENAMES,
    _check_url,
    plan_agents,
    plan_maps,
    plan_roles,
    safe_name,
)

ASCENT = {
    "uuid": "7eaecc1b-4337-bbf6-6ab9-04b8f06b3319",
    "displayName": "Ascent",
    "displayIcon": "https://media.valorant-api.com/maps/asc/displayicon.png",
    "splash": "https://media.valorant-api.com/maps/asc/splash.png",
    "listViewIcon": "https://media.valorant-api.com/maps/asc/listviewicon.png",
    "mapUrl": "/Game/Maps/Ascent/Ascent",
    "assetPath": "ShooterGame/Content/Maps/Ascent/Ascent",
    "xMultiplier": 7e-05,
    "yMultiplier": -7e-05,
    "xScalarToAdd": 0.813895,
    "yScalarToAdd": 0.573242,
    "callouts": [{"regionName": "A Site"}],
}

# The Range has no radar image at all; it is the shape every placeholder map
# takes, and none of them should reach the download list.
RANGE = {
    "uuid": "ee613ee9-28b7-4beb-9666-08db13bb2244",
    "displayName": "The Range",
    "displayIcon": None,
    "splash": "https://media.valorant-api.com/maps/rng/splash.png",
    "listViewIcon": None,
    "mapUrl": "/Game/Maps/Poveglia/Range",
    "xMultiplier": 0.0,
    "yMultiplier": 0.0,
    "xScalarToAdd": 0.0,
    "yScalarToAdd": 0.0,
    "callouts": None,
}

DUELIST = {
    "uuid": "dbe8757e-9e92-4ed4-b39f-9dfc589691d4",
    "displayName": "Duelist",
    "displayIcon": "https://media.valorant-api.com/roles/duelist.png",
}

JETT = {
    "uuid": "add6443a-41bd-e414-f6ad-e58d267f4e95",
    "displayName": "Jett",
    "developerName": "Wushu",
    "displayIcon": "https://media.valorant-api.com/agents/jett/displayicon.png",
    "fullPortrait": "https://media.valorant-api.com/agents/jett/fullportrait.png",
    "killfeedPortrait": "https://media.valorant-api.com/agents/jett/killfeed.png",
    "role": DUELIST,
    "abilities": [
        {
            "slot": "Ability1",
            "displayName": "Updraft",
            "displayIcon": "https://media.valorant-api.com/a/jett/ab1.png",
        },
        {
            "slot": "Ultimate",
            "displayName": "Blade Storm",
            "displayIcon": "https://media.valorant-api.com/a/jett/ult.png",
        },
        # Passive slots usually carry no icon, and an ability with no icon is
        # not art to cache.
        {"slot": "Passive", "displayName": "Drift", "displayIcon": None},
    ],
}

KAYO = {
    "uuid": "601dbbe7-43ce-be57-2a40-4abd24953621",
    "displayName": "KAY/O",
    "displayIcon": "https://media.valorant-api.com/agents/kayo/displayicon.png",
    "fullPortrait": None,
    "killfeedPortrait": None,
    "role": {**DUELIST, "displayName": "Initiator"},
    "abilities": [],
}


class SafeNameTests(unittest.TestCase):
    def test_slash_in_an_agent_name_becomes_an_underscore(self):
        assert safe_name("KAY/O") == "KAY_O"

    def test_ordinary_names_are_untouched(self):
        assert safe_name("Ascent") == "Ascent"
        assert safe_name("Basic Training") == "Basic_Training"

    def test_runs_are_collapsed_and_edges_trimmed(self):
        assert safe_name("  a // b  ") == "a_b"

    def test_a_name_with_nothing_usable_still_yields_a_folder(self):
        assert safe_name("///") == "unnamed"


class PlanMapsTests(unittest.TestCase):
    def test_a_map_without_a_radar_image_is_dropped_entirely(self):
        downloads, manifest, _ = plan_maps([ASCENT, RANGE])

        assert "The Range" not in manifest
        assert all("The_Range" not in d.path for d in downloads)

    def test_three_files_land_under_the_public_map_name(self):
        downloads, _, _ = plan_maps([ASCENT])

        assert [d.path for d in downloads] == [
            "maps/Ascent/minimap.png",
            "maps/Ascent/splash.png",
            "maps/Ascent/listview.png",
        ]

    def test_minimap_is_the_display_icon_not_the_splash(self):
        downloads, _, _ = plan_maps([ASCENT])
        by_path = {d.path: d.url for d in downloads}

        assert by_path["maps/Ascent/minimap.png"] == ASCENT["displayIcon"]

    def test_a_missing_image_field_drops_only_that_file(self):
        entry = {**ASCENT, "splash": None}
        downloads, manifest, _ = plan_maps([entry])

        assert [d.path for d in downloads] == [
            "maps/Ascent/minimap.png",
            "maps/Ascent/listview.png",
        ]
        assert "splash.png" not in manifest["Ascent"]["files"]

    def test_the_coordinate_transform_is_carried_into_the_manifest(self):
        _, manifest, _ = plan_maps([ASCENT])

        assert manifest["Ascent"]["transform"] == {
            "x_multiplier": 7e-05,
            "y_multiplier": -7e-05,
            "x_scalar_to_add": 0.813895,
            "y_scalar_to_add": 0.573242,
        }

    def test_the_internal_codename_is_recovered_from_the_viewer_table(self):
        bind = {**ASCENT, "displayName": "Bind"}
        _, manifest, _ = plan_maps([bind])

        assert manifest["Bind"]["codename"] == "Duality"
        assert CODENAMES["Bind"] == "Duality"

    def test_a_map_the_viewer_cannot_name_is_reported_not_dropped(self):
        stranger = {**ASCENT, "displayName": "Piazza"}
        downloads, manifest, warnings = plan_maps([stranger])

        assert manifest["Piazza"]["codename"] is None
        assert any("Piazza" in w for w in warnings)
        assert len(downloads) == 3

    def test_a_fully_known_roster_produces_no_warnings(self):
        _, _, warnings = plan_maps([ASCENT])

        assert warnings == []

    def test_maps_come_out_in_name_order(self):
        _, manifest, _ = plan_maps([{**ASCENT, "displayName": "Split"}, ASCENT])

        assert list(manifest) == ["Ascent", "Split"]


class PlanAgentsTests(unittest.TestCase):
    def test_portraits_and_ability_icons_land_under_the_agent_name(self):
        downloads, _ = plan_agents([JETT])

        assert [d.path for d in downloads] == [
            "agents/Jett/icon.png",
            "agents/Jett/portrait.png",
            "agents/Jett/killfeed.png",
            "agents/Jett/abilities/ability1.png",
            "agents/Jett/abilities/ultimate.png",
        ]

    def test_an_ability_with_no_icon_is_dropped(self):
        downloads, manifest = plan_agents([JETT])

        assert "Passive" not in manifest["Jett"]["abilities"]
        assert all("passive" not in d.path for d in downloads)

    def test_the_manifest_keeps_the_developer_name(self):
        """The only join from a pawn archetype path to an agent name."""
        _, manifest = plan_agents([JETT])

        assert manifest["Jett"]["developer_name"] == "Wushu"

    def test_an_agent_with_no_developer_name_records_none(self):
        _, manifest = plan_agents([KAYO])

        assert manifest["KAY/O"]["developer_name"] is None

    def test_the_manifest_keeps_the_role_and_the_ability_names(self):
        _, manifest = plan_agents([JETT])

        assert manifest["Jett"]["role"] == "Duelist"
        assert manifest["Jett"]["abilities"]["Ultimate"] == {
            "display_name": "Blade Storm",
            "file": "agents/Jett/abilities/ultimate.png",
        }

    def test_a_name_needing_sanitising_is_used_for_the_folder(self):
        downloads, manifest = plan_agents([KAYO])

        assert [d.path for d in downloads] == ["agents/KAY_O/icon.png"]
        # The manifest is keyed by the real name; only the path is sanitised.
        assert "KAY/O" in manifest

    def test_agents_come_out_in_name_order(self):
        _, manifest = plan_agents([KAYO, JETT])

        assert list(manifest) == ["Jett", "KAY/O"]


class PlanRolesTests(unittest.TestCase):
    def test_a_role_shared_by_two_agents_is_fetched_once(self):
        twin = {**JETT, "displayName": "Raze"}
        downloads, manifest = plan_roles([JETT, twin])

        assert [d.path for d in downloads] == ["roles/Duelist.png"]
        assert list(manifest) == ["Duelist"]

    def test_distinct_roles_each_get_an_icon(self):
        downloads, _ = plan_roles([JETT, KAYO])

        assert sorted(d.path for d in downloads) == [
            "roles/Duelist.png",
            "roles/Initiator.png",
        ]


class UrlGuardTests(unittest.TestCase):
    """Every planned URL must be https, since _fetch refuses anything else."""

    def test_planned_urls_are_all_https(self):
        planned = (
            plan_maps([ASCENT])[0] + plan_agents([JETT])[0] + plan_roles([JETT])[0]
        )

        assert planned
        for item in planned:
            assert item.url.startswith("https://"), item

    def test_the_guard_rejects_a_file_url(self):
        with pytest.raises(ValueError, match="non-https"):
            _check_url("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
