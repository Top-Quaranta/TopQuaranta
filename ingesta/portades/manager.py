"""Filesystem-backed manager for self-hosted covers.

Layout (state lives entirely on disk — no DB column):

    <PORTADES_ROOT>/<entitat>/<deezer_id>-<mida>.<format>
    e.g. /var/topquaranta/portades/album/12345-500.webp

`entitat` ∈ {album, cancio, artista}; `mida` ∈ settings.PORTADES_VARIANTS;
`format` ∈ settings.PORTADES_FORMATS.

A cover is considered present when its 500 px webp variant exists
(`exists()`), which is the sentinel the download command and later
phases key on.

# Spec: docs/architecture/portades.md
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# AVIF support is a Pillow plugin registered on import (side effect).
# Guarded so the module still imports where the wheel is absent (CI
# without libavif): callers that need AVIF will simply see the format
# fail and `download_and_convert` returns False, never an ImportError.
try:  # pragma: no cover - import side effect
    import pillow_avif  # noqa: F401

    _AVIF_AVAILABLE = True
except Exception:  # noqa: BLE001
    _AVIF_AVAILABLE = False

from PIL import Image, ImageOps

ENTITATS = ("album", "cancio", "artista")

# Quality per format. AVIF/WebP are perceptually fine well below JPEG's
# bitrate for these flat album-art images.
_QUALITY = {"avif": 70, "webp": 85, "jpg": 85}
# Pillow's encoder name differs from our file extension for JPEG.
_PIL_FORMAT = {"avif": "AVIF", "webp": "WEBP", "jpg": "JPEG"}

_USER_AGENT = "TopQuaranta/1.0 (+https://www.topquaranta.cat)"
_DOWNLOAD_TIMEOUT_S = 15
# Deezer CDN encodes the variant size as a `WxH` path segment; we
# rewrite it to the source size to always pull the largest cover.
_SIZE_SEGMENT = re.compile(r"/\d+x\d+-")


def _root() -> Path:
    return Path(settings.PORTADES_ROOT)


def path_for(entitat: str, deezer_id: int, mida: int, fmt: str) -> Path:
    """Deterministic path for one (entitat, deezer_id, mida, fmt).

    Raises ValueError on an unknown entitat so a typo can never write
    outside the three known subdirectories.
    """
    if entitat not in ENTITATS:
        raise ValueError(f"unknown entitat {entitat!r}; expected one of {ENTITATS}")
    return _root() / entitat / f"{int(deezer_id)}-{int(mida)}.{fmt}"


def exists(entitat: str, deezer_id: int) -> bool:
    """True iff the 500 px webp sentinel variant is on disk."""
    return path_for(entitat, deezer_id, 500, "webp").is_file()


def deezer_source_url(stored_url: str) -> str:
    """Normalise a stored Deezer cover URL to the configured source
    size (cover_xl, 1000×1000). Pass-through for non-Deezer URLs."""
    size = settings.PORTADES_DEEZER_SOURCE_SIZE
    return _SIZE_SEGMENT.sub(f"/{size}x{size}-", stored_url)


def _written_paths(entitat: str, deezer_id: int) -> list[Path]:
    """Every variant×format path for an entity (whether present or not)."""
    paths: list[Path] = []
    for mida in settings.PORTADES_VARIANTS:
        for fmt in settings.PORTADES_FORMATS:
            paths.append(path_for(entitat, deezer_id, mida, fmt))
    return paths


def _cleanup(paths: list[Path]) -> None:
    """Best-effort removal of files + any leftover .tmp siblings."""
    for p in paths:
        for candidate in (p, p.with_suffix(p.suffix + ".tmp")):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:  # pragma: no cover - defensive
                logger.warning("portades: could not unlink %s", candidate)


def _save_variant(img: Image.Image, dest: Path, mida: int, fmt: str) -> None:
    """Resize (square cover-fit) + encode one variant atomically."""
    if fmt == "avif" and not _AVIF_AVAILABLE:
        raise RuntimeError("AVIF plugin not available")
    resized = ImageOps.fit(img, (mida, mida), Image.LANCZOS)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    dest.parent.mkdir(parents=True, exist_ok=True)
    resized.save(tmp, format=_PIL_FORMAT[fmt], quality=_QUALITY[fmt])
    tmp.replace(dest)


def download_and_convert(entitat: str, deezer_id: int, source_url: str) -> bool:
    """Download the Deezer cover and write every variant×format.

    Returns True only when ALL variants were written; on any failure
    (download, decode, or a single encode) cleans up everything it
    touched and returns False. Idempotent: re-running overwrites.
    """
    if entitat not in ENTITATS:
        raise ValueError(f"unknown entitat {entitat!r}; expected one of {ENTITATS}")
    if not source_url:
        return False

    targets = _written_paths(entitat, deezer_id)
    try:
        resp = requests.get(
            deezer_source_url(source_url),
            timeout=_DOWNLOAD_TIMEOUT_S,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "portades: download/decode failed for %s/%s: %s",
            entitat,
            deezer_id,
            exc,
        )
        _cleanup(targets)
        return False

    try:
        for mida in settings.PORTADES_VARIANTS:
            for fmt in settings.PORTADES_FORMATS:
                _save_variant(img, path_for(entitat, deezer_id, mida, fmt), mida, fmt)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "portades: convert failed for %s/%s: %s", entitat, deezer_id, exc
        )
        _cleanup(targets)
        return False
    return True


def delete(entitat: str, deezer_id: int) -> None:
    """Remove every variant of one entity (purge / re-fetch)."""
    _cleanup(_written_paths(entitat, deezer_id))
