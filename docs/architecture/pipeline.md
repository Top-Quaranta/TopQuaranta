# CLAUDE_PIPELINE.md — Ingest → Signal → Ranking

> Daily + hourly automation. All commands run as user `topquaranta` from
> `/etc/cron.d/topquaranta`, with `DJANGO_SETTINGS_MODULE=topquaranta.settings.production`.

---

## 1. Overview

```
     Deezer (hourly, obtenir_novetats)     Last.fm (daily, obtenir_senyal)
           │                                        │
           ▼                                        ▼
   new Canco (verificada=False)              SenyalDiari (raw playcount)
           │                                        │
   staff review → verificada=True ──────────────────┤
                                                    ▼
                                     calcular_ranking (daily provisional,
                                                       Saturday official)
                                                    │
                               weekly_plays = playcount_today
                                              − playcount_7_days_ago
                                    × age_factor
                                    × past_top_factor
                                    × monopoly (album / artista)
                                                    │
                                                    ▼
                                     RankingProvisional / RankingSetmanal
```

## 2. API clients (`ingesta/clients/`)

All clients import `DEEZER_RATE_LIMIT`, `LASTFM_RATE_LIMIT`, `MAX_API_RETRIES`
from `music/constants.py`. Never raise — return `None` on any failure.

### `deezer.py` — primary metadata source
- Public API, no auth. Base: `https://api.deezer.com`.
- Rate limit 1.0 s, retry 3× with exponential backoff.
- Detects error code 4 ("Quota limit exceeded"), sets a session-scoped flag
  that stops further calls until next day (`quota_exhausted()`).
- Functions: `search_artist`, `get_artist_info`, `get_artist_albums`,
  `get_album_tracks`. Returns dict or `None`.

### `lastfm.py` — daily signal
- Endpoint: `track.getInfo?autocorrect=1`.
- Rate 0.2 s, retry 3×.
- On error 6 ("Track not found"), automatically retries once with the track
  name normalized: strips `(feat. X)`, `(Acoustic Version)`, `- Live`, `- Remix`,
  etc., and converts Unicode quotes to ASCII. Recovers ~10–15% of errors.

### `spotify.py` — playlist output (active since 2026-04)
- Two classes. `SpotifyClient` is the legacy Client-Credentials wrapper
  (ingest endpoints no longer available to us since Spotify gated Web API
  behind Premium in 2024).
- **`UserSpotifyClient`** is the live path: OAuth refresh-token flow for the
  admin account. Rotates access tokens on 401 mid-flight, honours 429
  `Retry-After`, persists a rotated refresh_token when Spotify issues one.
  Supports `search_isrc()` for resolution and chunked
  `replace_playlist_tracks()` for the daily sync (§3.9).
- Scopes used: `playlist-modify-private playlist-modify-public`.

## 3. Management commands

### Rules (all commands)
- `self.stdout.write()`, never `print()`.
- `raise CommandError(...)`, never `sys.exit()`.
- All DB writes inside `transaction.atomic()`.
- Idempotent where possible.
- Final line: counts of processed / success / errors.

### 3.1 `obtenir_senyal` — daily 06:00
```bash
python manage.py obtenir_senyal [--data YYYY-MM-DD] [--limit N] [--dry-run]
```
Selects `verificada=True AND activa=True AND artista.aprovat=True AND
data_llancament ≥ today - DIES_CADUCITAT` tracks, calls Last.fm per
track, writes raw cumulative `lastfm_playcount` + `lastfm_listeners`
into `SenyalDiari`. Skips tracks already ingested for that date
(idempotent). No post-processing — the former `score_entrada`
normalisation was removed in algorithm v2.0 (2026-04-23); the
ranking consumes the raw counts directly.

### 3.2 `calcular_ranking`
```bash
python manage.py calcular_ranking [--setmana YYYY-MM-DD] [--territori CODE]
                                   [--dry-run] [--provisional]
```
- Without `--provisional`: writes `RankingSetmanal`. Run Saturday 08:00.
  Territories processed: `TERRITORIS_FIXOS = {CAT, VAL, BAL}` + aggregates
  `{ALT, PPCC}`. Each territory is `delete + bulk_create` inside a transaction
  (prevents stale entries from previous runs).
- With `--provisional`: writes `RankingProvisional`. Run daily 07:00. Includes
  all eligible territories (fixed + aggregates + optional if they cross the
  `min_cancons_ranking_propi` threshold).
