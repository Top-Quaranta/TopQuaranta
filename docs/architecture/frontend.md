# Frontend (web-react SPA)

The TopQuaranta site is a single-page React app served from
`web-react/dist/` by Caddy. Django stays behind it on `/api/*` plus a
handful of full-page flows (registration, 2FA, sitemap, RSS). This
doc covers the SPA layout, build, and the seam where it meets the
backend; for the visual design system see
`docs/architecture/brand-logo.md`.

## Stack

- React 19, react-router-dom 7.
- Vite 8 + `@vitejs/plugin-react`, Tailwind v4 via
  `@tailwindcss/vite`.
- `mm-design` consumed as a git npm dep
  (`github:miquelmatoses/mm-design`) for tokens and brand SVGs.
- `recharts` for staff dashboards AND the public CancoPage ranking
  chart — both lazy-loaded (the chart is split into
  `components/CancoChart.jsx` and pulled via `React.lazy`) so the
  public bundle does not pay for it, `react-helmet-async` for SEO head
  tags,
  `react-markdown` + `remark-gfm` for community rich text,
  `vitest` for unit tests.
- Node 22 is the build target. CI uses `npm ci` against
  `package-lock.json`; the server only consumes `dist/`.

## Directory layout

```
web-react/
├── index.html              Vite entry; the only HTML file
├── package.json            scripts: dev, build, lint, preview, test
├── vite.config.js          dev proxy to Django, manualChunks split
├── vitest.config.js        unit-test config
├── public/
│   └── geodata/            Simplified GeoJSONs for /mapa (Caddy serves)
└── src/
    ├── main.jsx            Mounts <App /> + global providers
    ├── App.jsx             Single <Routes> tree (~76 routes)
    ├── i18n.js             ca-only labels (no library, plain map)
    ├── index.css           Tailwind imports + @theme tokens
    ├── assets/             SVGs and static images bundled by Vite
    ├── components/         Cross-page UI (Layout, AdminRoute,
    │                       editorial primitives, MmIcon, ...)
    │   ├── ui/             Buttons, inputs, modals
    │   └── staff/          Staff-only widgets
    ├── context/            React contexts:
    │                       - AuthContext (profile, login, refresh)
    │                       - FeedbackContext (toast bus)
    ├── hooks/              useApi (fetch wrapper + auth headers)
    ├── lib/                Pure helpers:
    │                       analytics, api, format, img, urls,
    │                       seoHead, strip-markdown
    ├── locales/            Catalan copy for legal pages + emails
    └── pages/              One file per route
        ├── HomePage / TopPage / ArtistesPage / MapaPage / ...
        ├── legal/          7 legal pages + LegalLayout
        └── staff/          Staff pages (StaffLayout)
            └── social/     Distribution sub-views: a shared,
                            descriptor-driven ChannelView template
                            (one page per simple channel)
```

Routing is centralised in `App.jsx`: a flat `<Routes>` tree with no
nested layouts beyond the per-section `<Layout>`, `<StaffLayout>`,
`<ComunitatLayout>` and `<LegalLayout>` wrappers.

## Public vs staff vs community

- **Public** (`Layout`): `/`, `/top`, `/artistes`, `/artista/:slug`,
  `/album/:slug`, `/canco/:slug`, `/mapa`, `/com-funciona`,
  `/legal/*`. Anonymous-cacheable for 300 s by Django (see
  `web/api/utils.py::cache_for_anon`).
- **Account flows** (handled by `ComptePage` and friends, plus
  Django full-page templates for registration and 2FA): `/compte`,
  `/compte/perfil`, `/compte/accedir`, `/compte/callback`,
  `/compte/artista/{proposta,gestio}`, `/spotify/callback`.
- **Community** (`ComunitatLayout`): `/comunitat`,
  `/comunitat/directori`, `/comunitat/u/:username`,
  `/comunitat/publicar`, `/missatges`.
- **Staff** (`StaffLayout` behind `<AdminRoute>`): everything under
  `/staff/...`. The route guard bounces unverified staff sessions
  full-page to `/compte/2fa/verificar`, so the same session cookie
  the SPA uses ends up OTP-flagged when it returns.

The `AdminRoute` 2FA handoff is the only architecturally interesting
auth seam; see the file's docstring for the rationale.

