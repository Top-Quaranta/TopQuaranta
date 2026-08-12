# Renderer social — imatges de les publicacions

> Com es generen les imatges que publiquem: primitives compartides,
> família TOP, redisseny del feed, portades i formats.
>
> La **distribució** (canals, calendari, portes, auth) viu a
> [`social.md`](social.md); les **stories** a
> [`social-stories.md`](social-stories.md); l'**etiquetatge d'Instagram**
> a [`social-etiquetatge.md`](social-etiquetatge.md).
>
> Partit de `social.md` el 2026-08-12: el fitxer havia arribat al
> llindar de mida i el renderer és una subàrea pròpia i coherent
> (docs-maintenance.md, Rule 3 — «split by sub-area»).

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