- Aggregates (ALT, PPCC) must run last — they read the just-computed individual
  rankings in memory (`algorisme.calcular_ppcc_ranking` calls the per-territory
  function for each source territory).

### 3.3 `obtenir_novetats` — hourly (every :00)
```bash
python manage.py obtenir_novetats [--limit N] [--dry-run]
```
Incremental Deezer ingestion with a 3-tier priority queue:
- **P1** — tracks with `deezer_id` but no ISRC; fetches full track to backfill.
- **P2** — albums with `cancons_obtingudes=False`; fetches tracks.
- **P3** — approved artists, oldest `last_checked_deezer` first; fetches albums
  released within `DIES_CADUCITAT` days.

Uses an `fcntl.flock` on `/tmp/obtenir_novetats.lock` — if a run is still
going, the next hour's run exits cleanly. All created Canco records start
with `verificada=False`; `classificar_i_guardar(canco)` applies the ML class.

### 3.4 `obtenir_metadata` — on demand
```bash
python manage.py obtenir_metadata [--artista-id N] [--force] [--dry-run] [--limit N]
```
For approved artists without an `ArtistaDeezer` link, resolves the
Deezer ID (name search + ISRC cross-validation) and pulls albums +
tracks. Previously the filter was `deezer_no_trobat=False`, but that
flag is a stale cache — the signal-cleared M2M relation is the source
of truth, so the command now targets `deezer_ids__isnull=True`
artists. The flag is still written on the failure path for
backwards-compat readers.

Not in the cron by default — run on demand when staff approves a
batch of new artists without Deezer ids, or before a marketing push
that needs fresh fan counts.

### 3.5 `analitzar_whisper` — nightly 05:00 UTC
```bash
python manage.py analitzar_whisper [--limit N] [--refresh-older-than DAYS]
                                    [--canco-id PK] [--dry-run]
```
Runs `faster-whisper large-v3 .detect_language()` on each Canco's
30-second Deezer preview. Populates `Canco.whisper_lang`,
`whisper_p`, `whisper_all_probs` (99-lang JSON), `whisper_processat_at`.
Processes tracks never analysed first, optionally re-analyses rows
older than N days. Cron window is 05:00 with `--limit 100` (~45 min
worst case at ~27 s/track on CPU, finishing well before the 06:00
signal step). Backfill of the historical ~6.7k catalogue completed
2026-04-25 — from now on the daily intake is <50 tracks/night.

See `scripts/model_comparison/resultats.md` for the eval numbers
that justified this integration.

### 3.6 `obtenir_metadata_musicbrainz` — hourly at minute 30
```bash
python manage.py obtenir_metadata_musicbrainz [--refresh-days N]
                                              [--limit N] [--artista-id PK]
```
Pulls MusicBrainz metadata into our Artista / Album / Canço rows.
Single-instance `fcntl.flock` on `/tmp/mb_sync.lock`; MB's 1 req/s
rate limit is globally enforced by the client.

