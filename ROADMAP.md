# ROADMAP.md — TopQuaranta

> Current state and next steps. Historical iteration detail lives in git log.
> Last updated: 2026-04-25.

### Recent deliveries (past two days, 2026-04-24/25)

- **Ranking factor breakdown** — `RankingProvisional` now stores
  `age_factor`, `past_top_factor`, `monopoli_factor` per row (migration
  `0011`). Staff ranking page surfaces them as percentage columns;
  per-cançó breakdown panel on `CancoEditPage` lists every territory
  the track is in with its decomposed score.
- **Provisional column rename (semantic)** — `lastfm_playcount` on
  `RankingProvisional` now stores the rolling 7-day plays delta (the
  same `weekly_plays` the algorithm computes); `dies_en_top` left
  NULL. UI relabelled "Escoltes 7d".
- **MusicBrainz hardening** — staff can now (a) **desvincular** an
  MBID and (b) optionally lock the artist out of further auto-match
  attempts. Two new fields on `Artista`: `mb_blocked_mbids` (JSON
  list) + `mb_auto_match_disabled` (bool). `resolve_mbid` short-circuits
  on the lockout flag and skips blocked IDs (migration `0048`).
  Extra Estat dashboard panel **Casos sospitosos d'homonímia** lists
  artists where a Deezer ID was rejected as `artista_incorrecte` but
  is still linked to a row with verified tracks. The auto-unlink in
  `services.rebutjar_canco` clears every Deezer ID when 100 % of the
  artist's tracks were rejected for that motiu (signal then
  desaprova when there's no MBID either).
- **Instagram + X (Twitter) on artists** (migration `0049`) — added
  to `Artista.SOCIAL_LINK_FIELDS`, `PropostaArtista`, and
  `PerfilUsuari`. `mb_sync` URL-relations route by URL host so MB's
  generic "social network" relation lands on the right field.
- **Cron pacing rebalanced** — backfill phase done, so
  `obtenir_metadata_musicbrainz` dropped from `*/15 min` → hourly at
  minute 30; `analitzar_whisper` from 01:30 / `--limit 700` →
  05:00 / `--limit 100`. Pipeline rearranged into a single nightly
  chain (backup → neteja → Whisper → senyal → ranking → playlists).
- **Public top redesign** — TopPage now a 2-column grid with bigger
  album art, song + artist + collaborators (max 3, single line) +
  album name + release date in Catalan long form; "Actualitzat el X"
  references the Saturday of the ISO week. Trend indicator (↑ or
  badge-new) before the position number, using mm-design SVG icons.
  No score visible publicly.
- **Filter panel pattern** — new `FilterPanel` component
  (`web-react/src/components/staff/FilterPanel.jsx`) with pending
  state + apply/cancel/restore + count badge. Refactored into
  StaffArtistesPage / StaffCanconsPage / StaffAlbumsPage.
  Click-throughs from Estat preserved via URL params.
- **Estat enriched** — MB block split into Artistes + Cançons (each
  with sub-buckets and click-throughs to filtered lists); Whisper bucket
  split into "pendent (cua)" vs "sense preview" (forever-pending);
  feature-importance bars now signed with direction tokens
  (↑ aprova / ↓ rebutja); homonímia panel with full case list.
- **Accent + apostrophe insensitive search** — shared helper
  `web/api/search_utils.py` (Postgres `unaccent` + apostrophe strip).
  Applied to staff lists (artistes / cançons / albums + typeahead),
  public artistes directory, and community search (perfils,
  publicacions, usuaris staff view).
- **Map cover correctness** — both `mapa_artistes_top` and
  `_latest_cover` now restrict to albums with verified Cançons,
  so a dirty Deezer ID can't surface a homonym's cover.
- **Artist page collaborations** — new "També col·labora a" section
  listing verified Cançons where the artist appears as
  `artistes_col` (with main-artist credit + cover + year).
- **Empty-string normalisation** — `Artista.save`, `Album.save`,
  `Canco.save` now coerce `""` to `None` on every nullable-unique
  CharField (`musicbrainz_id`, `spotify_id`). Prevents the
  `duplicate key value violates unique constraint` we hit in production
  on 2026-04-25 with two artists landing `mbid=""`.
- **Component dedup pass** — extracted shared `MmIcon`,
  `lib/format.js` (`fmtDataLlarga`, `fmtDataCurta`, `fmtAny`),
  and `Field` (in `StaffTable.jsx`). Removed inlined copies from
  three staff pages, FilterPanel, and TopPage.
- **Test coverage** — 112 passed (was 92): added regressions for
  `search_utils` normalisation, empty-string-unique save guards,
  and homonym auto-unlink (5 scenarios).

### Recent deliveries (past week)

- **Ranking algorithm v2.0** — rewrote `ranking/algorisme.py` from
  the old 14-CTE SQL to a Python pipeline that consumes raw
  `lastfm_playcount` deltas (plays this week vs a week ago).
  Dropped `score_entrada` (field + percentile normalisation +
  `actualitzar_score_entrada` command + cron). Simplified the
  penalty stack to four factors only: age, past-top positions
  (`coef / 2^(N-1)` per prior week), album monopoly, artist monopoly.
  Removed `penalitzacio_descens`, `penalitzacio_setmana_0..2`,
  `suavitat`, and the four `max_factor_*` clamps from
  `ConfiguracioGlobal`. `ALGORITHM_VERSION = v2.0`.
- **MusicBrainz integration** — continuous 15-min cron
  (`obtenir_metadata_musicbrainz`) pulls MBID + area + begin/end dates +
  URL relationships + full discography; reconciles Albums/Cançons by
  ISRC and normalised title. Staff panel exposes MBID field + on-demand
  sync button on every edit page. Invariant now `aprovat ⇒ Deezer OR MBID`,
  so Crim-style collisions can keep both artists live. Estat dashboard
  gains an MB coverage block. ML features grow 76 → **79** with
  `mbrainz_confirmed`, `mb_lyrics_cat`, `artista_te_mbid`.
- **Grup C community** — `PerfilUsuari`, `Publicacio`, `Comentari`,
  `Missatge`. Directori, feed moderat, DM 1-to-1, comentaris. Email
  notifications with per-user opt-outs. Unread-message badge on the
  account icon.
- **Mapa drill-down** — `/mapa` SVG of the PPCC with three zoom levels
  (territori → comarca → municipi) + sticky side panel with KPIs and a
  top-artist grid per region, sorted by cumulative Last.fm plays.
  GeoJSON preprocessed with Douglas-Peucker at 0.002° (5 MB → 2 MB
  across 17 files). L'Alguer renders as a Canaries-style inset.
- **Email pipeline** — real SMTP via cdmon (smtp.topquaranta.cat:587
  STARTTLS). HTML-styled emails matching site aesthetic. Password-reset
  + resend-verification + self-delete + DM/comment notifications all
  send via this channel now.
- **Staff UX fixes** — visible Tornar/action buttons on dark headers
  (new `outline` tone), semantic colour tokens in design system
  (`--color-tq-success/warning/danger/neutral/accent`), markdown
  rendering in publications (with heading-level shift + image support),
  staff usuaris merged with directori-usuaris into one page.
- **Pipeline reliability** — Deezer P2 no longer permanently marks an
  album as "no tracks" after a single empty response (retries while
  the album is <30 days old); NFD-encoded track names now hit Last.fm
  correctly; ALT ranking aggregates below-threshold territoris; stale
  RankingSetmanal rows cleared when a territori's feeders vanish.
- **Design system** — `--color-tq-*` semantic tokens used throughout
  `EstatPage` (dropped hardcoded hex). Intake-per-week bars switched to
  pixel heights to fix a flex percentage-height rendering bug.

---

## Current state (2026-04-22)

**Public site**: `https://www.topquaranta.cat/` — React SPA at the root.
Routes: `/` (home), `/top` (current weekly ranking per territori), `/artistes`
(directory + filters), `/artista/<slug>`, `/album/<slug>`,
`/canco/<slug>` (with multi-line ranking history chart), `/mapa` (territorial
browse), `/compte` (user dashboard), `/compte/artista/{proposta,gestio}`.
Every content page has **"Escolta-ho a"** buttons to Spotify / Deezer /
YouTube Music / Apple Music plus a **"Corregir"** feedback button.

