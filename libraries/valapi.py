"""
Client for Riot's official VALORANT API, as documented in docs/valorant-api.md.

Stdlib only, because the project declares no runtime dependencies: urllib does
what `requests` would, and envfile.py already stands in for python-dotenv.

Two things here are load-bearing rather than decorative.

The User-Agent header
---------------------
api.riotgames.com sits behind Cloudflare, which rejects urllib's default
`Python-urllib/3.x` with a 403 and the body `error code: 1010` -- *before* the
key is ever read, so a perfectly good key looks expired.  Every request
therefore carries an explicit User-Agent, and `_hint` recognises 1010 so the
failure is never blamed on the key.

Shards are not clusters
-----------------------
The `val-*` APIs are addressed by shard host (ap, br, eu, kr, latam, na);
account-v1 is addressed by cluster host (americas, asia, europe).  Crossing the
two returns 403 in both directions -- not 404, and not a redirect -- so the
endpoint helpers below default to the right host class for their path.

What a personal development key can actually reach: account-v1 (except
/accounts/me), val-status-v1, val-content-v1 and val-ranked-v1.  The whole of
val-match-v1 is 403 until a production key is granted, including
/matches/{matchId}.  `platform_data` is the discriminator: if it returns 200
while something else 403s, the key and the User-Agent are fine and the 403 is an
access grant.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import envfile

KEY_VAR = "RIOT_API"
USER_AGENT = "val-replay-analyzer/0.1"

# Shard hosts serve val-*; cluster hosts serve account-v1.  esports is a
# seventh routing value, for val-match-v1 and val-content-v1 only.
SHARDS = ("ap", "br", "eu", "kr", "latam", "na")
CLUSTERS = ("americas", "asia", "europe")
DEFAULT_SHARD = "ap"
DEFAULT_CLUSTER = "americas"
DEFAULT_LOCALE = "en-US"

TIMEOUT_S = 15
RETRIES = 3
BACKOFF_S = 1.5

# 429 and the 5xx family are Riot's own back-pressure; everything else is a
# request that will fail identically however many times it is sent.
RETRYABLE = frozenset({429, 500, 502, 503, 504})

# Paths a personal development key cannot reach at all.
GATED_PREFIXES = ("/val/match/", "/val/console/")

# Enough of an error body to carry Riot's errorCode, not enough to dump a page.
_BODY_PEEK = 400

_STATUS_UNAUTHORIZED = 401
_STATUS_FORBIDDEN = 403
_STATUS_NOT_FOUND = 404
_STATUS_RATE_LIMITED = 429


class RiotApiError(RuntimeError):
    """Anything that stopped a request from returning JSON."""


class MissingKeyError(RiotApiError):
    """No API key in the environment or in the nearest .env."""


class RiotHttpError(RiotApiError):
    """
    One non-2xx response, classified by the documented error table.

    `hint` is the part worth reading: the same 403 means an expired key, a
    wrong host class, the Cloudflare block or the production gate, and the
    difference is nowhere in the status line.
    """

    def __init__(
        self,
        status: int,
        reason: str,
        url: str,
        body: str = "",
        retry_after: int | None = None,
    ) -> None:
        self.status = status
        self.reason = reason
        self.url = url
        self.body = body
        self.retry_after = retry_after
        self.hint = _hint(status, url, body, retry_after)
        detail = f": {body}" if body else ""
        super().__init__(f"{status} {reason} for {url}{detail}\n  hint: {self.hint}")

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE


def _hint(status: int, url: str, body: str, retry_after: int | None) -> str:
    """Which of the several meanings of this status applies here."""
    split = urllib.parse.urlsplit(url)
    path = split.path
    host = split.netloc.split(".", 1)[0]

    if "error code: 1010" in body:
        return (
            "Cloudflare rejected the User-Agent before the key was read; this is "
            "not an expired key. Send any non-urllib User-Agent."
        )
    if status == _STATUS_UNAUTHORIZED:
        return (
            f"no X-Riot-Token header, or {KEY_VAR} is not a real key "
            "(a syntactically valid but fake key also 401s)"
        )
    if status == _STATUS_FORBIDDEN:
        return _forbidden_hint(path, host)
    if status == _STATUS_NOT_FOUND:
        return (
            "unknown match, act or PUUID -- or a val-* resource that lives on a "
            "shard other than the host used"
        )
    if status == _STATUS_RATE_LIMITED:
        wait = f" Retry after {retry_after}s." if retry_after else ""
        return f"rate limited; a development key allows 20/s and 100/2min.{wait}"
    return "retryable server-side failure" if status in RETRYABLE else "not retryable"


def _forbidden_hint(path: str, host: str) -> str:
    """A 403 has four distinct causes; name the likely one for this path."""
    if path.startswith(GATED_PREFIXES):
        return (
            "val-match-v1 and the console APIs need a production key; a personal "
            "development key 403s on every one of them, before the match id is "
            "even looked at. Call key_state() to confirm the key itself is live."
        )
    if path.startswith("/val/") and host in CLUSTERS:
        return f"val-* paths are addressed by a shard host, not the {host} cluster"
    if path.startswith("/riot/") and host in SHARDS:
        return f"account-v1 is addressed by a cluster host, not the {host} shard"
    return (
        f"key expired (development keys last 24 hours), or {path} is not granted "
        "to it; key_state() distinguishes the two"
    )


def api_key(key: str | None = None) -> str:
    """The explicit key, else RIOT_API from the environment or nearest .env."""
    resolved = key or envfile.get(KEY_VAR)
    if not resolved:
        msg = (
            f"no {KEY_VAR} in the environment or in the nearest .env; personal "
            "development keys come from https://developer.riotgames.com and "
            "expire every 24 hours"
        )
        raise MissingKeyError(msg)
    return resolved


def headers(key: str | None = None) -> dict[str, str]:
    """The two headers every request in this surface needs."""
    return {"X-Riot-Token": api_key(key), "User-Agent": USER_AGENT}


def url_for(host: str, path: str, params: dict | None = None) -> str:
    """Full URL for a routing value and path; the key never goes in the query."""
    url = f"https://{host}.api.riotgames.com{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    if not url.startswith("https://"):
        msg = f"refusing non-https url: {url!r}"
        raise ValueError(msg)
    return url


def http_error(exc: urllib.error.HTTPError, url: str) -> RiotHttpError:
    """Turn urllib's exception into one carrying the documented diagnosis."""
    try:
        body = exc.read()[:_BODY_PEEK].decode("utf-8", "replace").strip()
    except OSError:
        body = ""
    try:
        retry_after = int(exc.headers.get("Retry-After", "") or 0) or None
    except (AttributeError, TypeError, ValueError):
        retry_after = None
    return RiotHttpError(exc.code, str(exc.reason), url, body, retry_after)


