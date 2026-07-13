# Instagram story renderers

> Split out of `social.md` (2026-07-03) for the docs-size ceiling.
> The publishing pipeline, channels, distribution gate and feed
> renderers stay in `social.md`; this doc is the **story** surface
> (1080×1920): the PPCC editorial set, the paginated novetats set and
> the territorial port.

# Spec: docs/architecture/social.md

## PPCC story set — 7 editorial slides (Step 3b)

`renderer.render_stories_ppcc(setmana, entries, *, novetats_items,
hero_headline)` replaces the legacy PPCC sequence (intro + up to 40
cançó slides + CTA) with a fixed seven-slide set ordered toward the #1
climax (structure + a **2026-06-02 redesign** porting the validated
Claude Design canvas, pixel-measured from the 1080×1920 references).
Both are Step 3b; the territorial port is Step 3c (section below):

1. **intro** — green radial field, white logo, "presenta" serif accent,
   the big **EL TOP / 40 / D'AQUESTA SETMANA** stack, star-separated
   SETMANA pill row.
2. **top 40→11** — 5×6 cover mosaic, yellow Anton number badge pinned to
   each cover's top-left corner (`width:auto`, so double digits stay
   left-aligned), Bricolage titles + Roboto artist subtitles.
3. **top 10→4** — 2-column cover grid (#10/#9, #8/#7, #6/#5) with #4
   centred below (mirrors the newsletter D1a block).
4. **podi #3-2** — two centred 300 px covers stacked, big Anton badge +
   Bricolage title + Roboto artist.
5. **#1 hero** — inverted hierarchy: a ghost "1" clipped at the right, a
   subordinate yellow scenario kicker, and the SONG TITLE in **Playfair
   Display 800** as the primary element (the only Playfair on the set).
6. **novetats** — 2-3 most recent releases (albums + singles merged,
   newest first); **skipped** when nothing is recent → 6 or 7 slides.
7. **outro** — yellow field, ink logo, "EL TOP 40" (Anton), star
   separator, an informative (non-clickable) underlined `topquaranta.cat`
   CTA, SETMANA footer. No slate `COLOR_CARD` card.

**Typography** (vendored OFL TTFs under `social/fonts/`): **Anton**
(display/numbers/pills/footers), **Bricolage Grotesque 800** (song
titles on 2/3/4/6), **Playfair Display 800** (slide-5 title only),
**Instrument Serif italic** (the two serif accents); the sans role
(kickers, artist subtitles, hero scenario, CTA) reuses bundled
**Roboto**. Playfair/Bricolage are static instances cut from the upstream
variable fonts. Letter-spacing + line-height are emulated glyph-by-glyph
(`_draw_tracked`); the star separators are vector polygons
(`_draw_star`); backgrounds are numpy radial gradients (`_radial_bg`,
flat green/ink/yellow + gradient — grain deliberately skipped). The logo
reuses `svg_assets.logo_image_mono` (white on dark, ink on yellow). No
trend cues anywhere.

Covers resolve **local self-hosted portada first** (`ingesta.portades`,
250 px for small slots / 500 px for large) then the live Deezer CDN URL
then a placeholder tile — the newsletter placeholder does NOT apply here.
The PPCC story set is a fixed 7-slide editorial sequence (the
`story_max_cancons_ppcc` field + its `/staff/social/story-cap/` endpoint were
removed 2026-06-11 — they governed nothing). The `#1` headline comes from
`_story_hero_headline(setmana, territori)`. Output stays JPEG q90; a
full set is ~1 MB (7 JPG) vs the legacy ~42 PNG.

Operational note: the link-sticker on the outro story must still be
added manually each week through the Instagram app — the Graph API
does not expose story stickers programmatically.

## Novetats story set — paginated (2026-07-03)

`renderer.render_stories_novetats(setmana, items, *, per_page,
territori)` renders the novetats releases as a **paginated story set** —
one 1080×1920 JPEG per chunk of `per_page` items — so every release
appears (the weekly PPCC set's single slide 6 still shows only 2-3). The
page count is `ceil(len(items)/per_page)`; each page carries a discreet
`· k/M` suffix on the kicker (reusing the section-header style). Geometry
comes from `_novetats_fit(cap, band_top)`: it keeps the design cover
(210 px) and only tightens the inter-item gap, shrinking covers solely
once the gap floor is hit (≥5 per page); every page in a set is sized for
`per_page` so all share one scale and start-Y. `per_page` is
`ConfiguracioGlobal.novetats_stories_per_pagina` (default **4**,
staff-editable in Config → Editorial, renderer clamp 1-8).
`_story_novetats` is unchanged in single-page mode (no `page`/`total_pages`
args) — the weekly PPCC/territorial callers are byte-identical.

`user_tags` are computed **per story** from the visible items only
(principal + collaborators of those releases that have an `instagram_url`),
coordinates anchored to each item's cover — no mention without a visible
song. The publisher applies the same non-blocking guard as the feed
carousel: a handle that errors a STORIES container is dropped and the
story retried, last-resort published without mentions (stories support
`user_tags` since 2025-07-09; **no** collaborators/product tags — feed
only). First real run 2026-07-03: 11 nous_singles → 3 stories (4+4+3),
5 effective mentions.

## Story mentions — ALL pipeline story sets (2026-07-13)

The per-story mention engine now covers every story path the cron
publishes, not just the novetats pages. `publicar_social._story_tags`
builds one `user_tags` list per rendered story, mirroring
`render_stories_ppcc` / `render_stories_territorial` emission EXACTLY
(same slices, same conditional territorial tiers, same draw-order
reversal): intro/outro carry nothing; the mosaic tags entries 40→11
(capped at Meta's 20/image, principal-first round-robin so one
hyper-collaborative entry can't starve the rest); the grid 10→4; the
podi #3/#2; the hero #1; the PPCC novetats slide its ≤3 releases.
Anchors are approximate normalized centres of each drawn item
(`_pos_story_*` — same discipline as the feed tagger's row anchors,
not pixel-exact). `instagram_client.upload_story` gained an additive
`user_tags` param. Guards, two levels: per mention, the feed
substitution guard reused with `max_slots=20` (drop the offending
handle, retry, last resort untagged); per story, a page that still
fails is skipped and the REST of the set publishes — partial failure
marks the slot `publicat` with `metadata.stories_fallides` +
`error_msg` and exits non-zero (same report-don't-roll-back discipline
as the 2026-07-12 slot-level rule). A tag/slide count mismatch
publishes the whole set untagged rather than mis-anchored. Images are
untouched — this is API payload only. No new config: the only knob
remains `novetats_stories_per_pagina`.

**Collaborator parity (2026-07-03).** `payload.build_novetats` now emits
`artistes_noms` (principal + track collaborators, deduped, via a single
`_album_collabs` pass that also feeds the tag list), so the novetats feed
slides (`feed_redesign.build_album` / `build_singles`) and the novetats
story (`_story_novetats`) show **every** artist on a release — parity with
the top carousel (`top_redesign._artist_credit`, PR #301), which had the
fix while the novetats path did not.

## Territorial stories — Step 3c

`render_stories_territorial` reuses the PPCC builders, recoloured by
`colors.story_palette` (accent/deep/light + a `badge` role; CAT badge is
a vivid orange, others = accent). Slides add a `TERRITORI_SHORT` pill, an
intro territory-icon watermark (`_STORY_ICON_CODI` maps CAT → senyera)
and a `TERRITORI_DE` subtitle (step-down past 680 px); hero/outro stay
brand. Tiers degrade by omission (mosaic N>10, grid N>3, podi N>1; warn
below 11); only `calendari.TERRITORIS_ROTATORI` publish, others fail
loud. PPCC byte-identical.

