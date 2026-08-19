# CLAUDE.md — TopQuaranta

> Persistent memory for Claude Code. Read this file first on every session.
> Last updated: 2026-08-19 — docs reduced to invariants (see §"Docs").

## Docs — where things live

Docs say only what matters. A change edits a doc only when it changes an
invariant; everything else is an override on the docs gate — the normal
case. Policy: `docs/policies/conventions.md` §Documentation.

- **`docs/architecture/<app>.md`** — one per app (`music`, `ranking`,
  `ingesta`, `social`, `web`, `comptes`, `analytics`, `frontend`):
  invariants + traps, each with the test that guards it. Read the one
  for the app you touch. Brand-SVG traps are in `frontend.md`.
- **`docs/DECISIONS.md`** — every ADR in 4-6 lines. **`docs/LESSONS.md`**
  — every incident in one paragraph with its guard. Full texts in
  `docs/archive/`.
- **`docs/ops/runbook.md`** — the 3 a.m. procedures: deploy, health,
  restore, Caddy multi-tenant, secrets, mail, backups.
- **`docs/product/definition.md`** — què compta com a música en català.
  **`MANIFEST.md`** — mission, no-goals. **`LICENSE-DATA.md`** — CC BY 4.0.
- **`docs/history/roadmap.md`** — estat actual + pendents (update at the
  end of each session). **`docs/archive/`** — kept, not maintained.

---

## 1. Project

TopQuaranta (`topquaranta.cat`) is a weekly music ranking for Catalan-language
music across 10 territories: `CAT`, `VAL`, `BAL`, `PPCC` (aggregate, shown
as «Global»), `ALT`, `CNO`, `AND`, `FRA`, `ALG`, `CAR`. Mission: show that
Catalan-language music is alive and growing.

- **Signal:** Last.fm (`playcount` + `listeners`, normalised via
  `percentileofscore`); YouTube views per video as a second signal
  (2026-08). **Metadata:** Deezer (public API, ISRC on every track);
  MusicBrainz as disambiguation oracle. **Playlist output:** Spotify
  (OAuth refresh token, cron sync).

## 2. Architecture

Public site and staff panel are a React SPA (`web-react/`); Django owns
the API, a handful of auth flows and SEO:

```
                        ┌──────────── Caddy (TLS + routing) ────────────┐
  /api/v1/*             │                                                │
  /compte/{2fa/*, login, │─▶  Django · gunicorn :8083                    │
    logout, registre,    │    (session + CSRF + axes + django-otp +     │
    activar/*}           │     ConfiguracioGlobal)                       │
  /sitemap.xml /robots.txt /rss/*                                       │
  /static/*             │─▶  /home/topquaranta/app/staticfiles/          │
  /static/social/*      │─▶  /var/cache/topquaranta/social/renders/      │
  everything else       │─▶  web-react/dist/ (SPA index.html fallback)   │
                        └────────────────────────────────────────────────┘
```

SPA routes: `/`, `/top`, `/artistes`, `/artista/<slug>`, `/album/<slug>`,
`/canco/<slug>`, `/mapa`, `/compte/*`, `/staff/*`, `/spotify/callback`.
Django still renders registre/login/2FA/activation templates and the
error pages (`comptes/_base_auth.html`, self-contained). Bots get
server-rendered SEO pages (`web/seo/`).

## 3. Infrastructure

Hetzner CX22 (`188.245.60.20`), Ubuntu 22.04; Python 3.12, Django 6.0,
PostgreSQL 14 (localhost only); Node 22 + Vite for the SPA. Caddy is
multi-tenant: `/etc/caddy/Caddyfile` is ours (source `deploy/Caddyfile`,
installed by `bin/tq-sync-infra`); `/etc/caddy/conf.d/*.caddy` belongs to
other repos — never touch it. `topquaranta-web.service` → gunicorn :8083
(`ExecReload=HUP`). Cron `/etc/cron.d/topquaranta` (source
`deploy/cron.topquaranta`); logrotate likewise. Working dir
`/home/topquaranta/app/`, venv `.venv/`. Firewall: 22, ICMP, 80-443 only.
Mail: mailboxes on Purelymail, automatic sending via Brevo; nothing hosted
here (Hetzner blocks port 25). Ops scripts in `/home/topquaranta/bin/`
(`tq-run`, `tq-health`, `tq-backup`, `tq-recover`). Details: runbook.

