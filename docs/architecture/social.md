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
                                     {items}                    for nous_*
  ↓ social/captions.py
      compose_for_channel(channel, tipus, territori, setmana, entries)
        ↓ if tipus ∈ {top_ppcc, top_territorial}:
            social/narrative/scenarios.detect_all → 12 detectors a1-a12 (ADR-0008)
            social/narrative/composers/<channel>.compose
              ↓ pick_phrase(hero, long, …)     via registry (anti-repeat)
              ↓ pick_phrase(secondary, medium, …)  if scenarios[1] exists
              ↓ pick_phrase(tertiary, short, …)    IG-feed only (ADR-0008)
              ↓ for IG: `@handle` rewrite per ADR-0007
              ↓ top5_bank.pick_long / pick_short (ordinals per ADR-0006)
              ↓ hashtags_bank.build_hashtags
              ↓ cta_bank.pick_cta
          else: _legacy_for(channel, tipus, …)  ← novetats path
  ↓ social/renderer.py            → PNG slides
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

## Narrative engine (12 detectors)

Located at `social/narrative/scenarios.py`. Each detector runs
over the `TopSetmanal` for a given week and territory; returns at
most one `Scenario(code, severity, data)`. `detect_all` returns
the list sorted by severity desc; the composer picks
`scenarios[0]` as the hero, optionally `scenarios[1]` as a
secondary thread, and (IG feed only, ADR-0008) `scenarios[2]` as
a tertiary thread.

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
| `fallback_no_event` | Catch-all when nothing fires | 0 |

### Format de posicions (ADR-0006)

Les plantilles emeten posicions com a **ordinals catalans** (`1r`,
`2n`, `3r`, `4t`, `5è–99è`) via `social.narrative.utils.ordinal_ca`.
La forma anterior `#N` era parsejada com a hashtag clicable per
Instagram i Telegram. La conversió cobreix `banks/hero.py`,
`banks/top5.py` i tots els `posicio_anterior_str` / `posicio_nova_str`
que emeten els detectors.

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

## Static PNG hosting

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
