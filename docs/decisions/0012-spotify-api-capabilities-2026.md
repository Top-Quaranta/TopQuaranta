# ADR-0012: Spotify Web API capabilities for new apps (post-2026)

- **Status:** Accepted
- **Date:** 2026-05-22
- **Authors:** Miquel

## Context

Two consecutive Spotify policy waves have reshaped what a Web API
app can do, in ways the official docs only describe partially:

1. **"Wave One" (November 2024).** Spotify retired or app-gated a
   set of metadata fields and endpoints for newly registered apps:
   `track.popularity`, `track.preview_url`, `track.available_markets`,
   `artist.genres`, `artist.popularity`, `artist.followers`,
   `audio-features`, `audio-analysis`, the batch endpoints
   `/v1/tracks?ids=` and `/v1/artists?ids=`, and the `/me/player/*`
   family for apps that do not have Web Playback SDK approval. The
   change is silent: new apps simply see `null` on the affected
   fields and `403 Forbidden` on the affected endpoints, with no
   message hint in the response body.

2. **"Items migration" (February 2026).** Spotify deprecated
   `PUT|POST /v1/playlists/{id}/tracks` and replaced it with
   `/v1/playlists/{id}/items`. The shape of the request body and
   the snapshot response are unchanged. Apps registered after the
   migration date receive `403 Forbidden` on the old path, again
   with no helpful body. This is the immediate cause of the
   2026-05-22 outage that resolved on PR #66.

We ran a read-only empirical probe of the production TopQuaranta
app (client_id `85ec8b676ee048839c94a57515bb8665`) against three
real cached track IDs on 2026-05-22 to lock in what we actually
get back vs what the docs claim. Results below.

## Empirical capabilities table (2026-05-22, prod app)

### `GET /v1/tracks/{id}` (single, HTTP 200)

| Field | State | Notes |
|---|---|---|
| `id`, `uri`, `name`, `type` | populated | always present |
| `duration_ms` | populated | int, ms |
| `explicit` | populated | bool |
| `external_ids.isrc` | populated | matches our `Canco.isrc` |
| `is_playable` | populated | bool, per-market |
| `track_number`, `disc_number` | populated | int |
| `album.name`, `album.release_date` | populated | release_date_precision present |
| `album.album_type` | populated | `single` / `album` / `ep` |
| `album.images` | populated | three sizes (640, 300, 64) |
| `artists[].id`, `artists[].name`, `artists[].uri` | populated | nested |
| `popularity` | **NULL** | Wave One |
| `preview_url` | **NULL** | Wave One |
| `available_markets` | **NULL** | Wave One |

### `GET /v1/artists/{id}` (single, HTTP 200)

| Field | State | Notes |
|---|---|---|
| `id`, `uri`, `name`, `type` | populated | always present |
| `images` | populated | three sizes |
| `external_urls.spotify` | populated | open.spotify.com URL |
| `genres` | **NULL** | Wave One |
| `popularity` | **NULL** | Wave One |
| `followers` | **NULL** | Wave One |

### Batch endpoints

| Endpoint | Status | Notes |
|---|---|---|
| `GET /v1/tracks?ids=<csv>` | **403 Forbidden** | Wave One |
| `GET /v1/artists?ids=<csv>` | **403 Forbidden** | Wave One |

There is no Premium upgrade or scope addition that re-enables these
for the current app. Single-fetch only.

### Other gated endpoints

| Endpoint | Status |
|---|---|
| `GET /v1/audio-features/{id}` | **403 Forbidden** |
| `GET /v1/audio-analysis/{id}` | not tested, expected 403 |
| `PUT|POST /v1/playlists/{id}/tracks` | **403 Forbidden** (replaced by `/items`) |

### Endpoints that DO work (read + write)

| Endpoint | Status | Used by |
|---|---|---|
| `GET /v1/me` | 200 | OAuth callback + F.1 health check |
| `GET /v1/playlists/{id}` | 200 | rarely (see note below) |
| `GET /v1/playlists/{id}/items` | 200 | accurate item counts post-migration |
| `PUT /v1/playlists/{id}` (metadata) | 200 | unused today |
| `PUT|POST /v1/playlists/{id}/items` | 200 | core of the sync cron |
| `GET /v1/search?q=isrc:...` | 200 (rate limited) | URI resolution |
| `GET /v1/tracks/{id}` | 200 | future Process B enrichment |
| `GET /v1/artists/{id}` | 200 | future Process B enrichment |

