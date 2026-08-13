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

## Renderer — see `social-renderer.md`

Primitives compartides, família TOP, redisseny del feed, portades i
formats d'imatge. Partit de `social.md` el 2026-08-12 per mida
(docs-maintenance.md, Rule 3).

## Story sets — see `social-stories.md`

The `canco_dia` sonda tipus (2026-08-13; 2/day on story-less days,
gated by `canco_dia_actiu`, `--franja` runs) is documented in
`social-stories.md` §Sondes; its `SocialPost.slot_key` discriminator
extends the weekly idempotence key without touching existing rows.
The Instagram **story** renderers (PPCC 8-slide editorial set, the
paginated novetats story set, the territorial port) plus the standard
publish-robustness behaviour (resumable story sets + the 9007 readiness
retry, 2026-07-20) live in **`docs/architecture/social-stories.md`**
(split out per docs-maintenance Rule 3). Feed renderers stay below.

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

Detail: [`social-collaboradors.md`](social-collaboradors.md).

**Handles caducats (2026-08).** Etiquetem el principal i tots els
col·laboradors de cada cançó, i Meta **no ignora** una etiqueta dolenta:
llança `code 110` i s'endú la pujada sencera (el 03/08 va tombar el top
territorial CAT, que no s'ha publicat mai). `publicar_social` ara reintenta
sense els handles refusats i, per cada un, **buida `Artista.instagram_url`**
— és un camp públic que viatja a la fitxa i al `sameAs` del JSON-LD, així
que un compte renombrat hi deixava un enllaç mort. El valor va a
`instagram_rebutjat_url` i `instagram_revisat` torna a `False`, de manera
que l'artista **reapareix a la cua de staff** amb l'avís de buscar-ne el
compte nou. Detall a
[`social-etiquetatge.md`](social-etiquetatge.md).
In one line: artists invited as IG **collaborators** on feed posts
(never stories), gated on `ConfiguracioGlobal.ig_collaboradors_actiu`,
policy in `social/collaboradors.py`, non-blocking substitution guard at
publish. Acceptances are marked **manually from staff**
(`/staff/social/instagram`); the hourly `pollar_colaboracions_ig` is a
pure expiry cron (`caducada` at 14 days + registry-derived acceptance
rate — no Graph reads; the read path is unviable, ADR-0015 §5.5).
First real batch 2026-07-06; definitive cycle since 2026-07-13.

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
