"""Upload validation: what a stranger can put on our disk.

CLAUDE.md records a May-2026 audit fix — «`upload_imatge` validates
Pillow's `img.format`, not just the spoofable `content_type`» — and the
2026-08-15 audit found that fix has **no regression test**. It is the
kind of guard that is easy to "simplify" away later precisely because
the cheap check above it looks like it already does the job.

The two checks are not redundant:

* `content_type` is a header the client writes. Free to fake.
* `img.format` is what Pillow read out of the bytes. That is the truth.

A polyglot file — a valid GIF (or a script, or an HTML page) sent with
`Content-Type: image/png` — passes the first and must die on the second.
"""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from web.api._image_pipeline import (
    ImagePipelineError,
    _open_and_verify,
    validate_upload,
)


def _bytes(fmt: str, mida=(40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", mida, (250, 204, 21)).save(buf, format=fmt)
    return buf.getvalue()


def _fitxer(nom, contingut, content_type):
    return SimpleUploadedFile(nom, contingut, content_type=content_type)


@pytest.mark.parametrize("fmt,ct", [("PNG", "image/png"), ("JPEG", "image/jpeg")])
def test_a_real_image_is_accepted(fmt, ct):
    f = _fitxer(f"ok.{fmt.lower()}", _bytes(fmt), ct)
    validate_upload(f)
    assert _open_and_verify(f).format == fmt


def test_a_lying_content_type_does_not_get_a_file_through():
    """The whole point of the May-2026 fix. A GIF announced as PNG
    sails past the header check; only Pillow's verdict stops it."""
    f = _fitxer("truc.png", _bytes("GIF"), "image/png")
    validate_upload(f)  # el guardia barat el deixa passar…
    with pytest.raises(ImagePipelineError) as exc:
        _open_and_verify(f)  # …i el de veres, no
    assert "Format detectat" in str(exc.value)


def test_a_file_that_is_not_an_image_at_all_is_refused():
    """`<script>` bytes with an image header: the case where accepting
    it would mean serving attacker-controlled content from our origin."""
    f = _fitxer("x.png", b"<script>alert(1)</script>" * 40, "image/png")
    validate_upload(f)
    with pytest.raises(ImagePipelineError):
        _open_and_verify(f)


def test_a_disallowed_content_type_is_refused_early():
    """Cheap rejection before Pillow touches anything — that ordering is
    deliberate: never decode bytes you have already decided to refuse."""
    with pytest.raises(ImagePipelineError):
        validate_upload(_fitxer("doc.pdf", b"%PDF-1.4", "application/pdf"))


def test_an_oversized_upload_is_refused_with_413():
    from web.api._image_pipeline import _MAX_UPLOAD_BYTES

    f = _fitxer("gran.png", b"x" * (_MAX_UPLOAD_BYTES + 1), "image/png")
    with pytest.raises(ImagePipelineError) as exc:
        validate_upload(f)
    assert exc.value.status_code == 413


def test_a_missing_file_is_refused():
    with pytest.raises(ImagePipelineError):
        validate_upload(None)
