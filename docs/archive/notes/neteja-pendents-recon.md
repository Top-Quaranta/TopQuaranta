# Neteja de pendents — recon (cohort casc-buit + bug llista + 400 cançons)

> **NOMÉS-LECTURA, 2026-06-13.** Cap esborrat, cap canvi d'estat, cap
> migració, CAP crida nova a Spotify/Deezer/Last.fm/MB. Tot de la BD de prod
> (dades Spotify ja desades incloses). Cap acció presa.

## Resum executiu

- **Cohort casc-buit esborrable = 30 244 artistes** (pendent + 0 cançons +
  0 àncores + 0 senyal). És el 88 % dels 34 181 pendents. Esborrat **segur**:
  0 reclamats per usuaris, 0 propostes, cap FK que bloquegi.
- Queden **fora** (NO es toquen): 3 937 pendents amb cançons/àncora/senyal.
- **Bug llista d'staff:** el filtre `aprovat=0`/`""` inclou els **descartats**
  (estat terminal) → inunden la primera pàgina. Fix proposat (no aplicat):
  excloure descartats per defecte, amb opt-in explícit.
- **Cascada getSimilar:** ✅ confirmada parada — només artistes APROVATS són
  fonts de descobriment.
- **404 cançons pendents** triades per decidibilitat (sota).

---

## PART A · Caracterització dels pendents

### Estats (camp `(aprovat, pendent_review)`; no hi ha enum `estat`)

| Estat | (aprovat, pendent_review) | Recompte |
|---|---|---:|
| Aprovat (live) | (True, False) | 2 006 |
| **Pendent** (cua de revisió) | (False, True) | **34 181** |
| Descartat (terminal, es manté per FK) | (False, False) | 10 047 |
| **Total** | | 46 234 |

### Encreuat dels 34 181 PENDENTS

| Bucket | Recompte |
|---|---:|
| amb cançons (FK `cancons` o M2M `participacions`) | 253 |
| amb àncora real (deezer_id / spotify_artist_ids / MBID) | 3 608 |
| amb senyal/plays històric (`lastfm_te_scrobbles` o `lastfm_playcount_total>0` o `lastfm_listeners>0`) | 523 |
| **CASC-BUIT (0 cançons ∧ 0 àncora ∧ 0 senyal)** | **30 244** |
| Fora de la cohort (tenen cançons o àncora o senyal) | 3 937 |

(Contrast — els 10 047 DESCARTATS: 556 amb cançons, 6 336 amb àncora, 1 643
amb senyal, **3 528 buits 0/0/0**. Vegeu nota al final sobre escombrar-los.)

### Definició de la COHORT ESBORRABLE

```
aprovat = False AND pendent_review = True       (pendent)
AND no té cap Cançó (ni FK Canco.artista ni M2M artistes_col)
AND no té cap àncora (cap ArtistaDeezer, musicbrainz_id buit/null,
    spotify_artist_ids_distints buit/null)
AND no té senyal (lastfm_te_scrobbles=False AND
    lastfm_playcount_total IN (0, NULL) AND lastfm_listeners IN (0, NULL))
```

**Recompte EXACTE: 30 244.** La línia és neta — coincideix amb la signatura
de la cascada antiga:

- **`auto_descobert=True`: 30 229 / 30 244** (els 15 restants també són
  0/0/0, valuosos zero igualment; opcionalment es pot afegir
  `auto_descobert=True` com a salvaguarda extra → 30 229).
- **created_at:** 2026-04 → 5 094 · 2026-05 → **24 897** · 2026-06 → 253
  (el pic de maig = la cascada getSimilar desbocada).
