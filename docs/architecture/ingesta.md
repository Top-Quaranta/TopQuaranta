# ingesta — invariants

<!-- Every management command that talks to an external API (Deezer,
     Last.fm, MusicBrainz, Spotify, YouTube, Viasona) plus the API
     clients, the caducitat helper and the self-hosted cover pipeline.
     Schedule: `deploy/cron.topquaranta` (+ `deploy/cron-meta.json` for
     thresholds). Command flags: `--help`. "Untested" = rule in code,
     no test would fail if broken. -->

## Invariants

### Cross-cutting
- **Clients never raise on transport/API failure — they return `None`
  / empty**, retry `MAX_API_RETRIES` (3) with backoff and honour
  `DEEZER_RATE_LIMIT` (1 s) / `LASTFM_RATE_LIMIT` (0.2 s) / MB 1 req/s.
  Guarded by: `ingesta/tests/test_deezer_client.py`, `test_lastfm_client.py`.
- **A run whose per-item failure rate exceeds 50 % must exit non-zero**
  (`CommandError` at the end; per-item fail-open stays). Why: a dead
  upstream otherwise reports `status=OK` forever. Guarded by:
  `ingesta/tests/test_exception_threshold.py`.
- **Single-instance commands use `SingletonLock` → exit 75 → `tq-run`
  writes `SKIPPED_BY_LOCK` without refreshing `last_run`; `tq-health`
  escalates after `skip_concern` skips** (`deploy/cron-meta.json`).
  Commands may print `WORK_DONE=<n>` (last occurrence wins).
- **Deezer quota code 4 latches a process-wide flag; no further Deezer
  call is made that run** (`deezer.quota_exhausted()`). Guarded by:
  `ingesta/tests/test_deezer_quota.py`.
- **Titles are stored with Deezer casing verbatim; only
  `normalize_apostrophes` runs.** No titlecase at ingest. Guarded by:
  `test_obtenir_metadata.py::test_titles_stored_raw_apostrophes_normalized`.
- **A rejected `(isrc | deezer_id)` is never re-created by any ingest
  path unless `HistorialRevisio.reconsiderada=True`** (`_previously_rejected`
  in `obtenir_novetats` and `obtenir_metadata`). Guarded by:
  `ingesta/tests/test_previously_rejected_reconsiderada.py`.
- **Caducitat has one definition** — `ingesta/caducitat.py::
  caducitat_cutoff()` = today − `DIES_CADUCITAT`; `is_caducat` /
  `exclude_caducats` use `__lt`, so NULL-dated rows are **kept**.
  `netejar_caducades` (04:00) deletes only `verificada=False, activa=True`
  past it (`activa=False` rejections stay forever as dedup markers);
  no ingest path creates a caducat canço; `enriquir_spotify`'s pending
  pool must equal the purge's survivors. Guarded by:
  `ingesta/tests/test_caducitat_guard.py`, `test_netejar_caducades.py`,
  `test_enriquir_spotify.py::test_caducat_pending_never_selected`.

### Deezer catalogue (`obtenir_novetats` hourly, `obtenir_metadata` on demand)
- **Every non-`descartat` album with a `deezer_id` is re-checked on a
  per-album cooldown keyed on `Album.last_album_check`** (<30 d since
  release → 24 h, 30–365 d → 7 d, else 30 d; NULL first). `descartat` is
  the only permanent exclusion. Why: a done-flag left ~3.7 k albums "OK"
  with zero tracks. Ladder untested. **P3 (approved artists) has its own
  24 h cooldown on `last_checked_deezer` so the queue drains and the run
  exits** (a never-empty queue hid a 12-day hang, 2026-05-01); capped by
  `--max-p3-per-run` (200, untested). Guarded by:
  `test_obtenir_novetats_cooldown.py`.
- **`_create_track` is idempotent on `deezer_id` then ISRC; an ISRC
  collision (`canco_isrc_unique_when_set`) is caught and skipped, never
  aborts the artist's transaction.**
- **Album-alien guard: a track enters under `album.artista` only if
  `own_album OR our_on_track`** (album titular ∈ artist's Deezer ids, or
  one of them among the track's *live* contributors — never
  `contributors_raw`). Titular lookup failure → `own_album=True`
  (conservative). Guarded by: `ingesta/tests/test_album_alie_guard.py`.
