"""
Tests for the Riot API client's request shape and error classification.

Nothing here opens a socket.  valapi keeps URL building, header building and
diagnosis in pure functions and confines urlopen to `get`, so the half that is
easy to get wrong is exercised from synthetic HTTPError objects.

The two behaviours worth pinning are the ones docs/valorant-api.md records as
having cost real time: a request without an explicit User-Agent is 403ed by
Cloudflare before the key is read, and every val-match-v1 path 403s on a
personal development key, which looks identical to an expired key unless
something says otherwise.
"""

from __future__ import annotations

import io
import unittest
import urllib.error
from email.message import Message

import pytest

import valapi

KEY = "RGAPI-00000000-0000-0000-0000-000000000000"
MATCH_PATH = "/val/match/v1/matches/039f3991-5472-4119-bed2-838da0935f60"


def http_error(status, url, body=b"", retry_after=None):
    """An HTTPError shaped the way urllib hands one to `get`."""
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError(url, status, "Forbidden", headers, io.BytesIO(body))


def classify(status, url, body=b"", retry_after=None):
    return valapi.http_error(http_error(status, url, body, retry_after), url)


class UrlBuilding(unittest.TestCase):
    def test_shard_host_and_path(self):
        url = valapi.url_for("ap", "/val/status/v1/platform-data")
        assert url == "https://ap.api.riotgames.com/val/status/v1/platform-data"

    def test_params_are_encoded(self):
        url = valapi.url_for("ap", "/val/content/v1/contents", {"locale": "en-US"})
        assert url.endswith("/val/content/v1/contents?locale=en-US")

    def test_the_key_never_reaches_the_query_string(self):
        """The ?api_key= form works but leaks into logs, proxies and history."""
        url = valapi.url_for("ap", "/val/content/v1/contents", {"locale": "en-US"})
        assert "api_key" not in url
        assert KEY not in url


class Headers(unittest.TestCase):
    def test_key_travels_in_the_header(self):
        assert valapi.headers(KEY)["X-Riot-Token"] == KEY

    def test_a_user_agent_is_always_sent(self):
        """Cloudflare 403s urllib's default before the key is ever checked."""
        agent = valapi.headers(KEY)["User-Agent"]
        assert agent
        assert not agent.startswith("Python-urllib")

    def test_a_missing_key_is_not_an_anonymous_request(self):
        original = valapi.envfile.get
        valapi.envfile.get = lambda *_a, **_k: None
        try:
            with pytest.raises(valapi.MissingKeyError):
                valapi.headers()
        finally:
            valapi.envfile.get = original


class ErrorClassification(unittest.TestCase):
    def test_cloudflare_block_is_not_blamed_on_the_key(self):
        url = valapi.url_for("ap", "/val/status/v1/platform-data")
        error = classify(403, url, b"error code: 1010")
        assert "User-Agent" in error.hint
        assert "not an expired key" in error.hint

    def test_val_match_403_names_the_production_gate(self):
        error = classify(403, valapi.url_for("ap", MATCH_PATH))
        assert "production key" in error.hint
        assert not error.retryable

    def test_console_paths_are_gated_too(self):
        url = valapi.url_for("ap", "/val/console/ranked/v1/leaderboards/by-act/x")
        assert "production key" in classify(403, url).hint

    def test_val_path_on_a_cluster_host_names_the_host_class(self):
        url = valapi.url_for("americas", "/val/content/v1/contents")
        assert "shard host" in classify(403, url).hint

    def test_account_path_on_a_shard_host_names_the_host_class(self):
        url = valapi.url_for("ap", "/riot/account/v1/accounts/by-riot-id/N/T")
        assert "cluster host" in classify(403, url).hint

    def test_plain_403_offers_the_discriminator(self):
        url = valapi.url_for("ap", "/val/ranked/v1/leaderboards/by-act/x")
        assert "key_state()" in classify(403, url).hint

    def test_401_covers_a_fake_but_well_formed_key(self):
        url = valapi.url_for("ap", "/val/status/v1/platform-data")
        assert "not a real key" in classify(401, url).hint

    def test_429_is_retryable_and_carries_retry_after(self):
        url = valapi.url_for("ap", "/val/status/v1/platform-data")
        error = classify(429, url, retry_after=42)
        assert error.retryable
        assert error.retry_after == 42

    def test_server_errors_are_retryable_and_client_errors_are_not(self):
        url = valapi.url_for("ap", "/val/status/v1/platform-data")
        assert classify(503, url).retryable
        assert not classify(404, url).retryable

    def test_the_body_is_kept_for_the_message(self):
        url = valapi.url_for("ap", MATCH_PATH)
        error = classify(403, url, b'{"status":{"message":"Forbidden"}}')
        assert "Forbidden" in error.body
        assert url in str(error)


class Routing(unittest.TestCase):
    def test_shards_and_clusters_are_disjoint(self):
        """Crossing them is a 403 in both directions, so nothing may overlap."""
        assert not set(valapi.SHARDS) & set(valapi.CLUSTERS)

    def test_defaults_are_of_the_right_host_class(self):
        assert valapi.DEFAULT_SHARD in valapi.SHARDS
        assert valapi.DEFAULT_CLUSTER in valapi.CLUSTERS

    def test_key_state_reports_a_missing_key_without_a_request(self):
        original = valapi.envfile.get
        valapi.envfile.get = lambda *_a, **_k: None
        try:
            live, why = valapi.key_state()
        finally:
            valapi.envfile.get = original
        assert not live
        assert valapi.KEY_VAR in why


if __name__ == "__main__":
    unittest.main()
