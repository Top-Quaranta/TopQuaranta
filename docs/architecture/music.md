# music — invariants

<!-- Domain models (Artista / Album / Canco / Territori / Municipi),
     external-identity tables (ArtistaDeezer, ArtistaLastfmAlias/Similar,
     MB + YouTube fields), the two audit trails and the RF classifier.
     Fields/indexes: `music/models.py`. "Untested" = rule in code, no
     test would fail if broken — the first place to add one. -->

## Invariants

### Artista identity and state
- **`aprovat` and `pendent_review` are never both True.** Three states:
  live / in queue / tombstoned. Guarded by: `CheckConstraint
  artista_no_aprovat_pendent_review` (`music/models.py`). Untested.
- **`auto_descobert` is immutable provenance, not queue membership**
  (migration `music 0042` split the two; no service writes it).
- **`aprovat=True ⇒ ≥1 external anchor` (an `ArtistaDeezer` row OR a
  `musicbrainz_id`).** Losing the last Deezer id de-approves only when the
  MBID is also missing (`music/signals.py::unapprove_on_last_deezer_removed`,
  post_delete, writes via `.update()` so nothing refires). Approval
  *paths* are stricter: staff cannot approve without a Deezer anchor,
  and a Deezer id owned by another artist is a 409 (`web/tests/
  test_deezer_gate.py`). The MBID-keeps-approved branch is untested.
- **`aprovat=True ⇒ ≥1 ArtistaLocalitat`.** `Artista.clean()` — only
  runs via `full_clean()`, never from `save()`; approve endpoints call
  it. Untested.
- **`Artista.territoris` is derived, never edited.** Recomputed (on
  commit, once per transaction) from `ArtistaLocalitat → Municipi →
  Territori`; a `localitat_manual` (municipi NULL) adds `ALT` even when
  PPCC localitats exist; zero localitats keeps the legacy M2M. Guarded
  by: `music/signals.py::sync_territoris_on_localitat_{save,delete}`,
  `Artista.sync_territoris_from_localitats`. Untested.
- **Discarded pendents are tombstoned, not deleted** (`aprovat=False,
  pendent_review=False`, row kept; hidden from staff lists). Why: the
  Last.fm-similars resolver matches the surviving row and never re-queues
  it — deleting made the same name resurrect 4× (audit 2026-06-02).
  Guarded by: `web/tests/test_pendent_descartar.py`,
  `ingesta/tests/test_lastfm_similars.py::test_resolver_matches_tombstone_and_does_not_recreate_or_requeue`,
  `music/tests/test_purgar_pendents_buits.py` (descartats never purged).
- **Homonym auto-unlink.** When every track of an artist is rejected
  `desvincular_artista` and none stays active, all `ArtistaDeezer` rows
  go and the artist lands on `pendent_review=True` — MBID does not exempt
  (new releases come from Deezer). Mixed motius → human review. Guarded
  by: `music/tests/test_homonym_unlink.py`.
- **`nom_normalitzat`** (`normalitza_nom_homonim`: NFKD, lowercase,
  `[a-z0-9]` only) is rewritten on every `Artista.save()` and is the one
  homonym key (YouTube channel matching reuses it). Guarded by:
  `music/tests/test_homonims.py`.
- **`musicbrainz_id` / `spotify_id` `"" → NULL` in `save()`** (Artista,
  Album, Canco). Why: two empty strings collide in a UNIQUE column.
  Guarded by: `music/tests/test_save_normalization.py`.
- **D5: an artist is never a collaborator on its own track**
  (`m2m_changed` raises `ValidationError`); ingest compares against
  *all* of an artist's Deezer ids, not only the principal. Guarded by:
  `music/signals.py::prevent_self_collab`,
  `music/tests/test_services.py::TestProcessarCollaboradorsPendents::test_skips_self_collab`.

### Canço
- **One `Canco` row per recording; territory is derived** as
  `artista.territoris ∪ artistes_col.territoris` (`Canco.get_territoris`).
  Guarded by: `music/tests/test_models.py::TestCanco`.
- **ISRC unique when set** — `UniqueConstraint canco_isrc_unique_when_set`
  (partial, `isrc != ""`). Ingest catches the `IntegrityError` and skips
  (see `ingesta.md`). Constraint itself untested.
- **Public = `verificada=True AND activa=True`; pendent = `verificada=False
  AND activa=True`.** Always `Canco.objects.public()` / `.pendents()`.
  Guarded by: `music/tests/test_canco_public_manager.py` (`pendents()`
  untested); `ArtistaQuerySet` siblings in `music/tests/test_artista_queryset.py`.
- **A pendent canço is reviewable only if it has ≥1 approved artist**
  (main or collaborator). Orphans are deactivated (`activa=False`), never
  deleted; rows with non-empty `contributors_raw` are spared. Predicate
  `music.services.has_approved_artist`, bulk `orphan_pendents_qs`; applied
  by `rebutjar_artista` and weekly `netejar_cancons_orfes --grace-days 7`.
  Guarded by: `music/tests/test_services.py::TestOrphanPendents`,
  `music/tests/test_netejar_cancons_orfes.py`.

### Last.fm identity tables
- **`ArtistaLastfmAlias` UNIQUE(artista, nom); at most one `prioritari`
  per artist (partial unique); `Artista.lastfm_nom` ⇄ prioritari alias
  mirror both ways** (`music/signals.py`, re-entrancy guard). Only
  `confirmat=True` aliases sum into the signal. Guarded by:
  `music/tests/test_lastfm_aliases.py`, `music/tests/test_lastfm_prioritari.py`.
