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

## Rate limiting — `429` és part del contracte

Qualsevol endpoint de `/api/v1/` pot respondre **429 Too Many Requests**.
Els límits per defecte (`anon` 60/min, `user` 300/min) i els per endpoint
(`auth_login`, `registre`, `data_export`, `newsletter_unsubscribe`,
`feedback_crear`, `account_delete`, `dm_send`) viuen a
`DEFAULT_THROTTLE_RATES` de `topquaranta/settings/base.py`.

Els límits per endpoint hereten `web.api.utils.ScopedThrottle`, **mai** el
`ScopedRateThrottle` de DRF: aquell llig el scope de la vista
(`view.throttle_scope`) i deixa passar la petició quan no hi és, cosa que
els va mantindre inerts des de maig del 2026 fins al 2026-08-15. El
detall i el guardià són a [`comptes.md`](comptes.md); ací només importa
que **un client ha d'estar preparat per a un 429**, també en endpoints
que històricament no n'havien tornat mai.

Ajustar un límit no obliga a pujar de versió: no canvia cap forma de
resposta. Afegir-ne un a un endpoint que abans no en tenia tampoc, però
val la pena anunciar-ho al changelog d'ací baix.

## Changelog

- **2026-08-15:** els set límits per endpoint passen a aplicar-se de
  veres (abans eren inerts). Els endpoints d'accés, registre, exportació
  de dades, baixa de newsletter, feedback, esborrat de compte i enviament
  de DM poden tornar `429` a partir d'ara.
- **v1** — 2026. Initial public surface (map + location reference).
- **2026-06 (redisseny):** additive fields on `/api/v1/top/` — each
  entry's `artista.territori` (primary territori code for the row chip)
  and the response-level `setmana_numero` (project week number from
  `music.dates.project_week_number`, the single source the social kit
  uses). Additive only; no version bump.
