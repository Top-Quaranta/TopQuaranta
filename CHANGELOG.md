# Changelog

All notable changes to TopQuaranta are recorded here. Based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Dates are UTC.

> **Note (2026-04-26)**: starting from `0.8.0` the per-session/per-sprint
> changelog moved to **`ROADMAP.md`** (sections "Sprints — completats"
> and "Sprints — pendents"). The detailed `[Unreleased]` block below
> covers the work done between `0.8.0` (Phase 8 cleanup) and the start
> of the sprint cadence (Sprint A, 2026-04-25); from there on, ROADMAP
> is the source of truth. The next formal release tag (`0.9.0` or
> `1.0.0`) will reset this file to a normal Keep-a-Changelog rhythm.

---

## [Unreleased]

Phase 9 wrap-up + Whisper LID integration (Sessió 16) + Sessió 17
cleanup sweep (audit → safeguards + state-machine split + consistency
fixes across the whole Whisper + fusionar + pendents surfaces).

### Added (Sessió 17 — cleanup sweep)

- **`Artista.pendent_review`** (migration `0042`) as the authoritative
  "in staff triage queue" flag, separate from `auto_descobert` which
  is now immutable discovery provenance. A `CheckConstraint` forbids
  `(aprovat=True, pendent_review=True)` at the DB level; a composite
  index on `(pendent_review, aprovat)` keeps the list fast.
  RunPython backfill (a) flipped `pendent_review=True` on everyone
  in the old queue (2 291 rows), (b) surfaced 2 orphans with verified
  tracks that had no queue flag, (c) deleted 40 legacy-migration rows
  (`font_descoberta='legacy'`, zero Cançons) that had been invisible
  since the Wagtail import. Total: 4 259 → 4 209.
- **`StaffAuditLog.ACTION_CHOICES`** gains `artista_crear` (migration
  `0043`) so the audit-log filter surfaces manual creations.
- **`music/utils.py::normalize_nom`** as the single home for the
  accent/case-insensitive fold used by the `duplicats=si` filter and
  the artist-create duplicate guard.
- **`deezer_artist_url` template tag** in `staff_tags.py` consolidates
  `https://www.deezer.com/artist/{id}`.

### Fixed (Sessió 17)

- **`api_aprovar` 500 on Deezer-id collision**: entering a Deezer id
  that already belongs to another artist now returns a JSON 409 that
  names the owner artist, instead of leaking an `IntegrityError`
  from the `ArtistaDeezer.deezer_id` unique constraint. Wrapped in a
  nested savepoint so only the Deezer insert rolls back.
- **Fusionar artistes: HistorialRevisio migration**: the
  `ratio_rebuig_artista` ML feature keys on `artista_nom`, so without
  this the target silently inherited zero rejection history from the
  merged-away duplicate. `HistorialRevisio.objects.filter(artista_nom=
  source.nom).update(artista_nom=target.nom)` now runs inside the
  merge transaction.
- **Fusionar artistes: principal invariant**: after the merge we
  guarantee exactly one `ArtistaDeezer(principal=True)` on the target.
  Previously `.update(artista=target, principal=False)` on the source
  rows could leave target with zero principals, making
  `deezer_id_principal` a random `.first()`.
- **Whisper features training vs inference divergence**: the
  `_whisper_features()` fallback (used when `whisper_all_probs` is
  NULL) returned `margin_ca = p(top-1)` which didn't match the
  full-distribution value. The fallback now returns `0.0` for
  margin when it can't compute it correctly, so the RF learns to
  rely on margin only where it's informed.
- **Whisper features zeroed for merged tracks**: `_whisper_features_
  from_historial` now falls back to ISRC when `canco_deezer_id`
  misses — previously all merged-track historial rows got a zero
  vector and silently polluted training data.
- **Heuristic classifier threshold drift**: `_heuristic_classificar`
  now uses `ML_CLASSE_A_THRESHOLD` / `ML_CLASSE_B_THRESHOLD` (0.7 /
  0.4) instead of its own 0.65/0.35 hard-codes, so an RF-load
  failure doesn't silently reclassify tracks at a different
  boundary.
- **`api_descartar` ML recalc**: calls `recalcular_ml_si_cal()` on
  the keep branch, consistent with the other descartar paths.
