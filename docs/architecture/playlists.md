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

### Staff UI for FASE D (`/staff/social/spotify/`)

The page now renders three independent sections so the operator can
sync each cadence in isolation:

1. **Playlists públiques setmanals** (yellow-bordered, top section,
   only shown when at least one `freq=weekly` row exists). The 5
   mirrors of the weekly chart. Each row shows the latest published
   sync KPIs (`coverage` = last `last_n_matched / last_n_tracks`)
   AND a predictive `target_coverage` (of the cançons the next sync
   would push, how many already have `SpotifyMetadata.found`). The
   target column tells the operator "if I press Sync weekly now,
   will 95 % of the chart land, or only 40 %?" without hitting
   Spotify. A pair of buttons triggers `--freq weekly` (dry-run or
   wet).

2. **Playlists provisionals diàries**. The daily-top rows
   (TopProvisional sources). Same KPI layout, dedicated
   `--freq daily` buttons.

3. **Triage no verificades**. 6 chunks of 100 cançons each (capped from 7
   on 2026-06-06: the old no-verif-7 became the permanent
   `novetats_per_verificar` work list). They ride the daily cron.

The `target_coverage` field is computed on every `/estat/` call. For
weekly rows it reads `TopSetmanal` for the latest `setmana` per
territori; for daily rows it reads `TopProvisional`; for
no_verificades it slices the same `pendents()` window the cron uses
and counts the chunk. Crossing the 95 % threshold for the weekly
mirrors is the signal that the first wet sync is worth running.

### FASE D status (2026-05-23)

The 5 weekly rows now exist as `SpotifyPlaylist` entries (migration
0082). `SpotifyPlaylist.freq` selects between TopProvisional (daily)
and TopSetmanal (weekly) at sync time. The `--freq` flag on
`actualitzar_playlists_spotify` filters which rows a run touches.

**The weekly cron is registered but COMMENTED OUT** in
`deploy/cron.topquaranta` pending the first manual wet sync. To
activate after this PR merges:

1. SSH into the box and run:
   ```bash
   sudo -u topquaranta tq-run actualitzar_playlists_spotify --freq weekly
   ```
2. Inspect `last_n_matched / last_n_tracks` on the 5 weekly rows. The
   first run can legitimately have a partial match because the cache
   (`SpotifyMetadata.spotify_id`) only contains tracks Process B has
   already resolved. Coverage will climb as Process B walks the
   backlog over the following days.
3. Open the 5 playlists at `https://open.spotify.com/playlist/<id>` and
   confirm the tracks look right.
4. Uncomment the `0 10 * * 6 ... --freq weekly` line in
   `deploy/cron.topquaranta` and push via the normal Mac -> PR -> CI
   -> deploy flow. The Saturday 10:00 UTC tick will start syncing
   weekly from then on.

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

## Spotify enrichment (Process B)

Distinct from the sync cron (Process A) that writes the 12
playlists. Process B is a one-shot enrichment pass that pulls
Spotify metadata back into the DB so the public site can render
Spotify-canonical artist images and disambiguate Deezer-collapsed
artists.

Process B landed on 2026-05-22 alongside the Process A cache-only
refactor (see ADR-0013). The two processes are now strictly
separated:

  * Process A (`actualitzar_playlists_spotify`): cache-only. Reads
    `SpotifyMetadata.spotify_id` and pushes via `/items`. Never
    calls `/v1/search`. Safe to run on any cadence.
  * Process B (`enriquir_spotify`): one-shot per Cançó. Calls
    `/v1/search` then `/v1/tracks/{id}` and `/v1/artists/{id}`.
    Throttled (default 0.5s between calls). Writes the cache.

