# comptes — invariants

<!-- User identity and everything hung off it: registration/activation,
2FA, self-deletion, the verified-manager (gestor) relationship, the
community (profiles, directori, DMs, moderation), transactional
notifications and the weekly newsletter draft → send pipeline. -->

## Invariants

### Account lifecycle
- **Registration creates an inactive account and always renders the same "check your email" page, whether or not the address exists.** Why: anti-enumeration. Activation token hashes `is_active`, so a link dies once used. Guarded by: `comptes/tests/test_auth_flow.py::RegisterEndpointTest::test_register_existing_email_does_not_leak`, `web/tests/test_legal_endpoints.py::test_register_records_consent`.
- **Staff whose session is not OTP-verified are bounced full-page from `AdminRoute` to `/compte/2fa/verificar` (a plain Django view). Its rate limit is `comptes/ratelimit.py::excedeix_limit` — per *user*, not IP, reads `auth_2fa` from `DEFAULT_THROTTLE_RATES`, and fails OPEN on cache error by design.** Why: DRF throttles never reach a plain view, so this screen (the one accepting single-use backup codes in a loop) was unlimited until 2026-08-16; a cache outage must not lock accounts. Guarded by: `comptes/tests/test_limit_2fa.py` (`::test_the_limit_is_per_user_not_global`, `::test_a_broken_cache_does_not_lock_people_out`).
- **Self-delete is a token-signed email link: GET only confirms, POST deletes; single-use; staff accounts are refused even with a valid token.** Guarded by: `comptes/tests/test_esborrar_compte.py`.
- **`consent_newsletter_at` is stamped on the False→True transition of `vol_newsletter` (registration or profile PATCH), never overwritten.** Why: RGPD audit trail. Code: `web/api/compte_views/dashboard.py::perfil`.

### Gestor (verified manager)
- **A user is gestor of an artista iff `UserArtista.verificat=True AND estat=aprovat`. The predicate is duplicated in `web/api/auth_views.py::_profile` (for `verified_artist_pks`) and `web/api/compte_views/propostes.py::_gestor_check`; change both.** `solicitud_rebutjar` flips `verificat=False`. Guarded by: `web/tests/test_gestor_artista_portal.py::test_non_manager_forbidden`.
- **All `comptes/notifications.py` senders are best-effort: mail failure logs and never blocks the business write; admin fan-outs go to every active `is_staff` user and skip silently when there is none.** Guarded by: `comptes/tests/test_notifications.py::test_admin_notify_skips_when_no_staff`.
- **Retroactive/one-shot mailers are idempotent via a stamp (`UserArtista.email_aprovacio_at`, `AvisTopEnviat(artista, setmana)`) and dry-run by default.** Guarded by: `comptes/tests/test_notificar_gestors_retroactiu.py::test_already_notified_user_is_skipped`, `comptes/tests/test_avisos_top.py::test_send_emails_and_is_idempotent`.

### Community
- **The `admin` pseudo-user (`settings.ADMIN_INBOX_USERNAME`, seeded by `comptes.0016`) is always DM-reachable; a DM to it fans out by email to every active staff user plus the admin mailbox, ignoring the pseudo-user's own opt-out.** Guarded by: `comptes/tests/test_admin_inbox.py::test_dm_to_admin_fans_out_to_all_active_staff`, `::test_dm_to_admin_with_no_active_staff_still_hits_admin_mailbox`.
- **DM is refused (403) on a block in either direction or `accepta_dm=False`; messages with `ocult=True` are never served to either party.** Guarded by: `comptes/tests/test_comunitat_seguretat.py::test_block_prevents_dm_both_directions`, `::test_hidden_dm_not_served`.
- **Directori: non-staff see `visible_directori=True` only; staff see every active profile with the flag exposed per row; inactive users are excluded for everyone. Discoverability is the effective DM gate — `missatge_crear` accepts any user id.** Guarded by: `comptes/tests/test_directori_staff_visibility.py`.
- **The newsletter→community bridge (`comptes/community_bridge.py`) is OFF by default (`ConfiguracioGlobal.newsletter_publicacio_pont_actiu`), idempotent via `NewsletterDraft.publicacio`, produces markdown with no raw HTML, and sends nothing.** Guarded by: `comptes/tests/test_community_bridge.py` (`::test_flag_defaults_off`, `::test_never_sends_email`, `::test_idempotent`).

