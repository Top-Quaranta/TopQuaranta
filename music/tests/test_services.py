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
        rebutjar_canco(c, "desvincular_canco")
        c.refresh_from_db()
        assert c.verificada is False
        assert c.activa is False
        assert HistorialRevisio.objects.filter(
            artista_nom=a.nom, decisio="rebutjada", motiu="desvincular_canco"
        ).exists()

    def test_motiu_artista_incorrecte_triggers_unlink_attempt(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=12345)
        c = _mk_canco(a)
        # Only one Cançó, rejected for artista_incorrecte → eligible
        # for auto-unlink (no other active tracks; only motiu present).
        rebutjar_canco(c, "desvincular_artista")
        a.refresh_from_db()
        assert a.deezer_ids.count() == 0  # unlinked

    def test_no_unlink_for_other_motius(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=12345)
        c = _mk_canco(a)
        rebutjar_canco(c, "desvincular_canco")
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
        rebutjar_canco(c1, "desvincular_artista")
        rebutjar_canco(c2, "desvincular_canco")
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
        rebutjar_canco(c, "desvincular_artista")
        a.refresh_from_db()
        ids = sorted(a.deezer_ids.values_list("deezer_id", flat=True))
        assert ids == [111]  # 222 unlinked, 111 kept

    def test_multi_profile_defers_when_source_unknown(self):
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=111, principal=True)
        ArtistaDeezer.objects.create(artista=a, deezer_id=222)
        album = _mk_album(a, source_deezer_id=None)  # unknown
        c = _mk_canco(a, album=album)
        rebutjar_canco(c, "desvincular_artista")
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
        rebutjar_canco(c, "desvincular_artista")
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
    def test_multi_territori_artista_does_not_overflow_historial(self, _ix):
        """Caught 2026-05-08: a manual `aprovar_canco` on a multi-
        territori artista crashed with `value too long for type
        character varying(10)`. `crear_historial` does
        ",".join(territoris) and the column was max_length=10,
        which only fits a single 4-char code. Bumped to 100 + the
        join is truncated defensively. This test pins both — fails
        if either side regresses (column shrinks, or someone drops
        the slice in `crear_historial`)."""
        from music.models import Territori

        a = _mk_artista()
        for codi, nom in (
            ("CAT", "Catalunya"),
            ("VAL", "País Valencià"),
            ("BAL", "Illes Balears"),
        ):
            t, _ = Territori.objects.get_or_create(codi=codi, defaults={"nom": nom})
            a.territoris.add(t)
        c = _mk_canco(a, verificada=False)

        aprovar_canco(c)  # must not raise

        h = HistorialRevisio.objects.filter(artista_nom=a.nom).first()
        assert h is not None
        assert "CAT" in h.artista_territori
        assert "," in h.artista_territori  # confirms it's the joined form

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


# ── processar_collaboradors_pendents ────────────────────────────────


