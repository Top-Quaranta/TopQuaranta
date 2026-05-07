"""Coverage for `music.services` business-logic functions.

Targets the four public entry points + the homonym-Deezer auto-unlink
path. The audit (May-2026) flagged services.py as 50% covered with
the auto-unlink branches entirely uncovered — exactly the place
where a regression would silently break the staff flow.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from music.models import (
    Album,
    Artista,
    ArtistaDeezer,
    Canco,
    HistorialRevisio,
)
from music.services import (
    _try_auto_unlink_homonym_deezer,
    aprovar_canco,
    aprovar_canco_auto_ml,
    rebutjar_album,
    rebutjar_artista,
    rebutjar_canco,
)

# ── Helpers ─────────────────────────────────────────────────────────


def _mk_artista(nom="Test", **kwargs):
    return Artista.objects.create(nom=nom, lastfm_nom=nom, aprovat=True, **kwargs)


def _mk_album(artista, source_deezer_id=None, **kwargs):
    return Album.objects.create(
        artista=artista,
        nom=kwargs.pop("nom", "Album"),
        data_llancament=kwargs.pop("data_llancament", date(2026, 1, 1)),
        source_deezer_id=source_deezer_id,
        **kwargs,
    )


def _mk_canco(artista, album=None, **kwargs):
    return Canco.objects.create(
        artista=artista,
        album=album or _mk_album(artista),
        nom=kwargs.pop("nom", "Track"),
        data_llancament=kwargs.pop("data_llancament", date(2026, 1, 1)),
        verificada=kwargs.pop("verificada", False),
        activa=kwargs.pop("activa", True),
        **kwargs,
    )


# ── rebutjar_canco ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestRebutjarCanco:
    def test_marks_unverified_inactive_and_logs_historial(self):
        a = _mk_artista()
        c = _mk_canco(a, verificada=True)
        rebutjar_canco(c, "no_catala")
        c.refresh_from_db()
        assert c.verificada is False
        assert c.activa is False
        assert HistorialRevisio.objects.filter(
            artista_nom=a.nom, decisio="rebutjada", motiu="no_catala"
        ).exists()

    def test_motiu_artista_incorrecte_triggers_unlink_attempt(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=12345)
        c = _mk_canco(a)
        # Only one Cançó, rejected for artista_incorrecte → eligible
        # for auto-unlink (no other active tracks; only motiu present).
        rebutjar_canco(c, "artista_incorrecte")
        a.refresh_from_db()
        assert a.deezer_ids.count() == 0  # unlinked

    def test_no_unlink_for_other_motius(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=12345)
        c = _mk_canco(a)
        rebutjar_canco(c, "no_catala")
        assert a.deezer_ids.count() == 1


# ── _try_auto_unlink_homonym_deezer (the multi-branch heuristic) ────


@pytest.mark.django_db
class TestTryAutoUnlink:
    def test_no_op_when_active_canco_remains(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=12345)
        # Keep an active canço — defer to human.
        _mk_canco(a, activa=True, verificada=True)
        assert _try_auto_unlink_homonym_deezer(a) is False
        assert a.deezer_ids.count() == 1

    def test_no_op_when_no_rejection_history(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=12345)
        # No HistorialRevisio rows at all.
        assert _try_auto_unlink_homonym_deezer(a) is False
        assert a.deezer_ids.count() == 1

    def test_no_op_when_mixed_motius(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=12345)
        c1 = _mk_canco(a, nom="T1")
        c2 = _mk_canco(a, nom="T2")
        # Two rejections, different motius → defer.
        rebutjar_canco(c1, "artista_incorrecte")
        rebutjar_canco(c2, "no_catala")
        # The first call may have unlinked already; restore for test.
        if a.deezer_ids.count() == 0:
            ArtistaDeezer.objects.create(artista=a, deezer_id=12345)
        assert _try_auto_unlink_homonym_deezer(a) is False
        assert a.deezer_ids.count() == 1

    def test_multi_profile_unlinks_only_source(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=111, principal=True)
        ArtistaDeezer.objects.create(artista=a, deezer_id=222)
        album = _mk_album(a, source_deezer_id=222)
        c = _mk_canco(a, album=album)
        rebutjar_canco(c, "artista_incorrecte")
        a.refresh_from_db()
        ids = sorted(a.deezer_ids.values_list("deezer_id", flat=True))
        assert ids == [111]  # 222 unlinked, 111 kept

    def test_multi_profile_defers_when_source_unknown(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=111, principal=True)
        ArtistaDeezer.objects.create(artista=a, deezer_id=222)
        album = _mk_album(a, source_deezer_id=None)  # unknown
        c = _mk_canco(a, album=album)
        rebutjar_canco(c, "artista_incorrecte")
        a.refresh_from_db()
        # Both kept — defer to staff.
        assert a.deezer_ids.count() == 2

    def test_multi_profile_no_match_for_source_logs_warning(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=111, principal=True)
        ArtistaDeezer.objects.create(artista=a, deezer_id=222)
        # Source doesn't match any of the linked profiles.
        album = _mk_album(a, source_deezer_id=999)
        c = _mk_canco(a, album=album)
        rebutjar_canco(c, "artista_incorrecte")
        a.refresh_from_db()
        # Both kept — can't unlink something that's not there.
        assert a.deezer_ids.count() == 2


# ── aprovar_canco / aprovar_canco_auto_ml ───────────────────────────


@pytest.mark.django_db
class TestAprovarCanco:
    @patch("web.seo.indexnow.notify_canco")
    def test_approves_and_logs_ok(self, mock_indexnow):
        a = _mk_artista()
        c = _mk_canco(a, verificada=False)
        aprovar_canco(c)
        c.refresh_from_db()
        assert c.verificada is True
        assert HistorialRevisio.objects.filter(
            artista_nom=a.nom, decisio="aprovada", motiu="ok"
        ).exists()
        mock_indexnow.assert_called_once_with(c)

    @patch("web.seo.indexnow.notify_canco")
    def test_auto_ml_uses_distinct_motiu(self, mock_indexnow):
        from music.constants import MOTIU_AUTO_ML

        a = _mk_artista()
        c = _mk_canco(a, verificada=False)
        aprovar_canco_auto_ml(c)
        c.refresh_from_db()
        assert c.verificada is True
        assert HistorialRevisio.objects.filter(
            artista_nom=a.nom, decisio="aprovada", motiu=MOTIU_AUTO_ML
        ).exists()


# ── rebutjar_album / rebutjar_artista ──────────────────────────────


@pytest.mark.django_db
class TestRebutjarAlbum:
    def test_unverified_tracks_deleted_album_marked_descartat(self):
        a = _mk_artista()
        album = _mk_album(a)
        # 2 unverified, 1 verified → only the 2 unverified should die.
        _mk_canco(a, album=album, nom="U1", verificada=False)
        _mk_canco(a, album=album, nom="U2", verificada=False)
        verified = _mk_canco(a, album=album, nom="V", verificada=True)

        deleted = rebutjar_album(album, "no_musica")
        album.refresh_from_db()
        verified.refresh_from_db()

        assert deleted == 2
        assert album.descartat is True
        assert verified.verificada is True  # untouched
        assert (
            HistorialRevisio.objects.filter(
                artista_nom=a.nom, decisio="rebutjada", motiu="no_musica"
            ).count()
            == 2
        )


@pytest.mark.django_db
class TestRebutjarArtista:
    def test_clears_deezer_unverified_tracks_and_marks_albums(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=42)
        album1 = _mk_album(a, nom="A1")
        album2 = _mk_album(a, nom="A2")
        _mk_canco(a, album=album1, nom="U", verificada=False)
        verified = _mk_canco(a, album=album2, nom="V", verificada=True)

        deleted = rebutjar_artista(a, "no_catala")
        a.refresh_from_db()
        album1.refresh_from_db()
        album2.refresh_from_db()
        verified.refresh_from_db()

        assert deleted == 1  # only the unverified one
        assert a.deezer_ids.count() == 0  # M2M cleared
        assert album1.descartat is True
        assert album2.descartat is True
        assert verified.verificada is True  # untouched
