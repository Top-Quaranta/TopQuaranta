# Conflacions entre cançons APROVADES + homònims — 2026-06-11

> **NOMÉS BD, cap crida externa.** Consulta read-only sobre prod.

## Veredicte (TL;DR)

1. **Conflacions de `spotify_artist_id` sobre cançons APROVADES: ZERO casos
   Crim-style.** L'única artista amb >1 `spotify_artist_id` entre les seues
   cançons aprovades és **`dani6ix & IZZKID`** (un **duo**), i és un **split de
   crèdit/featuring**, no dos artistes nostres compartint perfil Deezer. → **
   L'estratègia d'encaminador es queda dissenyada al calaix; NO es construeix.**
2. **Homònims (mateix nom, ubicacions distintes): l'únic cas Crim-style amb
   contingut real és el mateix Crim.** Hi ha un segon `Artista` "Crim"
   (pk=3663, Sant Andreu de la Barca, **pendent, sense deezer_id, 11 cançons
   verificades**) enfront de l'aprovat pk=2908 (Tarragona, deezer 347962). La
   resta de noms duplicats són files pendents buides, duplicats de la mateixa
   ubicació, o artistes separats que **ja tenen el seu propi deezer_id** (per
   tant aprovables, no bloquejats).

---

## Part 1 — Conflacions sobre cançons aprovades

**Població correcta:** per cada artista, els `spotify_artist_id` **principals
distints** NOMÉS entre les seues cançons amb `verificada=True, activa=True` i
`SpotifyMetadata.enrichment_status ∈ {found, manual}`.

**Resultat: 1 artista amb >1 id** (i és un featuring, no homònim):

| pk | nom | ids | deezer | lectura |
|---|---|---|---|---|
| 7309 | **dani6ix & IZZKID** | 2 | 301891361 | **duo + featuring**, no homònim |

- `id=3uvPbZvw5KBjF8WRkMsjcz` (11 tracks, tots ISRC `ES84D…`): Arte, Classe,
  Kit Kat, M'enamora, Morena, Nòria, On Volíem Estar, Tantes…
- `id=2YFW9Z60cXbavpNZvvJnxe` (1 track, ISRC `QMDA6…`): **Ceo**

A ull: el nom és un **duo** ("dani6ix & IZZKID"); 11 temes van al perfil Spotify
del duo i 1 ("Ceo", ISRC d'una distribuïdora diferent) va a un id distint — un
crèdit de col·laboració/solista d'un dels dos membres, **no** dos artistes
nostres fusionats sota un Deezer. **No és un Crim.**

> ⚠️ **Per què Crim NO surt ací:** aquesta lent mesura la dispersió *dins* d'un
> mateix `Artista`. El cas Crim és **entre dos `Artista`** (homònims), no dins
> d'un — per això cal la Part 2. A més, els tracks del segon Crim no estan sota
> el `pk` aprovat.

**Conclusió Part 1:** zero casos nous → **encaminador al calaix.**

---

## Part 2 — Homònims (mateix nom a la nostra BD)

**68 noms** apareixen en >1 fila `Artista` (case-insensitive). La gran majoria
són artistes **realment distints** que comparteixen un nom curt, cadascun amb el
seu **propi deezer_id** → aprovables, **no** bloquejats. El patró Crim-style que
importa és: **aprovat + un homònim PENDENT que NO té deezer_id propi** (no es pot
aprovar sense un àncora distinta) **i ubicació diferent**.

### Casos amb contingut (el que importa)

| nom | aprovat (loc · deezer · cançons_apr) | pendent (loc · deezer · cançons_apr) | lectura |
|---|---|---|---|
| **Crim** | pk=2908 · Tarragona · 347962 · 2 | **pk=3663 · Sant Andreu de la Barca · — · 11** | **CRIM-STYLE real.** El 2n Crim té 11 cançons verificades però l'`Artista` és pendent i sense deezer propi. Ubicació distinta. **Aquest és EL cas.** |
| Lluc | pk=2409 · Cardedeu · 10861100 · 1 | pk=3779 · La Ràpita · — · 0 | homònim buit (0 cançons al pendent) — baixa prioritat |
| Llum | pk=2875 · Mataró · 1177597 · 6 | pk=4350 · Alcoi · — · 0 | homònim buit (0 cançons al pendent) |
| Deliri | pk=3881 · Gandia · 10160644 · 0 | pk=4201 · Sabadell · — · 0 | tots dos buits |

### Casos que NO són Crim-style

- **Pendent amb deezer_id PROPI** (artista separat, aprovable sense col·lisió):
  Cloe (pk=5334 deezer 1371273), Invers (pk=42763 deezer 141205802), Jim (5
  pendents, deezers distints), Nil Moliner (pk=35639 deezer 284391551), i la
  major part dels 68 (Heyden, JG, Lumi, Mimi, Sidonie, Tasi, …).
- **Mateixa ubicació = duplicat, no homònim** (pendent sense deezer + mateixa
  loc que l'aprovat): Alosa (Barcelona/Barcelona), Erm (Barcelona), Fat Chets
  (Barcelona), Vadebo (València). Probablement files pendents redundants del
  mateix artista, no homònims reals.

### Detall del cas Crim (per a destriar a ull)

```
nom='Crim'
  pk=3663  aprovat=False  deezer=[]         cançons_apr=11  tot=11  loc=Sant Andreu de la Barca
  pk=2908  aprovat=True   deezer=[347962]   cançons_apr=2   tot=6   loc=Tarragona
```

El segon Crim (pk=3663) ja té 11 cançons verificades penjades però la fila
`Artista` està pendent i sense deezer_id. És exactament el patró que la recon
(`deezer-compartit-recon.md`) anticipava: un homònim que **no es pot tancar net**
mentre no tinga un àncora Deezer pròpia distinta del 347962 de l'aprovat. **La
decisió de com separar-los és de Miquel** (cap canvi fet ací).

---

## Síntesi per a la decisió

- **Encaminador spotify_artist_id:** **zero casos nous** sobre cançons aprovades
  → **roman dissenyat al calaix, no es construeix.** (El featuring del duo no el
  justifica.)
- **Homònims:** **Crim és l'únic cas Crim-style amb contingut** (un 2n `Artista`
  pendent amb 11 cançons i sense deezer). Els altres 67 noms duplicats no
  necessiten res: o tenen deezer propi (aprovables), o són files buides, o són
  duplicats de la mateixa ubicació. El que sí que convindria és **una passada de
  neteja** dels duplicats same-location (Alosa/Erm/Fat Chets/Vadebo) i decidir
  què fer amb el 2n Crim — però això és gestió de catàleg, no enginyeria d'un
  encaminador.
