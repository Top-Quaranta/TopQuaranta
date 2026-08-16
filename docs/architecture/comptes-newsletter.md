# Weekly newsletter

> Split out of `comptes.md` (2026-08-12) for the docs-size ceiling
> (Rule 3). The subscriber model (`PerfilUsuari.vol_newsletter`),
> auth flow and the rest of the comptes surface stay in `comptes.md`.

# Spec: docs/architecture/comptes.md

## Weekly newsletter (Step 2 rework, 2026-06-01)

`comptes/newsletter.py::send_top_newsletter` builds **one Global
newsletter per week** (no territorial editions). `_build_top_context`
assembles a recipient-independent context once per run:

1. **Header** — raster logo (`logo_email.png`) + "Setmana N · Top
   Global" + "Veure al navegador".
2. **Podi** — #1 hero (500 px cover) + #2-3 sub-cards.
3. **Editorial** — narrative paragraphs (Step 1β composer).
4. **Top 4-10** — uniform full-width list rows.
5. **CTA** · 6. **Territorials** (CAT/VAL/BAL #1 mini-cards) ·
   7. **Novetats** (2-3 releases) · 8. **Share** buttons ·
   9. **Footer** (unsubscribe + browser link).

Template `comptes/templates/comptes/email_newsletter_top.html` is
self-contained (dark `#060608` surface, no `email_base.html`;
`_trend_badge.html` renders the movement) and follows the
**Gmail-compatibility pattern** (2026-07-05; hybrid columns 2026-08-01),
every rule pinned by a `test_gmail_*`: fluid-hybrid 640 px container, inline
styles everywhere (`<style>` is enhancement only — Gmail can drop it),
`bgcolor` on structural cells + `meta color-scheme: dark` against inversion,
solid-hex borders, no `<a>` around a `<table>`, card surfaces on `<div>`s
(nested `<table>`s are shrink-to-fit in Gmail), columns that are full-width
`<div>`s by default with the row-forming `max-width` caps in `<style>`, and
no inline padding on a `width:100%` element.

**Name links (Slice 1 2026-06-08; Slice 2 2026-06-09).** Song titles
render in italic and link to `/canco/{slug}`; artist names render in bold,
and **every artist with a known slug — principal AND collaborators —**
links to `/artista/{slug}`. Slice 1 linked only the principal;
Slice 2 added a parallel `artistes_slugs` list to the shared payload
(`social/payload.py::build_top`, ADDITIVE — the social engine ignores it)
so collaborators link too. In the cards/list this is data-driven:
`_enrich_entry` reads `artistes_slugs` (back-compat fallback to
`[artista_slug]`) and emits `artistes_render` (`[{nom, url}]`, one URL per
artist with a slug) + `artistes_truncated` (mirrors the legacy 80-char
ellipsis budget so a 39-collaborator row stays bounded), rendered by the
`_nl_artistes.html` partial. In the **editorial prose** a
deterministic post-processor `newsletter_linkify.linkify_narrative(html,
name_map)` (NEVER an LLM) wraps the FIRST occurrence of each canonical
name: songs `<em><a>`, artists `<strong><a>`/`<strong>`. Rules:
case-sensitive exact match, longest-match-first with consumed spans,
Unicode word boundaries, offset-preserving apostrophe normalisation, walks
text nodes only and skips the interior of existing `<a>/<strong>/<em>`
(idempotent), escapes the matched display + href. The `name_map` is built
in `_build_top_context` from the entries (which carry the slugs) and
applied to BOTH the engine narrative and the injected/override narrative
(preview + send paths).

Helpers:
- **`newsletter_utm.build_newsletter_url(base, content, setmana)`** —
  every body link gets `utm_source=newsletter`, `utm_medium=email`,
  `utm_campaign=top_<setmana>_global`, `utm_content=<block>` (`podi_1`,
  `top_4`, `cta_top`, `territorial_cat`, `novetat_1`, …).
- **`newsletter_covers.album_cover_url(deezer_id, mida)`** — local JPG
  at `/portades/album/<id>-{250,500}.jpg` (filesystem check via
  `ingesta.portades.manager`, no network) else the committed
  placeholder.
- **`newsletter_covers.ensure_cover_downloaded(deezer_id, source_url)`**
  — called from `_build_top_context` for every cover slot BEFORE
  composing: a missing local JPG is pulled synchronously via the SAME
  portades pipeline (`manager.download_and_convert`) — self-hosting
  only, no Deezer hotlink in the email. Best-effort: never raises; no
  `source_url` → placeholder. Closes the 2026-06-07 gap (Rosalía's #1
  showed the logo: the nightly cron had never generated its cover).
- **`newsletter_meta.trend_indicator(pos, pos_anterior, is_return)`** —
  ↑N / ↓N / → / DEBUT / TORNA (a13) with mm-design colours; deltas from
  `payload.build_top`'s `posicio_anterior` (no extra query).
- **`newsletter_meta.derive_subject(hero, week)`** — short editorial
  subject (≤60 chars) from a per-scenario_code phrase bank.

Raster assets (email clients don't render SVG) are committed PNGs
under `web/static/web/img/newsletter/` (`cover_placeholder.png` 500×500
ink + white logo; `logo_email.png` header mark), regenerable run-once
via `manage.py generar_assets_newsletter` (via `social.svg_assets`).

### Opt-out review flow (2026-06-07)

The subscriber newsletter is sent through a **review draft**. The text
is produced by a **cloud routine** (set up separately, in the UI) with
the narrative engine as fallback (`font` = `llm` vs `motor`). Model
`comptes.NewsletterDraft` — `unique(tipus, territori, setmana)`,
`estat` ∈ `pendent`/`enviat`/`cancellat` (NO "approved": `pendent` =
will send), `font`, `editat`.

0. **Cloud routine (token-authed, `web/api/newsletter_routine.py`)** —
   two narrow endpoints, authed by a static bearer
   `settings.NEWSLETTER_ROUTINE_TOKEN` (from the server env, NOT a staff
   session; `HasNewsletterRoutineToken` permission, blank token denies
   all):
   - `GET /api/v1/newsletter-routine/brief/` — grounded weekly brief
     (`comptes.newsletter_brief.build_brief`): context (week, Global, real
     top age); the **full top-40** in `top40` (movement, `can_call_new`
     via the freshness gate `is_verified_recent_release`, first-appearance
     with the week-1-birth vs genuine-debut distinction, per-artist top
     history); **group facts for all 40** in `fets_grup` (origin
     municipi/comarca/territori, collaborators + their origin only when
     known, release date, plus a `compromis_llengua` advisory flag —
     `te_obra_no_catala` / `n_cancons_desvinculades` from
     `desvincular_canco` rejections, a name-joined proxy for "has
     non-Catalan work"; see `brief.notes`); `fets_destacats`, up to
     `FETS_DESTACATS_K` (8) distinct-subject detector scenarios from
     `detect_all` + `select_slots` (each `{code, severity, data,
     freshness_blocked}`); `actualitat` (the 6-8 most recent VilaWeb RSS
     headlines so the voice picks by weight, best-effort), and a separate
     LOW-CONFIDENCE section with Last.fm tags for the top-5. The expansion
     (2026-06-08) is strictly **additive**: `top10` is an alias of
     `top40[:10]`, `fets_grup_top5` of `fets_grup[:5]`, and `fet_lider` of
     `fets_destacats[0]` (`detect_all[0]`), all byte-identical to their
     pre-expansion shape, so the token contract never breaks. Origin +
     collaborators are prefetched/batched (constant query budget, no N+1
     across the 40 rows). Returns `{"status": "not_ready"}` when the
     week's top isn't consolidated (same anti-stale guard). Accepts an
     optional `?setmana=<iso Monday>` (2026-06-08) for a specific week;
     absent → this week (production path unchanged). Also carries
     **`editorial_veu`** (2026-06): the staff-editable editorial-voice
     prompt, read from `ConfiguracioGlobal.editorial_veu` (a `TextField`,
     editable from the Configuració panel via reflection — no bespoke UI).
     Blank by default, so the routine falls back to its own default voice;
     the repo never imposes a voice. Top-level key, after `context`.
   - `POST /api/v1/newsletter-routine/esborrany/` — upsert THIS week's
     draft (`subject` + `narrative_html`, `font=llm`, `estat=pendent`).
     Idempotent; **can never** set approved/sent (any non-`pendent`
     `estat` rejected; an already `enviat`/`cancellat` week is terminal →
     409). It reads/leaves only; it never sends. On a successful upsert it
     emails `settings.ADMINS` — plus, when set, the render-testing
     address `ConfiguracioGlobal.newsletter_desti_prova` (blank default =
     ADMINS only, byte-identical; NEVER used for the subscriber send) —
     the **full newsletter preview** (`notify_admins_draft_preview`,
     best-effort, shared `render_newsletter_preview`), plus an admin-only
     management block (link to `/staff/social/esborrany` to edit or
     cancel; added only when `gestio_url` is set, so the subscriber copy
     never carries it). Deliverability headers (`List-Id`,
     `List-Unsubscribe`, `Auto-Submitted`) keep the automated mail out of
     spam. Every parada/error (not_ready, 400, 409) returns before the
     notify, so no mail fires on those paths.
1. **Saturday 16:00 — `generar_esborrany_newsletter` (engine fallback)**:
   composes `subject` + `narrative_html` via `newsletter.build_draft_text`
   (wraps `_build_top_context`, side-effect-free — no `mark_used`),
   persists a `pendent` draft **only if none exists for the week**
   (idempotent), emails staff a link to `/staff/social/esborrany`; when
   `newsletter_desti_prova` is set it ALSO sends the full rendered
   preview to that address only. Runs
   LATE (16:00) so the routine has had its turn first; if the routine
   failed, the engine still leaves a draft. An **anti-stale guard**
   refuses to generate unless the TopSetmanal for THIS week
   (`date.today() − weekday`) already exists.
   **On-demand generation** (2026-06-08, staff): `POST
   /staff/newsletter/esborrany/generar/?setmana=` runs this same engine
   seam for any chosen consolidated week (guards: consolidated-only;
   never clobbers a terminal/edited draft → 409; never sends), and `GET
   /staff/newsletter/setmanes/` lists the consolidated weeks + a live
   can-generate indicator. Surfaced in the SPA at the first-class
   Newsletter channel view (`/staff/social/newsletter`).
2. **Review** — staff endpoints (`web/api/staff/newsletter.py`, IsStaff):
   `GET /staff/newsletter/esborrany/` (draft + the live top it will ship
   with, to spot mismatches + the Sunday send date), `PATCH` (edit
   subject/narrative → `editat=True`, only while `pendent`), `POST
   …/cancellar/` (→ `cancellat`), `POST …/preview/` (full email HTML via
   `newsletter.render_newsletter_preview` — same `_build_top_context` +
   template as the send, honouring live editor overrides; render-only, no
   side effects). SPA page `NewsletterDraftPage` shows a faithful
   full-newsletter preview in a sandboxed iframe (no scripts), debounced
   on edits, with the list + real covers (logo fallback) as the
   subscriber sees.
3. **Sunday 10:00 — `enviar_newsletter`**: gated by
   `ConfiguracioGlobal.pot_publicar_tipus("newsletter", "top_ppcc")` —
   the three distribution gates (master + per-channel + the
   `MatriuPublicacio` cell; see `docs/architecture/social.md`), so an
   off matrix cell stops the send too; reads the week's
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

### Newsletter → Comunitat bridge (additive, gated)

A staff action can mirror a `NewsletterDraft` into a PUBLIC community
`Publicacio`, authored by the `admin` pseudo-user. It is **additive and
off by default**, gated by `ConfiguracioGlobal.newsletter_publicacio_pont_actiu`.

- Model link: `NewsletterDraft.publicacio` (nullable `OneToOneField` →
  `Publicacio`, `SET_NULL`, `related_name="newsletter_origen"`). Records
  the mirror so the action is **idempotent** (a draft maps to ≤1 post).
- Service: `comptes/community_bridge.py::publicar_draft_a_comunitat(draft)`.
  Raises `PontDesactivat` while the gate is off. Creates ONLY a `Publicacio`
  row (`visibilitat=publica`, `estat=publicat`) — **no email, no social
  distribution, no newsletter send**.
- Endpoint: `POST /api/v1/staff/newsletter/esborrany/publicar-comunitat/`
  (`web/api/staff/newsletter.py::esborrany_publicar_comunitat`) — 409 while
  the gate is off; staff button in `NewsletterDraftEditor.jsx`.
- Body: the draft's `narrative_html` is converted to **markdown**
  (`community_bridge._html_to_markdown`, via the `markdownify` dependency) and
  stored in `Publicacio.cos`. The feed renders `cos` with `react-markdown` +
  `remark-gfm` (never raw HTML) and previews via `stripMarkdown`, so markdown
  is the right shape. The service PRESERVES images (`![alt](url)`) and links
  (`[text](url)`), absolutises relative URLs (links AND images) to
  `PUBLIC_SITE_BASE`, and collapses blank-line runs; the result contains no
  raw HTML. The shared render (`web-react/src/components/Markdown.jsx`)
  sanitizes URL schemes (`safeUrl`: http/https/mailto only, never
  javascript:/data:) + lazy-loads images, so this widened render is safe for
  EVERY `Publicacio` (non-staff public posts still pass the moderation queue).

## Qui rep la newsletter

`comptes.newsletter.destinataris()` és la definició única: `PerfilUsuari.
vol_newsletter=True` **i** `Usuari.is_active=True`, sense correu buit.

L'`is_active` no és cosmètic: el registre marca `vol_newsletter` de
seguida, mentre el compte encara està inactiu esperant la confirmació del
correu. Sense el filtre, qualsevol podia donar d'alta l'adreça d'un
tercer i eixa adreça rebia correu sense que el seu amo hi haguera
consentit mai — a més de gastar el pressupost de Brevo (300/dia) en
adreces no confirmades. El comptador del panell
(`web/api/staff/analytics.py::newsletter_audience`) ja filtrava així, o
siga que **el número que veies i la llista que s'enviava no coincidien**
(trobat el 2026-08-15; aleshores, 1 destinatari i cap sense confirmar).

És una funció i no una consulta escrita dins de l'enviament perquè el
comptador i l'enviament es puguen provar contra la mateixa definició en
lloc de contra una còpia.