- `nb_similars_lastfm`: 25 173 amb 0, 5 071 amb >0 (descoberts com a similars
  d'algun aprovat, però sense cap valor propi).

### Seguretat del hard-delete (FK)

| Relació entrant | Cohort afectada |
|---|---:|
| `UserArtista` (reclamat per un usuari) | **0** |
| `PropostaArtista` (proposat per un usuari) | **0** |
| `ArtistaLastfmSimilar` com a SOURCE | **0** (consistent amb cascada parada) |
| `ArtistaLastfmSimilar` com a TARGET (edges des d'aprovats) | 3 085 |
| amb `localitats` (M2M) | 37 |
| amb `territoris` (M2M) | 37 |

→ **Esborrat segur.** Cap reclamació d'usuari ni proposta. Efectes de cascada:
- **3 085 edges de similars** (d'orígens aprovats cap a targets de la cohort)
  s'esborren → el `nb_similars_lastfm` (cache) d'aquests orígens queda
  lleugerament alt; cal **recomputar-lo** després (o acceptar el cache
  imprecís — és cosmètic al panell de pendents).
- **37 amb territori/localitat** (M2M): cascada neta de les files M2M. Són
  negligibles, però si vols màxima prudència, exclou-los → cohort 30 207.

### Mostra de 50 (per a ullar — els "coreans" hi són)

```
25024  Niklas Juritsch          30796  Æthenor              37011  Anson Kong 江𤒹生
25034  Ian Martir               36587  Titeknots            45249  SoulTremor
30850  Sura Isgenderli          41338  Juanjo Martin        47527  Becky G
41998  Twisted Illusion         24663  Nostalvania          37759  Doci
28452  Oliver Olson             46102  Charlie USG          15919  Mashiro Ayano
34592  Hepcat                   34125  Alex Cortiz          37499  Agus Padilla
34718  Hommarju vs P*Light      48602  Toni A. Martínez …   22983  Rebecca Martin
32155  V.O.S                    30575  Derek Vo             21435  暁Records
28173  DJ QUISSAK               47195  0.720 Aleacion       43644  Frosthelm
26950  Tiganá Santana           15585  Time's Forgotten     15331  The Dancehall Players
27801  Mc Bruninho da Praia     14562  Jane Birkin - Caetano Veloso
45302  One Brave Soul           31056  Jeremiah Lloyd Harmon
37881  Supa Bwe                 27796  Mad Dogz             24399  Wizzy Noise
18534  Danny Moffitt            30355  Izreel Jamez         23921  DOC OVG
34741  Samantha Barrón          43069  El Marcado           29002  Private Silence
39639  Brutus                   31501  Il Lungo Addio       35262  Fanatics
40466  Janel Leppin             29280  Spencer Croes & The State
20482  Jomeini Taim             42568  The Wonderboy        45302  One Brave Soul
```

(Cantopop, J-pop/idol, reggaeton, jazz, hardcore internacional… cap rastre
de música en català. És exactament el soroll de la cascada.)

### Pla d'esborrat dur EN LOTS — preparat, NO executat

Un cop Miquel digui endavant. Idempotent, per lots, re-verificant la cohort
a cada lot (perquè el conjunt no es mou entre lots):

```python
# Pla — management command nou `purgar_pendents_buits` (o shell puntual).
# NO és el codi final; és el guió per a revisió.
from django.db.models import Q, Exists, OuterRef
from music.models import Artista, Canco, ArtistaLastfmSimilar

has_fk  = Exists(Canco.objects.filter(artista_id=OuterRef('pk')))
has_m2m = Exists(Canco.objects.filter(artistes_col=OuterRef('pk')))
ANCHOR  = (Q(deezer_ids__isnull=False)
           | (~Q(musicbrainz_id__isnull=True) & ~Q(musicbrainz_id=''))
           | (~Q(spotify_artist_ids_distints=[]) & ~Q(spotify_artist_ids_distints__isnull=True)))
SIGNAL  = (Q(lastfm_te_scrobbles=True) | Q(lastfm_playcount_total__gt=0)
           | Q(lastfm_listeners__gt=0))

def cohort_qs():
    return (Artista.objects.filter(aprovat=False, pendent_review=True)
            .annotate(_fk=has_fk, _m2m=has_m2m)
            .filter(_fk=False, _m2m=False).exclude(ANCHOR).exclude(SIGNAL))

BATCH = 2000
# Capture the affected approved sources BEFORE deleting, to recompute their
# nb_similars_lastfm cache afterwards.
affected_sources = set(ArtistaLastfmSimilar.objects
    .filter(target__in=cohort_qs()).values_list('source_id', flat=True))

while True:
    pks = list(cohort_qs().values_list('pk', flat=True)[:BATCH])
    if not pks:
        break
    with transaction.atomic():
        # Django cascades ArtistaLastfmSimilar / M2M rows automatically.
        Artista.objects.filter(pk__in=pks).delete()
    log(f'deleted {len(pks)}')

# Post: recompute nb_similars_lastfm for the affected approved sources
# (COUNT(*) of remaining edges WHERE target=…) — cache, not critical.
```

- **Esperat: ~30 244 files** (15 lots de 2 000). Sense tombstone (decisió de
  Miquel: si algun torna a fer falta, reentra per la via normal).
- **Pre-guard recomanat al command:** re-assertar 0 `UserArtista` /
  0 `PropostaArtista` per lot (ara són 0; barata salvaguarda).
- **Post-step:** recomputar `nb_similars_lastfm` dels orígens afectats.
- Opcional: `--dry-run` que només imprimeixi el recompte.

---

## PART B · Bug de la llista d'artistes d'staff

### Causa (codi real)

`web/api/staff/artistes.py::artistes_list` (línies ~92-99):

```python
qs = Artista.objects.prefetch_related(...)
aprovat = request.GET.get("aprovat", "1")
if aprovat == "1":   qs = qs.filter(aprovat=True)     # Aprovats (default)
elif aprovat == "0": qs = qs.filter(aprovat=False)    # ← pendents + DESCARTATS
# aprovat == "" (Tots): cap filtre → tot, descartats inclosos
```

El frontend (`StaffArtistesPage.jsx`) ofereix `aprovat` ∈ {`1` Aprovats,
`0` No aprovats, `""` Tots}. Quan Miquel tria **No aprovats** o **Tots** per
buscar duplicats a fusionar, la consulta retorna també els **descartats**
(`aprovat=False, pendent_review=False`) — l'estat terminal — i com que són
~10 k (i la cohort casc-buit encara hi és com a pendent), inunden la primera
pàgina amb els "coreans".

### Fix proposat (NO aplicat)

Excloure l'estat terminal **descartat** de la llista per defecte, fins i tot
sense el filtre d'aprovats, però conservant pendents/inactius i amb un
opt-in explícit per veure descartats quan calgui:

```python
# Després de resoldre el filtre `aprovat`:
incl_descartats = request.GET.get("inclou_descartats") == "1"
if not incl_descartats:
    # Descartat = (aprovat=False, pendent_review=False). Mai a la llista
    # tret que es demani explícitament. No afecta "Aprovats" (cap és
    # descartat) i deixa intactes els PENDENTS (pendent_review=True).
    qs = qs.exclude(aprovat=False, pendent_review=False)
```

- **Aprovats** (`aprovat=1`): sense canvi.
- **No aprovats** (`aprovat=0`): ara mostra només **pendents** (descartats
  fora) → desapareix la inundació; segueixen visibles els duplicats a
  fusionar.
- **Tots** (`aprovat=""`): aprovats + pendents, descartats fora.
- Nova opció al `<Select>` o checkbox "Incloure descartats" (`inclou_descartats=1`)
  per al cas rar que es vulguin veure.

Nota: després d'esborrar la cohort casc-buit, gran part del soroll
desapareix sol; aquest fix cobreix el residu (els 3 937 pendents amb valor,
els ~6 500 descartats amb àncora/cançons) i els descartats futurs.

---

## PART C · Verdicte cascada getSimilar

✅ **Confirmat: només artistes APROVATS són font de descobriment.**
`ingesta/management/commands/obtenir_metadata_lastfm.py` (línies 104-117):
*"Only approved artistes act as discovery sources"* →
`Artista.objects.filter(aprovat=True)`. Els similars de pendents ja no
generen nous pendents (cascada parada). Consistent amb la BD: 0 artistes de
la cohort són `source` d'una vora de similars.

---

## PART D · Les 404 cançons pendents per decidibilitat

Cançons pendents = `verificada=False AND activa=True` → **404** (els ~400
esperats). Buckets (no mútuament exclusius; vegeu solapament):

| Bucket | Recompte | Decidibilitat |
|---|---:|---|
| **(A)** artista NO aprovat (pendent/descartat) | **40** | El destí segueix l'artista. Decidible amb la decisió de l'artista (no de la cançó). Cap és de la cohort casc-buit (la cohort té 0 cançons). |
| artista APROVAT | 364 | (desglossat sota) |
| **(B)** album-aliè candidat (`contributors_raw` no buit) | **37** (subconjunt dels 364) | Candidata a rebuig per la regla nova. Confirmació final necessita el **titular de l'àlbum a Deezer** (`/album/{id}` — font externa, no cridada aquí). |
| **(C)** decidible NOMÉS amb BD: ISRC + `whisper_lang` | **333** | **Tots 333 tenen `whisper_lang != 'ca'`** (LID diu NO-català) i **0 tenen `whisper_lang = 'ca'`**. Senyal fort de BD per a recomanació d'alta confiança (revisar/rebutjar com a probable no-català). El Whisper és senyal, no porta — staff decideix. |
| **(D)** necessita recerca externa | **31** | Artista aprovat **sense `whisper_lang`** (LID encara no corregut) → cal una passada de **Whisper LID** (`analitzar_whisper`) per decidir. Els 37 de (B) també necessiten **Deezer** (titular d'àlbum) per a confirmar la regla d'àlbum aliè. |

Notes:
- Els 364 aprovats es parteixen net: 333 amb `whisper_lang != ca` + 31 sense
  `whisper_lang`. **Cap té `whisper_lang = ca`.** La cua de cançons d'artistes
  aprovats està dominada per pistes que el LID marca com a NO-catalanes
  (foranes, instrumentals, o àlbum-aliè) — alta densitat de candidates a
  rebuig.
- Tots els 404 tenen ISRC (0 sense ISRC).
- Solapament: alguns dels 37 (B) també són dins els 333 (C). Per a una
  recomanació final convé l'ordre: (A) seguir artista → (B) confirmar
  àlbum-aliè amb Deezer → (C) la resta amb `whisper_lang != ca` com a
  rebuig de confiança mitjana-alta (staff verifica) → (D) 31 a esperar LID.

---

## Notes finals

- **Descartats buits (3 528):** mateix patró 0/0/0 però en estat terminal
  (ja fora de la cua). No formen part de la cohort definida (pendent), però
  són igualment valor-zero; es podrien escombrar en una segona passada amb la
  mateixa lògica si Miquel ho vol. (El fix de la llista, PART B, ja els
  amaga del soroll visual sense esborrar-los.)
- **Cap acció presa.** Cap fila esborrada, cap estat canviat, cap migració,
  cap crida externa. Tot són números de simulació sobre la BD de prod.
