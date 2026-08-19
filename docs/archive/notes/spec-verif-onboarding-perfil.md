# Finding 1 — Onboarding calls a 404 perfil endpoint

## Hypothesis (as given)
The onboarding flow calls `/api/v1/comunitat/perfil/` which 404s; the real
endpoints are `api/v1/compte/perfil/` and `api/v1/compte/perfil-usuari/`.

## Verdict: **CONFIRMED** (with one correction to the spec wording)

- The onboarding API calls DO 404. Confirmed on prod by URL resolution.
- The hypothesis lists *two* "real" endpoints. They are NOT
  interchangeable: `compte/perfil/` is the **account** endpoint
  (email/username/password/newsletter) and is the WRONG repoint target.
  The correct target is `compte/perfil-usuari/` only.

---

## Evidence

### 1. The onboarding call sites (literal path strings)

`web-react/src/pages/OnboardingPage.jsx`:

```
45:    api.get('/comunitat/perfil/').then(setPerfil).catch(() => {})
96:      await api.patch('/comunitat/perfil/', body)
110:      await api.patch('/comunitat/perfil/', { onboarding_complet: true })
```

API base is `/api/v1` (`web-react/src/lib/api.js:12 const API_BASE = '/api/v1'`),
so these hit `/api/v1/comunitat/perfil/`.

### 2. That path does not resolve (prod, read-only)

```
$ resolve('/api/v1/comunitat/perfil/')      -> RESOLVER404 (no route)
$ resolve('/api/v1/compte/perfil/')         -> api:compte_perfil
                                               web.api.compte_views.dashboard.view
$ resolve('/api/v1/compte/perfil-usuari/')  -> api:compte_perfil_usuari
                                               web.api.comunitat_views.perfil.view
```

`web/api/urls.py` has NO `"comunitat/perfil/"` line (grep for the exact
string returns nothing). The `comunitat/` prefix exists for directori,
publicacions, missatges, etc. — but not `perfil`. The own-profile route
was deliberately filed under `compte/`:

```
web/api/urls.py:61   path("compte/perfil/",        compte_views.perfil,            name="compte_perfil")
web/api/urls.py:704  path("compte/perfil-usuari/", comunitat_views.perfil_usuari,  name="compte_perfil_usuari")
```

Note: `/comunitat/perfil` IS a valid *SPA frontend* route
(`web-react/src/App.jsx:197 <Route path="/perfil" .../>` under the
`/comunitat` layout). The bug is purely the *API* path — the developer
reused the frontend route string for the fetch call.

### 3. Why the correct target is `perfil-usuari`, not `perfil`

The real community-profile page reads/writes the same surface and points
at `perfil-usuari`:

`web-react/src/pages/PerfilUsuariPage.jsx`:
```
39:    api.get('/compte/perfil-usuari/').then(...)
69:      const out = await api.patch('/compte/perfil-usuari/', {...})
```

`compte/perfil-usuari/` → `comunitat_views.perfil_usuari`
(`web/api/comunitat_views/perfil.py:19-122`) accepts every field the
onboarding form saves and returns every field it reads:

| Onboarding READ (OnboardingPage.jsx)        | Returned by `_serialize_perfil(include_private=True)` (`web/api/comunitat_views/_common.py:24-71`) |
|----------------------------------------------|-----------------|
| `perfil.rol_choices`                         | `rol_choices` ✓ |
| `perfil.busca_choices`                       | `busca_choices` ✓ |
| `perfil.nivell_choices`                      | `nivell_choices` ✓ |
| `perfil.social_fields`, `perfil.social`      | `social_fields`, `social` ✓ |
| `perfil.localitat?.pk`                       | `localitat: {pk,...}` ✓ |
| `nom_public/bio/instruments/generes/nivell`  | all ✓ |
| `onboarding_complet`                         | only with `include_private=True` ✓ (this view passes it) |

| Onboarding SAVE body (lines 81-95)           | Handled by `perfil_usuari` PATCH (`perfil.py:31-120`) |
|----------------------------------------------|-----------------|
| nom_public, bio, rol_musical, instruments, busca, generes, nivell | ✓ (lines 36-96) |
| visible_directori, obert_colaboracions, onboarding_complet | ✓ (flags loop, lines 98-107) |
| imatge_url, localitat_pk                      | ✓ (lines 50-66) |
| `...perfil.social` (social URL fields)        | ✓ (SOCIAL_FIELDS loop, lines 110-116) |

By contrast `compte/perfil/` → `compte_views.perfil`
(`web/api/compte_views/dashboard.py`) is the **account** endpoint. Its
docstring: "PATCH accepts any subset of: email, username, password
(requires current_password)" plus `vol_newsletter`. It does NOT accept
`nom_public`/`rol_musical`/`busca`/… and its GET payload (`_profile_payload`)
does NOT return `rol_choices`/`social_fields`/`onboarding_complet`.
Repointing onboarding there would break both read and save.

### 4. User-visible symptom (why it matters)

- GET error is swallowed: `OnboardingPage.jsx:45 .catch(() => {})`. With
  the 404, `perfil` stays `null`, so the page is stuck rendering
  `"Carregant…"` (line 56). The form never appears.
- PATCH errors (`saveAndContinue` line 96, `saltar` line 110) are caught
  at line 100 but only `err.payload?.errors` is surfaced; a 404 has no
  `errors` payload, so "Desar"/"Saltar" silently no-op and `onboarding_complet`
  is never flipped → the user can be bounced back to onboarding on next login.

---

## Verified spec (frontend-only repoint — do NOT implement)

Pure frontend repoint, three lines in
`web-react/src/pages/OnboardingPage.jsx`, replacing the API path string
`'/comunitat/perfil/'` with `'/compte/perfil-usuari/'`:

- line 45:  `api.get('/compte/perfil-usuari/')`
- line 96:  `await api.patch('/compte/perfil-usuari/', body)`
- line 110: `await api.patch('/compte/perfil-usuari/', { onboarding_complet: true })`

No backend change required: `compte/perfil-usuari/` already exists and its
read/save contract is a superset of the onboarding form. A dedicated
`comunitat/perfil` API endpoint is NOT expected — `perfil_usuari` is the
canonical own-profile endpoint and is already used by the live profile page.
