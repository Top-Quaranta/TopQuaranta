# Social distribution

Five-channel weekly publication system: Instagram (feed + stories),
Mastodon, Bluesky, Telegram, Newsletter. Plus an RSS surface for
syndication and a static-PNG hosting path for Meta's media-fetcher.

> **Note (May 2026):** the system was refactored during the
> 2026-05-21 sprint. Post-mortem
> `2026-05-20-narrative-engine-collapsed.md` is **Resolved** by
> ADR-0006 (ordinals catalans), ADR-0007 (`@username` restituït a
> IG) i ADR-0008 (detectors a9–a12 + slot terciari). Post-mortem
> `2026-05-21-bluesky-silent-failures.md` és **Resolved** per
> ADR-0005 (timeout 180 s + retry 3×).

## Flow

```
cron (publicar_social or publicar_canal)
  ↓ social/payload.py             → {entries, hero_cover_url}  for top_*
                                    (entries/items carry album_deezer_id
                                     for the newsletter's local-cover lookup)
                                     {items}                    for nous_*
  ↓ social/captions.py
      compose_for_channel(channel, tipus, territori, setmana, entries)
        ↓ if tipus ∈ {top_ppcc, top_territorial}:
            social/narrative/scenarios.detect_all → 13 detectors a1-a13
            social/narrative/scenarios.select_slots → distinct-subject slots
            social/narrative/composers/<channel>.compose
              ↓ pick_phrase(hero, long, …)     via registry (anti-repeat)
              ↓ pick_phrase(secondary, medium, …)  slot[1] if distinct subject
              ↓ pick_phrase(tertiary, short, …)    IG-feed only, slot[2] if distinct
              ↓ for IG: `@handle` rewrite per ADR-0007
              ↓ top5_bank.pick_long / pick_short (ordinals per ADR-0006)
              ↓ hashtags_bank.build_hashtags
              ↓ cta_bank.pick_cta
        ↓ elif tipus ∈ {nous_albums, nous_singles}:  ← narrative novetats
            social/narrative/novetats.detect_novetats → n1-n4 + fallback
            social/narrative/composers/{nous_albums,nous_singles}.compose
          else: _legacy_for(channel, tipus, …)  ← IG-story / fallback
  ↓ social/renderer.py            → JPEG slides (q=90)
  ↓ social/<channel>_client.py    → publish
  ↓ social.SocialPost row         status ∈ {publicat, error, omes}
  ↓ StaffAuditLog                 audit trail
```

Both publish commands (`publicar_social`, `publicar_canal`) exit
**non-zero** (`CommandError`) when any slot ends in `error`, so `tq-run`
records `status=FAIL` and the watchdog alerts. Slots that published stay
`publicat` — partial failure is reported, not rolled back; `omes` skips
don't count. (Before 2026-07 they returned 0 on partial failure, so a
dead IG token went unnoticed for days — the invisible-outage incident.)

## Channels

| Channel | Module | Max chars | Mentions | Hashtag density |
|---|---|---|---|---|
| Instagram feed | `social/instagram_client.py` + `narrative/composers/instagram_feed.py` | 2 200 | `@handle` at caption text (ADR-0007) + `user_tags` via Graph API | 8-12 |
| Instagram story | same client, `composers/instagram_story.py` | short | plain | minimal |
| Mastodon | `social/mastodon_client.py` + `composers/mastodon.py` | 500 | plain name | 3-5 |
| Bluesky | `social/bluesky_client.py` + `composers/bluesky.py` | 300 | plain name | 2-3 |
| Telegram | `social/telegram_client.py` + `composers/telegram.py` | 1 024 | plain name | 3-5 |
| Newsletter | `composers/newsletter.py` | unbounded | plain name | — |

## Narrative engine

13 detectors run over the `TopSetmanal` for a given week and
territory (`social/narrative/scenarios.py`); `detect_all` returns
the scenarios sorted by severity desc and the composer turns the
headline beat into a caption. The full spec — distinct-subject slot
selection, the novetats engine, caption density, account matching +
top-5 dedup, territorial labels, the ADR-0006/0007/0008 behaviours
and the anti-repeat registry — lives in its own doc:

See **[`social-narrative.md`](social-narrative.md)**.

