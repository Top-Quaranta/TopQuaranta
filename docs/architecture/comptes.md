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
- Every Django-rendered auth page extends `comptes/_base_auth.html`.
  Since 2026-08-12 the shell mirrors the **rd redisseny** (page-bg
  `#060608` + brand glows, liquid-glass card, Anton titles, Instrument
  Serif kickers, Bricolage body, pill buttons) and replicates the SPA
  header (`rd/Header.jsx`): real mono brand logo — `{% include %}`d
  inline from `web-react/src/assets/logo-topquaranta-rect-mono.svg`
  via a TEMPLATES dir added in `settings/base.py` (single source, no
  copy; see `docs/architecture/brand-logo.md`) — plus static nav
  pills and the account icon. Mobile (<900px) hides the nav (no
  burger: auth pages are single-purpose).

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
  login history). Throttled 3/h. **El contingut és el contracte**, no
  només que arribe un adjunt: fins al 2026-08-15 l'única prova
  comprovava que el correu portava un fitxer acabat en `.json` i prou,
  així que un export podia eixir amb `audit_log_sobre_meu` buit —
  `rgpd.py` s'empassa l'`ImportError` d'axes i emet `[]`— i tot verd.
  Això és una mala resposta a una petició legal: sembla «no tenim res»
  quan de fet és «no ho hem mirat». Fixat a
  `web/tests/test_export_rgpd_contingut.py`, que a més comprova el
  revés: el filtre per `target_id` no pot donar-li a algú l'historial de
  moderació d'una altra persona.
- `/compte/baixa-newsletter/` — token-signed unsubscribe (token
  expires after 1 year, May-2026 audit fix). Throttled 10/min.
- `/compte/esborrar-sollicitud/` — self-delete confirmation
  email flow. Throttled per `_AccountDeleteThrottle`.

## Weekly newsletter — see `comptes-newsletter.md`

The newsletter pipeline (draft generation, covers, UTM, send command,
Gmail-safe hybrid columns) lives in
**`docs/architecture/comptes-newsletter.md`** (split 2026-08-12 for
the docs-size ceiling).

## "Has entrat al top" manager alert (Fase 2 D1, 2026-06)

A SEPARATE notification path from scoring: the `enviar_avisos_top`
management command READS the already-computed weekly PPCC (`Global`)
`TopSetmanal` and emails the verified managers of any artist that NEWLY
enters the top. "New" = a cançó in this week's top whose `canco_id` was
absent last week (reuses `web.api.top_views._prev_week_positions`; never
touches ranking).

