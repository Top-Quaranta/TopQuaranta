# Investigació — re-estructurar les stories del top en trams de 10

> Nota local (untracked), 2026-08-12. Investigació prèvia al canvi
> 40-11 / 10-4 / 3-2 / 1 → 40-21 / 20-11 / 10-4 / 3-2 / 1.
> NOMÉS recon: cap canvi de codi.

## 1. Estat actual

Set editorial PPCC (`social/renderer.py::render_stories_ppcc`, l. 1700):

| # | Slide | Builder | Slice | Geometria |
|---|-------|---------|-------|-----------|
| 0 | intro | `_story_intro_ppcc` | — | «EL TOP / 40 / D'AQUESTA SETMANA» |
| 1 | **mosaic 40→11** | `_story_top_mosaic` | `entries[10:40]` | **5×6 = 30 covers de 150 px** |
| 2 | grid 10→4 | `_story_top_grid` | `entries[3:10]` | 2 col ×3 files + #4 centrat, covers 210 px |
| 3 | podi #3-#2 | `_story_podi` | `entries[1:3]` | 2 covers centrats 300 px |
| 4 | hero #1 | `_story_hero` | `entries[0]` | clímax groc |
| 5 | novetats (opcional) | `_story_novetats` | — | ≤3 estrenes; s'omet si no n'hi ha |
| 6 | outro | `_story_outro_ppcc` | — | «EL TOP 40» + CTA |

Territorial (`render_stories_territorial`, CAT/VAL/BAL en rotació):
mateixa gramàtica amb degradació per omissió — mosaic si `n>10`,
grid si `n>3`, podi si `n>1`, hero si `entries`.

Tota la geometria és DATA a `social/story_design/story-tokens.json`
(`mosaic.cols=5`, `mosaic.display_cap=30`, `grid.display_cap=7`…).

El diagnòstic «enforfoguida» és exactament el mosaic: 30 caràtules de
150 px en una sola story, la més densa de tot el sistema.

## 2. La proposta

Partir el mosaic en dos trams: **40→21** (20 ítems) i **20→11**
(10 ítems). El set PPCC passa de 7 a 8 slides (6→7 sense novetats).

Precedent intern: el **feed carousel ja va per blocs de 10**
(`renderer.py:518` — `blocks = [(30,40),(20,30),(10,20),(0,10)]`).
El canvi alinea stories amb feed.

## 3. Tot el que toca

### 3.1 Renderer (`social/renderer.py`)

- `render_stories_ppcc`: `entries[10:40]` → `entries[20:40]` +
  `entries[10:20]` (dues emissions).
- `render_stories_territorial`: noves condicions de degradació —
  tram 40-21 si `n>20`, tram 20-11 si `n>10`.
- `_story_top_mosaic`: parametritzar (cols, display_cap, títol de
  secció, rang de fallback del badge `40 - idx`) o fer dues variants.
  El fallback `posicio or (40 - idx)` assumeix el tram sencer.
- `story-tokens.json`: seccions de tokens noves per a les dues
  geometries (p. ex. 4×5 covers ~200 px per al 40-21; 2×5 covers grans
  per al 20-11 — DECISIÓ DE DISSENY pendent).
- Títols de secció a decidir (ara: «EL TOP» mosaic, «ENS ACOSTEM AL
  CIM» grid).
- Intro, outro, podi, hero, novetats: **intactes** (el top segueix
  sent de 40; «EL TOP 40» de intro/outro continua sent correcte).

### 3.2 Etiquetatge IG — EL PUNT MÉS DELICAT

`publicar_social.py::_story_tags` (l. 759) ha de reflectir EXACTAMENT
l'emissió del renderer: mateixes slices, mateixa reversió d'ordre de
dibuix, mateixes condicions de degradació. El guard de seguretat
(l. 883) fa que un mismatch tags↔slides publique **tot el set sense
cap menció** (warning, no error) — el mode de fallada és silenciós.
Renderer i tagger s'han de canviar al MATEIX commit.

- `_pos_story_mosaic` (l. 195) assumeix 5 columnes i pas de fila
  0.098: calen funcions d'ancoratge noves per a cada layout nou.
