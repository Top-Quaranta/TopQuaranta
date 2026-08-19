# Sessió stories de novetats — 2026-07-03 (referència local)

Resultat real de la sessió. No committat (nota de referència, com la resta
de `*.md` solts a l'arrel). El codi i l'spec sí que estan a main.

## Publicació real (Fase 4)

3 stories de novetats publicades a `@topquaranta` (nous_singles setmana
2026-06-22, feed media_id 18343289116216694), en ordre, ~20 s d'interval:

| Story | ig_media_id | permalink (rkey) | timestamp UTC |
|---|---|---|---|
| 1/3 | `18110410429756692` | .../stories/topquaranta/3933126884472279547 | 13:28:11 |
| 2/3 | `18104543747028723` | .../stories/topquaranta/3933127058653338673 | 13:28:34 |
| 3/3 | `18096786196965624` | .../stories/topquaranta/3933127251306112694 | 13:28:55 |

**Mencions efectives (5, 0 descartades):**

| Story | username | artista | cançó | coords |
|---|---|---|---|---|
| 1/3 | `auxili.oficial` | Auxili (princ.) | Tarrinetes al Sol | 0.42, 0.639 |
| 1/3 | `djtrapella` | Trapella (col·lab) | Tarrinetes al Sol | 0.58, 0.639 |
| 1/3 | `_ansia13` | Ànsia (princ.) | Tu Ho Sents | 0.50, 0.830 |
| 2/3 | `sr.corella` | Sr. Corella (princ.) | Tornaré | 0.50, 0.639 |
| 3/3 | `durumhawai` | Durum Hawai (princ.) | Com a Casa | 0.50, 0.639 |

Cap descartada: probe de container amb el set complet de cada story = 200 OK
per a les 3, confirmant que cap username va disparar el guard.

## Pool de mencions (Fase 2bis)

Les 11 cançons → 14 artistes (princ. + col·lab, dedup). Amb username:
**5 ara** (abans 3). Nous des de la vista staff nova: `sr.corella`,
`durumhawai`. Sense username: Som Núvol, Caïm Riba, Teresa Nogueron,
Confinaps, Andris el Sardo, Pilar Mena, AKA CITOS, JULS, La nena Samsó.

## Cobertura global (Fase 2.1 refrescada)

Pool top-40 PPCC + novetats 4 setmanes (dedup, 177 artistes):
**91/177 = 51.4 %** amb username (abans 74/177 = 41.8 %; +17, +9.6 pp).

## Codi + spec a main (PR #306, merge 4164b75)

- Fix de paritat: `payload.build_novetats` emet `artistes_noms`;
  `feed_redesign.build_album/build_singles` + `renderer._story_novetats`
  mostren col·laboradors (abans només principal). Commit 560fd2e.
- Paginació story: `renderer.render_stories_novetats` (N per pàgina,
  `_novetats_fit` manté portada 210px). `ConfiguracioGlobal.novetats_stories_per_pagina`
  default 4, editable a Config→Editorial, migració ranking/0032.
- Spec inert: `docs/architecture/social-stories.md` (split) i
  **`docs/decisions/0015-ig-collaborator-invitations.md`** ← per revisar
  abans de la sessió d'implementació.

## Contradiccions / troballes vs el que assumíem

1. **Self-collab (artista com a col·laborador de la seua pròpia cançó)
   NO és possible via ORM**: el senyal D5 (`music/signals.py`) el bloqueja.
   El cas "JULS a Cara de Cul" que vam veure a prod és homònims / dades,
   no el mateix pk. → El recompte principal+col·lab NO necessita restar
   overlap (ja disjunts per cançó). Afecta l'anotació `n_cancons_vives`
   (PR #305) i el pool de tags.
2. **La Graph API NO exposa `user_tags` de les stories en lectura**
   (provat: `fields=...` no torna els tags). La verificació post-publicació
   d'stories es limita a existència + permalink; els tags efectius es
   dedueixen de l'acceptació del container, no d'una lectura.
3. **Les stories NO admeten collaborators ni product tags** (només
   `user_tags`, des de 2025-07-09) — confirmat contra la doc de Meta. El
   sistema de col·laboradors (ADR-0015) és feed-only.
4. La caixa (`graph.instagram.com/v19.0`) accepta `user_tags` a
   `media_type=STORIES` sense problema amb el token actual (41 dies de
   marge quan es va publicar).
