# Recon — perfils Deezer compartits (homònims sota un mateix deezer_id) — 2026-06-11

> **NOMÉS-LECTURA.** Cap escriptura, cap migració, **cap crida a CAP API
> externa** (Spotify i Deezer prohibits per quota). Només codi, historial git i
> BD en lectura. Preparació, no detecció: el segon Crim no té cançons a la
> finestra activa de 365 dies, així que és **invisible a qualsevol consulta de
> BD per construcció** — no s'ha buscat.

---

## 0. TL;DR

- La constraint dura és **`ArtistaDeezer.deezer_id` UNIQUE** (`music/models.py:557`):
  **un deezer_id ⇒ un Artista**. No hi ha cap forat (BD: **0** deezer_ids
  compartits per >1 artista).
- Avui, un single del "segon Crim" al perfil `347962` **s'atribueix
  silenciosament a Crim (pk=2908)** com a cançó pendent. Miquel el veuria a la
  cua de verificació amb el badge "possible barreja" (si la dispersió no fos
  stale), **però no el pot resoldre**: crear un segon Artista amb el mateix
  deezer_id el bloqueja la UNIQUE; les úniques accions són aprovar (atribució
  incorrecta) o **desvincular** (esborra, no reassigna). **S'encalla aquí.**
- **NO existeix** cap camp canònic `Artista.spotify_artist_id` per a
  encaminament. Sí existeix el SENYAL de detecció: `spotify_artist_dispersio` +
  `spotify_artist_ids_distints` (compta els spotify_artist_id distints per
  artista). El hook natural d'un encaminador és `music/spotify_dispersio.py`.
- **Inventari actiu: 40 artistes amb dispersió >1** (Scorpio 6, Guerra/Gar 5,
  …). Crim mateix surt amb dispersió **None** ara mateix (stale — vegeu §4).

---

## 1. Traça del cas hipotètic, pas a pas pel codi real

**Escenari:** demà el segon Crim (català, homònim) treu un single al perfil
Deezer `347962`, que ja és de Crim (pk=2908).

