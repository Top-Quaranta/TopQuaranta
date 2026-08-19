# ADR-0010 — No second-output to YouTube Music (yet)

- **Status:** Accepted
- **Date:** 2026-05-22
- **Authors:** Miquel

## Context

The playlists revival sprint (FASE A-G) restores the Spotify daily
+ weekly sync. A natural follow-up question: do we also push the
same data to YouTube Music? The "Escolta-ho a" component on every
content page (`web-react/src/components/ExternalListenLinks.jsx`)
already builds search URLs for YouTube Music alongside Spotify,
Deezer and Apple Music. A managed playlist there would close the
loop for the Android-heavy user segment.

The decision below is the conclusion of a Sprint G research pass.

## Decision

We do **not** add a YouTube Music output in this sprint, nor in the
following one. Re-evaluate in 12 months (target: 2027-05).

The four blockers, in order of severity:

1. **No official API for YouTube Music.** Google ships YouTube
   Data API v3 for YouTube proper (videos, channels, generic
   playlists) but there is no first-party "YouTube Music"
   endpoint. The community-maintained `ytmusicapi` Python library
   exists but works by reverse-engineering the internal `music.youtube.com`
   endpoints. Every Google-side rotation of those endpoints (history
   shows ~2 to 3 per year) breaks the library until the maintainer
   ships a patch. Production critical-path code on a reverse-
   engineered surface is not a trade-off we want to take.

2. **ISRC matching is unreliable.** Tracks on YouTube Music are
   sometimes uploads of the official audio (with ISRC), sometimes
   user-uploaded covers (no ISRC), sometimes regional re-uploads
   under a different track. Searching `isrc:<value>` is not a
   supported filter on YouTube Search; we'd fall back to text search
   "title + artist", which empirically yields the wrong track
   (cover, live version, sped-up edit) on a non-trivial fraction
   of the catalog. Spotify's `isrc:` filter is exact; Deezer
   supports `/track/isrc:<value>` directly. YouTube Music does not.

3. **API quotas are tight.** YouTube Data API v3 default quota is
   10,000 units/day; a single search costs 100. A daily refresh of
   5 playlists × 40 tracks × 1 search-per-track = 20,000 units,
   exceeding the default quota by 2×. We'd need a quota raise from
   Google (~6 weeks lead time, sometimes rejected) plus the same
   `ytmusicapi` fragility on top.

4. **Playlist write surface needs OAuth + a Google account.** Same
   identity question as Spotify (ADR-0009): which account owns the
   playlist? `admin@topquaranta.cat` is the obvious answer, but
   YouTube Music playlists are scoped to a personal Google account
   in a way that's harder to delegate than Spotify's Premium-on-app-
   owner model. Migrating ownership later (the GSC incident pattern)
   is painful.

## Alternatives considered

- **Use the `ytmusicapi` library and accept the fragility.** Cost
  is a regular maintenance tax we don't want to take on for a
  secondary output. Re-considered if a first-party API ships.
- **Keep the "Escolta-ho a" search URL only (status quo).** This
  is the chosen path. The user clicks the YouTube Music pill and
  performs the search themselves. Latency cost is one extra click;
  privacy cost is zero (no tracking from us); maintenance cost is
  zero (the URL shape hasn't changed since 2020).
- **Push to YouTube proper (videos) instead of YouTube Music.** Even
  more mismatched: we don't have video URLs, only audio ISRCs.
  Building a video search layer is out of scope.

## Consequences

- ✅ The sprint stays focused on the Spotify revival (10 playlists,
  monitoring, embeds).
- ✅ "Escolta-ho a" continues to serve the Android-heavy segment
  with a one-click search redirect; no regression.
- ⚠️ We accept that the Android-first user who has no Spotify
  account doesn't get a curated TopQuaranta playlist on YouTube
  Music. The trade-off is "less coverage" vs "less fragility";
  the second wins for now.
- ⏰ **Review date 2027-05.** Triggers that would flip the decision:
  Google ships a first-party YouTube Music API, OR `ytmusicapi`
  stays stable for 12 months straight (no breaking changes), OR
  our user analytics show >25% of the audience preferring YT Music
  to Spotify (measured via `escolta_click` events in the
  `MetricaEsdeveniment` table).

## Related

- ADR-0009 — Spotify identity migration (the integration this ADR
  declines to duplicate).
- `web-react/src/components/ExternalListenLinks.jsx` — the
  click-through fallback.
- `analytics/models.py::MetricaEsdeveniment` with clau="escolta_click"
  — the event we'd query to re-evaluate.