- **`obtenir_metadata` filter**: switched from the stale
  `deezer_no_trobat=False` cache flag to `deezer_ids__isnull=True`
  (the source-of-truth relation), so artists whose Deezer link was
  deleted/merged get re-queried correctly.
- **`obtenir_novetats`, `obtenir_metadata` (×2), `fix_artista_principal`**:
  every Artista-creating path now sets `pendent_review=True`
  alongside `auto_descobert=True`, so provenance stays intact when
  staff approves/descartars.
- **`fetch_clips.py`**: exits `1` when every fetch failed and
  nothing was already cached (was `0`).
- **Staff CSS**: `html { font-size: 93.75% }` — everything scales
  6 % down so the staff tables fit on laptop viewports.

### Changed (Sessió 17)

- `pendents.llista` filter uses `pendent_review=True`.
- `api_aprovar` / `api_descartar` toggle `pendent_review`, not
  `auto_descobert`.
- `pendents.audit_log.action_taken` label updated:
  `kept_auto_descobert_false` → `kept_pendent_review_false`.

### Deferred (Sessió 17)

- Shared locality-cascade JS module (audit finding #11). Shipping
  dead infrastructure without migrating the two existing consumers
  is worse than the current duplication; the refactor lands the
  next time `pendents.html` or `artista_edit.html` needs real work.
- `deezer_no_trobat` column removal. The filter no longer reads it
  and a signal keeps it in sync, but the writers in
  `obtenir_metadata` still update it for backwards compat — a full
  sweep + removal migration is a later cleanup.

### Added (Sessió 16 — Whisper LID + harness)

- **Model-comparison harness** at `scripts/model_comparison/` — ground-
  truth manifest of 48 clips (21 Catalan vocals + 15 foreign-language
  hits + 11 instrumentals + 1 mislabelled), regenerable via
  `fetch_clips.py`, one runner per candidate model in its own venv. The
  harness paid for itself: surfaced two real catalogue errors (Martina
  Burón *In The Rain* = actually English; Marc Parrot *Visions Tàctils*
  = actually instrumental), both rebutjat with `motiu="no_catala"`.
  `resultats.md` records per-model numbers (Silero, Spleeter, Demucs,
  MusicNN, inaSpeechSegmenter, Whisper large-v3, VoxLingua107 ECAPA).
  Commits `9c83908`, `04db69e`, `4ba4bb5`, `ee58e8c`.
- **Whisper LID** (`ingesta/clients/whisper.py`,
  `ingesta/management/commands/analitzar_whisper.py`, migration `0040`,
  commit `f455054`) — `faster-whisper large-v3` via `detect_language()`
  on the 30-second Deezer preview. Initial fields on `Canco`:
  `whisper_lang`, `whisper_p`, `whisper_processat_at`. Evaluated on the
  48-clip harness after human correction of 2 ground-truth labels:
  **precision(ca) = 100 %**, recall(ca) = 81 %, specificity = 100 %.
  Zero false positives on the dangerous class — no foreign-language or
  instrumental clip got `p(ca) > 0.05`. Deliberately a staff **signal,
  not a hard gate**: a new badge + dropdown on `/staff/cancons/` flags
  tracks where `whisper_lang != ca`. Runs nightly via cron (see below).
- **Rich Whisper features** (`1cb8d47`) — added `Canco.whisper_all_probs`
  JSONField (migration 0041) storing the full 99-language probability
  dictionary alongside the top-1 shortcut. Extracted 4 new ML features
  into `music/ml.py` (total 219 → 223):
    - `whisper_p_ca`       — p(ca)
    - `whisper_p_es`       — p(es), primary confusion neighbour
    - `whisper_p_en`       — p(en)
    - `whisper_margin_ca`  — p(ca) − max(p over non-ca) in [−1, +1]
  A prediction `it=0.50 ca=0.45` now reaches the RF classifier as a
  very different signal from `it=0.95 ca=0.01` — the top-1 view
  flattens both to the same "non-Catalan", but the richer features
  encode the confidence gap. First automatic retrain after the ≥5-
  decision threshold lifted the Whisper features to ranks #10 and #11
  of 223 (importance ≈0.012 each) ahead of all 200 TF-IDF tokens.
- **Staff template tag** `whisper_badge` + filter dropdown "Idioma" +
  table column on `/staff/cancons/`.
- **Versioned cron at `deploy/cron.topquaranta`** (`222b3a3`) — the
  cron table had been hand-edited on the server through Silero add,
  revert, and Whisper. Now lives in the repo byte-for-byte identical
  to `/etc/cron.d/topquaranta` with `sudo install` deploy command
  documented in the header and in `CLAUDE.md §2`. Also includes the
  nightly `analitzar_whisper --limit 700` at 01:30 UTC (~5h 15m window,
  ≥15 min buffer before the 07:00 provisional ranking).
- **Staff `/staff/artistes/crear/`** (`601964e`) — manual artist
  creation with a minimal 3-field form (`nom` required; `lastfm_nom`
  and `deezer_id` optional). Surfaces duplicate-name hits before
  creating; "Crear igualment" checkbox forces through when staff
  confirms two different projects really share the name. After
  create, redirects to the existing editar view so the staff
  completes locations, social links, additional Deezer ids, etc.
- **`duplicats=si` filter on `/staff/artistes/`** (`a71e909`) —
  dropdown "Duplicats: Només duplicats (noms repetits)" shows artists
  sharing a name under accent/case-insensitive normalisation. The
  existing "Fusionar artistes" bulk action picks up right from there.

### Fixed

- **`/staff/artistes/` "sense Deezer" filter drifted** (`a94acf6`) —
  Àlex Blat surfaced in the list despite having a live Deezer id. The
  cause was an asymmetric filter (`deezer=si` read the current
  `ArtistaDeezer` relation, `deezer=no` read the stale
  `Artista.deezer_no_trobat` cache flag that was never cleared when
  auto-descoberta or staff later linked a Deezer id). Two fixes:
  the filter now uses `deezer_ids__isnull=True` symmetrically, and a
  new `post_save` receiver on `ArtistaDeezer` clears
  `deezer_no_trobat` automatically on any new link. Cleaned three
  existing inconsistent rows (Àlex Blat, Pep Gimeno "Botifarra",
  Vienna).
- **`/staff/artistes/pendents/` UX** (`47e9114`) — rows now vanish
  immediately after aprovar / descartar (were previously greyed out
  until a manual reload) and the counter in the header decrements in
  sync. Default ordering changed from alphabetical to
  `-nb_verif` (most verified songs first) so staff spend review time
  on the high-leverage candidates.
- **Two catalogue errors surfaced by Whisper** (batched in `f455054`):
  `pk=7925` Martina Burón "In The Rain" (was verificada=True
  idioma=ca, actually English) and `pk=721` Marc Parrot "Visions
  Tàctils" (was verificada=True, actually instrumental). Both
  rebutjat with `motiu=no_catala`. They stayed hidden until the
  harness pointed Whisper at them.

### Added (before Whisper)

- **Φ6 data retention** (`977beef`) — `docs/RETENTION.md` + new management
  command `arxivar_senyal_vell` that runs quarterly and archives
  `SenyalDiari` rows older than 2 years to gzipped CSV, then deletes from
  the live DB. Writes are atomic (fsync + rename before DB delete).
- **C4 deprecation policy** (`b8e2de5`) — `docs/DEPRECATION.md` establishing
  a 4-step process (announce in CHANGELOG, emit in-code warning, wait
  90/180 days, remove). Motivated by the R10b regression.
- **D6 composite indexes** (`cf52345`) — `RankingSetmanal(territori,
  setmana, posicio)` and `Canco(verificada, artista)` for the hot ranking
  and pipeline queries. Future-proofing for when the tables grow.
- **Artista.lastfm_te_scrobbles** (`116505a`) — new boolean that
  distinguishes "real Last.fm errors" (artist indexed, specific track
  not) from "silent tracks" (artist has no Last.fm data at all).
  Maintained by `obtenir_senyal`; migration 0037 backfills from
  `SenyalDiari` history.

### Changed

- **Φ7 manifest** (`694303a`) — "No monetization" section rewritten.
  Distinguishes mission-aligned revenue (cultural ads in Catalan,
  institutional support with placement-not-position) from revenue that
  would corrupt the measurement (selling data, selling the user list,
  anything tied to ranking outcomes).
- **Φ1 definition** (`a7b04fe`) — instrumental tracks no longer treated as
  a separate rule; they fail the "delivery is in Catalan" test and are
  rejected with `motiu="no_catala"`. No new motiu needed.
- **titlecase_catala** (`ee4652b`, `43a000b`) — orphan accents (` / ´ /
  curly quotes) normalised to ASCII apostrophe before tokenising;
  single-letter "I"/"A"/"O" stop being treated as acronyms mid-sentence;
  words after opening punctuation `([{«"¿¡` now capitalise the first
  alphabetic character. Applied in production via new `retitlecase`
  command over Canco.nom (2038 rows updated) and Album.nom (2881 rows).
  Upstream `_create_album` also titlecases now.
- **Last.fm signal ingest** (`116505a`) — `_normalize_track` now strips
  alternate titles after `|`; `get_track_info` gains a last-resort
  fallback via `artist.getTopTracks` (fuzzy match ratio ≥ 0.95) that
  recovers case-only variants like "+ Arcade" vs "+ ARCADE".

### Fixed

- **R10c** (`f41d40a`) — `obtenir_novetats._create_track`,
  `_process_track_data`, and `obtenir_metadata._upsert_track` now wrap
  the collaborator-resolution loop in `try/finally` with
  `classificar_i_guardar(canco)` in the finally. A brief regression
  window on 2026-04-16 left 1 track unclassified because the collab
  loop raised before the classifier ran; the fix guarantees a track is
  never persisted without an ML class set, even if collab fails.

### Docs

- **Sessió 13** (`fb2bd50`) — documentation for the D6/C4/Φ6 landing.

### Added / Reverted (Silero VAD experiment, Sessió 15)

Silero VAD was integrated end-to-end (commits `19a8904`, `abda422`,
`85756fa`, `cdc01e2`, `7fc2eba`, `49188cc`) — new Canco fields, RF
feature, staff badge, nightly cron, logrotate, deps, a partial
backfill of 410 tracks.

**Reverted at the end of the same session** because the model is
structurally inadequate for music:

  - Silero VAD is trained on speech (podcasts, phone calls, clean
    voice), not singing.
  - Against ground truth (47 staff-verified Catalan vocal tracks),
    Silero classified **51% as <10% voice** — i.e., a false-positive
    rate for "instrumental" of one in two.
  - Flagrantly wrong on rock bands with instrumentation (Sopa de
    Cabra concerts at 0-7%), hardcore (Katarrama 1.7%), typical
    vocal tracks (Aquarella "Aire Pur" 0%, ALTATXU 3.5%).
  - As an ML feature this would inject systematic noise, hurting
    the 97.7% CV accuracy of the current classifier.

Schema reverted via migration `0039_revert_silero_fields`. Code
deleted. Deps removed from requirements.txt. Cron + tq-health +
logrotate cleaned. The `torch` and `silero-vad` install stays in
the venv (~850 MB), harmless; a fresh install from requirements.txt
won't pull them.

Lesson recorded: speech-VAD ≠ voice-in-music detector. If we revisit
instrumental detection, the right model family is music-specific:
Spleeter (source separation), MusicNN (music tags), Demucs,
inaSpeechSegmenter. A standalone comparison harness is the next
step, NOT another integration-first attempt.

---

## [0.9.0] — 2026-04-17

Closes **Phase 9 session 1–11**: 41 of 62 audit findings resolved across
security, reliability, performance, operations, data model, frontend,
architecture and process. The system graduated from "functioning but
fragile" to "functioning and defensible."

### Security (Tier 1 complete)

- **S1** PostgreSQL password rotated to 40-char random.
- **S2** GitHub access migrated from PAT to ed25519 SSH deploy key; cleanup
  verified.
- **S3** Daily backups (already in place from Phase 7) now covered by R14
  monthly restore test.
- **S4** `django-axes` brute-force login protection enabled.
- **S5** Registration no longer reveals whether an email is registered
  (anti-enumeration).
- **S6** Strict `Content-Security-Policy`, `X-Frame-Options`, `X-Content-
  Type-Options` headers.
- **S7** `/mapa/` now uses `json_script` — no `|safe` on user-derived data.
- **S8** URL scheme allowlist on `PropostaArtista` social links.
- **S9** DRF throttling: 60/min anon, 300/min user on `/api/v1/*`.
- **S10** Argon2 password hashing.
- **S11** TOTP 2FA for staff (django-otp) with backup codes + reset
  management command.
- **S13** Branded 403/404/500 templates.

### Reliability (Tier 2 complete)

- **R1** `algorithm_version` + `config_snapshot` on `RankingSetmanal` so
  weekly rankings are reproducible.
- **R2** Foreign-key cascades that would rewrite ranking history changed
  to `SET_NULL` with name snapshots.
- **R5** Last.fm autocorrect drift detection + staff review flow.
- **R7** Cron retry — `tq-run` in-process (3 attempts, backoff 60/300s)
  + `tq-recover` sweep every 30 min.
- **R8** Min/max validators on `ConfiguracioGlobal` numeric fields.
- **R9** `StaffAuditLog` model + helper + cross-view integration +
  read-only UI at `/staff/auditlog/`.
- **R10, R11** Dual sources of truth eliminated: `Artista.deezer_id`
  and `Artista.{localitat,comarca,provincia}` dropped;
  `ArtistaDeezer` and `ArtistaLocalitat` are the sole sources.
- **R12** `sync_territoris_from_localitats` signal deferred to
  `transaction.on_commit`.
- **R13** Defensive `{% if canco.album %}` guards on staff templates;
  5 latent R10/R11 template regressions cleaned up along the way.
- **R14** Monthly `tq-restore-test` validates the latest daily backup
  can be restored and row counts are within 5% of live.

### Performance

- **P2** RF classifier + TF-IDF vectorizer cached with mtime invalidation.
- **P3** Composite indexes `(artista_nom, decisio)` + `(isrc_prefix,
  decisio)` on `HistorialRevisio`.
- **P4** `obtenir_senyal` switched from per-row `update_or_create` to
  batched `bulk_create(ignore_conflicts=True)`.
- **P6** `CONN_MAX_AGE=600` + `CONN_HEALTH_CHECKS=True` in production.
- **P8** `@last_modified` + `@etag` on homepage and `/ranking/` — 304
  Not Modified on revalidation.

### Data model

- **D1** Partial unique constraint on `Canco.isrc` (when non-empty).
- **D2** Dead Last.fm fields (`Canco.lastfm_mbid`,
  `Canco.lastfm_verificat`, `Artista.lastfm_mbid`) dropped.
- **D5** Self-collaboration guard: `m2m_changed` receiver rejects
  `canco.artistes_col.add(canco.artista)`; pre-existing rows cleaned up.

### Operations

- **O3** GitHub Actions CI on every push / PR: pytest +
  `manage.py check` + black + isort + missing-migration detection.
- **O5** SSH key policy documented (`deploy/SSH_KEY_POLICY.md`).
- **O8** `RUNBOOK.md` covering 8 operational incidents.
- **O9** `logrotate` weekly rotation for `/var/log/topquaranta/*.log`.

### Architecture

- **A8** API versioning policy (`web/api/VERSIONING.md`) +
  `X-API-Version` middleware.
- **A10** `mm-design` vendored into the repo at `vendor/mm-design/`;
  `npm install` no longer required for deploys.

### Frontend / UX

- **F3** SEO surface: `<meta name="description">`, Open Graph, Twitter
  Cards, `sitemap.xml`, `robots.txt`, default OG image.
- **F5** "Actualitzat el …" timestamp on ranking pages.

### Process

- **C1** pre-commit hooks mirroring CI (black + isort + missing-
  migration check).

### Cultural transparency

- **Φ4** `/com-funciona/` editorial + live coefficients + algorithm
  transparency history page.

### Infrastructure

- Ops layer from prior work: `tq-run` / `tq-health` / `tq-backup` /
  `tq-recover` / `tq-restore-test` ops scripts;
  `/etc/cron.d/topquaranta`; `/var/log/topquaranta/status/*.status`;
  systemd `topquaranta-web.service`.

---

## [0.8.0] — 2026-04-16

Phase 8 legacy cleanup:

- Dropped all pre-2026 legacy database tables (Wagtail CMS, old image
  generation, legacy Telegram distribution).
- Removed legacy Wagtail admin service.
- Caddy config simplified.
- Ops monitoring (`tq-health`) + daily backups (`tq-backup`) + settings
  split completed.

---

## Earlier phases

See `ROADMAP.md` for a summary of Phases 0–7 (project scaffold,
Last.fm ingestion, ranking algorithm port, metadata pipeline,
staff panel, legacy cleanup). No formal release tags for those
phases — the codebase lived as a rolling main branch until 0.8.0.
