# CLAUDE.md — TopQuaranta

> Persistent memory for Claude Code. Read this file first on every session.
> Last updated: 2026-05-04 — May-2026 audit sprint applied across
> security, performance, code quality and architecture:
>
> **Security**: cookies SECURE flag + HSTS, Django 5.2.13 (3 CVE
> patches), Dependabot security alerts enabled, PII removed from
> auth logs (`user.pk` instead of `user.email`), ConfiguracioGlobal
> endpoint masks fields matching `_token|_secret|_password|_key|
> _apikey`, `upload_imatge` validates Pillow's `img.format` not
> just the spoofable `content_type`, ScopedRateThrottle on
> `auth_login` (5/min), `data_export` (3/h), `newsletter_unsubscribe`
> (10/min), Postgres role `topquaranta` lost CREATEDB.
>
> **Privacy/RGPD**: `exportar-dades` now includes `StaffAuditLog`
> entries targeting the user + axes login history; newsletter
> unsubscribe token expires after 1 year (was permanent — leaked
> archived emails were a forever-unsubscribe primitive).
>
> **Ops**: shared `"ram_heavy"` SingletonLock between
> `analitzar_whisper` and `obtenir_metadata_musicbrainz` (closes
> the 4 GB CX22 OOM); `WHISPER_MODEL` env-configurable;
> `logrotate` globs `*.log` and prunes social PNG renders >60d.
> Cron tuning (2026-05-05): MB `--limit 200→100` (caps duration
> ≤17 min instead of occasional 5 h); Whisper `--limit 100→200`
> and slot moved 05:00→04:00 UTC so it's clear of the 04:30 MB
> tick. Resolves a recurring `SKIPPED_BY_LOCK` on Whisper when
> a long MB run held `ram_heavy.lock`. New `--max-p3-per-run 200`
> on `obtenir_novetats` prevents thundering-herd re-checks after
> a backfill (see commit 8200cc7).
>
> **Performance**: SPA staff routes lazy-loaded — anon bundle
> 1.205→1.030 KB (-15%); `cache_for_anon` TTL 60s→300s on
> `/ranking`, `/mapa`, `/albums-list`, `/home-stats`; new
> `Canco.objects.public()` and `.pendents()` manager methods to
> stop repeating `verificada=True, activa=True`; index
> `UserArtista (usuari, -created_at)`; dropped redundant standalone
> indexes on `SocialPost.platform/.tipus`.
>
> **Architecture**: `ingesta/social/*` moved to `social/*` (channel
> clients + renderer + payload + captions belong with publishing,
> not ingestion); `web/api/views.py` renamed to `mapa_views.py`
> for symmetry; `Album.cancons_obtingudes` purged from writes.

## Other docs

Every doc lives under `docs/` organised by audience. Quick map:

- **`docs/EMAIL.md`** — Stalwart + Brevo/Resend smarthost architecture.
- **`docs/architecture/`** — `algorithm.md`, `analytics.md`,
  `api-versioning.md`, `brand-logo.md` (read this BEFORE touching
  anything that loads the brand SVG — three traps documented),
  `comptes.md`, `models.md`, `pipeline.md`, `seo.md`, `social.md`,
  `staff.md`. Reference for the codebase.
- **`docs/policies/`** — `conventions.md`, `docs-maintenance.md`,
  `identities.md`, `post-mortems.md`, `sprint-process.md`. Rules.
- **`docs/decisions/`** — ADRs (Architecture Decision Records).
- **`docs/post-mortems/`** — incident write-ups.
- **`docs/product/`** — `definition.md` (què compta com a música en català).
- **`docs/ops/`** — `runbook.md`, `retention.md`, `deprecation.md`,
  `ssh-keys.md`, `backup-offsite.md` (capa 2 implementada GATED —
  restic→B2 append-only, esperant activació del Miquel; procediment §9).
  Things you read when something breaks or has to be decommissioned.
- **`docs/history/`** — `roadmap.md` (estat + sprints), `changelog.md`.

Also at the repo root:
- `MANIFEST.md` — mission, no-goals, values.
- `LICENSE-DATA.md` — CC BY 4.0 on the dataset.

---

## 1. Project

TopQuaranta (`topquaranta.cat`) is a weekly music ranking for Catalan-language
music across 10 territories: `CAT`, `VAL`, `BAL`, `PPCC` (aggregate), `ALT`,
`CNO`, `AND`, `FRA`, `ALG`, `CAR`. Cultural mission: show that Catalan-language
music is alive and growing.

- **Signal source:** Last.fm (`playcount` + `listeners`, normalized via
  `percentileofscore`).
- **Metadata source:** Deezer (public API, ISRC on every track).
- **Playlist output:** Spotify (daily sync via OAuth refresh token; cron
  07:15 UTC). Also "Escolta-ho a" universal search links on every content
  page as a no-API fallback (Spotify ISRC deep-link + Deezer direct +
  YouTube Music + Apple Music search URLs).

## 2. Architecture

Post Sprint-4 (April 2026), the public website and the staff panel moved
from Django-rendered templates to a React SPA living at `web-react/`.
Django now owns only the API, a handful of auth flows and SEO:

```
                        ┌──────────── Caddy (TLS + routing) ────────────┐
                        │                                                │
  /api/v1/*             │                                                │
  /compte/{2fa/*, login, │                                               │
    logout, registre,    │─▶  Django · gunicorn :8083                    │
    activar/*}           │    (session + CSRF + axes + django-otp +     │
  /sitemap.xml           │     ConfiguracioGlobal)                       │
  /robots.txt           │                                                │
  /rss/*                │                                                │
                        │                                                │
  /static/*             │─▶  /home/topquaranta/app/staticfiles/          │
  /static/social/*      │─▶  /var/cache/topquaranta/social/renders/      │
                        │     (raw PNGs for IG media-fetcher)            │
                        │                                                │
  /beta/*               │─▶  301 → /                                     │
                        │                                                │
  everything else       │─▶  web-react/dist/ (SPA index.html fallback)   │
                        │                                                │
                        └────────────────────────────────────────────────┘
```

The SPA handles: `/`, `/top`, `/artistes`, `/artista/<slug>`, `/album/<slug>`,
`/canco/<slug>`, `/mapa`, `/compte`, `/compte/accedir`, `/compte/perfil`,
`/compte/artista/{proposta,gestio}`, `/staff`, `/staff/*`,
`/spotify/callback`. Client-side 404 is handled by React Router.

