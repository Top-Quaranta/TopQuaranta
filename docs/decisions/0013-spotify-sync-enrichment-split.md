# ADR-0013: Split Spotify cron into Process A (sync) and Process B (enrichment)

- **Status:** Accepted
- **Date:** 2026-05-22
- **Authors:** Miquel

## Context

The original `actualitzar_playlists_spotify` command did two things in
one body:

1. For every Cançó to push to a Spotify playlist, resolve a Spotify
   URI: try the cached `Canco.spotify_id` first, fall back to
   `/v1/search?q=isrc:` and persist the result.
2. Push the resolved URIs to the playlist via the (then) `/tracks`
   endpoint.

This was simple but had two failure modes that compounded badly on
2026-05-22:

- **Cold-cache bursts.** A fresh DB or a long-silenced cron meant
  hundreds of Cançons had no `spotify_id`, and the first run hit
  `/v1/search` hundreds of times in sequence. Spotify's `/search`
  bucket is the tightest of any Web API endpoint for new
  Development-Mode apps and replied `429 Retry-After: 86076`
  (~24h ban). The whole cron was wedged for a day.
- **Rate-limit blast radius.** Even after we added the abort-on-
  long-retry contract (ADR-0009 sister fix), the user-visible
  outcome of a `/search` 429 was that the playlist sync itself
  failed, despite the playlist write endpoint being on a different
  rate-limit bucket and perfectly available.

The two responsibilities have nothing in common operationally:

- Sync is deterministic, cheap, idempotent, and safe to run on any
  cadence. The only thing it cares about is "what's cached".
- Enrichment is best-effort, throttle-sensitive, one-shot per
  Cançó, and has a natural cool-down (a Cançó stays found forever
  once enriched).

Mixing them meant the conservative one (sync) inherited the
risk profile of the aggressive one (enrichment).

## Decision

Split the cron into two commands and two processes:

### Process A: `actualitzar_playlists_spotify` (cache-only)

- Reads `SpotifyMetadata.spotify_id` for each candidate Cançó.
- Skips Cançons in `not_attempted` / `not_found` / no-row state.
- Never calls `/v1/search`. Never reads from `Canco.spotify_id`
  directly any more; the legacy field is now a shadow of
  `SpotifyMetadata.spotify_id` for backward compatibility.
- Pushes via `/v1/playlists/{id}/items` (the post-Feb-2026 path
  per ADR-0012).

### Process B: `enriquir_spotify` (enrichment)

- New management command. One-shot per Cançó:
  - `client.search_isrc(canco.isrc)` -> URI or None.
  - On match: `client.get_track(id)` + `client.get_artist(principal)`.
  - Persists `SpotifyMetadata` (status, spotify_id, principal
    artist, full artist ids list, album metadata, etc.).
- Compound source ordering (FASE 0 "opció C"):
  1. Public Cançons by latest `SenyalDiari.lastfm_playcount desc`.
  2. Pending Cançons by `ml_confianca desc`.
- Flags: `--limit`, `--throttle`, `--retry-not-found`,
  `--target-playlists` (the last narrows the pool to the
  current playlist windows for cold-cache priming).
- Throttle defaults to 0.5s between API calls; the per-tick
  `--limit 200` keeps the worst-case burst at ~100s of
  `/search` traffic per hour.
- Failure mode: `RateLimitedError` aborts the run with a clean
  `CommandError` so the watchdog sees a non-zero exit. Per-Cançó
  transaction means partial progress is durable.

### Supporting bits

- `SpotifyMetadata` (new model, migration 0079 + 0080 backfill)
  is the only place we store the cached identifiers and the
  handful of post-2026 live metadata fields.
- `Artista.spotify_artist_dispersio` and
  `spotify_artist_ids_distints` (new fields on Artista,
  migration 0079) are recomputed at the end of every Process B
  run for the affected artistes. `dispersio>1` surfaces in the
  triage workbench as a "possible Deezer merge" hint.

## Consequences

- Process A's failure surface shrinks to just the playlist
  write endpoint, which has been reliable. Operators can run
  it on any cadence without worrying about catalogue rate
  limits.
- Process B's risk is contained: a 429 only delays
  enrichment, never delays distribution to the live playlists.
- Cold-cache periods (after a long silence, a fresh prod, or a
  big batch ingest) are handled by a single `enriquir_spotify
  --target-playlists --throttle 1.0` run by the operator before
  the cron picks up.
- The Process B cron at hourly cadence means a fresh backlog
  of ~1500 cançons fills in ~7-8 hours at `--limit 200` even
  without operator intervention.
- The `Canco.spotify_id` legacy column stays in sync for
  backward compatibility but new code reads
  `Canco.spotify.spotify_id` directly.
- Tests are layered: client (mocks for `get_track`, `get_artist`,
  RateLimitedError contract); Process A (cache-only assertion
  + chunk math); Process B (ordering + abort + dispersion);
  dispersion module (clean / mixed / collaborator-don't-inflate
  cases); workbench (new payload shape).

## Cross-references

- [ADR-0009](0009-spotify-identity-migration.md): Premium + OAuth
  foundation that this split sits on top of.
- [ADR-0012](0012-spotify-api-capabilities-2026.md): empirical
  table of what the post-2026 API actually returns, constraining
  what Process B can pull (cover art, ISRC, duration, no
  popularity / preview_url / audio-features).
- `docs/architecture/playlists.md` "Spotify enrichment (Process B)"
  for the operational design and field tables.
- PR #66 (`fix/spotify-playlists-items-migration`): the
  `/tracks -> /items` migration that Process A depends on.
