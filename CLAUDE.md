# CLAUDE.md — TopQuaranta

> Persistent memory for Claude Code. Read this file first on every session.
> Last updated: 2026-04-21 — Post-Sprint-4 audit + Django-templates UI cleanup.

## Other docs
- **`CLAUDE_MODELS.md`** — every Django model with fields, relations, indexes.
- **`CLAUDE_PIPELINE.md`** — ingest → signal → ranking flow, API clients, crons.
- **`CLAUDE_STAFF.md`** — React staff panel, DRF endpoints, permission model.
- **`CLAUDE_ALGORITHM.md`** — 14-CTE ranking algorithm details.
- **`CLAUDE_EXCELLENCE.md`** — full audit + findings (S1..Φ7) from Phase 9.
- **`CLAUDE_LEGACY.md`** — historical audit of the pre-2026 system (reference only).
- **`ROADMAP.md`** — phase status; current state and next steps.
- **`RUNBOOK.md`** — operational troubleshooting.

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
                        │                                                │
  /static/*             │─▶  /home/topquaranta/app/staticfiles/          │
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
- **Runtime:** Python 3.10, Django 5.2, PostgreSQL 14. Node 22 + Vite 8
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
- **DB:** `topquaranta` on localhost. 37 tables (18 domain + Django/axes/
  otp/session internals).
- **Working dir:** `/home/topquaranta/app/`. Virtualenv: `.venv/`.
- **Repo:** `github.com/miquelmatoses/TopQuaranta` (private).

## 4. Project structure

```
/home/topquaranta/
├── bin/                 # ops scripts outside the repo
│   ├── tq-run           # runs manage.py command with retry + status file
│   ├── tq-recover       # detects missed/failed runs, relaunches
│   ├── tq-health        # non-zero exit on any cron failure
│   └── tq-backup        # pg_dump + tiered retention
├── backups/             # daily/ weekly/ monthly/ pg_dump snapshots
└── app/                         # The repo.
    ├── manage.py
    ├── .env                     # never commit
    ├── requirements.txt · requirements-dev.txt
    ├── pyproject.toml · pytest.ini · conftest.py
    │
    ├── topquaranta/             # Django settings + root URLs
    │   ├── settings/            # base · production · web_server · local · test
    │   └── urls.py              # /api/v1/ · /compte/ · /sitemap.xml · /robots.txt
    │
    ├── music/                   # core domain models + services
    │   │                        # Artista, Album, Canco, Territori, Municipi,
    │   │                        # ArtistaLocalitat, ArtistaDeezer,
    │   │                        # HistorialRevisio, StaffAuditLog,
    │   │                        # SpotifyAuth, SpotifyPlaylist
    │   ├── models.py · ml.py · services.py · verificacio.py · signals.py
    │   ├── audit.py · constants.py · titlecase_catala.py · utils.py
    │   ├── ml_model.joblib · ml_tfidf.joblib     # slim model post 2026-04-21
    │   └── migrations/          # 47 migrations (0001 … 0046)
    │
    ├── ranking/                 # ConfiguracioGlobal · SenyalDiari
    │   │                        # RankingSetmanal · RankingProvisional
    │   ├── algorisme.py         # 14-CTE SQL + PPCC aggregation
    │   └── management/commands/calcular_ranking.py
    │
    ├── ingesta/                 # external-API pipeline (ingest + Spotify export)
    │   ├── clients/             # deezer.py · lastfm.py · spotify.py · whisper.py
    │   └── management/commands/
    │       ├── obtenir_novetats.py · obtenir_metadata.py · obtenir_senyal.py
    │       ├── netejar_caducades.py
    │       ├── analitzar_whisper.py · arxivar_senyal_vell.py
    │       ├── autoritzar_spotify.py · configurar_spotify_playlists.py
    │       └── actualitzar_playlists_spotify.py
    │
    ├── comptes/                 # custom Usuari + UserArtista + PropostaArtista
    │   │                        # + Feedback (user correction reports)
    │   ├── views.py             # registre · activar · TQLoginView · 2FA flow
    │   ├── urls.py              # only Caddy-allowlisted routes
    │   ├── forms.py             # RegistreForm only
    │   ├── tokens.py
    │   └── templates/comptes/   # 7 files, all extend _base_auth.html
    │
    ├── web/                     # Django API + SEO + error handlers
    │   ├── api/                 # DRF — the primary Django surface
    │   │   ├── urls.py          # /api/v1/…
    │   │   ├── auth_views.py    # me · login · logout · register
    │   │   ├── ranking_views.py · artistes_views.py · album_views.py
    │   │   ├── canco_views.py · compte_views.py
    │   │   ├── staff/           # split-by-area staff endpoints (Sprint C, 2026-04-25)
    │   │   │                    # _common · dashboard · pendents · artistes
    │   │   │                    # cancons · albums · ranking · propostes
    │   │   │                    # solicituds · senyal · historial · configuracio
    │   │   │                    # audit · usuaris · feedback · estat
    │   │   ├── staff_views.py   # backward-compat shim → re-exports staff/*
    │   │   ├── search_utils.py  # accent + apostrophe insensitive search helpers
    │   │   ├── views.py         # localitzacio (territoris/comarques/municipis)
    │   │   └── middleware.py · VERSIONING.md
    │   ├── sitemaps.py          # hardcoded SPA URLs for /sitemap.xml
    │   ├── views/__init__.py    # 404/500/403 error handlers only
    │   └── templates/web/       # 4 files: robots.txt + 403/404/500
    │
    ├── web-react/               # React SPA ── public + staff UI
    │   ├── vite.config.js       # base: '/'
    │   ├── package.json
    │   ├── dist/                # built bundle served by Caddy
    │   └── src/
    │       ├── main.jsx · App.jsx
    │       ├── lib/             # api.js · urls.js
    │       ├── context/         # AuthContext · FeedbackContext
    │       ├── components/      # Layout · AccountButton · TopQuarantaLogo
    │       │   ├── FeedbackButton · ExternalListenLinks · MmIcon
    │       │   ├── editorial.jsx — shared Section/SectionHeader/
    │       │   │                  TerritoriBadge/TrendCue + TERR_COLORS
    │       │   ├── AdminRoute · StaffLayout · ComunitatLayout
    │       │   └── staff/       # StaffTable · ArtistaPicker
    │       │                    # ArtistesColPicker · LocationCascade
    │       └── pages/
    │           ├── HomePage · TopPage · ArtistesPage · ArtistaPage
    │           ├── AlbumPage · CancoPage · MapaPage
    │           ├── AuthPage · ComptePage · ComptePerfilPage
    │           ├── ProposarArtistaPage · SolicitarGestioPage
    │           ├── SpotifyCallbackPage
    │           └── staff/       # 17 pages — full staff panel
    │                            # StaffDashboard · EstatPage · Pendents
    │                            # StaffArtistes · ArtistaEdit · ArtistaCrear
    │                            # StaffCancons · CancoEdit · StaffAlbums
    │                            # AlbumEdit · StaffRanking · Propostes
    │                            # PropostaDetail · Solicituds · Senyal
    │                            # Historial · Configuracio · Auditlog
    │                            # Usuaris · UsuariDetail · FeedbackPage
    │
    ├── scripts/                 # non-command Python
    │   ├── analisi_lastfm.py · explorar_senyal.py · simular_ranking.py
    │   ├── model_comparison/    # Whisper vs VoxLingua LID evaluation
    │   └── archived_commands/   # one-shot migrations already run (kept for history)
    │
    ├── vendor/mm-design/        # vendored brand tokens for Django static
    ├── deploy/                  # Caddyfile · systemd · cron · logrotate
    └── docs/                    # DEFINITION · DEPRECATION · RETENTION
```

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
| **Grup C community (2026-04)** | `PerfilUsuari`, `Publicacio`, `Comentari`, `Missatge` — directori, feed moderat, DM 1-to-1, comentaris. Missatge té notificació email amb opt-out. Self-delete via email confirmation. |
| **Mapa drill-down (2026-04-22)** | `/mapa` SVG dels PPCC amb 3 nivells (territori → comarca → municipi) i panell lateral amb KPIs + graella d'artistes ordenats per reproduccions. GeoJSON preprocessats (Douglas-Peucker 0.002°) a `web-react/public/geodata/` via `scripts/simplify_geodata.py`. |
| **Public read cache (2026-04-25)** | Hot read endpoints `/api/v1/{ranking,artistes,mapa/artistes-top}/` cached **60 s for anonymous hits** in `pagecache` (LocMem per worker). Authenticated requests bypass. Each endpoint also exposes ETag + Last-Modified via Django's `condition` decorator (rooted at `RankingProvisional.data_calcul`, `Artista.created_at`, `SenyalDiari.data` respectively) — re-fetching clients get a 304 in ~5 ms. Helper at `web/api/utils.py::cache_for_anon`. |

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

Mock all external HTTP — no real API calls. Current suite: **92 passed, 5 skipped**.
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
At the end of each session, update `ROADMAP.md` to reflect reality.

**Deploy routine:**
1. Edit code (Python and/or React).
2. If SPA touched: `cd web-react && npm run build`.
3. `sudo systemctl reload topquaranta-web` — graceful worker swap, no 502.
4. Verify: `curl -sI https://www.topquaranta.cat/api/v1/auth/me/`.
