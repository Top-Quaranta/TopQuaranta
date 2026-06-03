"""Tests for the Sprint Portal Artista Ampliat slug-based endpoints.

Covers:
  * Permission (anon, non-manager, verified manager) on each route.
  * qualitat: 9 indicators + score calculation.
  * editar (slug): same contract as the legacy pk endpoint + imatge_url.
  * Deezer IDs M2M: add (deezer-mocked) / delete with last-row guard.
  * Last.fm aliases M2M: add (case-insensitive dedup) / delete / promote
    to prioritari + last-prioritari guard.
  * Localitats M2M: add (municipi or manual) / delete.
  * Cançons pendents + ping-staff: cooldown + audit row + DM to admin.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from comptes.models import Missatge, UserArtista, Usuari
from music.models import (
    Artista,
    ArtistaDeezer,
    ArtistaLastfmAlias,
    ArtistaLocalitat,
    Canco,
    HistorialRevisio,
    Municipi,
    StaffAuditLog,
    Territori,
)

# ───────────────────────── fixtures ──────────────────────────────


@pytest.fixture
def territori(db):
    t, _ = Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Principat"})
    return t


@pytest.fixture
def municipi(db, territori):
    return Municipi.objects.create(
        nom="Castelló", comarca="Plana Alta", territori=territori
    )


@pytest.fixture
def artista(db):
    a = Artista.objects.create(
        nom="Portal Band",
        slug="portal-band",
        aprovat=True,
        lastfm_nom="",
    )
    ArtistaDeezer.objects.create(artista=a, deezer_id=999001, principal=True)
    return a


@pytest.fixture
def admin_user(db):
    # The seed migration `comptes.0016_admin_pseudouser` already creates
    # a row with username="admin"; reuse it (or create if the test DB
    # was bootstrapped without migrations).
    return Usuari.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@topquaranta.cat",
            "is_active": True,
        },
    )[0]


@pytest.fixture
def gestor(db, artista):
    u = Usuari.objects.create_user(
        username="g_portal", email="gp@example.com", password="x"
    )
    UserArtista.objects.create(
        usuari=u,
        artista=artista,
        sollicitud_text="x" * 25,
        verificat=True,
        estat=UserArtista.ESTAT_APROVAT,
    )
    return u


@pytest.fixture
def other(db):
    return Usuari.objects.create_user(
        username="other_portal", email="op@example.com", password="x"
    )


@pytest.fixture
def client_g(gestor):
    c = APIClient()
    c.force_authenticate(user=gestor)
    return c


def _url(slug, suffix=""):
    return f"/api/v1/compte/artista/{slug}/{suffix}"


# ───────────────────────── qualitat ──────────────────────────────


def test_qualitat_permission(artista, other):
    c = APIClient()
    assert c.get(_url(artista.slug, "qualitat/")).status_code in (401, 403)
    c.force_authenticate(user=other)
    assert c.get(_url(artista.slug, "qualitat/")).status_code == 403


def test_qualitat_shape(client_g, artista):
    r = client_g.get(_url(artista.slug, "qualitat/"))
    assert r.status_code == 200
    body = r.json()
    assert "score" in body and 0 <= body["score"] <= 100
    assert "n_alerts" in body
    assert isinstance(body["indicators"], list)
    assert len(body["indicators"]) == 9
    for ind in body["indicators"]:
        assert set(ind.keys()) >= {"key", "label", "severity", "message"}
        assert ind["severity"] in {"success", "warning", "danger"}


def test_qualitat_deezer_vinculat_green(client_g, artista):
    r = client_g.get(_url(artista.slug, "qualitat/")).json()
    deezer = next(i for i in r["indicators"] if i["key"] == "deezer_vinculat")
    assert deezer["severity"] == "success"


# ───────────────────────── editar (slug) ─────────────────────────


def test_editar_get_includes_extended_surface(client_g, artista):
    r = client_g.get(_url(artista.slug, "editar/"))
    assert r.status_code == 200
    body = r.json()
    assert body["nom"] == "Portal Band"
    assert "imatge_url" in body
    assert isinstance(body["deezer_ids"], list) and len(body["deezer_ids"]) == 1
    assert isinstance(body["lastfm_aliases"], list)
    assert isinstance(body["localitats"], list)


def test_editar_patch_imatge_url(client_g, artista):
    r = client_g.patch(
        _url(artista.slug, "editar/"),
        {"imatge_url": "https://www.topquaranta.cat/media/artista/x/abc.webp"},
        format="json",
    )
    assert r.status_code == 200
    artista.refresh_from_db()
    assert artista.imatge_url.endswith("abc.webp")


def test_editar_patch_rejects_bad_url(client_g, artista):
    r = client_g.patch(
        _url(artista.slug, "editar/"),
        {"imatge_url": "javascript:alert(1)"},
        format="json",
    )
    assert r.status_code == 400
    assert "imatge_url" in r.json()["errors"]


# ───────────────────────── Deezer IDs ────────────────────────────


@pytest.fixture
def mock_deezer_ok():
    """Stub Deezer's `/artist/<id>` to return a happy payload."""

    class _R:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": 1, "name": "fake"}

    with patch("web.api.compte_views.gestor_artista.requests.get", return_value=_R()):
        yield


