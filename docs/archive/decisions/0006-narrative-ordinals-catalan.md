# ADR-0006 — Posicions com a ordinals catalans en lloc de `#N`

- **Status:** Accepted
- **Date:** 2026-05-21
- **Authors:** Miquel

## Context

El motor narratiu (`social/narrative/`) emitia posicions del top
amb la forma `#N` (p. ex. `«Sant Domingo Forever» #3`, `entra al
#5`). Instagram i Telegram interpreten `#3` com a hashtag clicable
i el rendaritzen en blau, fent que el text quedi tallat
visualment i que el clic porti a una cerca pública per «#3» —
exactament el contrari del que volem (volem destacar la posició,
no enviar trànsit a un hashtag genèric).

Bluesky i Mastodon respecten `#N` com a hashtag també, però
amb menys impacte visual. El comportament del newsletter és
benigne (HTML, no enllaça), però el text encara llegia com a
hashtag.

## Decision

Substituir totes les emissions `#N` per la forma ortogràfica IEC
de l'ordinal abreujat català: `1r`, `2n`, `3r`, `4t`, `5è`, `6è`,
…, `99è`. Implementació:

1. Nou helper `social.narrative.utils.ordinal_ca(n: int) -> str`.
   Coverage 1–99 (el top és 40; el marge no costa res). `n <= 0`
   llança `ValueError`. Sufix mapejat per als 4 primers, `"è"`
   per a tota la resta (forma IEC: `21è`, no `21r`).
2. Substitució mecànica a totes les plantilles dels dos bancs de
   frases:
   - `social/narrative/banks/hero.py` — 147 ocurrències en 8
     escenaris × 3 nivells (short/medium/long).
   - `social/narrative/banks/top5.py` — completing-line bank.
3. `social/narrative/scenarios.py`:
   - `detect_a1_outside_to_top1` i `detect_a3_fall_from_top1`
     emeten `posicio_anterior_str` / `posicio_nova_str` ja com a
     ordinal (`f"al {ordinal_ca(p)}"`).
   - Tres detectors (`a4_debut_alt`, `a6_artista_multiple`,
     `a8_*`) ara afegeixen `data["posicio_ordinal"]` paral·lel a
     `data["posicio"]` perquè les plantilles puguin interpolar el
     valor ja renderitzat sense duplicar la crida a l'helper.
4. `_detall(entry)` (top-5 long bank) renderitza la posició via
   `ordinal_ca`.

## Alternatives considerades

- **Zero-width-joiner abans del `#`** — funciona a Instagram però
  no a Telegram, i deixa caràcters invisibles al text. Descartada.
- **Posició entre parèntesis (`(3)`)** — neutralitza el hashtag
  però perd la lectura natural (`entra al (3)` no es llegeix).
- **Mantenir `#N` però descomptar als analytics** — no soluciona
  el problema visual del lector.

## Consequences

- ✅ El text dels 5 canals deixa de tenir hashtags falsos derivats
  de posicions.
- ✅ Lectura més natural en català periodístic
  (`entra al 5è`, `manté el 1r`).
- ⚠️ Les frases són ~1 caràcter més llargues per ordinal; el
  budget de 120 chars del tier `short` (Bluesky/stories) queda
  ajustat però es manté. Test
  `test_short_phrases_fit_under_120_chars` verifica l'invariant.
- ✅ Les plantilles ara reben `posicio` (int) i
  `posicio_ordinal` (str) als detectors a4/a6/a8 — patró
  consistent amb com ja ho feien `posicio_anterior_str` i
  `posicio_nova_str` als detectors a1/a3.

## Related

- Post-mortem `docs/post-mortems/2026-05-20-narrative-engine-collapsed.md`
- ADR-0007 — `@username` a Instagram (mateix sprint, paral·lel)
- ADR-0008 — Detectors a9–a12 expandits (mateix sprint)
