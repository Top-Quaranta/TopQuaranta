# Shared constants for the TopQuaranta project.
# Import from here instead of using magic numbers.

DIES_CADUCITAT = 365  # tracks older than this are excluded from ingestion
MAX_POSICIONS_TOP = 40  # top N positions per territory

# Territory codes and display names — single source of truth.
# The canonical data lives in the Territori DB model (music_territori); this
# dict mirrors it for use in templates and Python constants where we want
# display strings without a DB hit.
TERRITORI_NOMS = {
    "PPCC": "Països Catalans",
    "CAT": "Catalunya",
    "VAL": "País Valencià",
    "BAL": "Illes Balears",
    "ALT": "Altres territoris",
    "AND": "Andorra",
    "CNO": "Catalunya del Nord",
    "FRA": "Franja de Ponent",
    "ALG": "L'Alguer",
    "CAR": "El Carxe",
}
# Territories that have a ranking visible on the public site.
TERRITORIS_VALIDS = ("CAT", "VAL", "BAL", "PPCC", "ALT")

# ─── Territori subsets ──────────────────────────────────────────────
# Single source of truth for the partition of TERRITORI_NOMS used by
# the ranking algorithm, sitemaps, top-page picker and PPCC source
# computations. Defined as tuples (immutable, ordered, hashable);
# call sites that need set semantics wrap with set(...) locally.
#
# Drift target: until 2026-05 these literals lived in
# ranking/algorisme.py and were duplicated in web/sitemaps.py and
# elsewhere. Adding a territory now means editing this file only.

# Territoris that always render a public top (CAT/VAL/BAL).
TERRITORIS_FIXOS = ("CAT", "VAL", "BAL")

# Aggregated buckets (not real territoris of music origin). PPCC
# combines the seven PPCC sources below; ALT is the umbrella for
# below-threshold optionals plus artists outside PPCC.
TERRITORIS_AGREGATS = ("ALT", "PPCC")

# Smaller PPCC territoris that get a dedicated top only when they
# have enough verified content (gated by ConfiguracioGlobal
# .min_cancons_ranking_propi).
TERRITORIS_OPCIONALS = ("CNO", "AND", "FRA", "ALG", "CAR")

# Sitemap and `<select territori>` display order. Excludes CAR (not
# viable yet) and ALT (catch-all bucket, not a discovery surface).
TERRITORIS_SITEMAP = ("PPCC", "CAT", "VAL", "BAL", "AND", "CNO", "FRA", "ALG")
TERRITORIS_TOP_ORDER = TERRITORIS_SITEMAP  # same ordering, different intent

# Codes whose artistes feed the aggregated PPCC top. Excludes ALT,
# PPCC itself and CAR.
TERRITORIS_PPCC_SOURCES = ("CAT", "VAL", "BAL", "AND", "CNO", "FRA", "ALG")

# ML classifier thresholds
ML_CLASSE_A_THRESHOLD = 0.7  # confidence >= this → class A
ML_CLASSE_B_THRESHOLD = 0.4  # confidence >= this → class B (below → class C)
MIN_TRAINING_SAMPLES = 20  # minimum HistorialRevisio records to train RF
MIN_NEW_DECISIONS = 5  # new decisions since last recalc to trigger retrain

# TF-IDF capacity for the title char-n-gram features. Trimmed from 200
# (2026-04-21 audit) to 60 (Sprint B baseline) to 30 after a 5-fold CV
# A/B on 7 730 decisions (Sprint TF-IDF retall, 2026-04-25): max=30
# matched ROC-AUC (0.9998) and improved F1 (+0.0013) and Accuracy
# (+0.0006) over max=60. The bottom half of the 60-feature tail had
# individual importance <0.03 % and was acting as noise; dropping it
# tightened the decision boundary without losing signal.
TFIDF_MAX_FEATURES = 30

