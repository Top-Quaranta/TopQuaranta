# Cobertura Spotify — desglossament dels no-enriquits (2026-06-10)

> Investigació NOMÉS-LECTURA contra prod (Django shell, `settings.production`).
> Cap escriptura, **cap crida a l'API de Spotify** — tot és consulta de BD.
> Cooldown de metadata Spotify actiu; aquesta anàlisi no el toca.

## Pools (active + verified)

| Pool | Cançons |
|---|---|
| `activa=True, verificada=True` | **3 466** |
| └ sense ISRC | **0** |
| └ amb ISRC | 3 466 |
| └ amb ISRC i **caducat** (`data_llancament < 2025-06-10`) | **642** |
| └ **amb ISRC, no caducat → pool real d'enriquiment** | **2 824** |

L'ISRC no és mai el coll d'ampolla: **el 100 % de les cançons publicables tenen
ISRC**. Tampoc hi ha cap forat de "sense ISRC".

## Estat d'enriquiment dins del pool real (2 824)

| `enrichment_status` | Cançons | % |
|---|---|---|
| `found` | 1 519 | 53,8 % |
| `manual` | 4 | 0,1 % |
| **enriquides (found+manual)** | **1 523** | **53,9 %** |
| `not_attempted` | 1 257 | 44,5 % |
| `no_row` (sense fila SpotifyMetadata) | 38 | 1,3 % |
| `not_found` | 6 | 0,2 % |

## Desglossament dels NO-enriquits del pool real (1 301)

**Per causa:**

- **No-intentats encara (`not_attempted` + `no_row`) = 1 295 (99,5 %)** — tenen
  ISRC, no són caducats, però el Procés B encara no els ha tocat. **100 %
  recuperables** sense cap dependència externa nova: només falta que
  `enriquir_spotify` hi passi.
- **`not_found` = 6 (0,5 %)** — l'ISRC s'ha cercat i Spotify no el té. Únic bloc
  genuïnament no recuperable (el track no existeix a Spotify, o ISRC divergent).
- **sense ISRC = 0** · **caducats (fora del pool) = 642** (exclosos per disseny,
  PR #141 — no s'han de perseguir: el purgador els eliminarà / no compten).

**Per ml_classe** (dels 1 301 no-enriquits):

| ml_classe | Cançons |
|---|---|
| A | 872 |
| B | 258 |
| C | 153 |
| (buit) | 18 |

**Per territori** (artista principal):

| Territori | Cançons |
|---|---|
| CAT | 924 |
| VAL | 189 |
| BAL | 139 |
| ALT | 26 |
| (sense) | 23 |

## Lectura

- **El bloc més gran i recuperable són els 1 295 `not_attempted`/`no_row`.** No
  és un problema de dades ni d'ISRC ni de caducitat: és **backlog de throughput**
  del Procés B. La majoria (872) són **classe A** (alta confiança) i CAT (924),
  exactament el material que més interessa tenir enriquit per als playlists.
- A ritme nocturn (`enriquir_spotify`, cua per prioritats des de PR #186), 1 295
  tracks es drenen en uns quants dies — **no cal cap acció de dades, només deixar
  córrer el cron** (o pujar el `--limit`/throughput si es vol accelerar). Quan el
  cooldown de Spotify caduqui, el ritme es recupera sol.
- Els **6 `not_found`** són l'únic bloc realment perdut (0,5 %): es poden
  ignorar o revisar manualment l'ISRC cas per cas.
- Els **642 caducats** no s'han d'enriquir: queden fora del pool a propòsit.

**Conclusió:** la cobertura "real" és 53,9 % i el dèficit és **gairebé tot
backlog recuperable de classe A/CAT**, no un forat estructural. Cap intervenció
de dades necessària; és qüestió de temps de cron.