## Resolved regressions (2026-05-21 sprint)

1. **IG `@handle` restituït.** ADR-0007: composer d'IG reescriu
   `artista_nom` / `Scenario.data["artista"]` a `@handle` quan
   està disponible. Altres canals mantenen nom pla.
2. **`#N` → ordinals catalans.** ADR-0006: tots els bancs i
   detectors emeten ordinals (`1r`, `5è`) en lloc de `#N`.
3. **Bluesky timeout 60 s → 180 s + retry 3×.** ADR-0005: nou loop
   de reintents amb back-off (5 s, 15 s) i timeout per upload de
   blob ampliat a 180 s. `upload_blob` no retornarà silenciós; les
   excepcions reals (4xx) propaguen immediatament.

## Auth & identities

Vegeu `docs/policies/identities.md` for the rules. Token storage
per channel:

| Channel | Storage | Identity |
|---|---|---|
| Instagram | `.env::INSTAGRAM_ACCESS_TOKEN` + `social.InstagramAuth` row | TopQuaranta IG business account |
| Mastodon | `social.MastodonAuth` row | TopQuaranta instance app |
| Bluesky | `social.BlueskyAuth` row | `topquaranta.bsky.social` app password |
| Telegram | `social.TelegramAuth` row | `@topquaranta_bot` |
| Newsletter | `.env::EMAIL_HOST_PASSWORD` (Brevo SMTP) | `admin@topquaranta.cat` |

## Distribution gate — master + per-channel (2026-06-07)

Every publisher gates on the shared predicate
`ConfiguracioGlobal.pot_publicar(canal)` =
`distribucio_activa AND <canal>_actiu`:

- **`distribucio_activa`** — the master switch. The REAL global pause:
  False stops all six channels (IG, Mastodon, Bluesky, Telegram,
  newsletter, RSS). Default True (deploying changes nothing).
- **`<canal>_actiu`** — the per-channel switch (one each).

Consumers: `publicar_social` (`pot_publicar("instagram")`),
`publicar_canal` (`pot_publicar(channel)` for the four non-IG channels),
and the RSS feeds (`web/feeds.py` → `pot_publicar("rss")`, 503 when off).

The legacy Instagram-only per-slot rollout phase (`fase_distribucio` +
calendar `min_fase`) was **removed 2026-06**: prod sat at the final phase
(everything on), so removal was neutral. Per-slot day scheduling is fixed
by the calendar/cron (the matrix only gates on/off; the day is a
read-only indicator — see below).

**Distribution matrix — third gate (`MatriuPublicacio`, 2026-06).** On
top of the master switch and the per-channel switch sits a per-(canal ×
tipus) toggle: `ConfiguracioGlobal.pot_publicar_tipus(canal, tipus)` =
`pot_publicar(canal) AND MatriuPublicacio.actiu_per(canal, tipus)`. With
`actiu=False`, that channel does NOT distribute that content type that
week. The model lives in `ranking/models.py` next to
`ConfiguracioGlobal`; migration `0020` SEEDS one active row per (canal ×
tipus) actually published today (instagram/mastodon/bluesky/telegram ×
the four feed tipus, plus newsletter × top_ppcc — 17 rows, all on), so
the default is byte-identical to before. A MISSING row is fail-open
(True) — the matrix only ever blocks via an explicit off row.
Conceptual model: only the five PUSH channels are governed
(instagram, mastodon, bluesky, telegram, newsletter); the website
generates and shows the top regardless and is never gated, and RSS
stays on its own `rss_actiu` switch. Consumers: `publicar_social` (per
slot, `instagram × tipus`), `publicar_canal` (per slot,
`channel × tipus`), and
`enviar_newsletter` (`pot_publicar_tipus("newsletter", "top_ppcc")` —
off ⇒ the Sunday send does not run). An off cell records the slot as
`omès` so it shows inactive in the publications table rather than
vanishing. Staff edit it via
`/staff/social/matriu/` (GET) + `/staff/social/matriu/toggle/` (POST).