**Manual links + hydration** (`enrichment_status='manual'`, 2026-06-02).
Staff paste a track URL in the canço editor (`PATCH /staff/cancons/<pk>/
{spotify_url}`, see `staff.md`): format validated, **no API call**. The id
lands in `SpotifyMetadata.spotify_id` (mirrored to `Canco.spotify_id`) with
status `manual`, `enriched_at=NULL`. Process A puts it in playlists instantly
(reads `LOCKED_STATUSES = (found, manual)`). Process B **skips `/v1/search`**
for it but still hydrates: phase 2 of `enriquir_spotify` (after the search
pass, cap `--hydrate-limit` 50) selects `status=manual AND enriched_at IS
NULL` and runs `get_track` + `get_artist` from the known id — filling
`spotify_artist_id` + the rest and recomputing dispersion (hydrated manuals
count like `found`). The id is never re-resolved. `enriched_at` is stamped on
success or on a `get_track` 404 (bad pasted id → "failed" state in the editor,
not retried). The `/search` queue and `enriquir_spotify_rebuigs` both exclude
`LOCKED_STATUSES`. Fill-when-empty only; `spotify_url=""` clears to
`not_attempted`.

Source ordering inside Process B is **priority-tiered** (2026-06,
replacing the earlier pending equity floor). Tiers are concatenated in
order, deduped, truncated at `--limit`, so a charting song is never
stuck behind the backlog:
  1. Cançons in the current public top (latest `TopSetmanal`, any
     territori).
  2. Cançons in the provisional top (`TopProvisional`, any territori).
  3. Pending (`verificada=False, activa=True`) WITH an `ml_confianca`,
     most confident first.
  4. Pending WITHOUT an `ml_confianca`, oldest first.
  5. The verified backlog (`verificada=True`) by latest
     `SenyalDiari.lastfm_playcount desc`, NULLs last.
The two pending tiers keep the **caducitat guard** (the 04:00 purge only
sweeps `verificada=False`); tiers 1-2 are current-chart (never caducades)
and tier 5 is verified (never purged), so caducat pending is excluded
from every tier — it is never selected. `--pending-floor-frac` is kept
for back-compat but no longer alters selection (the tiers subsume the
old floor). Why tiers replaced the floor: the equity floor still let a
top-charting song wait behind hundreds of pending; surfacing the public
+ provisional top first is what actually matters for the listener.

Candidate **visibility is a LEFT JOIN** on `SpotifyMetadata`: a Canço
with no row has never been attempted, so it counts exactly like
`not_attempted` (the row is created lazily by `_enrich_one` via
`get_or_create`). Before this, ~420 cançons ingested after the one-shot
backfill (migration 0080) had no row and were invisible to the
inner-join candidate query. `isrc` must be non-NULL and non-empty.