def get(
    host: str,
    path: str,
    params: dict | None = None,
    key: str | None = None,
) -> dict:
    """GET one endpoint and decode it, retrying only what Riot says to retry."""
    url = url_for(host, path, params)
    request = urllib.request.Request(url, headers=headers(key))  # noqa: S310
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
                return json.load(response)
        except urllib.error.HTTPError as exc:
            error = http_error(exc, url)
            if not error.retryable or attempt + 1 >= RETRIES:
                raise error from exc
            time.sleep(error.retry_after or BACKOFF_S * (attempt + 1))
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 < RETRIES:
                time.sleep(BACKOFF_S * (attempt + 1))
    msg = f"{url} failed after {RETRIES} attempts: {last}"
    raise OSError(msg)


# --- endpoints -------------------------------------------------------------
# Each helper picks the host class its own path requires, so a shard/cluster
# mix-up cannot be made by a caller who goes through them.


def contents(
    shard: str = DEFAULT_SHARD,
    locale: str = DEFAULT_LOCALE,
    key: str | None = None,
) -> dict:
    """
    val-content-v1: the static catalogue of agents, maps, modes and acts.

    Always send a locale.  Without one the response carries all 18 translations
    and measures 14.3 MB, against 1.7 MB with `locale=en-US`.
    """
    params = {"locale": locale} if locale else None
    return get(shard, "/val/content/v1/contents", params, key)


def platform_data(shard: str = DEFAULT_SHARD, key: str | None = None) -> dict:
    """val-status-v1: shard health, and the cheapest proof that a key works."""
    return get(shard, "/val/status/v1/platform-data", None, key)


def match(shard: str, match_id: str, key: str | None = None) -> dict:
    """
    val-match-v1: one full MatchDto.

    403 on a personal development key.  Kept because a .vrf names its own match
    id, so this is the exact call to make the day a production key is granted.
    """
    return get(shard, f"/val/match/v1/matches/{match_id}", None, key)


def matchlist(shard: str, puuid: str, key: str | None = None) -> dict:
    """val-match-v1: one player's match history. Production-gated as well."""
    return get(shard, f"/val/match/v1/matchlists/by-puuid/{puuid}", None, key)


def account_by_riot_id(
    game_name: str,
    tag_line: str,
    cluster: str = DEFAULT_CLUSTER,
    key: str | None = None,
) -> dict:
    """account-v1: Name#TAG to an AccountDto. Cluster host, not a shard."""
    name = urllib.parse.quote(game_name, safe="")
    tag = urllib.parse.quote(tag_line, safe="")
    return get(cluster, f"/riot/account/v1/accounts/by-riot-id/{name}/{tag}", None, key)


def active_shard(
    puuid: str,
    cluster: str = DEFAULT_CLUSTER,
    key: str | None = None,
) -> dict:
    """
    account-v1: which val-* shard a player is on.

    The correct way to pick a host; a Riot ID tag line is cosmetic and encodes
    no region.  The response is exactly {puuid, game, activeShard} -- there is
    no `region` field, whatever the portal documents.
    """
    path = f"/riot/account/v1/active-shards/by-game/val/by-puuid/{puuid}"
    return get(cluster, path, None, key)


def key_state(shard: str = DEFAULT_SHARD, key: str | None = None) -> tuple[bool, str]:
    """
    Whether the key is live, and why not when it is not.

    This is the discriminator the documentation prescribes: val-status-v1 takes
    no identifier of any kind, so a 200 from it means the key, the host and the
    User-Agent are all good and any other 403 is an access grant, not the key.
    """
    try:
        data = platform_data(shard, key)
    except (RiotApiError, OSError) as exc:
        return False, str(exc)
    return True, f"key is live; {shard} reports id {data.get('id', '?')}"