**Per-cell day INDICATOR (item C, 2026-06).** The matrix shows the
PUBLISH DAY per (canal, tipus) as a **read-only indicator**, NOT an
editable field — the calendar/cron fixes the day, so an editable
per-cell day would have been redundant. The earlier editable
`MatriuPublicacio.dia_setmana` field + its `pot_distribuir_avui` gate
(5a) were removed (migration `0025`); they were a no-op anyway (every
cell was NULL), so publication is unchanged (`actiu_per` is the only
gate again). The indicator is derived by
`social.calendari.publish_weekdays_for(canal, tipus)` → a list of
weekday ints (0=Mon … 6=Sun): IG + push channels from `CALENDARI`
(top_ppcc→Sat, top_territorial→Mon+Wed, nous_singles→Fri,
nous_albums→Tue); the **newsletter** is the exception — it only sends
`top_ppcc`, on **Sunday**, via its own `enviar_newsletter` cron
(`0 10 * * 0`), captured by the `NEWSLETTER_PUBLISH_WEEKDAY` constant
(which MUST match that cron). A (canal, tipus) the channel never
publishes returns `[]` (the UI renders an em-dash; no day is invented).
The matrix GET exposes `dies` (weekday labels) + per-cell
`dies_publicacio`; the toggle endpoint is `actiu`-only again. The shared
`MatriuCanalToggles` renders one table per channel (rows = tipus,
columns = day indicator + actiu checkbox).

Staff controls (`web/api/staff/social/controls.py::social_toggle`):
`channel=global` writes `distribucio_activa`; `channel=<name>` writes the
per-channel switch. `channel` is required (no default — the old
default-to-`instagram` silently toggled IG and was the reason the
newsletter ignored the "global" pause before this fix). Honest
per-channel state (effective state + last send) at
`/staff/social/estat-canals/` (see `staff.md`).

## Calendar

Driven by `social/calendari.py`. Slots per weekday (the `min_fase`
rollout gate was removed 2026-06 — see the matrix section). Sat 09:30
UTC is the canonical `top_ppcc` cycle; territorials Mon (ROTATORI_B)
and Wed (ROTATORI_A) 09:30 UTC; novetats Tue (`nous_albums`) and Fri
(`nous_singles`) 10:00 UTC. **Thu** is the `moviment` slot (feed only,
over the Global top) — INERT until `moviment_actiu` (see below). Sun
is the newsletter's own cron, not `CALENDARI`.

## Renderer image format + PPCC feed cover (Step 3a, 2026-06-01)

`social/renderer.py` outputs **JPEG quality 90** (was PNG) for every
slide — `_path` emits `.jpg`, all `.save(...)` use `JPEG, quality=90`.
Instagram's Graph API accepts JPEG; the logrotate prune
(`deploy/logrotate.topquaranta`) now globs both `*.png` (legacy) and
`*.jpg`.

The **PPCC feed cover** (`_feed_portada_ppcc`) is rewritten as an
editorial cover on ink: big "TOP 40 / SETMANA N" kicker + a teaser of
up to 5 featured artist names (the main artist of each top-5 entry,
de-duplicated, chart order) + logo + footer URL. Replaces the
~85 %-empty legacy cover. Territorial covers (full-bleed album art) and
the feed list slides 1-4 are unchanged. Sans-only (Playfair is reserved
for the #1 story hero, landing in 3b).

`social/narrative/story_synth.py::synthesize_hero(scenario)` derives a
short uppercase headline (≤ 50 chars) per hero `scenario_code` for the
#1 story hero slide (e.g. a13 → "TORNA AL CIM DESPRÉS DE 5 SETMANES",
a2 → "5A SETMANA AL CIM"). Created in 3a; wired into the renderer in 3b.

## Story sets — see `social-stories.md`

The Instagram **story** renderers (PPCC 7-slide editorial set, the
paginated novetats story set, the territorial port) plus the standard
publish-robustness behaviour (resumable story sets + the 9007 readiness
retry, 2026-07-20) live in **`docs/architecture/social-stories.md`**
(split out per docs-maintenance Rule 3). Feed renderers stay below.

## Render engine — `social/render_core.py` (shared primitives)

