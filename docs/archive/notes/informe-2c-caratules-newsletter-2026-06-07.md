# Informe 2c — Caràtules de la newsletter cauen al logo

Data: 2026-06-07. Read-only (codi). Sense canvis. Exemple: tema de Rosalía amb caràtula → la newsletter mostra el logo.

## Divergència en una frase

La **web** renderitza la URL del CDN de Deezer guardada a `Album.imatge_url` (sempre poblada, amb fallback en runtime a Deezer via `onError`). La **newsletter** ignora aquesta URL i exigeix que existeixi un **fitxer JPG auto-allotjat al disc** a `/var/topquaranta/portades/album/<deezer_id>-<mida>.jpg`; quan el fitxer no hi és, retorna el **logo placeholder**, sense fallback a Deezer.

## Camí newsletter (el trencat)

- `social/management/commands/publicar_canal.py --channel newsletter` → `comptes/newsletter.py::send_top_newsletter`.
- Construcció de la portada per fila: `comptes/newsletter.py:66` (`_enrich_entry`), `:91`, `:117`:
  `"cover": album_cover_url(e.get("album_deezer_id"), mida)` — usa **només** `album_deezer_id`, mai `cover_url`.
- El payload (`social/payload.py::build_top`) exposa **dos** camps del **mateix** àlbum: `cover_url` (URL Deezer, `payload.py:132`) i `album_deezer_id` (`payload.py:135`). La newsletter no llegeix `cover_url`.
- Resolutor + fallback: `comptes/newsletter_covers.py::album_cover_url` (línies 32-44):
  ```python
  if not deezer_id: return placeholder_url()           # 36-37
  present = manager.path_for("album", id, mida, "jpg").is_file()   # 39
  if present: return f"{site}/portades/album/{id}-{mida}.jpg"      # 43
  return placeholder_url()                              # 44  ← LOGO
  ```
  `placeholder_url()` = `/static/web/img/newsletter/cover_placeholder.png` (logo de marca sobre tinta).

## Camí web (el que funciona)

- Llistes: `web-react/src/pages/HomePage.jsx:164-166` → `deezerImg(e.album.imatge_url, 120)` (`web-react/src/lib/img.js:32-37`), només reescriu el segment `WxH`, sense disc.
- `web-react/src/components/Cover.jsx`: prova `/portades/` primer però té **fallback a Deezer** que la newsletter no té: `onError` (línia 73) → re-renderitza `deezerImg(imatgeUrl, size)` (43-52).
- Camp canònic: **`Album.imatge_url`** (Deezer `cover_xl` 1000×1000), poblat per a qualsevol àlbum amb metadades ingestades → a la pràctica sempre present.

## Veredicte d'hipòtesis

- (a) camp buit/incorrecte → **parcial**: la newsletter llegeix un `album_deezer_id` vàlid (mateix àlbum), però **ignora el `cover_url` poblat** a favor d'una comprovació de disc.
- (b) Deezer >1400px 403 → **refutada**: la newsletter no construeix mai cap URL Deezer.
- (c) `or LOGO` → **confirmada**: `comptes/newsletter_covers.py:44`.
- (d) auto-allotjat vs Deezer → **confirmada, causa arrel**: la newsletter depèn només del fitxer portada al disc; per a un tema que acaba d'entrar al top, el cron nocturn `descarregar_portades` pot no haver generat encara `album/<deezer_id>-{250,500}.jpg` → `is_file()=False` → logo. Les mides demanades (250, 500) sí coincideixen amb `PORTADES_VARIANTS` (`topquaranta/settings/base.py:62`), o sigui que un àlbum *generat* es trobaria; el forat és purament "fitxer encara no generat".

## Conclusió FASE 3

És un **bug clar de divergència** (falta una grada de fallback), no un bug de camp/fila incorrecte. Fix direccional: quan la portada local no existeix, fer fallback a la URL Deezer (`cover_url`, que `build_top` ja proporciona a la mateixa entrada) abans del placeholder — mirall del `onError` de `Cover.jsx`. La newsletter ja rep `cover_url` al payload, però `_enrich_entry` no el passa al resolutor.

**STOP lleu (decisió de política de fallback)**: el comentari `newsletter_covers.py:5-9` justifica el self-hosting perquè els clients de correu carreguen el CDN de Deezer menys fiablement. Mostrar el logo en lloc d'una caràtula present-però-imperfecta és estrictament pitjor, així que una grada de fallback a Deezer està justificada — però com que toca la **política** de portades de la newsletter, ho deixo per a confirmació abans d'implementar. (Alternativa només-ops: garantir que `descarregar_portades` drena tots els àlbums del top abans de l'slot de dissabte; deixa la fragilitat sense-fallback.)
