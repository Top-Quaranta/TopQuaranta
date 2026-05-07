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
- **`docs/architecture/`** — `models.md`, `pipeline.md`, `algorithm.md`,
  `analytics.md`, `seo.md` (Sprint S),
  `staff.md`, `api-versioning.md`, `brand-logo.md` (read this BEFORE
  touching anything that loads the brand SVG — three traps documented).
  Reference for the codebase.
- **`docs/product/`** — `definition.md` (què compta com a música en català).
- **`docs/ops/`** — `runbook.md`, `retention.md`, `deprecation.md`,
  `ssh-keys.md`. Things you read when something breaks or has to be
  decommissioned.
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
- **Runtime:** Python 3.12, Django 6.0.4, PostgreSQL 14. Node 22 + Vite 8
  for the SPA.
- **Reverse proxy:** Caddy (auto TLS). Config: `/etc/caddy/Caddyfile`
  (source of truth: `deploy/Caddyfile`).
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
3. Territory accent: a single brand mapping lives at
   `web-react/src/components/editorial.jsx::TERR_COLORS`. Public-page
   labels use `TERRITORI_NOM` (visible) — note that "PPCC" is shown as
   **"Global"** to visitors but stays as the legacy code in DB and API
   query params.

**Editorial primitives** (Sprint J bis, `components/editorial.jsx`):
shared by HomePage, TopPage, ArtistesPage, MapaPage and the
`/comunitat` pages.
- `<Section tone="ink|white">` — alternating full-bleed band.
- `<SectionHeader kicker title>` — kicker auto-recolours per band
  (yellow on ink, ink/60 on white) so a kicker can never re-introduce
  the 1.53:1 yellow-on-white violation caught at the Sprint F audit.
- `<TerritoriBadge codi>` — monochrome SVG via mask (inherits
  `currentColor`).
