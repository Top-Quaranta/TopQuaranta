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

# Bayesian smoothing on the three "ratio_rebuig_*" ML features. With
# few decisions the raw ratio rej/total is extremely noisy (two
# rejections in a row push it to 100 % and feed a reinforcement loop).
# Mixing in PRIOR_K virtual decisions at PRIOR_P (=0.5 = neutral)
# keeps the ratio anchored until there's enough real signal to overcome
# the prior. See `music/ml.py::_smoothed`.
RATIO_PRIOR_K = 5
RATIO_PRIOR_P = 0.5

# MusicBrainz auto-match score threshold. Candidates below this never
# auto-resolve (require staff to paste the MBID by hand). 95 reflects
# MB's own scoring scale — anything lower is too lossy on close-name
# homonyms (Crim, Apa, …).
MB_AUTO_MATCH_SCORE = 95

# API rate limits (seconds between calls)
DEEZER_RATE_LIMIT = 1.0
LASTFM_RATE_LIMIT = 0.2
MAX_API_RETRIES = 3

# Score normalization batch size
SCORE_BATCH_SIZE = 500

# Motius de rebuig — single source of truth
MOTIUS_REBUIG = [
    ("no_catala", "No és en català"),
    ("artista_incorrecte", "El perfil Deezer no és el nostre artista"),
    ("album_incorrecte", "Àlbum incorrecte"),
    ("no_musica", "No és música"),
]
MOTIUS_VALIDS = {m[0] for m in MOTIUS_REBUIG}
