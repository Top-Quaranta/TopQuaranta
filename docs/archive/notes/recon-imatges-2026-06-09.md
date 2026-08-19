# Recon — generació d'imatges de novetats setmanals (2026-06-09)

> **NOMÉS LECTURA.** Worktree net `/tmp/tq-recon-imatges` des d'`origin/main`
> (`HEAD 56a43f4`), ja eliminat. Cap escriptura al repo, cap commit/push/PR,
> cap execució del pipeline de publicació, cap crida a API externa, cap imatge
> generada. Només lectura de codi i artefactes. Fitxer local de referència, NO
> és un commit.

---

## 0. TL;DR

- Tota la generació d'imatges viu a **`social/renderer.py`** (PIL/Pillow,
  2067 línies). Llenç únic **1080×1350 px** (feed 4:5), JPEG q90.
- **Novetats** = 2 tipus separats: **`nous_albums`** (publicat **dimarts**) i
  **`nous_singles`** (publicat **divendres**). Disparats pel cron via
  `publicar_social` (Instagram) + `publicar_canal` (Mastodon/Bluesky/Telegram).
- **Àlbums:** **1 àlbum per imatge** (slide), portada gran centrada. Màx **9
  àlbums** (9 slides + 1 portada = 10).
- **Singles:** **graella/llista de fins a 10 per imatge**, amb bin-packing
  dinàmic per no deixar slides amb 1-2 orfes. Màx 30 singles → fins a 3 slides.
- **Mateixa imatge per a tots els canals** (no hi ha resize per canal). L'única
  diferència per canal és **quantes slides s'adjunten**: IG carrusel complet
  (≤10), Mastodon/Bluesky **4**, Telegram **10**.
- Portada = **`Album.imatge_url`** (URL del CDN de Deezer), baixada i cachejada
  a disc. Fallback: tile de marca amb la 1a lletra del nom.
- Tipografies: Playfair Display (títols), Roboto (cos). Paleta: groc `#facc15`
  sobre tinta `#0a0a0a`; accents novetats blau `#0047ba` (àlbums) / vermell
  `#cf3339` (singles).
- **Cap imatge d'exemple de feed/novetats al repo ni en local** (només
  placeholders de newsletter i 3 HTML de preview de newsletter).

---

## 1. On viu la generació i qui la dispara

### Codi
- **`social/renderer.py`** — tots els builders PIL. Funcions clau de novetats:
  - `render_feed_novetats(tipus, setmana, items) -> list[Path]` (línia 1125) —
    orquestrador: portada + slides, desa JPEG q90, retorna `out[:10]`.
  - `_feed_novetats_portada(tipus, setmana)` (872) — slide 0 (portada).
  - `_feed_album_slide(item)` (962) — 1 àlbum per slide.
  - `_feed_singles_slide(items, page, total_pages)` (1033) — graella ≤10.
- **`social/payload.py`** — `build_novetats()` (171) tria els àlbums/singles de
  la setmana i serialitza els camps.
- **`social/cover_cache.py`** — `fetch()` baixa la portada de Deezer (cache
  SHA-1, TTL 7 dies, timeout 10 s).
- **`social/calendari.py`** — `CALENDARI` (slots → weekday/plataforma/tipus).
- **`social/colors.py`**, **`social/fonts.py`**, **`social/constants.py`** —
  tokens visuals.

### Commands
- **`social/management/commands/publicar_social.py`** — Instagram (feed + stories).
- **`social/management/commands/publicar_canal.py`** — Mastodon / Bluesky /
  Telegram / Newsletter (`--channel`).

### Cron (UTC, `deploy/cron.topquaranta`) — cadència real