- `<TrendCue posicio posicio_anterior>` — top-list arrow icon used
  by every weekly-top surface; its colours are tone-safe on both
  ink and white.

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
| **Multi-channel distribution (Sprint I bis, 2026-04-27)** | Same payload, five channels: **Instagram** (feed + stories), **Mastodon**, **Bluesky**, **Telegram** (full carousel via media-group, up to 10 photos), **Newsletter** (HTML email via Brevo to `Usuari.vol_newsletter=True`), **RSS** (`/rss/{top,novetats}.xml`, Atom 1.0). One command `publicar_canal --channel <name>` for the four non-IG channels; auth singletons `{Mastodon,Bluesky,Telegram}Auth`; staff endpoints `/staff/social/{name}/{,test/,clear/}`; toggles in `ConfiguracioGlobal.{instagram,mastodon,bluesky,telegram,newsletter,rss}_actiu`. Cron staggered: Sat IG 09:30 → Mastodon 09:40 → Bluesky 09:50 → Telegram 09:55 → Newsletter 10:00. Auto-tag artists on feed posts via `user_tags` Graph API. |
| **Renderer editorial redesign (2026-04-27)** | First-pass renderer was monochrome + dark + schematic. Rewrote 4 slide kinds + stories: SVG-rasterised brand logo (`vendor/mm-design/icons/brand/logo-topquaranta-rect.svg`) and territory icons (mm-design SVGs), `colors.terr_color()` mirroring SPA's `TERR_COLORS`, `colors.best_text_on()` for monochromatic logo over coloured pills, `ImageOps.fit` cover-fit (no black bars), pill-system using mm-design `--mm-radius-lg`. Caption uses project-week numbering (`music.dates.project_week_number`, anchor Sat 2026-04-25 = wk 34). Novetats window anchored to last publication of same tipus (no fixed 7-day rolling). Eliminated all "Països Catalans" references. |
| **Static social PNG hosting (2026-04-27)** | Meta's media fetcher rejected our Django view (CSP/COOP headers caused code 9004). Caddy now serves `/static/social/*` directly from `/var/cache/topquaranta/social/renders/` as plain files. Setting `SOCIAL_PUBLIC_BASE` in `web_server.py` switches the URL builder. The Django view at `/api/v1/social/render/` stays as fallback. |
| **Gunicorn `--reload`** | Added to `deploy/topquaranta-web.service` after a silent stale-code bug (renderer changes not picked up). Cost: a few stat() per request, negligible. Edits to `.py` files are now picked up automatically without `systemctl reload`. |
| **Mail infrastructure (Sprint I bis, 2026-04-27)** | **Stalwart Mail Server** v0.16.1 on the Hetzner box for inbound + IMAP for `topquaranta.cat` and `cercol.team`. **Outbound via smarthost routing** in Stalwart's MTA strategy: `sender_domain == 'cercol.team' ? 'resend-relay' : 'brevo-relay'`. Brevo (free tier 300/day) for TopQuaranta, Resend for Cercol. Hetzner blocks port 25 outbound, hence smarthosts. TLS cert Let's Encrypt: Caddy obtains it for `mail.topquaranta.cat`; a systemd `path` unit (`stalwart-cert-sync.path` + `.service`) syncs the cert into `/etc/stalwart/certs/` on rotation. **BIMI** TXT at `default._bimi.topquaranta.cat` + Tiny PS SVG at `https://www.topquaranta.cat/static/brand/bimi.svg` (no VMC). **Mozilla autoconfig** at `mail.topquaranta.cat/.well-known/autoconfig/...` so clients self-configure. Full architecture at `docs/EMAIL.md`. |
| **Hetzner Cloud + CDMON DNS APIs (2026-04-27)** | `HETZNER_API_TOKEN` in `.env` + `hcloud` CLI installed; we manage firewall rules via API (e.g. opening 25/465/587/993 was scripted). `CDMON_API_KEY` in `.env`; `dns-backup/cdmon_clean.py` script for batch DNS ops (used to drop 18 legacy CDMON-Micropla records). API endpoint: `https://api-domains.cdmon.services/api-domains/`, header `apikey:`. Caveat: `dnsrecords/create` rejects A apex with bogus error "Destination to redirect not valid"; that one record needs the web panel. |
| **Ingest robustness pass (2026-05-03)** | Three fixes after the APECAT cross-check turned up holes in the pipeline. (a) **D5 self-collab guard**: `_create_track` and `_upsert_track` now compare a Deezer contributor against `set(artista.deezer_ids.values_list("deezer_id", flat=True))` instead of just `deezer_id_principal`. Without this, an artista with multiple Deezer profiles (autoedit + label) crashed signal D5 every hour for ~12 h. (b) **ISRC collision skip**: `obtenir_metadata` now catches `IntegrityError` on `canco_isrc_unique_when_set` and skips the duplicate row instead of aborting the artista's transaction (single-on-LP and featuring-on-both-profiles cases). (c) **Multi-Deezer-ID iteration**: `_fetch_for_artist` loops every `ArtistaDeezer` row of an artista, principal first, so label-secondary catalogues no longer hide. |
| **`obtenir_novetats` P2 cooldown (2026-05-03)** | The legacy P2 used `cancons_obtingudes=False` as a gate and marked an album done as soon as Deezer returned *any* track list (or when the album was >30 days old) — leaving ~3.7 k phantom albums "OK" with zero tracks because Deezer flake at the wrong moment masqueraded as "no tracks". New design: every non-discarded album with a `deezer_id` is re-checked on a per-album cooldown via the new `Album.last_album_check` (DateTimeField, indexed). Cadence: <30 d since release → 24 h, 30-365 d → 7 d, >365 d or unknown → 30 d. NULL = never checked → highest priority. `descartat=True` is the only permanent exclusion. Idempotence preserved by `_create_track`'s deezer_id + ISRC dedup. Migration `music 0060`. `cancons_obtingudes` kept as a deprecated read-only field. |
| **Multi-channel social parity (2026-05-03)** | Bluesky + Mastodon now publish a 4-image carousel (portada + first 3 list slides via `embed.images` / `media_ids[]`, both networks cap at 4) instead of cover-only. Each `_publish_*` returns `(ext_id, extra_meta)`; for Telegram `extra_meta.message_ids` captures every message in the media-group so the new platform-aware delete (`/staff/social/eliminar-remot/`) can remove them all (Telegram has no group-level delete). Real remote delete added for every channel: `mastodon_client.delete_status`, `bluesky_client.delete_post` (parses AT URI → `com.atproto.repo.deleteRecord`), `telegram_client.delete_messages`. Staff list reordered: Data column first, Setmana N second; per-platform row tints; "Esborrar" label is platform-aware. |
| **Renderer readability v3 (2026-05-03)** | Posts list slide: position number 38 → 54 pt, song title 28 → 40 pt; pill width and row height *unchanged* (76 / 105) so the page indicator (`1/4` etc.) stays clear of the last card. Tighter top padding (y+0) inside each cell does the visual work. Posts portada: logo + Setmana pills shifted from x=30 → x=84 (+54 px = 5 % FEED_W), keeping the left-aligned stack but with more breathing room — applied to both `_feed_portada` and `_feed_novetats_portada`. Story canço: title 44 → 80 pt (line-height 90), artist 34 → 44 pt; new "topquaranta.cat" footer at `STORY_H-90` in `COLOR_TEXT_MUTED` (4.5:1 on ink → AA). |
| **Newsletter opt-in on profile (2026-05-03)** | `vol_newsletter` now editable from `/compte/perfil` (was previously settable only at registration). Backend: `compte_views.perfil` GET exposes the flag, PATCH accepts it, and on a False→True transition stamps `consent_newsletter_at` for RGPD audit. Frontend: new section between username and password with a checkbox + helper copy. Only PATCHes when the value actually changed. |