Django still renders: `registre.html`, `registre_ok.html`, `activar_error.html`,
`login.html`, `dos_fa_{configurar, verificar, gestio}.html`, plus the trio
of error pages (`403/404/500.html`) and `robots.txt`. Every auth template
extends a minimal self-contained `comptes/_base_auth.html` that mirrors
the SPA palette but has no dependency on mm-design.

## 3. Infrastructure

- **Server:** Hetzner CX22 (`188.245.60.20`), Ubuntu 22.04.
- **Runtime:** Python 3.12, Django 6.0.6, PostgreSQL 14. Node 22 + Vite 8
  for the SPA.
- **Reverse proxy:** Caddy (auto TLS). The shared box hosts TopQuaranta
  alongside other projects (e.g. cercol-api), so Caddy's config is
  multi-tenant:
  - `/etc/caddy/Caddyfile` — owned by TopQuaranta. Source of truth:
    `deploy/Caddyfile`. Synced by `tq-sync-infra`. The file ends with
    `import /etc/caddy/conf.d/*.caddy`, which pulls in per-project
    snippets.
  - `/etc/caddy/conf.d/*.caddy` — snippets owned by other repos
    deployed on the same server. TopQuaranta's tooling must never
    touch this directory; each project ships and reloads its own
    snippet independently. See `docs/ops/infra.md`.
- **Process:** `topquaranta-web.service` → gunicorn :8083, settings
  `topquaranta.settings.web_server`, user `topquaranta`. `ExecReload=HUP`
  so `systemctl reload topquaranta-web` swaps workers gracefully on deploy
  (no 502 window during code pushes).
- **Cron:** `/etc/cron.d/topquaranta` (source: `deploy/cron.topquaranta`).
  Redeploy with `sudo install -o root -g root -m 644
  deploy/cron.topquaranta /etc/cron.d/topquaranta` — cron auto-reloads.
- **Logrotate:** `/etc/logrotate.d/topquaranta` (source:
  `deploy/logrotate.topquaranta`).
- **DB:** `topquaranta` on localhost. 48 tables (18 domain + Django/axes/
  otp/session internals).
- **Working dir:** `/home/topquaranta/app/`. Virtualenv: `.venv/`.
- **Repo:** `github.com/Top-Quaranta/TopQuaranta` (private).

## 4. Project structure

Top-level layout. `ls -R` for the rest; the docs in `docs/` describe
each subsystem in detail.

```
app/
├── manage.py
├── topquaranta/   # Django settings (base · production · web_server · local · test)
├── music/         # core domain — Artista / Album / Canco / Territori / Municipi /
│                  # ArtistaLocalitat / HistorialRevisio / StaffAuditLog / Spotify*
├── ranking/       # algorithm v2.0 + ConfiguracioGlobal + Top* models
├── ingesta/       # Last.fm + Deezer + MusicBrainz + Spotify clients & commands
├── comptes/       # Usuari + auth flow + UserArtista + PropostaArtista + Feedback +
│                  # community models (PerfilUsuari · Publicacio · Comentari · Missatge)
├── web/           # Django API (`web/api/`) + SEO + error handlers
├── web-react/     # React SPA — public site + staff panel
├── social/        # 5-channel distribution clients (IG/Mastodon/Bluesky/Telegram/Newsletter) + renderer + payload + captions
├── analytics/     # Sprint K — pageviews, UTM, social metrics, GoAccess wrapper
├── scripts/       # non-command Python (analysis, archived migrations)
├── vendor/        # mm-design tokens (Django side)
├── deploy/        # Caddyfile · systemd · cron · logrotate
├── docs/          # see CLAUDE.md §"Other docs" above for the map
└── tests across each app under `*/tests/`
```

Operations scripts (outside the repo, in `/home/topquaranta/bin/`):
`tq-run`, `tq-recover`, `tq-health`, `tq-backup`. Backups land in
`/home/topquaranta/backups/{daily,weekly,monthly}/`.

## 5. Design system (mm-design)

Two consumers:

1. **React SPA** — `mm-design` is an npm git dep in `web-react/package.json`;
   tokens loaded in `main.jsx`. Colours exposed via Tailwind v4 `@theme`
   (`tq-yellow` `#facc15`, `tq-ink` `#0a0a0a`, `tq-yellow-deep` `#ca8a04`).
   Palette: **yellow headers on ink body**, accent on territory colours
   for the HomePage.
2. **Django auth templates** — `comptes/_base_auth.html` is self-contained.
   Inline CSS mirrors the SPA palette; no mm-design dependency.

`STATICFILES_DIRS` points to `vendor/mm-design/` for Django; the SPA uses
the npm version. After `npm update` in `web-react/`, run `npm run build`
to refresh the dist bundle that Caddy serves.

**Rules:**
1. Colors / fonts / spacing / shadows come from `var(--mm-*)` or Tailwind's
   `tq-*` tokens. Never hardcode hex values in templates or components.
2. Fonts: Playfair Display (headings), Roboto (body).
3. Territory accent: the canonical public mapping is the CSS custom
   properties `--color-terr-*` in `web-react/src/index.css`, mirrored
   in JS by `web-react/src/components/rd/terr.js::PAL` (consumed by the
   `rd/` primitives). Public-page labels use `TERRITORI_NOM` (visible) —
   note that "PPCC" is shown as **"Global"** to visitors but stays as the
   legacy code in DB and API query params. **Territory palette (Fase 1
   unified, 2026-06-23):** the single source is
   `web-react/src/components/rd/terr.js` — `PAL` (deep/accent pairs,
   mirrored by `index.css --color-terr-*`), plus `terrChart(code)` =
   the canonical **deep**, the one value every territory *chart* series
   uses. Both chart consumers read it: `CancoChart.jsx` (line stroke) and
   `StaffAnalyticsPage.jsx` (`<Cell fill>`). The earlier divergent copies
   (`editorial.jsx::TERR_COLORS` — removed PR A; the per-chart
   `TERR_COLORS`/`TERRITORI_COLORS` — removed PR B) are gone. Fase 2
   (promote the palette to `ConfiguracioGlobal` + a staff-editable API)
   is not done yet; it is all in code. See
   `docs/audits/2026-06-23-recon-disseny-unificacio.md`.

