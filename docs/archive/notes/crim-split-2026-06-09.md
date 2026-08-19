# Cas Crim — sonda d'enriquiment Spotify (2026-06-09)

> Operació de **DADES additiva** sobre prod, no canvi de repo. Límit dur
> respectat: **cap Artista nou, cap reassignació de cançó, cap canvi de scoring
> ni territori, cap esborrat.** L'única escriptura de dades = enriquir metadata
> de Spotify dels tracks de Crim (additiu). Fitxer local, no és commit.
>
> Crim aprovat: `Artista pk=2908`, Deezer `347962`.

---

## Resultat curt

**El split NO surt net en dos.** Després d'enriquir, els 9 tracks de Crim es
reparteixen en **com a mínim TRES** Spotify artist_id diferents (no dos), i
**2 tracks queden sense resoldre** perquè Spotify ens va aplicar un rate-limit
dur (Retry-After ≈ 7,5 h) a meitat de l'operació. No forço cap conclusió de
"dos Crim": amb les dades actuals no es sosté.

---

## 1. Tracks de Crim sense `spotify_artist_id` (objectius)

Detectats 5 de 9 (principal + col·laborador), tal com deia la recon:

| Canço | ISRC (prefix) | Estat SpotifyMetadata previ |
|---|---|---|
| c3847 Carnets de Punk | DEVF4 | found (artist_id buit) |
| c9877 Presó Mental | DEVF4 | found (artist_id buit) |
| c33534 Eye Cant Cry | QZYHJ | sense fila |
| c33804 Paper Cuts | QZYHJ | sense fila |
| c34032 Sugar Daddy (Demo) | QZYHJ | sense fila |

Pre-condicions verificades abans d'escriure: `SpotifyAuth` present; cooldown de
metadata Spotify **inactiu**.

## 2. Enriquiment (NOMÉS aquests 5, additiu)

Mètode: cap enriquiment global. He cridat `enriquir_spotify.Command._enrich_one`
(get_or_create de `SpotifyMetadata` → cerca per ISRC → hidratació) **track per
track** només per als 5 objectius, throttle 1 s. No he executat
`recalcular_dispersio` (toca un senyal de scoring → fora del límit permès).

Resultat: **3 enriquits abans del rate-limit, 2 bloquejats.**

| Canço | Outcome | spotify_artist_id | name |
|---|---|---|---|
| c3847 Carnets de Punk | found | `2p7rRgVQsbzdA8zkpb83Q2` | **Crim** |
| c9877 Presó Mental | found | `2p7rRgVQsbzdA8zkpb83Q2` | **Crim** |
| c33534 Eye Cant Cry | found | `0Eb1eu8crpFDACRQThhO2z` | **Gw Crimmy** ⚠️ |
| c33804 Paper Cuts | — | (rate-limited) | `not_attempted` |
| c34032 Sugar Daddy (Demo) | — | (mai arribat) | sense fila |

> A `/search` del track 4 (Paper Cuts) Spotify va tornar **HTTP 429
> Retry-After=27201s (~7,5 h)**, per damunt de la tolerància del client → avort.
> Els tracks 4 i 5 queden sense resoldre.

## 3. Agrupació completa dels 9 tracks per `spotify_artist_id`

```
artist_id=2p7rRgVQsbzdA8zkpb83Q2   name='Crim'        (5 tracks)  ← punk català
    c3847  Carnets de Punk          DEVF42202647   found
    c9877  Presó Mental             DEVF42202648   found
    c13619 Futur Medieval           QMDA62597575   found
    c13620 Combats d'Autoesgrima    QMDA62597576   found
    c13621 Res de Nou               QMDA62525826   found

artist_id=01LXoxJ5WJSPQ1w7zDLm9j   name='crim'        (1 track)
    c31037 Newpe$o                  QZES92631466   found

artist_id=0Eb1eu8crpFDACRQThhO2z   name='Gw Crimmy'   (1 track)  ← TERCER artista
    c33534 Eye Cant Cry             QZYHJ2664233   found

artist_id=∅ (buit)                                     (1 track)
    c33804 Paper Cuts               QZYHJ2665209   not_attempted  (bloquejat ban)

artist_id=NO_ROW                                       (1 track)
    c34032 Sugar Daddy (Demo)       QZYHJ2667475   NO_ROW         (bloquejat ban)
```

