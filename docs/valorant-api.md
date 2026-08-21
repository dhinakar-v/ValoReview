# VALORANT Riot API — Endpoint and DTO Reference

**Date:** 2026-08-21
**Source:** <https://developer.riotgames.com/apis> (val-* and account-v1 sections)
**Live-tested:** 2026-08-21 against a personal dev key — see
[Verification status](#verification-status) for exactly which claims were confirmed,
corrected, or left untested.
**Key:** `RIOT_API` in `.env` (gitignored). Personal development keys **expire every 24
hours** — regenerate at the portal.

The developer portal renders its endpoint tables in JavaScript, so it cannot be read
without a browser session. This file transcribes the whole VALORANT surface — six APIs
plus `account-v1` — so requests can be written without going back to the portal. See
[Caveats](#caveats-and-open-questions) for what is transcribed vs. verified.

Companion to `vrf-decoding-findings.md`: section
[Using this with `.vrf` replays](#using-this-with-vrf-replays) covers how the API lines up
with the offline decoder in `libraries/vrfnet/` and the viewer in `libraries/vrfview/`.

---

## Contents

- [Authentication and rate limits](#authentication-and-rate-limits)
- [Routing: shards vs. clusters](#routing-shards-vs-clusters)
- [account-v1](#account-v1)
- [val-match-v1](#val-match-v1)
- [val-ranked-v1](#val-ranked-v1)
- [val-content-v1](#val-content-v1)
- [val-status-v1](#val-status-v1)
- [val-console-match-v1](#val-console-match-v1)
- [val-console-ranked-v1](#val-console-ranked-v1)
- [DTO reference](#dto-reference)
- [Enumerations](#enumerations)
- [Recipes](#recipes)
- [Using this with `.vrf` replays](#using-this-with-vrf-replays)
- [Caveats and open questions](#caveats-and-open-questions)
- [Verification status](#verification-status)

---

## Authentication and rate limits

Every request carries the key. Two equivalent forms; prefer the header, because the query
form leaks the key into logs, proxies and shell history.

    X-Riot-Token: RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx     # preferred
    ?api_key=RGAPI-xxxx                                          # works, avoid

All VALORANT endpoints are `GET`. There are no request bodies anywhere in this surface.

### You must send a User-Agent

**Verified 2026-08-21.** `api.riotgames.com` sits behind Cloudflare, which rejects
Python's default `User-Agent: Python-urllib/3.x` with an HTML-free `403` and the body
`error code: 1010`. This happens *before* the key is ever checked, so a perfectly valid
key looks expired.

Any other User-Agent passes — including an empty string. Measured on the same valid key
against `/val/status/v1/platform-data`:

| `User-Agent` sent | Result |
|-------------------|--------|
| *(urllib default, `Python-urllib/3.11`)* | **403 `error code: 1010`** |
| `""` (empty) | 200 |
| `curl/8.4.0` | 200 |
| `val-replay-analyzer/0.1` | 200 |
| `python-requests/2.31.0` | 200 |

So every `urllib` request in this document sets one explicitly. `curl` is unaffected — it
sends its own. If a request works in `curl` and 403s in Python with the same key, this is
why; check for `error code: 1010` in the body before blaming the key.

### Development key limits

| Limit | Window |
|-------|--------|
| 20 requests | 1 second |
| 100 requests | 2 minutes |

Two independent limit classes apply simultaneously:

- **App rate limit** — the key's global budget, shared across every endpoint.
- **Method rate limit** — a per-endpoint budget. Enforced per key *and* per region, so the
  same method against `ap.` and `eu.` draws on separate method buckets.

### Rate-limit response headers

Read these instead of guessing at a sleep interval.

| Header | Meaning |
|--------|---------|
| `X-App-Rate-Limit` | The key's configured limits, `count:seconds` pairs, comma-separated (e.g. `20:1,100:120`) |
| `X-App-Rate-Limit-Count` | Current usage against each of those buckets |
| `X-Method-Rate-Limit` | Same format, for this specific method |
| `X-Method-Rate-Limit-Count` | Current usage against the method buckets |
| `X-Rate-Limit-Type` | On a 429: which limit tripped — `application`, `method`, or `service` |
| `Retry-After` | On a 429: seconds to wait before retrying |

A `service` type on a 429 is Riot's own back-pressure, not your key; it carries no
`X-App-Rate-Limit` headers and is retryable.

### Standard error responses

Every endpoint in this document returns the same error set. It is stated once here and
not repeated per endpoint.

| Status | Reason | Notes for this API surface |
|--------|--------|----------------------------|
| 400 | Bad request | Malformed PUUID, bad enum value, `size` outside 1–200 |
| 401 | Unauthorized | Header missing entirely, **or the key is syntactically fine but not a real key**. Verified both cases 2026-08-21. |
| 403 | Forbidden | Key expired (dev keys last 24 h); **endpoint not granted to your key** (this is what gates `val-match-v1` — see [access matrix](#what-a-personal-dev-key-can-actually-reach)); a `val-*` path sent to a cluster host; or the Cloudflare User-Agent block above |
| 404 | Data not found | Unknown match/act/PUUID; also an unplayed queue on `recent-matches` |
| 405 | Method not allowed | |
| 415 | Unsupported media type | |
| 429 | Rate limit exceeded | See `X-Rate-Limit-Type` and `Retry-After` |
| 500 | Internal server error | |
| 502 | Bad gateway | |
| 503 | Service unavailable | Shard in maintenance — cross-check `val-status-v1` |
| 504 | Gateway timeout | |

Treat 429, 500, 502, 503 and 504 as retryable with backoff; 400, 401, 403, 404, 405 and
415 are not.

---

## Routing: shards vs. clusters

This is the single most common mistake against the VALORANT API. **The `val-*` APIs are
addressed by shard host. They are not addressed by the `americas`/`asia`/`europe` cluster
hosts** used by `account-v1` and by League's `match-v5`. Sending a `val-*` path to
`americas.api.riotgames.com` returns **403** — not 404, and not a redirect. Verified
2026-08-21 against all three cluster hosts; the reverse (an `account-v1` path on a shard
host) also 403s.

| Host | Serves |
|------|--------|
| `ap.api.riotgames.com` | `val-*` — Asia-Pacific shard |
| `br.api.riotgames.com` | `val-*` — Brazil shard |
| `eu.api.riotgames.com` | `val-*` — Europe shard |
| `kr.api.riotgames.com` | `val-*` — Korea shard |
| `latam.api.riotgames.com` | `val-*` — Latin America shard |
| `na.api.riotgames.com` | `val-*` — North America shard |
| `esports.api.riotgames.com` | `val-match-v1`, `val-content-v1` — esports routing value |
| `americas.api.riotgames.com` | `account-v1` |
| `asia.api.riotgames.com` | `account-v1` |
| `europe.api.riotgames.com` | `account-v1` |

`account-v1` is global: any account resolves from any of its three clusters, so pick the
nearest one. The `val-*` shards are not global — a match played on `ap` is only readable
from `ap`.

### Which shards each API serves

| API | AP | BR | EU | KR | LATAM | NA | ESPORTS |
|-----|:--:|:--:|:--:|:--:|:-----:|:--:|:-------:|
| `val-match-v1` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `val-content-v1` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `val-ranked-v1` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `val-status-v1` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `val-console-match-v1` | ✓ | ✓ | ✓ | — | ✓ | ✓ | — |
| `val-console-ranked-v1` | ✓ | — | ✓ | — | — | ✓ | — |

Console has no KR shard, and console leaderboards exist only on AP, EU and NA.

### Finding a player's shard

Do not guess from the Riot ID tag line — it is cosmetic and does not encode a region. Ask
`account-v1`:

    GET https://americas.api.riotgames.com/riot/account/v1/active-shards/by-game/val/by-puuid/{puuid}

The returned `activeShard` is the host prefix to use for every subsequent `val-*` call.
After the fact, `MatchInfoDto.region` on a match you already have tells you the same thing.

---

## account-v1

Cross-game. Resolves Riot IDs to PUUIDs and tells you which VALORANT shard a player is on.
Hosts: `americas`, `asia`, `europe` (any works for any account). All responses share the
[standard error set](#standard-error-responses).

The portal lists each endpoint twice — once for the live routes above and once for an
`ESPORTS` routing value with an identical contract. Only the host differs; the duplicate
entries are folded together below.

### GET `/riot/account/v1/accounts/by-puuid/{puuid}`

Get account by PUUID.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `puuid` | path | yes | string | Encrypted PUUID, exactly 78 characters |

Response: [`AccountDto`](#accountdto)

### GET `/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}`

Get account by Riot ID. This is the entry point for almost every workflow: a human gives
you `Name#TAG`, you get back a PUUID.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `gameName` | path | yes | string | The part before the `#`; URL-encode spaces |
| `tagLine` | path | yes | string | The part after the `#`, without the `#` |

Response: [`AccountDto`](#accountdto)

### GET `/riot/account/v1/accounts/me`

Get the account belonging to an access token.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `Authorization` | header | yes | string | `Bearer <RSO access token>` |

**This endpoint does not take the dev key.** It requires a Riot Sign-On access token from
an OAuth flow. **Verified 2026-08-21:** with only `X-Riot-Token` set it returns **403**,
not the 401 the portal implies.

Response: [`AccountDto`](#accountdto)

### GET `/riot/account/v1/active-shards/by-game/{game}/by-puuid/{puuid}`

Get the active shard for a player. The correct way to pick a `val-*` host.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `game` | path | yes | string | `val`, `lor` or `2xko`. **Verified 2026-08-21** -- the API's own 400 message reads `must be one of [val,lor,2xko]`; the portal omits `2xko`. |
| `puuid` | path | yes | string | 78 characters |

Response: [`ActiveShardDto`](#activesharddto)

### GET `/riot/account/v1/region/by-game/{game}/by-puuid/{puuid}`

Get active region. Listed here for completeness — it covers `lol` and `tft` only, **not**
VALORANT. Use `active-shards` above for `val`.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `game` | path | yes | string | `lol` or `tft` |
| `puuid` | path | yes | string | 78 characters |

Response: [`AccountRegionDto`](#accountregiondto)

---

## val-match-v1

PC match history and match detail. The API this project cares about most — see the
[replay tie-in](#using-this-with-vrf-replays). Shards: AP, BR, ESPORTS, EU, KR, LATAM, NA.

> ### ⛔ Verified 2026-08-21: the whole of `val-match-v1` is 403 on a personal dev key
>
> **All three endpoints below return `403 Forbidden`** with a key that simultaneously
> returns 200 from `val-status-v1`, `val-content-v1`, `val-ranked-v1` and `account-v1`.
> That includes `/matches/{matchId}` — which earlier revisions of this document assumed
> worked. It does not.
>
> The 403 is returned **before** any parameter validation: an unknown match id, a
> malformed match id, and a bogus queue name all 403 rather than 404 or 400. So nothing in
> this section's error behaviour, and none of the `MatchDto` field tables, could be
> checked against a live response. Treat everything below as **transcribed, not
> verified** — see [Verification status](#verification-status).
>
> Getting past this needs a **production key** (an approved application at
> <https://developer.riotgames.com>), not a fresh personal key.

### GET `/val/match/v1/matches/{matchId}`

Get a match by ID. Returns the complete match: metadata, all players, both teams, and
every round with per-round kills, damage, economy and ability usage.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `matchId` | path | yes | string | Match UUID |

Response: [`MatchDto`](#matchdto) — this is the largest object in the surface; the full
field graph is in the [DTO reference](#matchdto).

The match must live on the shard you query — a match played on `ap` is not readable from
`na`. **Unverified:** the portal calls this a 404, but with a dev key every request here
403s first, so the 404-on-wrong-shard behaviour could not be confirmed. Tested against all
seven routing values with a local capture's id; all seven returned 403.

### GET `/val/match/v1/matchlists/by-puuid/{puuid}`

Get the match list for games played by a PUUID.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `puuid` | path | yes | string | 78 characters |

Response: [`MatchlistDto`](#matchlistdto)

Returns identifiers and timestamps only — no stats. Fan out to
`/val/match/v1/matches/{matchId}` for detail, minding the rate limit: a full history of
100 entries is 100 further requests, which is the entire 2-minute budget of a dev key.

Access note: **confirmed 403 on a personal dev key, 2026-08-21.** Requires a production
key. See [Caveats](#caveats-and-open-questions).

### GET `/val/match/v1/recent-matches/by-queue/{queue}`

Get recent match IDs for a queue.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `queue` | path | yes | string | See [PC queues](#pc-queue-values) |

Response: [`RecentMatchesDto`](#recentmatchesdto)

Riot's implementation notes, which materially affect how you use it:

- Returns matches completed in the **last 10 minutes** on live shards, and the last
  **12 hours** on the `esports` routing value.
- **NA, LATAM and BR share one match-history deployment.** Querying any of the three
  returns a combined list spanning all three, so results are not shard-pure and the same
  match appears from three hosts.
- Requests are load-balanced across backends, so consecutive calls can disagree about
  which matches are present. Do not treat the list as a stable or complete census —
  poll and accumulate.

Access note: **confirmed 403 on a personal dev key, 2026-08-21**, for all nine documented
queue values — and for an invalid queue name too, so the queue enum below is transcribed
but untested.

---

## val-ranked-v1

Competitive leaderboards. Shards: AP, BR, EU, KR, LATAM, NA (no ESPORTS).

### GET `/val/ranked/v1/leaderboards/by-act/{actId}`

Get the leaderboard for the competitive queue in a given act.

| Param | In | Required | Type | Default | Notes |
|-------|----|:--------:|------|---------|-------|
| `actId` | path | yes | string | — | Act UUID; obtain from [`val-content-v1`](#val-content-v1) |
| `size` | query | no | int | 200 | Valid 1–200 |
| `startIndex` | query | no | int | 0 | Offset for paging |

Response: [`LeaderboardDto`](#leaderboarddto)

Page with `startIndex += size`. Anonymized players come back with `puuid`, `gameName` and
`tagLine` **omitted entirely** — the keys are absent, not null, so read them defensively.

---

## val-content-v1

The static content catalogue: agents, maps, game modes, skins, sprays, cards, titles, and
the act list. This is how opaque IDs in match responses become names. Shards: AP, BR,
ESPORTS, EU, KR, LATAM, NA.

### GET `/val/content/v1/contents`

Get content, optionally filtered by locale.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `locale` | query | no | string | e.g. `en-US`; see [locales](#localizednamesdto-locale-keys) |

Response: [`ContentDto`](#contentdto)

Behaviour worth knowing:

- **With** `locale`: each item carries a single `name`, and `localizedNames` is omitted.
- **Without** `locale`: `name` is the default and `localizedNames` carries all 18
  translations. **Measured 2026-08-21 on AP:** 14.3 MB without a locale versus 1.7 MB
  with `locale=en-US` -- an 8x difference, so always send a locale unless you need every
  translation.
- `assetPath` is populated **only for maps and game modes**. Those are exactly the two
  cases where match responses give you an asset path rather than a UUID, so this field is
  the join key — see the [replay tie-in](#using-this-with-vrf-replays).

Cache the response. It changes only on patch boundaries and is by far the largest body in
this API surface.

---

## val-status-v1

Shard health. Shards: AP, BR, EU, KR, LATAM, NA (no ESPORTS).

### GET `/val/status/v1/platform-data`

Get VALORANT status for the shard addressed by the host.

No path or query parameters.

Response: [`PlatformDataDto`](#platformdatadto)

Takes no player identifier and no arguments, which makes it the cheapest possible check
that a key, a host and an auth header are all correct. Use it as a smoke test.

---

## val-console-match-v1

The console (PlayStation / Xbox) mirror of `val-match-v1`. Same three endpoint shapes,
different path prefix -- `/val/match/console/v1/` -- plus a required platform selector on
the match list. Shards: AP, BR, EU, LATAM, NA (**no KR**).

> **Verified 2026-08-21:** every endpoint in this section returns **403** on a personal dev
> key, exactly as `val-match-v1` does. The `platformType`-is-required claim below could not
> be tested, because the request 403s before parameters are validated.

### GET `/val/match/console/v1/matches/{matchId}`

Get a console match by ID.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `matchId` | path | yes | string | Match UUID |

Response: `MatchDto` -- the console variant. See the
[console delta table](#console-dto-deltas) for how it differs from the PC shape.

### GET `/val/match/console/v1/matchlists/by-puuid/{puuid}`

Get the match list for games played by a PUUID on a platform.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `puuid` | path | yes | string | 78 characters |
| `platformType` | query | **yes** | string | `playstation` or `xbox` |

Response: [`MatchlistDto`](#matchlistdto) -- identical to the PC shape.

Unlike the PC endpoint, `platformType` is **required**; omitting it is a 400.

### GET `/val/match/console/v1/recent-matches/by-queue/{queue}`

Get recent console match IDs for a queue.

| Param | In | Required | Type | Notes |
|-------|----|:--------:|------|-------|
| `queue` | path | yes | string | See [console queues](#console-queue-values) -- all `console_`-prefixed |

Response: [`RecentMatchesDto`](#recentmatchesdto)

The same implementation notes as the PC endpoint apply: 10-minute live window, 12 hours on
esports routing, NA/LATAM/BR results combined, load-balanced and therefore inconsistent
between calls.

---

## val-console-ranked-v1

Console competitive leaderboards. Shards: AP, EU, NA only.

> **Verified 2026-08-21:** **403** on a personal dev key across all shards tried
> (AP, EU, NA, BR, KR, LATAM) and both `platformType` values. Unlike PC `val-ranked-v1`,
> which a dev key *can* reach, the console leaderboard is gated. The console
> `LeaderboardDto` and the shard-coverage claim are therefore untested.

### GET `/val/console/ranked/v1/leaderboards/by-act/{actId}`

Get the console leaderboard for the competitive queue.

Note the path prefix differs from console-match: it is `/val/console/ranked/v1/`, with
`console` **before** the resource, whereas match uses `/val/match/console/v1/` with
`console` after. This asymmetry is Riot's, not a typo.

| Param | In | Required | Type | Default | Notes |
|-------|----|:--------:|------|---------|-------|
| `actId` | path | yes | string | -- | Act UUID from [`val-content-v1`](#val-content-v1) |
| `platformType` | query | **yes** | string | -- | `playstation` or `xbox` |
| `startIndex` | query | no | int | 0 | |
| `size` | query | no | int | 200 | Valid 1-200 |

Response: [`LeaderboardDto` (console)](#leaderboarddto-console) -- adds `query` and
`tierDetails` over the PC shape.

---

## DTO reference

Field names, types and Riot's own descriptions. Types are as the portal states them
(`int`, `long`, `float`, `boolean`, `string`); over the wire they are plain JSON numbers,
booleans and strings. Any field described as "may be omitted" is absent from the JSON
object rather than present-and-null.

### account-v1 objects

#### AccountDto

| Field | Type | Description |
|-------|------|-------------|
| `puuid` | string | Encrypted PUUID. Exact length of 78 characters. |
| `gameName` | string | May be excluded if the account has no gameName. |
| `tagLine` | string | May be excluded if the account has no tagLine. |

#### ActiveShardDto

| Field | Type | Description |
|-------|------|-------------|
| `puuid` | string | Encrypted PUUID, 78 characters. |
| `game` | string | Game identifier. |
| `activeShard` | string | Active shard for the player -- use as the `val-*` host prefix. |

**Corrected 2026-08-21.** The portal also lists a `region` field. A live response does
**not** contain it -- the object is exactly `{puuid, game, activeShard}`. Do not index
`["region"]` here; use `MatchInfoDto.region` or `activeShard` instead.

#### AccountRegionDto

| Field | Type | Description |
|-------|------|-------------|
| `puuid` | string | Encrypted PUUID, 78 characters. |
| `game` | string | Game to look up active region for. |
| `region` | string | Player active region. |

### val-match-v1 objects

The `MatchDto` graph, nesting top to bottom:

    MatchDto
      matchInfo     MatchInfoDto
                      premierMatchInfo   List[PremierMatchDto]
      players       List[PlayerDto]
                      stats              PlayerStatsDto
                                           abilityCasts   AbilityCastsDto
      coaches       List[CoachDto]
      teams         List[TeamDto]
      roundResults  List[RoundResultDto]
                      plantLocation           LocationDto
                      defuseLocation          LocationDto
                      plantPlayerLocations    List[PlayerLocationsDto] -> LocationDto
                      defusePlayerLocations   List[PlayerLocationsDto] -> LocationDto
                      playerStats             List[PlayerRoundStatsDto]
                                                kills     List[KillDto]
                                                            victimLocation    LocationDto
                                                            playerLocations   List[PlayerLocationsDto]
                                                            finishingDamage   FinishingDamageDto
                                                damage    List[DamageDto]
                                                economy   EconomyDto
                                                ability   AbilityDto

#### MatchDto

| Field | Type | Description |
|-------|------|-------------|
| `matchInfo` | MatchInfoDto | |
| `players` | List[PlayerDto] | |
| `coaches` | List[CoachDto] | |
| `teams` | List[TeamDto] | |
| `roundResults` | List[RoundResultDto] | |

#### MatchInfoDto

| Field | Type | Description |
|-------|------|-------------|
| `matchId` | string | |
| `mapId` | string | Asset path, not a UUID -- resolve via `val-content-v1` `assetPath`. |
| `gameVersion` | string | |
| `gameLengthMillis` | int | |
| `region` | string | Shard the match was played on. |
| `gameStartMillis` | long | Unix epoch milliseconds. |
| `provisioningFlowId` | string | |
| `isCompleted` | boolean | |
| `customGameName` | string | |
| `queueId` | string | |
| `gameMode` | string | Asset path, same as `mapId`. |
| `isRanked` | boolean | |
| `seasonId` | string | |
| `premierMatchInfo` | List[PremierMatchDto] | |

#### PlayerDto

| Field | Type | Description |
|-------|------|-------------|
| `puuid` | string | |
| `gameName` | string | |
| `tagLine` | string | |
| `teamId` | string | |
| `partyId` | string | Shared by players who queued together. |
| `characterId` | string | Agent UUID -- resolve via `val-content-v1` `characters`. |
| `stats` | PlayerStatsDto | |
| `competitiveTier` | int | |
| `isObserver` | boolean | |
| `playerCard` | string | |
| `playerTitle` | string | |
| `accountLevel` | int | |

#### PlayerStatsDto

| Field | Type | Description |
|-------|------|-------------|
| `score` | int | |
| `roundsPlayed` | int | |
| `kills` | int | |
| `deaths` | int | |
| `assists` | int | |
| `playtimeMillis` | int | |
| `abilityCasts` | AbilityCastsDto | |

#### AbilityCastsDto

| Field | Type | Description |
|-------|------|-------------|
| `grenadeCasts` | int | |
| `ability1Casts` | int | |
| `ability2Casts` | int | |
| `ultimateCasts` | int | |

Abilities are positional, not named -- `ability1` and `ability2` mean different things per
agent. Map them through the agent's `characterId`.

#### CoachDto

| Field | Type | Description |
|-------|------|-------------|
| `puuid` | string | |
| `teamId` | string | |

#### TeamDto

| Field | Type | Description |
|-------|------|-------------|
| `teamId` | string | Arbitrary string. `Red`/`Blue` in bomb modes; the player's PUUID in deathmatch. |
| `won` | boolean | |
| `roundsPlayed` | int | |
| `roundsWon` | int | |
| `numPoints` | int | Team points scored. Number of kills in deathmatch. |

#### RoundResultDto

| Field | Type | Description |
|-------|------|-------------|
| `roundNum` | int | |
| `roundResult` | string | |
| `roundCeremony` | string | |
| `winningTeam` | string | |
| `winningTeamRole` | string | |
| `bombPlanter` | string | PUUID of player. |
| `bombDefuser` | string | PUUID of player. |
| `plantRoundTime` | int | Milliseconds since round start. |
| `plantPlayerLocations` | List[PlayerLocationsDto] | Every player's position at the plant. |
| `plantLocation` | LocationDto | |
| `plantSite` | string | |
| `defuseRoundTime` | int | Milliseconds since round start. |
| `defusePlayerLocations` | List[PlayerLocationsDto] | Every player's position at the defuse. |
| `defuseLocation` | LocationDto | |
| `playerStats` | List[PlayerRoundStatsDto] | |
| `roundResultCode` | string | |

Plant and defuse fields are absent or zeroed in rounds where the spike was never planted,
and in non-bomb modes.

#### PlayerLocationsDto

| Field | Type | Description |
|-------|------|-------------|
| `puuid` | string | |
| `viewRadians` | float | Yaw the player was facing, in radians. |
| `location` | LocationDto | |

#### LocationDto

| Field | Type | Description |
|-------|------|-------------|
| `x` | int | |
| `y` | int | |

Two-dimensional and integral -- there is no `z`. These are world-space game units, not
minimap pixels; converting to a minimap needs the per-map multiplier and offset, which
this API does not publish.

#### PlayerRoundStatsDto

| Field | Type | Description |
|-------|------|-------------|
| `puuid` | string | |
| `kills` | List[KillDto] | |
| `damage` | List[DamageDto] | |
| `score` | int | |
| `economy` | EconomyDto | |
| `ability` | AbilityDto | |

#### KillDto

| Field | Type | Description |
|-------|------|-------------|
| `timeSinceGameStartMillis` | int | |
| `timeSinceRoundStartMillis` | int | |
| `killer` | string | PUUID. |
| `victim` | string | PUUID. |
| `victimLocation` | LocationDto | |
| `assistants` | List[string] | List of PUUIDs. |
| `playerLocations` | List[PlayerLocationsDto] | Every player's position at the moment of the kill. |
| `finishingDamage` | FinishingDamageDto | |

#### FinishingDamageDto

| Field | Type | Description |
|-------|------|-------------|
| `damageType` | string | |
| `damageItem` | string | |
| `isSecondaryFireMode` | boolean | |

#### DamageDto

| Field | Type | Description |
|-------|------|-------------|
| `receiver` | string | PUUID. |
| `damage` | int | |
| `legshots` | int | |
| `bodyshots` | int | |
| `headshots` | int | |

Damage is recorded per victim per round, so a round's headshot percentage is a sum across
the list, not a single field.

#### EconomyDto

| Field | Type | Description |
|-------|------|-------------|
| `loadoutValue` | int | |
| `weapon` | string | |
| `armor` | string | |
| `remaining` | int | Credits left after buying. |
| `spent` | int | |

#### AbilityDto

| Field | Type | Description |
|-------|------|-------------|
| `grenadeEffects` | string | |
| `ability1Effects` | string | |
| `ability2Effects` | string | |
| `ultimateEffects` | string | |

#### PremierMatchDto

Riot publishes this DTO with an **empty field table**. Its contents are undocumented -- do
not assume a shape; inspect a live Premier match response. See
[Caveats](#caveats-and-open-questions).

#### MatchlistDto

| Field | Type | Description |
|-------|------|-------------|
| `puuid` | string | |
| `history` | List[MatchlistEntryDto] | |

#### MatchlistEntryDto

| Field | Type | Description |
|-------|------|-------------|
| `matchId` | string | |
| `gameStartTimeMillis` | long | Unix epoch milliseconds. |
| `queueId` | string | |

#### RecentMatchesDto

| Field | Type | Description |
|-------|------|-------------|
| `currentTime` | long | Server time, epoch ms -- anchor for the 10-minute window. |
| `matchIds` | List[string] | A list of recent match ids. |

### val-ranked-v1 objects

#### LeaderboardDto

| Field | Type | Description |
|-------|------|-------------|
| `shard` | string | The shard for the given leaderboard. |
| `actId` | string | The act id for the given leaderboard. |
| `totalPlayers` | long | Total number of players in the leaderboard. |
| `players` | List[PlayerDto] | |
| `startIndex` | int | **Undocumented.** Echo of the `startIndex` used. |
| `query` | string | **Undocumented on PC.** Echo of the query string; `""` when none. |
| `tierDetails` | dict | **Undocumented on PC.** See [TierDto](#tierdto). |
| `immortalStartingIndex` | int | **Undocumented.** First 0-based index at Immortal. |
| `immortalStartingPage` | int | **Undocumented.** Same boundary, as a page number. |
| `topTierRRThreshold` | int | **Undocumented.** RR threshold of the highest tier. |

> **Correction (verified 2026-08-21).** The portal documents only the first four fields,
> and presents `query` and `tierDetails` as *console-only* additions. They are **not** --
> the PC response carries all ten fields above. A live `ap` response was:
>
>     actId immortalStartingIndex immortalStartingPage players query shard
>     startIndex tierDetails topTierRRThreshold totalPlayers
>
> `totalPlayers` is capped per shard, not a true population count: AP 15000, EU 15000,
> NA 5931, BR 3995, LATAM 3160, KR 2936 on the same act.

#### PlayerDto (leaderboard)

Distinct from the match `PlayerDto` despite the shared name.

| Field | Type | Description |
|-------|------|-------------|
| `puuid` | string | **May be omitted** if the player has been anonymized. |
| `gameName` | string | **May be omitted** if the player has been anonymized. |
| `tagLine` | string | **May be omitted** if the player has been anonymized. |
| `leaderboardRank` | long | 1-based. `startIndex=10` yields ranks 11, 12, 13... |
| `rankedRating` | long | |
| `numberOfWins` | long | |
| `competitiveTier` | int | **Undocumented by Riot; always present in live responses.** |
| `prefix` | string | **Undocumented.** Localized name prefix; often `""`. |
| `premierRosterType` | string | **Undocumented.** Often `""`. |

`puuid` here is a full 78-character encrypted PUUID -- confirmed 2026-08-21, and it
round-trips through `account-v1` `by-puuid` and `by-riot-id` cleanly. That makes the
leaderboard the easiest source of a real PUUID for testing when you have no Riot ID
to hand.

#### LeaderboardDto (console)

The console leaderboard adds two fields over the PC shape.

| Field | Type | Description |
|-------|------|-------------|
| `actId` | string | The act id for the given leaderboard. |
| `totalPlayers` | long | Total number of players in the leaderboard. |
| `query` | string | Echo of the query that produced this page. |
| `shard` | string | The shard for the given leaderboard. |
| `players` | List[PlayerDto] | Same shape as the PC leaderboard player. |
| `tierDetails` | List[TierDto] | |

#### TierDto

Riot publishes `TierDto` with an **empty field table**, but a live response gives its
shape. **It is not a list.** Despite `tierDetails` being typed `List[TierDto]`, the wire
format is a **JSON object keyed by competitive tier number**:

    "tierDetails": {
      "24": {"rankedRatingThreshold": 0,   "startingPage": 751, "startingIndex": 3754},
      "25": {"rankedRatingThreshold": 100, "startingPage": 291, "startingIndex": 1451},
      "26": {"rankedRatingThreshold": 200, "startingPage": 101, "startingIndex": 501},
      "27": {"rankedRatingThreshold": 300, "startingPage": 1,   "startingIndex": 1}
    }

| Field | Type | Description |
|-------|------|-------------|
| `rankedRatingThreshold` | int | Minimum RR to sit in this tier. |
| `startingPage` | int | 1-based page on which the tier starts. |
| `startingIndex` | int | Index at which the tier starts. |

Iterate it with `.items()`, not as a sequence. Observed on the PC (`val-ranked-v1`)
leaderboard on 2026-08-21; the console shape is untested.

### val-content-v1 objects

#### ContentDto

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | |
| `characters` | List[ContentItemDto] | Agents. |
| `maps` | List[ContentItemDto] | |
| `chromas` | List[ContentItemDto] | |
| `skins` | List[ContentItemDto] | |
| `skinLevels` | List[ContentItemDto] | |
| `equips` | List[ContentItemDto] | |
| `gameModes` | List[ContentItemDto] | |
| `sprays` | List[ContentItemDto] | |
| `sprayLevels` | List[ContentItemDto] | |
| `charms` | List[ContentItemDto] | |
| `charmLevels` | List[ContentItemDto] | |
| `playerCards` | List[ContentItemDto] | |
| `playerTitles` | List[ContentItemDto] | |
| `acts` | List[ActDto] | Source of `actId` for the ranked endpoints. |
| `totems` | List[ContentItemDto] | **Undocumented by Riot; present in live responses** (23 items on `release-13.04`). |
| `ceremonies` | List[ContentItemDto] | **Undocumented by Riot; present in live responses** (6 items on `release-13.04`). |

Collection sizes on `release-13.04` (AP, `locale=en-US`), for sanity-checking a parse:
`characters` 29, `maps` 27, `chromas` 2921, `skins` 1405, `skinLevels` 2677, `equips` 38,
`gameModes` 17, `totems` 23, `sprays` 912, `sprayLevels` 912, `charms` 884,
`charmLevels` 884, `playerCards` 974, `playerTitles` 407, `acts` 53, `ceremonies` 6.

#### ContentItemDto

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | |
| `localizedNames` | LocalizedNamesDto | Excluded from the response when a `locale` is set. |
| `id` | string | |
| `assetName` | string | |
| `assetPath` | string | **Only included for maps and game modes.** These values are what appear in match responses. **Verified 2026-08-21:** of 17 collections, only `maps` and `gameModes` carry it -- and even in `maps` it is 26/27, because the placeholder entry `"Null UI Data!"` has none. Always guard with `.get("assetPath")`. |

#### ActDto

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | |
| `localizedNames` | LocalizedNamesDto | Excluded when a `locale` is set. |
| `id` | string | Pass as `actId` to the ranked endpoints -- **only if `type` is `act`**. |
| `isActive` | boolean | See the warning below. |
| `parentId` | string | **Undocumented by Riot.** For an `act`, the id of its parent `episode`; for an `episode`, all-zero UUID. |
| `type` | string | **Undocumented by Riot.** `act` or `episode`. |

> **Correction (verified 2026-08-21).** The portal's "exactly one act is active" is
> **wrong**, and believing it produces a 404. The `acts` collection mixes two kinds of
> entry -- on `release-13.04` there were 39 of `type: "act"` and 14 of `type: "episode"`
> -- and **exactly one of each is active simultaneously**, so filtering on `isActive`
> alone returns **two** ids:
>
>     {"id": "3737c391-...", "type": "episode", "name": "V26",    "parentId": "00000000-...", "isActive": true}
>     {"id": "8102cd81-...", "type": "act",     "name": "ACT V",  "parentId": "3737c391-...", "isActive": true}
>
> Passing the **episode** id to a leaderboard endpoint returns
> `404 MMR_LEADERBOARD_NOT_FOUND`. Always filter on both fields:
>
>     act_id = next(a["id"] for a in content["acts"] if a["isActive"] and a["type"] == "act")

### val-status-v1 objects

#### PlatformDataDto

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | |
| `name` | string | |
| `locales` | List[string] | |
| `maintenances` | List[StatusDto] | |
| `incidents` | List[StatusDto] | |

#### StatusDto

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | |
| `maintenance_status` | string | `scheduled`, `in_progress`, `complete` |
| `incident_severity` | string | `info`, `warning`, `critical` |
| `titles` | List[ContentDto] | |
| `updates` | List[UpdateDto] | |
| `created_at` | string | |
| `archive_at` | string | |
| `updated_at` | string | |
| `platforms` | List[string] | `windows`, `macos`, `android`, `ios`, `ps4`, `xbone`, `switch` |

Note the `snake_case` field names -- this is the only DTO in the surface that is not
`camelCase`.

#### ContentDto (status)

Unrelated to `val-content-v1`'s `ContentDto` despite the name.

| Field | Type | Description |
|-------|------|-------------|
| `locale` | string | |
| `content` | string | |

#### UpdateDto

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | |
| `author` | string | |
| `publish` | boolean | |
| `publish_locations` | List[string] | `riotclient`, `riotstatus`, `game` |
| `translations` | List[ContentDto] | |
| `created_at` | string | |
| `updated_at` | string | |

### Console DTO deltas

The console `MatchDto` graph is the PC graph minus a few fields. Everything not listed
here is identical, including `PlayerStatsDto`, `AbilityCastsDto`, `CoachDto`, `TeamDto`,
`PlayerLocationsDto`, `LocationDto`, `PlayerRoundStatsDto`, `KillDto`,
`FinishingDamageDto`, `DamageDto`, `EconomyDto`, `AbilityDto`, `MatchlistDto`,
`MatchlistEntryDto` and `RecentMatchesDto`.

| DTO | Present on PC, absent on console |
|-----|----------------------------------|
| `MatchInfoDto` | `gameVersion`, `region`, `premierMatchInfo` |
| `PlayerDto` | `isObserver`, `accountLevel` |
| `RoundResultDto` | `winningTeamRole` |

Losing `region` from console `MatchInfoDto` means a console match does not tell you which
shard it came from; you have to remember which host you asked.

---

## Enumerations

Values Riot documents as legal. Anything outside these sets is a 400.

### PC queue values

For `GET /val/match/v1/recent-matches/by-queue/{queue}`:

    competitive  unrated  spikerush  tournamentmode  deathmatch  onefa  ggteam  hurm  swiftplay

`onefa` is Replication, `ggteam` is Escalation, `hurm` is Team Deathmatch.

### Console queue values

For `GET /val/match/console/v1/recent-matches/by-queue/{queue}`:

    console_competitive  console_unrated  console_swiftplay  console_deathmatch  console_hurm

Console has no spike rush, replication, escalation or tournament queue.

### platformType

For the console match list and console leaderboard:

    playstation  xbox

Required on both. There is no combined or "all platforms" value.

### game (account-v1)

| Endpoint | Legal values |
|----------|--------------|
| `/active-shards/by-game/{game}/by-puuid/{puuid}` | `val`, `lor`, `2xko` (verified) |
| `/region/by-game/{game}/by-puuid/{puuid}` | `lol`, `tft` |

### Status enumerations

| Field | Legal values |
|-------|--------------|
| `maintenance_status` | `scheduled`, `in_progress`, `complete` |
| `incident_severity` | `info`, `warning`, `critical` |
| `platforms` | `windows`, `macos`, `android`, `ios`, `ps4`, `xbone`, `switch` |
| `publish_locations` | `riotclient`, `riotstatus`, `game` |

### LocalizedNamesDto locale keys

**Corrected 2026-08-21.** The portal lists 19 keys including `en-GB`. A live response
carries **18** -- `en-GB` is **not** among them:

    ar-AE  de-DE  en-US  es-ES  es-MX  fr-FR  id-ID  it-IT  ja-JP
    ko-KR  pl-PL  pt-BR  ru-RU  th-TH  tr-TR  vi-VN  zh-CN  zh-TW

`en-GB` is still accepted as a `locale` *query* value; it just never appears as a
`localizedNames` key. An unknown locale returns
`400 {"errorCode": "UNKNOWN_LOCALE"}`.

Note also that `PlatformDataDto.locales` (in `val-status-v1`) uses **underscores** for the
same idea -- `en_US`, `ar_AE` -- not the hyphens used here.

Pass any one of these as the `locale` query parameter to `val-content-v1` to collapse
`localizedNames` down to a single `name`.

---

## Recipes

`curl` first, then the stdlib equivalent. This project has **no runtime dependencies** --
`pyproject.toml` is stdlib plus tkinter -- so the Python below uses `urllib` rather than
`requests`, matching the rest of the codebase.

### Loading the key

PowerShell:

    $k = ((Get-Content .env | Select-String '^RIOT_API=') -split '=', 2)[1].Trim()

Bash:

    k=$(grep '^RIOT_API=' .env | cut -d= -f2-)

Python, without a dotenv dependency:

    from pathlib import Path

    def riot_key(path=".env"):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.startswith("RIOT_API="):
                return line.split("=", 1)[1].strip()
        raise RuntimeError("RIOT_API not found in .env")

### Riot ID to match detail

The canonical four-hop flow. Note the host changes between hops 1-2 and 3-4.

**Hops 1-2 work on a personal dev key; hops 3-4 do not** — both are `val-match-v1` and
both 403 without a production key (verified 2026-08-21). The flow is written out in full
because it is correct once the key is approved.

    # 1. Riot ID -> PUUID                                        (cluster host)
    curl -s -H "X-Riot-Token: $k" \
      "https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/Name/TAG"

    # 2. PUUID -> shard                                          (cluster host)
    curl -s -H "X-Riot-Token: $k" \
      "https://americas.api.riotgames.com/riot/account/v1/active-shards/by-game/val/by-puuid/$puuid"

    # 3. PUUID -> match ids                                      (SHARD host)
    curl -s -H "X-Riot-Token: $k" \
      "https://ap.api.riotgames.com/val/match/v1/matchlists/by-puuid/$puuid"

    # 4. match id -> full match                                  (SHARD host)
    curl -s -H "X-Riot-Token: $k" \
      "https://ap.api.riotgames.com/val/match/v1/matches/$matchId"

In Python:

    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    KEY = riot_key()

    # Cloudflare 403s urllib's default User-Agent before the key is even read, so this
    # header is mandatory, not cosmetic. See "You must send a User-Agent" above.
    HEADERS = {"X-Riot-Token": KEY, "User-Agent": "val-replay-analyzer/0.1"}

    def get(host, path, **params):
        url = f"https://{host}.api.riotgames.com{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            body = exc.read()[:200].decode("utf-8", "replace")
            # 1010 => the User-Agent block, not the key. 429 carries Retry-After.
            # 403 on any /val/match/ path => needs a production key.
            raise RuntimeError(f"{exc.code} {exc.reason} for {url}: {body}") from exc

    account = get("americas", "/riot/account/v1/accounts/by-riot-id/Name/TAG")
    puuid = account["puuid"]
    shard = get("americas", f"/riot/account/v1/active-shards/by-game/val/by-puuid/{puuid}")["activeShard"]
    history = get(shard, f"/val/match/v1/matchlists/by-puuid/{puuid}")["history"]
    match = get(shard, f"/val/match/v1/matches/{history[0]['matchId']}")

URL-encode `gameName` if it contains spaces: `urllib.parse.quote(name, safe="")`.

### Act id, then leaderboard

Filtering on `isActive` alone returns **two** ids -- the active episode and the active
act -- and the episode id 404s against the leaderboard. Filter on `type` as well:

    # Current ACT id (not the episode), then the top 10 of that act on AP.
    curl -s -H "X-Riot-Token: $k" \
      "https://ap.api.riotgames.com/val/content/v1/contents?locale=en-US" \
      | python -c "import json,sys; print([a['id'] for a in json.load(sys.stdin)['acts'] if a['isActive'] and a['type']=='act'])"

    curl -s -H "X-Riot-Token: $k" \
      "https://ap.api.riotgames.com/val/ranked/v1/leaderboards/by-act/$actId?size=10&startIndex=0"

Verified end to end on 2026-08-21: act `8102cd81-43a0-d0d7-bd59-47b8fe9bed1b` ("ACT V"),
`size` accepted across 1-200 with 200 as the default, `startIndex=10` returning
`leaderboardRank` 11 onward, and `size` of 0, 201 or -1 each returning
`400 ... must be between 1 and 200`. An unparseable actId returns `400 BAD_PARAMETER`.

### Resolving asset paths to names

`mapId` and `gameMode` in a match are asset paths, and `assetPath` is the only field that
carries them in the content catalogue:

    content = get(shard, "/val/content/v1/contents", locale="en-US")
    maps = {m["assetPath"]: m["name"] for m in content["maps"] if m.get("assetPath")}
    modes = {g["assetPath"]: g["name"] for g in content["gameModes"] if g.get("assetPath")}
    agents = {c["id"].lower(): c["name"] for c in content["characters"]}

    print(maps[match["matchInfo"]["mapId"]])
    print(agents[match["players"][0]["characterId"].lower()])

`characterId` casing is not guaranteed to match the content `id` casing -- normalise both
sides before joining, as above. **This is not hypothetical:** on 2026-08-21 the content
catalogue returned agent ids uppercase (`E370FA57-4757-3604-3648-499E1F642D3F`) while the
decoded replay stores them lowercase. Joining without `.lower()` matches nothing.

---

## Using this with `.vrf` replays

> **Tested 2026-08-21.** Join keys 2 and 3 are **confirmed against live API data**. Join
> key 1 is confirmed on the replay side but **cannot be confirmed on the API side**,
> because `val-match-v1` is 403 without a production key. Everything in this section that
> needs a `MatchDto` — the coordinate cross-check especially — is therefore still a plan,
> not a result.

The API and the offline decoder in `libraries/vrfnet/` describe the same match from two
directions. The decoder gives continuous, per-tick truth with no names attached; the API
gives sparse, authoritative, fully-named truth. They join cleanly, and the join keys were
checked against the decoded header of `Demos/039f3991-5472-4119-bed2-838da0935f60.vrf`
(see `out/039f3991.json`, produced by `runners\vrf-to-json.bat`).

### Join key 1: the filename is the match id

`Demos/<uuid>.vrf` is named by match UUID. Confirmed three ways in the decoded header:

| Where | Value |
|-------|-------|
| `source.file_name` | `039f3991-5472-4119-bed2-838da0935f60.vrf` |
| `container_header.friendly_name` | `039f3991-5472-4119-bed2-838da0935f60` |
| `events[].id` | `039f3991-5472-4119-bed2-838da0935f60_<eventGuid>` |

So any local capture can be looked up directly, with no search step:

    matchId = Path("Demos/039f3991-5472-4119-bed2-838da0935f60.vrf").stem
    match = get(shard, f"/val/match/v1/matches/{matchId}")

**Status: half-verified.** The replay side holds — all 101 files in `Demos/` are named by
a UUID that matches the header three ways, as above. The API side is untested: the lookup
was tried on 2026-08-21 with the newest capture
(`5dd34fdc-0694-4ec3-adf2-6fef5176e454`, recorded 2026-06-30) against all seven routing
values, and every one returned **403, not 404** — the production-key gate, hit before the
match id is ever looked at. So this is still the right shape for the join, but it has not
been shown to return a match.

You still need the right shard. `MatchInfoDto.region` confirms it after the fact; before
the fact, try the shard you play on. Note that with a dev key you cannot tell "wrong host"
from "no such match" from "no access" — all three are 403.

### Join key 2: map asset path

`demo_header.maps[0]` in the decoded replay is `/Game/Maps/Infinity/Infinity` -- exactly
the format `MatchInfoDto.mapId` uses, and exactly what `val-content-v1` exposes as
`ContentItemDto.assetPath` on the `maps` collection. That makes the content catalogue a
drop-in name resolver for the replay's own map field, with no API call needed per replay
once the catalogue is cached:

    maps = {m["assetPath"]: m["name"] for m in content["maps"] if m.get("assetPath")}
    print(maps[replay["demo_header"]["maps"][0]])

**Confirmed live 2026-08-21.** Run against a real `val-content-v1` response, the replay's
`/Game/Maps/Infinity/Infinity` resolves to:

    {"name": "Abyss", "id": "224B0A95-48B9-F703-1BD8-67ACA101A61F",
     "assetName": "Infinity", "assetPath": "/Game/Maps/Infinity/Infinity"}

Note that the internal name (`Infinity`) is not the display name (`Abyss`) — which is the
whole reason this join is needed. The `.get("assetPath")` guard is load-bearing: one entry
in `maps` (`"Null UI Data!"`) has no `assetPath` at all.

`assetPath` is populated for maps and game modes only -- that restriction, noted in
[`ContentItemDto`](#contentitemdto), is exactly why this join works for maps and not for
anything else.

### Join key 3: agent UUIDs

`match_metadata.players[]` in the decoded header carries `{index, subject, characterId}`,
e.g. `characterId: 41fb69c1-4189-7b37-f117-bcaf1e96f1bf`. That is the same UUID space as
`PlayerDto.characterId` in a match response and as `ContentItemDto.id` in the content
catalogue's `characters` collection. So agent names resolve for a replay offline:

    agents = {c["id"].lower(): c["name"] for c in content["characters"]}
    [agents[p["characterId"].lower()] for p in replay["match_metadata"]["players"]]

**Confirmed live 2026-08-21.** All **10/10** `characterId` values from the decoded header
resolve against the live catalogue's 29 characters:

    ['Astra', 'Killjoy', 'Waylay', 'Sova', 'Reyna', 'Sova', 'Reyna',
     'Brimstone', 'Chamber', 'Raze']

which is exactly the multiset this document predicted — 8 distinct agents with Sova x2 and
Reyna x2.

This also upgrades the cross-check recorded in `vrf-decoding-findings.md`. That check
validated the agent codenames recovered from the replication stream against the header's
own `playerLoadouts` -- two paths, but both inside the same file. `val-content-v1` is a
genuinely external third source, and it agrees: the ten decoded pawns resolve to the
expected 8 distinct agents with Sova x2 and Reyna x2.

The stronger check -- comparing against the ten `characterId` values in a `MatchDto`,
which would also confirm the match id itself -- still needs a production key.

### What the API adds that the replay does not have

| Need | API source |
|------|------------|
| Player display names | `PlayerDto.gameName` / `tagLine` -- the replay header has UUIDs only |
| Rank at time of match | `PlayerDto.competitiveTier` |
| Party composition | `PlayerDto.partyId` |
| Round outcome and reason | `RoundResultDto.roundResult`, `roundResultCode`, `roundCeremony` |
| Per-round economy | `EconomyDto` -- loadout value, weapon, armor, credits spent/remaining |
| Damage breakdown | `DamageDto` -- legshots/bodyshots/headshots per victim per round |
| Weapon behind each kill | `FinishingDamageDto.damageItem`, `isSecondaryFireMode` |
| Map and mode display names | via `val-content-v1` as above |

### What the replay has that the API does not

The decoded sample carries 143 events -- 108 `characterDeath`, 15 `roundStarted`, 9
`characterUltimateUsed`, 7 `spikePlanted`, 2 `spikeDefused`, 1 `spikeExploded`, 1
`switchTeams` -- plus the full replication stream behind them. The API has no equivalent
of continuous motion: `LocationDto` values exist **only** at plants, defuses and kills.
Everything between those instants -- movement, peeks, rotations, utility placement,
crosshair placement over time -- exists only in the replay. The API cannot replace the
decoder; it annotates it.

### Coordinate cross-check for the viewer

> **Blocked on a production key.** Every input this procedure needs lives in a `MatchDto`,
> which a personal dev key cannot fetch. The method below is unchanged and still sound;
> it simply has not been run.

`RoundResultDto.plantLocation` / `defuseLocation` and the `PlayerLocationsDto` entries
attached to plants, defuses and kills are free ground-truth samples for calibrating the
coordinate mapping in `libraries/vrfview/`. The workflow:

1. Take a round with a plant. Read `plantRoundTime` (ms since round start) and
   `plantLocation` `{x, y}` from the API.
2. Seek the decoded replay to the same round-relative time and read the spike's decoded
   position.
3. The two should describe the same point. A constant offset or scale factor between them
   is the map transform; a rotation or axis swap means the decoder's axes are mislabelled.

Kills give many more sample points than plants do: every `KillDto` carries
`victimLocation` plus a `playerLocations` array for all ten players at that instant, and
`timeSinceRoundStartMillis` to seek by. A single competitive match yields on the order of
150 correspondences, which is far more than a least-squares fit for a 2D similarity
transform needs.

Caveats for this cross-check: `LocationDto` is integer-valued and 2D, so expect rounding
noise and no height information; and `viewRadians` gives yaw only, which constrains a
rotation term but not pitch.

### Suggested order of work

1. Cache `val-content-v1` once per patch -- it is the largest body and changes least.
   Send `locale=en-US` (1.7 MB, versus 14.3 MB unfiltered). **This works today.**
2. Resolve map and agent names offline from that cache; no per-replay API call needed.
   **This works today** -- steps 1 and 2 are fully verified and need nothing more than the
   personal key already in `.env`.
3. Apply for a **production key**. Steps 4-5 are unreachable without one; this is the real
   blocker, not rate limits.
4. Fetch `/val/match/v1/matches/{matchId}` per replay you actually analyse, and cache the
   response next to the `.vrf`. One call per replay stays comfortably inside a dev key's
   100-per-2-minutes budget; a bulk sweep of all 101 captures in `Demos/` does not.
5. Only then attempt the coordinate cross-check.

---

## Caveats and open questions

Stated plainly rather than papered over.

### Provenance of this document

The developer portal renders its endpoint tables client-side, so they cannot be read by a
plain HTTP fetch. The field tables above were originally transcribed from a mirror of the
portal's own documentation, not from live API responses. The **shapes are Riot's**, but
they were one hop removed from the source.

On 2026-08-21 that transcription was checked against the live API with a personal dev key.
Roughly half the surface could be reached; the rest is gated behind a production key.
Sections that were checked now carry an explicit "verified" or "corrected" note with that
date, and the transcription turned out to be **wrong or incomplete in twelve places** —
all now fixed inline. Anything without such a note is still transcription only. The full
breakdown is in [Verification status](#verification-status).

### Endpoints that may not work with a personal dev key

### What a personal dev key can actually reach

**Measured 2026-08-21**, one valid key, all seven routing values. This is the single most
important practical finding in this document, and it is worse than the earlier text
assumed.

| API | Dev key | Notes |
|-----|:-------:|-------|
| `account-v1` | ✅ 200 | Except `/accounts/me` (403 — needs RSO). |
| `val-status-v1` | ✅ 200 | All six shards. |
| `val-content-v1` | ✅ 200 | Live and `esports` routing. |
| `val-ranked-v1` | ✅ 200 | All six shards. |
| `val-match-v1` | ❌ **403** | **All three endpoints**, including `/matches/{matchId}`. |
| `val-console-match-v1` | ❌ 403 | All three endpoints. |
| `val-console-ranked-v1` | ❌ 403 | All shards, both platforms. |

Earlier revisions of this document said "if the match list returns 403 while
`/val/match/v1/matches/{matchId}` works, that is the production-key gate". **That test does
not work** — `/matches/{matchId}` 403s too, so there is nothing to contrast it against. A
403 from any `/val/match/` path means one of: expired key, no production grant, or the
Cloudflare User-Agent block. Distinguish them by calling
`/val/status/v1/platform-data` — if that returns 200, the key and User-Agent are fine and
you are looking at the production gate.

For this project the consequence is concrete: the `.vrf` filenames supply match IDs, but
**nothing can currently be done with them**. Map names and agent names resolve offline via
`val-content-v1` and need no further access; everything else in the
[tie-in](#using-this-with-vrf-replays) waits on a production key.

### Undocumented DTOs

Riot ships two DTOs with empty field tables. Their contents are genuinely unpublished --
they are not omitted here by mistake, and no shape should be assumed for them:

- `PremierMatchDto`, referenced by `MatchInfoDto.premierMatchInfo` — still unknown, since
  no `MatchDto` could be fetched.
- `TierDto` — **no longer unknown.** It was recovered from a live PC leaderboard on
  2026-08-21 and is documented at [TierDto](#tierdto). It is a **dict keyed by tier**,
  not the `List[TierDto]` the portal's type says, and it appears on the **PC** leaderboard
  as well as the console one.

Beyond those two, live responses carried **thirteen fields Riot does not document at all**:
`totems` and `ceremonies` on `ContentDto`; `parentId` and `type` on `ActDto`;
`startIndex`, `query`, `tierDetails`, `immortalStartingIndex`, `immortalStartingPage` and
`topTierRRThreshold` on the PC `LeaderboardDto`; and `competitiveTier`, `prefix` and
`premierRosterType` on the leaderboard `PlayerDto`. Riot also documents one field that
does not exist: `ActiveShardDto.region`. Parse defensively in both directions.

### PUUID format mismatch

`account-v1` documents `puuid` as **exactly 78 characters** (an encrypted PUUID). The
`subject` values in a decoded `.vrf` header are 36-character UUIDs, e.g.
`19c14046-bb7d-5c30-84e6-b09b4910cbce`. **The 78-character length is confirmed** — live
`account-v1` and leaderboard responses on 2026-08-21 returned PUUIDs of exactly 78
characters, e.g.
`k-6NmMC6yxiyhiTco1K43iprZGrWh-lIPkql9W5byjBeDe0ENyM7JVY9-WvPX6mgJuwnlbbGXrjQLA`.
These are not the same encoding, so replay `subject` values almost certainly **cannot be
joined directly** to API `puuid` values.
Treat any player-level join between replay and API as unproven until tested; the
`characterId` and map-path joins in the [tie-in](#using-this-with-vrf-replays) do not
depend on it.

### Other things worth knowing

- **Dev keys expire every 24 hours.** A 403 that appeared overnight is almost always this.
- **`recent-matches` is not a census.** Load balancing makes consecutive calls disagree,
  and NA/LATAM/BR results are combined across all three shards.
- **Leaderboard identity fields can vanish.** Anonymized players omit `puuid`, `gameName`
  and `tagLine` entirely; use `.get()`, not `[...]`.
- **`val-status-v1` uses `snake_case`** while every other DTO is `camelCase`.
- **Console path prefixes are inconsistent**: `/val/match/console/v1/` but
  `/val/console/ranked/v1/`.
- **The API is read-only.** Every endpoint is `GET`; there is no write surface.

### Verifying this document

Two endpoints need no PUUID, no act id and no match id, which makes them the cheapest
confirmation that the key, the host and the auth header are all as documented:

    $k = ((Get-Content .env | Select-String '^RIOT_API=') -split '=', 2)[1].Trim()
    curl.exe -s -H "X-Riot-Token: $k" "https://ap.api.riotgames.com/val/status/v1/platform-data"
    curl.exe -s -H "X-Riot-Token: $k" "https://ap.api.riotgames.com/val/content/v1/contents?locale=en-US"

Both returned 200 on 2026-08-21. Use `val-status-v1` as the discriminator whenever
something else 403s: if status returns 200, the key is live and the User-Agent is
acceptable, so the other 403 is an access grant problem.

Then the central claim of the tie-in section, taking any `Demos/` filename stem as a
match id:

    curl.exe -s -H "X-Riot-Token: $k" `
      "https://ap.api.riotgames.com/val/match/v1/matches/039f3991-5472-4119-bed2-838da0935f60"

This returns **403**, on every shard, for both an eight-month-old capture and the newest
one in `Demos/` — the production-key gate, not a stale match. Retest after a production
key is granted; until then a 404-versus-200 result here is unobtainable.

---

## Verification status

Everything below was measured on **2026-08-21** with the personal dev key in `.env`,
against ~100 live requests. No 429 was hit at ~0.75 req/s.

### Confirmed as documented

- App rate limits — response headers reported exactly `20:1,100:120`.
- The six `val-*` shard hosts, all returning their own `id`: AP, BR, EU, KR, LATAM, NA.
- `account-v1` clusters are interchangeable — the same PUUID resolved from `americas`
  and `asia`.
- `AccountDto` is exactly `{puuid, gameName, tagLine}`, and `by-puuid` ↔ `by-riot-id`
  round-trips, including a non-ASCII `gameName` when URL-encoded.
- `PlatformDataDto` is exactly `{id, name, locales, maintenances, incidents}`.
- `assetPath` appears on `maps` and `gameModes` and on no other collection.
- `localizedNames` is omitted when `locale` is set, present when it is not.
- Leaderboard `size` is 1–200, defaults to 200, and `startIndex` is a 0-based offset.
- `val-ranked-v1` serves six shards and 403s on `esports`.
- `region/by-game` rejects `val` and accepts `lol`.
- PUUIDs are 78 characters; replay `subject` values are 36-character UUIDs, so the two
  cannot be joined.
- Both offline join keys: map asset path → `Abyss`, and 10/10 agent UUIDs → the exact
  multiset predicted.

### Corrected in place

| # | Claim as written | Reality |
|:-:|------------------|---------|
| 1 | urllib recipe works as given | Cloudflare 403s `Python-urllib/*`; a `User-Agent` is mandatory |
| 2 | `val-*` on a cluster host → 404 | → **403** |
| 3 | 401 means "header missing entirely" | Also returned for a syntactically valid but fake key |
| 4 | `/accounts/me` → 401 with a dev key | → **403** |
| 5 | Only matchlists/recent-matches are production-gated | **All of `val-match-v1`** is, including `/matches/{matchId}` |
| 6 | `ContentDto` has 15 fields | Also `totems` and `ceremonies` |
| 7 | "Exactly one act is active" | Two are — one `episode`, one `act`; the episode id 404s |
| 8 | `ActDto` has 4 fields | Also `parentId` and `type` |
| 9 | 19 `localizedNames` keys | **18** — `en-GB` is absent |
| 10 | `query`/`tierDetails` are console-only | Both appear on the PC leaderboard, plus four more undocumented fields |
| 11 | `TierDto` is undocumented and a `List` | Shape recovered; it is a **dict keyed by tier** |
| 12 | `ActiveShardDto` has a `region` field | It does not |
| 13 | `active-shards` accepts `val`, `lor` | Also `2xko` |

### Not testable with a dev key

All of it behind a 403, so the field tables remain transcription:

- The entire `MatchDto` graph — `MatchInfoDto`, `PlayerDto`, `TeamDto`, `RoundResultDto`,
  `KillDto`, `DamageDto`, `EconomyDto`, `LocationDto` and the rest.
- `MatchlistDto`, `RecentMatchesDto`, `PremierMatchDto`.
- Both PC queue enums and both console queue enums — the 403 precedes validation, so even
  a deliberately invalid queue name could not be shown to 400.
- All console DTOs and the console shard-coverage table.
- `recent-matches` behaviour: the 10-minute window, the 12-hour esports window, and the
  NA/LATAM/BR combined deployment.
- The claim that a match 404s from the wrong shard.

### Reproducing

The probe scripts used are not committed; the sequence was: auth and routing, shard
sweep, `val-content-v1` shape, `val-ranked-v1` shape and bounds, `account-v1` with a
PUUID lifted from the leaderboard, then the gated `val-match-v1` and console endpoints.
The leaderboard is the practical trick — it hands you a real, live PUUID without needing
anyone's Riot ID.