**Design layers (real state, 2026-06-23).** There is no single shared
primitive set across the SPA; public and staff run on separate systems
on top of the common `index.css` `@theme` tokens:

- **Public** → `components/rd/primitives.jsx` (`Band`, `Glass`, `Btn`,
  `Kicker`, `Crit`, `TerrLogo`, …) + the `.rd-*` CSS in `index.css`.
  This is the live public design system (the "redisseny", introduced
  2026-06-13); ~14 pages consume it.
- **Staff** → the **rd light canon**. The staff table/form kit lives at
  `components/rd/surface.jsx` (`TableCard`, `Table`, `Th`/`Td`/`Tr`,
  `Pill`, `Input`, `Select`, `Pagination`, `PageHeader`, `Field`,
  `Callout`, `EmptyState`, `Btn`); `TableCard` delegates to `Glass
  tone="light"` and `Btn` to the unified canon `Btn` (staff `primary`
  default preserved). The 36 staff pages import from `rd/surface` + use
  `components/StaffLayout.jsx`. Staff stays **white/data-dense** (option
  B: rd gained a light mode rather than staff going dark). The retrofit
  was **pixel-identical by construction** (the rd light variants mirror
  the old `StaffTable` byte-for-byte). `components/staff/StaffTable.jsx`
  is now a **back-compat shim** re-exporting `rd/surface` so public pages
  (`Field`/`Select`) and the shared `FilterPanel`/panels keep working.

- **`components/editorial.jsx` is LEGACY, pending retirement.** It was
  the original public primitive set (Sprint J bis: `Section`,
  `SectionHeader`, `TerritoriBadge`, `TrendCue`, `TERRITORI_NOM`) but the
  public pages migrated to `rd/primitives` in the 2026-06-13 redisseny.
  It is now stranded with only **2 importers** (`CancoChart.jsx`,
  `rd/terr.js`), both pulling only `TERRITORI_NOM`. (Its dead
  `TERR_COLORS` export was removed in PR A; `StaffAnalyticsPage.jsx` does
  **not** import editorial — it has its own local chart palette.) Do
  **not** build new UI on it; prefer `rd/primitives` (public) or `staff/*`
  (staff). Retirement is a tracked follow-up
  (`docs/audits/2026-06-23-auditoria-dry-modular.md` §2.2).

**A11y baseline** (Sprint F + J bis): WCAG AA across the public
SPA. Re-audited via puppeteer + axe-core on every redesign sprint
(`/tmp/axe/run.js`); see ROADMAP for the latest pass and the URL
list.

## 6. Key decisions

