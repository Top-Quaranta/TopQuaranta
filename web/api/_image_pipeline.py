"""Shared image upload + resize pipeline for `/api/v1/upload/imatge/`.

Extracted from `comunitat_views/perfil.py` during Sprint Portal Artista
Ampliat (2026-05-20) so a third caller — manager-authored artist hero
images — can reuse the validation/normalisation path without copy-paste
drift.

Contract: `process_and_save_image(file, *, kind, dest_dir, max_width,
square_crop=False, output_format="WEBP", quality=85)` returns the saved
filename (relative to `dest_dir`). Validation errors raise
`ImagePipelineError(message, status_code)`; the caller turns that into
a DRF `Response`.

Why WebP by default: ~30 % smaller than JPEG at the same perceived
quality, supported by every browser we care about, and Pillow ships
the codec. Profile + publication uploads stay on JPEG until their
callers explicitly opt-in (no breaking change to the existing schema).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "WEBP"}
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class ImagePipelineError(Exception):
    """Validation failure with the HTTP status code the caller should
    surface (400 for client errors, 413 for oversize)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_upload(f) -> None:
    """First-pass checks on the raw `UploadedFile`. Cheap and runs
    before we touch Pillow."""
    if f is None:
        raise ImagePipelineError("Falta el fitxer.")
    if f.size > _MAX_UPLOAD_BYTES:
        raise ImagePipelineError(
            f"Màxim {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB per imatge.",
            status_code=413,
        )
    # NB: `f.content_type` is the browser-supplied header; trivially
    # spoofable. Used as a fast rejection only; the authoritative check
    # is Pillow's `img.format` after load. May-2026 audit fix.
    if f.content_type not in _ALLOWED_CONTENT_TYPES:
        raise ImagePipelineError("Tipus no permès. Només JPEG, PNG o WebP.")


def _open_and_verify(f) -> Image.Image:
    try:
        img = Image.open(f)
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImagePipelineError("El fitxer no és una imatge vàlida.") from exc
    if img.format not in _ALLOWED_PIL_FORMATS:
        raise ImagePipelineError(f"Format detectat invàlid: {img.format}.")
    return img


def _square_crop(img: Image.Image) -> Image.Image:
    s = min(img.width, img.height)
    left = (img.width - s) // 2
    top = (img.height - s) // 2
    return img.crop((left, top, left + s, top + s))


def _flatten_alpha(img: Image.Image, keep_alpha: bool) -> Image.Image:
    """Convert to RGB (or RGBA for WebP/PNG that needs transparency)."""
    if keep_alpha and img.mode in ("RGBA", "P"):
        return img.convert("RGBA")
    if img.mode in ("RGBA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        return bg
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def process_and_save_image(
    f,
    *,
    dest_dir: Path,
    max_width: int,
    square_crop: bool = False,
    output_format: str = "WEBP",
    quality: int = 85,
) -> str:
    """Run the full pipeline. Caller has already done auth + per-user
    quota checks; we only handle the bytes.

    Returns the filename (e.g. ``"abc123.webp"``) written under
    ``dest_dir``. The caller composes the absolute URL.

    Raises ``ImagePipelineError`` on any validation failure. The
    exception carries the HTTP status code the view should return."""
    validate_upload(f)
    img = _open_and_verify(f)

    if square_crop:
        img = _square_crop(img)
        if img.width > max_width:
            img = img.resize((max_width, max_width), Image.Resampling.LANCZOS)
    elif img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.Resampling.LANCZOS)

    fmt = output_format.upper()
    keep_alpha = fmt in {"WEBP", "PNG"}
    img = _flatten_alpha(img, keep_alpha=keep_alpha)

    ext = {"JPEG": "jpg", "WEBP": "webp", "PNG": "png"}.get(fmt, fmt.lower())
    filename = f"{uuid.uuid4().hex}.{ext}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename

    save_kwargs: dict = {"format": fmt, "quality": quality}
    if fmt == "JPEG":
        save_kwargs["optimize"] = True
    elif fmt == "WEBP":
        # method=6 → slowest/best compression. Worth the extra ~50ms
        # for a smaller file that's served forever.
        save_kwargs["method"] = 6

    img.save(dest, **save_kwargs)
    return filename