- **`ArtistaLastfmSimilar` UNIQUE(source, target); `nb_similars_lastfm`
  is a recomputed cache** (`COUNT(*) WHERE target=…`), replaced wholesale
  per source. Guarded by: `ingesta/tests/test_lastfm_similars.py`.

### MusicBrainz
- **Auto-match is name + PPCC location, never Lucene score**
  (`MB_AUTO_MATCH_SCORE=50` is only a floor). No localitats → refuse;
  candidate without `area` → refuse; >1 PPCC match → refuse;
  `mb_blocked_mbids` skipped; `mb_auto_match_disabled` kills it.
  Guarded by: `music/tests/test_mb_resolve_location.py`.
- **`validate_artista_area` treats "Spain"/"France" as inconclusive** —
  only an explicit non-PPCC country auto-unassigns (+ blocklist + audit
  `artista_mbid_auto_unassign`). Guarded by:
  `test_mb_resolve_location.py::test_validate_treats_spain_as_inconclusive`.
- **Changing an MBID resets the artist's Album/Canço MB fingerprints**
  (`sync_from_mbid`, also on staff PATCH), so a wrong MBID leaves no residue.

### Audit trails
- **`HistorialRevisio` is append-only by convention** (no constraint;
  the one mutable field is `reconsiderada`). It snapshots track/artist/
  ML state at decision time and is the RF training set. `motiu` ∈
  `MOTIUS_REBUIG` (action codes) | `ok` | `auto_ml` | `auto_whisper`.
  Sole writer `music/verificacio.py::crear_historial`. A rejected
  `(isrc, deezer_id)` blocks re-ingest until `reconsiderada=True`
  (`ingesta/tests/test_previously_rejected_reconsiderada.py`).
- **`StaffAuditLog` snapshots `target_type/id/label` and never raises**
  (`music/audit.py::log_staff_action` returns `None` on failure) — an
  audit outage cannot 500 a staff action.

### ML classifier (`music/ml.py`)
- **`FEATURE_NAMES` is append-only.** `_get_clf` flags a model whose
  `n_features_in_ ≠ len(FEATURE_NAMES)` as `MISALIGNED` (ERROR log,
  heuristic fallback); `entrenar_model` refuses while the deploy lock
  exists. Guarded by: `music/tests/test_ml_load_validation.py`,
  `music/tests/test_ml_spotify_dispersion.py` (index pin).
- **`auto_ml` decisions never feed training; `auto_whisper` ones do**
  (`entrenar_model` excludes only `MOTIU_AUTO_ML`; Whisper is an
  independent oracle). Guarded by:
  `music/tests/test_ml_auto_decide.py::test_auto_ml_decisions_excluded_from_training`
  (inclusion side untested).
- **No ML sub-tier auto-decides today** (`ML_AUTO_*_SUBTIERS = ()`); the
  only auto-approval is Whisper `p_ca > WHISPER_AUTO_APPROVE_P_CA` (0.90,
  strict, from `whisper_all_probs["ca"]`) with an approved artist anchor.
  Guarded by: `test_ml_auto_decide.py::test_no_subtier_is_currently_auto`,
  `music/tests/test_services.py::TestAutoAprovarPerWhisper`.
- **Rejection ratios are Bayesian-smoothed** (`RATIO_PRIOR_K=5, P=0.5`);
  the pair key is `(artista_deezer_id, artista_spotify_id)` with fallbacks.
  Guarded by: `music/tests/test_ml_pair_rejection_ratio.py`.

### Ops primitives
- **`music.locks.SingletonLock` exits 75 on contention** (`tq-run` →
  `SKIPPED_BY_LOCK`, `last_run` not refreshed); `"ram_heavy"` is shared
  by `analitzar_whisper` and `obtenir_metadata_musicbrainz` (CX22 OOM).
  Untested; the shared name is not pinned anywhere.
- **`music.dates.project_week_number`: Sat 2026-04-25 = week 34;
  weeks start Saturday.** ~10 consumers, no dedicated test.

## Traps
- `youtube_channel_id` (auto "- Topic" channel) ≠ `youtube_url` /
  `youtube_canal_oficial` (the band's human channel). Mixing them
  double-counts the Art Track. `youtube_canal_revisat`,
  `Canco.youtube_revisat` and `instagram_revisat` mean "reviewed, has
  none" — a final state, and what makes the daily work queues drain.
- `Canco.youtube_publicat_at` is the Art Track's publication date and
  means *when the recording appeared*, not when we matched it
  (`youtube_matched_at`). The ranking reads it as age evidence; write it
  only from the Art Track lane.
- `instagram_suggerit` is a candidate, not evidence; `instagram_rebutjat_at`
  (Meta code 110) blanks the public URL. Never promote a suggestion by code.
- `Album.descartat=True` is the only permanent exclusion from ingest;
  `last_album_check` is a cooldown, not a done-flag.
- `TERRITORIS_VALIDS` (ranking-eligible) ≠ the 10 `Territori` rows.

## Where the detail lives
- code: `music/models.py`, `music/signals.py`, `music/services.py`,
  `music/verificacio.py`, `music/ml.py`, `music/constants.py`,
  `music/locks.py`, `music/dates.py`, `music/audit.py`
- archived narrative: `docs/archive/architecture/models.md`
- ADRs: 0004 (workflow sol·licituds / `reconsiderada`), 0014 (Whisper LID)