| Decision | Rationale |
|---|---|
| Last.fm as signal | Spotify popularity deprecated 2024-11. Last.fm exposes public playcount + listeners. |
| Deezer as metadata | Spotify API 403 since 2024 (Premium required for new apps). Deezer: public + 100% ISRC. |
| Algorithm ported, not rewritten | 14-CTE SQL from legacy views → Python in `ranking/algorisme.py`, same math. |
| PPCC aggregates, not computes | Takes top 40 of each non-aggregate territory, applies position penalty, dedupes by canco. |
| Territory on artist (M2M), not track | Legacy duplicated tracks per territory. Now auto-syncs from ArtistaLocalitat → Municipi → Territori. |
| Human approval for every auto-discovered artist | Prevents false positives (metal "Aion", anime "Animal"). |
| ISRC on every Canco | Universal key. Enables cross-DSP resolution (Spotify ISRC deep-links). |
| 12-month track cutoff | Current music only (`DIES_CADUCITAT` in `music/constants.py`). |
| No Celery | Daily/weekly cron is enough. |
| **React SPA** (Sprint 4, Apr 2026) | Shared brand across public + staff. Django becomes pure API backend. |
| Session cookie auth for SPA | Same `csrftoken`/`sessionid` as Django. Axes + django-otp work untouched. |
| **2FA via Django page** | Unverified staff session is bounced full-page from `AdminRoute` to `/compte/2fa/verificar` (Django form); on success same cookie is OTP-flagged and IsStaff API checks pass. |
| **ML slim** (2026-04-21) | 223 → 76 → **79** features (2026-04-22 added MB signals). Bayesian smoothing on rejection ratios. 5-fold CV ROC-AUC 0.9994. |
| **Spotify as playlist output** | One-time OAuth → long-lived refresh_token → daily sync cron. Premium needed on the app owner, free for listeners. Catalog reads via Client Credentials also require app-owner Premium (policy change late 2024) — we don't rely on them. |
| **Invariant: aprovat ⇒ Deezer ID OR MBID** | Enforced by `post_delete` signal on ArtistaDeezer (2026-04-21; relaxed 2026-04-22). An artist needs ≥1 external anchor. Motivation: Crim-style collisions where two PPCC artists share a Deezer ID — one keeps Deezer, the other lives off MusicBrainz. |
| **MusicBrainz as disambiguation oracle** (2026-04-22) | Deezer stays primary (discovery + previews + scale). MB adds an always-on cron every 15 min (`obtenir_metadata_musicbrainz`) that pulls MBID + area + begin/end dates + URL relations + aliases + tags + full discography (release-groups/recordings/ISRCs/Work language). Reconciles Albums/Cançons via ISRC then normalised title fuzzy. Feeds 3 ML features (`mbrainz_confirmed`, `mb_lyrics_cat`, `artista_te_mbid`). Staff pins MBID manually on collision cases. |
| **MB auto-match — name + location, ignore Lucene score** (2026-04-29) | `resolve_mbid()` rewritten after the "Casual" bug (US rapper at score 100 vs CAT band at score 91 — old logic auto-picked the rapper). MB's Lucene score is a search-relevance metric biased toward well-edited mainstream artists; for PPCC music it's actively misleading. New rules: exact-name match + score ≥ 50 (loose floor); then if `Artista` has PPCC `localitats`, keep MB candidates whose `area` is PPCC and require exactly one match. No localitats → refuse auto-match. Empty area on candidates → refuse (can't verify honestly). Plus: `artista_detail` PATCH now auto-triggers `sync_from_mbid()` on MBID change so cançons don't carry orphan `mb_recording_id` from the previous wrong MBID. New audit command `auditar_mb_orphans` cleans up legacy residue. |
| **MB defence-in-depth at the cron** (2026-04-29) | The `obtenir_metadata_musicbrainz` cron now validates each artista's existing MBID against PPCC localitats every iteration via `validate_artista_area()`. On mismatch (MB says non-PPCC, our localitats say PPCC): auto-unassign + add to `mb_blocked_mbids` + reset stale `mb_*` fields on Cançons/Albums + audit-log (`artista_mbid_auto_unassign`). The cron then re-attempts `resolve_mbid()` in the same iteration with the new strict rules. This sweeps drift accumulated by the pre-2026-04-29 score-based resolver across the whole DB without a one-shot migration. |
| **Last.fm aliases sum signal** (2026-05-01) | `ArtistaLastfmAlias(artista, nom, confirmat, rebutjat, …)` — staff-curated variant names that `obtenir_senyal` sums into the canonical track playcount via `get_track_info_literal(canonical_artist=…)` (autocorrect=0 + URL guard against Last.fm's silent case-fold collapse). Detector `detectar_lastfm_aliases` proposes candidates with top-tracks ≥50 % overlap; staff confirms via `LastfmAliasesCard` at `/staff/artistes/<pk>`. Confirming an alias auto-absorbs any pendent at the same name with no Cançons/Deezer/territoris/collabs (saves manual cleanup). Caught from the user's «Delên» case; 35 of 1958 approved artists affected, worst losing 87-99 % of plays (Boira, Sabor de Gràcia). |
| **Last.fm similars row-per-edge** (2026-05-01) | `ArtistaLastfmSimilar(source, target, last_seen, match)` UNIQUE(source, target). The integer `Artista.nb_similars_lastfm` becomes a recomputed cache (`COUNT(*) WHERE target=…`). Cron resolves variant names through `ArtistaLastfmAlias` (alias-of-approved beats stale-pendent), dedups within a source, and replaces wholesale per source (idempotent re-run). Caught simultaneously with the alias work — same artist appearing twice in a source's similars under different spellings was double-counting. |
| **`tq-health` watchdog + lock-skip detection** (2026-05-01) | `obtenir_novetats` had been hung for ~12 days while every hourly tick reported `status=OK` because the lock-skip path exited 0. New `music.locks.SingletonLock` exits 75 (EX_TEMPFAIL) on contention; `tq-run` writes `status=SKIPPED_BY_LOCK` without refreshing `last_run`. `tq-health` distinguishes `SKIP(N)` (under threshold, gray) from `STUCK(Nh, Nskips)` (red, alert). New cron line `15 * * * * tq-health --email-on-fail` mails admin@ via Django's `mail_admins` (Brevo SMTP) when overall != 0; silent when healthy. `silenced` flag in CRON_META for known-acceptable failures (e.g. `actualitzar_playlists_spotify` waiting for Spotify Premium re-OAuth). Panel `/staff/estat` cron table sorts by frequency + shows per-row concern threshold and worry text. |
| **Grup C community (2026-04)** | `PerfilUsuari`, `Publicacio`, `Comentari`, `Missatge` — directori, feed moderat, DM 1-to-1, comentaris. Missatge té notificació email amb opt-out. Self-delete via email confirmation. |
| **Mapa drill-down (2026-04-22)** | `/mapa` SVG dels PPCC amb 3 nivells (territori → comarca → municipi) i panell lateral amb KPIs + graella d'artistes ordenats per reproduccions. GeoJSON preprocessats (Douglas-Peucker 0.002°) a `web-react/public/geodata/` via `scripts/simplify_geodata.py`. |
| **Public read cache (2026-04-25)** | Hot read endpoints `/api/v1/{ranking,artistes,mapa/artistes-top}/` cached **60 s for anonymous hits** in `pagecache` (LocMem per worker). Authenticated requests bypass. Each endpoint also exposes ETag + Last-Modified via Django's `condition` decorator (rooted at `RankingProvisional.data_calcul`, `Artista.created_at`, `SenyalDiari.data` respectively) — re-fetching clients get a 304 in ~5 ms. Helper at `web/api/utils.py::cache_for_anon`. |
| **Multi-channel distribution (Sprint I bis, 2026-04-27)** | Same payload, five channels: **Instagram** (feed + stories), **Mastodon**, **Bluesky**, **Telegram** (full carousel via media-group, up to 10 photos), **Newsletter** (HTML email via Brevo to `PerfilUsuari.vol_newsletter=True`), **RSS** (`/rss/{top,novetats}.xml`, Atom 1.0). One command `publicar_canal --channel <name>` for the four non-IG channels; auth singletons `{Mastodon,Bluesky,Telegram}Auth`; staff endpoints `/staff/social/{name}/{,test/,clear/}`; toggles in `ConfiguracioGlobal.{instagram,mastodon,bluesky,telegram,newsletter,rss}_actiu`. Cron staggered: Sat IG 09:30 → Mastodon 09:40 → Bluesky 09:50 → Telegram 09:55 → Newsletter 10:00. Auto-tag artists on feed posts via `user_tags` Graph API. |
| **Renderer editorial redesign (2026-04-27)** | First-pass renderer was monochrome + dark + schematic. Rewrote 4 slide kinds + stories: SVG-rasterised brand logo (`vendor/mm-design/icons/brand/logo-topquaranta-rect.svg`) and territory icons (mm-design SVGs), `colors.terr_color()` mirroring SPA's `TERR_COLORS`, `colors.best_text_on()` for monochromatic logo over coloured pills, `ImageOps.fit` cover-fit (no black bars), pill-system using mm-design `--mm-radius-lg`. Caption uses project-week numbering (`music.dates.project_week_number`, anchor Sat 2026-04-25 = wk 34). Novetats window anchored to last publication of same tipus (no fixed 7-day rolling). Eliminated all "Països Catalans" references. |
| **Static social PNG hosting (2026-04-27)** | Meta's media fetcher rejected our Django view (CSP/COOP headers caused code 9004). Caddy now serves `/static/social/*` directly from `/var/cache/topquaranta/social/renders/` as plain files. Setting `SOCIAL_PUBLIC_BASE` in `web_server.py` switches the URL builder. The Django view at `/api/v1/social/render/` stays as fallback. |
| **Gunicorn `--reload` (REMOVED 2026-05-20)** | Vegeu `docs/decisions/0001-gunicorn-no-reload.md` (Accepted 2026-05-20). |
| **Mail infrastructure (Sprint I bis, 2026-04-27)** | **Stalwart Mail Server** v0.16.1 on the Hetzner box for inbound + IMAP for `topquaranta.cat` and `cercol.team`. **Outbound via smarthost routing** in Stalwart's MTA strategy: `sender_domain == 'cercol.team' ? 'resend-relay' : 'brevo-relay'`. Brevo (free tier 300/day) for TopQuaranta, Resend for Cercol. Hetzner blocks port 25 outbound, hence smarthosts. TLS cert Let's Encrypt: Caddy obtains it for `mail.topquaranta.cat`; a systemd `path` unit (`stalwart-cert-sync.path` + `.service`) syncs the cert into `/etc/stalwart/certs/` on rotation. **BIMI** TXT at `default._bimi.topquaranta.cat` + Tiny PS SVG at `https://www.topquaranta.cat/static/brand/bimi.svg` (no VMC). **Mozilla autoconfig** at `mail.topquaranta.cat/.well-known/autoconfig/...` so clients self-configure. Full architecture at `docs/EMAIL.md`. |
| **Hetzner Cloud + CDMON DNS APIs (2026-04-27)** | `HETZNER_API_TOKEN` in `.env` + `hcloud` CLI installed; we manage firewall rules via API (e.g. opening 25/465/587/993 was scripted). `CDMON_API_KEY` in `.env`; `dns-backup/cdmon_clean.py` script for batch DNS ops (used to drop 18 legacy CDMON-Micropla records). API endpoint: `https://api-domains.cdmon.services/api-domains/`, header `apikey:`. Caveat: `dnsrecords/create` rejects A apex with bogus error "Destination to redirect not valid"; that one record needs the web panel. |
| **Ingest robustness pass (2026-05-03)** | Three fixes after the APECAT cross-check turned up holes in the pipeline. (a) **D5 self-collab guard**: `_create_track` and `_upsert_track` now compare a Deezer contributor against `set(artista.deezer_ids.values_list("deezer_id", flat=True))` instead of just `deezer_id_principal`. Without this, an artista with multiple Deezer profiles (autoedit + label) crashed signal D5 every hour for ~12 h. (b) **ISRC collision skip**: `obtenir_metadata` now catches `IntegrityError` on `canco_isrc_unique_when_set` and skips the duplicate row instead of aborting the artista's transaction (single-on-LP and featuring-on-both-profiles cases). (c) **Multi-Deezer-ID iteration**: `_fetch_for_artist` loops every `ArtistaDeezer` row of an artista, principal first, so label-secondary catalogues no longer hide. |
| **`obtenir_novetats` P2 cooldown (2026-05-03)** | The legacy P2 used `cancons_obtingudes=False` as a gate and marked an album done as soon as Deezer returned *any* track list (or when the album was >30 days old) — leaving ~3.7 k phantom albums "OK" with zero tracks because Deezer flake at the wrong moment masqueraded as "no tracks". New design: every non-discarded album with a `deezer_id` is re-checked on a per-album cooldown via the new `Album.last_album_check` (DateTimeField, indexed). Cadence: <30 d since release → 24 h, 30-365 d → 7 d, >365 d or unknown → 30 d. NULL = never checked → highest priority. `descartat=True` is the only permanent exclusion. Idempotence preserved by `_create_track`'s deezer_id + ISRC dedup. Migration `music 0060`. `cancons_obtingudes` was kept as a deprecated read-only field at the time, then removed entirely in migration `music 0069`. |
| **Multi-channel social parity (2026-05-03)** | Bluesky + Mastodon now publish a 4-image carousel (portada + first 3 list slides via `embed.images` / `media_ids[]`, both networks cap at 4) instead of cover-only. Each `_publish_*` returns `(ext_id, extra_meta)`; for Telegram `extra_meta.message_ids` captures every message in the media-group so the new platform-aware delete (`/staff/social/eliminar-remot/`) can remove them all (Telegram has no group-level delete). Real remote delete added for every channel: `mastodon_client.delete_status`, `bluesky_client.delete_post` (parses AT URI → `com.atproto.repo.deleteRecord`), `telegram_client.delete_messages`. Staff list reordered: Data column first, Setmana N second; per-platform row tints; "Esborrar" label is platform-aware. |
| **Renderer readability v3 (2026-05-03)** | Posts list slide: position number 38 → 54 pt, song title 28 → 40 pt; pill width and row height *unchanged* (76 / 105) so the page indicator (`1/4` etc.) stays clear of the last card. Tighter top padding (y+0) inside each cell does the visual work. Posts portada: logo + Setmana pills shifted from x=30 → x=84 (+54 px = 5 % FEED_W), keeping the left-aligned stack but with more breathing room — applied to both `_feed_portada` and `_feed_novetats_portada`. Story canço: title 44 → 80 pt (line-height 90), artist 34 → 44 pt; new "topquaranta.cat" footer at `STORY_H-90` in `COLOR_TEXT_MUTED` (4.5:1 on ink → AA). |
| **Newsletter opt-in on profile (2026-05-03)** | `vol_newsletter` now editable from `/compte/perfil` (was previously settable only at registration). Backend: `compte_views.perfil` GET exposes the flag, PATCH accepts it, and on a False→True transition stamps `consent_newsletter_at` for RGPD audit. Frontend: new section between username and password with a checkbox + helper copy. Only PATCHes when the value actually changed. |
| **Staff sees private profiles in community directori (Fase 1.5.B parcial, 2026-05-17)** | The `/api/v1/comunitat/directori/` listing is bifurcated by `request.user.is_staff`: staff get every active `PerfilUsuari` (regardless of `visible_directori`); non-staff keep the existing `visible_directori=True` gate. Each row in the payload carries `visible_directori` so the SPA can flag non-public rows visibly in the staff view. Purpose: let admins reach users for one-on-one moderation correspondence without forcing them to self-publish. Note: the DM endpoint `missatge_crear` was already permissive (raw `User.objects.get`), so no change was needed there — discoverability is the effective gate. Partial because the broader Fase 1.5.B item (a user→admin contact channel; "contact us" surface) is still being scoped and is NOT in this slice. |
| **Admin pseudo-user + DM relay (Fase 1.5.B, 2026-05-18)** | A seed `Usuari(username="admin", email="admin@topquaranta.cat", is_staff=False)` fronts a community inbox. Settings: `ADMIN_INBOX_USERNAME = "admin"`. Any logged-in user can DM this account (it shows up in the directori) and the `_enviar_notificacio_missatge` helper fans the alert out by email to every active `is_staff=True` user plus the `admin@` mailbox itself. The pseudo-user's own `notificar_missatges_email` opt-out is ignored on the fan-out branch — the staff alert is the whole point. Staff replies use the staff user as `remitent` (the existing flow already does this; no change needed). Seeded by migration `comptes.0016_admin_pseudouser` (idempotent: looked up by email; reverse deletes the row). |
| **Social counter source = SocialPost (Bug 1 Fase 3, 2026-05-18)** | `analytics_summary.social[]` ara deriva de `SocialPost.objects.filter(status=publicat, setmana__gte=...).values("platform","tipus").annotate(total=Count("id"))` en lloc de `MetricaEsdeveniment(clau="social_publicat")`. SocialPost és la font canònica idempotent (una fila per slot, status=publicat només quan realment ha sortit). `MetricaEsdeveniment` és append-only i depenia de cada call site recordar invocar `register()` — això va causar (a) publicacions pre-wire del register() invisibles i (b) story-sets over-comptats (resolt al PR #31). `MetricaEsdeveniment` manté el rol per a esdeveniments sense entitat pròpia (clicks UTM, page views, feedback creat). El filter és per `setmana__gte=since_week` (Monday of since-date) perquè `setmana` és el camp natural d'agrupació, no `published_at`. |
| **Narrative engine for weekly social posts (Fase 4 PR 1, 2026-05-18; wired since)** | `social/narrative/` package — **wired into `captions.py::compose_for_channel`** for tipus `top_ppcc` / `top_territorial`. Expanded to **13 detectors** (a1-a13 + fallback) over `TopSetmanal`. Anti-repeat registry backed by `social.NarrativePhraseUsage`. Per-channel composers apply mention style (IG `@handle` on legacy path only — narrative path regressed, vegeu `docs/post-mortems/2026-05-20-narrative-engine-collapsed.md`) and length budgets. Full architecture at `docs/architecture/social.md`. |
| **SocialTab quick wins: KPI delta + Newsletter audience + Omès visibility (Fase 3 problems 3/4/6, 2026-05-18)** | Tres millores discretes a `StaffAnalyticsPage.jsx::SocialTab` sense reorganitzar-la estructuralment: (3) `<Kpi>` del strip de seguidors rep `delta` calculat al frontend des de `followers_series` (punt ~7 dies enrere); (4) `analytics_summary` exposa `newsletter_audience` (`PerfilUsuari.vol_newsletter=True, usuari__is_active=True`) i la SocialTab afegeix una entrada Newsletter al strip; (6) `analytics_summary` exposa `social_omes[]` (mateixa shape que `social[]` però `status=OMES`), i la SocialTab afegeix una card "Publicacions omeses" amb count per canal en pills. Decisió de separar la card omeses en lloc de stacked-bar al chart existent: evita barrejar el comptador d'èxit amb el de fallades. |
| **Story-set counts as 1 publication (Bug 2 Fase 3, 2026-05-18)** | `publicar_social._publish_story` cridava `_register_event("social_publicat", n=len(story_ids))`, inflant el comptador 42× per cada top-story-set i 5× per als territorials. Una publicació conceptual = un slot (mateix tractament que un carrusel feed amb N imatges). Fix d'una línia: `n=1`. Test al `test_publicar_social.py` que mock-eja renderer + instagram_client i captura les crides a `register()` per a verificar `n=1`. Bug 1 de la mateixa auditoria (doble font de veritat `MetricaEsdeveniment` vs `SocialPost`) NO és aquest PR. |
| **Deezer image sizing per slot (Fix 2, 2026-05-18)** | Tiny util `web-react/src/lib/img.js::deezerImg(url, size)` rewrites the `WxH` segment of stored Deezer CDN URLs at consumption time. `Album.imatge_url` is stored as the canonical 1000×1000 string (Deezer `cover_xl`); serving that to a 40×40 slot was the main LCP driver per PSI 2026-05-16 (≈4.2 MiB wasted per page). Slot → size table (2× retina baked in): ≤48 px → 120, ≤128 px → 250, ≤320 px → 500, social renderer (1080) keeps 1000. Deezer supports arbitrary `WxH` up to ~1400; 2000+ returns 403 (verified empirically). No model change, no migration. 14 `<img>` slots touched across HomePage / TopPage / ArtistaPage / AlbumPage / CancoPage / ArtistesPage / MapaPage / StaffAlbumsPage / AlbumEditPage. |
| **Staff workflow "Artistes sense Instagram" (Fase 2, 2026-05-18)** | New SPA route `/staff/artistes/sense-instagram` cloning the PendentsPage inline-edit pattern: rows of approved artistes without `instagram_url`, prioritised by historical top presence. Backend reuses the existing `/api/v1/staff/artistes/` endpoint with `?aprovat=1&instagram=no&include_n_top=1&sort=-n_top`. The `n_top` annotation (`Count("cancons__rankings", distinct=True)`) is opt-in via `?include_n_top=1` so the general list endpoint stays cheap. Each row has an inline `<Input>` for the URL + a "Cercar a Google" external link (Google site-restricted search, `site:instagram.com "{nom}"` works without IG login, unlike `instagram.com/explore/search/`) + a "Desa" button that PATCHes the existing endpoint. Optimistic remove on save (the row no longer matches the filter). Sidebar entry under "Catàleg". No new endpoint, no new model field. |
| **Definitive moderation-mail content + retroactive notifier (Fase 1.5.C, 2026-05-18)** | The six Fase 1.5.A placeholder templates are replaced by content. The single `email_user_solicitud_resolta.html` (if/else by `accio`) is split into two files: `email_user_solicitud_aprovada.html` (full walkthrough: editable fields, comunitat capabilities, DMs, Admin TopQuaranta inbox, 2 FAQs on the 365-day window + Deezer source) and `email_user_solicitud_rebutjada.html` (motiu + invite to re-apply). Same split for `proposta_*`. `feedback_resolt` keeps its existing structure with friendlier copy. Admin templates stay minimal. New `UserArtista.email_aprovacio_at` (migration `comptes.0017_userartista_email_aprovacio_at`) stamps the "verified" email at send-time; the new management command `notificar_gestors_retroactiu` (with `--dry-run` and `--exclude-user-id`) is idempotent and uses this stamp to skip already-notified rows. |
| **Notification layer + UserArtista audit fields (Fase 1.5.A, 2026-05-17)** | Central transactional-email module at `comptes/notifications.py` with six paired entry points: `notify_admins_{nova_solicitud_gestio,nova_proposta,nou_feedback}` fire on user submit; `notify_user_{solicitud,proposta}_resolta(accio)` + `notify_user_feedback_resolt` fire on staff resolution. All best-effort: a mail-server hiccup logs and never blocks the business write. Six placeholder templates extending `email_base.html`; Fase 1.5.C will fill in the walkthrough + FAQ content. `UserArtista` gained `aprovat_at` (DateTime, null OK), `aprovat_per` (FK→Usuari, SET_NULL), `motiu_rebuig` (Text) — backfilled from `StaffAuditLog` rows when present. Two latent bugs fixed: `_gestor_check` now requires `verificat=True AND estat='aprovat'` (was just `verificat`); `solicitud_rebutjar` now flips `verificat=False` (was leaking auth on previously-approved-then-rejected users). |
| **Captions per-channel labeling (Fase 1, 2026-05-16)** | `social/captions.py` exposes two modes via a single helper `_artist_label(entry, *, use_handle)`. **Long mode** (`caption_top`, `caption_novetats`) → Instagram only via `publicar_social`; emits `@instagram_handle` so the post autolinks and notifies the artist. **Short mode** (`caption_short`) → Mastodon, Bluesky, Telegram, Newsletter via `publicar_canal`; emits the plain artist name. Reason: only Instagram autolinks an `@handle`; on the other networks mention syntax differs (`@user@instance`, `@user.bsky.social`, etc.) and we don't store per-network handles, so the IG-style `@handle` showed up as broken literal text. We did NOT add per-network handle fields on `Artista` — too thin coverage (instagram_url at 8.2% of approved already). |

## 7. Shared constants

Import from `music/constants.py`:
- `DIES_CADUCITAT = 365`, `MAX_POSICIONS_TOP = 40`
- `TERRITORI_NOMS` (dict), `TERRITORIS_VALIDS` (tuple of ranking-eligible codes)
- `ML_CLASSE_A_THRESHOLD`, `ML_CLASSE_B_THRESHOLD`, `MIN_TRAINING_SAMPLES`,
  `MIN_NEW_DECISIONS`
- `DEEZER_RATE_LIMIT`, `LASTFM_RATE_LIMIT`, `MAX_API_RETRIES`
- `MOTIUS_REBUIG` — 3 action-based reject codes: `desvincular_canco`,
  `desvincular_album`, `desvincular_artista`. Renamed 2026-05-25 from
  cause-based codes; semantics in `docs/architecture/staff.md §5`.

## 8. Environment (.env)

```dotenv
DJANGO_SECRET_KEY=
DJANGO_SETTINGS_MODULE=topquaranta.settings.production
ALLOWED_HOSTS=topquaranta.cat,www.topquaranta.cat
DEBUG=False
DATABASE_URL=postgres://topquaranta:PASSWORD@localhost:5432/topquaranta
LASTFM_API_KEY=
LASTFM_API_SECRET=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=https://www.topquaranta.cat/spotify/callback
```

Loaded via `python-decouple`. Always access via `from django.conf import settings`.

## 9. Testing

```ini
# pytest.ini
DJANGO_SETTINGS_MODULE = topquaranta.settings.test
python_files = tests/test_*.py
```

Mock all external HTTP — no real API calls. Current suite: **1481 passed, 10 skipped** (July 2026, CI on main 98e1d00).
Run: `.venv/bin/python -m pytest -q`.

`pytest.ini` pins `addopts = --ds=topquaranta.settings.test`, so env-var
overrides can't silently flip pytest to production settings. Vegeu
`docs/decisions/0003-pytest-ds-pin.md`.

React SPA: Vitest not yet wired for runtime tests; builds validated via
`npm run build` in CI-style deploys.

## 10. Code conventions

Canonical home: **`docs/policies/conventions.md`**. Summary
(authoritative source is the policy file):

- No `print()` → `logging` or `self.stdout.write()`.
- No `sys.exit()` → `raise CommandError(...)`.
- No `TRUNCATE` or raw DDL outside migrations.
- No raw psycopg2 — always Django ORM (exception: `ranking/algorisme.py`
  uses raw SQL for the 14-CTE).
- All DB writes inside `transaction.atomic()`.
- Type hints on new functions. `f-strings` in code, `%s` in `logger` calls.
- black + isort on Python. Comments and docstrings in English.
- Catalan for user-facing strings (React pages, Django templates, error
  messages). Technical English everywhere else.
- `# Spec: docs/<path>.md` backlink at the head of modules with a
  dedicated architecture doc (pre-commit hook validates the path).
- Captures shown in reports must be real or labelled `EXAMPLE`/`MOCK`.
- E2E smokes use the `qa_smoke` user + fixture artist, never real
  artistes.

See `docs/policies/conventions.md` for the rationale, examples, and
links to the post-mortems each rule traces back to.

### Docs gates (FASE 2, hard CI checks)

Three independent CI checks under `.github/workflows/ci-docs.yml`,
each its own job-id so branch protection can require them
individually. The canonical config they all read is
**`docs/policies/docs-map.yml`** (single source of truth for the
prefix-to-doc mapping, the exclude list and the size thresholds;
shared with the planned pre-commit hook).

- **`docs-coherence`** is a HARD gate: a PR that touches a mapped
  subsystem without updating its doc fails. Test files
  (`*/tests/*`, `test_*.py`, `*_test.py`, `conftest.py`), Django
  migrations (`*/migrations/*`) and dependency manifests/lockfiles
  (`package.json`, `package-lock.json`, `requirements*.txt` —
  2026-07-13, unblocks dependabot) are filtered out before
  resolution: they are implementation churn, not architecture, and
  do not trigger the gate.
- Override (excepcional): one line in the PR body, format
  `docs-reviewed: <doc-path> : <raó>`. CI verifies the doc exists
  on disk, is the doc the mapping resolved for the triggered
  subsystem, and the reason is non-empty. Accepted overrides add
  the `docs-review-skipped` label for audit.
- Update the doc when the change alters what the doc DESCRIBES
  (new endpoint, route, model, command, channel; changed data flow
  or contract; renamed concept; new invariant). Use the override
  only when you touch a mapped subsystem but the doc stays
  accurate (internal refactor, typo, log line, style edit). Full
  criteria + examples at `docs/policies/docs-maintenance.md`.
- **`docs-novelty`** is a HARD gate: a new top-level code
  directory (Django app or any directory with at least one `*.py`)
  must appear in `docs-map.yml` under `mapping:` (with its doc) or
  `exclude:` (with a `reason:`). New top-level Python work must
  make the docs decision explicit.
- **`docs-size`** is a HARD gate: docs under `size.scope`
  (`docs/architecture/`, `docs/ops/`) must respect
  `size.threshold_lines` (400). When a doc grows past the
  threshold, split it per `docs-maintenance.md` Rule 3 (split by
  sub-area, keep the original as an index) rather than
  compressing. Update every `# Spec:` backlink and the
  `docs-map.yml` entries that pointed at the old path.
- ML feature ordering: new features go at the **END** of
  `FEATURE_NAMES` in `music/ml.py`, never in the middle. Required
  by the load-time alignment check (`music/ml.py::_get_clf`) that
  blocks a model trained on N features from being served once
  `FEATURE_NAMES` has N+1. See the 2026-05-23 incident postmortem
  in `docs/ops/runbook.md` and ADR-equivalent comments inside
  `music/ml.py`.

## 11. Workflow

Edits happen **locally on the Mac** (via Claude Code in the worktree, or
your editor). GitHub is canonical. Commits are authored by
`Miquel Matoses <miquelmatoses@gmail.com>` — not by the server user.
At the end of each session, update `docs/history/roadmap.md` to reflect
reality.

**Cicle de git estàndard (cada PR de Claude Code):** mantenir SEMPRE el
main local sincronitzat amb `origin/main`. Checklist obligatòria:

1. **Inici de sessió, abans de tocar res:** comprovar que `git status`
   està net. Si hi ha canvis locals no committats, ATURAR-SE i preguntar
   al Miquel. Si està net, executar `git fetch && git checkout main &&
   git pull`. Mai crear una branca sense aquest pas previ.
2. **Crear la branca de feature des del main local** ja actualitzat (no
   des d'`origin/main`: amb el pas 1 són equivalents, i així el flux és
   uniforme).
3. **Treball → commit → push → PR → squash-merge** a GitHub.
4. **Després del squash-merge, OBLIGATORI:** `git checkout main &&
   git pull` per descarregar el commit de merge. Aquest era el pas que
   es saltava i deixava el main local enrere.
5. **Cleanup:** `git branch -d <feature-branch>` al final.

**Deploy pipeline (GitHub Actions, since 2026-05-11):**

1. Edit at the Mac → `git commit` → `git push origin main`.
2. GHA picks it up:
   - `.github/workflows/ci.yml` — pytest, lint, migrations check,
     `web-react` build. Runs on every push and PR.
   - `.github/workflows/deploy.yml` — SSHes to the Hetzner box as
     `topquaranta@` and runs `bin/tq-deploy`. Triggered only on push to
     `main`. `paths-ignore`: `docs/**`, `*.md`, `LICENSE*`,
     `.github/workflows/ci.yml` (doc-only pushes don't deploy).
   - Secrets: `HETZNER_HOST`, `HETZNER_USER`, `HETZNER_DEPLOY_KEY`
     (already configured in the repo).
3. `bin/tq-deploy` (on the server) enforces the safe order:
   `git pull` → **`bin/tq-sync-infra`** → `migrate` (if pending) →
   `npm run build` (only if `web-react/` changed) → `systemctl reload
   topquaranta-web` → smoke-test `/api/v1/auth/me/`. Exits 5 if
   `tq-sync-infra` fails.
4. `bin/tq-sync-infra` is the idempotent installer for files that live
   outside the repo's working tree: `deploy/Caddyfile` →
   `/etc/caddy/Caddyfile`, `deploy/cron.topquaranta` →
   `/etc/cron.d/topquaranta`, `deploy/logrotate.topquaranta` →
   `/etc/logrotate.d/topquaranta`, `deploy/topquaranta-web.service` →
   `/etc/systemd/system/topquaranta-web.service`. It validates
   `Caddyfile` with `caddy validate` before installing, and only
   reloads caddy / runs `systemctl daemon-reload` when the file
   actually changed. `tq-sync-infra` is the sole owner of
   `/etc/caddy/Caddyfile`. It must never read, write, or delete
   anything under `/etc/caddy/conf.d/`. That directory is reserved
   for snippets owned by other repos deployed on the same server.

**Never** SSH in to commit-and-deploy by hand. The 2026-05-07
`Album.label` incident (gunicorn `--reload` picked up the new code
before the migration was applied → 30 admin emails in 15 min) is the
canonical reason the pipeline must run end-to-end.

**Never write code directly into `/home/topquaranta/app/`.** Prod is
deployed exclusively via push→GHA→`bin/tq-deploy`, and `tq-deploy` does
`git reset --hard origin/main` — so any file you write into the prod
working tree (a) runs un-reviewed, un-tested code immediately, and (b) is
silently reverted on the next deploy, so a "hotfix" can vanish without
warning. The canonical incident is the 2026-06-02 caducitat guard:
`ingesta/caducitat.py` ran in prod for days while absent from
`origin/main`. The only sanctioned change path is a committed PR. A
`tq-health` git-drift check (added 2026-06-02) now emails admin@ within
the hour whenever the prod tree is dirty (excluding `data/`) or
`HEAD != origin/main`.

**When you DO still need to SSH to the Hetzner box** (these are
operational, not deploy paths):
- Tail live logs: `tail -f /var/log/caddy/access.log`,
  `journalctl -u topquaranta-web -f`,
  `tail -f /var/log/topquaranta/*.log`.
- Debug a cron that failed: `sudo -u topquaranta tq-run <command>`
  and inspect `CRON_META` / `tq-health`.
- Ad-hoc DB inspection that doesn't belong in code:
  `sudo -u topquaranta /home/topquaranta/app/.venv/bin/python
  manage.py shell`.
- Recovery / restore scripts: `tq-recover`, `tq-restore-test`,
  `tq-backup`, `tq-health --email-on-fail`.

Detection net: `tq-health` (hourly cron) emits a `DB migrations: …`
row that flags pending migrations within an hour even when the
pipeline is bypassed. Pytest gate at
`topquaranta/tests/test_deploy_safety.py` asserts the static
invariants (no orphan model changes, scripts well-formed).