Flags:
  * `--limit N` caps per-run work (default 200; the cron uses **250**
    since the 2026-06 throughput raise — drains the ~1.5 k
    `not_attempted` backlog in ~6 days vs ~31 at 50/day).
  * `--throttle FLOAT` overrides the per-call sleep (default 0.5; cron
    **0.5** → ~120 req/min, well under Spotify's ~180 req/30s window).
  * `--pending-floor-frac FLOAT` (default 0.5) reserves that fraction of
    `--limit` for pending cançons.
  * `--retry-not-found` cycles through previously-not-found
    cançons after the main pool is exhausted.
  * `--target-playlists` narrows the pool to Cançons currently
    in any active SpotifyPlaylist window. Used for the first
    cold-cache run only; regime cron runs without it.

Dispersion signal: every successful Process B run calls
`music.spotify_dispersio.recalcular_dispersio` for the affected
artistes. `Artista.spotify_artist_dispersio` ends up as the count
of distinct PRINCIPAL `spotify_artist_id` values across that
artist's enriched cançons. `>1` is the canonical signature of a
Deezer name-collapse (Crim-style); the staff triage workbench
surfaces it as a "possible barreja" badge. A standalone command
`recalcular_dispersio_spotify` re-runs the full-DB calc when an
operator needs to refresh it.

### Two purposes, one column on Canco

The cached `Canco.spotify_id` (a 22-char Spotify track ID written
by `actualitzar_playlists_spotify` after a successful
`search_isrc` resolution) does double duty:

1. **Distribution.** `spotify:track:<id>` URIs feed
   `replace_playlist_tracks` (Process A) so the playlist sync
   stays cheap on repeat runs.
2. **Disambiguation.** The Spotify track JSON includes an
   authoritative `artists[]` list with stable Spotify artist IDs.
   When Deezer collapses two distinct artists under one ID
   (caught at the Crim / D5 incident, see CLAUDE.md), the
   Spotify mapping lets us split them on the canonical Spotify
   identity rather than guessing from name strings.

### Field availability (empirical, 2026-05-22)

Single-fetch via `GET /v1/tracks/{id}` and `GET /v1/artists/{id}`,
both HTTP 200 for the prod app. Full table at ADR-0012.

Available fields (track):

| Field | Use case |
|---|---|
| `id`, `uri`, `name`, `duration_ms`, `explicit` | always populated |
| `external_ids.isrc` | cross-check our own `Canco.isrc` |
| `album.images` (3 sizes) | cover art fallback if Deezer is missing |
| `album.release_date` | release_date precision (day/month/year) |
| `album.album_type` (single / album / ep) | type classification |
| `artists[].id`, `artists[].name`, `artists[].uri` | disambiguation anchor |
| `is_playable` | per-market playability flag |

Available fields (artist):

| Field | Use case |
|---|---|
| `id`, `uri`, `name` | canonical identifier |
| `images` (3 sizes) | artist cover image |
| `external_urls.spotify` | open.spotify.com link for "Escolta-ho a" |

Dead fields (always NULL on our app, do NOT rely on):
`track.popularity`, `track.preview_url`, `track.available_markets`,
`artist.genres`, `artist.popularity`, `artist.followers`.
Dead endpoints (403 Forbidden): `/v1/tracks?ids=...`,
`/v1/artists?ids=...`, `/v1/audio-features/{id}`,
`/v1/audio-analysis/{id}`.

The signal we feed the ranking comes from Last.fm; the rich
metadata comes from Deezer and MusicBrainz. Spotify is identifier
+ disambiguation only. See ADR-0012 for the constraint rationale
and ADR-0009 for the identity-migration backstory.

### Batch limitation

The batch endpoints (`/v1/tracks?ids=`, `/v1/artists?ids=`) are
Forbidden for our app. Process B does one HTTP request per
Canco, throttled to 0.2s by default (the
`UserSpotifyClient.DEFAULT_THROTTLE_S` constant added in the
2026-05-22 rate-limit mitigation). A full pass over ~2000 Canco
rows takes ~7 minutes (well within any reasonable cron slot).

### Idempotence

Process B is gated by `SpotifyMetadata.enrichment_status`:
  * `not_attempted` -> picked up on the next run.
  * `found` -> skipped (we already have the cache).
  * `not_found` -> skipped UNLESS `--retry-not-found` is set, in
    which case the oldest `enriched_at` are re-attempted first so
    each retry cycle walks the pool evenly.

The OneToOne `Canco -> SpotifyMetadata` link plus the
`enriched_at` timestamp suffice to drive idempotence; no separate
queue table.

### Caching post-write

After a `/items` write, the legacy `GET /v1/playlists/{id}`
endpoint returns `tracks.total=0` for migrated apps. Monitoring
that needs an authoritative count must use
`GET /v1/playlists/{id}/items?limit=1` and read `total` from the
paging envelope. This affects F.2 (`check_spotify_coverage`)
which we will likely re-point at the `/items` endpoint when
Process B lands. Documented at ADR-0012.

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
- ADR-0012: Web API capabilities for new apps (empirical, 2026-05-22).
- `ingesta/clients/spotify.py` — both clients (Client Credentials
  for catalog reads, refresh-token-backed for playlist writes).
- `ingesta/management/commands/actualitzar_playlists_spotify.py`
  — daily + weekly cron entrypoint.
- `web/api/staff/social/spotify.py` — staff UI backend.
- `web-react/src/pages/staff/StaffSocialSpotifyPage.jsx` —
  staff UI frontend.
- `music/models.py::SpotifyAuth`, `::SpotifyPlaylist` — singletons +
  per-playlist row.
