# Playlists

External-DSP output of the TopQuaranta ranking. Today: Spotify
only (10 managed playlists). Planned: YouTube Music — declined for
now per ADR-0010. Deezer — backlog (no ADR yet).

This doc is the architectural reference; FASE-by-FASE implementation
detail lives at the corresponding ADRs and in the revival sprint
commits (`feat/playlists-*` branches).

## Why this exists

The ranking is a database table. Most users discover music through
DSPs (Spotify primarily, YouTube Music + Apple Music secondarily).
A playlist that mirrors the live ranking on Spotify closes the loop:
the user follows the playlist once, then sees TopQuaranta's editorial
output appear in their own Spotify library every cycle.

> **History.** The Spotify sync was built in commit `5adc898`
> (2026-04-20) and went live in name only. The cron ran daily but
> failed every tick with `CommandError: No hi ha autorització
> Spotify` because the one-time OAuth dance had never been
> completed on prod. The `cron-meta.json::silenced=true` flag
> kept `tq-health` quiet. A second blocker surfaced in May 2026:
> Spotify Web API requires Premium on the app owner since late
> 2024, and the previous app owner had a free plan. ADR-0009
> documents the migration to `admin@topquaranta.cat` + Premium;
> the FASE B staff UI replaces the SSH-only OAuth dance; FASE D
> splits the sync into daily-every-6h + weekly-Saturday cadences
> (ADR-0011).

## Flow

```
ranking (TopProvisional, TopSetmanal)
  ↓
SpotifyPlaylist row selects which (freq, kind, territori) it tracks
  ↓
ingesta/management/commands/actualitzar_playlists_spotify
  ↓ ISRC search (cached on Canco.spotify_id)
  ↓
ingesta/clients/spotify.py::UserSpotifyClient.replace_playlist_tracks
  ↓ PUT /v1/playlists/<id>/tracks  (first 100)
  ↓ POST /v1/playlists/<id>/tracks (rest, chunks of 100)
  ↓
Spotify Web API → public playlist URL stays stable
```

The PUT is idempotent: it replaces the entire tracklist in place.
Followers keep their subscription; the URL keeps its `/playlist/<id>`
shape; only the inner tracks change. This is how every "official
Spotify-curated" playlist works (e.g. Discover Weekly under the
hood).

## 10 managed playlists

| codi | kind | freq | territori | Spotify playlist ID | source |
|---|---|---|---|---|---|
| top-cat-daily | top | daily | CAT | `0Vzdo5gpRPeSBpWVFUKE1G` | TopProvisional |
| top-val-daily | top | daily | VAL | `0zt9V8u8lRsgdPPRVIc9kC` | TopProvisional |
| top-bal-daily | top | daily | BAL | `2MMTTGmQkpte20Ripx3hxa` | TopProvisional |
| top-alt-daily | top | daily | ALT | `3qvaDqSrhbvrR5TOvANEvp` | TopProvisional |
| novetats-daily | novetats | daily | — | `4nBIangCLrNMFj0L1Uj2jb` | Canco.data_llancament |
| top-ppcc-weekly | top | weekly | PPCC | `75IQLLWrOrJ1BaJc1RlJeY` | TopSetmanal |
| top-cat-weekly | top | weekly | CAT | `2rjDevnzE7qPphdrxAhYOT` | TopSetmanal |
| top-val-weekly | top | weekly | VAL | `5yMimy5GaaG5ipQadbm1Yq` | TopSetmanal |
| top-bal-weekly | top | weekly | BAL | `4GhnQ4rvBPJxwBH0PJ3QKK` | TopSetmanal |
| top-alt-weekly | top | weekly | ALT | `4ts0Pyov3qnexNGrk6wWul` | TopSetmanal |

Notable: **`top-ppcc` only exists at the weekly cadence.** The
daily PPCC playlist was never created at the Spotify Dashboard.
If product wants it later, the path is `SpotifyPlaylist.objects.create(...)`
+ `configurar_spotify_playlists --top-ppcc-daily <id>`.

## Schedule (ADR-0011)

