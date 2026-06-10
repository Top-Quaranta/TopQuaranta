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
UTC is the canonical `top_ppcc` cycle; territorials Sun 09:50 UTC;
novetats slots Mon/Wed mornings.

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
`story_max_cancons_ppcc` no longer governs the PPCC set (kept for the
config/staff surfaces). The `#1` headline comes from
`_story_hero_headline(setmana, territori)`. Output stays JPEG q90; a
full set is ~1 MB (7 JPG) vs the legacy ~42 PNG.

Operational note: the link-sticker on the outro story must still be
added manually each week through the Instagram app — the Graph API
does not expose story stickers programmatically.

## Territorial stories — Step 3c

`render_stories_territorial` reuses the PPCC builders, recoloured by
`colors.story_palette` (accent/deep/light + a `badge` role; CAT badge is
a vivid orange, others = accent). Slides add a `TERRITORI_SHORT` pill, an
intro territory-icon watermark (`_STORY_ICON_CODI` maps CAT → senyera)
and a `TERRITORI_DE` subtitle (step-down past 680 px); hero/outro stay
brand. Tiers degrade by omission (mosaic N>10, grid N>3, podi N>1; warn
below 11); only `calendari.TERRITORIS_ROTATORI` publish, others fail
loud. PPCC byte-identical.

## Feed redesign — editorial "Sèrie 7" (gated, additive)

The three novetats feed slides (carousel cover, single-album slide, singles
grid) have an alternate editorial layout in `social/feed_redesign.py`, driven
by `social/feed_design/feed-tokens.json` — the **exact** computed values
(`getComputedStyle` + `getBoundingClientRect`) extracted from the curated
Claude Design HTML export rendered headless at 1080×1350 (replaces the earlier
hand-measured tokens). It is **off by default**, gated by
`ConfiguracioGlobal.feed_redisseny_actiu` (additive boolean). `renderer.py`
reads the flag once in `render_feed_novetats` and threads `redesign=` into
`_feed_novetats_portada` / `_feed_album_slide` / `_feed_singles_slide`; when
True each delegates to `feed_redesign.build_{cover,album,singles}`, else the
legacy layout renders byte-for-byte.

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

## Related

- Narrative engine detail: [`social-narrative.md`](social-narrative.md).
- Post-mortems: `2026-05-20-narrative-engine-collapsed.md`
  (Resolved by ADR-0006/0007/0008),
  `2026-05-21-bluesky-silent-failures.md` (Resolved by ADR-0005).
- ADRs: 0005 (Bluesky retry), 0006 (ordinals), 0007 (`@handle`
  IG), 0008 (detectors a9-a12 + tertiary slot).
- Modules: `social/captions.py`, `social/payload.py`,
  `social/narrative/`, `social/management/commands/publicar_*.py`
- Calendar source of truth: `social/calendari.py`
