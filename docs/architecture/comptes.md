# comptes — auth, profile, workflow sol·licituds

The `comptes` app owns user identity, the verified-manager
relationship to artists, the community surface (DMs, profiles,
publications), and the new Workflow Sol·licituds de Revisió.

## Models

| Model | Purpose |
|---|---|
| `Usuari` | Custom `AUTH_USER_MODEL` (extends `AbstractUser`, no extra fields yet). `db_table = "auth_user"`. |
| `PerfilUsuari` | One-to-one community profile (visible_directori, nom_public, imatge_url, vol_newsletter, opt-outs). |
| `UserArtista` | Gestor↔Artista relationship. `verificat=True` + `estat=aprovat` ⇒ gestor can self-edit the artist via `/compte/artista/<slug>/editar/`. |
| `PropostaArtista` | A user proposes a new artist (with Deezer IDs + localitats). Staff approves → triggers `Artista` creation. |
| `Feedback` | Anonymous correction reports (per-page URL). |
| `Missatge` | DM between users; community inbox. |
| `Publicacio` | Community feed post (moderated). |
| `Comentari` | Flat comments on `Publicacio`. |
| `SolicitudRevisio` | Gestor → staff review request (vegeu ADR-0004). |

Migrations live at `comptes/migrations/`. Most recent significant:
- `0016_admin_pseudouser` — seed the `admin` pseudo-user (community
  fan-out target).
- `0017_userartista_email_aprovacio_at` — stamp the "verified"
  email at send-time so the retroactive notifier is idempotent.
- `0018_solicitudrevisio` — Workflow Sol·licituds (ADR-0004).

## Auth flow

- Registration via Django form (`registre.html` template, the
  only one not yet ported to the React SPA).
- Email activation: `activar/<uidb64>/<token>/` route.
- 2FA TOTP via `django-otp` + `django-otp-totp`. Staff users are
  bounced to `/compte/2fa/verificar` if their session isn't
  OTP-flagged.
- Login throttled by `django-axes` (5 attempts per (username, ip)
  per minute via `ScopedRateThrottle` mirror on `auth_login`).
- Session cookies shared with the React SPA (same origin), so
  CSRF token + sessionid carry over without extra config.

## Workflow Sol·licituds de Revisió

