# Ingesta d'àlbums aliens — recon (Baya Baye / Pangea)

> **NOMÉS-LECTURA, 2026-06-13.** Cap canvi al codi ni a dades. Simulació
> feta contra l'API pública de Deezer + la BD de prod. La implementació i
> la neteja són decisió de Miquel després de veure els números.

## Resum

- La regla objectiu **és segura**: simulada sobre tot l'historial capturable,
  descartaria **11 tracks**, **tots forans de veritat**, amb **0 falsos
  positius** (cap cançó verificada, cap d'àlbum propi, cap col·laboració
  legítima del nostre artista).
- Els casos legítims es conserven correctament: *Els Veritables* (Baya Baye
  hi col·labora de veritat) i el **remix de Roger Martínez** de "Glowing Tide"
  (ell sí que és al track) **es mantenen**; els originals/altres remixos no.
- Abast viu a la cua: **9 tracks actius** mal assignats (6 de Pangea + 3 de
  "Glowing Tide"), repartits en **2 artistes nostres** a banda de Baya Baye.
  11 en total comptant 2 ja inactius.

---

## 1. Condició exacta (a `_create_album` / `_create_track`)

### Senyals disponibles al moment de la ingesta

| Senyal | On | Disponible ara? |
|---|---|---|
| `track.contributors` (ids + noms de tots els crèdits del track) | `get_album_tracks` ja fa `/track/{id}` per track → ho porta a `track_data["contributors"]` | **Sí** |
| `track.artist_id` (artista principal del track segons Deezer) | `track_data["artist_id"]` | **Sí** |
| `our_artist.all_deezer_ids` (tots els perfils Deezer del nostre artista) | `Artista.all_deezer_ids` | **Sí** |
| **Titular de l'àlbum** (`album.artist.id` a Deezer) | `get_artist_albums` **NO** el retorna (només `id/title/release_date/cover/record_type` — verificat empíricament). Cal una crida extra `/album/{id}` | **No avui** — cal afegir-la |

> **Important sobre `contributors_raw`:** NO serveix per decidir la regla. El
> rol guardat és poc fiable: `_defer_contributor` dedupa per `deezer_id` amb
> *first-write-wins*, així que un "main" forà pot quedar congelat com a
> `"secondary"` (cas real: 3GSC guarda TIPO TRANQILO com a `secondary`). La
> condició s'ha de basar en una **comprovació en viu dels contribuïdors**, no
> en el rol emmagatzemat.

### Distinció "àlbum propi" vs "àlbum aliè on només col·laborem"

