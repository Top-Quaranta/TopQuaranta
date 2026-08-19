# Informe 2b — Lentitud de les vistes staff

Data: 2026-06-07. Read-only (codi + git history). Sense canvis.

Pàgina staff per defecte: 50 files, tope 200 (`web/api/staff/_common.py:96`) → cada cost per-fila es multiplica ×200.

## Xifres / colls clau

| # | Endpoint | Fitxer:línia | Patró | Cost | Fix |
|---|---|---|---|---|---|
| 1 | artistes list + pendents | `pendents.py:118`, `artistes.py:92` | `a.localitats.select_related(...).first()` per fila ignora el prefetch | 1 query × fins a 200 files | **clar, baix risc** |
| 2 | cançons list | `cancons.py:189` | falta `prefetch_related("artistes_col")` + `select_related("spotify")` (OneToOne) | 1-2 queries × 200 | **clar, baix risc** |
| 3 | estat dashboard | `estat.py:620` | 50+ `.count()`/`.exists()` en sèrie + `_top_artistes_backlog` (`estat.py:198`) escaneja **tot** el backlog no-verificat a Python cada càrrega | latència dominada per nombre de queries; escaneig sense tope | mixt (parcial baix risc, col·lapse complet = refactor) |
| 4 | `_homonym_suspects_details` | `estat.py:294` | N+1 (1 query annotada per grup de rebuig); s'executa també dins `artistes_list?homonim_sospitos=1` (`artistes.py:132`) abans de paginar | N+1 lligat a la mida de l'historial de rebuigs | refactor mitjà (reescriure com 1 query) |
| 5 | artistes list `n_top` | `artistes.py:193-214` | 2 subconsultes correlacionades `COUNT(DISTINCT TopSetmanal)` per fila quan `include_n_top=1`/`sort=-n_top` (sempre a `/staff/artistes/sense-instagram`) + `.distinct()` apilat | car en LEFT JOIN gran | més pesat (índex o denormalitzar `n_top`) |

## Quan es va introduir (git)

- #1, #2, #4: des de la creació de l'API staff a la migració SPA — commit `a8b1c8d` (2026-04-26). N+1 de naixement.
- #2 (accés `spotify`): més recent, amb l'enriquiment Spotify (~2026-05/06).
- #5: commit `e4286a3` (2026-05-23, "tag IG collaborators + count collabs"). És el canvi **més recent** i el candidat més probable a "quan es va alentir" la pantalla artistes/sense-instagram.

## Endpoints nets (verificats OK)

albums (`albums.py:82`), propostes (`propostes.py:104`), comunitat directori (`comunitat_views/perfil.py:104`), analytics summary (`analytics.py:65`) — tots usen `select_related`/`prefetch_related` i agregació SQL.

## Recomanació FASE 3

- **Fer ja (clar, alt impacte):** #1 i #2 — correccions de querset/prefetch d'1-3 línies que eliminen fins a 200 queries/pàgina. Tots dos amb guard `assertNumQueries`.
- **Després (mitjà):** #4 (N+1 que s'esmuny a un filtre de llista) i #3 (fan-out de counts + escaneig sense tope).
- **Més pesat / menys prioritari:** #5 — primer un índex abans de reescriure. **STOP si esdevé refactor de pes.**
