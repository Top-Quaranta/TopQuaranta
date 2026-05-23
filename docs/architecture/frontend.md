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
- `recharts` for staff dashboards (lazy-loaded so the public bundle
  does not pay for it), `react-helmet-async` for SEO head tags,
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
        └── staff/          28 staff pages (StaffLayout)
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

`vite.config.js` declares `manualChunks` for `recharts` and
`react-router-dom` so the public bundle (HomePage / TopPage /
ArtistaPage) does not download the staff-only chart library.
Dynamic `import()` is used for the entire staff page tree (`pages/
staff/*`) and the legal pages, so an anonymous visitor's first byte
pays for the public surface only. Current gzipped public bundle is
about 200 kB.
