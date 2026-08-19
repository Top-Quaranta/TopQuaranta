# Platform Overview — TopQuaranta

> Cross-cutting onboarding map of the whole platform. Read this first in a
> fresh session, then jump to the per-subsystem docs under
> `docs/architecture/` for depth. Every section cites `file_path:line` so
> you can jump straight to the code. Cross-cutting on purpose, so it lives
> at the top level of `docs/` (like `docs/EMAIL.md`) rather than under the
> size-gated `docs/architecture/`.
>
> Last verified against the codebase + production DB: 2026-06-09.

## Index

1. [Stack & architecture (Wagtail resolved)](#1-stack--architecture)
2. [Data model](#2-data-model)
3. [Data sources & ingestion pipeline](#3-data-sources--ingestion-pipeline)
4. [Territory system](#4-territory-system)
5. [Staff review flow & API](#5-staff-review-flow--api)
6. [Per-song editing (+ where a manual Spotify URL fits)](#6-per-song-editing)
7. [Social / stories subsystem](#7-social--stories-subsystem)
8. [Recent relevant PRs](#8-recent-relevant-prs)
9. [Known gaps & debt (+ "per verificar" diagnostic)](#9-known-gaps--debt)
10. [Community subsystem](#10-community-subsystem)

---

## 1. Stack & architecture

**Confirmed stack: Django 6.0 + DRF + React SPA + PostgreSQL 14.** No CMS.

- Backend: Django 6.0, Django REST Framework, Python 3.12 (`README.md:61-75`,
  `CLAUDE.md` §3). Settings split into `base / production / web_server /
  local / test` (`topquaranta/settings/`).
- Frontend: React 19 + Vite 8 + Tailwind v4 SPA at `web-react/` — both the
  public site and the staff panel (`CLAUDE.md` §2). Django is a pure API
  backend plus a few server-rendered auth/SEO pages.
- DB: PostgreSQL 14, ~48 tables.
- Edge: Caddy (auto-TLS) reverse-proxies `/api/v1/*`, the auth/2FA pages,
  `sitemap.xml`, `/rss/*`, `/static/*`, `/portades/*`, `/media/*` to
  gunicorn `:8083`; everything else falls through to `web-react/dist/`
  (`CLAUDE.md` §2). Server: Hetzner CX22 (`188.245.60.20`).

### Wagtail: gone. Definitively not in the stack.

A previous incarnation of the site ran on **Wagtail CMS**; it was fully
removed. The only residues are inert:

1. `music/migrations/0001_initial.py:61` — a frozen `help_text="False =
   pending human review in Wagtail admin."` baked into the initial
   migration string. Historical text only; the live field's help_text was
   since updated to "...in staff panel." (`music/models.py:148`).
2. `docs/history/changelog.md:37,39` — records "Dropped pre-2026 legacy DB
   tables (Wagtail CMS…)" and "Removed legacy Wagtail admin service."
3. `vendor/mm-design/README.md:109,161` — the **vendored** design-system
   README (not TopQuaranta-authored) still lists `topquaranta.cat` as
   "Django / Wagtail". Stale third-party label; ignore.

There is **no `wagtail` dependency** in `requirements.txt`, **no
`admin.py`** with `ModelAdmin` registrations anywhere in the repo, and no
Django-admin URL mounted. Confirmed by grep: zero `admin.site.register` /
`@admin.register` / `ModelAdmin` hits in app code. The staff back-office is
100 % the custom DRF API (`web/api/staff/`) + React (`web-react/src/pages/
staff/`). See §5.

---

## 2. Data model

Domain models live in `music/models.py`; ranking/config models in
`ranking/models.py`. Full reference: `docs/architecture/music.md`.

### Core entities (`music/models.py`)

| Model | Line | Purpose |
|---|---|---|
| `Territori` | 16 | 1 row per territory code (`CAT`, `VAL`, …). Data-migration seeded. |
| `Municipi` | 34 | Municipality → comarca → `Territori` FK. PPCC location source. |
| `Artista` | 89 | The artist. Custom manager `ArtistaQuerySet` (60): `.public()`, `.pendents()`, `.with_ppcc()`, `.with_mbid()`. |
| `ArtistaDeezer` | 549 | M2M of Deezer artist IDs (an artist can have several). `deezer_id_principal` property (469). |
| `ArtistaLastfmAlias` | 569 | Staff-curated alternate Last.fm names summed into the signal (`confirmat` / `rebutjat` / `prioritari`). |
| `ArtistaLastfmSimilar` | 698 | Row-per-edge `source→target` getSimilar recommendations (dedup; recomputable). |
| `ArtistaLocalitat` | 768 | Links artist → `Municipi` (or `localitat_manual` for non-PPCC). Drives territories. |
| `Album` | 831 | `deezer_id` (unique), `data_llancament`, `tipus` (album/single/ep), `last_album_check` (848), `descartat` (860), `label` (887). |
| `Canco` | 942 | The track. Manager `CancoQuerySet` (927): `.public()`, `.pendents()`. |
| `HistorialRevisio` | 1163 | Append-only review decisions (the rejection trail). |
| `StaffAuditLog` | 1285 | Append-only audit of every consequential staff action (~50 action codes, 1301). |
| `SpotifyAuth` | 1416 | Singleton OAuth refresh token (pk=1). |
| `SpotifyPlaylist` | 1451 | Output playlists: `top` / `novetats` / `no_verificades`; `freq` daily/weekly. |
| `SpotifyMetadata` | 1525 | Per-`Canço` Spotify enrichment (Process B). Identifier/disambiguation only. |

### `Canco` key fields (`music/models.py:942`)

- `deezer_id` (959, unique-when-set), `spotify_id` (958), `isrc` (960) —
  ISRC is the universal key; `canco_isrc_unique_when_set` constraint (1080).
- `album` FK (965, CASCADE), `artista` FK (966, main), `artistes_col` M2M
  (972, collaborators). Territory = union of all of them (`get_territoris`,
  1149).
- `data_llancament` (1000) — release date; the 12-month cutoff anchor.
- **`activa`** (1006, default True) and **`verificada`** (1007, default
  False) — the publish gates. Only `verificada=True AND activa=True` tracks
  are public / counted by the ranking (`CancoQuerySet.public()`, 933).
- `contributors_raw` (1031) — JSON of unresolved Deezer contributors,
  deferred to approval time (the 2026-05-07 fix that cut ~76 % of pendent
  noise; see the field docstring).
- `ml_classe` / `ml_confianca` (1032) — Random-Forest pre-classification.
- `whisper_lang` / `whisper_p` / `whisper_all_probs` (1039-1045) — Whisper
  language ID over the Deezer preview.
- `mb_recording_id` / `mb_lyrics_language` / `mbrainz_confirmed`
  (1048-1055) — MusicBrainz cross-reference.

### State machines

**`Canco` (verificada × activa)** — managers at `music/models.py:927-939`:

| verificada | activa | Meaning |
|---|---|---|
| `True` | `True` | **Live** — public + counted (`.public()`). |
| `False` | `True` | **Pending review** — the staff queue (`.pendents()`). |
| `False` | `False` | **Rejected** — kept forever as a dedup marker (so a re-issue isn't re-ingested). `netejar_caducades` must NOT delete these. |
| `True` | `False` | Verified-then-deactivated (rare; e.g. caducat-but-verified). |

**`Artista` (aprovat × pendent_review)** — `music/models.py:145-160`, with a
`CheckConstraint` (424) forbidding `aprovat=True AND pendent_review=True`:

| aprovat | pendent_review | Meaning |
|---|---|---|
| `True` | `False` | Live. |
| `False` | `True` | In `/staff/artistes/pendents/`. |
| `False` | `False` | Discarded (kept for FK integrity). |

**`HistorialRevisio`** (`music/models.py:1163`): `decisio ∈ {aprovada,
rebutjada}`, `motiu` is the *action* that resolved it — `ok` / `auto_ml` for
approvals; `desvincular_canco` / `desvincular_album` / `desvincular_artista`
for rejections (`music/constants.py::MOTIUS_REBUIG`; semantics in
`docs/architecture/web.md` §5). Denormalises `canco_isrc` +
`canco_deezer_id` so the rejection trail survives the `Canco` row's deletion.
`reconsiderada` (1255) re-opens a rejected track for re-ingestion.

---

## 3. Data sources & ingestion pipeline

**Signal** = Last.fm (`playcount` + `listeners`). **Metadata** = Deezer
(public, 100 % ISRC). **Output** = Spotify playlists. **Disambiguation
oracle** = MusicBrainz. Full pipeline: `docs/architecture/ingesta.md`.

Commands live in `ingesta/management/commands/`. The cron table is
`deploy/cron.topquaranta` (every line runs through `bin/tq-run`, which
captures status for `tq-health` and retries 3× on failure).

### Cron schedule (UTC)

| When | Command | What |
|---|---|---|
| hourly `:00` | `obtenir_novetats` | Deezer incremental ingest (P1/P2/P3). |
| hourly `:30` | `obtenir_metadata_musicbrainz --limit 100` | MB oracle (MBID/area/dates/discography), 1 req/s. |
| 02:00 | `descarregar_portades --entitat all --limit 200` | Self-host Deezer covers → webp/avif/jpg. |
| 03:00 | `enriquir_spotify --limit 50 --throttle 1.0` | Process B (ISRC→Spotify id). |
| 04:00 | `netejar_caducades` | Delete expired unverified tracks (see §9). |
| 04:00 | `analitzar_whisper --limit 200` | Whisper LID on previews (shares `ram_heavy` lock w/ MB). |
| 05:00 | `obtenir_metadata_lastfm --limit 500` | Last.fm artist info + similars. |
| 05:00 | `enriquir_spotify_rebuigs --shortlist-only --include-orfes` | Backfill rejected rows' Spotify ids (AIMD-controlled). |
| 06:00 | `obtenir_senyal` | Last.fm signal → `SenyalDiari` per (canço, day). |
| 06:45 | `detectar_anomalies_senyal` | Flag phantom playcount spikes (`corregit`). |
| 07:00 | `calcular_top --provisional` | Daily provisional ranking → `TopProvisional`. |
| `:15` every 2 h | `actualitzar_playlists_spotify --freq daily` | Process A, cache-only (no `/search`). |
| Sat 08:00 | `calcular_top` | **Official weekly ranking** → `TopSetmanal`. |
| Sat 09:30 → 10:00 | `publicar_social` / `publicar_canal …` | Multi-channel distribution (§7). |
| Sat 10:00 | `actualitzar_playlists_spotify --freq weekly` | Process A weekly slice. |
| Mon 02:00 / 02:15 | `netejar_pendents_orfes` / `netejar_pendents_no_ppcc` | Weekly pendent-queue hygiene. |

(Plus SEO inference 02:00, metrics 21:00–23:30, `tq-recover` */30, `tq-health
--email-on-fail` hourly, backups 03:00, quarterly `arxivar_senyal_vell`.)

Note: the ranking command is **`calcular_top`**
(`ranking/management/commands/calcular_top.py`); the models are
**`TopSetmanal`** / **`TopProvisional`** (renamed from `Ranking*` in
migration `ranking/0013`, tables `ranking_top{setmanal,provisional}`).

### `obtenir_novetats` — P1/P2/P3 (`ingesta/management/commands/obtenir_novetats.py`)

A single hourly command with a priority queue (help string at line 97):

- **P1** — ISRC backfill on tracks missing an ISRC.
- **P2** — re-scan existing albums on a **per-album cooldown** keyed on
  `Album.last_album_check` (178-260): <30 d since release → 24 h, 30-365 d →
  7 d, >365 d / unknown → 30 d; `NULL` = never checked → highest priority
  (`order_by(F("last_album_check").asc(nulls_first=True))`, 233).
  `descartat=True` is the only permanent exclusion (192-201).
- **P3** — approved artists, oldest `last_checked_deezer` first; asks Deezer
  for `get_artist_albums(min_date=cutoff)` (324). Capped by
  `--max-p3-per-run` (110) so one tick doesn't monopolise the hour.
- Dedup: `_create_track` (422) / `_create_album` (598) dedup by `deezer_id`
  + ISRC; iterates **every** `ArtistaDeezer` of an artist, principal first.

**Rejection filter** — `_previously_rejected(isrc, deezer_id)`
(`obtenir_novetats.py:29-64`): returns True if any
`HistorialRevisio(decisio="rebutjada", reconsiderada=False)` matches by ISRC
**or** deezer_id, and the track is skipped (called at line 441). Survives
physical deletion of the `Canco` because HR denormalises both keys.
`reconsiderada=True` rows no longer block (the staff re-opened them).

**Caducity guard at creation** — `_create_track` calls
`is_caducat(album.data_llancament, cutoff)` and skips creating tracks older
than `DIES_CADUCITAT`. Helper: `ingesta/caducitat.py`. Merged via **PR #131**
(`021bf03`, *DIES_CADUCITAT guard at every Canco-creation frontier*) with the
enrich-pool follow-up **PR #141** (`aac3999`); both are ancestors of
`origin/main`. It closes a hole where ancient albums recreated pendents every
~30 days (real case in the docstring: "Tres Fan Ball 1994/1997/2005/2013…
recreating 38 pendents"). See §9 for the residual NULL hole.

### Signal — `obtenir_senyal`

Stores raw `lastfm_playcount` + `lastfm_listeners` per `(canço, data)` in
`SenyalDiari` (`ranking/models.py:209`). Aliases: `ArtistaLastfmAlias`
(confirmed) names are summed into the canonical track's signal
(`music/models.py:569` docstring; Böira/Boira → one 23 k-play signal).
Sets `Artista.lastfm_te_scrobbles=True` on first non-zero playcount
(`music/models.py:173`). No normalisation step — the ranking reads the
weekly delta of playcount directly.

### Deezer / MusicBrainz metadata

- `obtenir_metadata` — Deezer track/album metadata + `label`; catches
  `IntegrityError` on ISRC collisions and skips the dup (2026-05-03 fix).
- `obtenir_metadata_musicbrainz` — MBID + area + begin/end dates + aliases +
  tags + discography; reconciles by ISRC then fuzzy title; validates the
  artist's MBID against PPCC localitats every tick (auto-unassign on
  mismatch). Strict resolver (`resolve_mbid`) ignores Lucene score.

### Spotify residue — what's alive vs dormant

Spotify is now **identifier + playlist output only** (ADR-0012/0013), never a
metadata source. Two cleanly-split processes:

- **Process A (alive)** — `actualitzar_playlists_spotify` (`--freq daily`
  every 2 h, `--freq weekly` Sat). **Cache-only since 2026-05-22**: reads
  `SpotifyMetadata.spotify_id`, never calls `/v1/search`. Replaces playlist
  tracklists in place so URL + followers persist.
- **Process B (alive, throttled)** — `enriquir_spotify` (nightly 03:00) and
  `enriquir_spotify_rebuigs` (05:00, AIMD rate controller). ISRC → `/search`
  → `/tracks` → `/artists`; fills `SpotifyMetadata`. Drives the
  `spotify_artist_dispersio` homonym signal (`music/models.py:390`).
- **Setup/auth (run-once)** — `autoritzar_spotify`, `configurar_spotify_
  playlists`, `recalcular_dispersio_spotify`.
- **Dormant** — the `Artista.spotify_id` / `Album.spotify_id` columns
  predate the Process-A/B split and are largely unused for sync; live
  Spotify ids live in `SpotifyMetadata`. Catalog reads via Client
  Credentials are NOT relied on (owner-Premium policy change, ADR-0012).

---

## 4. Territory system

10 codes (`music/constants.py:11-56`), partitioned:

- `TERRITORIS_FIXOS = (CAT, VAL, BAL)` — the three always-on territorial tops.
- `TERRITORIS_OPCIONALS = (CNO, AND, FRA, ALG, CAR)` — smaller territories.
- `TERRITORIS_AGREGATS = (ALT, PPCC)` — `ALT` (catch-all "Altres"), `PPCC`
  (the Global aggregate; shown to visitors as "Global").
- `TERRITORIS_VALIDS = (CAT, VAL, BAL, PPCC, ALT)` — currently
  ranking-eligible.
- `TERRITORIS_PPCC_SOURCES = (CAT, VAL, BAL, AND, CNO, FRA, ALG)` — feed the
  PPCC aggregate.

Territory is **not** stored on the track. It is derived:
`ArtistaLocalitat → Municipi → Territori`, recomputed into the
`Artista.territoris` M2M by `sync_territoris_from_localitats`
(`music/models.py:510`), fired by signals. A track appears in territory T if
**any** of its artists (main or collaborator) belongs to T
(`Canco.get_territoris`, 1149). PPCC municipality = `municipi` FK non-NULL;
non-PPCC = `localitat_manual` with `municipi=NULL` → contributes `ALT`.

**"per verificar 1"** (the staff "to-verify" queue): the *N* next to a
territory/filter is a count of `Canco.objects.pendents()` (verificada=False,
activa=True) scoped by that filter. The whole queue is the dashboard's
`cancons_no_verificades` counter (`web/api/staff/dashboard.py:91`). See §9
for why a specific surface can read "1" while the global queue is large.

---

## 5. Staff review flow & API

The back-office is a **custom DRF API** under `web/api/staff/` consumed by
the React staff pages — **not** Django ModelAdmin, **not** Wagtail (see §1).
Endpoints require `IsStaff`. Routes in `web/api/urls.py` (`staff/*`). Full
contract: `docs/architecture/web.md`.

Modules (`web/api/staff/`): `dashboard`, `cancons`, `artistes`, `pendents`,
`albums`, `propostes`, `solicituds`, `sollicituds_revisio`, `senyal`,
`historial`, `configuracio`, `audit`, `estat`, `usuaris`, `feedback`, `top`,
`analytics`, and `social/`.

### Verify / reject a song (`web/api/staff/cancons.py`)

- **List** `GET /api/v1/staff/cancons/` → `cancons_list` (151). Default
  `verificada=0` → `Canco.objects.pendents()`, sorted `-ml_confianca`. Rich
  filters: `ml_classe`, `whisper`, `deezer`, `mb`, `preview`, `recent`,
  `q`, `artista_pk` (166-262). No territory filter.
- **Approve/reject** `POST /api/v1/staff/cancons/accio/` → `cancons_accio`
  (289). Body `{action, ids, motiu}`:
  - `aprovar` → `aprovar_canco(c)` per id + `log_staff_action("canco_aprovar")`
    + `recalcular_ml_si_cal()` (298-304).
  - `rebutjar` with `motiu=desvincular_artista` → `rebutjar_artista` on each
    artist; `desvincular_album` → `rebutjar_album` (physical
    `cancons.delete()`); else `rebutjar_canco` per track (311-343). All write
    `HistorialRevisio` + `StaffAuditLog`.
- ML auto-approval path: `aprovar_canco_auto_ml` (services) processes
  deferred `contributors_raw`.

Other queues: artist triage `/staff/artistes/pendents/`
(`pendents.py`); new-artist proposals (`propostes.py`); manager-gestió
requests (`solicituds.py`); manager song-review requests
(`sollicituds_revisio.py`, the `reconsiderada` re-open flow).

---

## 6. Per-song editing

Same endpoint, `GET`/`PATCH /api/v1/staff/cancons/<pk>/` → `canco_detail`
(`web/api/staff/cancons.py:350`). The React form is `web-react/src/pages/
staff/` (the cançons workbench). Editable fields (PATCH whitelist):
`nom`, `isrc`, `lastfm_nom`, `verificada`, `activa`, `data_llancament`,
`deezer_id`, `artista_pk` (reassign main artist), `artistes_col_pks`
(replace collaborators), and **`spotify_url`** (manual Spotify id). Each
save calls `canco.save()` and logs `canco_edit`. Works on verified and
unverified tracks alike.

### Manual Spotify URL — now implemented (PR #139)

The earlier backlog item ("no Spotify field in the song edit form") is
**done**. `canco_detail` PATCH accepts **`spotify_url`**
(`web/api/staff/cancons.py:417`); the raw value is parsed through
`web/api/staff/_spotify_url.py::parse_track_id`, and the resulting id is
stored id-first then hydrated **without a `/v1/search` call** (PR #139,
*manual Spotify id with /search-free hydration*). The `_canco_row`
serializer surfaces the current `SpotifyMetadata` state with a `hydration`
field — `ok` (artist id resolved), `pending` (id saved, not yet hydrated),
or `failed` (hydration ran but couldn't resolve the id / bad URL). A manual
id behaves like a `found` row for playlist purposes; Process B hydrates the
remaining fields on its next tick.

---

## 7. Social / stories subsystem

Five-channel weekly distribution (Instagram, Mastodon, Bluesky, Telegram,
Newsletter) + RSS, all from one payload. Code in `social/`; full doc
`docs/architecture/social.md`.

What fires on a given day is no longer a fixed staggered cron alone — it is
gated at publish time by an **editable distribution matrix** plus a master
switch (`ranking/models.py::MatriuPublicacio`, gate in
`social/management/commands/publicar_canal.py:137`). Three gates run in
order: master `distribucio_activa` AND `<channel>_actiu`
(`ConfiguracioGlobal.pot_publicar`, PR #163), idempotency on the `SocialPost`
row, then `MatriuPublicacio.actiu_per(channel, tipus)` per cell (PR #180) —
an off cell marks the post `omès` instead of publishing.

- **Renderer** `social/renderer.py` — PIL/Pillow image builders, JPEG q90.
  The **PPCC story set is 7 editorial slides** via `render_stories_ppcc`
  (`social/renderer.py:2164`): intro → top 40→11 mosaic → top 10→4 grid →
  podi #3-2 → #1 hero (Playfair climax) → novetats (skipped when none) →
  yellow outro. Builders `_story_intro_ppcc`, `_story_top_mosaic`,
  `_story_top_grid`, `_story_podi`, `_story_hero`, `_story_novetats`,
  `_story_outro_ppcc`.
- **Covers** — `_story_cover` (`social/renderer.py:324`): local self-hosted
  portada (`ingesta.portades`, 250/500 px) → live Deezer CDN URL →
  placeholder. The cover is bound to the song's `Canco.album` (per-album, not
  per-artist), via `payload.build_top` (`social/payload.py:132-135`).
- **#1 hero headline** — `synthesize_hero(scenario)`
  (`social/narrative/story_synth.py:43`) returns a short uppercase Playfair
  line keyed by `scenario_code`, threaded from `publicar_social.
  _story_hero_headline` → `scenarios.detect_all("PPCC", …)` (strongest
  post-dedup scenario).
- **Publish pipeline** — `publicar_social` (Instagram) +
  `publicar_canal --channel <name>` (others). `_publish_story`
  (`social/management/commands/publicar_social.py:353`) renders → uploads
  each slide → publishes; idempotent per `SocialPost` row; dry-run safe.
- **Territorial story set (Step 3c) — done.** The territorial editorial story
  set shipped in **PR #146** (`render_stories_territorial`,
  `social/renderer.py`), recoloured per territory via
  `colors.story_palette(...)`. Step 3c is no longer a future item.
- **Manual outro link sticker** — the outro story's tap-through link must be
  added by hand each week in the Instagram app; the Graph API does not expose
  story stickers programmatically (documented in `social.md`).

---

## 8. Recent relevant PRs

| PR | One-liner |
|---|---|
| #21 (`b4a170c`) | Analytics: the social-publication counter derives from `SocialPost` (the canonical, idempotent source) instead of append-only `MetricaEsdeveniment` (Bug 1, Fase 3). |
| #123 (`6a41c57`) | Newsletter HTML rework — 9 blocks, album covers, trend cues, UTM tagging, dark-mode support. |
| #125 (`94cd994`) | Social Step 3b — rewrote the PPCC story set from 42 slides to 7 editorial slides ordered toward the #1 climax. |
| #127 (`ef41fea`) | Ported the validated Claude-Design canvas into the 7 Pillow builders; bundled 4 OFL fonts (Anton, Bricolage Grotesque, Instrument Serif, Playfair 800). |
| #128 (`75e4f52`) | Docs/nomenclature: relabel the PPCC redesign as **Step 3b**. |
| #129 (`5489ea3`) | PPCC story polish — dynamic grid row heights (2-line titles no longer crowd) + hard-omit the novetats slide when empty. |
| #131 (`021bf03`) | **Caducity guard** — `is_caducat` at every Canco-creation frontier; stops ancient re-scanned albums recreating pendents every ~30 days. Merged 2026-06-02 (closes the prior "deployed but uncommitted" drift). |
| #139 | **Manual Spotify id** in the song edit form (`spotify_url` PATCH) with /search-free hydration (see §6). |
| #141 (`aac3999`) | Exclude caducats from the `enriquir_spotify` pending pool (caducity-guard follow-up). |
| #146 | **Territorial editorial story set (Step 3c)** — `render_stories_territorial`, recoloured per territory (see §7). |
| #159 (`e597486`) | **Pendent gate** — a `Canco` now needs ≥1 *approved* artist to be reviewable; trimmed the pending queue (see §9). |
| #176 | Brief: additive top-40 expansion for `build_brief`. |
| #177 | Newsletter: link + emphasise artist/song names (Slice 1). |
| #178 | Staff/social: per-platform engagement summary on the publications table. |
| #182 | **Catalog-wide Spotify enrichment-coverage KPI** on the `estat` endpoint (`coverage_total/_public/_pending`, `web/api/staff/estat.py`). |
| #187 | Newsletter: `editorial_veu` prompt on `ConfiguracioGlobal` (`ranking/models.py:245`), served in the brief. |
| #163 / #180 | Distribution: real master switch + honest per-channel view (#163); editable canal×tipus matrix gate (#180). See §7. |

---

## 9. Known gaps & debt

### `data_llancament IS NULL` escapes the caducity sweep (confirmed)

`netejar_caducades` filters `verificada=False, activa=True,
data_llancament__lt=cutoff` (`ingesta/management/commands/
netejar_caducades.py:33-35`). In SQL `NULL < cutoff` is never true, so
**unverified tracks with a NULL release date are never purged** and can
accumulate in the staff queue indefinitely. The creation guard agrees
(`is_caducat` returns False for NULL, by design — `ingesta/caducitat.py:54`),
and that module's own docstring (31-35) flags the NULL hole as "a separate,
known follow-up — not addressed here." Production right now: **0** such rows,
so latent, not active.

### `netejar_caducades` is a once-daily sweep vs. hourly ingest churn

The purge runs once at 04:00, but P2 album re-scans can *rewind* an existing
track's `data_llancament` to an older true value after it was created
(`obtenir_novetats.py:367-372, 522-525`), creating fresh caducity candidates
through the day. Observed 2026-06-02: the 04:30 run deleted 0; by midday
`netejar_caducades --dry-run` reported **225** to delete. Sawtooth, not a
bug — but old-dated tracks are briefly verifiable by staff before the next
sweep.

### Git/prod alignment — resolved

The earlier "caducity guard deployed but uncommitted (prod ahead of GitHub)"
debt is **closed**. `ingesta/caducitat.py`, its test, and the
`obtenir_novetats.py` guard edits were committed via **PR #131** (`021bf03`)
with the enrich-pool follow-up **PR #141** (`aac3999`); both are ancestors of
`origin/main`. As of 2026-06-09 production `HEAD == origin/main == 56a43f4`
with a clean working tree — no drift. The hourly `tq-health` git-drift check
(`CLAUDE.md` §11) guards against a recurrence.

### Other tracked debt

- **`Canco.album` FK hygiene** — covers + territory derivation trust
  `canco.album`; a mis-linked album silently mis-renders/mis-territories the
  track. No automated audit.
- **Name normalisation** — Deezer titles are stored verbatim (e.g. "Nexo
  10.bona Nit"); `retitlecase` (`music/management/commands/`) is manual.
- **Novetats slide format for 1–2 items** — slide 6 currently centres a
  single cover and looks sparse with one novetat; the multi-count layout is
  deferred pending several weeks of data (noted with PR #129).
- **Last.fm rejection-filter scope** — `_previously_rejected` matches by ISRC
  **or** deezer_id; a re-issue that changes *both* keys can slip past the
  dedup until staff reject it again.
- **`collectstatic` not in the deploy path** — `bin/tq-deploy` runs migrate +
  `npm run build` + reload; Django `collectstatic` is not part of it (the SPA
  serves its own assets; Django static is auth/SEO-only), so new Django
  static must be handled out-of-band.
- **Low-yield narrative detectors n3/n4** — the collaboration / shared-label
  novetats detectors fire rarely (guest names aren't stored); generic copy
  only (`docs/architecture/social.md`).

### Diagnostic: why does "per verificar" look tiny?

**Production is healthy — this is not an ingestion failure.** As of
2026-06-09 the live pending queue (`Canco.objects.pendents()`,
`verificada=False, activa=True`, `web/api/staff/dashboard.py:91`) is:

- **341 total** (was 784 on 2026-06-02). By ML class: **C = 325, B = 16,
  A = 0**. By main-artist territory: **CAT 234, VAL 44, BAL 23**, plus **40**
  with no approved main artist (no territory).
- **The drop is mostly definitional, not a stall.** **PR #159** now requires
  a pending `Canco` to have ≥1 *approved* artist to be reviewable, which is
  why the "no approved artist" bucket fell from 235 → 40; the caducity guard
  (#131) and the recurring orphan sweep (#161) further trimmed churn.
- Rejections stay brisk: **15 608** `HistorialRevisio` rows total. Latent NULL
  hole is quiet: **0** unverified tracks with `data_llancament IS NULL`.

So a surface that reads "**per verificar 1**" is the **filter/scope**, not a
broken pipeline: `cancons_list` supports `ml_classe`, `whisper`, `mb`,
`recent`, `q`, `artista_pk` filters (`cancons.py:166-262`), and an optional/
aggregate territory (AND/CNO/ALT/PPCC) currently has ~0 pending — any of these
easily yields 1. A genuinely empty surface in a fresh checkout is a local/dev
DB, not production.

### Spotify enrichment coverage

A catalog-wide coverage KPI is exposed on the `estat` endpoint
(`web/api/staff/estat.py::_spotify_enrichment_stats`, PR #182):
`coverage_total`, `coverage_public`, `coverage_pending`. As of 2026-06-09,
enriched (`found`+`manual`) over the active+verified+ISRC pool is **≈60.3 %
(2 088 / 3 463)**; the remaining ~1.3 k are `not_attempted`, drained nightly
by `enriquir_spotify` (Process B, §3).

---

## 10. Community subsystem

A logged-in-user community lives in the `comptes` app + `web/api/comunitat_views/`
+ React `web-react/src/pages/` (full model reference: `docs/architecture/comptes.md`).

- **Registration** — `Usuari` (`comptes/models.py:18`) + `PerfilUsuari`
  (`:263`, auto-created on signup). `POST /api/v1/auth/register/` sends a
  token activation email; RGPD consent + `vol_newsletter` captured at signup.
  SPA: `AuthPage.jsx`.
- **Direct messages** — `Missatge` (`comptes/models.py:443`), 1-to-1, no
  threading. `GET /api/v1/missatges/`, `POST /missatges/nou/`,
  `GET /missatges/amb/<pk>/` (`web/api/comunitat_views/missatgeria.py`,
  send-throttled). SPA: `MissatgesPage.jsx`.
- **Directory / user search** — `PerfilUsuari.visible_directori`.
  `GET /api/v1/comunitat/directori/` (`perfil.py`) — search by
  name/instrument/bio + filters; **staff see all profiles** (incl.
  `visible_directori=False`) for moderation reach. SPA:
  `ComunitatDirectoriPage.jsx`.
- **Artist accounts** — `UserArtista` (`comptes/models.py:32`, claim/manage an
  existing artist: `estat ∈ {pendent,aprovat,rebutjat}`, `verificat`, audit
  fields) and `PropostaArtista` (`:103`, propose a *new* artist). User
  endpoints `/compte/{propostes,solicituds}/` + `/compte/artista/<pk>/editar/`
  (verified managers self-edit); staff `/staff/{propostes,solicituds}/`. SPA:
  `ProposarArtistaPage.jsx`, `SolicitarGestioPage.jsx`, staff queues.
- **Public feed** — `Publicacio` (`comptes/models.py:371`,
  `visibilitat ∈ {interna,publica}` × `estat ∈ {esborrany,pendent,publicat,
  rebutjat}`) + `Comentari` (`:479`). Authenticated CRUD at
  `/api/v1/comunitat/publicacions/`; **anonymous** read at
  `/api/v1/comunitat/publicacions-publiques/` (`web/api/urls.py:700`). Staff
  moderation `/staff/publicacions/` + `/decidir/`. A regular user choosing
  `publica` lands in `pendent` (staff approval); `interna` publishes directly.
  SPA: `ComunitatPage.jsx`, public `ComunitatPublicaPage.jsx`, editor
  `ComunitatPublicarPage.jsx`, staff `StaffPublicacionsPage.jsx`.
- **Admin pseudo-user + DM relay** — a seed `Usuari(username="admin")`
  (`ADMIN_INBOX_USERNAME`, `topquaranta/settings/base.py:99`; seeded by
  migration `comptes/migrations/0016_admin_pseudouser.py`) fronts a community
  inbox. Any user can DM it; the notification helper fans the alert out by
  email to every `is_staff` user (the pseudo-user's own opt-out is ignored on
  that branch). Replies use the real staff user as `remitent`.

### Known gap: no Newsletter → Publicacio bridge

The weekly newsletter and the public feed are **separate systems**. The
newsletter is email-only: `NewsletterDraft` (`comptes/models.py:608`,
`subject` + `narrative_html` + `estat`) has **no FK to `Publicacio`**, and no
endpoint or staff action turns a draft into a public post. Surfacing the
newsletter on `/comunitat/public` would only need a small bridge (a link/FK +
a "publish as community post" action) — **the destination already exists**
(`Publicacio` with `visibilitat=publica, estat=publicat`), the wiring does not.

---

## See also

- `docs/architecture/music.md` · `pipeline.md` · `staff.md` ·
  `social.md` · `playlists.md` · `algorithm.md` · `comptes.md` · `web.md`
- `docs/decisions/` (ADRs — esp. 0012/0013 Spotify split) ·
  `docs/ops/runbook.md` · `docs/history/roadmap.md`
- `CLAUDE.md` (canonical project memory) · `deploy/cron.topquaranta`