def test_deezer_id_add_ok(client_g, artista, mock_deezer_ok):
    r = client_g.post(
        _url(artista.slug, "deezer-ids/"), {"deezer_id": 999002}, format="json"
    )
    assert r.status_code == 201
    assert artista.deezer_ids.filter(deezer_id=999002).exists()


def test_deezer_id_add_duplicate_per_artist(client_g, artista, mock_deezer_ok):
    r = client_g.post(
        _url(artista.slug, "deezer-ids/"), {"deezer_id": 999001}, format="json"
    )
    assert r.status_code == 400


def test_deezer_id_delete_last_blocked(client_g, artista):
    last = artista.deezer_ids.first()
    r = client_g.delete(_url(artista.slug, f"deezer-ids/{last.deezer_id}/"))
    assert r.status_code == 400
    assert artista.deezer_ids.count() == 1


def test_deezer_id_delete_non_last_ok(client_g, artista):
    ArtistaDeezer.objects.create(artista=artista, deezer_id=999003)
    r = client_g.delete(_url(artista.slug, "deezer-ids/999003/"))
    assert r.status_code == 200
    assert artista.deezer_ids.count() == 1


# ───────────────────────── Last.fm aliases ───────────────────────


def test_lastfm_alias_add_creates_confirmed(client_g, artista):
    r = client_g.post(
        _url(artista.slug, "lastfm-aliases/"),
        {"nom": "Pörtal Bànd"},
        format="json",
    )
    assert r.status_code == 201
    alias = ArtistaLastfmAlias.objects.get(artista=artista, nom="Pörtal Bànd")
    assert alias.confirmat is True
    assert alias.prioritari is False


def test_lastfm_alias_add_case_insensitive_dup(client_g, artista):
    ArtistaLastfmAlias.objects.create(artista=artista, nom="Portal", confirmat=True)
    r = client_g.post(
        _url(artista.slug, "lastfm-aliases/"), {"nom": "PORTAL"}, format="json"
    )
    assert r.status_code == 400


def test_lastfm_alias_set_prioritari(client_g, artista):
    a1 = ArtistaLastfmAlias.objects.create(
        artista=artista, nom="One", confirmat=True, prioritari=True
    )
    a2 = ArtistaLastfmAlias.objects.create(
        artista=artista, nom="Two", confirmat=True, prioritari=False
    )
    r = client_g.post(_url(artista.slug, f"lastfm-aliases/{a2.pk}/prioritari/"))
    assert r.status_code == 200
    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.prioritari is False
    assert a2.prioritari is True


def test_lastfm_alias_delete_prioritari_with_others_blocked(client_g, artista):
    prio = ArtistaLastfmAlias.objects.create(
        artista=artista, nom="One", confirmat=True, prioritari=True
    )
    ArtistaLastfmAlias.objects.create(
        artista=artista, nom="Two", confirmat=True, prioritari=False
    )
    r = client_g.delete(_url(artista.slug, f"lastfm-aliases/{prio.pk}/"))
    assert r.status_code == 400
    assert ArtistaLastfmAlias.objects.filter(pk=prio.pk).exists()


