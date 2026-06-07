"""Guards for the recurring orphan-canço sweep (FASE 2, informe 2a).

The command deactivates pendent cançons with no approved artist, reusing
`orphan_pendents_qs` (so the contributors_raw caveat holds) and adding a
grace window so it never races an in-progress approval.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from music.models import Album, Artista, Canco


def _artista(nom, *, aprovat):
    return Artista.objects.create(nom=nom, lastfm_nom=nom, aprovat=aprovat)


def _canco(nom, main, *, collabs=(), contributors_raw=None, age_days=30):
    al = Album.objects.create(artista=main, nom=f"AL-{nom}")
    c = Canco.objects.create(
        artista=main,
        album=al,
        nom=nom,
        data_llancament=date(2026, 1, 1),
        verificada=False,
        activa=True,
    )
    if contributors_raw is not None:
        c.contributors_raw = contributors_raw
        c.save(update_fields=["contributors_raw"])
    for col in collabs:
        c.artistes_col.add(col)
    # created_at is auto_now_add; override via update() to age the row.
    Canco.objects.filter(pk=c.pk).update(
        created_at=timezone.now() - timedelta(days=age_days)
    )
    c.refresh_from_db()
    return c


def _run(**kw):
    out = StringIO()
    call_command("netejar_cancons_orfes", stdout=out, **kw)
    return out.getvalue()


@pytest.mark.django_db
def test_deactivates_old_orphan():
    main = _artista("MainPend", aprovat=False)
    col = _artista("ColPend", aprovat=False)
    c = _canco("OldOrphan", main, collabs=[col], age_days=30)
    _run()
    c.refresh_from_db()
    assert c.activa is False


@pytest.mark.django_db
def test_spares_orphan_within_grace():
    main = _artista("MainPend2", aprovat=False)
    c = _canco("YoungOrphan", main, age_days=2)  # < 7d default grace
    _run()
    c.refresh_from_db()
    assert c.activa is True


@pytest.mark.django_db
def test_spares_song_with_approved_artist():
    main = _artista("MainOK", aprovat=True)
    c = _canco("HasApproved", main, age_days=30)
    _run()
    c.refresh_from_db()
    assert c.activa is True


@pytest.mark.django_db
def test_spares_song_with_approved_collab():
    main = _artista("MainPend3", aprovat=False)
    col = _artista("ColOK", aprovat=True)
    c = _canco("HasApprovedCollab", main, collabs=[col], age_days=30)
    _run()
    c.refresh_from_db()
    assert c.activa is True


@pytest.mark.django_db
def test_spares_song_with_pending_contributors():
    main = _artista("MainPend4", aprovat=False)
    c = _canco(
        "AwaitingCollabs",
        main,
        contributors_raw=[{"name": "Z", "deezer_id": 3, "role": "secondary"}],
        age_days=30,
    )
    _run()
    c.refresh_from_db()
    assert c.activa is True


@pytest.mark.django_db
def test_dry_run_changes_nothing():
    main = _artista("MainPend5", aprovat=False)
    c = _canco("OldOrphanDry", main, age_days=30)
    out = _run(dry_run=True)
    c.refresh_from_db()
    assert c.activa is True
    assert "WORK_DONE=1" in out  # would-deactivate count surfaced


@pytest.mark.django_db
def test_grace_days_flag_override():
    main = _artista("MainPend6", aprovat=False)
    c = _canco("ThreeDayOrphan", main, age_days=3)
    # Default grace (7d) spares it; grace 1 deactivates it.
    _run(grace_days=1)
    c.refresh_from_db()
    assert c.activa is False