The low-level PIL primitives live **once** in `social/render_core.py` and are
consumed by both `feed_redesign.py` (feed novetats) and `renderer.py` (the
editorial stories): ink-anchored text (`draw_text` — em-box / cap-top / ink-top,
composite or direct, glyph-by-glyph or whole-string), `radial_bg` (the gradient,
`stop`/`dtype` covering both the feed float64 and story float32 variants),
`rect`, `star`, `apply_grain` (`round_alpha` covering the cover/page vs album-band
variants), `paste_logo`/`logo_mono`, the territory code resolution (`CODE_TO_KEY`
/ `terr_key`, ALT/CAR, CAT=senyera), the `silhouette` mask and the fallback
`tile`. Each parameter exists so a call site reproduces its previous output
**pixel-for-pixel** (guarded by the feed + story fidelity pins). Geometry stays
with each caller as DATA — the feed in `feed-tokens.json`, the stories in
`social/story_design/story-tokens.json` (2026-06-12; loaded once via
`renderer.story_tokens()`). Every hand-stitched constant of the seven `_story_*`
builders (and their story-only shared helpers: `_header_row`, `_section_header`,
`_footer_url`, `_header_pill`, `_bg_ink`, `_draw_star`) — positions, sizes,
trackings, radii, gaps, local mix ratios — lives in that file; the builders carry
no geometry literal. Unlike feed-tokens (measured from a curated HTML export),
the story tokens were lifted **verbatim** from the running code, so the values
match exactly, ugly inconsistencies included (e.g. the podi line-height 62 vs its
entry-height title component 64). Colours stay in code (palette-driven via
`colors.*` / `story_palette`); only the slide-local mix ratios are tokenised.

## TOP family — `social/top_redesign.py` (2026-06)

The weekly TOP renders, composed over `render_core` + `feed_redesign`, geometry
in `social/top_design/top-tokens.json` (extracted headless from the Claude
Design "TOP" handoff). Four builders, all 1080×1350:

- **`build_poster`** — the **cartell**: a single image with the whole top 40
  (top-10 rich rows with mini-cover + movement, 11-40 dense in two columns).
  Generated for the global top (variant `ppcc`, **never labelled** — no "PPCC"
  text/name) AND per territory (its `deep/accent` palette + name).
- **`build_top_cover`** + **`build_top_list`** — the Instagram **carousel**:
  green/territory field cover + up to 4 list slides of 10, **counting down to #1**
  (40→31 … 10→1). PPCC rows carry the territory silhouette chip (CAT=senyera);
  territorial editions drop the chip (every row is the same territori).
- **`build_albums_mosaic`** — the new-albums **mosaic** (single image, Tuesday),
  up to 9 covers (CSS auto-row heights + vertical centring).

**Vocabulary:** the TOP renders never use the word "rànquing" (vetat) — "el top
sencer de la setmana", "EL TOP DE LA SETMANA", "el top de la setmana N".
**Fix pins (2026-06-12):** ink-anchored ±8 px against the artboards — EL TOP/40
gap, list numerals + SETMANA pill ink-centred (`render_core.draw_text(ink_center=)`),
and no title↔artist overlap (rich = 2-line clamp + artist stacked & centred;
dense = title ellipsised but artist always kept). **IG tagging + credits (2026-06):** list rows show the full credit (principal + collaborators via `artistes_noms`, like the stories) and `user_tags` mirror the carousel EXACTLY — same countdown blocks, each reversed — so every tag lands on its drawn row (`publicar_social._slide_tags`); top + nous_singles tag all collaborators, nous_albums tags the album artist + track collaborators (`payload.artistes_instagram_urls`). **Story mentions (2026-07):** the cron story sets (PPCC + territorial) carry per-story `user_tags` too — `publicar_social._story_tags` mirrors the story-set emission (same slices/conditional tiers/draw order) so each story mentions only the artists of its visible songs, anchored near their drawn item; `upload_story` gained an additive `user_tags` param; the feed's non-blocking guard is reused per story (`max_slots=20`), and a story that still fails is skipped without blocking the rest of the set (partial failure → `stories_fallides` in metadata + non-zero exit). Detail: `social-stories.md`.

**Movement** is one primitive: `render_core.draw_move` (up/down/new/re/eq;
semantic colours, palette-independent). `parse_move` derives it from real data;
re-entry ("RE") needs `posicio_anterior is None` AND a prior chart appearance —
computed in `payload.build_top` (`reentrada`, one batched indexed query).

