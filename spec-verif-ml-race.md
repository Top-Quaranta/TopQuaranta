# Finding 2 — ML retrain race across gunicorn workers (non-atomic joblib)

## Hypothesis (as given)
Each gunicorn worker runs the song-classifier retrain in a background
thread; concurrent `.joblib` writes/reads race → EOFError / "EOF: reading
array data" tracebacks.

## Verdict: **CONFIRMED**

The mechanism, the trigger fan-out, the non-atomic writes, and the
matching prod tracebacks are all verified. The model is the staff
song-classifier (`ml_classe`/`ml_confianca`) and is NOT used by scoring /
soft-cap.

---

## Evidence

### 1. Trigger fans out per-worker, per-request, into a daemon thread

`music/ml.py:986-1012` — `recalcular_ml_si_cal()` spawns a daemon thread:
```
1011    thread = threading.Thread(target=recalcular_ml, daemon=True, name="ml-recalc")
1012    thread.start()
```
It is called from ~7 staff API request handlers (each runs inside the
gunicorn worker that served the request):
```
web/api/staff/top.py:218, 234       recalcular_ml_si_cal()
web/api/staff/cancons.py:345, 384   recalcular_ml_si_cal()
web/api/staff/pendents.py:462       recalcular_ml_si_cal()
```
gunicorn runs `--workers 2`
(`deploy/topquaranta-web.service` ExecStart: `… --workers 2 …`), so a
staff decision in worker A and another in worker B each spawn an
independent `ml-recalc` thread. No cross-worker (or cross-thread)
coordination exists.

### 2. The thread both WRITES and READS the same joblib paths

`recalcular_ml` (`music/ml.py:941-983`):
```
949     entrenar_model()                       # WRITES the joblibs
...
959     for canco in qs.iterator() ...:
960         result = pre_classificar(canco)    # READS the joblib (reloads on mtime change)
```

WRITE sites — all direct, no temp file, no lock:
```
music/ml.py:729   joblib.dump(tfidf, TFIDF_PATH)
music/ml.py:747   joblib.dump(clf, MODEL_PATH)
music/ml.py:770   joblib.dump(directions, DIRECTIONS_PATH)
```
READ sites — direct `joblib.load`, reloads whenever `mtime` changed:
```
music/ml.py:213   _model_cache["tfidf"] = joblib.load(TFIDF_PATH)   # _get_tfidf
music/ml.py:235   clf = joblib.load(MODEL_PATH)                     # _get_clf
```
No `os.replace`, `*.tmp`, `tempfile`, `flock`/`fcntl`/`FileLock` anywhere
in `music/ml.py` (grep for those returns nothing). The only existing
guard is `DEPLOY_LOCK_PATH` (`music/ml.py:174`), which only blocks
retrain *during a tq-deploy* — it does NOT serialize concurrent retrains
or guard readers against a half-written file.

### 3. Prod tracebacks match exactly (read-only journal, last 7 days)

Counts:
```
ml-recalc                       : 9
EOF: reading array data         : 3
EOFError                        : 12
UnpicklingError / truncated     : 0
```
The full traceback pins the read site:
```
File "/home/topquaranta/app/music/ml.py", line 960, in recalcular_ml
    result = pre_classificar(canco)
File "/home/topquaranta/app/music/ml.py", line 789, in pre_classificar
    clf = _get_clf()
File "/home/topquaranta/app/music/ml.py", line 235, in _get_clf
    clf = joblib.load(MODEL_PATH)
  ...
  File "/usr/lib/python3.12/pickle.py", line 1254, in load
    raise EOFError
```
and the truncated-array variant:
```
ValueError: EOF: reading array data, expected 25536 bytes got 0
ValueError: EOF: reading array data, expected 6672 bytes got 0
```
"expected N bytes got 0" = the file on disk is shorter than the pickle
header promised → a reader observing a dump still in flight.