| Dia | Hora | Command | Contingut |
|---|---|---|---|
| Dissabte | 09:30 | `publicar_social` | top_ppcc (feed+stories) |
| Dimecres | 09:30 | `publicar_social` | top_territorial A |
| Dilluns | 09:30 | `publicar_social` | top_territorial B |
| **Dimarts** | **10:00** | `publicar_social` | **nous_albums** |
| **Divendres** | **10:00** | `publicar_social` | **nous_singles** |
| Dimarts/Divendres | 10:10 | `publicar_canal --channel mastodon` | novetats |
| Dimarts/Divendres | 10:20 | `publicar_canal --channel bluesky` | novetats |
| Dimarts/Divendres | 10:25 | `publicar_canal --channel telegram` | novetats |

(Mastodon/Bluesky/Telegram també corren dilluns/dimecres/dissabte als minuts
:40/:50/:55 de les 09:00 per als tops. La **newsletter** NO passa per aquest
camí — només envia `top_ppcc` el diumenge via el seu propi cron.)

Les imatges **es generen cada vegada que es publica** (efímeres). Es desen a
`SOCIAL_CACHE_DIR/renders/` (prod: `/var/cache/topquaranta/social/renders/`,
servit per Caddy a `/static/social/*`). No es versionen.

---

## 2. Imatge d'àlbum — 1 àlbum per imatge ✅