- **Contributor-vs-self compares against ALL of the artist's Deezer ids;
  every `ArtistaDeezer` row is fetched, principal first.** Why: multi-
  profile artists (autoedit + label) crashed the cron for 12 h.
- **Deezer id resolution needs an ISRC cross-check or exact name match;
  the source of truth for "has Deezer" is the `ArtistaDeezer` relation
  (`deezer_ids__isnull=True`), not `deezer_no_trobat`.** Guarded by:
  `ingesta/tests/test_obtenir_metadata.py`.
- **Ingest never creates artists for unknown contributors: it defers
  them to `Canco.contributors_raw` (dedup by deezer id, first write
  wins); a contributor whose Deezer id is already ours attaches at once.**
  Materialisation happens at approval
  (`music.services.processar_collaboradors_pendents` →
  `pendent_review=True, auto_descobert=True, font_descoberta=
  "deezer_contributor"`). Guarded by:
  `test_obtenir_metadata.py::test_secondary_contributor_*`,
  `music/tests/test_services.py::TestProcessarCollaboradorsPendents`.

### Last.fm signal (`obtenir_senyal` 06:00)
- **Eligibility is the canço, not who signs it:** `Canco.objects.public()`
  within `DIES_CADUCITAT`; no `artista.aprovat` gate. Idempotent per
  `(canco, data)`. Guarded by:
  `test_obtenir_senyal.py::test_verified_track_of_an_unapproved_artist_is_processed`,
  `::test_already_ingested_track_is_skipped`.
- **`get_track_info` asks with `autocorrect=0` (trust `lastfm_nom`); on
  error 6 it retries (a) without the recording MBID, (b) with the
  normalised title and `autocorrect=1`, (c) via the artist's top-tracks;
  the command then tries up to `MAX_COL_FALLBACK` (3) collaborator
  names.** Why: Last.fm resolves `mbid` *instead of* names — an unindexed
  MBID answered "not found" and a successful MB match silently killed the
  signal; the autocorrect=1 retry's homonym risk is bounded by drift
  detection. Guarded by: `test_lastfm_client.py::TestMbidFallback`,
  `::TestGetTrackInfoTopTracksFallback`,
  `test_obtenir_senyal.py::TestCollaboratorFallback`.
- **The name that answered (`asked_artist`) drives drift detection and
  alias summing; aliases are never summed onto a collaborator.** Drift
  (`_detect_drift`: artist ratio <0.90 or track <0.80 after stripping
  decoration; skipped when `lastfm_confirmed`) sets `corregit=True` and
  the ranking drops the row.
  Guarded by: `test_obtenir_senyal.py::test_aliases_are_not_summed_onto_a_collaborator`,
  `::test_drift_flag_persisted`.
- **Alias summing uses `get_track_info_literal(canonical_artist=…)`:
  `autocorrect=0` + URL guard against Last.fm's silent case-fold
  collapse; only `confirmat` aliases count.** Guarded by:
  `music/tests/test_lastfm_aliases.py`.

### Last.fm artist metadata (`obtenir_metadata_lastfm` 05:00)
- **Similars are resolved through confirmed aliases (alias-of-approved
  beats a stale pendent), deduped per source, replaced wholesale per
  source; a tombstoned name is matched, never re-created or re-queued;
  pendents are never sources.** Guarded by: `ingesta/tests/test_lastfm_similars.py`.
- **`netejar_pendents_no_ppcc` only sweeps `nb_similars_lastfm = 0`.**
  Guarded by: `music/tests/test_netejar_pendents_no_ppcc.py`.

### MusicBrainz (`obtenir_metadata_musicbrainz` :30 hourly)
- **Each iteration validates the existing MBID's area before anything
  else, then `resolve_mbid` (rules in `music.md`); a colliding MBID is
  blocklisted instead of raising; `sync_from_mbid` resets stale
  fingerprints at the start of each full cycle (`MB_RGS_PER_RUN`=20
  release-groups per run, round-robin); recon is ISRC first, then
  normalised title ≥0.9; `mb_last_sync` is stamped regardless of
  outcome.** Shared `"ram_heavy"` lock (see `music.md`). Sync internals
  untested (`test_mb_resolve_location.py` covers resolve/validate only).