**Per-channel routing (2026-06).** Instagram → the rich carousel
(`render_feed_top`, now the new builders; the legacy `_feed_portada` /
`_feed_list_slide` were **removed**). Telegram / Mastodon / Bluesky → **one
image** (`publicar_canal`): TOP → cartell, new albums → mosaic, new singles →
the grid's first page with overflow titles appended to the post text (>10
singles single-image is Miquel's pending call). Newsletter unchanged. Routes on
the existing matrix/config — no new view, idempotency untouched (a channel's
distinct image keys off the same `_path`). The cartell JPEG stays < 1 MB
(Bluesky blob limit, pinned).

## Feed redesign — editorial "Sèrie 7" (the only novetats renderer)

The three novetats feed slides (carousel cover, single-album slide, singles
grid) render with the editorial layout in `social/feed_redesign.py`, driven
by `social/feed_design/feed-tokens.json` — the **exact** computed values
(`getComputedStyle` + `getBoundingClientRect`) extracted from the curated
Claude Design HTML export rendered headless at 1080×1350. **This is the only
path** (2026-06-11): `renderer.py::render_feed_novetats` delegates the three
pieces straight to `feed_redesign.build_{cover,album,singles}`. The earlier
`ConfiguracioGlobal.feed_redisseny_actiu` gate and the legacy PIL layout were
**removed** once the design was approved (migration `ranking/0029` drops the
field). The legacy top-feed (`render_feed_top`) is unrelated and unchanged.

Scope is layout only: album selection, singles bin-packing, per-channel
gating, idempotency and the Deezer cover sourcing/fallback contract
(`cover_cache.fetch`) are untouched — only the cover-missing *tile* gets the
new spec visual (territory `deep` fill + initial in `accent`). Territory
palettes resolve via `feed_redesign.territori(code)` (DB code → JSON key;
`CNO`→`nor`; aggregate/unknown → green). Rendering is deterministic (fixed
grain seed). Album titles wrap to two lines (then shrink) instead of
ellipsising; PPCC is never a row territory. Bricolage Grotesque 500/700/800
are all real vendored OFL statics. Fidelity floor vs the references is text
rasterisation (PIL FreeType vs the 3×-downscaled Chrome export) + the
gaussian-grain approximation; positions/sizes/colours are exact.

**Singles chip = territory silhouette (2026-06-11).** The singles-grid chip no
longer shows the abbr TEXT (CAT/VAL…); it shows a hand-drawn territory
**silhouette** (senyera, rat penat, flama del Canigó, …) recoloured to
`territori.accent`. Assets: `social/feed_design/territory_logos/{key}.png`
(alpha = shape; recoloured via alpha-mask in `feed_redesign._terr_logo`). The
chip geometry is unchanged (92×85 `deep`); only its content. Sizing is
**optical, not geometric** — per-territory `optH` + `aspect` in the
`territory_logos` token block, width capped at `maxW=74`, centred. `CAT`(pri) =
the **senyera** (`territory-ppcc.svg` art), never the cross; `ALT`/`CAR` added
to the palette + code map. The territory short name stays at the right
(Instrument italic, one line). Values from the Claude Design feed-kit handoff.

## Static hosting

Meta's IG media-fetcher rejects rendered images served through
Django (CSP/COOP headers cause code 9004). Caddy serves
`/static/social/*` directly from
`/var/cache/topquaranta/social/renders/` as plain files.

The URL handed to the fetchers comes from
`SOCIAL_PUBLIC_BASE` via `_public_url_for`; if that setting is unset it
falls back to the Django `/api/v1/social/render` view — the exact
header-laden path that triggers 9004. The publish commands run under
**`production`** settings, so `SOCIAL_PUBLIC_BASE` MUST live in
`base.py` (not only `web_server.py`). Caught 2026-06-03: it was
`web_server`-only, so every cron publish sent the Django URL and BAL's
IG/Telegram slots failed with 9004 / `WEBPAGE_MEDIA_EMPTY` while the
byte-upload channels (Mastodon, Bluesky) — which never fetch a URL —
published fine. Guarded by `test_public_url_for_uses_caddy_static_not_django_fallback`.

## Ambassador share caption (Fase 2 E)

