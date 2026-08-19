# Neteja de backlog — estat de continuïtat

> Onada autònoma de neteja. Font: `backlog-2026-06.md` + informes citats.
> Dos modes: **AUTO-MERGE** (inert/mecànic/reversible, CI verda → squash-merge
> directe) i **PR-I-ESPERA** (canvia comportament → PR obert, no mergejar).
> Si un ítem toca exclusions dures o resulta VIU → **STOP-and-propose**.
> Última actualització: 2026-06-13 (sessió inicial).

## Llegenda d'estat
- ✅ FET · 🔄 EN CURS · ⏳ PENDENT · ⛔ STOP (proposta, no tocat)

## AUTO-MERGE
| # | Ítem | Estat | Nota |
|---|---|---|---|
| 1 | Podar ~74 branques mortes + redisseny-web | ✅ | 74 esborrades (totes head de PR merged) + redisseny-web. Queden main/legacy + 2 vives (redisseny-tail, feat/routine-esborrany-setmana) |
| 2 | Doc-fixes | ✅ | PR #237 merged → 66ff184. (a)8→13 (b)cancons_obtingudes (c)notifications (d)social_reset docstring (e)Sprint K copy. platform-overview JA estava actualitzat (06-09) → sense canvi. docs-decay-2026-Q2 DIFERIT (sweep de criteri, no fix mecànic). |
| 3 | Eliminar export TerrChip | ✅ | PR #238 merged → d59f6c3. 0 consumidors confirmats. |
| 4 | Dependabot torch (low) | ⛔ STOP | `first_patched=null` (cap versió pegada existeix; rang <=2.12.0) + el path vulnerable `torch.jit.script` només s'usa als runners morts de `scripts/model_comparison/` (item 8 els esborra), mai a prod (`whisper.py` usa faster_whisper, sense jit). Bump impossible/inútil i torch és dep ML/Whisper pesada → NO tocat. **RESOLT 2026-06-13:** un cop l'item 8 va eliminar l'únic camí de codi viu, l'alerta #35 es va **descartar** (`gh api ... state=dismissed reason=not_used`, comentari amb la justificació). **0 alertes Dependabot obertes ara.** |

**AUTO-MERGE tancat:** main == prod == d59f6c3 (deploy success, smoke 200).

## PR-I-ESPERA (recon-primer)
| # | Ítem | Estat | PR |
|---|---|---|---|
| 5 | Fallback caràtules newsletter | ✅ JA-FET | El bug d'informe-2c ja està resolt via `ensure_cover_downloaded` (pre-descàrrega síncrona abans del send, cridada a `comptes/newsletter.py`). El fallback Deezer-hotlink que suggeria el backlog CONTRADIU la decisió documentada "no hotlinking to Deezer inside the email" (clients de correu no carreguen el CDN de Deezer fiablement). Cap canvi. |
| 6 | Forat data_llancament NULL | ⛔ STOP-propose | `is_caducat`/`netejar_caducades` tracten NULL com "no caducar" a propòsit. Tractar NULL com a caducat = decisió de catàleg/dades (exclusió dura) i arrisca esborrar cançons recents amb data desconeguda. **Proposta** (no implementat): (a) backfill `data_llancament` des de Deezer/MB a l'enriquiment P1 quan és NULL (resol l'incògnita en lloc d'endevinar); (b) vista de triatge d'staff per a pendents amb data NULL (additiu, segur); (c) NO tractar NULL com a caducat automàticament. Decisió de Miquel. |
| 7 | N+1 staff (inerts) | ✅ JA-FET | Els 2 fixos inerts ja van landar 2026-06-07 just després del recon: #1 `_artista_card` llegeix del prefetch (docstring ho confirma) + `artistes_list` ja prefetcha `localitats__municipi`; #2 `cancons_list` ja té `select_related("artista","album","spotify").prefetch_related("artistes_col")`. Les `.first()`/`.all()` restants (pendents.py:385, artistes.py:523) són one-off de detall (1 query, no N+1). PER A MIQUEL (no inerts, exclosos): #3 fan-out de counts a estat.py + escaneig backlog sense tope; #4 `_homonym_suspects` N+1 (refactor); #5 `n_top` subconsultes correlacionades (cal índex o denormalitzar). |
| 8 | git rm scripts/model_comparison + ADR-0014 | ✅ | **PR #240 merged → 4eb899b** (deploy success, smoke 200). ADR-0014 `docs/decisions/0014-whisper-lid-eval.md` preserva la provinença LID (precision 100%/recall 81%/spec 100%, VoxLingua rebutjat). 14 fitxers esborrats (inclou l'únic `torch.jit.script` viu). 3 cites repuntades. Exclusió ci-docs treta. |
| 9 | tq-backup visible a tq-health | ✅ JA-FET (verificat live) | Ja resolt 2026-06-07: `bin/tq-backup` escriu `tq-backup.status`, registrat a `deploy/cron-meta.json` (Cada nit 03:00, max_age 26h, skip_concern 1) i al grup "Manteniment i mètriques" de `health_report.py`. **Verificat al panell de prod:** `🟢 tq-backup OK(11h)` amb el backup d'avui (03:00, exit 0, 27 MB). Cap canvi. |
| 10 | Fatiga d'alerta — RECON-PRIMER | ✅ JA-FET | El Pattern 2 de l'auditoria (signatura de dedup inestable) ja el va resoldre **PR #155** (2026-06-07): `analytics/health_report.py` calcula ara una clau d'alerta sobre la IDENTITAT estable de l'anomalia (quins crons + estat), ignorant edat/comptador d'errors/hores-stale (tests ho fixen: `ignores_age_and_error_count`, `stale_hours_do_not_change_it`, `changes_on_new_anomaly`, `changes_on_threshold_crossing`, `excludes_silenced_nonescalating`). Cap canvi (recon-only + exclusió de lògica d'alertes). |
| 11 | Instagram opció C | ✅ | **PR #239 merged → f9a7fca** (ampliat: amaga TAMBÉ "Re-publicar" per a IG, mateixa causa arrel; conserva Mastodon/BS/Telegram). Reset→"Reconciliar registre" amb ajuda honesta. Deploy success, smoke 200. |

## Registre
- (inici) Branca base: main @ 5bd1c31. Git net.
- AUTO-MERGE: #237 (doc-fixes), #238 (TerrChip) mergejats → main==prod==d59f6c3 (deploy ok, smoke 200). 74 branques podades.
- PR-ESPERA obert: #239 (IG opció C).
- JA-FETS (cap acció): 5 (cover pre-download), 7 (N+1 inerts 06-07), 10 (dedup #155).
- STOP-propose: 4 (torch sense patch), 6 (NULL data_llancament = decisió de catàleg).
- DIFERITS pròxima sessió (plans a la taula): 8 (rm model_comparison), 9 (tq-backup→tq-health).
