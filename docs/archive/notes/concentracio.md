# Concentració d'artista/àlbum al top — fan la feina les penalitzacions? (2026-06-10)

> Investigació NOMÉS-LECTURA contra prod. Cap escriptura, cap Spotify.
> Mesura: concentració del top actual (setmana 2026-06-01) i si les
> penalitzacions de monopoli compleixen. **No canvio res — és decisió teua.**

## Penalitzacions vigents (`ConfiguracioGlobal`)

- `penalitzacio_album_per_canco` = **0,25** → cada cançó addicional del mateix
  àlbum multiplica el score per ×0,75.
- `penalitzacio_artista_per_canco` = **0,20** → cada cançó addicional del mateix
  artista ×0,80.
- `coeficient_penalitzacio_top` = 0,04 (penalització per setmanes prèvies, no de
  concentració). El soft-cap d'outliers (#196) és **off** i ataca la MAGNITUD,
  no la multiplicitat.

Són penalitzacions **multiplicatives decreixents**, no un límit dur.

## Mesura (top 40 per territori, setmana 2026-06-01)

| Territori | N | Artistes diferents | Àlbums diferents | HHI artista | HHI àlbum | Artista màx | Àlbum màx |
|---|---|---|---|---|---|---|---|
| **PPCC** | 40 | 27 | 31 | 0,053 | 0,045 | Maria Jaume 5 | Sant Domingo Forever 5 |
| **CAT** | 40 | 30 | 34 | 0,044 | 0,036 | La Ludwig Band 4 | Pel Barri Es Comenta 4 |
| **VAL** | 40 | 20 | 31 | 0,065 | 0,043 | Low Kost 5 | Brega 4 |
| **BAL** | 40 | 17 | 23 | **0,105** | **0,081** | **Maria Jaume 8** | **Sant Domingo Forever 8** |

(HHI = índex Herfindahl sobre quota de slots; com més alt, més concentrat.)

## Lectura

- **CAT, PPCC i VAL: concentració ben controlada.** 27-30 artistes diferents
  sobre 40, HHI baix (0,04-0,065), cap artista passa de 5 cançons. Les
  penalitzacions **fan la feina**: comprimeixen sense ofegar la diversitat.
- **BAL és l'excepció.** Escena petita (només 17 artistes al top 40): **Maria
  Jaume (8) + Joan Miquel Oliver (7) ocupen 15 dels 40 slots (37,5 %)**, i dos
  àlbums (*Sant Domingo Forever* 8, *Roïssos* 5) en sumen 13. HHI artista 0,105
  (2× el de CAT).
- **Les penalitzacions estan actives i comprimeixen**, però en un catàleg prim
  com BAL **no posen sostre**: ×0,8 per cançó addicional decau, però un artista
  amb moltíssimes escoltes brutes sobreviu fins a 8 cançons perquè **no hi ha
  prou material alternatiu elegible** que el desplaci. No és que la penalització
  falli; és que multiplica un nombre que segueix sent el més gran de l'escena.

## Recomanació (decisió teua — no aplicada)

La concentració de BAL **reflecteix escoltes reals** (Maria Jaume ÉS dominant a
Balears), així que no és un bug; és una tensió editorial diversitat-vs-fidelitat.

Si l'objectiu és més diversitat visible al top:

1. **Sostre dur per artista/àlbum** (p. ex. màx 4-5 cançons/artista i /àlbum per
   top) — el més directe i predictible; la cua s'omple amb el següent elegible.
   Atenció: amb el `min_escoltes_top` actual, a BAL pot deixar el top més curt.
2. **Penalització més agressiva** (pujar `penalitzacio_artista_per_canco` cap a
   0,3-0,35) — més suau que un sostre, però afecta tots els territoris; caldria
   verificar que no aplana CAT/VAL on ja està bé.
3. **No tocar res** — acceptar que una escena petita es vegi dominada pels seus
   caps de cartell és una decisió editorial defensable.

Si es vol provar (1) o (2), recomano fer-ho **gated/off-by-default** i mesurar
l'efecte a BAL sense degradar CAT/PPCC/VAL, igual que el soft-cap (#196). Cap
canvi fet aquí.