`social/ambassador.py::ambassador_top_caption(nom, slug, posicio=None)`
returns a ready-to-share "has entrat al top" caption (artist + canonical
URL + the position when known), cohesive with the press kit. It is
DECOUPLED from publishing: no gating, never auto-posted — it's text for
an artist/team to share, the move behind our best organic reach. No
positional `#<digit>` (same audience-leak discipline as the weekly
captions). The live post + campaign strategy stay manual (Miquel).

## Collaborator invitations — feed (ADR-0015; live since 2026-07-06)

Detail moved to [`social-collaboradors.md`](social-collaboradors.md)
(2026-07-06, docs-size split — same pattern as `social-narrative.md`).
In one line: artists invited as IG **collaborators** on feed posts
(never stories), gated on `ConfiguracioGlobal.ig_collaboradors_actiu`,
policy in `social/collaboradors.py`, non-blocking substitution guard at
publish. Acceptances are marked **manually from staff**
(`/staff/social/instagram`); the hourly `pollar_colaboracions_ig` is a
pure expiry cron (`caducada` at 14 days + registry-derived acceptance
rate — no Graph reads; the read path is unviable, ADR-0015 §5.5).
First real batch 2026-07-06; definitive cycle since 2026-07-13.

## Feed artwork covers + `moviment` (2026-07, gated OFF)

Two additions, both **inert by default** (`ConfiguracioGlobal` flags,
staff-editable in Configuració → Editorial; ADR-0016):

- **Artwork covers** (`feed_artwork_actiu`): the feed **cover slide**
  (list slides untouched) is backed by the duotoned artwork of the
  edition's #1 (tops) or a mosaic of the week's novetats. The duotone
  treatment lives in `social/duotone.py` (greyscale+contrast+brightness
  → accent multiply → edition-hue veil 0.30 → readability gradient),
  normative values transcribed from the approved mocks. Cover source =
  the SAME chain as the pipeline (`_artwork_cover`: local `/portades`
  jpg → Deezer → None → typographic fallback). Tops add a `Nº1 · artist
  · title` credit above the rule (the 40-name megacollab degrades to
  just the title). Novetats mosaic: 2×2 (≥4) / 2×3 (≥6, capped by
  `feed_artwork_mosaic_max`); <2 covers → typographic. Palette from the
  existing `top-tokens`/`feed-tokens` (never hardcoded).
- **`moviment` tipus** (`moviment_actiu`): Thursday feed post over the
  Global top. `payload.build_moviment` reuses `build_top`'s
  `posicio_anterior`/`reentrada`: a NEW/RE entry into the top 10 wins
  (`entrada`), else the strongest rise (`pujada`); a best rise below
  `moviment_pujada_minima` → omitted like an empty novetats window.
  `top_redesign.build_moviment_cover` renders LA PUJADA/+delta or
  L'ENTRADA/Nº pos over the protagonist's duotoned artwork; caption via
  `captions.caption_moviment`. With the flag off the Thursday slot
  creates **no SocialPost row** (full no-op, unlike the matrix 'omès').
  - **Tags + collaborator parity (2026-07-16):** protagonist tagged on
    its cover via `_tags_for_entries` (not `_slide_tags`; the moviment IS
    the cover) + ADR-0015 invite via `_collaborator_plan`, gated by
    `ig_collaboradors_actiu` **not** `moviment_actiu`. See `social-collaboradors.md`.

Stories are untouched. No-regression: with both flags off the covers
never call `duotone` and are byte-identical (pinned in
`social/tests/test_feed_artwork_moviment.py`).

## Related

- Collaborator invitations detail: [`social-collaboradors.md`](social-collaboradors.md).
- Narrative engine detail: [`social-narrative.md`](social-narrative.md).
- Post-mortems: `2026-05-20-narrative-engine-collapsed.md`
  (Resolved by ADR-0006/0007/0008),
  `2026-05-21-bluesky-silent-failures.md` (Resolved by ADR-0005).
- ADRs: 0005 (Bluesky retry), 0006 (ordinals), 0007 (`@handle`
  IG), 0008 (detectors a9-a12 + tertiary slot).
- Modules: `social/captions.py`, `social/payload.py`,
  `social/narrative/`, `social/management/commands/publicar_*.py`
- Calendar source of truth: `social/calendari.py`