**Two workers retraining at the same second** (the smoking gun) — note
the two distinct gunicorn PIDs at 18:27:12:
```
Jun 21 18:27:12 gunicorn[713053]: Exception in thread ml-recalc: ... EOFError
Jun 21 18:27:12 gunicorn[713051]: Exception in thread ml-recalc: ... EOFError
```
Worker 713051 then logs repeated `RF model trained …` lines minutes
apart (18:28:56, 18:29:57, 18:32:02) — back-to-back retrains, each a new
dump that any concurrent reader can catch mid-write.

### 4. The model is the staff classifier, NOT the scorer

- Docstring `music/ml.py:13`: classes A/B/C "Stored on
  Canco.ml_classe / ml_confianca." `pre_classificar` (`ml.py:784`) maps
  RF probability to A/B/C via `ML_CLASSE_A_THRESHOLD` / `ML_CLASSE_B_THRESHOLD`.
- Scoring / soft-cap lives in `ranking/` (`ranking/algorisme.py`,
  `ranking/management/commands/calcular_top.py`,
  `ranking/migrations/0026_soft_cap_outlier.py`). `grep` for any `ml`
  import or `pre_classificar`/`_get_clf`/`entrenar_model` reference across
  `ranking/` returns **nothing**. The classifier is fully decoupled from
  `calcular_top` and the sostre suau. A racing/misaligned classifier
  degrades staff triage (falls back to a heuristic), it does not corrupt
  the public ranking.

---

## Proposed minimal additive fix (spec only — do NOT implement)

Two cooperating changes, both in `music/ml.py`:

**(a) Atomic writes** — replace each `joblib.dump(obj, PATH)` at lines
729 / 747 / 770 with dump-to-temp-in-same-dir + `os.replace`:
```
# helper, applied at all three dump sites
fd, tmp = tempfile.mkstemp(dir=PATH.parent, suffix=".tmp")
os.close(fd)
joblib.dump(obj, tmp)
os.replace(tmp, PATH)        # atomic on POSIX, same filesystem
```
`os.replace` is atomic on the same filesystem, so a reader at `_get_clf`/
`_get_tfidf` always sees either the old complete file or the new complete
file — never a truncated one. This alone kills the "EOF: reading array
data / got 0" reader-vs-writer race.

**(b) A shared lock serialising retrains** — atomic write alone does NOT
prevent two `entrenar_model()` runs from executing concurrently (wasted
CPU; and TFIDF+MODEL could be replaced by two different retrains
interleaved, leaving an inconsistent TFIDF/MODEL pair). Wrap the
write-side of `entrenar_model` (and ideally the whole `recalcular_ml`
body) in a cross-process lock. Reuse the existing `music.locks.SingletonLock`
pattern (already used elsewhere per CLAUDE.md) or an `fcntl.flock` on a
dedicated `/var/run/topquaranta/ml-retrain.lock`, non-blocking so a
second concurrent trigger simply skips (a fresh retrain is redundant
anyway — `recalcular_ml_si_cal` will fire again on the next decision).

**Does atomic write ALONE suffice?**
- It removes the **EOFError / truncated-read tracebacks** (the symptom in
  the hypothesis) — yes, that class is fully closed by (a).
- It does NOT stop **two full retrains running at once** across the two
  workers (the 18:27:12 double-PID evidence). That is wasteful and can
  still interleave TFIDF vs MODEL dumps from different retrains. So (b)
  is needed for correctness/efficiency, even though (a) covers the
  crash.

**Stronger structural alternative (note, not required by the prompt):**
because the trigger is a per-request background thread fanned across
workers, the cleanest long-term fix is to stop spawning the retrain in
web workers at all and move `recalcular_ml` to a cron / single-runner
(the codebase already has `tq-run` + `SingletonLock` cron infra). That
eliminates the fan-out at the source rather than guarding its symptoms.
Given the prompt asks for the *minimal additive* fix: **(a) + (b)** is
the minimal correct change; the cron move is the recommended follow-up.