**Staff panel**: `/staff/*` — React pages backed by DRF. 17 pages:
dashboard, estat (visual health), pendents, artistes (+ crear + editar),
cançons (+ editar), albums (+ editar), ranking provisional, propostes
(+ detall), sol·licituds, senyal, historial, configuració, auditoria,
usuaris (+ detall), feedback. Full collab editing on track edit, artista
reassignment with cascade-canço toggle.

**Authentication**: Django session cookies + CSRF. Staff uses TOTP 2FA
enforced at the API layer (`IsStaff` requires `user.is_verified()`). The
2FA pages still render via Django templates under the Caddy allow-list.

**Pipeline** (deploy/cron.topquaranta):
- Hourly: `obtenir_novetats` (Deezer incremental).
- **01:30 UTC**: `analitzar_whisper --limit 700` (LID, ~5h15m window).
- 04:00: `netejar_caducades` (drop unverified > 12 months).
- 06:00: `obtenir_senyal` (Last.fm). No normalisation post-ingest (algorithm v2.0 reads raw playcounts).
- **07:00**: `calcular_ranking --provisional`.
- **07:15**: `actualitzar_playlists_spotify` (top-CAT/VAL/BAL/ALT + novetats).
- Saturday 08:00: `calcular_ranking` (official weekly).
- Quarterly: `arxivar_senyal_vell`.
- Daily 03:00: pg_dump via `tq-backup`.

**Database**: PostgreSQL 14. 37 tables (18 domain + Django/axes/otp internals).
Post-purge 2026-04-20: 1,920 aprovats + 2,323 pendents = 4,244 Artistes;
3,563 Albums; 8,144 Cançons (100% with Deezer ID + ISRC); 1,770 verified
(21.8%); 17,408 SenyalDiari rows; 4,371 HistorialRevisio decisions.

**ML classifier** (`music/ml.py`) — RandomForestClassifier + TF-IDF.
**79 features** post-slim + MB (12 structured + 4 Whisper + 3 MusicBrainz + 60 TF-IDF).
5-fold CV: ROC-AUC 0.9994, F1 0.9522, accuracy 0.9675. Top features:
`ratio_rebuig_artista` (22.2%), `ratio_rebuig_registrant` (14.9%),
`ratio_rebuig_isrc_prefix` (13.6%), all Bayesian-smoothed (k=5, p=0.5).
Auto-retrain when ≥5 new decisions.

**Infrastructure**: Caddy 2.x (TLS + SPA fallback), single gunicorn
with `ExecReload=HUP` for graceful deploys. SPA bundle at
`web-react/dist/`. Legacy Wagtail code preserved at `/root/TopQuaranta/`
but the service is disabled.

---

## Phase status

| Phase | Summary | Status |
|---|---|---|
| 0 | Project skeleton, user, DB, settings split | ✅ done |
| 1 | Legacy data imported into new models | ✅ done (legacy tables dropped in 8) |
| 2 | Last.fm ingestion running | ✅ done |
| 3 | Formula B (percent_rank) signal normalization | ✅ done |
| 4 | Ranking algorithm ported from SQL views to Python | ✅ done |
| 5 | Provisional ranking + admin review | ✅ done (image/Telegram distribution shelved) |
| 6 | Metadata pipeline (Deezer) + public website | ✅ done |
| 7 | Custom `/staff/` panel replaces Wagtail/Django admin | ✅ done |
| 8 | Legacy cleanup (tables, code, services) | ✅ done (2026-04-16) |
| Audit | Consolidation + doc rewrite | ✅ done (2026-04-16) |
| Ops | Monitoring (tq-health) + daily backups + settings cleanup | ✅ done (2026-04-16) |
| 9 | Excellence — security, reliability, architecture, cultural transparency | ✅ done (landed incrementally across sessions) |
| **10** | **React SPA migration + cleanup** (April 2026) | ✅ **done** |
| **11** | **Community platform** (Grup C, 2026-04-21) | ✅ **done** |

### Phase 10 · React SPA migration (completed 2026-04-21)

- **Sprint 1**: Fork of cercol's React scaffold (JS + Vite 8 + Tailwind v4
  + React Router v7), adapted to TopQuaranta palette. Auth + ranking API +
  `/beta/top` live.
- **Sprint 2**: Public pages (artistes directory, artist/album/canço
  profiles, mapa stub). `Canco.slug` + nested SEO URLs.
- **Sprint 2D**: `/compte` card-grid dashboard + Perfil edit.
- **Sprint 3**: Full staff panel in React — 17 pages, shared chrome,
  sidebar navigation, ~30 DRF endpoints (`web/api/staff_views.py`).
- **Sprint 4**: Caddy flip — React served from `/`, Django kept for
  `/api/*`, `/compte/{2fa/*, login, logout, registre, activar}/*`,
  `/sitemap.xml`, `/robots.txt`. Legacy `/beta/*` redirects to root.
- **Feedback feature**: `Feedback` model + "Corregir" button on every
  content page (staff → edit link, user → modal, anonymous → login).
- **Spotify playlist sync**: one-time OAuth + daily cron.
- **ML slim**: 223 → 76 → 79 features (2026-04-22 added MB signals), Bayesian smoothing on rejection
  ratios, ROC-AUC 0.9994.
- **Visual `/staff/estat` dashboard**: live BD inventory, cron health,
  weekly flux, ML feature-importance chart.
- **Cleanup** (2026-04-21): removed ~7 900 LOC of dead Django-templates
  UI (39 templates + 10 view modules + legacy URLs); archived 6 one-shot
  management commands to `scripts/archived_commands/`.

### Phase 11 · Community platform — Grup C (completed 2026-04-21)

- New models `PerfilUsuari` (1:1 with Usuari, auto-created via signal)
  and `Publicacio` (markdown posts with visibilitat=interna/publica +
  estat pipeline). Migration `comptes/0008_perfilusuari_publicacio`.
- Post-registration guided onboarding at `/onboarding` with a single
  "Saltar" escape; accessible later from `/compte/perfil-usuari`.
- Community routes: `/comunitat` (mixed feed), `/comunitat/directori`
  (opt-in list of users), `/comunitat/publicar`, `/comunitat/public`
  (unauthenticated), `/comunitat/:pk` (detail).
- Staff moderation surfaces: `/staff/publicacions` (with
  publicar/rebutjar/despublicar + staff notes), `/staff/directori-usuaris`
  (toggle visibility flag on any profile).
- `PropostaArtista`: Deezer IDs now required (≥ 1) — without them no
  track can be verified. Localitzacions now required too and use the
  LocationCascade (territori → comarca → municipi, with ALT falling
  back to free-text manual entry).
- Public nav gains "Comunitat" link. Staff dashboard gains two tiles
  and sidebar gains two entries. `/api/v1/auth/me/` exposes
  `onboarding_complet` so first-time logins auto-route to the form.

---

## Ops layer (2026-04-16)

- **`/home/topquaranta/bin/tq-run`** wraps every cron command. Captures exit
  codes and last output to `/var/log/topquaranta/status/<tag>.status`.
- **`/home/topquaranta/bin/tq-health`** prints a summary and exits non-zero
  if any command is FAIL / STALE or if today's Django `errors.log` has any
  entries. Intended for manual SSH inspection; can be wired to any external
  notifier later.
- **`/home/topquaranta/bin/tq-backup`** runs as `postgres` at 03:00, tiered
  retention (7 daily / 4 weekly / 12 monthly).
- **`settings/base.py::LOGGING`** adds a file handler for ERROR+ to
  `/var/log/topquaranta/errors.log`. Tests are isolated via NullHandler.
- Root crontab cleaned (8 stale legacy entries removed).

---

## Phase 9 — Excellence (next)

**Goal**: close the gap between "the system works" and "the system is an
artifact worth preserving". Full diagnosis in **`CLAUDE_EXCELLENCE.md`**.

