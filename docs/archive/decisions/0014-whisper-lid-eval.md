# ADR-0014: Whisper as the language-ID signal (LID evaluation)

- **Status:** Accepted
- **Date:** 2026-06-13
- **Authors:** Miquel

> Preserves the provenance of the Whisper language-identification (LID)
> evaluation that backs the `whisper_lang` / `whisper_p` signal. The raw
> comparison harness (`scripts/model_comparison/`, runners + 48 audio
> clips) was removed from the repo on 2026-06-13 — it was a one-shot
> analysis, the audio is gitignored, and one runner held the only live
> use of `torch.jit.script`. The eval numbers and decision live here so
> the citing code/docs no longer point at deleted files. Full per-clip
> tables remain in git history (`scripts/model_comparison/resultats.md`,
> last at commit `9c83908`).

## Context

TopQuaranta is a catalogue of Catalan-language music. The classifier
question is **binary**: `ca` vs everything else (other languages,
instrumentals, ambiguous). The metric that matters is **precision(ca)** —
of everything accepted as `ca`, how much really is `ca` — which must
approach 100% or the catalogue gets polluted. Recall(ca) can be lower:
staff review rescues false negatives.

We evaluated candidate models on 48 clips: 23 Catalan vocals + 5 Spanish +
5 English + 2 French + 2 Italian + 1 Portuguese + 10 instrumentals
(`ca=—`). Catalan clips spanned pop, folk, rock, hardcore, cantautor,
female-lead, prog-live and feat. tracks; foreign clips were Deezer hits by
famous single-language artists.

## Evaluation

### faster-whisper large-v3 (CPU int8) — chosen

`detect_language()` on the raw 30 s clip, no source separation.

Binary confusion (ca vs no-ca, 48 clips, after ground-truth correction):

|  | Predicted ca | Predicted no-ca |
|---|---:|---:|
| Is ca (21) | 17 (TP) | 4 (FN) |
| Not ca (27) | 0 (FP) | 27 (TN) |

- **Precision(ca) = 17/17 = 100%**
- **Recall(ca) = 17/21 = 81.0%** (top-1 rule `predicted == "ca"`)
- **Specificity = 27/27 = 100%**

All 27 non-Catalan clips stayed safely below threshold (instrumentals
≤ 0.05 p(ca), Spanish ≈ 0.01, English ≤ 0.02, French/Italian/Portuguese
< 0.01). Of the 6 originally-Catalan clips Whisper flagged, staff found 2
were our own catalogue label errors (an English track and an instrumental
mistagged `ca`) and 3 were genuine false negatives (notably Jonatan
Penalba's timbre read as Spanish); 1 was unverifiable (broken preview).

Threshold note: top-1 gives precision 100% / recall ~74–81%; relaxing to
`p(ca) ≥ 0.10` recovers a borderline true positive with no new false
positives. Cost ≈ 27 s/clip on the CX22; model ≈ 1.5 GB int8.

### SpeechBrain VoxLingua107 ECAPA-TDNN — rejected

Second-opinion sanity check on the same clips: multi-class accuracy
36.8% (vs Whisper 84.2%), and **two false positives on `ca`** (C. Tangana,
Rozalén both predicted `ca` at 0.44) — disqualifying. VoxLingua is trained
on YouTube speech, not singing, and hallucinated wildly on music.

### Vocal/instrumental detection — not needed

Explored separately (Silero VAD, inaSpeechSegmenter, Spleeter, Demucs,
MusicNN) but **superseded**: if Whisper rejects an instrumental as
non-Catalan, no separate instrumental filter is required. MusicNN's
`male/female voice` tags may return later for a "% female voice" metric.

## Decision

Integrate faster-whisper large-v3 LID as a staff **signal** on `Canco`
(`whisper_lang`, `whisper_p`, `whisper_processat_at`), surfaced as a triage
badge and fed to the RF classifier as a feature. It is a signal, **not a
gate**: staff verification stays the source of truth. Do not integrate
MusicNN instrumental detection as a primary filter — LID subsumes it.

## Caveats

48 clips is a go/no-go sample, not a formal benchmark; the foreign-language
subset is small. The hardest adversarial case (a Catalan song whose 30 s
preview is dominated by a long Spanish/English featured verse) was not
tested. Demucs-vocals preprocessing was left untested — 100% precision
without it removed the motivation to add complexity.
