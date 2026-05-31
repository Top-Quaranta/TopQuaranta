"""Tests for the self-hosted cover pipeline (Fase 1).

Manager tests use a tmp PORTADES_ROOT, mock `requests.get`, and a
real Pillow round-trip so the variant dimensions are actually
verified. The command test mocks the manager so it exercises only
candidate selection + wiring (no real download).

# Spec: docs/architecture/portades.md
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from PIL import Image

from ingesta.portades import manager
from music.models import Album, Artista, ArtistaDeezer, Canco


def _png_bytes(size=(1000, 1000), color=(200, 50, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


_DZ_URL = "https://cdn-images.dzcdn.net/images/cover/abc123/500x500-000000-80-0-0.jpg"


@pytest.fixture
def portades_root(tmp_path, settings):
    settings.PORTADES_ROOT = str(tmp_path)
    settings.PORTADES_VARIANTS = [250, 500]
    settings.PORTADES_FORMATS = ["avif", "webp", "jpg"]
    settings.PORTADES_DEEZER_SOURCE_SIZE = 1000
    return tmp_path


# ── path_for ─────────────────────────────────────────────────────────


def test_path_for_builds_deterministic_paths(portades_root):
    assert (
        manager.path_for("album", 12345, 500, "webp")
        == portades_root / "album" / "12345-500.webp"
    )
    assert manager.path_for("cancio", 7, 250, "avif").name == "7-250.avif"
    assert manager.path_for("artista", 9, 500, "jpg").parent.name == "artista"


def test_path_for_rejects_unknown_entitat(portades_root):
    with pytest.raises(ValueError):
        manager.path_for("nope", 1, 500, "webp")


# ── exists ───────────────────────────────────────────────────────────


def test_exists_keys_on_500_webp_sentinel(portades_root):
    assert manager.exists("album", 1) is False
    sentinel = manager.path_for("album", 1, 500, "webp")
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_bytes(b"not-a-real-image")
    assert manager.exists("album", 1) is True


# ── download_and_convert ─────────────────────────────────────────────


@patch("ingesta.portades.manager.requests.get")
def test_download_and_convert_success(mock_get, portades_root):
    resp = MagicMock(content=_png_bytes())
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    ok = manager.download_and_convert("album", 999, _DZ_URL)
    assert ok is True

    # All variant×format files exist with the right dimensions.
    for mida in (250, 500):
        for fmt in ("avif", "webp", "jpg"):
            f = manager.path_for("album", 999, mida, fmt)
            assert f.is_file(), f"missing {f}"
            with Image.open(f) as im:
                assert im.size == (mida, mida)

    # The stored 500px URL was normalised to the 1000px source.
    requested_url = mock_get.call_args[0][0]
    assert "1000x1000-" in requested_url


@patch("ingesta.portades.manager.requests.get")
def test_download_failure_returns_false_and_cleans_up(mock_get, portades_root):
    mock_get.side_effect = Exception("network down")
    ok = manager.download_and_convert("album", 5, _DZ_URL)
    assert ok is False
    assert all(not p.exists() for p in manager._written_paths("album", 5))


@patch("ingesta.portades.manager.requests.get")
def test_convert_failure_cleans_up_partial_writes(mock_get, settings, portades_root):
    # Use webp+jpg only so this test does not depend on the AVIF plugin.
    settings.PORTADES_FORMATS = ["webp", "jpg"]
    resp = MagicMock(content=_png_bytes())
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    real_save = manager._save_variant

    def flaky_save(img, dest, mida, fmt):
        if fmt == "jpg":  # second format → some webp files already written
            raise RuntimeError("encode boom")
        return real_save(img, dest, mida, fmt)

    with patch("ingesta.portades.manager._save_variant", side_effect=flaky_save):
        ok = manager.download_and_convert("album", 77, _DZ_URL)

    assert ok is False
    leftover = [p for p in manager._written_paths("album", 77) if p.exists()]
    assert leftover == [], f"partial writes not cleaned: {leftover}"


def test_delete_removes_all_variants(portades_root):
    resp = MagicMock(content=_png_bytes())
    resp.raise_for_status = MagicMock()
    with patch("ingesta.portades.manager.requests.get", return_value=resp):
        assert manager.download_and_convert("album", 321, _DZ_URL) is True
    assert manager.exists("album", 321) is True
    manager.delete("album", 321)
    assert manager.exists("album", 321) is False
    assert all(not p.exists() for p in manager._written_paths("album", 321))


# ── command ──────────────────────────────────────────────────────────


@pytest.mark.django_db
@patch("ingesta.management.commands.descarregar_portades.download_and_convert")
@patch("ingesta.management.commands.descarregar_portades.time.sleep")
def test_command_album_wires_deezer_id_and_url(mock_sleep, mock_dl, portades_root):
    mock_dl.return_value = True
    a = Artista.objects.create(nom="X")
    al = Album.objects.create(artista=a, nom="Al", deezer_id=4242, imatge_url=_DZ_URL)
    # An album without a cover must be ignored.
    Album.objects.create(artista=a, nom="No cover", deezer_id=4243, imatge_url="")

    call_command("descarregar_portades", entitat="album", limit=10)

    mock_dl.assert_called_once_with("album", 4242, al.imatge_url)


@pytest.mark.django_db
@patch("ingesta.management.commands.descarregar_portades.download_and_convert")
@patch("ingesta.management.commands.descarregar_portades.time.sleep")
@patch("ingesta.management.commands.descarregar_portades.exists")
def test_command_skips_already_present_without_force(
    mock_exists, mock_sleep, mock_dl, portades_root
):
    mock_exists.return_value = True  # already on disk
    a = Artista.objects.create(nom="Y")
    Album.objects.create(artista=a, nom="Al2", deezer_id=5555, imatge_url=_DZ_URL)

    call_command("descarregar_portades", entitat="album", limit=10)

    mock_dl.assert_not_called()


@pytest.mark.django_db
@patch("ingesta.management.commands.descarregar_portades.download_and_convert")
@patch("ingesta.management.commands.descarregar_portades.time.sleep")
def test_command_artista_uses_principal_deezer_id(mock_sleep, mock_dl, portades_root):
    mock_dl.return_value = True
    a = Artista.objects.create(nom="Z", imatge_url=_DZ_URL)
    ArtistaDeezer.objects.create(artista=a, deezer_id=8888, principal=True)

    call_command("descarregar_portades", entitat="artista", limit=10)

    mock_dl.assert_called_once_with("artista", 8888, _DZ_URL)


# ── budget split across entitats (--entitat all) ─────────────────────


def _seed_entities(n_album, n_cancio, n_artista):
    """Create exactly n candidates per entity, kept disjoint:
    - structural artista carries no image → not an artista candidate;
    - cançó parent albums have a cover but NO deezer_id → cancio
      candidates without also being album candidates."""
    struct = Artista.objects.create(nom="struct")  # imatge_url="" → not a candidate
    for i in range(n_album):
        Album.objects.create(
            artista=struct, nom=f"alb{i}", deezer_id=10000 + i, imatge_url=_DZ_URL
        )
    for i in range(n_cancio):
        alb = Album.objects.create(
            artista=struct, nom=f"calb{i}", imatge_url=_DZ_URL  # deezer_id=None
        )
        Canco.objects.create(
            artista=struct, album=alb, nom=f"c{i}", deezer_id=20000 + i
        )
    for i in range(n_artista):
        a = Artista.objects.create(nom=f"art{i}", imatge_url=_DZ_URL)
        ArtistaDeezer.objects.create(artista=a, deezer_id=30000 + i, principal=True)


def _calls_per_entity(mock_dl):
    counts = {"album": 0, "cancio": 0, "artista": 0}
    for c in mock_dl.call_args_list:
        counts[c.args[0]] += 1
    return counts


@pytest.mark.django_db
@patch("ingesta.management.commands.descarregar_portades.download_and_convert")
@patch("ingesta.management.commands.descarregar_portades.time.sleep")
def test_all_even_split(mock_sleep, mock_dl, portades_root):
    """6/6/6 candidates, limit=9 → 3 per entity."""
    mock_dl.return_value = True
    _seed_entities(6, 6, 6)
    call_command("descarregar_portades", entitat="all", limit=9)
    assert _calls_per_entity(mock_dl) == {"album": 3, "cancio": 3, "artista": 3}


@pytest.mark.django_db
@patch("ingesta.management.commands.descarregar_portades.download_and_convert")
@patch("ingesta.management.commands.descarregar_portades.time.sleep")
def test_all_fallthrough(mock_sleep, mock_dl, portades_root):
    """1 album + 5 cancio + 5 artista, limit=9 → 1 album, 5 cancio
    (gets album's 2 leftover), 3 artista (absorbs the rest)."""
    mock_dl.return_value = True
    _seed_entities(1, 5, 5)
    call_command("descarregar_portades", entitat="all", limit=9)
    assert _calls_per_entity(mock_dl) == {"album": 1, "cancio": 5, "artista": 3}


@pytest.mark.django_db
@patch("ingesta.management.commands.descarregar_portades.download_and_convert")
@patch("ingesta.management.commands.descarregar_portades.time.sleep")
def test_single_entity_mode_unchanged(mock_sleep, mock_dl, portades_root):
    """--entitat album --limit 5 still caps at 5 (no split)."""
    mock_dl.return_value = True
    _seed_entities(8, 0, 0)
    call_command("descarregar_portades", entitat="album", limit=5)
    counts = _calls_per_entity(mock_dl)
    assert counts["album"] == 5
    assert counts["cancio"] == 0 and counts["artista"] == 0