## 7. Shared constants

Import from `music/constants.py`:
- `DIES_CADUCITAT = 365`, `MAX_POSICIONS_TOP = 40`
- `TERRITORI_NOMS` (dict), `TERRITORIS_VALIDS` (tuple of ranking-eligible codes)
- `ML_CLASSE_A_THRESHOLD`, `ML_CLASSE_B_THRESHOLD`, `MIN_TRAINING_SAMPLES`,
  `MIN_NEW_DECISIONS`
- `DEEZER_RATE_LIMIT`, `LASTFM_RATE_LIMIT`, `MAX_API_RETRIES`
- `MOTIUS_REBUIG` — 4 valid reject reasons: `no_catala`, `artista_incorrecte`,
  `album_incorrecte`, `no_musica`. Semantics in `CLAUDE_STAFF.md §5`.

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

Mock all external HTTP — no real API calls. Current suite: **302 passed, 8 skipped**.
Run: `.venv/bin/python -m pytest -q`.

React SPA: Vitest not yet wired for runtime tests; builds validated via
`npm run build` in CI-style deploys.

## 10. Code conventions

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

## 11. Workflow

Claude Code runs on the production server. GitHub is canonical:
`git pull --rebase` before pushing. Never commit without explicit request.
At the end of each session, update `docs/history/roadmap.md` to reflect reality.

**Deploy routine:**

Always use `sudo /home/topquaranta/bin/tq-deploy` after editing code.
Never run a bare `systemctl reload` after a code change.

`tq-deploy` enforces the safe order: pull → check & apply migrations →
build SPA if touched → reload gunicorn → smoke-test. Caught
2026-05-07: a push that referenced a new `Album.label` column was
reloaded by gunicorn `--reload` BEFORE the migration was applied;
every `/album/<slug>` visitor hit a 500, generating 30 admin emails
in 15 min. See `docs/ops/runbook.md §9.4 bis` for the post-mortem.

If `tq-deploy` doesn't fit (e.g. partial deploy, debugging), the
manual safe order is:
1. Edit code (Python and/or React).
2. **`python manage.py migrate`** if any new migration was added.
3. If SPA touched: `cd web-react && npm run build`.
4. `sudo systemctl reload topquaranta-web` — graceful worker swap, no 502.
5. Verify: `curl -sI https://www.topquaranta.cat/api/v1/auth/me/`.

Detection net: `tq-health` (hourly cron) emits a `DB migrations: …`
row that flags pending migrations within an hour even when the
wrapper is bypassed. Pytest gate at
`topquaranta/tests/test_deploy_safety.py` asserts the static
invariants (no orphan model changes, scripts well-formed).