Per artist the flow is:
  0. **Validate the existing MBID** (added 2026-04-29). If the
     artista has both an MBID and PPCC `localitats`, fetch the MB
     artist's `area` and check it's PPCC-compatible. If MB explicitly
     says non-PPCC (e.g. "United States"), the MBID is auto-unassigned
     + added to `mb_blocked_mbids` + audit-logged
     (`artista_mbid_auto_unassign`) + the artist's Cançons/Albums
     have their MB fingerprints reset. This catches accumulated drift
     from the pre-2026-04-29 score-based auto-resolver. After
     unassign, step 1 re-attempts a clean match.
  1. If no `musicbrainz_id`: `resolve_mbid(artista)` →
     `search_artist(nom)` then disambiguate ourselves on **name +
     location**, ignoring MB's Lucene score as a quality signal.
     Rules (post 2026-04-29):
       * Exact-name match (case-insensitive), score ≥ 50 (loose
         floor — see `MB_AUTO_MATCH_SCORE`).
       * If our `Artista` has **localitats** in PPCC: keep candidates
         whose MB `area` matches PPCC. One match → accept. Zero or
         multiple → refuse (staff picks).
       * If our `Artista` has **no localitats**: refuse — we can't
         disambiguate honestly without a location anchor.
     History: pre-2026-04-29 the score floor was 95 and the location
     check only ran on multi-candidate ties; the "Casual" homonym bug
     (US rapper at 100 vs CAT band at 91) prompted the rewrite.
     Ambiguous names (Crim, Apa, …) still get skipped; staff sets
     the MBID by hand.
  2. Otherwise: `get_artist` + `get_artist_release_groups` +
     `get_release_group_with_recordings` → fills type/gender/area/
     begin_date/end_date/disambiguation/sort_name/aliases/tags/rating,
     plus URL relationships (bandcamp/spotify/youtube/youtube music/
     soundcloud/wikipedia/viasona/facebook/myspace — never overwriting
     values staff already set).
  3. **Reset** stale MB-reconciliation fields on this artist's
     existing Albums + Cançons (`mb_release_group_id`,
     `mb_recording_id`, `mb_work_id`, `mb_lyrics_language`,
     `mbrainz_confirmed`) so a corrected MBID purges its predecessor's
     fingerprints. The same `sync_from_mbid()` is also auto-invoked by
     `artista_detail` PATCH whenever staff changes the MBID — caught
     2026-04-29 ("Casual" case).
  4. Reconciles Albums by normalised title (fuzzy 0.9+) →
     `mb_release_group_id`, `mb_type_secondary`, `mb_status`,
     `mbrainz_confirmed=True`.
  5. Reconciles Cançons by ISRC first, then normalised title →
     `mb_recording_id`, `mb_work_id`, `mb_lyrics_language`,
     `mbrainz_confirmed=True`. A `Work.language=='cat'` is logged
     and feeds the `mb_lyrics_cat` ML feature.
  6. Caches `{isrcs, titles}` on `Artista.mb_discography_cache` for
     quick future matches.
  7. Stamps `mb_last_sync` regardless of outcome, so idle retries
     don't thrash.

There is also a one-shot audit command `auditar_mb_orphans` (added
2026-04-29) that sweeps existing rows looking for `mb_recording_id` /
`mb_release_group_id` values that no longer belong to the artist's
current MB discography (i.e. residue from a previous wrong MBID
auto-resolve). `--dry-run` lists; `--apply` resets.

Queue priority: aprovat > pendent > descartat; within each, oldest
`mb_last_sync` first. Refresh every 7 days by default. The cron
exits when nobody needs attention — idle invocations are cheap.

### 3.7 `netejar_caducades` — daily 04:00
```bash
python manage.py netejar_caducades
```
Deletes unverified tracks with `data_llancament < today - DIES_CADUCITAT`.

### 3.8 `obtenir_metadata_lastfm` — daily 05:00 UTC
```bash
python manage.py obtenir_metadata_lastfm [--limit N] [--refresh-days N]
                                         [--artista-id PK] [--dry-run]
```
Pulls Last.fm artist-level metadata into `Artista.lastfm_*` and walks
the `artist.getSimilar` network to surface candidate pendents. Single-
instance `fcntl.flock` on `/tmp/lastfm_artist_sync.lock`. Defaults to
500 artists per invocation; refresh window 7 days.

Per artist (queue order = aprovat → pendent → discartat, then oldest
`lastfm_last_sync`):
  1. `artist.getInfo` → fill bio summary/content, listeners,
     playcount, ontour, tags, four image sizes, url.
  2. `artist.getSimilar` (limit 100, `match >= 0.3`) → for every
     candidate name, find an existing Artista by `lastfm_nom` or
     case-insensitive `nom`. If found, increment
     `nb_similars_lastfm`. Otherwise create a placeholder
     (`pendent_review=True`, `auto_descobert=True`,
     `font_descoberta="lastfm_similar"`, `nb_similars_lastfm=1`).
  3. Stamp `lastfm_last_sync = now()`.

Idempotency is gated by the source artist's recency: re-running on
the same artist within `--refresh-days` is a no-op (the queue skips
it). Within a single sync each similar's counter is incremented
exactly once.

The `nb_similars_lastfm` count surfaces in the staff Artistes /
Pendents lists and in the `LastfmPanel` of `ArtistaEditPage`. Pendents
gains a sort `?sort=similars_lastfm` (high-affinity first) and a
filter `?font_descoberta=lastfm_similar` to triage just this batch.

### 3.9 Utility / ad-hoc commands (not cron-scheduled)
- `recalcular_ml` — force retrain the RF model and reclassify all unverified
  tracks. Normally runs automatically via `recalcular_ml_si_cal()` when 5+ new
  decisions have accumulated.
- `arxivar_senyal_vell` — quarterly archive of SenyalDiari rows older than 2 years
  (Φ6 retention).