def test_lastfm_alias_delete_only_row_ok(client_g, artista):
    only = ArtistaLastfmAlias.objects.create(
        artista=artista, nom="Only", confirmat=True, prioritari=True
    )
    r = client_g.delete(_url(artista.slug, f"lastfm-aliases/{only.pk}/"))
    assert r.status_code == 200


# ───────────────────────── Localitats ────────────────────────────


def test_localitat_add_municipi(client_g, artista, municipi):
    r = client_g.post(
        _url(artista.slug, "localitats/"),
        {"municipi_pk": municipi.pk},
        format="json",
    )
    assert r.status_code == 201
    assert ArtistaLocalitat.objects.filter(artista=artista, municipi=municipi).exists()


def test_localitat_add_manual(client_g, artista):
    r = client_g.post(
        _url(artista.slug, "localitats/"),
        {"manual": "Sud de França"},
        format="json",
    )
    assert r.status_code == 201
    assert ArtistaLocalitat.objects.filter(
        artista=artista, municipi__isnull=True
    ).exists()


def test_localitat_add_duplicate_blocked(client_g, artista, municipi):
    ArtistaLocalitat.objects.create(artista=artista, municipi=municipi)
    r = client_g.post(
        _url(artista.slug, "localitats/"),
        {"municipi_pk": municipi.pk},
        format="json",
    )
    assert r.status_code == 400


def test_localitat_delete(client_g, artista, municipi):
    loc = ArtistaLocalitat.objects.create(artista=artista, municipi=municipi)
    r = client_g.delete(_url(artista.slug, f"localitats/{loc.pk}/"))
    assert r.status_code == 200
    assert not ArtistaLocalitat.objects.filter(pk=loc.pk).exists()


# ───────────────────────── Cançons pendents + ping ───────────────


@pytest.fixture
def cancons_pendents(db, artista):
    from music.models import Album

    album = Album.objects.create(artista=artista, nom="Pendent EP", slug="pendent-ep")
    return [
        Canco.objects.create(
            artista=artista,
            album=album,
            nom=f"Track {i}",
            slug=f"portal-band-track-{i}",
            verificada=False,
        )
        for i in range(3)
    ]


def test_cancons_pendents_list(client_g, artista, cancons_pendents):
    r = client_g.get(_url(artista.slug, "cancons-pendents/"))
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 3
    assert body["cooldown_until"] is None


def test_ping_staff_first_call_creates_sollicitud_and_audit(
    client_g, artista, cancons_pendents
):
    """Sprint Workflow: ping crea un SolicitudRevisio (no DM) + audit
    row + actualitza cooldown."""
    from comptes.models import SolicitudRevisio

    r = client_g.post(_url(artista.slug, "cancons-pendents/ping-staff/"))
    assert r.status_code == 201
    body = r.json()
    assert body["n_cancons"] == 3
    assert body["sollicitud_pk"]
    artista.refresh_from_db()
    assert artista.ultim_ping_revisio_at is not None
    s = SolicitudRevisio.objects.get(pk=body["sollicitud_pk"])
    assert s.artista_id == artista.pk
    assert s.n_pendents == 3
    assert s.estat == SolicitudRevisio.ESTAT_PENDENT
    assert StaffAuditLog.objects.filter(
        action="sollicitud_revisio_creada", target_id=artista.pk
    ).exists()


def test_ping_staff_cooldown_429(client_g, artista, cancons_pendents):
    artista.ultim_ping_revisio_at = timezone.now() - timedelta(days=2)
    artista.save(update_fields=["ultim_ping_revisio_at"])
    r = client_g.post(_url(artista.slug, "cancons-pendents/ping-staff/"))
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert "next_ping_at" in r.json()


def test_ping_staff_after_cooldown_passes(client_g, artista, cancons_pendents):
    artista.ultim_ping_revisio_at = timezone.now() - timedelta(days=8)
    artista.save(update_fields=["ultim_ping_revisio_at"])
    r = client_g.post(_url(artista.slug, "cancons-pendents/ping-staff/"))
    assert r.status_code == 201


# ───────────────────────── Quick fixes: rebutjades + ping mix ────