```cron
# Daily, every 6h (00, 06, 12, 18 UTC)
0 */6 * * *  topquaranta  ... actualitzar_playlists_spotify --freq daily

# Weekly, Saturday 10:00 UTC (30 min after publicar_social)
0 10 * * 6   topquaranta  ... actualitzar_playlists_spotify --freq weekly
```

The 6h cadence is the empirical compromise between user-visible
freshness (≤6h delay from a TopProvisional change) and quota /
log volume / chances-of-catching-a-transient-5xx.

## Auth

* `SpotifyAuth` row (singleton, `pk=1`) holds the OAuth refresh
  token minted via `/staff/social/spotify/`. The page exchanges
  the `code` returned by Spotify for the refresh token, validates
  that `me().product == "premium"`, and persists.
* `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` live in `.env`
  and belong to the Spotify Developer app under
  `admin@topquaranta.cat`.
* `SPOTIFY_REDIRECT_URI` defaults to
  `https://www.topquaranta.cat/staff/social/spotify/callback`
  (registered at the Spotify Dashboard). The legacy
  `/spotify/callback` route is kept for the SSH `autoritzar_spotify`
  fallback flow.

## Monitoring (FASE F — pending)

Two checks planned, fired from `tq-health`:

1. **`spotify_premium_active`** — weekly. `GET /me` and assert
   `product == "premium"`. Premium lapse silently breaks the
   cron with 403; this catches it within 7 days of the lapse,
   well before the credit-card retry cycle would re-activate it.
2. **`spotify_coverage`** — daily. Read `SpotifyPlaylist`; alert
   WARN if `last_n_matched / last_n_tracks < 0.85`, CRITICAL if
   < 0.50. Coverage that suddenly dips usually means ISRC drift
   in the upstream Last.fm/Deezer data; a 50%+ dip means a major
   ingestion failure upstream.

## Embeds (FASE E — pending)

Three SPA pages will embed the relevant playlist via Spotify's
public iframe widget:

* Homepage → `top-ppcc-weekly`
* `/ranking/<territori>/` → `top-<territori>-weekly`
* `/novetats/` → `novetats-daily`

The embed is server-less (Spotify hosts the iframe), `loading="lazy"`,
and doesn't ship the Spotify SDK. No JS-CDN cost on the page-load
critical path.

## Backlog: Deezer

The "Escolta-ho a" component already builds a direct Deezer URL
(`https://www.deezer.com/track/<deezer_id>`) for every track on
the site, thanks to ~100% Deezer ID coverage on `Canco`. A
managed playlist on Deezer would be a natural second output:

* No Premium required on the app owner (Deezer's policy stayed
  open after Spotify's 2024 squeeze).
* OAuth flow shape similar to Spotify (refresh-token-backed).
* `/track/isrc:<value>` endpoint supports exact ISRC lookup,
  matching Spotify's coverage promise.
* `DeezerAuth` + `DeezerPlaylist` models would mirror the Spotify
  ones; the management command could be parameterised by DSP
  rather than duplicated.

Not in the current sprint. Open work item: refactor `SpotifyAuth`
+ `SpotifyPlaylist` into a generic `DSPAuth` + `DSPPlaylist` base
when adding the second DSP, so we don't end up with three
half-parallel implementations.

## Backlog: YouTube Music

Declined per ADR-0010. Re-evaluate 2027-05 or sooner if any of the
ADR-0010 triggers fires.

## Backlog: Apple Music

No ADR yet. Apple's MusicKit API requires the Apple Developer
Program ($99/year) + JWT-signed requests. Probably the same
"declined for now" outcome as YouTube Music, but worth a
proper ADR when the time comes.

## Related

- ADR-0009 — Spotify identity migration.
- ADR-0010 — No YouTube Music.
- ADR-0011 — Cron schedule.
- `ingesta/clients/spotify.py` — both clients (Client Credentials
  for catalog reads, refresh-token-backed for playlist writes).
- `ingesta/management/commands/actualitzar_playlists_spotify.py`
  — daily + weekly cron entrypoint.
- `web/api/staff/social/spotify.py` — staff UI backend.
- `web-react/src/pages/staff/StaffSocialSpotifyPage.jsx` —
  staff UI frontend.
- `music/models.py::SpotifyAuth`, `::SpotifyPlaylist` — singletons +
  per-playlist row.