1. **Ingest** — `obtenir_novetats` (cron horari) el veu. A P3 (artistes aprovats)
   o P2 (re-scan d'àlbum), per a cada track resol l'artista amb
   `_artist_for_deezer_id(deezer_id)`
   (`obtenir_novetats.py:69-78`):
   ```python
   ad = ArtistaDeezer.objects.filter(deezer_id=deezer_id).select_related("artista").first()
   return ad.artista if ad else None
   ```
   Com que `347962 → Crim (pk=2908)`, **el track s'atribueix a Crim**. No hi ha
   cap altra branca: un deezer_id sempre torna un únic artista.
2. **Creació** — `_create_track` (`obtenir_novetats.py:422`) fa
   `Canco.objects.create(artista=Crim, verificada=False, activa=True, …)` (línia
   ~551). Si passa la guarda de caducitat i `_previously_rejected`, **la cançó
   entra a la cua de pendents com a Crim**.
3. **Enriquiment** — el cron nocturn `enriquir_spotify` resol l'ISRC→Spotify i
   `_hydrate_from_id` (`enriquir_spotify.py:444-509`) escriu **el
   `spotify_artist_id` real del track** (el del segon Crim, distint del 2p7r del
   Crim català) a `SpotifyMetadata`. Després crida `recalcular_dispersio` per a
   Crim → la **dispersió de Crim puja** (passa a ≥2).
4. **Verificació manual (què veu Miquel)** — al workbench de cançons
   (`/staff/cancons/`), la fila apareix com a cançó pendent de **Crim**, amb el
   badge **"possible barreja"** (`web/api/staff/cancons.py:150-154` exposa
   `spotify_dispersio = c.artista.spotify_artist_dispersio`). El badge li diu
   "aquest artista té tracks de >1 Spotify artist", però **no li diu quin track
   és de qui ni li ofereix separar-los**.
5. **Què NO pot resoldre des d'allí** — les úniques accions de rebuig són
   (`music/constants.py:230` `MOTIUS_REBUIG`): `desvincular_canco`,
   `desvincular_album`, `desvincular_artista`. **Cap reassigna** a un altre
   artista. I crear un **segon Artista amb el mateix deezer_id `347962` el
   bloqueja la UNIQUE**: a l'ingest, `obtenir_metadata.py:311` fa
   `ArtistaDeezer.objects.get_or_create(deezer_id=…)` i atrapa l'`IntegrityError`
   (línia 315) → *"Deezer ID already assigned to another artist — skipping"*.
   Així que el segon Crim **no pot existir com a Artista propi** mentre el
   deezer_id estigui pres.

**Conclusió — què passa HUI i on s'encalla:** el single s'atribueix
**silenciosament al Crim equivocat** i entra a la seua cua de pendents. Miquel
el veu però **no té cap mecanisme per a separar-lo**: ni reassignar, ni crear el
segon Crim (UNIQUE), ni un estat "pendent de desambiguar". Les opcions reals són
**aprovar-lo malament** (contamina el catàleg/senyal de Crim) o **desvincular-lo**
(el perd). **S'encalla a la frontera deezer_id-UNIQUE + l'absència
d'encaminament per spotify_artist_id.**

---

## 2. Mapa de la unicitat "un deezer_id = un artista"

**Constraint (font de veritat):**
- `ArtistaDeezer.deezer_id = BigIntegerField(unique=True)` — `music/models.py:557`.
  La direcció `Artista.deezer_id` directa es va eliminar (R10, 2026-04-16); ara
  tot passa per la M2M `ArtistaDeezer` via `deezer_id_principal`
  (`models.py:470`) i `all_deezer_ids` (`models.py:485`).

**Codi que assumeix la unicitat (lookup deezer_id → un artista):**

| Lloc | Què fa |
|---|---|
| `obtenir_novetats.py:75` `_artist_for_deezer_id` | Atribució a l'ingest (el cas de §1). `.first()` sobre la UNIQUE. |
| `obtenir_metadata.py:311` `ArtistaDeezer.get_or_create(deezer_id=…)` | Enllaça deezer_id→artista; `IntegrityError`→skip (l'enforcement real). |
| `obtenir_metadata.py:415,420,554,575` | Itera `artista.deezer_ids`; dedup per deezer_id. |
| `music/services.py:116,135,206,213,228` | Desvincular/materialitzar collab: `get_or_create(deezer_id=…)` i lookups. |
| `music/signals.py:135` | Invariant "aprovat ⇒ ≥1 deezer_id (o MBID)". |
| `descarregar_portades.py:241`, `backfill_album_source.py:75` | Portada/àlbum per `deezer_id_principal`. |
| `Album.deezer_id`, `Canco.deezer_id` (UNIQUE, nullable) | dedup de tracks/àlbums per deezer_id (no és el coll d'ampolla del cas, però mateixa assumpció). |

**Caches / narratives:** el motor narratiu i el feed **no llegeixen deezer_id**:
treballen sobre `TopSetmanal`/`Canco`/`Artista`. La conflació els arriba només
indirectament (un track del segon Crim atribuït a Crim podria entrar al top com
a Crim). No hi ha cache de deezer_id→artista a invalidar.

---

## 3. Punts d'enganxament per a un encaminador (router)

- **On es resol el spotify_artist_id del track:** `enriquir_spotify._hydrate_from_id`
  (`enriquir_spotify.py:478-481`) — escriu `sm.spotify_artist_id = principal_id`
  i `sm.spotify_artist_ids`. **Aquí és on el router compararia** el id del track
  contra el canònic de l'Artista.
- **On es compararia contra un canònic d'Artista:** `music/spotify_dispersio.py::recalcular_dispersio`
  ja construeix `by_artist[artista_id] = set(spotify_artist_id)`
  (línies 52-57). És el lloc natural per a: (a) designar el **canònic** (p. ex.
  el majoritari o un pin de staff), i (b) marcar els tracks amb id ≠ canònic com
  a "forasters".
- **Camp canònic `Artista.spotify_artist_id`: NO EXISTEIX (confirmat).** Hi ha
  `Artista.spotify_id` (`models.py:112`, UNIQUE nullable) però és **dormant**:
  grep a tot el repo no troba cap lectura per a routing (és relíquia pre-split
  ADR-0012). El que sí existeix és el **senyal** `spotify_artist_dispersio`
  (`models.py:390`) + `spotify_artist_ids_distints` (`models.py:399`) — detecten,
  no encaminen.
- **On viuria l'estat "pendent de desambiguar":** avui **no existeix**. El
  `Canco` té `verificada`/`activa` (pendent/live/rebutjat) i prou. Un estat nou
  hauria de viure **al Canco** (p. ex. `Canco.desambiguacio_pendent` o un
  `motiu`/cua pròpia) i desembocar a una **vista de verificació manual**, MAI a
  assignació silenciosa. El punt d'injecció és el mateix `_hydrate_from_id` /
  `recalcular_dispersio`: quan el track resol a un spotify_artist_id ≠ canònic de
  l'Artista, en lloc de deixar-lo atribuït, marcar-lo per a revisió.

---

## 4. Inventari DB-only de conflacions latents (finestra activa)

> ⚠️ **AVÍS OBLIGATORI:** això **només veu la finestra activa de 365 dies**. El
> cas "homònim **inactiu**" (com el segon Crim sense cançons recents) **hi és
> invisible per construcció** — cap senyal de BD el pot mostrar. Aquest inventari
> és el sòl, no el sostre.

**Artistes amb `spotify_artist_dispersio > 1`: 40.** Top:

| pk | nom | disp | deezer | aprovat |
|---|---|---|---|---|
| 3236 | Scorpio | **6** | 63753 | sí |
| 3441 | Guerra | 5 | 191504 | sí |
| 3341 | Gar | 5 | 4131820 | sí |
| 3799 | Ànsia | 4 | 284177 | sí |
| 3201 | Mendra | 4 | 4863053 | sí |
| 3200 | Patch | 4 | 327338 | sí |
| 3646 | Quinto | 4 | 1407503 | sí |
| … | (33 més amb disp 2-3: Lavanda, Amulet, Renata, Montenegro, Coco, Iker, Brams, Gisela…) | | | |

- **deezer_ids compartits per >1 Artista: 0** — la UNIQUE es manté íntegra.
- **Crim (pk=2908): dispersió = None, ids = []** — **STALE**. Els 9 tracks de
  Crim SÍ que estan enriquits (3 spotify_artist_id distints: 2p7r/0Eb1/01LX), però
  la dispersió no s'ha recalculat des de l'enriquiment dirigit (es va fer amb
  `_enrich_one` saltant-se `recalcular_dispersio` a propòsit). Per tant **el badge
  de Crim NO es mostra ara mateix**; s'actualitzarà al pròxim `enriquir_spotify`
  nocturn que toqui un track de Crim, o amb `recalcular_dispersio_spotify`.
  *(Cap acció presa: read-only.)*

Nota: dispersió >1 no és sempre conflació real (un featuring com a principal, una
versió/cover, una reedició col·laborativa poden inflar-la). Però disp 4-6
(Scorpio, Guerra, Gar) és quasi segur homònims fusionats per Deezer.

---

## 5. Opcions (amb costos i riscos) — SENSE implementar

### (a) Unicitat condicional: deezer_id repetible només amb spotify_artist_id propi distint i no nul

Permetre dos `ArtistaDeezer` amb el mateix `deezer_id` **només si** cada un porta
un `spotify_artist_id` canònic propi, distint i no nul.

- **Semàntica Postgres real amb NULL:** un `UniqueConstraint(deezer_id)` actual
  tracta cada fila com a única globalment. Per a relaxar-la sense afluixar la
  garantia quan no hi ha spotify_artist_id:
  - **Índex parcial:** mantenir `UNIQUE(deezer_id) WHERE spotify_artist_id IS NULL`
    (un sol artista sense desambiguar per deezer_id) **+** `UNIQUE(deezer_id,
    spotify_artist_id) WHERE spotify_artist_id IS NOT NULL`. Així: cap deezer_id
    pot tenir dos artistes "sense resoldre"; sí dos si cada un té el seu
    spotify_artist_id.
  - **`NULLS NOT DISTINCT`** (PG15+): faria que dos NULL xoquin → manté la
    garantia actual per als no-resolts, però **cal confirmar la versió de
    Postgres (prod = PG14 segons CLAUDE.md → `NULLS NOT DISTINCT` NO disponible)**.
    Per tant l'opció viable a PG14 és **l'índex parcial**.
- **Migració:** afegir `ArtistaDeezer.spotify_artist_id` (nou camp) + substituir
  `unique=True` per dos `UniqueConstraint` parcials. **Implicació de dades:**
  cap backfill destructiu, però cal poblar el nou camp (additiu, NULL inicial).
- **Superfície de codi:** `_artist_for_deezer_id` deixa de poder fer `.first()`
  ingenu — ha de triar per spotify_artist_id del track ⇒ toca l'atribució a
  l'ingest (el punt més delicat). `deezer_id_principal`/`all_deezer_ids` i tots
  els lookups de §2 han d'assumir N artistes per deezer_id.
- **Risc de deute:** ALT. Trenca l'invariant més assumit del sistema (un
  deezer_id = un artista) en \~10 call-sites; fàcil introduir atribucions
  silencioses incorrectes si un track encara no està enriquit (spotify_artist_id
  desconegut). Aquesta opció **sola** no és segura sense (b).

### (b) Encaminador a l'enriquiment + cua de desambiguació manual

Quan `_hydrate_from_id` resol un `spotify_artist_id` ≠ canònic de l'Artista,
**no atribuir silenciosament**: marcar el `Canco` com a "pendent de desambiguar"
i enviar-lo a una vista de verificació manual.

- **Migració:** afegir un estat/camp al `Canco` (p. ex. `desambiguacio_pendent`
  bool o un `motiu`) + designar el canònic (camp `Artista.spotify_artist_id_canonic`
  o derivar-lo del majoritari). Tot **additiu** (nullable/default).
- **Superfície de codi:** `_hydrate_from_id`, `recalcular_dispersio` (designar
  canònic), nova cua + endpoint staff + UI; el badge actual evoluciona de
  "avís" a "acció".
- **Risc de deute:** MITJÀ. Additiu i reversible; el risc és **fluxos a mig fer**
  (tracks encallats a la cua si ningú la mira) i decidir el canònic (majoritari
  vs pin). És el complement necessari de (a): (a) dóna l'espai a la BD, (b) dóna
  el procés perquè res s'assigni en silenci.

### (c) Tracks sense presència a Spotify → cua manual explícita

Tracks amb `enrichment_status = not_found` (o sense ISRC) **no tenen
spotify_artist_id** → l'encaminador de (b) no els pot classificar. Avui es
queden atribuïts a l'Artista del deezer_id sense senyal.

- **Migració:** cap nova si reutilitza l'estat de (b); si no, un flag addicional.
- **Superfície de codi:** una branca a l'encaminador: "sense senyal Spotify →
  cua manual" en lloc d'assumir que pertany a l'Artista. Petita.
- **Risc de deute:** BAIX, però **volum**: hi ha tracks `not_found`/sense-ISRC
  legítims que SÍ pertanyen a l'Artista; enviar-los tots a revisió inundaria la
  cua. Cal un gate (només quan l'Artista ja té dispersió >1, p. ex.).

### (d) Baseline — no fer res: què costa esperar

- **Migració/codi:** zero.
- **Cost real:** cada homònim que comparteix perfil **contamina el seu hoste**:
  tracks atribuïts a l'artista equivocat poden **entrar al top** com l'hoste,
  inflar-li el catàleg, i esbiaixar senyals (dispersió, narratives "novetat").
  El badge avisa **després** del fet, i la única sortida manual és **perdre** el
  track (desvincular) o **acceptar** l'error. Amb **40 conflacions actives ja
  visibles** (i un nombre desconegut d'inactives), el deute creix amb el catàleg.
  El cas Crim concret està "congelat" mentre el segon Crim no publiqui; el dia
  que ho faci, cau al camí de §1 sense xarxa.
- **Quan és acceptable:** si la freqüència real de col·lisions que **arriben al
  top** és baixa i el cost editorial de revisar-les a mà (desvincular) és
  tolerable. L'inventari de §4 suggereix que NO és negligible.

**Lectura de conjunt:** l'opció mínima coherent és **(b) + (c)** (encaminador +
cues, additiu, mitjà risc) abans que **(a)** (relaxar la UNIQUE, alt risc); (a)
només té sentit un cop (b) garanteix que res s'assigna en silenci. **Cap canvi
fet — decisió de Miquel.**