@pytest.fixture
def rebutjades_fixture(db, artista):
    """Three HistorialRevisio rebutjada rows tied to Portal Band's
    Deezer ID 999001, one per common motiu."""
    rows = []
    for motiu, nom in [
        ("desvincular_canco", "Track ES-only"),
        ("desvincular_album", "Track wrong-album"),
        ("desvincular_artista", "Track wrong-deezer-profile"),
    ]:
        rows.append(
            HistorialRevisio.objects.create(
                canco_nom=nom,
                album_nom="Some Album",
                artista_nom="Portal Band",
                artista_deezer_id=999001,
                canco_deezer_id=11100 + len(rows),
                canco_isrc=f"X{len(rows):010d}",
                decisio="rebutjada",
                motiu=motiu,
            )
        )
    return rows


def test_cancons_pendents_includes_verificades(client_g, artista, cancons_pendents):
    """A verified Canco shows up under `verificades` (not `pendents`)."""
    from music.models import Album

    album = Album.objects.create(artista=artista, nom="Verified EP", slug="verified-ep")
    Canco.objects.create(
        artista=artista,
        album=album,
        nom="Verified Track",
        slug="portal-band-verified",
        verificada=True,
    )
    r = client_g.get(_url(artista.slug, "cancons-pendents/"))
    assert r.status_code == 200
    body = r.json()
    assert len(body["verificades"]) == 1
    assert body["verificades"][0]["nom"] == "Verified Track"
    assert body["n_verificades_total"] == 1
    # Must NOT leak into pendents.
    assert all(c["nom"] != "Verified Track" for c in body["pendents"])


def test_cancons_pendents_n_verificades_total_caps_at_50(client_g, artista):
    """`verificades` is capped at 50 recents but `n_verificades_total`
    reflects the full count so the SPA can say 'mostrant les 50 més
    recents'."""
    from music.models import Album

    album = Album.objects.create(artista=artista, nom="Big LP", slug="big-lp")
    for i in range(55):
        Canco.objects.create(
            artista=artista,
            album=album,
            nom=f"Track {i:02d}",
            slug=f"portal-band-verified-{i:02d}",
            verificada=True,
        )
    body = client_g.get(_url(artista.slug, "cancons-pendents/")).json()
    assert len(body["verificades"]) == 50
    assert body["n_verificades_total"] == 55


def test_cancons_pendents_includes_rebutjades(
    client_g, artista, rebutjades_fixture, cancons_pendents
):
    """The endpoint now returns three keys: legacy `results` (pendents,
    for back-compat) + `pendents` + `rebutjades`."""
    r = client_g.get(_url(artista.slug, "cancons-pendents/"))
    assert r.status_code == 200
    body = r.json()
    assert len(body["pendents"]) == 3
    assert len(body["results"]) == 3
    assert len(body["rebutjades"]) == 3
    motius = {row["motiu"] for row in body["rebutjades"]}
    assert motius == {"desvincular_canco", "desvincular_album", "desvincular_artista"}
    # Required keys for the SPA's row renderer.
    sample = body["rebutjades"][0]
    for k in (
        "canco_nom",
        "album_nom",
        "motiu",
        "data_rebuig",
        "canco_deezer_id",
        "isrc",
    ):
        assert k in sample


def test_cancons_pendents_no_deezer_ids_returns_empty_rebutjades(
    db, gestor, artista, rebutjades_fixture
):
    """If an artist somehow has zero Deezer IDs, the rebutjades query
    must return an empty list rather than matching all HistorialRevisio
    rows with NULL deezer ids (which would leak unrelated rejections)."""
    ArtistaDeezer.objects.filter(artista=artista).delete()
    c = APIClient()
    c.force_authenticate(user=gestor)
    r = c.get(_url(artista.slug, "cancons-pendents/"))
    assert r.status_code == 200
    assert r.json()["rebutjades"] == []


def test_ping_staff_with_rebutjades_kind(client_g, artista, rebutjades_fixture):
    """`kind=rebutjades` crea una SolicitudRevisio amb només
    rebutjades — el snapshot conté els motius originals."""
    from comptes.models import SolicitudRevisio

    r = client_g.post(
        _url(artista.slug, "cancons-pendents/ping-staff/"),
        {"kind": "rebutjades"},
        format="json",
    )
    assert r.status_code == 201
    body = r.json()
    assert body["n_pendents"] == 0
    assert body["n_rebutjades"] == 3
    s = SolicitudRevisio.objects.get(pk=body["sollicitud_pk"])
    assert s.pendents_ids == []
    assert len(s.rebutjades_snapshot) == 3
    motius = {row["motiu"] for row in s.rebutjades_snapshot}
    assert motius == {"desvincular_canco", "desvincular_album", "desvincular_artista"}