## 4. Project structure

```
app/
├── topquaranta/   # settings (base · production · web_server · local · test)
├── music/         # domain: Artista / Album / Canco / Territori / HistorialRevisio / ML
├── ranking/       # algorithm + ConfiguracioGlobal + Top* + distribution gates
├── ingesta/       # Last.fm / Deezer / MusicBrainz / Spotify / YouTube clients + commands
├── comptes/       # Usuari, auth, gestors, community, newsletter
├── web/           # DRF API (web/api/), SEO, staff endpoints
├── web-react/     # React SPA — public + staff
├── social/        # 5-channel publishing, narrative engine, renderer, IG tags, sondes
├── analytics/     # pageviews, health report, digest, GoAccess
├── scripts/       # ad-hoc Python (docs checks, mutation harness, analyses)
├── deploy/        # Caddyfile · systemd · cron · logrotate · cron-meta.json
└── docs/          # see top of this file
```

## 5. Design system

`mm-design` tokens (npm git dep in `web-react/`; `vendor/mm-design/` for
Django). Colours/fonts/spacing only via `var(--mm-*)` or Tailwind `tq-*`
tokens — never hardcode hex. Fonts: Playfair Display (headings), Roboto
(body). Public pages use `components/rd/primitives.jsx`; staff uses the
rd light canon in `components/rd/surface.jsx`; `components/editorial.jsx`
is legacy — do not build on it. Territory palette single source:
`components/rd/terr.js`. WCAG AA baseline. Traps + details:
`docs/architecture/frontend.md`.

## 6. Key decisions (one line each; why + guard in `docs/DECISIONS.md` / architecture docs)

| Decision | Rationale |
|---|---|
| Last.fm as signal, Deezer as metadata | Spotify popularity deprecated 2024-11; Spotify API 403 for new apps. Deezer: public + 100 % ISRC. |
| Algorithm ported, not rewritten; PPCC aggregates | Same 14-CTE math in `ranking/algorisme.py`; PPCC = top-40 of each territory + position penalty, deduped. |
| Territory on artist (M2M), auto-synced from localitats | Legacy duplicated tracks per territory. |
| Human approval for every auto-discovered artist | False positives (metal "Aion", anime "Animal"). ML pre-classifies; no sub-tier auto-decides today. |
| **aprovat ⇒ Deezer ID OR MBID** | An artist needs ≥ 1 external anchor (Crim-style Deezer collisions). |
| MusicBrainz = disambiguation oracle; auto-match by name + PPCC area, never Lucene score | "Casual" bug (US rapper at score 100). Cron re-validates MBIDs against localitats. |
| Last.fm aliases sum into the signal; similars are row-per-edge | «Delên» case: 35 artists lost up to 99 % of plays. |
| ISRC on every Canco; 12-month track cutoff (`DIES_CADUCITAT`) | Universal key; current music only. |
| No Celery — cron + `SingletonLock` (exit 75) + `tq-health` watchdog | A lock-skip that exits 0 hid a 12-day hang. |
| React SPA + session-cookie auth; 2FA via Django page | Same cookie as Django; axes + django-otp untouched. |
| Spotify as playlist output (app-owner Premium) | OAuth refresh token → cron sync; catalog reads not relied on. |
| Public read cache: `cache_for_anon` per endpoint (LocMem, anon only) | Hot endpoints; authenticated requests bypass. |
| Multi-channel distribution: IG, Mastodon, Bluesky, Telegram, Newsletter, RSS | Same payload; three gates (master → channel → matrix); story-set counts as 1. |
| Static social renders served by Caddy (`SOCIAL_PUBLIC_BASE`) | Meta media fetcher rejects Django headers (9004). |
| Narrative engine for captions; `@handle` only on Instagram | Other networks' mention syntax differs; we store no per-network handles. |
| Gunicorn `--reload` removed; deploy only via `bin/tq-deploy` | Workers hot-reloaded models before migrations (ADR-0001). |
| Test policy: promises, not detectors; mutation-verified | Audit 2026-08-18 (`scripts/mutacio/`). |
| Docs policy: invariants only; override is the norm | Audit 2026-08-19 (`conventions.md` §Documentation). |

## 7. Shared constants