- **Audience:** `UserArtista` rows with `verificat=True`, `estat=aprovat`,
  an active user with an email, and `PerfilUsuari.vol_avis_top=True`
  (default True, opt-OUT — it's a relevant service alert, not marketing).
- **Idempotency:** one `AvisTopEnviat(artista, setmana)` row gates each
  artist+week (unique constraint), so re-runs never double-send.
- **Safety:** DRY-RUN BY DEFAULT; `--send` actually emails. `--setmana`
  targets a specific Monday (defaults to the latest PPCC week).
- **Opt-out:** signed-token unsubscribe at
  `/api/v1/compte/baixa-avis-top/` (salt `avis-top-baixa`, 1-year token,
  RFC 8058 one-click), mirroring the newsletter unsubscribe.
- Make-or-break (investigation 2026-06): only ~3 artists have a reachable
  verified-manager email today, so this reaches a tiny audience until
  more managers verify.

## Community safety (Slice A, 2026-06)

Trust-and-safety prerequisites before opening the community to public
traffic. All additive.

- **Models** (`comptes/models.py`): `BloqueigUsuari` (blocker, blocked,
  unique pair), `DenunciaUsuari` (reporter + one of four nullable target
  FKs usuari/publicacio/comentari/missatge + `tipus` + `estat`
  pendent/revisada/desestimada), and a new `Missatge.ocult` flag
  (hidden-by-moderation messages are never served). `PerfilUsuari` gains
  `accepta_dm` (True = anyone can DM, False = nobody; the admin support
  inbox bypasses it).
- **Member endpoints** (`web/api/comunitat_views/seguretat.py`):
  `POST /comunitat/bloquejar/`, `/comunitat/desbloquejar/` (idempotent),
  `POST /comunitat/denunciar/` ({tipus, target_pk, motiu}).
- **DM gate** (`web/api/comunitat_views/missatgeria.py::_dm_block_reason`):
  `missatge_crear` returns 403 when a block exists in EITHER direction or
  the recipient has `accepta_dm=False`. The inbox + thread queries
  filter `ocult=False`, so a hidden DM disappears for both parties.
- **Staff moderation** (`web/api/comunitat_views/staff_moderacio.py`):
  `GET /staff/denuncies/` (report queue) + `POST /staff/denuncies/<pk>/
  resoldre/` ({action: revisar|desestimar, ocultar?}). With
  `ocultar=true` a reported DM gets `ocult=True` and a reported
  publication is unpublished.

## Directory matching (Slice B, 2026-06)

`PerfilUsuari` gains matching fields (additive): `busca` (comma-separated
tokens from `BUSCA_CHOICES`: grup/colaboradors/cantant/instrumentista/
productor), `generes` (comma-separated style tags) and `nivell`
(`NIVELL_CHOICES` incl. `aspirant` = "vull ser músic"). The directory
(`web/api/comunitat_views/perfil.py::directori`) filters by `q`, `rol`,
`obert`, `territori`, `instrument`, `genere`, `busca`, `nivell` so staff
and members can resolve queries like "guitarristes a València de rock que
busquen grup". Tokens are stored comma-joined and matched with
`__icontains`.

## Related

- ADR: `docs/decisions/0004-workflow-sollicituds-revisio.md`
- Post-mortems: `2026-05-19-workflow-sollicituds-redesigned.md`,
  `2026-05-20-smoke-side-effects.md`
- Policy: `docs/policies/identities.md`
- Modules: `comptes/models.py`, `comptes/views.py`,
  `comptes/notifications.py`, `comptes/management/`,
  `comptes/newsletter.py`, `comptes/newsletter_{utm,covers,meta}.py`,
  `web/api/compte_views/`, `web/api/staff/sollicituds_revisio.py`

## Limitadors de ritme: el scope va a la classe, no a la vista

Els sis limitadors (`auth_login`, `data_export`, `newsletter_unsubscribe`,
`feedback_crear`, `account_delete`, `dm_send`) i el de registre hereten
`web.api.utils.ScopedThrottle`, **no** el `ScopedRateThrottle` de DRF.

El motiu és que aquell llig el scope de la *vista*
(`view.throttle_scope`) i, si no hi és, **deixa passar la petició sense
comptar-la**:

```python
self.scope = getattr(view, self.scope_attr, None)
if not self.scope:
    return True
```

Declarar `scope = "..."` a la subclasse no serveix de res: eixe mètode
el sobreescriu a cada crida. Com que cap vista definia `throttle_scope`,
els sis limitadors van estar inerts des que es van afegir (auditoria de
maig del 2026) fins al 2026-08-15: connectats, invocats a cada petició, i
sense limitar res. El scope `registre` ni tan sols tenia classe.

`ScopedThrottle` llig el scope de la classe i fa la clau de cache igual
que DRF (per usuari si està autenticat, per IP si no). El guardià és
`web/tests/test_throttles.py`, que a més falla si algun limitador torna a
heretar de `ScopedRateThrottle`.

### El repte de 2FA no és de DRF

`dos_fa_verificar` és una vista de Django plana, així que cap limitador
de DRF hi arriba: el scope `auth_2fa` estava configurat des del maig del
2026 i **no s'aplicava enlloc**. Era, precisament, l'única pantalla del
projecte que accepta codis de recuperació d'un sol ús en bucle.

Des del 2026-08-16 el limitador és `comptes/ratelimit.py::excedeix_limit`,
una finestra fixa comptada al cache compartit que llig el ritme del mateix
`DEFAULT_THROTTLE_RATES`, de manera que els números viuen en un sol lloc.
Superar-lo torna **429** amb la mateixa pantalla i un missatge clar.

Dues decisions que val la pena conéixer:

- **La identitat és l'usuari, no la IP.** Qui arriba a esta pantalla ja ha
  passat la contrasenya, així que algú amb una galeta robada és *un*
  usuari per moltes IPs que rote.
- **Falla obert.** Si el cache peta, es deixa passar. La contrasenya
  continua sent necessària per a arribar ací, i una caiguda del cache no
  pot convertir-se en un bloqueig del compte — però implica que el
  limitador és tan disponible com el cache.
