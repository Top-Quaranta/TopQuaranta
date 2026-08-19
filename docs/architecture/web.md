# web — invariants

<!-- The Django surface that survives the SPA: the DRF API under
`/api/v1/` (public + staff), session/CSRF auth glue, the SEO layer
(dynamic rendering for bots, sitemaps, IndexNow, OG cards) and the
Django-side error pages and RSS feeds. -->

## Invariants

### Auth, permissions, throttles
- **The SPA authenticates with Django's own session cookie; the CSRF token is planted by `GET /api/v1/auth/me/` (`@ensure_csrf_cookie`) and echoed back as `X-CSRFToken` by `web-react/src/lib/api.js`.** Why: axes + django-otp keep working untouched. Guarded by: `web/tests/test_auth_login.py::test_login_succeeds_and_opens_a_session`.
- **`IsStaff` (`web/api/staff/_common.py`) = authenticated AND `is_staff` AND OTP-verified — but the OTP clause only applies when django-otp's middleware is installed (`user.is_verified` present).** Why: test settings without OTP must still exercise staff endpoints; a verified session never promotes a non-staff user. Guarded by: `web/tests/test_staff_otp_gate.py` (all five tests).
- **Every per-endpoint throttle subclasses `web.api.utils.ScopedThrottle` and declares `scope` on the class; the scope has a rate in `DEFAULT_THROTTLE_RATES`.** Why: DRF's `ScopedRateThrottle` reads `view.throttle_scope`, which no `@api_view` sets, and *allows everything* when absent — the six limits were inert May→2026-08-15. Guarded by: `web/tests/test_throttles.py::test_no_throttle_relies_on_a_view_attribute_nobody_sets`, `::test_every_throttle_declares_a_scope_with_a_configured_rate`.
- **Any `/api/v1/` endpoint may return 429; adding or tuning a limit is not a version bump.** Guarded by: `test_throttles.py::test_the_login_throttle_stops_credential_guessing`, `::test_the_login_throttle_is_per_ip`.
- **Login lookup is by email, case-insensitive; unknown email and wrong password are the same 401.** Guarded by: `test_auth_login.py::test_an_unknown_email_is_401_not_404`.

### Caching
- **`cache_for_anon(ttl)` caches rendered bytes per `path?query` in `pagecache` for anonymous requests only; authenticated requests always recompute.** Why: staff must see their own edits at once. TTLs are per call site (300 s ranking/map/albums/home-stats, 3600 s home-destacats, 60 s artistes — see the decorators). Pair with `@condition` for ETag/304. No dedicated test; the decorator sits below `@api_view` so `request.user` is DRF's.

### Staff writes
- **`ConfiguracioGlobal` reads mask any field whose name matches `_token|_secret|_password|_key|_apikey`, and the audit diff records `***`.** Why: the model is reflection-iterated, so a future secret field must not leak by default. Guarded by: `web/api/staff/configuracio.py::_is_secret_field` (no test — add one if you touch it).
- **Image uploads are validated by Pillow's `img.format` in `web/api/_image_pipeline.py`, never by the browser `content_type` alone.** Guarded by: `web/tests/test_pujada_imatges.py::test_a_lying_content_type_does_not_get_a_file_through`.
- **Reject motius are the three action-based codes in `music.constants.MOTIUS_REBUIG` (`desvincular_canco` → `rebutjar_canco`: `verificada=activa=False`, row kept; `desvincular_album` → `rebutjar_album`: deletes unverified cançons + `Album.descartat=True`, Deezer links untouched; `desvincular_artista` → `rebutjar_artista`: deletes unverified cançons, clears `ArtistaDeezer`, discards albums, forces `aprovat=False, pendent_review=True` regardless of MBID, deactivates orphan collab songs). Labels name the action only — the cause lives here, not in the choices.** Guarded by: `music/tests/test_services.py::TestRebutjarCanco`, `::TestRebutjarAlbum`, `::TestRebutjarArtista`, `::TestOrphanPendents`; migration `music.0083_rename_motius_to_actions`.
- **Approving a pendent requires ≥1 `ArtistaDeezer` (Deezer, not "Deezer or MBID"); a Deezer id owned by another artista is 409 with `owner_pk`; the `aprovat` flip is the last write of one transaction.** Guarded by: `web/tests/test_deezer_gate.py`.
- **`descartar` tombstones (`aprovat=False, pendent_review=False`), never deletes.** Why: the Last.fm similar resolver otherwise re-creates the pendent (resurrection loop). Guarded by: `web/tests/test_pendent_descartar.py::test_descartar_songless_placeholder_tombstones_not_deletes`.
- **Staff user writes refuse self first, then other staff; 2FA reset wipes TOTP *and* static devices; hard delete leaves a `StaffAuditLog` row with the vanished email/pk.** Guarded by: `web/tests/test_staff_usuaris_escriptures.py`.
- **`/staff/social/toggle/` requires `channel` (`global` or a channel name); there is no default.** Guarded by: `web/tests/test_social_master_switch.py::test_toggle_missing_channel_is_400`.
- **Manual YouTube video on `PATCH /staff/cancons/<pk>/`: store-and-trust (format only, no quota spent), and the destination depends on what the song has — no Art Track → it becomes `youtube_video_id` (`MATCH_MANUAL`); already has one → an extra `CancoYouTubeVideo` lane, never a replacement. A channel or playlist URL is a 400 naming the mistake. Setting a video also sets `youtube_revisat`; lanes are not removable (discovery re-creates them).** Why: the daily report hands out video searches, so the answer needs somewhere to land, and overwriting the Art Track would drop the audience already measured. Guarded by: `web/tests/test_staff_cancons_youtube_manual.py`.