`music/constants.py`: `DIES_CADUCITAT = 365`, `MAX_POSICIONS_TOP = 40`,
`TERRITORI_NOMS`, `TERRITORIS_VALIDS`, ML thresholds, `DEEZER_RATE_LIMIT`,
`LASTFM_RATE_LIMIT`, `MAX_API_RETRIES`, `MOTIUS_REBUIG` (3 action-based
reject codes; semantics in `docs/architecture/web.md`).

## 8. Environment (.env)

```dotenv
DJANGO_SECRET_KEY=
DJANGO_SETTINGS_MODULE=topquaranta.settings.production
ALLOWED_HOSTS=topquaranta.cat,www.topquaranta.cat
DEBUG=False
DATABASE_URL=postgres://topquaranta:PASSWORD@localhost:5432/topquaranta
LASTFM_API_KEY=            LASTFM_API_SECRET=
SPOTIFY_CLIENT_ID=         SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=https://www.topquaranta.cat/spotify/callback
```

Loaded via `python-decouple`; always `from django.conf import settings`.

## 9. Testing

`pytest.ini`: `addopts = --ds=topquaranta.settings.test -n 4` (the `--ds`
pin blocks env-var overrides, ADR-0003; `-n 4` fixed, ADR-0017 — pass
`-n 0` for a single test). Mock all external HTTP. Suite: **1805 passed,
5 skipped**, ~75 s. Run: `.venv/bin/python -m pytest -q`. React: Vitest
runs in CI (`frontend-tests`).

**Test policy:** anchor tests to the *promise*, never to today's
coordinates, copy or call shape. Diagnostic: *if someone improved this
code, would the test fail?* If yes it obstructs. A test that survives an
audit must fail under a mutation of what it guards — `scripts/mutacio/`.

## 10. Code conventions

Canonical: `docs/policies/conventions.md`. Summary: no `print()`
(logging / `self.stdout.write`), no `sys.exit()` (`CommandError`), no raw
DDL outside migrations, ORM only (exception: `ranking/algorisme.py`), all
writes in `transaction.atomic()`, type hints, f-strings in code / `%s` in
logger, black + isort, English comments, Catalan user-facing strings,
`# Spec: docs/architecture/<app>.md` backlink on modules (pre-commit
validates), captures real or labelled MOCK, E2E smokes on `qa_smoke`.
ML: new features go at the **end** of `FEATURE_NAMES` (`music/ml.py`
alignment check). Docs gates (`ci-docs.yml`, config `docs-map.yml`):
`docs-coherence` (override line `docs-reviewed: <doc> : <reason>` when
no invariant changed), `docs-size` (400, no grandfathering),
`docs-novelty` (new top-level dir must be in the map).

## 11. Workflow

Edits happen locally on the Mac; GitHub is canonical; commits authored by
`Miquel Matoses <miquelmatoses@gmail.com>`. End of session: update
`docs/history/roadmap.md`.

**Cicle de git (cada PR):** (1) `git status` net — si no, ATURAR-SE i
preguntar; `git fetch && git checkout main && git pull`. (2) Branca de
feature des del main local. (3) Treball → commit → push → PR →
squash-merge. (4) **Després del merge, obligatori:** `git checkout main
&& git pull`. (5) `git branch -d <branca>`.

**Deploy pipeline (GHA):** push to `main` → `ci.yml` (pytest, lint,
migrations, SPA build) + `deploy.yml` (SSH → `bin/tq-deploy`:
`git reset --hard origin/main` → `bin/tq-sync-infra` → `migrate` →
`npm run build` if `web-react/` changed → `systemctl reload` → smoke
`/api/v1/auth/me/`; exit codes documented in the script). Doc-only pushes
don't deploy.

**Never** SSH in to commit-and-deploy by hand, and **never write code
into `/home/topquaranta/app/`**: it runs unreviewed and vanishes on the
next deploy (2026-06-02 caducitat guard). `tq-health` mails admin@ within
the hour on git drift or pending migrations. SSH is for operations only:
tail logs (`journalctl -u topquaranta-web -f`, `/var/log/topquaranta/*.log`),
`sudo -u topquaranta tq-run <command>`, `manage.py shell`, `tq-recover` /
`tq-backup`. Procedures: `docs/ops/runbook.md`.

**Agents in parallel** must each work in their own git worktree; long
sessions need `caffeinate` (the Mac sleeps and kills background agents).