## Lectura honesta (no forçada)

- **El Crim català (`2p7r…`, "Crim")** queda ara **net i ben consolidat amb 5
  tracks**: els 3 de *Futur Medieval* (QMDA6) MÉS els 2 de *Carnets de Punk* /
  *Presó Mental* (DEVF4), que abans tenien artist_id buit i ara resolen tots
  dos a `2p7r…`. Aquesta meitat és sòlida.
- **NO és un split de dos.** Apareix un **tercer** artist_id real:
  `0Eb1eu8crpFDACRQThhO2z` "**Gw Crimmy**" (Eye Cant Cry). La hipòtesi de la
  recon que tot el clúster QZYHJ (anglès) era el mateix "01LX crim" **no es
  confirma**: el primer QZYHJ que hem pogut resoldre va a "Gw Crimmy", no a
  "01LX".
- **2 tracks QZYHJ sense resoldre** (Paper Cuts, Sugar Daddy (Demo)) pel ban.
  Podrien anar a "Gw Crimmy", a "01LX crim", o a un quart artista — **no ho
  sabem encara**. No assumir.
- Per tant, ara mateix tenim **3 artist_id confirmats** sobre 7 tracks resolts
  (Crim 2p7r ×5, crim 01LX ×1, Gw Crimmy 0Eb1 ×1) **+ 2 incògnites**. El
  "Newpe$o" (01LX) i el "Eye Cant Cry" (Gw Crimmy) són clarament forasters
  enganxats al Deezer `347962` del Crim català, però **no formen un sol "segon
  Crim"** — són artistes diferents entre ells.

## Efecte secundari registrat (transparència)

Com que vaig cridar `_enrich_one` fora de `handle()`, el rate-limit no s'hauria
registrat al fitxer de cooldown compartit, i el cron nocturn (03:00/05:00)
hauria sondejat durant el ban i l'hauria estès. Per **no deixar prod pitjor**,
he replicat el que fa `handle()` en aquest mateix error: `cd.write(resume_at)`
amb `resume_at = now + 27201s` → **cooldown compartit fins ~2026-06-10 05:01
UTC**. Això NO és una dada de Crim; és higiene operativa que evita un dany que
hauria introduït la sonda. Cap altre fitxer ni taula tocats.

També: `get_or_create` va crear una fila buida `SpotifyMetadata` per a Paper
Cuts (`not_attempted`) — additiu i inert (el cron global l'hauria creada
igualment).

## Per completar (decisió teua)

1. **Acabar els 2 tracks** quan caduqui el cooldown (després de ~2026-06-10
   05:01 UTC): re-córrer la mateixa sonda dirigida sobre
   `[33804, 34032]`. Llavors tindràs el mapa complet dels 9.
2. Només **amb el mapa complet** decidir la separació. Recorda que **no és un
   2-way**: hi ha ≥3 artistes forasters (crim 01LX, Gw Crimmy, i potser més al
   QZYHJ). Cada un necessitaria el seu propi tractament; el Crim català (2p7r)
   és qui ha de quedar-se el Deezer `347962`.

**No he creat cap Artista, no he reassignat cap cançó, no he tocat scoring ni
territori, no he esborrat res.** Parat aquí.

---

## Actualització 2026-06-10 — els 9 tracks RESOLTS (mapa complet)

El cooldown compartit de Spotify ja havia caducat (`active_resume_at = None`).
He enriquit **NOMÉS** els 2 tracks que quedaven bloquejats (`_enrich_one`,
throttle 1 s): `c33804 Paper Cuts` i `c34032 Sugar Daddy (Demo)`. **Cap
creació d'Artista, cap reassignació, cap recalc global.** Ara els 9 tracks
estan tots `found`.