The **distribution area** under `/staff/social` is being split from a
single monolithic page into homogeneous house-style views. `/staff/social`
is the cockpit (master switch + the six-channel grid); the simple
channels have their own page at `/staff/social/<canal>` (`mastodon`,
`bluesky`, `telegram`), all sharing one `pages/staff/social/ChannelView.jsx`
template that paints from `channelDescriptors.jsx` — adding a channel or
a credential field means extending the descriptor, not writing a new
page. The **unified publications table** lives at
`/staff/social/publicacions` (`StaffSocialPublicacionsPage` →
`PublicacionsTable`, fed by the paginated `social_list`): one house-kit
table with search, a FilterPanel (canal/estat/tipus/setmana), deep-link
query params, a per-row clickable link, and the lifecycle actions. Above
the table, a self-fetching `MetricsStrip` shows per-platform engagement
totals from `/staff/social/metrics-summary/` (renders nothing while
loading, on error, or before any post has a metric snapshot). The
channel views embed that same `PublicacionsTable` scoped to their
channel. Each descriptor also declares a **4-section schema** (`section1`
/ `kpis` / `control` / `analytics`), and `ChannelView` renders those
sections generically — a missing KPI/metric for a channel paints an
honest dash, never a fake 0. **Newsletter** is the first complete
instance: a first-class view at `/staff/social/newsletter` whose Section
1 (`NewsletterSection`) adds a live can-generate indicator + a
consolidated-week selector + on-demand "Generate (engine)" + the shared
`NewsletterDraftEditor` (extracted from the legacy
`/staff/social/esborrany` page, now a thin wrapper kept for the cron
email links). Instagram and RSS are still managed in-page on the cockpit
(which keeps the week calendar + slide-render button); Spotify stays on
its own page for now (whose header carries a catalog-wide
enrichment-coverage KPI from `spotify/estat`'s `enrichment_coverage`). The cockpit also hosts the **distribution matrix**
(`pages/staff/social/MatriuGrid.jsx`): a self-fetching canal × tipus grid
of Actiu checkboxes (the third gate, `MatriuPublicacio`) over
`/staff/social/matriu/` + `/staff/social/matriu/toggle/`. An off cell
renders inactive (never hidden); non-seeded combos paint a blank dash. Not to be confused with `/staff/publicacions`
(community posts).

## Backend seam

- All data goes through `lib/api.js` which prefixes `/api/v1/` and
  attaches the `X-CSRFToken` header from the `csrftoken` cookie.
  Same session cookie as Django, so DRF's `SessionAuthentication`
  works untouched; django-axes + django-otp also see the SPA traffic
  as normal session requests.
- DRF endpoints under `web/api/` (documented at
  `docs/architecture/api-versioning.md` and
  `docs/architecture/staff.md`). The SPA does not know about model
  internals; everything it consumes is a serialised payload.
- ETag + Last-Modified on the hot read endpoints
  (`/ranking`, `/artistes`, `/mapa/artistes-top`) means re-fetches
  return 304 in a few ms.

## Build, dev, deploy

```
# Local dev (Vite + HMR, proxies /api to Django on :8083)
cd web-react && npm install && npm run dev

# Unit tests (vitest)
npm test

# Production build (writes to web-react/dist/)
npm run build
```

On the server, `bin/tq-deploy` runs `npm run build` only when the
incoming push touched `web-react/`. Caddy then serves
`web-react/dist/` for everything that is not under Django's owned
paths (`/api/*`, `/compte/{2fa,login,registre,activar}/*`,
`/sitemap.xml`, `/robots.txt`, `/rss/*`, `/static/*`). React Router
handles client-side 404.

## Code splitting

`vite.config.js` declares `manualChunks` for `react` (core), `recharts`
and `react-router-dom`. The dedicated `react` chunk is evaluated first
and pins React core (`react` / `react-dom` / `react-is` / `scheduler`)
so the shared React runtime is never co-located into a feature chunk —
without it, a shared runtime module landed inside the `recharts` chunk,
so the entry imported a symbol from it and every public page
`modulepreload`ed all of recharts (~110 kB gz) even though only the
lazy `CancoChart` uses it (LCP audit Task 1, 2026-05).

`recharts` is now reached ONLY through dynamic `import()`: the staff
page tree (`pages/staff/*`), the legal pages, and the public
CancoPage ranking chart (`components/CancoChart.jsx`). So an anonymous
visitor's first byte pays for the public surface only and recharts is
no longer in the entry `modulepreload` list.

## Fonts

Self-hosted (OFL), served from `public/fonts/*` on our own origin.
Replaced the Google Fonts `@import` (which added a 3-hop critical
chain — external CSS → `fonts.googleapis.com` CSS → `fonts.gstatic.com`
woff2 — with no preload, delaying the text LCP on home/top per LCP
audit Task 1).

- **Families:** Playfair Display (headings) + Roboto (body). Both are
  **variable** fonts, so one woff2 per family+subset covers all weights
  via a `font-weight` range (Playfair `400 800`, Roboto `300 700`).
- **Subsets:** `latin` + `latin-ext` only (latin-ext carries Catalan
  edge glyphs such as `ŀ`). No italic axis — italics stay synthetic,
  identical to before. Four files total (~132 kB; latin 38/43 kB,
  latin-ext 21/29 kB).
- `@font-face` blocks live in `src/index.css` with `font-display: swap`
  and the Google unicode-ranges preserved.
- **Preloaded** in `index.html` (`<link rel="preload" as="font"
  crossorigin>`): the two `latin` faces (`playfair-display-latin.woff2`,
  `roboto-latin.woff2`) — the above-the-fold text LCP. `latin-ext`
  loads on demand.
- `mm-design/tokens/typography.css` is intentionally NOT imported in
  `main.jsx`: its only effect was a Google Fonts `@import` (its
  `--mm-font-*`/`--mm-text-*` tokens are unused here). `colors.css` and
  `spacing.css` are still imported.
- The Django auth templates (`comptes/_base_auth.html`) still use Google
  Fonts — a separate, self-contained surface — so the shared Caddy CSP
  keeps `fonts.googleapis.com` / `fonts.gstatic.com` allowed.