- **The rotation is aprovats → pendents. Descartats never enter it.**
  Why: they are 14.731 of 24.518 rows kept only for FK integrity, and
  nothing reads their discography — with them in, the queue never
  drains, the hourly run outlives its own hour, the next one skips on
  the lock and the watchdog reports STUCK (22/08/2026: 0 aprovats and
  25 pendents due, 8.604 descartats). Guarded by:
  `ingesta/tests/test_obtenir_metadata_musicbrainz_cua.py::test_la_rotacio_ignora_els_descartats`.

### Whisper (`analitzar_whisper` 04:00)
- **After saving Whisper fields, `auto_aprovar_per_whisper` may approve
  on the spot** (`p_ca > 0.90`, approved anchor). `ram_heavy` lock.
  Guarded by: `music/tests/test_services.py::TestAutoAprovarPerWhisper`.

### Spotify (ADR-0009/0011/0012/0013)
- **Only `UserSpotifyClient` exists** (Client-Credentials removed
  2026-08-16). 429 with a short `Retry-After` sleeps; a long one raises
  `RateLimitedError`. Guarded by: `test_user_spotify_client_throttle.py`.
- **Process A (`actualitzar_playlists_spotify`) is cache-only: it never
  calls `/v1/search`, reads `SpotifyMetadata` in `LOCKED_STATUSES`
  (`found`, `manual`), `--freq daily` ← `TopProvisional`, `--freq
  weekly` ← latest `TopSetmanal`.** Guarded by:
  `test_actualitzar_playlists_spotify.py::test_cache_only_skips_unenriched_cancons`,
  `::test_freq_*`.
- **Process B (`enriquir_spotify`) is the only writer of the ISRC cache:
  priority tiers (current top → provisional → pending by `ml_confianca`
  → pending oldest → verified backlog); candidate visibility is a LEFT
  JOIN (no row = `not_attempted`); `manual` ids are hydrated but never
  re-searched; ISRC must be non-empty; every run recomputes
  `Artista.spotify_artist_dispersio` (>1 distinct principal Spotify
  artist = Deezer name-collapse signature).** Guarded by:
  `test_enriquir_spotify.py`, `test_enriquir_spotify_hydrate.py`,
  `music/tests/test_spotify_dispersio.py`.
- **Metadata cooldown is one shared file** (`spotify_metadata_cooldown`;
  longest unexpired `resume_at` wins); **playlist sync is OUT of it** —
  a metadata ban must not skip playlist writes. Guarded by:
  `test_spotify_metadata_cooldown.py::test_playlist_sync_does_not_reference_metadata_cooldown`.
- **AIMD backfill controller (`enriquir_spotify_rebuigs`): ban detection
  runs BEFORE expired sentinels are pruned, keys on sentinel mtime read
  as UTC, remembers `last_ban_at` 48 h; `--limit` bypasses without
  touching state.** Cascade: live shortlist → orphans (`--include-orfes`,
  30-day `spotify_lookup_at` memo) → pendents (`--include-pendents`). Guarded by:
  `test_spotify_backfill_controller.py`, `test_enriquir_spotify_rebuigs.py`.

### YouTube (`sembrar_canals_youtube` 02:00 · `descobrir_youtube` 03:00 · `obtenir_senyal_youtube` 06:30)
- **Quota rules the design: `search.list` costs 100/10 000 units.
  `QuotaExhausted` (also the per-metric variant) aborts WITHOUT stamping
  `youtube_checked_at`; a genuine miss IS stamped.** Guarded by:
  `test_youtube.py::test_quota_death_must_not_be_recorded_as_no_channel`,
  `::TestQuota::test_per_metric_quota_is_still_quota`,
  `::test_a_miss_is_remembered_so_we_dont_respend_100_units`.