@pytest.mark.django_db
class TestProcessarCollaboradorsPendents:
    @patch("web.seo.indexnow.notify_canco")
    def test_creates_pendent_artista_from_raw_on_approve(self, _ix):
        """The deferred contributor materialises into a pendent
        Artista + ArtistaDeezer + artistes_col only when the
        canco is approved."""
        a = _mk_artista()
        c = _mk_canco(
            a,
            verificada=False,
            contributors_raw=[
                {"deezer_id": 9991, "name": "Producer Foo", "role": "secondary"}
            ],
        )
        aprovar_canco(c)
        c.refresh_from_db()
        assert c.contributors_raw == []
        # Pendent created.
        producer = Artista.objects.get(nom="Producer Foo")
        assert producer.aprovat is False
        assert producer.pendent_review is True
        assert producer.font_descoberta == "deezer_contributor"
        assert ArtistaDeezer.objects.filter(deezer_id=9991, artista=producer).exists()
        assert producer in c.artistes_col.all()

    @patch("web.seo.indexnow.notify_canco")
    def test_reuses_existing_artista_by_deezer_id(self, _ix):
        """A contributor whose Deezer ID already maps to an existing
        Artista must NOT create a duplicate; it links via
        artistes_col instead."""
        a = _mk_artista()
        existing = _mk_artista(nom="Existing Featuring")
        ArtistaDeezer.objects.create(artista=existing, deezer_id=4242, principal=True)
        c = _mk_canco(
            a,
            verificada=False,
            contributors_raw=[
                {"deezer_id": 4242, "name": "Some Other Name", "role": "secondary"}
            ],
        )
        aprovar_canco(c)
        c.refresh_from_db()
        assert c.contributors_raw == []
        assert Artista.objects.filter(nom="Some Other Name").count() == 0
        assert existing in c.artistes_col.all()

    @patch("web.seo.indexnow.notify_canco")
    def test_skips_self_collab(self, _ix):
        """A contributor whose Deezer ID is one of the canco's
        artista's own profiles is a self-collab — skip silently."""
        a = _mk_artista()
        ArtistaDeezer.objects.create(artista=a, deezer_id=11, principal=True)
        ArtistaDeezer.objects.create(artista=a, deezer_id=22, principal=False)
        c = _mk_canco(
            a,
            verificada=False,
            contributors_raw=[{"deezer_id": 22, "name": a.nom, "role": "main"}],
        )
        aprovar_canco(c)
        c.refresh_from_db()
        assert c.contributors_raw == []
        assert c.artistes_col.count() == 0

    @patch("web.seo.indexnow.notify_canco")
    def test_no_pendent_creation_when_canco_rebutjada(self, _ix):
        """Songs that get rejected never enter the verified path —
        their `contributors_raw` stays untouched, no pendents bloom.
        This is the whole point of the deferral."""
        from music.services import rebutjar_canco

        a = _mk_artista()
        c = _mk_canco(
            a,
            verificada=False,
            contributors_raw=[
                {"deezer_id": 7777, "name": "Wrong Featuring", "role": "secondary"}
            ],
        )
        rebutjar_canco(c, "desvincular_album")
        # No pendent created from the contributors_raw.
        assert not Artista.objects.filter(nom="Wrong Featuring").exists()
        assert not ArtistaDeezer.objects.filter(deezer_id=7777).exists()


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

        deleted = rebutjar_album(album, "desvincular_canco")
        album.refresh_from_db()
        verified.refresh_from_db()

        assert deleted == 2
        assert album.descartat is True
        assert verified.verificada is True  # untouched
        assert (
            HistorialRevisio.objects.filter(
                artista_nom=a.nom, decisio="rebutjada", motiu="desvincular_canco"
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

        deleted = rebutjar_artista(a, "desvincular_canco")
        a.refresh_from_db()
        album1.refresh_from_db()
        album2.refresh_from_db()
        verified.refresh_from_db()

        assert deleted == 1  # only the unverified one
        assert a.deezer_ids.count() == 0  # M2M cleared
        assert album1.descartat is True
        assert album2.descartat is True
        assert verified.verificada is True  # untouched


# ── Orphan-pendent predicate + de-approval hook (informe 2a) ────────


@pytest.mark.django_db
class TestOrphanPendents:
    """Guards for the ingest-hole fix: a pendent canço must have ≥1
    approved artist (main or collaborator) to stay reviewable."""

    @staticmethod
    def _mk(nom, *, aprovat):
        return Artista.objects.create(nom=nom, lastfm_nom=nom, aprovat=aprovat)

    def _pendent_song(self, main, collabs=(), contributors_raw=None):
        c = _mk_canco(main, verificada=False, activa=True)
        if contributors_raw is not None:
            c.contributors_raw = contributors_raw
            c.save(update_fields=["contributors_raw"])
        for col in collabs:
            c.artistes_col.add(col)
        return c

    def test_has_approved_artist_main(self):
        from music.services import has_approved_artist

        a = self._mk("MainOK", aprovat=True)
        assert has_approved_artist(self._pendent_song(a)) is True

    def test_has_approved_artist_via_collab(self):
        from music.services import has_approved_artist

        main = self._mk("MainPend", aprovat=False)
        col = self._mk("ColOK", aprovat=True)
        assert has_approved_artist(self._pendent_song(main, [col])) is True

    def test_has_approved_artist_none(self):
        from music.services import has_approved_artist

        main = self._mk("MainPend", aprovat=False)
        col = self._mk("ColPend", aprovat=False)
        assert has_approved_artist(self._pendent_song(main, [col])) is False

    def test_orphan_qs_matches_real_orphan(self):
        from music.services import orphan_pendents_qs

        main = self._mk("MP", aprovat=False)
        col = self._mk("CP", aprovat=False)
        orphan = self._pendent_song(main, [col])
        assert orphan_pendents_qs().filter(pk=orphan.pk).exists()

    def test_orphan_qs_spares_approved_collab(self):
        from music.services import orphan_pendents_qs

        main = self._mk("MP2", aprovat=False)
        col = self._mk("COK", aprovat=True)
        song = self._pendent_song(main, [col])
        assert not orphan_pendents_qs().filter(pk=song.pk).exists()

    def test_orphan_qs_spares_pending_deferred_contributors(self):
        from music.services import orphan_pendents_qs

        main = self._mk("MP3", aprovat=False)
        song = self._pendent_song(
            main,
            contributors_raw=[{"name": "X", "deezer_id": 9, "role": "secondary"}],
        )
        # No approved artist, but deferred contributors may yet resolve.
        assert not orphan_pendents_qs().filter(pk=song.pk).exists()

    def test_orphan_qs_ignores_verified(self):
        from music.services import orphan_pendents_qs

        main = self._mk("MP4", aprovat=False)
        song = self._pendent_song(main)
        Canco.objects.filter(pk=song.pk).update(verificada=True)
        assert not orphan_pendents_qs().filter(pk=song.pk).exists()

    def test_reject_artista_deactivates_orphaned_collab_song(self):
        """The Irokz mechanism: rejecting the only approved artist (a
        collaborator) on a pendent song leaves it with no approved
        artist → the hook deactivates it."""
        main = self._mk("IrokzPend", aprovat=False)
        col = self._mk("AishaOK", aprovat=True)
        song = self._pendent_song(main, [col])
        rebutjar_artista(col, "desvincular_artista")
        song.refresh_from_db()
        assert song.activa is False

    def test_reject_artista_keeps_song_with_other_approved_artist(self):
        main = self._mk("ApprovedMain", aprovat=True)
        col = self._mk("RejectMe", aprovat=True)
        song = self._pendent_song(main, [col])
        rebutjar_artista(col, "desvincular_artista")
        song.refresh_from_db()
        assert song.activa is True  # main still approved

    def test_reject_artista_spares_song_with_pending_contributors(self):
        main = self._mk("MainPend5", aprovat=False)
        col = self._mk("RejectMe5", aprovat=True)
        song = self._pendent_song(
            main,
            [col],
            contributors_raw=[{"name": "Y", "deezer_id": 7, "role": "secondary"}],
        )
        rebutjar_artista(col, "desvincular_artista")
        song.refresh_from_db()
        assert song.activa is True  # deferred contributors may resolve
