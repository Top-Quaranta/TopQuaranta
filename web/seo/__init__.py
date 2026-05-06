"""SEO module — server-rendered HTML for crawlers and JS-disabled
clients. Mounted via Caddy's bot-UA matcher (see `deploy/Caddyfile`)
so humans with JavaScript continue receiving the React SPA, while
Googlebot, Mastodon link previews, GPTBot and friends get a
self-contained HTML page with rich metadata + structured data +
the same canonical content the SPA renders client-side.

See `docs/architecture/seo.md` for the full design rationale.
"""