# Fixed ML sub-tier boundaries used by the staff status dashboard
# and the auto-decision logic. Each main class A/B/C has a *fixed*
# overall range driven by ML_CLASSE_*_THRESHOLD:
#   A: [0.70, 1.00]   (ML_CLASSE_A_THRESHOLD = 0.70)
#   B: [0.40, 0.70)   (ML_CLASSE_B_THRESHOLD = 0.40)
#   C: [0.00, 0.40)
# Within each class we cut into 4 sub-bands by quartile of the live
# HistorialRevisio confidence distribution at decision time. The
# bounds are pinned (not recomputed dynamically) so auto-status
# decisions stay reproducible — re-tune after each retrain if the
# distribution shifts noticeably.
#
# Listed HIGH-to-LOW confidence: A++ (most confident "approve") at
# the top, C-- (most confident "reject") at the bottom. The list
# is iterated in this order by the staff dashboard, so the visual
# order matches the actual confidence axis.
#
# Honest accuracy (HistorialRevisio decision-time snapshot,
# excluding motiu='auto_ml' to avoid feedback-loop bias) audited
# 2026-04-30 on n=7 893:
#
#   A++  conf [0.99, 1.00)  acc-ap 93.1 %  ← NOT auto-approve material
#   A+   conf [0.95, 0.99)  acc-ap 97.8 %
#   A−   conf [0.85, 0.95)  acc-ap 92.7 %
#   A−−  conf [0.70, 0.85)  acc-ap 85.1 %
#   B++  conf [0.58, 0.70)  acc-ap 57.0 %
#   B+   conf [0.49, 0.58)  acc-ap 36.2 %
#   B−   conf [0.44, 0.49)  acc-ap 22.4 %
#   B−−  conf [0.40, 0.44)  acc-ap 14.1 %
#   C++  conf [0.27, 0.40)  acc-rej 95.2 %
#   C+   conf [0.17, 0.27)  acc-rej 97.4 %
#   C−   conf [0.05, 0.17)  acc-rej 98.9 %
#   C−−  conf [0.00, 0.05)  acc-rej 99.2 %  ← closest to auto-reject
#
# No tier currently clears the 99.5 % bar. Auto-decision lists are
# both empty.
#
# Earlier (now-corrected) figures relied on live Canco.ml_classe /
# ml_confianca, which the model has re-scored after retrains
# (target leakage). HistorialRevisio is the only honest source.
ML_SUBTIERS: list[tuple[str, float, float]] = [
    # Class A — confidence ≥ 0.70
    ("A++", 0.99, 1.001),
    ("A+", 0.95, 0.99),
    ("A-", 0.85, 0.95),
    ("A--", 0.70, 0.85),
    # Class B — 0.40 ≤ confidence < 0.70
    ("B++", 0.58, 0.70),
    ("B+", 0.49, 0.58),
    ("B-", 0.44, 0.49),
    ("B--", 0.40, 0.44),
    # Class C — confidence < 0.40
    ("C++", 0.27, 0.40),
    ("C+", 0.17, 0.27),
    ("C-", 0.05, 0.17),
    ("C--", 0.00, 0.05),
]

# A sub-tier becomes a blind-trust candidate when its accuracy on
# the historical decisions exceeds the threshold AND the sample
# size is large enough.
ML_AUTO_APPROVE_THRESHOLD = 0.995
ML_AUTO_REJECT_THRESHOLD = 0.995
ML_AUTO_MIN_SAMPLES = 200

# Sub-tiers that are currently auto-decided. EMPTY by default —
# graduate a sub-tier here only after the dashboard shows it as
# "candidat" stably across multiple weeks. Auto-decided cançons
# land in HistorialRevisio with motiu="auto_ml" and are excluded
# from training (entrenar_model) to avoid the model reinforcing
# its own decisions. As of 2026-04-30 no sub-tier qualifies — the
# 100 %-on-A++ figure that originally suggested otherwise was a
# leaked metric from live (re-scored) Canco fields.
ML_AUTO_APPROVE_SUBTIERS: tuple[str, ...] = ()
ML_AUTO_REJECT_SUBTIERS: tuple[str, ...] = ()
MOTIU_AUTO_ML = "auto_ml"

# Whisper LID auto-approval gate (2026-07). A track whose Whisper
# Catalan probability exceeds this threshold is auto-approved right
# after `analitzar_whisper` scores it, WITHOUT waiting for staff.
# Empirically justified: on 18 755 staff decisions, of the 1 961 with
# p_ca > 0.90 the precision was 100 % once the 6 apparent rejections
# (all songs staff false-rejected and later re-approved → currently
# verified) are counted as approvals. The first genuine non-Catalan
# false positive only appears at p_ca ≈ 0.879 (an Italian track), so
# 0.90 leaves margin. This is the ONLY signal that clears
# ML_AUTO_APPROVE_THRESHOLD; no ML sub-tier does. Unlike `auto_ml`,
# whisper is an independent oracle (an acoustic LID model, not the RF),
# so `auto_whisper` approvals DO feed RF training — they propagate the
# "this spotify_artist_id / deezer_id is ours" label into feature space
# even for the artist's future tracks that lack a preview. Distinct
# motiu kept only for provenance and honest-accuracy audits.
WHISPER_AUTO_APPROVE_P_CA = 0.9
MOTIU_AUTO_WHISPER = "auto_whisper"

# Bayesian smoothing on the three "ratio_rebuig_*" ML features. With
# few decisions the raw ratio rej/total is extremely noisy (two
# rejections in a row push it to 100 % and feed a reinforcement loop).
# Mixing in PRIOR_K virtual decisions at PRIOR_P (=0.5 = neutral)
# keeps the ratio anchored until there's enough real signal to overcome
# the prior. See `music/ml.py::_smoothed`.
RATIO_PRIOR_K = 5
RATIO_PRIOR_P = 0.5