### Mapa complet (artist_id → tracks) — `Artista pk=2908`, Deezer `347962`

| Spotify artist_id | Nom Spotify | # | Tracks (canço · ISRC) |
|---|---|---|---|
| `2p7rRgVQsbzdA8zkpb83Q2` | **Crim** (punk català) | **5** | Carnets de Punk `DEVF4…`, Presó Mental `DEVF4…`, Futur Medieval `QMDA6…`, Combats d'Autoesgrima `QMDA6…`, Res de Nou `QMDA6…` |
| `0Eb1eu8crpFDACRQThhO2z` | **Gw Crimmy** | **3** | Eye Cant Cry `QZYHJ…`, Paper Cuts `QZYHJ…`, Sugar Daddy (Demo) `QZYHJ…` |
| `01LXoxJ5WJSPQ1w7zDLm9j` | **crim** (minúscula) | **1** | Newpe$o `QZES9…` |

**Veredicte definitiu: NO és un split de dos — és una conflació de TRES
artistes** sota el mateix Deezer `347962`. El clúster anglès QZYHJ (3 singles)
és **tot de "Gw Crimmy"**, no del "01LX crim" com s'havia hipotetitzat; "01LX
crim" només té *Newpe$o*. El registrant ISRC ho confirma net:
- **QMDA6 + DEVF4** → Crim català (2p7r) — 5 tracks.
- **QZYHJ** → Gw Crimmy (0Eb1) — 3 tracks.
- **QZES9** → crim 01LX — 1 track.

### Opcions de separació (decisió de Miquel — JO NO executo cap split)

L'`Artista pk=2908` actual (aprovat, Deezer `347962`, territori PPCC/català)
ha de quedar-se **només els 5 tracks del Crim català** (`2p7r`). Els altres 4
tracks (Gw Crimmy ×3, crim 01LX ×1) són forasters enganxats pel Deezer
compartit i caldria treure'ls. Recordatori d'invariant: **aprovat ⇒ Deezer ID
OR MBID**, així que qualsevol artista nou necessita la seua pròpia àncora.

1. **Tres artistes nets (recomanat si es vol conservar tot el catàleg):**
   - Crim català → es queda `pk=2908` + Deezer `347962` + Spotify `2p7r`.
   - **Gw Crimmy** → `Artista` nou amb els 3 QZYHJ; àncora pròpia (buscar el seu
     Deezer/MBID; si no en té, no es pot aprovar — quedaria pendent/descartat).
   - **crim (01LX)** → `Artista` nou amb *Newpe$o*; mateixa necessitat d'àncora.
   - Com que Gw Crimmy i "crim 01LX" probablement **no són música en català**,
     el més provable és **descartar-los** (rebuig `desvincular_artista` /
     treure els tracks de `pk=2908`) en lloc de crear artistes nous.

2. **Neteja mínima (si Gw Crimmy i crim no compten com a PPCC):** desvincular /
   rebutjar els 4 tracks forasters de `pk=2908` i deixar el Crim català net amb
   5 tracks. No es crea cap artista nou. És probablement el camí correcte: el
   Deezer `347962` és del Crim català i els altres dos són homònims que no
   haurien d'estar al catàleg.

3. **No tocar:** acceptar la conflació (no recomanat — infla el catàleg del
   Crim català amb 4 tracks que no són seus, i podria contaminar senyal/rànquing
   si entren al top).

**Com identificar quins tracks moure/treure:** per `spotify_artist_id` (net) o
pel registrant ISRC (QZYHJ→Gw Crimmy, QZES9→crim 01LX). Els 5 del Crim català
són QMDA6+DEVF4.

**Cap split executat. Cap escriptura tret de l'enriquiment additiu dels 2
tracks.** La decisió és de Miquel.
