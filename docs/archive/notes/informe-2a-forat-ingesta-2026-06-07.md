# Informe 2a — Forat d'ingesta: cançons a la cua de verificar sense cap artista aprovat

Data: 2026-06-07. Read-only (codi + BD de prod). Cas llavor: "Love Me (Slowed)".

## Xifres clau (BD prod, cua = `verificada=false AND activa=true`)

| Mètrica | Valor |
|---|---|
| Cua de verificar total | **537** |
| Cua amb **main artista pendent** (`aprovat=false`) | **191** (36%) |
| Cua amb **cap artista aprovat** (main + tots els col·labs pendents) | **149** (28%) |
| D'aquests, amb àlbum `descartat=true` (com 11134) | **73** |

## El cas "Love Me (Slowed)" (Canço pk=11134)

- `deezer_id=3832427521`, `isrc=QM4TX2622980`, `verificada=f`, `activa=t`, `created_at=2026-04-10 11:51:37`.
- Main artista actual: **Irokz** (pk=5713) — `aprovat=f`, `auto_descobert=t`, `pendent_review=t`, `font_descoberta=deezer_contributor`, creat **2026-04-12 21:00** (dos dies DESPRÉS de la cançó).
- Àlbum: "Love Me" (pk=4801, `deezer_id=914983671`, **`descartat=t`**), pertany a **Aïsha** (pk=2714, `aprovat=f`, `font=legacy`), creat 2026-04-10 11:51:35 (2 s abans de la cançó).
- Col·laboradors de la cançó: **Aïsha** (2714, pendent, legacy) i **Karl Wine** (5714, pendent, deezer_contributor).
- Historial (`StaffAuditLog`):
  - 2026-04-22: `artista_rebutjar` sobre **Aïsha** amb `motiu=artista_incorrecte` (avui `desvincular_artista`), `cancons_afectades=63`, actor staff id=4.
  - 2026-05-11: `pendent_descartar` sobre **Karl Wine** pel cron `netejar_pendents_no_ppcc` (`auto_no_ppcc`).
  - Cap entrada de reassignació per a la Canço 11134.

Cronologia: la cançó + l'àlbum entren el 04-10 via ingest del catàleg Deezer d'Aïsha (artista *legacy* pendent). Els col·laboradors Irokz i Karl Wine es materialitzen el 04-12. El 04-22 Aïsha és rebutjada (`desvincular_artista`, 63 cançons), però 11134 sobreviu amb el main reassignat a Irokz (col·laborador pendent) i l'àlbum marcat `descartat`. Resultat: cançó activa a la cua de verificar amb **els tres artistes pendents/rebutjats**.

## Mecanisme (com hi arriba amb la regla "només aprovats")

La regla "només aprovats" només s'aplica a **P3** d'`obtenir_novetats` (`ingesta/management/commands/obtenir_novetats.py:287`, `Artista.objects.filter(aprovat=True, …)`) — decideix **quins catàlegs es rastregen per descobrir àlbums nous**. NO s'aplica a:

1. **P1 (backfill ISRC, línies 153-176)** ni **P2 (re-scan d'àlbums, línies 178-266)**: re-escanegen tot `Album` amb `deezer_id` i `descartat=false` sense mirar `album.artista.aprovat`, i `_create_track` crea Cançons amb `verificada=False`. Així, un àlbum d'un artista *legacy* pendent (com Aïsha) genera cançons a la cua. (L'àlbum 4801 és ara `descartat=t`, però la cançó ja existia i resta `activa=t`.)
2. **El vincle de col·laborador** (`_create_track`, ~línies 581-591): un contributor que ja mapeja a un Artista pendent existent s'afegeix via `canco.artistes_col.add(collab)` sense comprovar `aprovat`. (Els contributors nous es difereixen a `contributors_raw` i no creen vincle fins a `aprovar_canco`.)
3. **La cua de verificar**: `cancons_list` (`web/api/staff/cancons.py:184`) usa `Canco.objects.pendents()` = `filter(verificada=False, activa=True)` (`music/models.py:937-939`), **sense cap filtre d'aprovació d'artista**. L'estat d'aprovació només es mostra a la fila, no filtra.

A més, el rebuig d'artista (`rebutjar_canco`, `music/services.py:19-39`) posa `activa=False` només a les cançons encara enllaçades a l'artista rebutjat com a **main**; una cançó ja reassignada a un altre pendent (Irokz) no es desactiva i queda òrfena a la cua.

## Invariants (docs) i per què no protegeixen

- El gate "només aprovats" del **ranking/`obtenir_senyal`** sí requereix `artista.aprovat=True` (`docs/architecture/pipeline.md:80-81`), així que aquestes cançons **mai surten al rànquing públic**. El forat és estrictament a la **cua de verificar staff**, aigües amunt d'aquell gate.
- L'invariant `aprovat ⇒ Deezer ID OR MBID` (`docs/architecture/models.md:189-193`) només aplica a artistes **aprovats** → no constreny col·laboradors pendents.

## Conclusió per a FASE 3

Dos sub-fixos possibles, tots dos additius i de baix risc:
- **(additiu, recomanat) Guard a `cancons_list`/`Canco.objects.pendents()` o a l'ingest** perquè una cançó sense **cap** artista aprovat no aparegui a la cua de verificar (o no s'encui). Cal triar el punt exacte (filtre a la cua vs guard a l'ingest).
- **Neteja en de-aprovar**: en rebutjar/descartar un artista, desactivar o re-encuar coherentment les cançons que queden sense cap ancoratge aprovat.

**STOP (decisió de producte requerida)**: què fer amb les **149 cançons òrfenes ja existents** (esborrar / tombstone `activa=False` / desactivar) i si el guard ha d'anar a l'ingest (no encuar) o a la cua (no mostrar). Vegeu la secció STOPs del resum.