**One-shot migrations already executed** live under
`scripts/archived_commands/` (out of `manage.py` reach):
`fix_album_dates`, `fix_artista_principal`, `deduplicar_isrc`,
`backfill_deezer_artistes`, `backfill_preview_url`,
`seed_spotify_playlists`. Preserved for history only.

### 3.10 Spotify playlist sync — daily 07:15 UTC
```bash
python manage.py actualitzar_playlists_spotify [--dry-run] [--only <codi>]
```
Reads every `SpotifyPlaylist` row with a configured `spotify_playlist_id`
and rewrites its tracklist in place. Runs 15 minutes after the provisional
ranking settles.

Per kind:
- `top` → `RankingProvisional.filter(territori=X).order_by('posicio')[:40]`
- `novetats` → `Canco.filter(data_llancament=yesterday, activa=True)[:100]`

Resolves each Canço to a Spotify URI via `UserSpotifyClient.search_isrc()`
and caches the result on `Canco.spotify_id` so subsequent runs skip the
search. Mismatches (ISRC not found on Spotify) are silently dropped; the
`SpotifyPlaylist.last_n_tracks` vs `last_n_matched` fields expose the
mismatch rate per run.

One-time setup (once per Spotify account):
```bash
# Prints the OAuth URL, takes the `code` from the callback, persists
# refresh_token to SpotifyAuth (singleton).
python manage.py autoritzar_spotify

# Attach the existing Spotify playlist IDs to the 5 seeded rows.
python manage.py configurar_spotify_playlists \
    --top-cat <id> --top-val <id> --top-bal <id> --top-alt <id> \
    --novetats <id>
```

## 4. Track verification (ML classifier)

`music/ml.py` — Random Forest (100 estimators, `class_weight="balanced"`)
trained on **7,912** decisions from `HistorialRevisio`. After the
2026-04-25 TF-IDF retall: **49 features** (12 structured + 4 Whisper LID
+ 3 MusicBrainz + 30 TF-IDF char n-grams of the track title). Path
to today: 223 → 76 (slim) → 79 (+ MB) → 49 (TF-IDF cap 60 → 30 after
A/B 5-fold CV proved the smaller cap matched ROC-AUC and improved F1
+ accuracy slightly).

5-fold CV metrics (2026-04-25, 7 730 training rows, max_features=30):
- ROC-AUC **0.9998** · F1 **0.9908** · Accuracy **0.9953**.
- Top 7 features (4 of which are Whisper LID) carry **70%** of the
  signal; estructurals dominate at 95.6 %, TF-IDF only 4.4 %.

Top 5 features by importance (2026-04-25 retrain, max_features=30):
1. `ratio_rebuig_artista` (20.0%) — Bayesian-smoothed (k=5, prior=0.5)
2. `whisper_p_ca` (17.8%) — Whisper LID confidence the track is català
3. `ratio_rebuig_registrant` (10.7%)
4. `whisper_p_en` (9.8%)
5. `whisper_margin_ca` (9.0%)

Bayesian smoothing on the three `ratio_rebuig_*` features: returns
`(rej + k*p) / (total + k)` with `k=5, p=0.5`, so an artist with few
decisions can't collapse to 0 or 1 from one or two calls. Prevents
feedback loops where an early false rebuig biases the model
permanently.

Classes: `A ≥ 0.7`, `B 0.4–0.7`, `C < 0.4`. Stored on `Canco.ml_classe` +
`ml_confianca`. Model files: `music/ml_model.joblib` + `ml_tfidf.joblib`.
Both cached in-memory with mtime-based invalidation.

Retraining triggers automatically via `recalcular_ml_si_cal()` when
≥ `MIN_NEW_DECISIONS=5` records have arrived since last run (marker:
`/tmp/tq_last_ml_recalc`). Runs in a daemon thread. If
< `MIN_TRAINING_SAMPLES=20` decisions exist, `pre_classificar` falls
back to a hand-tuned heuristic.

Live feature importances + training size + class distribution + mean
confidence are surfaced on `/staff/estat` via `/api/v1/staff/estat/`.

## 5. Cron schedule

File: `/etc/cron.d/topquaranta`. Commands go through
`/home/topquaranta/bin/tq-run` which captures each run's exit code and last
output into `/var/log/topquaranta/status/<tag>.status` — consumed by the
health check (§7).