- **The Art Track channel must carry the literal `- Topic` suffix (any
  known locale) and match the artist by `normalitza_nom_homonim`; the
  band's human channel is never accepted as Topic.** Guarded by:
  `test_youtube.py::TestFindTopicChannel`, `::TestNomsAmbAccents`, `::TestSufixLocalitzat`.
- **Art Track matching = exact normalised title; official-channel
  matching = title as prefix + allowed decoration only (`_conte_titol`);
  containment is never enough.** Guarded by:
  `test_youtube.py::TestDescobrirYoutube::test_matches_art_tracks_by_normalised_title`,
  `::TestConteTitol`.
- **The official channel is never guessed by code** — it comes from a
  MusicBrainz link (`sembrar_canals_youtube`) or a human; absence of a
  link never marks `youtube_canal_revisat`; `/@handle` resolution costs
  a search and stops at `--budget` (4 000); discovery keeps 9 000 and
  remembers a miss 30 days. Guarded by: `test_youtube.py::TestSembrarCanals`,
  `::TestDescobrirYoutube`.
- **A song's signal is the SUM of its lanes (Art Track + official
  videos); each snapshot stores `views_per_video`; a lane with no data
  (dead id, hidden `viewCount`) is not counted and does not raise
  `n_videos`; all lanes dead → `error=True, views=NULL`.** Guarded by:
  `test_youtube.py::TestObtenirSenyalYoutube`, `::TestDuesLlanes`.
- **Staff pasting a Topic channel into the official-channel field
  adopts it as Art Track lane only if the artist has none, and pairs
  songs immediately** (`_cua()` skips artists with a channel). Guarded
  by: `web/tests/test_staff_canal_youtube.py`.

### Instagram suggestions (`suggerir_instagram` 02:30)
- **Writes only `instagram_suggerit`, never `instagram_url`; a handle in
  `instagram_suggerits_descartats` is never re-proposed (veto per handle,
  not per artist).** Guarded by: `ingesta/tests/test_suggerir_instagram.py`.

### Covers (`descarregar_portades` 02:00 · `netejar_portades` Mon 03:00)
- **State is the filesystem, no DB column: present ⇔ the 500 px webp
  sentinel exists** at `<PORTADES_ROOT>/<entitat>/<deezer_id>-<mida>.<fmt>`.
  Writes are atomic (`*.tmp` + rename) and all-or-nothing per entity.
  Guarded by: `ingesta/tests/test_portades.py`.
- **`--limit` counts new downloads only; present covers cost nothing;
  `--entitat all` splits `limit // 3` with fall-through; ranking entities
  first; candidates are the public catalogue only.** Guarded by:
  `test_portades.py::test_all_*`, `::test_album_ranking_priority_first`,
  `::test_candidates_exclude_non_public_catalogue`.
- **`netejar_portades` KEEP-set = public catalogue ∪ everything ever in
  `TopSetmanal`** — newsletters embed absolute cover URLs. Guarded by:
  `test_portades.py::test_netejar_prunes_stale_keeps_public_and_ranked`.

## Traps
- Deezer `/artist/{id}/albums` lists albums the artist merely *appears*
  on; without the alien guard a guest feature drags a whole foreign LP in.
- A Deezer album delisting leaves `/track/{id}` returning stale 200 —
  detect dead releases at album level.
- Google's quota day resets 09:00 CEST: any daytime one-off eats the
  next night's discovery budget.
- MB `mb_last_sync` is stamped even on failure — a broken artist is
  retried in 7 days, not next tick.
- The rebuig backfill runs `--shortlist-only --include-orfes` in cron;
  `--include-pendents` is off — validate by hand with `tq-run` first.
- Cover cron once iterated the whole catalogue incl. descartats (1.7 G,
  disk-90 % alert 2026-08-12) — keep candidates bounded.

## Where the detail lives
- code: `ingesta/clients/`, `ingesta/caducitat.py`, `ingesta/portades/`,
  `ingesta/management/commands/`, `music/locks.py`, `bin/tq-run`,
  `deploy/cron.topquaranta`, `deploy/cron-meta.json`
- archived narrative: `docs/archive/architecture/{pipeline,playlists,portades}.md`
- ADRs: 0009, 0010, 0011, 0012, 0013 (Spotify), 0014 (Whisper)
