# Social narrative engine

Detail spec for the weekly-caption narrative engine. Split out of
[`social.md`](social.md) (which stays the index for the social
subsystem) to keep each doc under the 400-line docs-size gate.

## Detectors (13 + fallback)

Located at `social/narrative/scenarios.py`. Each detector runs
over the `TopSetmanal` for a given week and territory; returns at
most one `Scenario(code, severity, data)`. `detect_all` returns
the list sorted by severity desc.

### Cold-start guard (no baseline week, 2026-06-05)

The freshness/novelty detectors read *absence from last week* as
news: `a1` ("la setmana anterior estava fora del top"), `a4` /
`a9` ("debut"), and `a10` ("estrena absoluta" / first-ever artist
in the territori's top history). On the **first ranking week of a
territori** — or the first time a new territori crosses the
`min_cancons_ranking_propi` floor and starts ranking — there is no
previous week, so *every* entry is trivially "new" and *every*
artist is trivially "first ever". Firing these there manufactures a
false-freshness claim for what may be long-standing catalogue (the
cold-start week stamped "debuta a la primera setmana" on four
territoris at once in the 2026-04-13 data).

The helper `_has_previous_week(territori, setmana)` checks whether a
`TopSetmanal` exists for the previous week. `a1`, `a4`, `a9` and
`a10` return `None` when it does not, so the composer falls back to
the baseline-free detectors (`a5`/`a6`/`a7`/…) or
`fallback_scenario`. No new phrasing is invented — the guard only
suppresses the unverifiable claims. Detectors that already require
explicit previous-week rows (`a2`, `a3`, `a8`, `a11`, `a12`, `a13`)
need no guard: they naturally do not fire without a baseline.

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

## Verified-recent-release fact (2026-06-05, wired 2026-06-06)

`social/narrative/freshness.py` computes a single boolean —
*is this `Canço` a verified recent release* — combining
`data_llancament` recency with a plausibility check that the stored
date is not obviously a reissue / alternate-version date.

Motivation (2026-06-05 measurement): `data_llancament` is the
Deezer/MusicBrainz date we hold, which for catalogue is frequently
the **reissue** date, not the original studio release. The
`age_factor` in `ranking/algorisme.py` therefore treats a reissued
1971 song as fresh, and the freshness beats (`a4`/`a6`) inherit
that — the canonical case being Pau Riba's «Noia de Porcellana»
(reissue dated 2026, artist deceased 2022).

`assess_recent_release(canco, *, ref_date, max_age_days=30)` returns
a `FreshnessVerdict(is_verified_recent_release, age_days, reasons)`.
A release is verified-recent when ALL hold:

1. `data_llancament` is known and within `max_age_days` of
   `ref_date` (future / same-day dates count as age 0);
2. the title carries no version marker (live / remix / remaster /
   reissue / acoustic / versió);
3. the artist was not deceased before the release date
   (`Artista.mb_end_date < data_llancament` → posthumous reissue).

`is_verified_recent_release(...)` is the boolean convenience
wrapper. The function is pure (reads `canco` + its `artista`, never
writes), so it works against stored `TopSetmanal` rows read-only as
well as in the live pipeline.

**Wired (2026-06-06).** The fact gates the freshness scenarios at the
detector, with NO new editorial text (logic + selection only):

- **`a6_canco_recent`** is a pure freshness scenario (every phrase
  asserts "just publicada" / "fa només N dies"). When its candidate is
  not `is_verified_recent_release`, the detector returns `None`: there
  is no non-freshness variant to fall back to, so suppression is the
  honest answer, and a movement/position scenario headlines. (Pau Riba's
  «Noia de Porcellana» — artist deceased before the reissue date — no
  longer says "just publicada"; SX3's genuinely new release keeps it.)
- **`a4_debut_alt`** still fires for a non-verified-recent debut (the
  "debuta al N" claim is chart-accurate) but sets `freshness_blocked` in
  its `data`. `registry.pick_phrase` then drops the phrase variants that
  carry the "first week" touch (`_FRESHNESS_MARKERS`) and keeps a4's
  pure debut-position variants. a4 has such variants, so no STOP / no
  new phrase.
- **`a1_outside_to_top1`** carries no release-freshness claim (all
  variants are chart-movement: "salt de … al 1r"); no change.

## Concentration demotion (2026-06-06)

`a5_artista_multiple` celebrates one artist holding ≥3 cançons in the
top. When that share becomes **domination** (`n_cancons ≥ 5`, or
`n_cancons / top_size ≥ 0.25` for small territoris), the detector
returns `None` instead. Rationale (sonda 2026-06-06): a5 has only
celebratory phrasing (no neutral variant), and a large concentration
can be a fusion/score artifact, so celebrating it is editorially wrong;
suppression lets a movement/position scenario take the headline. Below
the threshold a5 fires normally (a genuine good week). Maria Jaume's BAL
weeks (7-9 cançons) no longer headline with concentration celebration.