- **Benefici fort i mesurat**: Meta capa a 20 `user_tags`/imatge
  (`USER_TAGS_CAP`). La verificació real del 2026-07-15 (BAL) va
  confirmar el mosaic **saturat a 20/20** amb 26 caràtules dibuixades
  → artistes visibles sense menció. Amb trams de 20 i 10 entrades,
  cada slide cap dins del límit: ~+10 mencions/set i marge per als
  col·laboradors (round-robin de `_tags_for_entries`).

### 3.3 Resumibilitat (post-mortem story-3, 2026-07-20)

`metadata.published_slides` desa `{idx, name, sid}` per **índex** de
slide. Un set en ERROR parcial amb l'estructura vella, reintantat
després del deploy de la nova, resumiria amb els índexs desplaçats
(mapatge de slides equivocat). Mitigació al desplegar: confirmar que
no hi ha cap `SocialPost` de story en ERROR pendent (o primer run
amb `--force`, que ignora l'estat de resume). Cal dir-ho al PR.

### 3.4 Tests que fixen l'estructura

- `social/tests/test_renderer_ppcc_stories.py` — `len(paths)==7/6`,
  ordre d'emissió (spy), slices per builder.
- `social/tests/test_story_mentions.py` — `len(tags)==7/6`,
  alineació 1:1 tags↔slides (PPCC i territorial), degradació,
  resumibilitat (`{0,1,2,4,5}`).
- `test_story_synth.py` — NO afectat (només el headline narratiu).
- `test_publicar_social.py` — majoritàriament feed; revisar de pas.

### 3.5 Docs (gate CI `docs-coherence`)

`docs/architecture/social-stories.md` descriu el set de 7 slides
explícitament (llista numerada, mencions per tram, degradació).
Actualització OBLIGATÒRIA al mateix PR o el CI falla. Vigilar el gate
`docs-size` (el doc té 165 línies, marge fins a 400).

### 3.6 Coses que NO toquen (verificat)

- **Feed carousel i cartell**: sense canvi (ja van per blocs de 10).
- **Captions/narrativa**: les stories no porten caption; el hero
  headline (13 detectors) és independent de l'estructura.
- **Analytics**: el comptador és 1 per set (`n=1`), independent del
  nombre de slides; `n_slides` a metadata és purament informatiu.
- **Calendari/slots**: un slot = un set; res a canviar.
- **Col·laboracions IG**: only-feed (les stories accepten user_tags
  però no collaborators — límit de la Graph API).
- **SPA staff**: cap referència a `n_slides`/`story_ids` al frontend.
- **Stories de novetats**: pipeline separat
  (`render_stories_novetats`), intacte.
- Únics callers dels renderers de story: `publicar_social.py`
  (cap endpoint staff ni cap altre command).

## 4. Consideracions de disseny pendents (abans de codificar)

1. **Layout del 40-21** (20 ítems): 4×5 amb covers ~200 px sembla el
   natural (vs 150 px actuals — ja guanya aire).
2. **Layout del 20-11** (10 ítems): 2×5 amb covers grans, o reutilitzar
   la gramàtica del grid 10-4? Jerarquia creixent cap al #1.
3. **Trams parcials als territorials**: amb el col·lapse de Last.fm
   (2026-07-27) els tops VAL/BAL s'encongeixen; un top de n=25 posaria
   només 5 covers al tram 40-21 (layout mig buit). La degradació per
   omissió ja ho cobreix per a n≤20, però el rang 21-29 quedarà
   escampat — acceptar-ho (com ara) o exigir un mínim per emetre el
   tram.
4. Títols de secció dels dos trams nous.
5. Cost marginal: +1 JPEG i +1 story per run — trivial, però el disc
   és al 90% (investigació paral·lela en curs).

## 5. Forma del canvi (quan es faça)

Un sol PR: renderer (builders + tokens) + `_story_tags`/`_pos_*` +
tests + `docs/architecture/social-stories.md`. Validació visual
prèvia amb renders locals (patró `render_samples.py` de
`top_design/`/`feed_design/`; `story_design/` encara no en té — és el
moment d'afegir-lo). Desplegar amb la finestra neta de stories en
ERROR (§3.3).