**Scope**: 62 findings across 9 areas (Security, Reliability, Performance,
Architecture, Data model, Operations, Frontend/UX, Process, Philosophy).

**Severity distribution**:
- 🔴 7 CRITICAL — real exposure or guaranteed data loss under normal conditions
- 🟠 15 HIGH — concrete risk under plausible conditions
- 🟡 22 MEDIUM — defense-in-depth, structural debt
- 🟢 18 LOW / PHILOSOPHICAL — polish, transparency, cultural fidelity

**Execution tiers** (mirror the ones listed at the end of `CLAUDE_EXCELLENCE.md`):

### Tier 1 — Foundations (weeks)
Rotate secrets (DB password, GitHub PAT, SECRET_KEY). Encrypted off-site
backups. `django-axes` + Argon2 + staff 2FA. Real CSP. Input validation on
user-generated fields (`PropostaArtista.nom`, social URLs).

### Tier 2 — Reliability (weeks)
`algorithm_version` + `config_snapshot` on `RankingSetmanal` for forever-
reproducible rankings. Immutable staff audit log. `@cache_page` + `ETag` on
public pages. CI/CD (pytest + ruff + mypy on every push). Monthly backup
restore drill.

### Tier 3 — Architecture (months)
Extract a domain layer from `music.models`. Proper job queue (Celery / RQ)
for ML retraining and notifications. Versioned REST API with resource-per-
resource design. Event bus to decouple approvals from downstream actions.
Port the 14-CTE to testable Python (at least a SQLite-runnable variant).

### Tier 4 — Culture (months)
`CULTURAL.md` manifesto: what is Catalan music according to TopQuaranta,
why the coefficients weigh what they weigh. Algorithmic transparency (per-
song "why here?" button). Artist agency — verified artists can propose
corrections. Data licensed CC-BY-SA. Multilingual (at least CA + EN).

### Tier 5 — Exquisiteness (years)
Native mobile app on the v1 API. Personalised recommendations for logged-in
users. Federation with sister Catalan-culture projects. Open editorial
governance for coefficient changes. Physical / digital magazine edition.

**Ground rule for Phase 9**: every fix lands with a test that would have
caught the defect, and every architectural change is reversible or
documented with an ADR.

---

## Phase 10 — Polish & backlog (after 9)

Tactical items not tied to specific CLAUDE_EXCELLENCE findings:

### High-value polish
- [ ] Investigate Last.fm ~18% error rate for genuinely un-scrobbled tracks.
      Normalization already recovers ~3/4 of fixable cases; document the
      remaining set as "expected misses" or flag them for manual review.
- [ ] Mobile responsive polish (site works but device testing would help).

### Tech debt / nice-to-haves
- [ ] Test coverage 52% → 70%. Main 0% gaps: `music/services.py`,
      `music/verificacio.py`, `ranking/senyal.py`,
      `ranking/management/commands/calcular_ranking.py`.
      (Partially covered by Phase 9 Tier 2 "CI/CD".)
- [ ] Decide whether to archive `/root/TopQuaranta/` (1.4 GB legacy Wagtail
      code). tar.gz to offsite storage or `rm -rf`.
- [ ] Move `PPCC_PENALITZACIO_PER_POSICIO = 0.04` into `ConfiguracioGlobal`
      alongside the other algorithm coefficients.
- [ ] Extract heuristic-classifier magic numbers in `music/ml.py` to
      `music/constants.py`.
- [ ] Consolidate reject-action handling; some inline styles in staff
      templates could become CSS classes.

### Sessió 17 follow-ups (from the cleanup sweep)

- [ ] **Remove `Artista.deezer_no_trobat` column**. The pendents and
      staff filters no longer read it; a signal keeps it in sync. The
      only remaining writers are in `obtenir_metadata.py`
      (lines 199-203, 230-231, 253-256). Once those lines are pruned
      a migration can drop the column. Blocked on a confident test
      run: the write side still marks artists Deezer-rejected so an
      audit trail survives on failure.
- [ ] **Migrate `pendents.html` + `artista_edit.html` to a shared
      `locality-cascade.js` module** (the deferred finding). The JS
      pattern is now duplicated across both templates; extract when
      either gets real work next time.
- [ ] **Drop `Album.lastfm_mbid`, `Canco.lastfm_mbid` references
      from CLAUDE_MODELS.md** — they were removed in D2 (2026-04-17)
      but the doc still mentions them in the Canco fields table. The
      wider sweep above already fixed the Artista row.

### Sessió 16 follow-ups

- [ ] When the Whisper backfill finishes (~27-28 April) re-evaluate the
      feature importances of the 4 Whisper features. If they climb into
      top-5, consider trimming the 200 TF-IDF features — they may have
      been carrying load Whisper now covers more cheaply.
- [ ] **Demucs → Whisper pipeline** as a recall booster for the 3-4 false
      negatives where Whisper hears `es` on Catalan tracks (Jonatan
      Penalba × 2, Adrien Broadway). Source-separate vocals first, then
      LID on `vocals.wav`. Cost ~55 s + 27 s per track (3× slower). Only
      worth it if the backfill surfaces a significant cluster of FN
      tracks that share the pattern. Deferred until we have data.
- [ ] Audit the 39 `ja` (Japanese) Whisper predictions in the current
      slice — suspicious cluster, likely Whisper hallucinating on
      vocalises / long sustained vowels / certain instrumentals. If
      the pattern is an indicator of *something* specific
      (instrumentals? scat? hardcore screaming?) it could be a cheap
      extra ML feature.
- [ ] Record a snapshot of the pre-Whisper RF baseline before the next
      retrain (`cp music/ml_model.joblib music/ml_model.baseline.joblib`)
      so we can A/B the classifier's precision on the same 48-clip set
      in a week and measure the real contribution of the Whisper
      features in isolation.

### Post-Excellence (apuntat durant la fase 9)
- [ ] **Naming consolidation**: unificar "ranking / top / top /
      top40" a **"top"** al llarg del codi, templates i URLs. El projecte
      es diu TopQuaranta; l'UX actual barreja cinc variants del mateix
      concepte. Caldrà una pantalla de naming + migració d'URLs amb 301.
- [ ] **Correu @topquaranta.cat**: configurar hosting de correu propi
      (Hetzner Hosted Mail, Fastmail o servidor propi). Aboliria el
      pseudofailback FileEmailBackend actual i permetria enviar correus
      de verificació, recuperacions, notificacions admin reals.
- [ ] **Redisseny estètic**: revisió visual completa del projecte. Les
      pàgines s'han anat afegint iterativament i barregen patrons
      diferents (staff-tool-card, ranking-entry, historial-entry,
      chart-bar...). Cal decidir un sistema visual coherent per a
      tot el projecte (public + staff), probablement basat en
      components nous de mm-design, i aplicar-lo transversalment.
      Inclou: tipografia jeràrquica, consistència d'espais, dark
      mode, accessibilitat (a11y WCAG AA), mobile polish real
      testing cross-device.

---

## Phase 12 — Sprints planificats

