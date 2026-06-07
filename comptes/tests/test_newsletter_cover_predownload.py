"""Guards for the newsletter cover pre-download (informe 2c, 2026-06-07).

Policy: the newsletter stays self-hosting-only (no Deezer hotlink in the
email). The fix turns that into a guarantee — before composing the send
we pull any missing top-album cover synchronously, reusing the portades
pipeline. So the logo fallback only shows for albums genuinely without a
Deezer cover.

These tests mock `manager.download_and_convert` so no network is hit.
"""

from __future__ import annotations

import pytest

from comptes import newsletter_covers as nc
from ingesta.portades import manager


@pytest.fixture
def portades_root(settings, tmp_path):
    settings.PORTADES_ROOT = str(tmp_path)
    return tmp_path


def _write_jpgs(root, deezer_id):
    """Create the JPG variants the newsletter requests, marking the
    album cover as already present on disk."""
    from django.conf import settings

    for mida in settings.PORTADES_VARIANTS:
        p = manager.path_for("album", deezer_id, mida, "jpg")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\xff\xd8\xff\xd9")  # minimal JPEG-ish bytes


def test_downloads_when_missing(portades_root, monkeypatch):
    calls = []

    def fake_dl(entitat, deezer_id, source_url):
        calls.append((entitat, deezer_id, source_url))
        return True

    monkeypatch.setattr(manager, "download_and_convert", fake_dl)
    ok = nc.ensure_cover_downloaded(851013072, "https://cdn/deezer/cover.jpg")
    assert ok is True
    assert calls == [("album", 851013072, "https://cdn/deezer/cover.jpg")]


def test_no_download_when_present(portades_root, monkeypatch):
    _write_jpgs(portades_root, 851013072)
    called = []
    monkeypatch.setattr(
        manager,
        "download_and_convert",
        lambda *a, **k: called.append(a) or True,
    )
    ok = nc.ensure_cover_downloaded(851013072, "https://cdn/deezer/cover.jpg")
    assert ok is True
    assert called == []  # already on disk → no network


def test_no_download_without_source_url(portades_root, monkeypatch):
    called = []
    monkeypatch.setattr(
        manager,
        "download_and_convert",
        lambda *a, **k: called.append(a) or True,
    )
    # Genuinely cover-less album: missing on disk, no Deezer URL → stays
    # on the logo, no download attempted (the one case where the logo is
    # correct).
    ok = nc.ensure_cover_downloaded(851013072, None)
    assert ok is False
    assert called == []


def test_no_download_without_deezer_id(portades_root, monkeypatch):
    called = []
    monkeypatch.setattr(
        manager,
        "download_and_convert",
        lambda *a, **k: called.append(a) or True,
    )
    assert nc.ensure_cover_downloaded(None, "https://cdn/deezer/cover.jpg") is False
    assert called == []


def test_never_raises_on_download_error(portades_root, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(manager, "download_and_convert", boom)
    # Must swallow and return False — a hiccup can't break the send.
    assert (
        nc.ensure_cover_downloaded(851013072, "https://cdn/deezer/cover.jpg") is False
    )