- **Àlbum propi** = el **titular de l'àlbum a Deezer** és un dels
  `deezer_ids` del nostre artista. → entra **sencer** (com ara; els convidats
  s'afegeixen com `artistes_col`).
- **Àlbum aliè** = el titular **no** és nostre. → només entren els tracks on
  el nostre artista **apareix entre els contribuïdors** d'aquell track.

### Pseudocodi (condició proposada)

```python
# _create_album: resoldre el titular una sola vegada per àlbum nou.
album_titular_id = deezer.get_album(dz_album_id)["artist"]["id"]   # crida /album/{id}
own_album = album_titular_id in our_artist.all_deezer_ids
# (passar own_album a _create_track, o desar-lo a Album per a la P2/enriquiment)

# _create_track (per cada track de l'àlbum):
track_contributor_ids = {c["id"] for c in track_data.get("contributors", [])}
our_on_track = bool(set(our_artist.all_deezer_ids) & track_contributor_ids)

if own_album or our_on_track:
    create_canco(under=our_artist)     # comportament actual (guarda de col·lab. intacta)
else:
    skip()                             # àlbum aliè + no hi som → NO crear sota el nostre
```

**Cost:** una crida `/album/{id}` extra **per àlbum nou** (un cop, no per
track). Negligible al ritme de novetats.

**Variant sense crida extra** (no recomanada): regla només per-track
`keep := our_on_track`. Estalvia la crida però **descartaria** tracks d'un
**àlbum propi** on el nostre artista no surt als crèdits del track (interludis,
skits, un tema liderat per un convidat dins el nostre disc). És el risc de fals
positiu que la branca `own_album` evita. La simulació de baix usa la regla
**amb titular** (la fidel a la teva intenció).

---

## 2. Simulació històrica (regla amb titular)

Xarxa de candidats = totes les cançons amb `contributors_raw` no buit
(**96 cançons**; sempre que els crèdits Deezer discrepen del nostre artista
queda rastre). Cada una verificada en viu contra Deezer (contribuïdors del
track + titular de l'àlbum).

**Resultat: 11 descarts · 85 mantingudes · 0 falsos positius · 0 vermells.**

| CID | Cançó | Àlbum | Artista nostre | Verif. | Activa | Titular Deezer |
|---|---|---|---|---|---|---|
| 34243 | Pangea | Pangea | Baya Baye Mgt Los Sosis | no | sí | TIPO TRANQILO |
| 34244 | Libertos | Pangea | Baya Baye Mgt Los Sosis | no | sí | TIPO TRANQILO |
| 34245 | **3gsc** | Pangea | Baya Baye Mgt Los Sosis | no | sí | TIPO TRANQILO |
| 34246 | Mercedes Fúnebre | Pangea | Baya Baye Mgt Los Sosis | no | sí | TIPO TRANQILO |
| 34248 | Misión Imposible | Pangea | Baya Baye Mgt Los Sosis | no | sí | TIPO TRANQILO |
| 34249 | Cashmere | Pangea | Baya Baye Mgt Los Sosis | no | sí | TIPO TRANQILO |
| 33166 | Glowing Tide (Futura Cut remix) | Glowing Tide | Roger Martinez | no | sí | Alex O'Rion |
| 33167 | Glowing Tide | Glowing Tide | Roger Martinez | no | sí | Alex O'Rion |
| 33169 | Glowing Tide (Kebin Van Reeken remix) | Glowing Tide | Roger Martinez | no | sí | Alex O'Rion |
| 32879 | I Want To Break Free | Berlin Y la Dama… | Frank Montasell | no | **no** | Lucas Peire |
| 32880 | Every Breath You Take | Berlin Y la Dama… | Frank Montasell | no | **no** | Lucas Peire |

**Confirmació de no-fals-positius (cap cançó que SÍ sigui del nostre artista
es descarta):**
- `RED — discard amb verificada=True`: **cap**.
- `RED — discard amb own_album` (titular nostre): **cap**.
- *Els Veritables* (Pangea, Baya Baye **verificada**) → **MANTINGUDA** perquè
  Baya Baye és contribuïdor del track. Era el test crític i el passa.
- *Glowing Tide (Roger Martinez remix)* (CID 33168) → **MANTINGUDA** perquè
  Roger Martínez és al track (és el seu remix). Els altres 3 "Glowing Tide"
  (original + 2 remixos d'altri) no el porten → descartats. La regla separa
  bé remix-propi de remix-aliè dins el mateix àlbum.

---

## 3. Casos de la vora

| Cas | Com el tracta la condició |
|---|---|
| **Àlbum propi amb convidats** | `own_album=True` → entra sencer; els convidats s'afegeixen com `artistes_col` (sense canvi). |
| **El nostre col·labora en 1 track d'un àlbum aliè** (cas Pangea / *Els Veritables*) | `own_album=False`, però `our_on_track=True` per a aquell track → **entra només aquell**; la resta de l'àlbum es descarta. ✅ resol el bug. |
| **Remix: el nostre fa un remix d'un tema aliè** (cas Glowing Tide) | El track del remix té el nostre artista als crèdits → entra; original i remixos d'altri, no. ✅ |
| **Main real de l'àlbum és nostre però distint del col·laborador** | `own_album=True` (titular = nostre) → entra sencer; la guarda per-track existent ja reassigna/defereix el main quan cal. Sense canvi de comportament. |
| **Split / recopilatori amb titular ambigu** (ex. "Various Artists", o titular que NO és cap dels nostres) | `own_album=False` → només entren els tracks on el nostre artista és als crèdits. Conservador i correcte. |
| **⚠️ Perfil Deezer del nostre artista que ÉS un agregat/segell** (titular de recopilatoris de tercers) | `own_album=True` (el titular ÉS un `deezer_id` nostre) → **entraria sencer** i el bug persistiria per aquell perfil. **No és el cas de Pangea** (titular = TIPO TRANQILO, no nostre), però és el límit de la regla: depèn de la decisió "àlbum propi = entra sencer". Lligat al problema de `deezer-compartit-recon.md`. |
| **Track sense `contributors` a Deezer** | `our_on_track=False`; si l'àlbum és aliè → descart. Si és propi → `own_album` el salva. Cap dada Deezer trobada a la mostra (0 casos). |

---

## 4. Abast actual (magnitud)

Dins la xarxa de candidats (`contributors_raw` no buit, **96** cançons):

- **11 descarts** en total, **4 àlbums**, **3 artistes nostres**:
  - **Baya Baye Mgt Los Sosis** — 6 tracks de l'àlbum *Pangea* (de TIPO
    TRANQILO). Tots actius, a la cua.
  - **Roger Martinez** — 3 tracks de *Glowing Tide* (d'Alex O'Rion). Actius,
    a la cua.
  - **Frank Montasell** — 2 tracks de *Berlin Y la Dama…* (de Lucas Peire).
    Ja **inactius** (a=0) → fora de la cua viva.
- **A la cua viva (actius, no verificats): 9 tracks** (6 Pangea + 3 Glowing
  Tide). Cap ha arribat al top públic (cap verificat).
- **85 candidats es mantenen** (col·laboracions legítimes o àlbums propis).

### Cobertura i punt cec

La xarxa `contributors_raw` és **efectivament completa** per al fenomen:
qualsevol track on els crèdits Deezer discrepen del nostre artista deixa
rastre a `contributors_raw`. Validat amb una **mostra de 60** cançons
actives/no-verificades amb `contributors_raw` **buit** (de 328 sota artista
aprovat): **0 mal-assignacions amagades** — confirma que els tracks
sense rastre són d'àlbum propi. Punt cec residual (no quantificat, presumpte
petit): tracks molt antics anteriors a la maquinària de `contributors_raw`, o
casos on Deezer no retornava crèdits. Si es vol una escombrada total, caldria
un audit per **titular d'àlbum** sobre els 6.126 àlbums (una crida `/album/{id}`
cadascun) — no fet aquí.

---

## Apèndix — mètode

- Candidats: `Canco.objects.exclude(contributors_raw=[]).exclude(contributors_raw__isnull=True)` (96).
- Per candidat: `GET /track/{deezer_id}` → contribuïdors; `GET /album/{album.deezer_id}` → titular (cau-en-memòria per àlbum).
- Descart ⇔ `(album_titular ∉ our.all_deezer_ids) AND (our.all_deezer_ids ∩ track_contributor_ids == ∅)`.
- Vermells comprovats: descart amb `verificada=True` (0) i descart amb
  `own_album=True` (0).
- Punt cec: mostra de 60/328 cançons amb `contributors_raw` buit → 0 amagats.

*Recon acabat. Cap canvi. Implementació + neteja de les 9 (o 11) → decisió de Miquel.*
