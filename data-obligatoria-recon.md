# Data de llançament obligatòria a la ingesta — FASE A (recon)

> **NOMÉS-LECTURA, 2026-06-13.** Cap canvi. Mesura sobre la BD de prod.
> FASE B (rebuig a la porta) només després de l'OK de Miquel.

## On es resol la data i d'on ve

1. **`_create_album`** (`ingesta/management/commands/obtenir_novetats.py`):
   `data_llancament = album_data["release_date"]`, que ve de
   `deezer.get_artist_albums()` (camp `release_date` de l'endpoint
   `/artist/{id}/albums`, parsejat per `_parse_date`). Pot ser `None` si
   Deezer el retorna buit/no-parsejable.
2. **`_create_track`** ("Fix album date"): si el track porta
   `album_release_date` (de `get_album_tracks` → `/track/{id}` →
   `album.release_date`) i és més antic, **rebobina** la data de l'àlbum a
   la del track. És la font més fiable (la data original de l'àlbum).
3. **Font única: Deezer.** No hi ha fallback a MusicBrainz/Last.fm per a la
   data a la ingesta.
4. La guarda de caducitat (`is_caducat`) tracta `NULL` com "no caducar" →
   una fila sense data **passaria** el filtre i entraria (el forat
   documentat a `caducitat.py:35`).

## Números (BD de prod, 2026-06-13)

| Mètrica | Valor |
|---|---:|
| Albums totals | 6 126 |
| **Albums amb `data_llancament` NULL** | **0** (0,0 %) |
| Albums creats últims 30 d | 512 |
| …dels quals NULL (estimació de rebuig de la regla) | **0** (0,0 %) |
| Cançons totals | 5 546 |
| **Cançons amb `data_llancament` NULL** | **0** (0,0 %) |
| Cançons actives NULL / verificades NULL / pendents NULL | 0 / 0 / 0 |
| Cançons creades últims 30 d | 622 |
| …de les quals NULL | **0** (0,0 %) |

## Lectura

- **NULL ja acumulades: 0.** No hi ha cap fila a proposar per a tractament
  (el forat de `caducitat.py:35` és teòric — mai s'ha materialitzat).
- **Quantes rebutjaria la regla del flux actual: ~0.** En els últims 30 dies,
  el 100 % de les altes (albums i cançons) van resoldre data. Deezer la
  proveeix de manera fiable, i el rebobinat a `album.release_date` al nivell
  de track la garanteix encara més.
- **Conclusió:** fer la data obligatòria és una **guarda preventiva** (defensa
  contra un futur canvi de Deezer on `release_date` falti), de **risc ~nul
  avui** — no descartaria res del que entra ara, i no hi ha NULL acumulades a
  netejar. És un bon "belt-and-suspenders" a la porta de creació.

## FASE B proposada (NOMÉS amb l'OK; PR per a revisió, no mergejar sol)

- **Rebuig conservador a la porta** dins `_create_track` (i `_create_album`
  per a l'àlbum): si `data_llancament` no es resol (None després del
  rebobinat), **no crear la fila**; `logger.info` del descart amb
  `deezer_id`/títol perquè sigui auditables (no silenciós).
- **Pin de test:** amb data → entra; sense data resoluble → NO entra + log.
- **NULL existents:** 0 → no cal cap pas de neteja. (Si en aparegueren en el
  futur, es proposarien amb recompte, mai esborrades automàticament.)
- Mateixa filosofia que la guarda d'àlbum aliè ja desplegada: conservadora,
  amb log, sense tocar dades existents.

*FASE A acabada. Cap canvi. Espera l'OK per a FASE B.*
