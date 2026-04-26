# API Versioning Policy

## Status

**Version live:** `v1` — served at `/api/v1/*` since 2026.

**Version planned:** `v2` — no live routes yet. See "When to bump" below.

## Scope

Today's `/api/v1/` surface:
- `GET /api/v1/mapa/artistes/` — map data (territoris + comarques + municipis + artistes) in a single response. Internal consumer: the public `/mapa/` page.
- `GET /api/v1/localitzacio/{territoris,comarques,municipis,municipi-lookup}/` — reference data for the location picker.

No public SDK, no external integrations — so the API is effectively *private* today. The `v1` prefix still matters because:
1. It documents that the surface is a public contract (not a view helper).
2. It provides a painless escape hatch when we need a breaking change.

## When to bump to `v2`

Bump when a **response schema changes in a backward-incompatible way**:
- Field removed, renamed, or type-changed.
- Semantics of a field changed (e.g. a ranking value that previously went 1–40 now goes 0–39).
- A required filter parameter added.

Additions that DON'T require a bump:
- New optional query parameter.
- New field in a response (clients must be tolerant of unknown fields — our DRF responses use plain dicts, so they are).
- New endpoint alongside the old ones.

## How to bump

1. Create `web/api/v2/` alongside `web/api/` (which stays live as v1).
2. Add `path("api/v2/", include("web.api.v2.urls"))` to `topquaranta/urls.py` **before** the v1 line.
3. Implement only the endpoints that changed; unchanged ones can be `from web.api.views import X` re-exports from v2's urls module.
4. Announce the deprecation window: **v1 stays live for 6 months** after v2 is introduced. During the overlap, both versions serve traffic.
5. After 6 months, remove v1 and its URL prefix. Audit the access log for v1 hits before deleting — if the count is non-zero, find the consumer and give them more time.

## Response headers

Every API response carries `X-API-Version: 1` (or `2`) so client bugs that ignore the URL prefix still leave a traceable fingerprint. See `web/api/views.py` middleware / decorator.

## Changelog

- **v1** — 2026. Initial public surface (map + location reference).
