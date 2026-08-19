# Cohort maig — PAS 1 (esborrat 21) + PAS 2 (Viasona) + PAS 3 (opcions)

> **L'ABRIL (5 094) segueix 100 % EXCLÒS.** PAS 1 executat (21 esborrats);
> PAS 2 NOMÉS-LECTURA i **no concloent** (vegeu sota); PAS 3 sense acció.

## PAS 1 · Esborrat dur dels 21 PROBABLE FORA — FET i verificat

Re-verificats abans (els 21, tots `aprovat=False, pendent_review=True`, 0/0/0,
cap descartat), després esborrats amb `purgar_pendents_buits --execute
--pks=<21>` (intersecció amb la cohort 0/0/0, mai per regla ampla).

- **Esborrats: 21** (S3an, Gatillazo, Tha God Fahim, Black Milk, Oddisee,
  Sadat X, Blueprint, Godfather Don, Canibus, Raydar, Vector Seven, BARBARO
  URBANO VARGAS & AVENREC, Dano & Emelvi, Isla K, Emxnii, Rels B ft. Maikel
  Delacalle, Diles, Rels B/Dellafuente, Akauzazte, AZ, Smut Peddlers).
- `nb_similars_lastfm` recomputat en **5 orígens aprovats** afectats.
- **Verificació post:** pendents **34 181 → 34 160** (−21 exacte), descartats
  **10 047 intactes**, aprovats **2 006 intactes**. Els **891 PROBABLE
  CATALÀ no s'han tocat**.

Codi: command `purgar_pendents_buits` + opció `--pks` (PR #243, merged
`9156764`, desplegat; CI verda, 4 pins).

## PAS 2 · Oracle de Viasona — NO CONCLOENT (no s'ha esborrat res)

**Viasona no exposa un catàleg descarregable d'una sola fetch.** El recon:

- `sitemap.xml` → 404; `robots.txt` sense directiva `Sitemap:`.
- `/grups` = ~108 grups (subconjunt destacat, no el catàleg).
- Sí que hi ha índex alfabètic `/grups/lletra/{A..Z, numeros}` = **27
  pàgines**. Les vaig baixar (throttle 0,4 s, timeout 15 s, tallacircuits) →
  **només 666 claus de grup**.

**Dos problemes que invaliden l'encreuament:**

1. **Catàleg incomplet.** 666 és molt poc per a l'enciclopèdia de Viasona
   (milers de grups). Les pàgines per lletra estan **paginades/truncades**:
   no en tinc el catàleg sencer.
2. **Extracció contaminada.** El patró `grup/` apareix tant a l'enciclopèdia
   (`/grup/<slug>`) com a l'**agenda de concerts** (`/agenda/grup/<Nom>`, que
   llista artistes forans de gira). Resultat: dels 15 "coincidents", n'hi ha
   de **clarament no-catalans** — *Jackson Browne, Pablo López, OBK, Macaco,
   Saigon* — **falsos positius**.

→ **L'encreuament (15 coincidències sobre 23 985) NO és fiable** (incomplet +
sorollós). No el faig servir per a cap decisió. He **aturat** abans d'entrar
en un scrape complet paginat+desambiguat (seria el bucle que el tallacircuits
prohibeix). **Cap esborrat en aquest pas.**

## PAS 3 · Residu final + opcions (decisió de Miquel, sense acció)

- **Residu dubtós actual: 23 985** (maig, sense vora de similar, sense
  coincidència de nom amb seed/aprovats). El PAS 2 no l'ha pogut acotar de
  manera fiable.
- Conservats amb seguretat: **891 PROBABLE CATALÀ** (no es toquen).

Opcions (no n'executo cap):

1. **Deixar-lo dormir (recomanada ara).** La cascada està parada (només
   aprovats són font) i el fix de la llista d'staff (#241) ja amaga aquests
   pendents del soroll visual. Cost de mantenir-los ≈ baix; cost d'esborrar
   un català per error ≈ alt i irreversible (sense tombstone). El guany net
   ja segur (els 21) ja s'ha fet.
2. **Oracle català fiable, ben fet (si vols acotar el residu).** No amb una
   fetch de Viasona (no existeix), sinó:
   - un scrape *bounded* i correcte de Viasona: paginar cada
     `/grups/lletra/<L>` fins al final i **desambiguar** enciclopèdia
     (`/grup/`) vs agenda (`/agenda/grup/`), amb tallacircuits; o
   - una altra font catalana amb export real (p.ex. dump/àrea de dades), o
   - MusicBrainz per àrea (artist `area` = territori PPCC) com a senyal de
     catalanitat — consultable, però és per-artista (24 k crides → cal
     acotar abans).
3. **Recerca fina per-artista** (Deezer/Viasona/Bandcamp, mai Spotify) amb
   tallacircuits — **només** sobre un residu ja acotat per l'opció 2, mai
   sobre els 23 985 directament.

**No segueixo sense la teva decisió.** El guany net segur (21) ja és a prod;
la resta espera el camí que triïs.

---
Recordatori: FRONT 3 (recerca de les ~404 cançons) i FRONT 5 (rendiment
d'staff) segueixen per a les seues sessions pròpies.
