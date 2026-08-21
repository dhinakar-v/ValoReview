"""
Tests for the content catalogue: two cache shapes, two joins, one fallback.

The fixtures are deliberately tiny but keep the three details that actually
break a join, all of them recorded in docs/valorant-api.md:

  * one map entry has no assetPath at all -- Riot ships a "Null UI Data!"
    placeholder, so 26 of 27 map entries carry the key;
  * the catalogue states agent UUIDs uppercase while replays store them
    lowercase, so a join that does not normalise matches nothing;
  * in the fetch_assets manifest the field that matches a replay's map path is
    `map_url`, not the differently-notated `asset_path` sitting next to it.

Nothing here opens a socket: `refresh` is the only networked function and is
not exercised.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

import valcatalog

ABYSS_PATH = "/Game/Maps/Infinity/Infinity"
ASTRA_UUID = "41fb69c1-4189-7b37-f117-bcaf1e96f1bf"

CONTENT = {
    "version": "release-13.04",
    "maps": [
        {"name": "Abyss", "id": "224B0A95", "assetPath": ABYSS_PATH},
        {"name": "Ascent", "id": "7EAECC1B", "assetPath": "/Game/Maps/Ascent/Ascent"},
        {"name": "Null UI Data!", "id": "00000000"},
    ],
    "characters": [
        {"name": "Astra", "id": ASTRA_UUID.upper()},
        {"name": "Sova", "id": "320B2A48-4D9B-A075-30F1-1F93A9B638FA"},
    ],
    "acts": [{"name": "ACT V", "id": "8102CD81", "isActive": True, "type": "act"}],
}

MANIFEST = {
    "version": {"branch": "release-13.04", "version": "13.04.00.5304478"},
    "maps": {
        "Abyss": {
            "uuid": "224b0a95",
            "codename": "Infinity",
            "map_url": ABYSS_PATH,
            "asset_path": "ShooterGame/Content/Maps/Infinity/Infinity_PrimaryAsset",
        },
        "The Range": {"uuid": "ee613ee9", "map_url": "/Game/Maps/Poveglia/Range"},
    },
    "agents": {
        "Astra": {"uuid": ASTRA_UUID, "role": "Controller"},
        "Sova": {"uuid": "320b2a48-4d9b-a075-30f1-1f93a9b638fa", "role": "Initiator"},
    },
}


class FromContents(unittest.TestCase):
    def test_map_joins_on_asset_path(self):
        assert valcatalog.from_contents(CONTENT).map_name(ABYSS_PATH) == "Abyss"

    def test_an_entry_without_an_asset_path_is_dropped(self):
        """Riot's placeholder map has no assetPath; indexing it would raise."""
        catalog = valcatalog.from_contents(CONTENT)
        assert len(catalog.maps) == 2
        assert "Null UI Data!" not in catalog.maps.values()

    def test_agent_uuids_join_across_a_case_difference(self):
        """The catalogue answers uppercase, the replay asks lowercase."""
        catalog = valcatalog.from_contents(CONTENT)
        assert catalog.agent_name(ASTRA_UUID) == "Astra"
        assert catalog.agent_name(ASTRA_UUID.upper()) == "Astra"

    def test_version_and_source_are_carried(self):
        catalog = valcatalog.from_contents(CONTENT, "cache.json")
        assert catalog.version == "release-13.04"
        assert catalog.source == valcatalog.SOURCE_CONTENT
        assert "cache.json" in catalog.described


class FromManifest(unittest.TestCase):
    def test_map_joins_on_map_url_not_asset_path(self):
        catalog = valcatalog.from_manifest(MANIFEST)
        assert catalog.map_name(ABYSS_PATH) == "Abyss"
        asset_path = MANIFEST["maps"]["Abyss"]["asset_path"]
        assert catalog.map_name(asset_path) is None

    def test_agents_invert_the_name_keyed_manifest(self):
        assert valcatalog.from_manifest(MANIFEST).agent_name(ASTRA_UUID) == "Astra"

    def test_version_comes_from_the_branch(self):
        assert valcatalog.from_manifest(MANIFEST).version == "release-13.04"


class ShapeSniffing(unittest.TestCase):
    def test_a_content_response_is_recognised(self):
        assert valcatalog.from_document(CONTENT).source == valcatalog.SOURCE_CONTENT

    def test_a_manifest_is_recognised(self):
        assert valcatalog.from_document(MANIFEST).source == valcatalog.SOURCE_MANIFEST

    def test_anything_else_is_rejected(self):
        with pytest.raises(ValueError, match="neither"):
            valcatalog.from_document({"hello": "world"}, "odd.json")


class Loading(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.assets = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name, doc):
        (self.assets / name).write_text(json.dumps(doc), encoding="utf-8")

    def test_a_refreshed_cache_wins_over_the_manifest(self):
        self._write("content-en-US.json", CONTENT)
        self._write("manifest.json", MANIFEST)
        assert valcatalog.load(assets=self.assets).source == valcatalog.SOURCE_CONTENT

    def test_the_manifest_is_used_when_no_cache_was_fetched(self):
        self._write("manifest.json", MANIFEST)
        assert valcatalog.load(assets=self.assets).source == valcatalog.SOURCE_MANIFEST

    def test_no_cache_at_all_is_an_empty_catalogue_not_an_error(self):
        """A clean checkout has neither file; the viewer must still run."""
        catalog = valcatalog.load(assets=self.assets)
        assert catalog.empty
        assert catalog.map_name(ABYSS_PATH) is None
        assert catalog.agent_name(ASTRA_UUID) is None

    def test_an_explicit_path_is_used_verbatim(self):
        self._write("manifest.json", MANIFEST)
        self._write("elsewhere.json", CONTENT)
        catalog = valcatalog.load(self.assets / "elsewhere.json", assets=self.assets)
        assert catalog.source == valcatalog.SOURCE_CONTENT

    def test_an_explicit_path_that_is_missing_raises(self):
        """Silently ignoring a --catalog the user named would hide a typo."""
        with pytest.raises(OSError, match="No such file"):
            valcatalog.load(self.assets / "absent.json", assets=self.assets)

    def test_the_search_order_is_reported_for_the_cli(self):
        order = valcatalog.candidates(None, "en-US", self.assets)
        assert [p.name for p in order] == ["content-en-US.json", "manifest.json"]


if __name__ == "__main__":
    unittest.main()