Confirmat: **`render_feed_novetats` itera `items[:9]` i crida
`_feed_album_slide(item)` un cop per àlbum** (renderer.py:1133-1137). Per tant
**una imatge = un àlbum**. Màxim 9 àlbums (9 slides + portada = 10, límit del
carrusel d'Instagram).

### Maquetació `_feed_album_slide` (renderer.py:962)
- **Llenç:** 1080×1350, fons tinta `#0a0a0a` (`_feed_canvas`).
- **Logo marca** (dalt-esquerra): `_logo_block(img, x=60, y=50, width=270)` —
  SVG rectangular `logo-topquaranta-rect`, monocrom, aspect 4.93:1.
- **Pill de territori** (dalt-dreta): només icona (sense text), color del
  territori de l'artista (`colors.terr_color(ter)`), icona blanca 44 px,
  cantonada radius 22, a `x = FEED_W − 60 − ample_pill`, `y=44`. El territori
  surt de `item["artista_territori"]` (fallback `"PPCC"`).
- **Portada gran** centrada: `_cover(cover_url, 800, …)` → 800×800, cantonades
  arrodonides 24 px, enganxada a `((1080−800)/2, 160)` = `(140, 160)`.
- **Títol de l'àlbum:** Playfair **Bold 54 pt**, blanc, centrat, a `y=980`
  (truncat a `FEED_W−120`).
- **Artista:** Roboto **Regular 44 pt**, gris mutat `#9ca3af`, centrat, a
  `y=1054`.
- **Footer:** `"topquaranta.cat"` Roboto 20 pt, gris subtil `#6b7280`, centrat
  a `y = h−40`.

### Portada (font)
`cover_url = Album.imatge_url` (Deezer CDN; payload.py:250). Es baixa via
`cover_cache.fetch()` (renderer `_cover` → `fetch_cover`). **Nota:** les slides
de feed **NO** usen la portada local self-hostada (`_portada_local`); això
només ho fan les *stories* (`_story_cover`). Fallback si no hi ha URL o falla
la baixada: `_placeholder_cover` (tile `#1f2937` amb la 1a lletra del nom en
Playfair).

### Selecció dels àlbums de la setmana — `build_novetats` (payload.py:171)
- Finestra temporal: **`(última_publicació_del_mateix_tipus, publish_date]`**
  (`data_llancament` entre `last+1d` i el dia de publicació). 1a vegada:
  `publish_date − 7 dies`. Evita comptar dues vegades el dia frontera.
- Filtre tipus: `Album.tipus__iexact="album"` per `nous_albums`.
- Només àlbums amb **≥1 cançó `verificada=True, activa=True`** (`.distinct()`).
- Ordre: `-data_llancament, -id`. **Tall a `[:30]`** a la query; després
  `_feed_album_slide` només en pinta `[:9]`.
- Si `albums` buit → retorna `None` → el command marca el `SocialPost` com
  **`omes`** i surt net.

---

## 3. Imatge de singles — graella ≤10 amb bin-packing ✅

Confirmat: **`_feed_singles_slide` pinta fins a 10 files per imatge**
(`items[:10]`, renderer.py:1074) i `render_feed_novetats` reparteix
dinàmicament.

### "Flexibilitat" / quantes imatges (renderer.py:1138-1161)
- `n = len(items)` (màx 30 per la query).
- `n_slides = max(1, ceil(n/10))`; `per_slide = ceil(n / n_slides)`.
- Reparteix el més uniformement possible perquè **mai quedi una slide amb 1-2
  orfes**. Exemples del docstring:
  - ≤10 → **1 slide**
  - 11 → **6+5**, 13 → **7+6**, 20 → **10+10**
  - 21-30 → **3 slides**
- La darrera slide pot ser més petita (intencionat). Indicador de pàgina
  `"page/total"` només si `total_pages > 1`. Resultat final tallat a `out[:10]`.

### Maquetació `_feed_singles_slide` (renderer.py:1033)
- **Llenç:** 1080×1350, fons tinta.
- **Logo marca** dalt-esquerra (`_logo_block`, width 270).
- **Pill "Nous singles"** dalt-dreta: Roboto Bold 24, fons vermell
  `#cf3339`, text blanc, radius 18.
- **Regla d'accent** sota la capçalera: rectangle arrodonit
  `(60,130)→(FEED_W−60,138)`, vermell `#cf3339`.
- **Files** (geometria compartida via `social/constants.py`):
  - `LIST_TOP_Y = 170` (top de la 1a fila), `LIST_ROW_HEIGHT = 105`
    (76 px card + 29 px gap).
  - Card per fila: rectangle arrodonit radius 18, **tintat pel territori**
    (`colors.darken(ter_color, 0.78/0.85)` alternant parells/senars) — així el
    color "traspua".
  - **Portada** miniatura 80×80 (radius 12) a `(60, y)`.
  - **Icona de territori** 48 px a la dreta (`FEED_W−60−48`).
  - **Títol cançó:** Playfair **Bold 40 pt**, blanc, a `(175, y)`.
  - **Artista:** Roboto Regular 22 pt, gris `#9ca3af`, a `(175, y+54)`.
  - Tots dos truncats a l'ample disponible.
- **Indicador de pàgina** `"1/2"`: Roboto Bold 22, gris, centrat a `y=h−80`.
- **Footer** `"topquaranta.cat"` igual que àlbums.

### Portada de singles
Mateixa font (`Album.imatge_url`, Deezer) i mateix fallback. Selecció idèntica
a §2 però `Album.tipus__iexact ∈ {"single","ep"}` (EP es tracta com single).

### Portada (slide 0) de novetats — `_feed_novetats_portada` (renderer.py:872)
Comuna a àlbums i singles. Fons **tinta sòlida** (sense portada d'àlbum, perquè
novetats no s'ancoren a un sol artista). Pill dalt-dreta amb el text del tipus
("Nous àlbums" / "Nous singles") en l'accent (blau/vermell). Pill de logo
(ample 70% = 756 px, `x=84`, `y=944`) amb logo blanc monocrom sobre l'accent.
Pill de setmana a sota (blanc, text tinta, Roboto Bold 38).

---

## 4. Agrupació en la publicació — carrusel únic, slides variables per canal

Cada execució d'un tipus de novetats produeix **UNA publicació** (un
`SocialPost` per `(platform, tipus, territori, setmana)`, idempotent) que és un
**carrusel** de N imatges. **No** són posts separats.

| Canal | Command | Slides adjuntades | Mida imatge |
|---|---|---|---|
| **Instagram** (feed) | `publicar_social` | **carrusel complet** (portada + slides, ≤10) | 1080×1350 |
| **Mastodon** | `publicar_canal` | **`paths[:4]`** (portada + 3) — `_carousel_paths` | 1080×1350 |
| **Bluesky** | `publicar_canal` | **`paths[:4]`** (`embed.images` cap a 4) | 1080×1350 |
| **Telegram** | `publicar_canal` | **`paths[:10]`** (`MEDIA_GROUP_MAX=10`, media-group) | 1080×1350 |

> **No hi ha cap variant de mida per canal.** Tots reben exactament el mateix
> fitxer JPEG 1080×1350 q90; l'únic que canvia és **quantes** slides s'envien
> (`publicar_canal._carousel_paths` = `paths[:4]`; Telegram fins a 10). Cap
> client (`instagram_client`, `bluesky_client`, `telegram_client`,
> `mastodon_client`) fa `resize`/`thumbnail` — pugen el fitxer tal qual.
> Telegram envia per URL pública (`/static/social/*`), els altres pugen el blob.

**Gates abans de publicar** (publicar_canal.py): (1) màster
`distribucio_activa` + `<channel>_actiu` (`cfg.pot_publicar`), (2) idempotència
(`status==publicat` i no `--force`), (3) **matriu de distribució**
`MatriuPublicacio.actiu_per(channel, tipus)` → si off, `SocialPost=omes`.

---

## 5. Dades que consumeix cada imatge

Construïdes a `payload.build_novetats` → `items[]` (un dict per àlbum/single):

| Camp dict | Origen | Usat per |
|---|---|---|
| `nom` | `Album.nom` | títol de la slide |
| `slug` | `Album.slug` | (caption/enllaços) |
| `tipus` | `Album.tipus` | filtre album/single |
| `artista_nom` | `Album.artista.nom` | subtítol |
| `artista_slug` | `Artista.slug` | (caption) |
| `artista_instagram_url` | `Artista.instagram_url` | tagging IG |
| `artista_territori` | `Artista.territoris` (1r no-PPCC, fallback PPCC) | color card + icona |
| **`cover_url`** | **`Album.imatge_url` (Deezer CDN)** | portada |
| `album_deezer_id` | `Album.deezer_id` | (cover local newsletter) |
| `dies`, `segell`, `artista_en_top`, `primer_release`, `te_collab`, `segell_compartit` | flags batch `_novetats_flags` | motor narratiu de captions (no afecten la imatge) |

- **Font de la portada:** `Album.imatge_url` (string del CDN de Deezer,
  típicament `cover_xl` 1000×1000). Baixada+cache a `cover_cache.fetch()`.
- **Fallback si no n'hi ha:** `_placeholder_cover` — tile `#1f2937` (gray-800)
  amb la 1a lletra del nom en Playfair Bold gris. Mai bloqueja la publicació
  (un cover dolent → tile; cap excepció propaga).

> Camps de **Canco** que NO entren a la imatge de novetats: la slide d'àlbum/
> single només llegeix dades d'**Album** + el seu **Artista**. Les cançons
> només s'usen al filtre de selecció (`cancons__verificada/activa`) i als flags
> narratius. (Els tops sí que llegeixen Canco per entrada.)

---

## 6. Tokens visuals actuals (per comparar amb la Sèrie 7)

### Dimensions
- Feed: **1080×1350** (4:5). Stories: 1080×1920. JPEG **quality 90**.
- Portada àlbum: 800×800 (radius 24). Miniatura single: 80×80 (radius 12).
- Files singles: `LIST_TOP_Y=170`, `LIST_ROW_HEIGHT=105` (card 76 + gap 29).

### Tipografies (`social/fonts.py`, TTF vendoritzats a `social/fonts/`)
- **Playfair Display Bold** — títols (`display_bold`). Àlbum títol 54 pt;
  single títol 40 pt; placeholder lletra.
- **Roboto Regular** — cos/artista (`sans_regular`). Àlbum artista 44; single
  artista 22; footer 20.
- **Roboto Bold** — pills/labels (`sans_bold`). Pills 24-38.
- Famílies extra (només stories Step 3b/3c, **no** a les novetats de feed):
  Anton, Bricolage Grotesque XBold, Instrument Serif Italic, Playfair XBold.
- Fallback DejaVu si falta el TTF (no peta en dev).

### Paleta (`social/colors.py`, mirall de mm-design / SPA `tq-*`)
- Fons: **`#0a0a0a`** (tq-ink). Blanc `#ffffff`.
- Groc primari **`#facc15`** (tq-yellow); groc fosc `#ca8a04`.
- Text mutat `#9ca3af` (gray-400, 4.5:1 sobre tinta); subtil `#6b7280`.
- Cards: `#1f2937` (gray-800), `#374151` (gray-700).
- **Accents novetats:** àlbums **blau `#0047ba`** (`COLOR_NOVETATS_ALBUMS`),
  singles **vermell `#cf3339`** (`COLOR_NOVETATS_SINGLES`). Semànticament
  editorials (no territorials), tot i coincidir amb BAL/VAL avui.
- Colors per territori `TERR_COLORS` (PPCC verd `#427c42`, CAT amber `#8a6900`,
  VAL `#cf3339`, BAL `#0047ba`, AND violeta, CNO teal, FRA taronja, ALG rosa,
  ALT/CAR gris). Helpers: `terr_color`, `darken`, `mix`, `best_text_on`.
- Radius pills: 12 (mm `--mm-radius-lg`), 18, 22 segons l'element.

> Observació per al redisseny: les **slides de novetats** són força "planes"
> respecte a les **stories Step 3b/3c**, que ja tenen un sistema editorial
> molt més ric (radials, Anton/Bricolage/Instrument, paletes per territori
> `story_palette`). La distància cap a una "Sèrie 7" més editorial és gran a
> feed-novetats i petita a stories: el llenguatge visual ambiciós ja existeix,
> però **no s'aplica a àlbums/singles de feed**.

---

## 7. Imatges d'exemple generades (repo / local)

- **Repo:** CAP imatge d'exemple de feed/novetats versionada. Els únics PNG
  tracked relacionats amb publicació són de **newsletter**, no de feed:
  - `web/static/web/img/newsletter/cover_placeholder.png`
  - `web/static/web/img/newsletter/logo_email.png`
  - `web/static/web/img/og-default.png`
- **Local (Mac, `~/Claude/TopQuaranta/`):** només 3 previews HTML de
  **newsletter** (no imatges de feed):
  - `newsletter_preview_2026-06-01.html`
  - `newsletter_preview_collab_2026-06-01.html`
  - `newsletter_preview_links_2026-06-01.html`
- **No** hi ha `/tmp/tq_social/renders/` al Mac. Les imatges reals de feed són
  efímeres i viuen només al servidor a `/var/cache/topquaranta/social/renders/`
  (servides a `/static/social/*`), regenerades a cada publicació; no es
  versionen ni hi ha snapshots al repo.
- Per veure'n una sense publicar res: `publicar_social --dry-run` o
  `publicar_canal --dry-run` renderitza els JPEG al cache sense pujar-los — NO
  executat en aquesta sessió (read-only).

---

## Apèndix — fitxers/línies citats

```
social/renderer.py:1125  render_feed_novetats   (orquestrador novetats)
social/renderer.py:962   _feed_album_slide      (1 àlbum/slide)
social/renderer.py:1033  _feed_singles_slide    (graella ≤10)
social/renderer.py:872   _feed_novetats_portada (slide 0)
social/renderer.py:292   _cover / 277 _placeholder_cover / cover_cache.fetch
social/payload.py:171    build_novetats         (selecció + camps)
social/calendari.py:50   CALENDARI              (dimarts àlbums, divendres singles)
social/management/commands/publicar_social.py   (Instagram)
social/management/commands/publicar_canal.py:251 _carousel_paths (paths[:4])
social/constants.py:39   LIST_ROW_HEIGHT=105 / LIST_TOP_Y=170
social/colors.py · social/fonts.py              (tokens)
deploy/cron.topquaranta:296-337                 (cadència)
```

Cap comanda d'escriptura ni de publicació executada. Worktree eliminat.