### RGPD
- **`exportar-dades` content is the contract: account, perfil, gestió, propostes, feedback, community rows, `StaffAuditLog` rows targeting the user, axes login history (block always present, `[]` when axes absent) — and never another user's moderation history.** Guarded by: `web/tests/test_export_rgpd_contingut.py`.
- **Newsletter and avis-top unsubscribe tokens are `signing` tokens with `max_age` = 1 year (salts `newsletter-baixa`, `avis-top-baixa`); GET and POST both accepted (RFC 8058).** Guarded by: `comptes/tests/test_auth_flow.py::NewsletterTokenExpiryTest`, `web/tests/test_legal_endpoints.py::test_baixa_avis_top_token_older_than_a_year_is_refused`, `::test_baixa_newsletter_rejects_token_for_other_salt`.

### SEO
- **Dynamic rendering: Caddy routes UAs matching `@bot` (`deploy/Caddyfile`) for public paths to Django SSR views; humans get `dist/index.html`. Every SSR response carries `Vary: User-Agent`.** Why: same URL, different HTML — without Vary an intermediate cache crosses them. `analytics.bots.BOT_UA_MARKERS` must mirror the regex (`analytics/tests/test_bots.py::test_python_markers_match_caddyfile_regex`).
- **`web/seo/meta.py` is the single source of `<head>` metadata for SSR templates and the SPA `SeoHead` (`/api/v1/seo/<entity>/<slug>/`).** Guarded by: `web/tests/test_seo.py::test_seo_api_endpoint_for_helmet`.
- **Indexability: unapproved/missing artiste → 404; approved artiste with no verified active cançó → 200 + `noindex,follow` thin page (`_artista_has_indexable`), shared with the sitemap; album needs approved parent + `descartat=False`; cançó `verificada=True, activa=True`; comarca <3 artistes and dècada <5 cançons → 404; top-històric 404 without `TopSetmanal` rows. 404, not 410, when indexability is lost (may come back).** Guarded by: `test_seo.py::test_artista_seo_404_when_unapproved`, `::test_artista_thin_200_noindex_generated_desc`, `::test_sitemap_excludes_thin_artista`, `::test_album_seo_404_when_descartat`, `::test_canco_seo_404_when_unverified`, `::test_decada_thin_404`, `::test_top_historic_no_data_404`.
- **`/sitemap.xml` is an index of sub-sitemaps, each capped at 50 000 URLs (`limit = 50_000`); `lastmod` from `updated_at`.** Guarded by: `test_seo.py::test_sitemap_index_lists_all_sections`.
- **IndexNow is fire-and-forget: `web/seo/indexnow.py` logs failures and never raises; called synchronously from `pendent_aprovar`.** Why: a Bing outage must not block approval. Guarded by: `music/tests/test_services.py` mocks `requests.post` throughout (`_ix` fixtures).
- **Editorial prose (`LandingProsa`) is rendered with `linebreaks`, never `safe`; the routine token (`landing-routine`, `newsletter-routine`) is a static bearer and a blank setting denies all.** Guarded by: `test_seo.py::test_landing_routine_requires_token`, `web/tests/test_newsletter_routine.py::test_blank_setting_denies_even_with_header`.
- **RSS feeds honour `ConfiguracioGlobal.pot_publicar("rss")` (master AND channel) and return 503 when off.** Code: `web/feeds.py`.

### Versioning
- **`/api/v1/` bumps to `/api/v2/` only on a backward-incompatible response change; additive fields/params/endpoints never bump; v1 stays live 6 months after v2 (audit access logs before removal).** `X-API-Version` header is stamped by `web/api/middleware.py` — **untested**.

## Traps
- Multi-line `{# … #}` template comments leak in Django (single-line only). The SEO `_base.html` comment shipped to every bot page (2026-05-31). Guarded by: `test_seo.py::test_no_template_comment_leaks_in_seo_pages`, `comptes/tests/test_newsletter_template.py::test_no_template_comment_leaks`.
- `cache_for_anon` is LocMem per gunicorn worker: a stale-looking value on one worker and fresh on another is expected, not a bug.
- `IsStaff` fails **open** on the OTP clause when django-otp is not installed; never remove `OTPMiddleware` from production settings.
- Registration rate-limit is a plain-cache limiter in `comptes/views.py`, not a DRF throttle; the 2FA challenge has its own (see `comptes.md`).

## Where the detail lives
- code: `web/api/` (`utils.py`, `auth_views.py`, `staff/`, `compte_views/`, `comunitat_views/`, `_image_pipeline.py`, `middleware.py`), `web/seo/`, `web/sitemaps.py`, `web/feeds.py`, `music/services.py`, `deploy/Caddyfile`
- archived narrative: `docs/archive/architecture/{web,seo,staff,staff-api,api-versioning}.md`
- ADRs: 0004 (workflow sol·licituds), 0015 (IG collaborator invitations)
