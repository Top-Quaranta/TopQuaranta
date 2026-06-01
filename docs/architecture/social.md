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

## Narrative engine (13 detectors)

Located at `social/narrative/scenarios.py`. Each detector runs
over the `TopSetmanal` for a given week and territory; returns at
most one `Scenario(code, severity, data)`. `detect_all` returns
the list sorted by severity desc.

### Distinct-subject slot selection (2026-06-01, audit #1/#6)

`select_slots(scenarios, max_slots)` picks up to `max_slots`
scenarios with **distinct subjects**, greedily by severity. Two
scenarios conflict when they share a non-None `canco_id` OR a
non-None `artista_id` (`_scenario_subject` returns the
`(canco_id, artista_id)` tuple; `_base_data` populates both — a
song-focal scenario carries both, the artist-focal `a5` carries
only `artista_id`). This stops the hero/secondary/tertiary from
repeating the same song or artist (e.g. hero `a10` "Noia de
Porcellana 5è" + tertiary `a6` about the same song). IG feed asks
for 3 slots; the other composers for 2. **The tertiary slot is no
longer systematic** — a caption ends at hero+secondary (or just
hero) when the detectors don't supply enough distinct subjects.

| Code | Trigger | Severity range |
|---|---|---|
| `a1_outside_to_top1` | Top-1 song was outside top last week or at pos ≥ 5 | 6-10 |
| `a2_streak` | Top-1 song N consecutive weeks (N≥2) | min(N, 10) |
| `a3_fall_from_top1` | Previous top-1 is no longer top-1 | 4-7 |
| `a4_debut_alt` | New entry at position ≤3 | 10 − posicio |
| `a5_artista_multiple` | Artist with ≥3 songs in the top | n_cancons |
| `a6_canco_recent` | Song <30 days old currently in top 10 | 11 − posicio |
| `a7_long_runner` | Song ≥180 days old in top 10 | 5 (fixed) |
| `a8_pujada_forta` | Song climbed ≥10 positions and now in top 10 | climb // 2 |
| `a9_debut_anywhere` | New entry at position 4-40 (ADR-0008) | 1-5 |
| `a10_artista_first_ever` | Artist's first-ever top appearance (ADR-0008) | 8 (fixed) |
| `a11_top5_drop_generic` | Song was top 2-5, now out of top 10 (ADR-0008) | 4-5 |
| `a12_artista_emerging` | Artist re-appears after a one-week gap (ADR-0008) | 3 (fixed) |
| `a13_top1_return` | Song reclaims #1 after a gap (was #1 before, not #1 at W-1) | min(9, max(5, gap_weeks+3)) |
| `fallback_no_event` | Catch-all when nothing fires | 0 |

`a13_top1_return` (2026-06-01) is distinct from `a1` (fresh #1 with
no #1 history) and `a2` (consecutive streak). Severity scales with
the gap since the last #1 reign (min gap 2 weeks → floor 5; ≥6 weeks
caps at 9). Its bank ships 6 variants/tier (rarer trigger) vs the
15/tier of the original detectors.

### Novetats narrative engine (2026-06-01, audit #5)

`nous_albums` / `nous_singles` no longer use the skeleton
`caption_novetats`; they run a parallel engine. `payload.build_novetats`
batch-computes per-album flags (`artista_en_top`, `primer_release`,
`te_collab`, `segell_compartit`, `dies`, `segell`) in
`_novetats_flags`. `novetats.detect_novetats(items)` runs four detectors
over those flags and always appends a `fallback_novetat`:

| Code | Trigger | Severity |
|---|---|---|
| `n1_debut_artist_known` | release by an artist in the recent top | 6 |
| `n2_first_release` | artist's first catalogued release | 5 |
| `n3_collaboration` | release with a featuring (generic copy — guest names aren't stored) | 4 |
| `n4_label_release` | label shared by ≥2 distinct top artists | 3 |
| `fallback_novetat` | most recent release (always present) | 0 |

Novetats scenarios are **album-focal** (`canco_id=None`, `artista_id`
set), so `select_slots` dedups them by artist. `composers/novetats.py`
is the shared composer (per-channel budget); `nous_albums.py` /
`nous_singles.py` are thin tipus-pinning wrappers. Bank:
`banks/novetats.py` (no territori placeholders). Hashtags are the
TitleCase `HASHTAGS_NOVETATS`; CTAs are novetats-specific (the top
CTAs reference a "rànquing" that a roundup isn't).

### Caption density (2026-06-01, audit #4/#13)

The IG-feed composer has a **density floor** `MIN_CAPTION_RATIO = 0.45`
(~990 of 2200 chars). Below it, it upgrades phrase tiers before
truncation — tertiary `short → medium`, then secondary `medium → long`
— keeping any upgrade that still fits 2200. It never synthesises
filler; a still-thin caption is `logger.warning`-ed, not padded. The
**newsletter** now carries a third paragraph (`select_slots(…, 3)` →
hero + secondary + tertiary + top-5 detail); it has no hard ceiling.
A symmetric newsletter floor is deferred (proposed, not applied).

Novetats hashtags are now TitleCase (`#TopQuaranta #MúsicaEnCatalà
#Novetats` via `captions.HASHTAGS_NOVETATS`), consistent with the
tops' bank (audit #2).

### Format de posicions (ADR-0006)

Les plantilles emeten posicions com a **ordinals catalans** (`1r`,
`2n`, `3r`, `4t`, `5è–99è`) via `social.narrative.utils.ordinal_ca`.
La forma anterior `#N` era parsejada com a hashtag clicable per
Instagram i Telegram. La conversió cobreix `banks/hero.py`,
`banks/top5.py` i tots els `posicio_anterior_str` / `posicio_nova_str`
que emeten els detectors.

### Concordança de comptes i dedup top-5 (2026-05-31)

Dos fixos editorials petits:

- **`dies_str(n)`** (`social.narrative.utils`) — concordança
  singular/plural: `dies_str(1)` → "1 dia", la resta → "{n} dies" (inclòs
  "0 dies"). Les plantilles de `banks/hero.py` usen `{dies_str}` en lloc
  del patró antic `{dies} dies`, que llegia "1 dies" en debuts d'un dia.
  `scenarios.detect_a6_canco_recent` ompla `dies_str`; `registry.pick_phrase`
  el deriva de `dies` si l'escenari només porta el comptador cru.
  *(Altres plurals hardcoded — `{streak} setmanes`, `{mesos} mesos`,
  `{pujada} llocs`, `{n_cancons} cançons` — són latents però segurs: els
  detectors garanteixen ≥2, així que mai surt el singular. No tocats.)*
- **Dedup top-5** — `banks/top5.py::_dedup_artist_names` elimina noms
  d'artista repetits (per primera ocurrència) al registre SHORT, que
  llista noms plans ("X, Y i Z"). Abans, un artista amb 2+ cançons al top
  5 sortia N cops ("Max Navarro, Ouineta i Max Navarro"). En el cas amb
  líder (hero ≠ 1r), el nom del líder s'**exclou** del llistat "també al
  top 5" si també hi té una segona cançó (cas real Maria Jaume al top
  BAL); si tot el que queda és el líder, es cau a la línia només-líder. El
  registre LONG NO es dedupa: llista cançons distintes amb posició, on un
  mateix artista hi recorre legítimament.

### Etiquetes territorials (2026-05-31)

`social.narrative.utils` té TRES mapes (abans un de sol,
`_TERRITORI_LABELS`, amb errors de concordança):

- **`TERRITORI_DE`** — forma genitiu, per a contextos on l'etiqueta
  penja d'un nom "top"/"rànquing" ("Top …", "al rànquing …", "al top
  …"). Porta la preposició + article correctes. PPCC és `Global` SENSE
  preposició (encaixa com a adjectiu de "top": "al top Global").
- **`TERRITORI_SHORT`** — forma curta per a pills de stories, OG i
  hashtags. `social/captions.py::TERRITORI_NOM` n'és un àlies (renderer).
- **`TERRITORI_ORDINAL`** — override per a contextos ordinal/locatius on
  l'etiqueta penja directament d'una paraula de posició ("al 1r …", "el
  cim …", "al podi …", "al capdamunt …") sense "top"/"rànquing" pel mig.
  Només conté l'override de **PPCC → `del top general`** (perquè "al 1r
  Global" sonava terse); la resta de territoris hi cau a la seva forma
  `TERRITORI_DE`, així que és un no-op.

Els 10 territoris i les seves formes:

| Slug | `TERRITORI_DE` | `TERRITORI_SHORT` | `TERRITORI_ORDINAL` |
|---|---|---|---|
| PPCC | Global | Global | **del top general** |
| CAT | de Catalunya | Catalunya | (= DE) |
| VAL | del País Valencià | País Valencià | (= DE) |
| BAL | de les Illes Balears | Balears | (= DE) |
| AND | d'Andorra | Andorra | (= DE) |
| CNO | de Catalunya Nord | Catalunya Nord | (= DE) |
| FRA | de la Franja | la Franja | (= DE) |
| ALG | de l'Alguer | l'Alguer | (= DE) |
| CAR | del Carxe | el Carxe | (= DE) |
| ALT | *(omès)* | *(omès)* | *(omès)* |

**`ALT`** ("Altres territoris") no es publica mai com a top, així que
està DELIBERADAMENT fora dels tres mapes: `territori_label("ALT")` (i
`_short` / `_ordinal`) llencen `KeyError` natural en lloc d'un fallback
silent, per a detectar qualsevol invocació errònia (decisió 2026-05-31).

Funcions: `territori_label()` → `TERRITORI_DE`; `territori_short()` →
`TERRITORI_SHORT`; `territori_ordinal()` → `TERRITORI_ORDINAL` amb
fallback a `TERRITORI_DE`. Les plantilles de `banks/hero.py` usen
`{territori_label}` quan pengen de "top"/"rànquing"/"territori" i
`{territori_ordinal}` quan pengen de "1r/cim/podi/capdamunt/{ordinal}"
(157 de 478 plantilles). `registry.pick_phrase` reomple els dos
placeholders des de l'argument `territori` si l'escenari no els porta.

**PPCC mai apareix com a text d'usuari** en el LABEL del top: "Països
Catalans" no s'usa enlloc visible i el hashtag `#PaïsosCatalans` s'ha
eliminat.

### Prosa geogràfica "Països Catalans" (decisió editorial 2026-05-31)

El rebrand a "Global"/"del top general" aplica NOMÉS a l'etiqueta del
**top** (el rànquing). El terme **"Països Catalans" es manté** com a
terme cultural-geogràfic descriptiu a la prosa de homepage, pàgines
legals i mapa (p.ex. "música en català dels Països Catalans"): allà
descriu el territori, no un rànquing, i "Global" no hi encaixa. La
distinció és deliberada: *label del top* → Global/General; *terme
cultural* → Països Catalans.

### `@username` a Instagram (ADR-0007)

El composer d'IG-feed reescriu `Scenario.data["artista"]` (i les
variants preposicionals) a `@handle` quan l'artista té
`instagram_url` emmagatzemat. Mateixa transformació per als
`artista_nom` de les entrades del top 5. Els altres 4 canals
mantenen el nom pla (diferent sintaxi de menció per xarxa; vegeu
`social/captions.py::_artist_label`).

### Slot terciari al composer d'IG (ADR-0008)

Només a `composers/instagram_feed.py`. Ordre de truncament quan
el text supera 2 200 chars: tertiary → secondary → top5 detail →
hashtags (un a un). Altres composers mantenen 2 slots
(hero + secondary).

Anti-repeat: `social.NarrativePhraseUsage` row per (channel,
territori, phrase_id, setmana). The `registry.pick_phrase` helper
filters phrases already used at the same (channel, territori) in
a recent window; falls back to the full bank if exhausted (a post
must go out).

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

## Calendar

Driven by `social/calendari.py`. Slots per weekday with
`min_fase` gates (Instagram rollout phases). Sat 09:30 UTC is
the canonical `top_ppcc` cycle; territorials Sun 09:50 UTC;
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

## PPCC story set — 7 editorial slides (Step 3b, 2026-06-01)

`renderer.render_stories_ppcc(setmana, entries, *, novetats_items,
hero_headline)` replaces the legacy PPCC story sequence (intro + up to
40 cançó slides + CTA) with a fixed seven-slide set ordered to build
toward the #1 climax:

1. **intro** — green PPCC senyera (`territory-ppcc.svg`) + brand logo +
   Setmana pill (reuses `_story_intro`; no typographic wordmark).
2. **top 11-40** — 5×6 cover mosaic, a position badge per cell, peu
   "Top 11-40 · Setmana N".
3. **top 4-10** — 2-column cover grid with the last cover centred
   (mirrors the newsletter D1a block).
4. **podi #2-3** — two 350 px covers stacked, big green position number
   + song title + artist each.
5. **#1 hero** — large framed cover + the synthesised Playfair headline
   (the **only** Playfair text in the set) + song/artist in Roboto.
6. **novetats** — 2-3 most recent releases (albums + singles merged,
   newest first) with covers; **skipped** when nothing is recent, so
   the set is 6 or 7 slides.
7. **outro** — yellow-accent CTA ("Top complet a topquaranta.cat", ink
   mono logo). No slate `COLOR_CARD` card (that primitive stays in use
   by the territorial `_story_cta`).

Covers resolve **local self-hosted portada first** (`ingesta.portades`,
250 px for small slots / 500 px for large) then the live Deezer CDN URL
then a placeholder tile — the newsletter placeholder does NOT apply here.
No trend cues anywhere. `story_max_cancons_ppcc` no longer governs the
PPCC set (kept for the config/staff surfaces). Territorial stories are
untouched and still use `render_stories_top`. The `#1` hero headline is
threaded from `publicar_social._story_hero_headline` →
`scenarios.detect_all("PPCC", …)` (strongest post-dedup scenario) →
`story_synth.synthesize_hero`. Output stays JPEG q90; a full set is
~1 MB (7 JPG) vs the legacy ~42 PNG.

Operational note: the link-sticker on the outro story must still be
added manually each week through the Instagram app — the Graph API
does not expose story stickers programmatically.

## Static hosting

Meta's IG media-fetcher rejects rendered images served through
Django (CSP/COOP headers cause code 9004). Caddy serves
`/static/social/*` directly from
`/var/cache/topquaranta/social/renders/` as plain files.

## Related

- Post-mortems: `2026-05-20-narrative-engine-collapsed.md`
  (Resolved by ADR-0006/0007/0008),
  `2026-05-21-bluesky-silent-failures.md` (Resolved by ADR-0005).
- ADRs: 0005 (Bluesky retry), 0006 (ordinals), 0007 (`@handle`
  IG), 0008 (detectors a9-a12 + tertiary slot).
- Modules: `social/captions.py`, `social/payload.py`,
  `social/narrative/`, `social/management/commands/publicar_*.py`
- Calendar source of truth: `social/calendari.py`