### Newsletter
- **`comptes.newsletter.destinataris()` is the single definition of who is mailed: `vol_newsletter=True AND is_active=True AND email != ""`; the staff audience counter uses the same function.** Why: registration sets `vol_newsletter` before the address is confirmed — without `is_active` anyone could subscribe a third party. Guarded by: `comptes/tests/test_newsletter_destinataris.py` (both tests).
- **Draft state machine `NewsletterDraft.estat ∈ {pendent, enviat, cancellat}` (`pendent` = will send; no "approved"). Only the Sunday `enviar_newsletter` sends, gated by `pot_publicar_tipus("newsletter","top_ppcc")` (master + channel + matrix). Terminal or `editat=True` drafts are never clobbered by the routine or the on-demand generator (409); the LLM routine can only upsert `pendent`.** Guarded by: `comptes/tests/test_newsletter_draft.py::test_send_cancelled_does_not_send`, `::test_send_blocked_by_master_switch`, `::test_send_already_sent_is_idempotent`; `web/tests/test_newsletter_ondemand.py::test_generar_does_not_clobber_edited_draft`, `::test_generar_creates_motor_draft_and_never_sends`; `web/tests/test_newsletter_routine.py::test_post_rejects_non_pendent_estat`.
- **`newsletter_desti_prova` receives previews only; it never enters the subscriber send.** Guarded by: `test_newsletter_draft.py::test_desti_prova_never_reaches_subscriber_send`.
- **Covers are pre-downloaded before compose (`newsletter_covers.ensure_cover_downloaded`, same portades pipeline, self-hosted, never raises); a missing cover falls back to the committed placeholder — no Deezer hotlink in the email.** Guarded by: `comptes/tests/test_newsletter_cover_predownload.py::test_never_raises_on_download_error`.
- **Name links: every artist with a slug (principal AND collaborators) and every song title link into the site; prose linking is the deterministic `newsletter_linkify.linkify_narrative` (first occurrence, longest-match-first, idempotent, skips existing anchors, escapes href) — never an LLM.** Guarded by: `comptes/tests/test_newsletter_linkify.py::test_idempotent`, `comptes/tests/test_newsletter_namelinks.py::test_preview_links_collaborator_in_prose_and_cards`.
- **The template is Gmail-safe hybrid: 640 px fluid container, every rule inline (`<style>` is enhancement only), `bgcolor` on structural cells, columns are full-width `<div>`s with `max-width` caps only in `<style>`, card surfaces on `<div>`s not nested tables, no padding on a `width:100%` box, MSO ghost columns balanced for Outlook.** Guarded by: `comptes/tests/test_newsletter_template.py::test_gmail_*` (nine tests).

## Traps
- `test_gmail_*` pin the *technique*; a "small" template edit that adds inline padding to a full-width column breaks Gmail rendering silently in production — run the suite, don't eyeball.
- The 2FA limiter shares the DB-backed `default` cache across gunicorn workers on purpose; a per-process cache multiplies every limit by the worker count.
- `Missatge` notification fan-out relies on the pseudo-user being `is_staff=False`; if someone flags it staff it will also receive its own fan-out.
- `enviar_newsletter` rebuilds the list/covers from the FINAL top at send time — the reviewed draft only fixes subject + narrative (`test_send_uses_edited_text_and_rebuilds_list`).

## Where the detail lives
- code: `comptes/` (`views.py`, `tokens.py`, `ratelimit.py`, `notifications.py`, `newsletter*.py`, `community_bridge.py`, `management/commands/`), `web/api/auth_views.py`, `web/api/compte_views/`, `web/api/comunitat_views/`, `web/api/newsletter_routine.py`, `web/api/staff/{newsletter,solicituds,sollicituds_revisio,avisos_top}.py`
- archived narrative: `docs/archive/architecture/{comptes,comptes-newsletter}.md`
- ADRs: 0004 (workflow sol·licituds de revisió) · policy: `docs/policies/identities.md` · post-mortems: `2026-05-19-workflow-sollicituds-redesigned.md`
