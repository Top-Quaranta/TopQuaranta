# Social distribution

Five-channel weekly publication system: Instagram (feed + stories),
Mastodon, Bluesky, Telegram, Newsletter. Plus an RSS surface for
syndication and a static-PNG hosting path for Meta's media-fetcher.

> **Note (May 2026):** the system is scheduled for a refactor sprint
> driven by `docs/post-mortems/2026-05-20-narrative-engine-collapsed.md`.
> This doc captures **architecture and decisions** so the refactor
> has a stable spec; implementation details may move.

## Flow

```
cron (publicar_social or publicar_canal)
  ↓ social/payload.py             → {entries, hero_cover_url}  for top_*
                                     {items}                    for nous_*
  ↓ social/captions.py
      compose_for_channel(channel, tipus, territori, setmana, entries)
        ↓ if tipus ∈ {top_ppcc, top_territorial}:
            social/narrative/scenarios.detect_all → 8 detectors a1-a8
            social/narrative/composers/<channel>.compose
              ↓ pick_phrase(hero, length, …)   via registry (anti-repeat)
              ↓ top5_bank.pick_long / pick_short
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
| Instagram feed | `social/instagram_client.py` + `narrative/composers/instagram_feed.py` | 2 200 | `@handle` (legacy path; regressed on narrative path, see post-mortem) + `user_tags` via Graph API | 8-12 |
| Instagram story | same client, `composers/instagram_story.py` | short | plain | minimal |
| Mastodon | `social/mastodon_client.py` + `composers/mastodon.py` | 500 | plain name | 3-5 |
| Bluesky | `social/bluesky_client.py` + `composers/bluesky.py` | 300 | plain name | 2-3 |
| Telegram | `social/telegram_client.py` + `composers/telegram.py` | 1 024 | plain name | 3-5 |
| Newsletter | `composers/newsletter.py` | unbounded | plain name | — |

## Narrative engine (8 detectors)

Located at `social/narrative/scenarios.py`. Each detector runs
over the `TopSetmanal` for a given week and territory; returns at
most one `Scenario(code, severity, data)`. `detect_all` returns
the list sorted by severity desc; the composer picks
`scenarios[0]` as the hero, optionally `scenarios[1]` as a
secondary thread.

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
| `fallback_no_event` | Catch-all when nothing fires | 0 |

Anti-repeat: `social.NarrativePhraseUsage` row per (channel,
territori, phrase_id, setmana). The `registry.pick_phrase` helper
filters phrases already used at the same (channel, territori) in
a recent window; falls back to the full bank if exhausted (a post
must go out).

## Known regressions (May 2026)

1. **IG `@handle` lost on narrative path.** Legacy
   `_caption_top_legacy` called `_artist_label(use_handle=True)`
   which rendered `@username` for autolinking. The new narrative
   composers go through `top5_bank.pick_long` which renders plain
   names. Fix scope: refactor sprint.
2. **`#N` positional hashtags.** Templates in
   `narrative/banks/hero.py` and `banks/top5.py` literally
   contain `al #1`, `al #{posicio}`. IG and Telegram parse
   `#<digit>` as hashtag-clickable; the post leaks audience out.
   Mastodon and Bluesky parsers ignore numeric hashtags so
   they render as text. Fix scope: refactor sprint (alternatives:
   "núm. N", emoji digits, drop the number when context is clear).
3. **Bluesky timeout 60 s.** `upload_blob` against
   `bsky.social` for 4-PNG carousels is marginal. No retry. ~2/3
   of weekly Bluesky publications fail silently. See
   `docs/post-mortems/2026-05-21-bluesky-silent-failures.md`.

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

- Post-mortems: `2026-05-20-narrative-engine-collapsed.md`,
  `2026-05-21-bluesky-silent-failures.md`
- Modules: `social/captions.py`, `social/payload.py`,
  `social/narrative/`, `social/management/commands/publicar_*.py`
- Calendar source of truth: `social/calendari.py`