Full de ruta executable per a sessions futures. Cada sprint és
autocontingut: nom, objectiu en una frase, i les tasques concretes.
Sprints en ordre alfabètic (l'ordre de execució no és per la lletra
sinó per prioritat — vegeu el report d'auditoria de 2026-04-25).

### Sprint A — Tancar deute acumulat ✅ (2026-04-25)

> Deixar el codi sense columnes mortes ni constants hardcoded ni
> documentació desfasada.

- [x] Drop `RankingProvisional.dies_en_top` (sempre NULL des de v2.0).
      Migració `ranking 0012`.
- [x] Rename `RankingProvisional.lastfm_playcount` → `escoltes_setmanals`.
      Migració `ranking 0012` (RenameField). Lectors/writers a
      `staff_views`, `calcular_ranking._save_provisional`, tests i UI
      (StaffRankingPage, RankingBreakdownPanel) actualitzats.
- [x] Drop `Artista.deezer_no_trobat` — la columna ja s'havia eliminat
      a `music 0044`. CLAUDE_MODELS depurat (entrada de la taula i
      paràgraf explicatiu).
- [x] Moure `PPCC_PENALITZACIO_PER_POSICIO` a `ConfiguracioGlobal`
      (camp nou `ppcc_penalitzacio_per_posicio`, default 0.04).
      `_calcular_ranking_ppcc` el llegeix de la config.
- [x] Magic numbers de l'heurístic ML → `constants.py`:
      `TFIDF_MAX_FEATURES`, `RATIO_PRIOR_K`, `RATIO_PRIOR_P`,
      `MB_AUTO_MATCH_SCORE`. `music/ml.py` i `music/mb_sync.py` els
      importen.
- [x] `CLAUDE_MODELS.md` ja no menciona `lastfm_mbid` (cap referència
      activa). Migrations footer actualitzat fins a `ranking 0012`.
- [x] `/root/TopQuaranta/` arxivat a
      `/home/topquaranta/backups/legacy-wagtail-archive-20260425.tar.gz`
      (4.9 MB comprimits) i esborrat. (Eren 16 MB reals, no 1.4 GB
      com deia el plan inicial.)

### Sprint B — Whisper milestone i reentrenament ML ✅ (2026-04-25)

> Tancar el cicle del backfill Whisper i decidir si simplifiquem el
> model amb les noves dades.

- [x] Whisper backfill ja completat (2026-04-25).
- [x] Baseline desat: `music/ml_{model,tfidf,directions}.pre_whisper.joblib`
      (snapshot del model anterior al re-entrenament).
- [x] Re-entrenat sobre 7.602 mostres (1.958 aprovades + 5.644
      rebutjades) amb cobertura Whisper 75.8 % del catàleg.
- [x] Feature importances post-train: **4 de 4 features Whisper són
      al TOP-7** (`whisper_p_ca` #2, `whisper_p_es` #4,
      `whisper_margin_ca` #6, `whisper_p_en` #7). Estructurals
      sumen 95.6 % del senyal; TF-IDF només 4.4 % (60 features).
- [x] **Follow-up TF-IDF retall** ✅ (2026-04-25). 5-fold CV A/B
      sobre 7 730 decisions:

      | Mètrica  | max=60 (A) | max=30 (B) | Δ (B−A) |
      |---|---|---|---|
      | ROC-AUC  | 0.9998 ± 0.0001 | 0.9998 ± 0.0001 | +0.0000 |
      | F1       | 0.9895 ± 0.0017 | 0.9908 ± 0.0031 | +0.0013 |
      | Accuracy | 0.9947 ± 0.0009 | 0.9953 ± 0.0016 | +0.0006 |

      Model B iguala AUC i millora marginalment F1 + Accuracy.
      Adoptat: `TFIDF_MAX_FEATURES = 30` a `music/constants.py`,
      model i tfidf de producció re-entrenats sobre 7 912 mostres
      (49 features = 19 estructurals + 30 TF-IDF). De pas, fixat un
      bug latent a `_tfidf_features` (no padejava quan el vocab era
      més petit que el cap, cosa que provocava `ValueError:
      inhomogeneous shape` quan `min_df=2` retallava la cua).

### Sprint C — Robustesa staff_views i tests ✅ (2026-04-25)

> Trencar el monòlit de `staff_views.py` i pujar la cobertura de
> tests de l'API.

- [x] Split de `web/api/staff_views.py` (3.330 línies) en el paquet
      `web/api/staff/` amb 16 mòduls per àrea (`_common`,
      `dashboard`, `pendents`, `artistes`, `cancons`, `albums`,
      `ranking`, `propostes`, `solicituds`, `senyal`, `historial`,
      `configuracio`, `audit`, `usuaris`, `feedback`, `estat`).
      `staff_views.py` queda com a shim de 18 línies que re-exporta
      el paquet via `from web.api.staff import *`. Cap canvi a
      `urls.py` ni a `comunitat_views.py`.
- [x] Tests d'integració (`web/tests/test_staff_endpoints.py`):
      auth gate, estat (full payload shape), ranking_list, cancons_list,
      artistes_list (exerceix la cadena d'imports cross-module
      artistes → pendents._artista_card → estat._homonym_suspects_qs),
      i regressió del shim legacy.
- [x] Cobertura `web/api/staff/*` ara **47 %** (era 0 %), amb pics
      a `estat` (87 %) i `dashboard` (97 %). Total tests del projecte:
      112 → 118 (+6). Cap regressió.

### Sprint D — Performance pública ✅ (2026-04-25)

> Reduir càrrega Postgres a hores punta amb cache HTTP a les rutes
> més consultades.

- [x] Helper `web/api/utils.py::cache_for_anon` — cache 60 s a
      `pagecache` (LocMem per worker, ja existent des de Phase 9)
      només per a usuaris anònims; els autenticats sempre veuen
      dades fresques. Emmagatzema l'`HttpResponse` ja renderitzat
      via `add_post_render_callback` perquè els hits cached siguin
      bytes purs.
- [x] `@condition` (Django) amb ETag + Last-Modified a:
      - `/api/v1/ranking/` → `RankingProvisional.data_calcul` ↦
        fallback `RankingSetmanal.created_at`.
      - `/api/v1/artistes/` → `Artista.created_at` (Max).
      - `/api/v1/mapa/artistes-top/` → `SenyalDiari.data` (Max).
      ETag pesat amb el query string perquè cada combinació de
      filtres rebi el seu propi 304.
- [x] Mesures (intra-host, 5 hits consecutius, 2 workers):

      | Endpoint | Cold | Cached | 304 (If-None-Match) |
      |---|---|---|---|
      | `/api/v1/ranking/?territori=CAT` | ~410 ms | **15 ms** | **5 ms** |
      | `/api/v1/artistes/?per_page=40` | ~520 ms | **18 ms** | (ETag funciona) |
      | `/api/v1/mapa/artistes-top/?territori=CAT` | ~145 ms | **15 ms` | (ETag funciona) |

      Speedup ~30× a hits servits des de cache; ~80–100× quan el
      client envia ETag i el servidor pot retornar 304 sense cos.
- [x] Sense invalidació activa: la cache de 60 s és curta enough
      perquè els ~daily cron writes (provisional 07:00, setmanal
      dissabte) es propaguin sols. La capa ETag/Last-Modified actua
      com a contracte segon: si el `data_calcul` no ha canviat el
      304 protegeix amplada de banda fins i tot durant els 60 s de
      stalebess potencial.

### Sprint E — Transparència algorítmica pública ✅ (2026-04-25)

> Donar als visitants la mateixa visió que té l'staff sobre per què
> una cançó està on està.

- [x] Endpoint `GET /api/v1/cancons/<slug>/top-breakdown/` amb
      payload diferenciat per permís: anònim/usuari sense relació
      veu només els territoris on la cançó és al `TopProvisional`;
      staff i `UserArtista.verificat=True` sobre l'artista
      principal veuen també els territoris elegibles on la cançó
      no està al top, amb factors i score teòric calculats sobre
      la marxa via `_compute_weekly_plays`, `_age_factor` i
      `_past_top_factor` (`canco_views.py::canco_top_breakdown`).
- [x] Component nou `web-react/src/components/TopBreakdownPanel.jsx`
      (compartit, no només staff). Toggle "Per què està aquí?"
      (anon) o "Com ho fa al top?" (elevated). Selector de
      territoris quan n'hi ha més d'un. Frases divulgatives en
      català per a cada penalització: antiguitat, top passat,
      monopoli àlbum/artista. Quan la cançó no és al top mostra
      la puntuació teòrica i ho explica.
- [x] Unificat amb el panell d'staff: `RankingBreakdownPanel.jsx`
      eliminat. `CancoEditPage` ara fa servir el mateix component
      (passant `slug`), eliminant la duplicació.
- [x] `CLAUDE_STAFF.md` documenta el nou endpoint i la lògica de
      permisos diferenciada.

### Sprint F — Accessibilitat i mobile ✅ (2026-04-26)

> Passar WCAG AA i validar el SPA en dispositius reals.

**Fets globals (afecten totes les pàgines)**:
- [x] Skip-to-content link al `Layout.jsx` ("Salta al contingut
      principal") — `sr-only` per defecte, visible en focus, jumpa
      a `<main id="main-content">`. Compleix WCAG 2.4.1 (Bypass
      Blocks).
- [x] `<main id="main-content" tabIndex="-1">` — destí del skip
      link, focusable programàticament des del cop.
- [x] `:focus-visible` global a `index.css` amb 2px outline groc
      (sobre superfícies fosques) o ink (sobre groc/blanc) +
      offset 2px. Compleix WCAG 2.4.7 (Focus Visible). Usa
      `:focus-visible` perquè els clics de ratolí no mostrin
      l'outline (només navegació per teclat).
- [x] Auditoria estàtica de patrons comuns sense violacions
      crítiques trobades:
      - Cap `<img>` sense `alt` (revisat tot `web-react/src`).
      - Inputs amb `<Field label>` wrapper (`PerfilUsuariPage`,
        `ComptePerfilPage`, `ProposarArtistaPage`).
      - Pills sempre amb text (no només color).
      - Landmarks ja correctes a `Layout.jsx`: `<header>`, `<nav
        aria-label>`, `<main>`, `<footer>`.
      - Hamburger button té `aria-label` + `aria-expanded`.
      - Cap `text-tq-yellow` directament sobre `bg-white` (el groc
        de marca sempre va sobre fons fosc).

**Auditoria axe-core a producció (2026-04-26)**:
Instal·lat `chromium-browser` (snap) + `@axe-core/puppeteer` a
`/tmp/axe/`. Executat amb tags `wcag2a`/`wcag2aa`/`wcag21a`/`wcag21aa`
sobre 6 pàgines públiques (`/`, `/top`, `/artista/zoo`,
`/canco/zoo-tot-anira-be`, `/comunitat`, `/compte/accedir`).

**Violacions trobades i corregides (4)**:
- [x] `/` — 3 nodes color-contrast a les targetes de territori
      (CAT `#c99b0c` 2.56:1, CNO `#0891b2` 3.68:1, FRA `#ea580c`
      3.55:1 sobre blanc). Substituïts per CAT `#8a6900` (5.08:1),
      CNO `#0e7490` (4.78:1), FRA `#c2410c` (4.84:1).
      `web-react/src/pages/HomePage.jsx` `COLORS`.
- [x] `/top` — 31 nodes color-contrast en els números de posició
      (`var(--color-tq-yellow)` sobre blanc, 1.53:1; el llindar
      WCAG AA per text gran és 3:1). Canviats a `text-tq-ink`
      (21:1). La icona de tendència manté el color de marca, així
      que la identitat visual es preserva sense violar contrast.
      `web-react/src/pages/TopPage.jsx`.
- [x] `/artista/zoo` — 1 node color-contrast a la metadada any
      de col·laboracions (`text-gray-400` `#99a1af` sobre blanc,
      2.6:1). Pujat a `text-gray-600` (5.7:1).
      `web-react/src/pages/ArtistaPage.jsx`.
- [x] `/compte/accedir` — `aria-required-children` al pill toggle
      (`role="tablist"` sense fills `role="tab"`). Afegit
      `role="tab"` + `aria-selected` + `tabIndex` al `TabButton`.
      `web-react/src/pages/AuthPage.jsx`.

**Re-auditoria final**: `0 violations` a les 6 pàgines auditades.

**Follow-up (no bloquejant)**:
- [ ] Pàgines staff a WCAG A — auditoria cas per cas pendent (no
      són públiques; volum baix d'usuaris).
- [ ] Verificació de mides de toc 44×44 px en touch devices —
      regla CSS global descartada per ser massa disruptiva sense
      review per component (inflaria pills de `StaffTable.Btn` i
      altres elements compactes per disseny).
- [ ] Testing visual mòbil 375 px en dispositiu real.

### Sprint G — Gestors d'artista i correu ✅ (2026-04-26)

> Donar agència als artistes verificats per editar-se directament i
> avaluar la infraestructura de correu.

**Bloc 1 — Correccions de camp per gestors d'artista**:
- [x] Nou camp `Artista.bio` (TextField, blank). Distingit dels
      `lastfm_bio_*` que el cron sobreescriu — aquest l'edita el
      gestor verificat. Migració `music 0053_artista_bio`.
- [x] Nova entrada al taxonomia `StaffAuditLog.ACTION_CHOICES`:
      `gestor_edita_artista` ("Artista: edició per gestor"). Migració
      `music 0052_add_gestor_edita_artista_action`.
- [x] Endpoint `GET/PATCH /api/v1/compte/artista/<pk>/editar/`
      (`web/api/compte_views.py::gestor_artista_editar`). Requereix
      `UserArtista(usuari, artista, verificat=True)`; 403 si no.
      PATCH escriu només els camps a la llista blanca:
        - text lliure: `bio`, `genere`
        - choices: `percentatge_femeni` (validat contra
          `Artista.PERCENTATGE_FEMENI_CHOICES`)
        - URL: tots els 12 `Artista.SOCIAL_LINK_FIELDS` (Spotify,
          Viasona, Web, Bandcamp, Myspace, YouTube, Viquipèdia,
          SoundCloud, TikTok, Facebook, Instagram, X) — validats amb
          `HTTP_ONLY_URL` (només http/https).
      Camps fora de la llista (nom, slug, deezer_ids, localitats,
      aprovat, MB lockouts) s'ignoren silenciosament. L'audit
      s'escriu **només** quan algun camp realment canvia
      (`metadata={camps: [...], usuari: pk}`).
- [x] Nova ruta SPA `/compte/artista/:pk/editar` →
      `GestioArtistaEditPage.jsx`. Formulari amb tres fieldsets
      (Sobre l'artista / Xarxes / botons), diff client-side perquè
      el PATCH només envia camps modificats, re-hidratació des de
      la resposta canònica del backend, errors per camp i missatges
      `Cap canvi per desar.` / `Desat. Camps actualitzats: …`.
- [x] Targeta `ArtistaCard` a `ComptePage.jsx` ara mostra un botó
      "Editar" als artistes verificats que ho enllaça. El payload
      `_serialize_user_artista` ara exposa `artista.pk` perquè el
      SPA pugui construir l'URL.
- [x] Tests: `web/tests/test_gestor_artista_editar.py` — 7 casos
      (anon, no-manager, GET, PATCH valid, camps crítics ignorats,
      URL invàlida, PATCH no-op no audita). 125 passed, 8 skipped.

**Bloc 2 — Valoració Hetzner Hosted Mail**:

Hetzner no ven el correu com a producte solt; va dins els plans
**Webhosting** (S/M/L/XL) amb mailboxes il·limitades, IMAP/SMTP+TLS,
webmail, CalDAV/CardDAV, DKIM/SPF/MX personalitzat. **Webhosting S**:
~€1,90–€2,50/mes + setup únic ~€9, 10 GB compartits. Per a 3-5
comptes: **€25-35/any tot inclòs**.

Comparativa cdmon actual:
- **Micropla** (l'actual): inclòs amb el domini, 1 mailbox, 100 MB,
  100 enviaments/dia. Cost addicional: €0 (ja paguem el `.cat`).
- **cdmon Standard Hosting Mail**: €4,95/mes (~€59/any), però
  mínim **10 mailboxes**, 5 GB cadascuna, DKIM/SPF/IMAP/SMTP/webmail
  complets.

**Recomanació: continuar amb cdmon, no migrar a Hetzner ara.**
L'estalvi (~€25/any) no compensa el canvi d'MX, refer SPF/DKIM/DMARC,
el setup fee, ni el risc de deliverability del `noreply@` durant la
transició. Quan es superi el límit de 100 enviaments/dia de Micropla
o calguen comptes addicionals, el següent salt natural és cdmon
Standard (els 10 slots no són un problema — s'utilitzaran).

**Comptes addicionals que tindrien sentit** quan es faci el salt:
- `info@` — contacte públic genèric (peu de pàgina).
- `premsa@` — premsa i festivals.
- `gestio@` — sol·licituds de gestió d'artista (ara no hi ha
  adreça d'entrada per a aquest flux).
- `hola@` — alias amistós per a comunitat/feedback.
- `noreply@` — es manté per a transaccionals (registre, activació, 2FA).

### Sprint H — Comunicació del producte i onboarding ✅ (2026-04-26)

> Que qualsevol visitant nou entengui immediatament què és
> TopQuaranta, què pot fer aquí i com començar. Cap pàgina nova de
> documentació estàtica: el contingut viu integrat a les pàgines
> existents. El document públic divulgatiu és part del SPA.

**Pàgines tocades**:

- [x] **HomePage (`HomePage.jsx`)** — afegida secció hero sota la
      graella de territoris: títol "El punt de trobada de la música
      en català", 2 línies de pitch, **3 blocs visuals** (icona +
      títol + 2 línies) per al top setmanal, mapa i comunitat. Cada
      bloc usa una icona de `mm-design/icons/ui/` (`icon-ranking`,
      `icon-mapa`, `user`) i una halo del color territorial real
      (BAL blau, VAL roig, CAT ambre) per ancorar la identitat
      geogràfica. **2 CTAs**: "Escolta el top" → `/top` i "Vols fer
      música amb algú?" → `/compte/accedir?mode=registre` per
      anònims o `/comunitat` per autenticats.
- [x] **TopPage (`TopPage.jsx`)** — afegit text introductori discret
      (3 línies, `text-xs text-white/60`) sobre el selector. No
      competeix visualment amb el rànquing.
- [x] **MapaPage (`MapaPage.jsx`)** — afegit panell d'introducció a
      sobre del grid del mapa. Explica què mostra, com navegar (clic
      → zoom, panell lateral) i la freqüència d'actualització.
- [x] **ComunitatPage (`ComunitatPage.jsx`)** — `IntroPanel`
      destacat a sobre del feed amb pitch ("Un espai per a músics i
      amants de la música en català…") i un únic CTA dependent
      d'estat: "Activa el teu perfil" si `visible_directori=False`,
      "Explora el directori" si ja hi és.
- [x] **ComunitatDirectoriPage (`ComunitatDirectoriPage.jsx`)** —
      capçalera amb dues frases: "Músics i creadors de música en
      català oberts a connectar i col·laborar" + suggeriment de
      filtres. La línia tècnica sobre activar la casella es manté.
- [x] **ComptePage (`ComptePage.jsx`)** — reestructurada amb
      guiatges contextuals (`GuidanceCard`) que apareixen i
      desapareixen segons l'estat:
        - Sense artistes verificats → "Tens un artista o grup?
          Proposa'l per aparèixer al top i al mapa." + botó.
        - Amb artistes verificats → cada targeta mostra "Millor
          posició al top: #N" o "Encara no està al top." + dos
          botons "Editar perfil" + "Veure al mapa".
        - `visible_directori=False` → "Vols que altres músics et
          trobin? Activa el teu perfil al directori." + botó
          "Activar perfil".
        - `visible_directori=True` → línia "✓ El teu perfil és
          visible al directori. Editar perfil →".
- [x] **OnboardingPage (`OnboardingPage.jsx`)** — abans dels camps
      del formulari, targeta amb 3 punts ("Què pots fer com a usuari
      registrat") explicant proposar/gestionar artistes, activar el
      perfil al directori i publicar a la comunitat. El botó
      "Saltar" es manté visible i accessible.
- [x] **ComFuncionaPage (`ComFuncionaPage.jsx`)** — pàgina **nova**
      a `/com-funciona`, accessible des del peu de pàgina, sense
      requerir autenticació. Sis seccions divulgatives en català (1)
      Què és TopQuaranta, (2) Com funciona el top — quatre factors
      en llengua planera, sense fórmules, (3) Què compta com a
      música en català — versió simplificada de `docs/DEFINITION.md`,
      (4) Qui decideix — staff + ML acceleratiu mai decisiu, (5) El
      que no farem mai — extracte del `MANIFEST.md`, (6) Com
      participar — enllaços a propostes, gestió, perfil, "Corregir"
      i GitHub. Disseny editorial: targetes blanques sobre fons
      ink, icones `mm-design/icons/ui/` per cada secció, tipografia
      Playfair per títols + Roboto per cos, accent groc de marca.

**Backend touchpoints**:
- [x] `/api/v1/compte/dashboard/` (`web/api/compte_views.py`) ara
      inclou un bloc `perfil` amb `visible_directori`,
      `onboarding_complet` i `nom_public`. Permet a la `ComptePage`
      i a la `ComunitatPage` mostrar guiatges sense un segon round-
      trip a `/comunitat/perfil/`.

**Routing + footer**:
- [x] Nova ruta `<Route path="/com-funciona" element={<ComFuncionaPage />} />`
      a `App.jsx` (a sobre dels routes autenticats — pàgina pública).
- [x] Enllaç "Com funciona" afegit al `FooterLine` de `Layout.jsx`,
      en primera posició abans d'"Open source · GitHub · Privacitat".

**Disseny — criteris seguits**:
- Cap hex hardcoded; tot via tokens (`tq-yellow`, `tq-ink`,
  `tq-yellow-deep`) o el palette territorial existent del
  `HomePage.COLORS`.
- Icones via el component `MmIcon` existent (mascarat CSS sobre SVGs
  de `vendor/mm-design/icons/`), pickup de `currentColor` per
  inheritance.
- Tipografia: Playfair (`font-display`) per títols/destacats, Roboto
  per cos. Jerarquia respectada.
- Densitat: textos introductoris a `text-xs`–`text-sm` amb
  `text-white/60`–`text-white/80` perquè no competeixin amb el
  contingut principal de cada pàgina.
- To: primera persona del plural, directe, sense paternalisme.

**Verificacions**:
- `manage.py check`: ✅ net.
- `pytest -q`: 125 passed, 8 skipped (cap test trencat).
- `npm run build`: ✅ net (1.11 MB JS / 309 kB gz; +6 kB respecte
  Sprint G per la nova pàgina + hero + intros).
- `systemctl reload topquaranta-web`: ✅ tres pàgines noves
  responen 200 (`/`, `/top`, `/mapa`, `/com-funciona`, `/comunitat`).

### Sprint I bis — Redisseny editorial de la HomePage ✅ (2026-04-26)

> Convertir `/` d'una pàgina-selector de territoris a una portada
> editorial vertical en deu seccions, inspirada en FACT/Bandcamp/RA.
> El selector de territoris desapareix de la home (queda al `/top` i
> al `/mapa`). Cada secció té un propòsit narratiu propi.

**Backend — endpoints nous** (`web/api/home_views.py`):
- [x] `GET /api/v1/stats/` — `{cancons_verificades, artistes_aprovats,
      territoris_actius, setmana}`. `cache_for_anon(60s)`.
- [x] `GET /api/v1/top/nova-setmana/` — entrada amb `posicio_anterior=null`
      i menor `posicio` al darrer top oficial PPCC.
      `cache_for_anon(3600s)`.
- [x] `GET /api/v1/artistes/destacat/` — artista amb `UserArtista.verificat=True`
      que ha tingut la millora de posició més gran al PPCC respecte
      la setmana anterior; tie-breaker per nombre de cançons
      verificades. Inclou `bio_curta` truncada a 120 caràcters i
      imatge `lastfm_image_large`. `cache_for_anon(3600s)`.
- [x] `GET /api/v1/artistes/descoberta/?limit=6` — artistes
      `aprovat=True` aprovats els darrers 30 dies amb almenys una
      cançó verificada que mai han aparegut a `TopSetmanal`. Capat
      a 12. `cache_for_anon(3600s)`.

**Backend — extensions a endpoints existents**:
- [x] `GET /api/v1/albums/` (nou llistat — abans només existia
      `/api/v1/albums/<slug>/`). Filtres: `ordering=-data_llancament`
      o `data_llancament`, `amb_verificades=true|false`, `limit≤24`.
      Retorna `n_verificades` i `imatge_url` per àlbum.
- [x] `GET /api/v1/top/?oficial=true&limit=N` — força resposta des
      de `TopSetmanal` (sense fallback a `TopProvisional`); buida
      explícitament si encara no hi ha top oficial. `limit` capat a
      `MAX_POSICIONS_TOP` (40).

**Frontend — `HomePage.jsx` reescrita completament**:
Deu seccions verticals amb fons alternat ink/blanc per crear ritme
sense línies divisòries. Tots els colors via tokens `tq-*` o
`var(--mm-color-*)`; els colors territorials viuen al diccionari
`TERR_COLORS` (mapping de marca documentat al fitxer).
1. **Hero** — pitch principal, 3 blocs (top/mapa/comunitat) amb
   icones `mm-design/icons/ui/`, 2 CTAs i link discret a
   `/com-funciona`.
2. **Stats** — tres números prominents amb tipografia editorial.
3. **Top oficial PPCC** — primeres 10 entrades amb cue de tendència
   (`badge-new`, `arrow-up-trend`, `arrow-down-trend`, `dash-stable`).
4. **Cançó nova de la setmana** — targeta gran amb caràtula 280px.
5. **Artista destacat** — imatge circular, badge territorial amb
   icona pròpia, bio truncada.
6. **Últims llançaments** — grid 3×2 d'àlbums amb caràtula i
   recompte de cançons verificades.
7. **Artistes en descoberta** — grid 3×2 amb territoris i gènere.
8. **Territori en focus** — rotació setmanal mitjançant
   `isoWeek(now) % FOCUS_TERRITORIS.length`. Mostra el badge SVG
   territorial gros + top-3 oficial d'aquell territori + recompte
   d'artistes aprovats. Link a `/artistes?territori=<codi>`.
9. **Notícies de la comunitat** — només autenticats; 3 publicacions
   més recents en estat `publicat` via `/comunitat/publicacions/`.
10. **Compte enrere** — peu discret amb temps fins el proper
    dissabte a les 9h, amb estats per dissabte/diumenge.

**Llenguatge i to**:
- "Vols fer música amb algú?" → "Vols trobar algú amb qui fer música?"
  a la CTA del hero (`HomePage.jsx`).
- Resta de textos del Sprint H revisats; ja eren en primera persona
  del plural i to comunitari.

**Verificacions**:
- `manage.py check`: ✅ net.
- `pytest -q`: 125 passed, 8 skipped.
- `npm run build`: ✅ net (1.12 MB JS / 312 kB gz; +2,5 kB respecte
  Sprint H per la nova home).
- `systemctl reload topquaranta-web`: ✅. Smoke test 200 a `/` i
  resposta vàlida a tots els endpoints nous (`/api/v1/stats/`,
  `/api/v1/top/nova-setmana/`, `/api/v1/artistes/destacat/`,
  `/api/v1/artistes/descoberta/`, `/api/v1/albums/?...`,
  `/api/v1/top/?...&oficial=true`).

### Sprint J bis — Redisseny editorial /top, /artistes, /mapa, /comunitat ✅ (2026-04-26)

> Aplicar el llenguatge editorial de la HomePage (bandes
> alternants ink/blanc, kicker + títol Playfair, tone-aware) a la
> resta de pàgines públiques. Extreure primitives compartides per
> reduir duplicació i evitar regressions.

**Components compartits nous** (`web-react/src/components/editorial.jsx`):
- `<Section tone>` — banda full-bleed amb fons ink/blanc.
- `<SectionHeader kicker title>` — kicker tone-aware (groc sobre
  ink, ink/60 sobre blanc) + títol Playfair.
- `<TerritoriBadge codi>` — SVG monocrom via mask, hereta
  `currentColor`.
- `<TrendCue posicio posicio_anterior>` — cue de tendència estàndard
  per a totes les llistes de top.
- `TERR_COLORS`, `TERRITORI_NOM`, `FOCUS_TERRITORIS` — taules de
  marca exposades una vegada.

`HomePage.jsx` i `TopPage.jsx` migrades a aquests imports;
~120 línies de duplicació eliminades.

**Backend**:
- [x] `/api/v1/top/` ara retorna `prev_setmana` + `next_setmana`
      (ISO o `null`) calculats sobre el territori resolt després
      del fallback. Permet al SPA habilitar/deshabilitar les
      fletxes del navegador setmanal de manera correcta.

**TopPage** (`/top`):
- Hero ink: kicker "El nostre top setmanal" + títol gegant
  ("Top {territori}", e.g. "Top Global"), pills de territori,
  navegador setmanal amb fletxes ←/→ deshabilitades als límits +
  link "Tornar a l'última →" quan no estàs a la setmana actual.
  Pill "Provisional" si el top és provisional.
- Llista en banda blanca: 40 entrades en 2 columnes (1-20 / 21-40)
  amb `TopRow` compartit.
- Banda peu ink discreta amb link a `/com-funciona`.
- URL: `?t=<codi>` + `?s=<YYYY-MM-DD>` (totes dues opcionals).

**ArtistesPage** (`/artistes`):
- Hero ink: kicker "Directori", títol "Artistes", recompte total.
  Filtres dins el hero: cerca per nom + pills territorial + dropdowns
  cascada (comarca / municipi) + 3 toggles (amb dones / llançaments
  últim any / amb cançons al top) + "Netejar filtres".
- Resultats en banda blanca: grid de 4 columnes amb `ArtistaCard`
  (caràtula quadrada o monograma de territori, nom, localitat,
  badges de territori amb icona, gènere). Paginació al peu amb
  botons ink.

**MapaPage** (`/mapa`):
- Hero ink: kicker "Mapa" + títol "La música al territori" + 3
  línies d'explicació concisa de la interacció.
- Mapa + panell lateral en banda blanca, sense canvis funcionals.
- Eliminat el panell d'introducció en línia (quedava redundant).
- KPI principal del panell ara `text-tq-ink` en comptes de
  `text-tq-yellow-deep` (era 3.6:1 sobre blanc — fail WCAG AA per
  text gran serif).

**ComunitatPage** (`/comunitat`):
- Sense bandes full-bleed (la pàgina viu dins `ComunitatLayout`
  amb sidebar; les bandes ink/blanc xocarien).
- Targeta-hero al capdamunt amb pitch + CTA dependent d'estat
  (Activar perfil / Explora directori).
- Pills de filtre amb `role="tablist"`/`role="tab"`/`aria-selected`.
- Vista anònima amb la mateixa shape (targeta-hero + dos botons
  Feed públic / Registra't).
- Estat-badges del feed amb tons que passen 4.5:1 sobre blanc.

**ComunitatDirectoriPage** (`/comunitat/directori`):
- Targeta-hero al capdamunt (mateixa shape que `ComunitatPage`).
- Tots els controls de filtre amb `<label>` (alguns `sr-only`
  perquè la primera opció ja fa de label visualment).

**Llenguatge i a11y**:
- "Catalunya" / "País Valencià" / etc. mantinguts. Només "PPCC" →
  "Global" al text visible. Els camps i query params interns es
  mantenen com `PPCC`.
- 5 violacions de contrast detectades i corregides per la auditoria
  axe-core sobre 10 pàgines públiques (color-contrast a `text-white/40`
  sobre ink, `text-tq-ink/40`/`/50` sobre blanc, `text-tq-yellow-deep`
  sobre blanc, `text-white opacity-80` sobre brand colors,
  brand colors com text d'enllaç sobre tq-ink).
- Re-auditoria final: **0 violacions a 10 URLs** (`/`, `/top`,
  `/top?t=cat`, `/artistes`, `/mapa`, `/comunitat`,
  `/comunitat/public`, `/com-funciona`, `/artista/zoo`,
  `/compte/accedir`).

**Tests**:
- Nou `web/tests/test_home_views.py` — 7 casos cobrint stats,
  destacada (fallback a #1, biggest-climber tie-breaker),
  descoberta (diversitat per territori), destacat (requereix
  gestor verificat), top oficial sense fallback, prev/next
  setmana. **132 passed, 8 skipped** total.

**Verificacions**:
- `manage.py check`: ✅ net.
- `pytest -q`: 132 passed / 8 skipped.
- `npm run build`: ✅ net (1.13 MB JS / 313 kB gz).
- `systemctl reload topquaranta-web`: ✅ 200 a totes les URLs
  públiques esmentades.
- axe-core (puppeteer): 0 violacions sobre 10 URLs.

### Sprint I — Instagram automàtic

> Distribuir els tops setmanals automàticament al canal d'Instagram.

- [ ] Publicar automàticament els tops setmanals a Instagram.
- [ ] Definir format visual, compte, credencials i cron.
- [ ] Avaluar si usar l'API oficial de Meta o una solució alternativa.

### Sprint J — Privacitat i cookies

> Posar el lloc al dia amb el GDPR.

- [ ] Implementar GDPR: política de privacitat, política de cookies,
      banner de consentiment.
- [ ] Revisar quines dades es guarden i amb quin propòsit.
- [ ] Textos legals en català.

### Sprint K — Capa editorial pública

> Donar a un visitant nou una entrada clara al projecte.

- [ ] Pàgines de contingut per a nous visitants: com funciona el
      projecte, per què registrar-se, què et trobaràs com a usuari,
      com proposar un artista.
- [ ] Integrar-ho a la navegació principal.

### Sprint M — Naming consolidation: "ranking" → "top" ✅ (2026-04-25)

> Unificar el lèxic del projecte sota un sol mot canònic ("top",
> alineat amb la marca TopQuaranta) sense trencar dades, URL públiques
> ni APIs externes.

- [x] **Pas 1 — UI** (5 strings, 4 fitxers): "Ranking prov." → "Top
      provisional"; "rànquing" → "top" al `RankingBreakdownPanel`;
      títols staff actualitzats.
- [x] **Pas 2 — URLs API**: `/api/v1/top/` (canònica) + 301 des de
      `/api/v1/ranking/` (GET-only, query string preservat).
      Endpoints staff (`/staff/top/`, `/staff/top/accio/`,
      `/staff/cancons/<pk>/top/`) amb alias POST-safe a les rutes
      antigues. SPA route `/staff/top` + `<Navigate>` legacy.
- [x] **Pas 3 — Fitxers Python**: `ranking_views.py` →
      `top_views.py`, `web/api/staff/ranking.py` → `staff/top.py`,
      `scripts/simular_ranking.py` → `simular_top.py`. Imports
      actualitzats.
- [x] **Pas 4 — Funcions/constants**: `calcular_ranking_territori`
      → `calcular_top_territori`, `_calcular_ranking_ppcc` →
      `_calcular_top_ppcc`, `_ranking_for_territoris` →
      `_top_for_territoris`, `territoris_amb_ranking_propi` →
      `territoris_amb_top_propi`, `ranking_list/_accio` →
      `top_list/_accio`, `canco_ranking_breakdown` →
      `canco_top_breakdown`, `RANKING_TERRITORIS` →
      `TOP_TERRITORIS`, `_ranking_last_modified/_etag` →
      `_top_last_modified/_etag`. Aliases legacy a
      `staff/__init__.py`.
- [x] **Pas 5 — Models** (alt risc, fet amb `pg_dump` previ +
      migració manual `ranking 0013_rename_models_to_top` amb
      `RenameModel` ops): `RankingSetmanal` → `TopSetmanal`,
      `RankingProvisional` → `TopProvisional`. Taules SQL renombrades
      via `ALTER TABLE … RENAME TO …` (502 files preservades sense
      pèrdua). Aliases legacy a `ranking/models.py`. App label
      `ranking` mantingut intencionalment (renaming-lo afecta
      ContentType i 30+ migracions; sprint propi futur).
- [x] **Pas 6 — Command** `calcular_ranking` → `calcular_top`.
      Cron + tq-recover actualitzats. Status files antics queden
      orfes a `/var/log/topquaranta/status/` (logrotate els netejarà).
- [x] **Pas 7 — Logs**: `provisional.log` → `top-provisional.log`,
      `ranking.log` → `top.log`. Symlinks de compatibilitat per
      preservar historial. logrotate.d actualitzat.
- [x] **Pas 8 — Icona**: `icon-ranking.svg` no s'usa al SPA — cap
      canvi necessari.
- [x] **Pas 9 — Documentació**: substituïdes les ocurrències de
      "rànquing"/"ranquing" a CLAUDE_*.md, ROADMAP.md, README.md.

**Mètriques globals**:
- Fitxers tocats: ~30 (codi + docs + ops).
- Ocurrències canviades: ~150+ (textos UI: 5; URLs SPA: 8; Python:
  112 imports/refs; cron/log: 6).
- Migracions noves: 1 (`ranking 0013_rename_models_to_top`).
- Tests: 118/8 (sense regressions).
- Backup pre-rename: `/tmp/topquaranta_pre_rename_*.sql` (28 MB).

**Coses no canviades intencionalment**:
- App label `ranking` (cost desproporcionat: ContentType + 13
  migracions + cascada FKs reverse).
- Carpeta `ranking/` (lligada a l'app label).
- Prefix DB tables `ranking_*` (idem).
- Related-name `Canco.rankings` (back-reference; canviar-lo trenca
  filters arreu del codi).
- Comentaris i docstrings amb la paraula "ranking" en context
  algorítmic (terme tècnic correcte en anglès).
- `CLAUDE_EXCELLENCE.md` i `CLAUDE_LEGACY.md` deixats parcialment
  intactes (referència històrica, prioritat baixa).

### Sprint L — Metadata d'artista des de Last.fm ✅ (2026-04-25)

> Enriquir les fitxes d'artista amb dades públiques de Last.fm i
> aprofitar la xarxa de `getSimilar` per descobrir artistes
> propers als nostres aprovats.

- [x] 14 camps `lastfm_*` nous a `Artista` + `nb_similars_lastfm`
      (migració `music 0050`).
- [x] Client Last.fm ampliat amb `get_artist_info(artist_name)` i
      `get_artist_similar(artist_name, limit=100)`. Mateix patró
      retry/rate-limit que `get_track_info`.
- [x] Nou command `obtenir_metadata_lastfm` (`--limit`,
      `--artista-id`, `--refresh-days`, `--dry-run`). Cua de
      prioritat aprovat → pendent → discartat, oldest sync first.
      Idempotent per recencia (no toca dues vegades el mateix
      artista en menys de 7 dies).
- [x] Cron diari 05:00 UTC (`obtenir_metadata_lastfm --limit 500`),
      en paral·lel amb Whisper. ~3 minuts per cua plena.
- [x] Staff: columna `Similars LFM` a `StaffArtistesPage` i
      `PendentsPage`; filtre `font_descoberta=lastfm_similar` i
      sort `?sort=similars_lastfm` a Pendents; nou panell
      `LastfmPanel` (lectura) a `ArtistaEditPage` amb url, bio,
      listeners, playcount total, ontour, tags, imatges, last sync.
- [x] Documentació: `CLAUDE_MODELS.md` (camps + migració),
      `CLAUDE_PIPELINE.md` (§3.8 + cron table), aquest ROADMAP.

---

## Shelved indefinitely

- Image generation (PIL) for ranking posters.
- Telegram / Instagram distribution.

Original assets (TTF fonts, SVG territory logos) were on a local machine
that is no longer accessible. The public website is the distribution
channel instead.

---

## Ground rules for future work

- Never commit without explicit request.
- Update this file at the end of each session.
- Follow the conventions in `CLAUDE.md` §9.
- No new parallel design systems — tokens come from mm-design.
- No raw SQL outside `ranking/algorisme.py` and migrations.
- When in doubt about a decision, check §5 of `CLAUDE.md`.
- While Phase 9 is active: tag each commit's subject with the finding ID
  (e.g. `fix(S1): rotate DB password and update .env template`) so progress
  against `CLAUDE_EXCELLENCE.md` is traceable.