def test_ping_staff_mix_via_include_rebutjada_historial_pks(
    client_g, artista, cancons_pendents, rebutjades_fixture
):
    """El nou param canònic `include_rebutjada_historial_pks` combina
    pendents (default ALL unverified) amb una selecció de rebutjades."""
    from comptes.models import SolicitudRevisio

    reb_ids = [h.pk for h in rebutjades_fixture[:2]]
    r = client_g.post(
        _url(artista.slug, "cancons-pendents/ping-staff/"),
        {"include_rebutjada_historial_pks": reb_ids},
        format="json",
    )
    assert r.status_code == 201
    body = r.json()
    assert body["n_pendents"] == 3
    assert body["n_rebutjades"] == 2
    s = SolicitudRevisio.objects.get(pk=body["sollicitud_pk"])
    assert len(s.pendents_ids) == 3
    assert {r_["historial_pk"] for r_ in s.rebutjades_snapshot} == set(reb_ids)


def test_ping_staff_legacy_include_rebutjada_ids_still_works(
    client_g, artista, cancons_pendents, rebutjades_fixture
):
    """El nom legacy `include_rebutjada_ids` (que la SPA encara
    emet al rollout) ha de ser equivalent al canònic."""
    from comptes.models import SolicitudRevisio

    reb_ids = [h.pk for h in rebutjades_fixture[:1]]
    r = client_g.post(
        _url(artista.slug, "cancons-pendents/ping-staff/"),
        {"include_rebutjada_ids": reb_ids},
        format="json",
    )
    assert r.status_code == 201
    s = SolicitudRevisio.objects.get(pk=r.json()["sollicitud_pk"])
    assert s.n_rebutjades == 1


# ───────────────────────── D.1: dashboard surfaces qualitat ──────


def test_dashboard_attaches_qualitat_to_verified_row(client_g, artista):
    """Verified rows in `gestio_list` carry `qualitat: {score, n_alerts}`
    so the ArtistaCard pill renders without a per-row round-trip."""
    r = client_g.get("/api/v1/compte/dashboard/")
    assert r.status_code == 200
    body = r.json()
    rows = body["gestio_list"]
    assert rows, "expected one UA row for the gestor fixture"
    row = rows[0]
    assert row["verificat"] is True
    assert "qualitat" in row
    assert "score" in row["qualitat"] and 0 <= row["qualitat"]["score"] <= 100
    assert "n_alerts" in row["qualitat"]
    # The verified-spotlight key carries the same payload.
    assert body["artista_verificat"]["qualitat"]["score"] == row["qualitat"]["score"]


def test_dashboard_skips_qualitat_on_unverified_row(db, artista, other):
    """A non-verified UA shouldn't pay the qualitat compute cost
    (and there's no card to render the pill on)."""
    UserArtista.objects.create(
        usuari=other,
        artista=artista,
        sollicitud_text="x" * 25,
        verificat=False,
        estat=UserArtista.ESTAT_PENDENT,
    )
    c = APIClient()
    c.force_authenticate(user=other)
    r = c.get("/api/v1/compte/dashboard/")
    assert r.status_code == 200
    rows = r.json()["gestio_list"]
    assert len(rows) == 1
    assert rows[0]["verificat"] is False
    assert "qualitat" not in rows[0]


# ───────────────────────── Auth perimeter ────────────────────────


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "qualitat/"),
        ("get", "editar/"),
        ("patch", "editar/"),
        ("post", "deezer-ids/"),
        ("post", "lastfm-aliases/"),
        ("post", "localitats/"),
        ("get", "cancons-pendents/"),
        ("post", "cancons-pendents/ping-staff/"),
    ],
)
def test_non_manager_forbidden(other, artista, method, path):
    c = APIClient()
    c.force_authenticate(user=other)
    fn = getattr(c, method)
    r = (
        fn(_url(artista.slug, path), {}, format="json")
        if method != "get"
        else fn(_url(artista.slug, path))
    )
    assert r.status_code == 403