# MB's Lucene score is a *search-relevance* metric, not a quality
# signal — it reflects how well-edited the MB record is, which biases
# hard towards mainstream international artists. For PPCC music (a
# niche on MB) the right answer often scores lower than a popular
# homonym. We set the floor low enough that MB's own ranking stops
# being the gatekeeper, and disambiguate ourselves via name+location
# in `mb_sync.resolve_mbid` (caught 2026-04-29 with the "Casual"
# case: US rapper at 100 vs CAT band at 91).
MB_AUTO_MATCH_SCORE = 50

# Round-robin pagination for MusicBrainz discography sync
# (`mb_sync.sync_from_mbid`). MB enforces 1 req/sec; an artist with
# many release-groups (e.g. 48) plus the per-track `recordings`
# detail call would otherwise eat ~50 s of a single cron tick. We
# process at most this many release-groups per `sync_from_mbid`
# call; the cursor advances and resets to 0 once a full pass
# completes. Big artists drain over several ticks predictably while
# small ones still finish in one. Added 2026-05-04.
MB_RGS_PER_RUN = 20

# API rate limits (seconds between calls)
DEEZER_RATE_LIMIT = 1.0
LASTFM_RATE_LIMIT = 0.2
MAX_API_RETRIES = 3

# Score normalization batch size
SCORE_BATCH_SIZE = 500

# Accions post-rebuig (single source of truth).
#
# Renamed from `motius de rebuig` on 2026-05-25. The previous names
# described the cause (`no_catala`, `album_incorrecte`, ...) which
# kept getting misread (e.g. assuming `album_incorrecte` meant "the
# album is wrong but the artist is right" instead of the real
# meaning "the album belongs to a homonym artist that Deezer
# collapsed under the right Deezer profile"). The new codes
# describe the concrete action each value triggers, so the name
# itself locks the contract:
#
#   desvincular_canco   -> rebutjar_canco(canco):
#       sets verificada=False, activa=False. The row stays in DB
#       for audit but disappears from pendents and rankings.
#       Covers the legacy `no_catala` (canço in another language)
#       and `no_musica` (podcast, sample, interview).
#
#   desvincular_album   -> rebutjar_album(album):
#       deletes all unverified cançons of the album + marks
#       album.descartat=True. The artista's ArtistaDeezer rows are
#       NOT touched: the album belongs to a homonym that Deezer
#       collapsed under the right artista's Deezer profile.
#
#   desvincular_artista -> rebutjar_artista(artista):
#       deletes all unverified cançons + clears every
#       ArtistaDeezer row + marks every album descartat. The
#       post_delete signal on ArtistaDeezer then sets aprovat=False
#       and pendent_review=False on the artista (unless it has an
#       MBID anchor). The artista does NOT auto-return to pendents.
#
# Data migration `music.0096_rename_motius_to_actions` rewrites
# historical HistorialRevisio.motiu values: `artista_incorrecte`
# -> `desvincular_artista`, `album_incorrecte` -> `desvincular_album`,
# `no_catala` + `no_musica` -> `desvincular_canco`.
#
# IMPORTANT: the human label MUST name only the action, never the
# cause. Including the cause ("homonim", "no és en català", ...)
# brings back the same ambiguity the rename was meant to kill: the
# operator reads the label, infers a meaning that does not match
# what the action actually does, and we end up needing another doc
# to undo the confusion. All cause / when-to-use prose lives in
# `docs/architecture/staff.md` section 5; this list stays
# action-only.
MOTIUS_REBUIG = [
    ("desvincular_canco", "Desvincular la cançó"),
    ("desvincular_album", "Desvincular l'àlbum"),
    ("desvincular_artista", "Desvincular l'artista"),
]
MOTIUS_VALIDS = {m[0] for m in MOTIUS_REBUIG}

# Canonical iteration order for an artist/profile's outbound social
# links. The SCHEMA (individual URLField definitions on Artista,
# PerfilUsuari, PropostaArtista) is unchanged; this tuple drives only
# the UI/serializer iteration order and labelling. Adding a network
# means appending here and adding the matching URLField to each
# consumer model.
SOCIAL_LINK_FIELDS = (
    ("spotify_url", "Spotify"),
    ("viasona_url", "Viasona"),
    ("web_url", "Web"),
    ("bandcamp_url", "Bandcamp"),
    ("youtube_url", "YouTube"),
    ("viquipedia_url", "Viquipèdia"),
    ("soundcloud_url", "SoundCloud"),
    ("tiktok_url", "TikTok"),
    ("facebook_url", "Facebook"),
    ("instagram_url", "Instagram"),
    ("twitter_url", "X"),
)