```cron
# Hourly: ingest + metadata refresh
0 * * * *    topquaranta  tq-run obtenir_novetats                 # every hour
30 * * * *   topquaranta  tq-run obtenir_metadata_musicbrainz     # 30 min after novetats

# Nightly pipeline (each step feeds the next)
0 3 * * *    postgres     tq-backup                               # 03:00 DB backup
0 4 * * *    topquaranta  tq-run netejar_caducades                # 04:00 purge expired
0 5 * * *    topquaranta  tq-run analitzar_whisper --limit 100    # 05:00 Whisper LID
0 5 * * *    topquaranta  tq-run obtenir_metadata_lastfm --limit 500  # 05:00 Last.fm artist meta
0 6 * * *    topquaranta  tq-run obtenir_senyal                   # 06:00 Last.fm signal
0 7 * * *    topquaranta  tq-run calcular_ranking --provisional   # 07:00 provisional
15 7 * * *   topquaranta  tq-run actualitzar_playlists_spotify    # 07:15 Spotify sync

# Weekly
0 8 * * 6    topquaranta  tq-run calcular_ranking                 # Sat 08:00 official

# Retention + ops
0 5 1 1,4,7,10 * topquaranta tq-run arxivar_senyal_vell           # quarterly
30 4 1 * *   postgres       tq-restore-test                       # monthly
*/30 * * * * topquaranta    tq-recover                            # recovery sweep
```

Two pacing changes since the original schedule (2026-04-25 sweep):
- `obtenir_metadata_musicbrainz` was `*/15` during the MB backfill;
  now hourly at minute 30 — the queue is empty most of the time and
  the 15-min cadence was just polling for nothing.
- `analitzar_whisper` was 01:30 with `--limit 700` (5 h backfill
  window). Backlog drained 2026-04-25; now 05:00 with `--limit 100`
  (~45 min worst case), so it slots cleanly into the daily pipeline
  before signal ingestion.

## 6. Backups

`/home/topquaranta/bin/tq-backup` runs daily at 03:00 as `postgres`.
Tiered retention in `/home/topquaranta/backups/`:
- `daily/` — last 7 days
- `weekly/` — Sundays, last 4 weeks
- `monthly/` — 1st of month, last 12 months

DB is ~45 MB uncompressed; gzipped ≈ 3 MB per backup. Total retention
worst case ≈ 60 MB.

## 7. Monitoring / health check

No external services. Everything is file-based on the server.

- **`errors.log`** (`/var/log/topquaranta/errors.log`): every `logger.error(...)`
  / `logger.exception(...)` call across the project ends up here (configured
  in `settings/base.py::LOGGING`). Tests are isolated via a `NullHandler` in
  `settings/test.py` so this file only ever captures real production errors.
- **Per-command status files** (`/var/log/topquaranta/status/<tag>.status`):
  written by `tq-run`. Contain `status=OK|FAIL`, `exit_code`, `last_run`
  (ISO-8601), and the last 20 lines of output.
- **`/home/topquaranta/bin/tq-health`**: prints a summary table and exits
  non-zero if any command is FAIL, STALE (past its expected cadence), or if
  there are any Django ERROR-level entries logged today. Safe to pipe to a
  notifier or to read manually when inspecting the server.

## 6. Artist discovery

1. **Deezer contributor detection** — `obtenir_novetats` P3 reads an album's
   tracks; unknown contributors get created as
   `Artista(aprovat=False, auto_descobert=True, pendent_review=True,
   font_descoberta="collaborador")` — `pendent_review=True` enqueues
   it for staff review; `auto_descobert` is immutable provenance.
2. **User proposal** — `PropostaArtista` submitted via `/compte/artista/proposta/`;
   staff approves via `/staff/propostes/<pk>/` which creates the Artista
   together with its Deezer IDs + locations in one transaction.
3. **Manual** — staff can create an approved artist directly.

All auto-discovered artists sit in the pending queue (`/staff/artistes/pendents/`)
until a human approves them with a municipality assignment (which auto-sets
the territory via the `ArtistaLocalitat` → `Municipi` → `Territori` chain).

## 7. HomePage feed endpoints (Sprint I bis, 2026-04-26)

The redesigned `/` is composed from a small set of read-only public
endpoints, all anonymous-friendly and cached via `cache_for_anon`.
Live in `web/api/home_views.py`:

