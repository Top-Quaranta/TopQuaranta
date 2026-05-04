"""Whisper LID client — language identification over Deezer previews.

Given a track's `preview_url` (and optionally its Deezer track ID), we:
  1. Download the 30-second MP3 preview (refreshing the signed URL via
     `/track/{id}` when the stored token has expired — Deezer previews
     carry `hdnea=exp=…` tokens that are hours-fresh and typically stale
     by the time the nightly cron picks a track up).
  2. Transcode to 16 kHz mono WAV via ffmpeg (Whisper's native format).
  3. Run `faster-whisper large-v3 .detect_language()` without transcribing.
  4. Return (lang_code, probability).

Evaluated on 48 clips (`scripts/model_comparison/resultats.md`):
  precision(ca) = 100 %, recall(ca) = 81 %, specificity = 100 %.

The model (~1.5 GB on disk, int8 quantised) is downloaded on first use
to `~/.cache/huggingface/hub/`. Inference is ~27 s per track on CPU.
Caller loads the model once via `get_model()` to amortise the ~5 s
startup cost across a batch.

We deliberately do NOT run Whisper in the web process — it holds ~1.5 GB
of tensors. Nightly cron via `tq-run analitzar_whisper`.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

logger = logging.getLogger(__name__)

# Whisper expects 16 kHz mono. The model pads/crops internally to 30 s.
_SAMPLE_RATE = 16000

# Module-level cache — inference is expensive to load; keep the model
# warm for a full batch run.
_model = None


def get_model():
    """Lazy-load faster-whisper (int8 CPU); cache module-wide.

    Model size is configurable via the `WHISPER_MODEL` env var (default
    `large-v3`). Recommended trade-offs on a 4 GB Hetzner CX22 box:
      * `large-v3`: 1.5 GB on disk, ≈3 GB RAM. Best lang-ID accuracy.
      * `medium`:    1 GB on disk, ≈1.5 GB RAM. Comparable accuracy on
        ≥5 s previews; safer when running concurrently with other
        memory-hungry crons.
      * `small`:     500 MB / ≈1 GB RAM. Faster but worse on multilingual
        edge cases.
    """
    global _model
    if _model is None:
        # Deferred import so Django startup doesn't pay the 1.5 GB cost.
        import os

        from faster_whisper import WhisperModel

        size = os.environ.get("WHISPER_MODEL", "large-v3")
        _model = WhisperModel(size, device="cpu", compute_type="int8")
    return _model


def _download_preview(url: str, dest: Path) -> bool:
    """Download the Deezer preview MP3 to `dest`. True on success."""
    try:
        r = requests.get(url, timeout=15, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    fh.write(chunk)
        return dest.stat().st_size > 1024
    except requests.RequestException as exc:
        logger.debug("Whisper: preview download failed for %s: %s", url, exc)
        return False


def _mp3_to_wav(mp3: Path, wav: Path) -> bool:
    """Transcode MP3 → 16 kHz mono WAV via ffmpeg. True on success."""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(mp3),
                "-ac",
                "1",
                "-ar",
                str(_SAMPLE_RATE),
                "-f",
                "wav",
                str(wav),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return wav.exists() and wav.stat().st_size > 1024
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("Whisper: ffmpeg failed on %s: %s", mp3, exc)
        return False


def _detect_language(wav_path: Path) -> tuple[str, float, dict[str, float]] | None:
    """Run Whisper LID on `wav_path`. Returns (lang, top_prob, all_probs) or None.

    `all_probs` covers every language in Whisper's vocabulary; caller keeps
    only what it needs (typically `ca`, `es`, top-1).
    """
    try:
        data, sr = sf.read(str(wav_path), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != _SAMPLE_RATE:
            # Shouldn't happen — ffmpeg forces 16 kHz — but be defensive.
            logger.warning("Whisper: unexpected SR %d on %s", sr, wav_path)
            return None
        # Whisper pads/crops to 30 s internally; we cap to 30 s for safety.
        data = data[: _SAMPLE_RATE * 30]
        if data.size == 0:
            return None
        model = get_model()
        lang, prob, all_probs = model.detect_language(data)
        if isinstance(all_probs, list):
            all_probs = dict(all_probs)
        return lang, float(prob), {k: float(v) for k, v in all_probs.items()}
    except Exception as exc:
        logger.warning("Whisper: inference failed on %s: %s", wav_path, exc)
        return None


def _refresh_preview_url(deezer_track_id: int) -> str | None:
    """Fetch a fresh preview URL from Deezer (hdnea= tokens expire)."""
    from ingesta.clients.deezer import _get

    data = _get(f"https://api.deezer.com/track/{deezer_track_id}")
    if data is None:
        return None
    return data.get("preview") or None


def analyze_preview(
    preview_url: str | None, deezer_track_id: int | None = None
) -> tuple[str, float, dict[str, float]] | None:
    """Download + analyse a Deezer preview, return (lang, prob, all_probs).

    `all_probs` is the full distribution over Whisper's 99 languages. The
    caller uses (lang, prob) for fast staff-badge rendering and all_probs
    as a richer ML signal that captures near-miss languages (e.g. a clip
    predicted it=0.50 ca=0.45 is very different from it=0.95 ca=0.01).

    None if:
      - Preview URL is missing and cannot be refreshed.
      - ffmpeg cannot decode the MP3.
      - Whisper inference fails.
    Caller treats None as "retry on next cron" (leave
    `whisper_processat_at` NULL).
    """
    with tempfile.TemporaryDirectory(prefix="whisper-") as tmpdir:
        tmp = Path(tmpdir)
        mp3 = tmp / "preview.mp3"
        wav = tmp / "preview.wav"

        got = False
        if preview_url:
            got = _download_preview(preview_url, mp3)
        if not got and deezer_track_id:
            fresh = _refresh_preview_url(deezer_track_id)
            if fresh:
                got = _download_preview(fresh, mp3)
        if not got:
            return None
        if not _mp3_to_wav(mp3, wav):
            return None
        return _detect_language(wav)