Sprint 2026-05-20 (PR #54). Replaces the previous DM-ping
pattern (see
`docs/post-mortems/2026-05-19-workflow-sollicituds-redesigned.md`)
with a structured workflow.

```
gestor                              staff
  │                                  │
  ├─ POST /compte/artista/<slug>/   │
  │  cancons-pendents/ping-staff/   │
  │                                  │
  ↓                                  │
SolicitudRevisio(estat=pendent)    │
  │                                  │
  ├─ email notify_admins ──────────→ inbox
  │                                  │
  │                                  ├─ open /staff/sollicituds-revisio/
  │                                  ├─ POST .../marcar-en-revisio/
  │                                  │   → estat=revisada
  │                                  ├─ POST .../reconsiderar-rebutjada/
  │                                  │   → HistorialRevisio.reconsiderada=True
  │                                  │   → cron re-imports on next tick
  │                                  └─ POST .../resoldre/
  │                                      → estat=resolta + nota_resolucio
  │                                      → email notify_gestor
  ↓                                  ↓
GET /compte/artista/<slug>/         (workflow complete)
sollicituds/                         
  → returns latest + count
```

State machine: `pendent → revisada → resolta`. No reverse
transitions; a re-request is a new `SolicitudRevisio` row (with
the 7-day per-artist cooldown on
`Artista.ultim_ping_revisio_at`).

## Identities

The `admin` pseudo-user (seeded by migration 0016) is the
community-inbox target. Any DM addressed to `admin` fans out via
email to every active `is_staff=True` user; the
pseudo-user's own opt-out preference is ignored on the fan-out
branch (the staff alert is the whole point).

Production auth tokens (Google OAuth, Brevo SMTP, etc.) belong to
`admin@topquaranta.cat`, never a personal account. See
`docs/policies/identities.md`.

## Notifications

Central transactional-email module at `comptes/notifications.py`.
Six paired entry points:

- `notify_admins_nova_solicitud_gestio` / `notify_user_solicitud_resolta`
- `notify_admins_nova_proposta` / `notify_user_proposta_resolta`
- `notify_admins_nou_feedback` / `notify_user_feedback_resolt`

Plus the workflow sol·licituds pair:

- `notify_admins_nova_sollicitud_revisio` — fires on gestor ping.
- `notify_gestor_sollicitud_revisio_resolta` — fires on staff
  resolution.

All best-effort: a mail-server hiccup logs and swallows so the
business write isn't blocked.

## RGPD surfaces

- `/compte/exportar-dades/` — JSON export of everything tied to
  the user (Feedback, UserArtista, Publicacio, Comentari,
  Missatge, StaffAuditLog rows where they're the target, axes
  login history). Throttled 3/h.
- `/compte/baixa-newsletter/` — token-signed unsubscribe (token
  expires after 1 year, May-2026 audit fix). Throttled 10/min.
- `/compte/esborrar-sollicitud/` — self-delete confirmation
  email flow. Throttled per `_AccountDeleteThrottle`.

## Weekly newsletter (Step 2 rework, 2026-06-01)

`comptes/newsletter.py::send_top_newsletter` builds **one Global
newsletter per week** (no territorial editions). `_build_top_context`
assembles a recipient-independent context once per run:

1. **Header** — raster logo (`logo_email.png`) on ink + "Setmana N ·
   Top Global" + "Veure al navegador".
2. **Podi** — #1 hero (500 px cover) + #2-3 sub-cards.
3. **Editorial** — the narrative paragraphs from the social newsletter
   composer (Step 1β).
4. **Top 4-10** — hybrid: 4-5 list rows, 6-9 a 2×2 grid, 10 centred.
5. **CTA** — "Veure el top complet".
6. **Territorials** — CAT/VAL/BAL current #1 mini-cards.
7. **Novetats** — 2-3 of the week's releases.
8. **Share** — IG/Mastodon/Bluesky/Telegram buttons.
9. **Footer** — unsubscribe + backup link.

Template `comptes/templates/comptes/email_newsletter_top.html` is
self-contained (640 px, light `#fafafa` body + ink header, system
sans, `@media` responsive + dark mode), no longer extends
`email_base.html`. The `_trend_badge.html` partial renders the
per-entry movement.

Helpers:
- **`newsletter_utm.build_newsletter_url(base, content, setmana)`** —
  every body link gets `utm_source=newsletter`, `utm_medium=email`,
  `utm_campaign=top_<setmana>_global`, `utm_content=<block>`
  (`podi_1`, `top_4`, `cta_top`, `territorial_cat`, `novetat_1`,
  `compartir_telegram`, …).
- **`newsletter_covers.album_cover_url(deezer_id, mida)`** — local JPG
  at `/portades/album/<id>-{250,500}.jpg` (filesystem check via
  `ingesta.portades.manager`, no network) else the committed
  placeholder.
- **`newsletter_covers.ensure_cover_downloaded(deezer_id, source_url)`**
  — called from `_build_top_context` for every cover slot (podi, resta,
  territorials, novetats) BEFORE composing. If the local JPG is missing
  it pulls it synchronously via the SAME portades pipeline
  (`manager.download_and_convert`), so the policy stays self-hosting-only
  (no Deezer hotlink in the email) yet the logo fallback only shows for
  albums genuinely without a Deezer cover. Best-effort: never raises;
  an album with no `source_url` stays on the placeholder. Closes the
  2026-06-07 gap where a long-standing #1 (Rosalía · "Divinize") showed
  the logo because the nightly `descarregar_portades` cron — unordered,
  200/run, no ranking priority — had never generated its cover.
- **`newsletter_meta.trend_indicator(pos, pos_anterior, is_return)`** —
  ↑N / ↓N / → / DEBUT / TORNA (a13) with mm-design colours. Deltas
  come from `payload.build_top`'s `posicio_anterior` (no extra query).
- **`newsletter_meta.derive_subject(hero, week)`** — short editorial
  subject (≤60 chars) from a per-scenario_code phrase bank.

Raster assets (email clients don't render SVG) are committed PNGs
under `web/static/web/img/newsletter/`, regenerable run-once via
`manage.py generar_assets_newsletter` (rasterises the vendored brand
SVG through `social.svg_assets`): `cover_placeholder.png` (500×500,
ink + white logo) and `logo_email.png` (full-colour header mark).

### Opt-out review flow (2026-06-07)

The subscriber newsletter is sent through a **review draft**, still fed
by the narrative engine (an LLM is a later phase). Model
`comptes.NewsletterDraft` — `unique(tipus, territori, setmana)`,
`estat` ∈ `pendent`/`enviat`/`cancellat` (NO "approved": `pendent` =
will send), `font` (`motor`/`llm`), `editat`.

1. **Saturday 09:00 — `generar_esborrany_newsletter`** (after
   `calcular_top`): composes `subject` + `narrative_html` via
   `newsletter.build_draft_text` (wraps `_build_top_context`,
   side-effect-free — no `mark_used`), persists a `pendent` draft
   (idempotent: never overwrites an existing week), emails staff a link
   to `/staff/social/esborrany`.
2. **Review** — staff endpoints (`web/api/staff/newsletter.py`, IsStaff):
   `GET /staff/newsletter/esborrany/` (draft + the live top it will ship
   with, to spot mismatches + the Sunday send date), `PATCH` (edit
   subject/narrative → `editat=True`, only while `pendent`), `POST
   …/cancellar/` (→ `cancellat`). SPA page `NewsletterDraftPage`.
3. **Sunday 10:00 — `enviar_newsletter`**: gated by
   `ConfiguracioGlobal.pot_publicar("newsletter")`; reads the week's
   draft — `cancellat` → skip; else sends the (possibly edited)
   `subject`+`narrative_html` via `send_top_newsletter(...,
   subject_override=, narrative_html_override=)`, **rebuilding the list
   (podi/entries/covers) from the FINAL top at send time**; writes the
   `newsletter` `SocialPost` + `newsletter_publicat` audit; marks the
   draft `enviat`. Idempotent (already-`enviat` skipped unless
   `--force`).

The other channels stay on Saturday (`publicar_canal`); only the
newsletter moved to the Sunday draft path. `publicar_canal --channel
newsletter` remains as the manual immediate-send fallback (no draft).

## Related

- ADR: `docs/decisions/0004-workflow-sollicituds-revisio.md`
- Post-mortems: `2026-05-19-workflow-sollicituds-redesigned.md`,
  `2026-05-20-smoke-side-effects.md`
- Policy: `docs/policies/identities.md`
- Modules: `comptes/models.py`, `comptes/views.py`,
  `comptes/notifications.py`, `comptes/management/`,
  `comptes/newsletter.py`, `comptes/newsletter_{utm,covers,meta}.py`,
  `web/api/compte_views/`, `web/api/staff/sollicituds_revisio.py`
