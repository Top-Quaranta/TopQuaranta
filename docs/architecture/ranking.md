# ranking — invariants

<!-- Algorithm v2.0 (`ranking/algorisme.py`), the two signal tables
     (`SenyalDiari`, `SenyalYouTube`), the two outputs (`TopSetmanal`
     official, `TopProvisional` rolling), the `ConfiguracioGlobal`
     singleton and the three distribution gates. Formulas below are the
     contract; coefficients live in `ConfiguracioGlobal` — read the
     config, not this doc, for current values. -->

## Invariants

### Signal → weekly plays (`_compute_weekly_plays`)
- **`weekly_plays = playcount_today − playcount_≈7d`; the delta is never
  extrapolated from a shorter baseline.** Baseline = closest row within
  ±`_WEEK_WINDOW_DAYS` (3) of −7 d, else any row ≥4 d old rescaled ×7/gap;
  no baseline → 0 (song out). Negative → 0. Guarded by:
  `ranking/tests/test_compute_weekly_plays.py`.
- **A release <7 d old counts its whole counter — unless the same artist
  already has an older track with the same `_track_identity`** (a
  re-issue: Last.fm returns the original's lifetime count). Looked up over
  the artist's *whole* catalogue, not the pool. Guarded by:
  `test_compute_weekly_plays.py::test_reissue_of_an_older_homonym_is_not_fresh`,
  `test_coherencia_ranking.py::test_reissue_does_not_bank_the_originals_lifetime_playcount`.
- **Last.fm merge steps are excised** (`_robust_weekly_from_series`): a
  one-day jump that is ≥8× the song's median daily rate AND ≥40 % of the
  cumulative AND ≥300 absolute is dropped and the week refilled from the
  other days. Strict 7-day window, so the week after a merge is untouched.
  Guarded by: `test_compute_weekly_plays.py::test_robust_series_*`, `::test_calib_*`.
- **A baseline is only valid against the same recording**
  (`lastfm_returned_track` normalised); a track switch falls to 0 until a
  new baseline accrues. Guarded by: `test_compute_weekly_plays.py::test_track_switch_*`.
- **`SenyalDiari` rows with `error=True` or `corregit=True` never enter
  the pool.** `corregit` is set by `detectar_anomalies_senyal` (06:45,
  |Δ| ≥ 100 AND > 20× median |Δ| → flag, never delete) and by
  `obtenir_senyal` drift detection. Guarded (writer side) by:
  `ingesta/tests/test_detectar_anomalies_senyal.py`; reader side untested.

### Score
- **`base = plays_eff × age × past_top`; `final = base × monopoli`; rows
  with `final < 1` dropped; top 100 kept, ≤40 published.**
  `age = max(0, 1 − min(1, (days/365)^exp))`;
  `past_top = max(0, 1 − Σ coef/2^(pos−1))` over prior `TopSetmanal`
  rows of the *same territori* at pos ≤ 40; `monopoli = (1−p_album)^n ×
  (1−p_artista)^n` over rows already ranked above in this pass. Guarded by:
  `ranking/tests/test_coherencia_ranking.py` (age, past-top, monopoly, ordering).
- **Every `TopSetmanal` read excludes the week being computed**
  (`_setmana_en_curs`, `setmana__lt`): past-top penalty, `canvi_posicio`,
  soft-cap median. Why: otherwise a re-run reads the rows it just saved
  and penalises #1 more than #2 (Bocc/Rosalía inversion, 2026-08-15).
  Guarded by: `test_coherencia_ranking.py::test_recalculating_the_same_week_is_idempotent`.
- **Eligibility floor `min_escoltes_top` is judged on raw plays; the
  soft cap only reshapes score.** Soft cap (`soft_cap_actiu`, off by
  default): `plays_eff = K(1+ln(plays/K))` above knee
  `K = max(floor, mult × median(top-N weekly_plays, last 10 weeks))`,
  per territori, before PPCC aggregation. Guarded by:
  `ranking/tests/test_soft_cap.py`.
- **Candidate pool = `Canco.objects.public()` within `DIES_CADUCITAT`
  whose main artist OR any collaborator sits in the territori.** No
  `artista.aprovat` check. Guarded by:
  `ranking/tests/test_algorisme_collaboradors.py`.

### YouTube as second source (`ranking/senyal_youtube.py`)
- **There is no switch.** It activates when ≥ `youtube_dies_minims` (7)
  days of *per-video* history exist (`actiu`); rows without
  `views_per_video` do not age the history. Then `signal = plays ×
  youtube_pes_escolta + weekly_views` and the floor becomes
  `min_senyal_combinat`. Multiply plays, never divide views (an absolute
  floor would drop YouTube-only songs). Guarded by:
  `ranking/tests/test_youtube_al_top.py`.
- **Weekly views = Σ per-video deltas over videos present in both
  snapshots.** A lane contributes from the day after it appears; a lane
  that vanishes subtracts nothing; a song without a comparable pair is
  *absent*, not zero. Why: `views` is a sum of lanes and a new lane brings
  its lifetime count (Andreu Valor: 103 048 false vs 17 real). Guarded by:
  `test_youtube_al_top.py::test_a_lane_that_appeared_this_week_does_not_count_as_views`,
  `::test_swapping_a_video_does_not_count_either`,
  `analytics/tests/test_informe_yt_comparativa.py`.
- **`SenyalYouTube` is a separate table from `SenyalDiari`** — a view is
  not a scrobble; combining is editorial and happens only in the algorithm.

### PPCC and territories
- **PPCC aggregates the results it is handed, it does not recompute.**
  `score_global = score × (1 − (pos−1)×p)`, dedup by canço keeping max,
  top 100; PPCC has no permanence penalty of its own (never read as
  history). Only a standalone `--territori PPCC` recomputes. Guarded by:
  `test_coherencia_ranking.py::test_ppcc_aggregates_the_results_it_is_given`.
- **Fixed CAT/VAL/BAL + aggregates ALT/PPCC always run; an optional
  territori gets its own top iff it has ≥ `min_cancons_ranking_propi`
  eligible songs, otherwise it folds into ALT** (`territoris_amb_top_propi`).
  Untested.
- **`calcular_top`: `--setmana` must be a Monday; non-aggregates first,
  aggregates last; each territori is delete + bulk_create in one
  transaction; provisional truncates and rebuilds.** Guarded by:
  `ranking/tests/test_calcular_ranking.py` (partial).
- **Each `TopSetmanal` row carries `algorithm_version` + `config_snapshot`**
  (`calcular_top::_CONFIG_SNAPSHOT_FIELDS`). Untested.

### Config and gates
- **`ConfiguracioGlobal` is a singleton (`pk=1`, `full_clean()` on every
  save; `load()`).** Guarded by: `ranking/tests/test_models.py::TestConfiguracioGlobal`.
- **The staff config endpoint masks any field whose name contains
  `_token|_secret|_password|_key|_apikey`** and hides the distribution
  section entirely (`web/api/staff/configuracio.py::_SECRET_PATTERNS`).
  Latent — no field matches today; masking itself untested.
- **Three distribution gates, in order: `distribucio_activa` (master) →
  per-channel `*_actiu` → `MatriuPublicacio.actiu_per(canal, tipus)`
  (fail-open when no row).** `pot_publicar(canal)` = first two;
  `pot_publicar_tipus` = all three; web and RSS are never matrix-gated.
  Guarded by: `ranking/tests/test_models.py::TestPotPublicar`,
  `social/tests/test_matriu_distribucio.py`.

## Traps
- `MAX_POSICIONS_TOP` exists in `music/constants.py` but `algorisme.py`
  (`posicio__lte=40`) and `calcular_top.py` (`<= 40`) hardcode 40.
- `config_snapshot` omits `min_escoltes_top`, `ppcc_penalitzacio_per_posicio`,
  `soft_cap_base_top_n` and every `youtube_*` field — a historic week is
  not fully reproducible from its snapshot.
- `TopSetmanal.algorithm_version` model default is `"v1.0"`; only
  `calcular_top` writes `"v2.0"`. Rows created elsewhere lie.
- `test_soft_cap.py::TestMergeInertness` is a docstring with no tests.
- `MatriuPublicacio.dia_setmana` / `pot_distribuir_avui` are gone
  (migration `ranking 0025`); publish days come from `social.calendari`.
- Old docs promised YouTube stays out of the score "until decided" — the
  self-activation above supersedes that (2026-08-19).

## Where the detail lives
- code: `ranking/algorisme.py`, `ranking/senyal_youtube.py`,
  `ranking/models.py`, `ranking/management/commands/calcular_top.py`,
  `ingesta/management/commands/{detectar_anomalies_senyal,arxivar_senyal_vell}.py`
- archived narrative: `docs/archive/architecture/algorithm.md`
- ADRs: none specific; YouTube rationale in `docs/architecture/analytics-youtube.md`