Note on `GET /v1/playlists/{id}`: after a `/items`-based write the
legacy `tracks.total` field on this endpoint stops refreshing (it
shows the count from before the migration cutoff or 0). For an
accurate count post-migration use `GET /v1/playlists/{id}/items?limit=1`
and read `total` from the paging envelope. We surfaced this on
2026-05-22 when the cache-only validation run reported every
playlist as `tracks.total=0` despite `last_n_matched > 0` in our DB.

## Decision

Spotify is the source of two things only:

1. **A canonical identifier** (`spotify:track:<id>`,
   `spotify:artist:<id>`) for distribution into Spotify playlists
   and embeds.
2. **A disambiguation oracle** for the artist mapping (`Canco`
   has a Spotify-canonical `Artista` association via the cached
   `spotify_id`, which is independent of Deezer's name-collapsing
   collisions, see CLAUDE.md "Multi-Deezer-ID iteration").

Spotify is NOT the source of any rich metadata. Specifically:

- **Popularity / playcount / followers / genres** never come from
  Spotify. Last.fm provides our signal (`playcount` + `listeners`
  via `obtenir_senyal`); Deezer provides our metadata at scale
  (cover art, release date, full discography, audio previews via
  the public preview URLs); MusicBrainz is the disambiguation
  oracle for artists (MBID + area + tags + work language).
- **Audio analysis** (BPM, energy, valence, key) is unavailable.
  If we ever need it, AcousticBrainz is the open-data alternative
  keyed by MBID; no Spotify call is involved.
- **Batch operations** are unavailable. Process B (track / artist
  enrichment) must dispatch one HTTP request per item with the
  throttle from ADR-0009 sister fix (`UserSpotifyClient.throttle_s`,
  default 0.2s).

## Consequences

- **Enrichment is one-shot, not real-time.** A future Process B
  (planned, no commit yet) walks `Canco.objects.public()` rows
  with `spotify_id IS NOT NULL` and pulls the per-track JSON
  once, then persists the new fields (album.images cache, artist
  cover image). It does NOT run every sync; once a Canco has been
  resolved + enriched, the values are durable in the DB.
- **Ordering for the no_verificades triage windows uses
  `ml_confianca DESC` from our own classifier**, not Spotify
  popularity (which is NULL anyway). Decided independently on
  PR #64.
- **No "discovery" features driven by Spotify.** We won't ever
  consume Spotify's recommendation graph (related artists, audio
  fingerprint similarity, taste profile). The product is curated
  through Last.fm + Deezer + MB + staff verification, and Spotify
  is downstream.
- **The 0.2s throttle (ADR-0009 sister fix) is the floor for
  any future bulk job.** Single-fetch endpoints have a separate
  budget from `/search`, and we never hit either bucket hard
  enough to trip an outage under the cron schedule of ADR-0011.
- **Re-test the capabilities table when Spotify ships the next
  policy wave.** Spotify hasn't published a deprecation calendar;
  the next "Wave" usually shows up in a Developer Community thread
  before the official changelog. Re-run the probe script (saved
  at `scripts/archived_commands/` for posterity, not part of
  hot-path code) when in doubt.

## Cross-references

- [ADR-0009: Spotify identity migrated to admin@topquaranta.cat](0009-spotify-identity-migration.md):
  the Premium / OAuth foundation.
- [ADR-0010: Why not YouTube Music (for now)](0010-why-not-youtube-music.md).
- [ADR-0011: Spotify cron schedule](0011-spotify-cron-schedule.md):
  the daily + weekly cadence that consumes this API budget.
- `docs/architecture/playlists.md::Spotify enrichment (Process B)`:
  the design space this ADR constrains.
- PR #66 (`fix/spotify-playlists-items-migration`): the one-line
  endpoint fix for the February 2026 migration.

## Test that produced this table (2026-05-22)

Run by a one-off Python script, NOT committed to the repo because
it queries the live Spotify API. The script:

1. Loads `SpotifyAuth` from prod, refreshes the access token.
2. Picks 3 cached Cançons (`Canco.spotify_id IS NOT NULL`).
3. Hits `GET /v1/tracks/{id}` for each, dumps full JSON of the
   first response and tabulates field-by-field nullity for all
   three.
4. Repeats with `GET /v1/artists/{id}` for the 3 derived artist
   IDs.
5. Probes `GET /v1/tracks?ids=`, `GET /v1/artists?ids=`,
   `GET /v1/audio-features/{id}` to confirm the documented
   403 status codes.

The 3 tracks used as fixtures were Cançons currently in the
no_verificades window, so the IDs themselves are not stable; the
test should pick fresh fixtures on every re-run. Numbers above
match the run completed at 2026-05-22 13:24 UTC.