| Endpoint | Cache | Returns |
|---|---|---|
| `GET /api/v1/stats/` | 60 s | `{cancons_verificades, artistes_aprovats, territoris_actius, setmana}` — the latter is the latest `TopSetmanal.setmana` against which `territoris_actius` is computed (number of distinct `territori` values). |
| `GET /api/v1/top/nova-setmana/` | 1 h | First entry (lowest `posicio`) of the latest PPCC `TopSetmanal` whose `canco_id` was absent from the previous PPCC week. `null` when first run / no movement. |
| `GET /api/v1/artistes/destacat/` | 1 h | The artist with `UserArtista.verificat=True` whose biggest per-cançó positive PPCC delta is the largest. Tie-breaker: count of `Canco(verificada=True)`. Includes `lastfm_image_large`, `bio` (or `lastfm_bio_summary` truncated to 120 chars), territoris codes. |
| `GET /api/v1/artistes/descoberta/?limit=N` | 1 h | Artists `aprovat=True`, `created_at >= today − 30 d`, with `≥1` verified cançó, never present in `TopSetmanal`. Ordered by `-created_at`. `limit` capped at 12. |

Plus extensions to existing endpoints:

- **`GET /api/v1/albums/`** (new list view; the per-slug detail
  endpoint is unchanged). Filters: `ordering=±data_llancament`,
  `amb_verificades=true|false`, `limit≤24`. Annotates each album
  with `n_verificades` (count of `Canco(verificada=True, activa=True)`
  rows under it).
- **`GET /api/v1/top/?oficial=true&limit=N`**. The default behaviour
  falls back to `TopProvisional` when no weekly row exists; with
  `oficial=true`, the response is `entries=[]` instead — the
  HomePage hero can then hide the section cleanly. `limit` is also
  honoured (capped at `MAX_POSICIONS_TOP`) so the home strip can
  request only the 10 first rows.

## 8. Social distribution (Sprint I)

App `social/` + package `ingesta/social/` ship the weekly Instagram
publication.

**Model**: `SocialPost(platform, tipus, territori, setmana, status,
instagram_media_id, metadata, error_msg, scheduled_at, published_at)`.
Unique together `(platform, tipus, territori, setmana)` makes the
publication command naturally idempotent — re-running `publicar_social`
is safe; only `--force` re-publishes a `publicat` row.

**Commands**:
- `autoritzar_instagram` — interactive token-exchange flow. Run once
  per long-lived (60-day) token. Prompts for the OAuth `code`,
  exchanges it for a long-lived token, prints the values to add to
  `.env`.
- `publicar_social [--data D] [--tipus T] [--platform P] [--dry-run]
  [--force]` — the cron entrypoint. Walks `ingesta.social.calendari`
  for the target weekday, gates each slot on
  `ConfiguracioGlobal.fase_distribucio`, builds payload, renders
  PNGs to `<SOCIAL_CACHE_DIR>/renders/`, uploads them via
  `ingesta.social.instagram_client` and publishes.
- `renovar_token_instagram` — monthly cron. Refreshes the long-lived
  token via the Graph API; prints the new value (you write it to
  `.env`).

**DRY_RUN**: `instagram_client.is_dry_run()` returns `True` when
`INSTAGRAM_ACCESS_TOKEN` is empty or `"test"`. Every API method
returns a synthetic ID and logs what would happen; PNGs are still
rendered. This is the default during local development.

**Cron schedule** (`deploy/cron.topquaranta`):

| Day | Slot | Phase needed |
|---|---|---|
| Saturday 09:30 UTC | feed + stories PPCC | 1 (default) |
| Wednesday 09:30 | feed + stories territorial rotatori | 2 |
| Monday 09:30 | feed + stories second territorial | 3 |
| Friday 10:00 | feed nous singles | 4 |
| Tuesday 10:00 | feed nous àlbums | 5 |
| 1st of month 03:00 | `renovar_token_instagram` | always |

The cron rows are present unconditionally; phase gating happens
inside `publicar_social`, marking the SocialPost as `omes` when the
slot's `min_fase` exceeds the active phase.

**Staff cockpit**: `/staff/social` exposes the SocialPost list
along with kill switch, phase selector and `story_max_cancons_ppcc`
slider; preview button renders dry-run PNGs and prints the captured
stdout; "Publicar ara" forces a re-publication. Token expiry days
shown via `instagram_client.days_until_expiry()`.

**Caddy serving**: Caddy needs a `handle_path /static/social/*` rule
pointing at `/var/cache/topquaranta/social/renders/` so Meta can
fetch the rendered PNGs by URL. Update `deploy/Caddyfile` before
the first non-dry-run publication.
