# TopQuaranta · Feed — Fitxa de tokens per al port a PIL

Llenç **fix 1080×1350** per a TOTS els canals. Als canals truncats (Mastodon, Bluesky) només es veuen **4 slides**, així que la **portada i les primeres han de transmetre el missatge soles**. El que varia per canal és *quantes* slides es mostren, mai la mida.

Valors exactes (hex, mides, pesos, interlletratge, coordenades) a **`feed-tokens.json`** — és la font de veritat, mesurada del render real. Aquest document explica les regles que el JSON no captura bé en taula.

---

## Sistema (canon de les stories)

**Veus tipogràfiques**
- **Anton** — crits curts: NOVETATS, ÀLBUMS/SINGLES, capçaleres, abreviatures de territori, pills.
- **Playfair Display** — glòria editorial: títol de l'àlbum (i res més al feed).
- **Instrument Serif _italic_** — xiuxiueig: dates, peus, nom de territori als singles.
- **Bricolage Grotesque** — mobiliari: artistes, metadades, indicador de pàgina.

**Decisió resolta:** el **territori condueix la paleta**. Àlbum vs single es distingeix per **etiqueta + layout**, mai per color de tipus. (La comparativa color-per-tipus s'ha descartat.)

**Ancoratges de marca:** ink `#0a0a0a` · groc `#facc15` · verd PPCC `#427c42`. Cada territori afegeix un **`deep`** (tint fosc, fons de banda/xip/fila) i un **`accent`** (brillant, per a text/icona) — els 7 al JSON.

---

## Les tres peces

1. **Portada del carrusel** — *Camp verd*. Fons verd PPCC amb gra, logo blanc, "NOVETATS / ÀLBUMS|SINGLES" en Anton, pill SETMANA 39. Dues germanes per `kind`: `albums` (dimarts) i `singles` (divendres) — idèntiques tret de l'etiqueta i la cadència.
2. **Àlbum individual** — *Banda editorial*. Ink + portada heroi 660×660 centrada; **banda inferior tintada pel `deep` del territori** amb títol Playfair + artista Bricolage + abreviatura/nom del territori. Etiqueta discreta "NOU ÀLBUM" en Anton (color `accent`) dalt-dreta.
3. **Graella de singles** — *Bloc d'accent*. Ink; capçalera "NOVETATS · SINGLES" (Anton, es llig sola); files amb **xip de territori `deep`** a l'esquerra (abreviatura en `accent`), miniatura 72, títol+artista Bricolage, nom curt de territori en Instrument italic a la dreta; indicador de pàgina elegant al peu.

---

## Gra de paper

Soroll monocrom (equivalent a `feTurbulence fractalNoise`, `baseFrequency 0.85`, `numOctaves 2`, escala de grisos) fusionat sobre el fons. En PIL: generar soroll gris i fusionar amb el mode i opacitat indicats per capa (portada 0.14 soft-light · pàgina d'àlbum/singles 0.08 overlay · banda d'àlbum 0.12 soft-light només dins la banda).

## Slot del logo (mai re-tipografiat)

Sempre l'**asset SVG/PNG real**, mai text. Tres tractaments:
- **Blanc** (`brightness(0) invert(1)`) sobre verd/ink — el cas de les 3 peces.
- **Negre** (`brightness(0)`) sobre groc.
- **Color original** només sobre ink.

Ràtio d'aspecte **≈ 4.93** (ample = alçada × 4.93). Posicions i altures exactes al JSON.

## Regla de fallback (sense portada)

Quan `cover == null`, el tile substitueix la portada **a la mateixa mida** (660 a l'àlbum, 72 al single):
- Fons = `territori.deep`.
- **Inicial** (1a lletra del títol) en Anton, color = `territori.accent`, mida = 0.5 × tile, centrada.
- Keyline interior 2px `accent` opacitat 0.4, inset 0.06 × tile.
- Peu "TOPQUARANTA" en Anton, mida 0.04 × tile, letterSpacing 4, `rgba(255,255,255,0.5)`, a 0.07 × tile del fons.

## Paginació dels singles

Fins a **10 files per slide**. El sistema reparteix per evitar slides amb 1-2 files òrfenes (p.ex. 14 → 7+7, no 10+4). Amb més d'una slide, l'indicador de pàgina mostra `NN / NN` (zero-padded) + punts (l'actiu, groc i allargat).

---

**Fitxers del sistema net:** `feed-kit.jsx` (paletes + components compartits) · `feed-cover.jsx` · `feed-album.jsx` · `feed-singles.jsx` · `feed-data.js` (dades de mostra; substituïu per les reals — `cover: null` dispara el fallback). Canvas viu: `TopQuaranta - Feed.html`.
