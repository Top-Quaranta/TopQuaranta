"""Sonda «la cançó del dia» (2026-08-13): selector ladder, diversity,
reach-outlier evaluator and the publish flow (slot_key idempotence,
dormant gate, franja partition).
"""

from __future__ import annotations

import datetime
import io
import pathlib
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest
from django.core.management import call_command

from analytics.models import MetricaSocialPost
from music.models import Album, Artista, Canco
from ranking.models import ConfiguracioGlobal, SenyalDiari, TopSetmanal
from social import sonda
from social.models import InvitacioColaboracioIG, SocialPost, SondaStoryIG

AVUI = datetime.date(2026, 8, 18)  # dimarts (weekday 1) — dia de sonda


def _DT(y, m, d):
    return datetime.datetime(y, m, d, tzinfo=datetime.timezone.utc)


_DZ = "https://e-cdns-images.dzcdn.net/images/cover/x/1000x1000-000000-80-0-0.jpg"


def _artista(nom, *, ig=True, genere="", **kw):
    return Artista.objects.create(
        nom=nom,
        aprovat=True,
        instagram_url=f"https://instagram.com/{nom}/" if ig else "",
        genere=genere,
        **kw,
    )


def _canco(artista, nom, *, deezer=None, llancament=None, verificada=True):
    alb = Album.objects.create(
        artista=artista,
        nom=f"alb-{nom}",
        deezer_id=deezer or abs(hash(nom)) % 10**8,
        imatge_url=_DZ,
        data_llancament=llancament,
    )
    return Canco.objects.create(
        artista=artista, album=alb, nom=nom, verificada=verificada, activa=True
    )


# ── elegibilitat ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_elegibles_excludes_every_blocked_state():
    ok = _artista("verge")
    _canco(ok, "c-verge")

    no_ig = _artista("noig", ig=False)
    _canco(no_ig, "c-noig")

    pendent = _artista("pendent")
    _canco(pendent, "c-pendent")
    InvitacioColaboracioIG.objects.create(
        artista=pendent,
        ig_media_id="m1",
        username_snapshot="pendent",
        tipus_publicacio=SocialPost.TIPUS_TOP_PPCC,
        estat=InvitacioColaboracioIG.ESTAT_PENDENT,
        data_invitacio=_DT(2026, 8, 1),
    )

    acceptat = _artista("acceptat")
    _canco(acceptat, "c-acceptat")
    InvitacioColaboracioIG.objects.create(
        artista=acceptat,
        ig_media_id="m2",
        username_snapshot="acceptat",
        tipus_publicacio=SocialPost.TIPUS_TOP_PPCC,
        estat=InvitacioColaboracioIG.ESTAT_ACCEPTADA,
        data_invitacio=_DT(2026, 8, 1),
    )

    receptiu = _artista("receptiu")
    _canco(receptiu, "c-receptiu")
    SondaStoryIG.objects.create(
        artista=receptiu,
        data=AVUI - datetime.timedelta(days=400),
        franja="mati",
        reaccio_auto=True,
    )

    sondejat_fa_poc = _artista("recent")
    _canco(sondejat_fa_poc, "c-recent")
    SondaStoryIG.objects.create(
        artista=sondejat_fa_poc,
        data=AVUI - datetime.timedelta(days=100),
        franja="mati",
        reaccio_auto=False,
    )

    topat = _artista("topat")
    c_top = _canco(topat, "c-topat")
    TopSetmanal.objects.create(
        canco=c_top,
        territori="PPCC",
        setmana=datetime.date(2026, 6, 1),
        posicio=40,
        score_setmanal=1.0,
    )
    _canco(topat, "c-topat-fora")  # té material mai-top, però és topat

    noms = {c.artista.nom for c in sonda.elegibles(AVUI)}
    assert noms == {"verge"}


@pytest.mark.django_db
def test_ladder_tiers_and_order():
    # Property: the three ladder situations are all eligible and strictly
    # ordered by priority — never probed (verge) before re-probe after the
    # cooldown (resonda) before caducada re-entry (caducat) — and
    # `tria_artista` follows that ladder as candidates disappear. The
    # numeric encoding of the tiers is not pinned. The lower tiers get a
    # recent release so the later sort keys would favour THEM — the tier
    # must be what decides.
    verge = _artista("verge")
    _canco(verge, "c1")

    resonda = _artista("resonda")
    _canco(resonda, "c2", llancament=AVUI - datetime.timedelta(days=20))
    SondaStoryIG.objects.create(
        artista=resonda,
        data=AVUI - datetime.timedelta(days=400),
        franja="mati",
        reaccio_auto=False,
    )

    caducat = _artista("caducat")
    _canco(caducat, "c3", llancament=AVUI - datetime.timedelta(days=10))
    InvitacioColaboracioIG.objects.create(
        artista=caducat,
        ig_media_id="m3",
        username_snapshot="caducat",
        tipus_publicacio=SocialPost.TIPUS_TOP_PPCC,
        estat=InvitacioColaboracioIG.ESTAT_CADUCADA,
        data_invitacio=_DT(2026, 2, 15),
        data_resolucio=_DT(2026, 3, 1),
    )

    per_nom = {c.artista.nom: c.esglao for c in sonda.elegibles(AVUI)}
    assert set(per_nom) == {"verge", "resonda", "caducat"}
    assert per_nom["verge"] < per_nom["resonda"] < per_nom["caducat"]
    # The pick walks down the ladder.
    assert sonda.tria_artista(AVUI, "mati").artista.nom == "verge"
    verge.delete()
    assert sonda.tria_artista(AVUI, "mati").artista.nom == "resonda"
    resonda.delete()
    assert sonda.tria_artista(AVUI, "mati").artista.nom == "caducat"


@pytest.mark.django_db
def test_caducada_cooldown_90_dies():
    a = _artista("fresc")
    _canco(a, "c")
    InvitacioColaboracioIG.objects.create(
        artista=a,
        ig_media_id="m",
        username_snapshot="fresc",
        tipus_publicacio=SocialPost.TIPUS_TOP_PPCC,
        estat=InvitacioColaboracioIG.ESTAT_CADUCADA,
        data_invitacio=_DT(2026, 7, 15),
        data_resolucio=_DT(2026, 8, 1),  # fa 17 dies
    )
    assert sonda.elegibles(AVUI) == []


@pytest.mark.django_db
def test_topat_amb_caducada_entra_esglao_3():
    # Property: an artist with a topped song re-enters the funnel ONLY via
    # an old caducada, and then at the lowest-priority tier (below a
    # never-probed artist); without the caducada it is not eligible.
    a = _artista("topat-caducat")
    c_top = _canco(a, "hit")
    TopSetmanal.objects.create(
        canco=c_top,
        territori="PPCC",
        setmana=datetime.date(2026, 6, 1),
        posicio=1,
        score_setmanal=9.0,
    )
    _canco(a, "deep-cut")  # material mai-top
    inv = InvitacioColaboracioIG.objects.create(
        artista=a,
        ig_media_id="m",
        username_snapshot="tc",
        tipus_publicacio=SocialPost.TIPUS_TOP_PPCC,
        estat=InvitacioColaboracioIG.ESTAT_CADUCADA,
        data_invitacio=_DT(2026, 2, 15),
        data_resolucio=_DT(2026, 3, 1),
    )
    verge = _artista("verge")
    _canco(verge, "c-verge")
    per_nom = {c.artista.nom: c for c in sonda.elegibles(AVUI)}
    assert set(per_nom) == {"topat-caducat", "verge"}
    assert per_nom["topat-caducat"].esglao > per_nom["verge"].esglao
    assert per_nom["topat-caducat"].ultima_caducada == inv.data_resolucio.date()
    assert sonda.tria_artista(AVUI, "mati").artista.nom == "verge"
    # Take the caducada away → the topped artist is out of the funnel.
    inv.delete()
    assert {c.artista.nom for c in sonda.elegibles(AVUI)} == {"verge"}


@pytest.mark.django_db
def test_quota_no_cat_al_torn():
    # Property: on the reserved turn (one probe out of every
    # `sonda.QUOTA_NO_CAT`) a non-CAT artist beats a CAT artist that would
    # otherwise win; off the turn the CAT artist wins on the later keys
    # (here: a recent release). The turn recurs with that period.
    from music.models import Territori

    cat = Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Catalunya"})[0]
    val = Territori.objects.get_or_create(
        codi="VAL", defaults={"nom": "País Valencià"}
    )[0]
    a_cat = _artista("de-cat")
    a_cat.territoris.add(cat)
    _canco(a_cat, "c-cat", llancament=AVUI - datetime.timedelta(days=10))  # recent
    a_val = _artista("de-val")
    a_val.territoris.add(val)
    _canco(a_val, "c-val", llancament=AVUI - datetime.timedelta(days=700))
    # Probes are logged against a third, never-eligible artist (no IG) so
    # they only move the global counter.
    altre = _artista("altre", ig=False)

    def _log_sonda(i):
        SondaStoryIG.objects.create(
            artista=altre,
            data=AVUI - datetime.timedelta(days=800 + i),  # unique (data, franja)
            franja="mati",
            reaccio_auto=False,
        )

    for n in range(2 * sonda.QUOTA_NO_CAT + 1):
        assert SondaStoryIG.objects.count() == n
        winner = sonda.tria_artista(AVUI, "mati").artista.nom
        if n % sonda.QUOTA_NO_CAT == 0:
            assert winner == "de-val", n  # reserved turn: non-CAT wins
        else:
            assert winner == "de-cat", n  # off-turn: quota does not force
        _log_sonda(n)


# ── cançó ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_tria_canco_playcount_i_mai_top():
    # Artista TOPAT → només elegible per esglaó 3 (caducada antiga);
    # la cançó topada mai és candidata (el criteri és de cançó).
    a = _artista("cantant")
    fluixa = _canco(a, "fluixa", llancament=datetime.date(2026, 1, 1))
    forta = _canco(a, "forta", llancament=datetime.date(2025, 6, 1))
    topada = _canco(a, "topada")
    TopSetmanal.objects.create(
        canco=topada,
        territori="PPCC",
        setmana=datetime.date(2026, 6, 1),
        posicio=40,
        score_setmanal=1.0,
    )
    InvitacioColaboracioIG.objects.create(
        artista=a,
        ig_media_id="mm",
        username_snapshot="cantant",
        tipus_publicacio=SocialPost.TIPUS_TOP_PPCC,
        estat=InvitacioColaboracioIG.ESTAT_CADUCADA,
        data_invitacio=_DT(2026, 2, 15),
        data_resolucio=_DT(2026, 3, 1),
    )
    SenyalDiari.objects.create(
        canco=fluixa, data=AVUI - datetime.timedelta(days=1), lastfm_playcount=10
    )
    SenyalDiari.objects.create(
        canco=forta, data=AVUI - datetime.timedelta(days=1), lastfm_playcount=999
    )
    cand = sonda.tria_artista(AVUI, "mati")
    tri = sonda.tria_canco(cand, AVUI)
    assert tri.nom == "forta"  # més playcount; la topada exclosa


@pytest.mark.django_db
def test_tria_canco_mai_repeteix():
    a = _artista("repetit")
    c1 = _canco(a, "unica")
    SondaStoryIG.objects.create(
        artista=a,
        canco=c1,
        data=AVUI - datetime.timedelta(days=400),
        franja="mati",
        reaccio_auto=False,
    )
    cand = [c for c in sonda.elegibles(AVUI) if c.artista == a][0]
    assert sonda.tria_canco(cand, AVUI) is None  # l'única ja sondejada


# ── avaluador (reach-only) ───────────────────────────────────────────


def _sonda_avaluada(dies_enrere, reach):
    a = _artista(f"base{dies_enrere}")
    return SondaStoryIG.objects.create(
        artista=a,
        data=AVUI - datetime.timedelta(days=dies_enrere),
        franja="mati",
        reach=reach,
        reaccio_auto=False,
    )


@pytest.mark.django_db
def test_avaluar_flags_outlier():
    for i, r in enumerate((28, 30, 31, 29, 33, 30)):
        _sonda_avaluada(30 + i, r)
    a = _artista("estrella")
    post = SocialPost.objects.create(
        platform="instagram_story",
        tipus="canco_dia",
        setmana=datetime.date(2026, 8, 10),
        slot_key="2026-08-15-mati",
    )
    s = SondaStoryIG.objects.create(
        artista=a,
        data=AVUI - datetime.timedelta(days=3),
        franja="mati",
        socialpost=post,
    )
    MetricaSocialPost.objects.create(socialpost=post, data=AVUI, reach=120)
    n = sonda.avaluar_sondes_pendents(AVUI)
    s.refresh_from_db()
    assert n == 1 and s.reach == 120 and s.reaccio_auto is True


@pytest.mark.django_db
def test_avaluar_dins_de_base_no_flag():
    for i, r in enumerate((28, 30, 31, 29, 33, 30)):
        _sonda_avaluada(30 + i, r)
    a = _artista("normal")
    post = SocialPost.objects.create(
        platform="instagram_story",
        tipus="canco_dia",
        setmana=datetime.date(2026, 8, 10),
        slot_key="2026-08-15-vesprada",
    )
    s = SondaStoryIG.objects.create(
        artista=a,
        data=AVUI - datetime.timedelta(days=3),
        franja="vesprada",
        socialpost=post,
    )
    MetricaSocialPost.objects.create(socialpost=post, data=AVUI, reach=31)
    sonda.avaluar_sondes_pendents(AVUI)
    s.refresh_from_db()
    assert s.reaccio_auto is False


@pytest.mark.django_db
def test_avaluar_cold_start_mai_flag():
    a = _artista("pioner")
    post = SocialPost.objects.create(
        platform="instagram_story",
        tipus="canco_dia",
        setmana=datetime.date(2026, 8, 10),
        slot_key="2026-08-15-mati",
    )
    s = SondaStoryIG.objects.create(
        artista=a,
        data=AVUI - datetime.timedelta(days=3),
        franja="mati",
        socialpost=post,
    )
    MetricaSocialPost.objects.create(socialpost=post, data=AVUI, reach=500)
    sonda.avaluar_sondes_pendents(AVUI)
    s.refresh_from_db()
    assert s.reaccio_auto is False  # <MIN_BASELINE prèvies → mai flag


# ── publish flow ─────────────────────────────────────────────────────


def _run(franja="mati", data="2026-08-18", force=False):
    argv = {"data": data, "franja": franja}
    if force:
        argv["force"] = True
    out = io.StringIO()
    with (
        patch(
            "social.management.commands.publicar_social.renderer."
            "render_story_canco_dia",
            return_value=pathlib.Path("sonda_0.jpg"),
        ),
        patch(
            "social.management.commands.publicar_social._public_url_for",
            side_effect=lambda p: f"https://x/{p.name}",
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client."
            "upload_story",
            return_value="cid-1",
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client."
            "wait_until_finished",
            return_value=None,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client."
            "publish_container",
            return_value="mid-1",
        ),
        redirect_stdout(out),
    ):
        call_command("publicar_social", stdout=out, **argv)
    return out.getvalue()


@pytest.fixture
def sonda_activa(db):
    cfg = ConfiguracioGlobal.load()
    cfg.instagram_actiu = True
    cfg.save()
    a = _artista("elegida")
    _canco(a, "la-canco")
    return a


@pytest.mark.django_db
def test_sonda_publica_i_es_idempotent(sonda_activa):
    out = _run()
    assert "sonda publicada" in out
    post = SocialPost.objects.get(tipus="canco_dia")
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert post.slot_key == "2026-08-18-mati"
    s = SondaStoryIG.objects.get()
    assert s.artista == sonda_activa and s.story_media_id == "mid-1"
    # Re-run: idempotent, cap segona publicació.
    out2 = _run()
    assert "ja publicat" in out2
    assert SocialPost.objects.filter(tipus="canco_dia").count() == 1


@pytest.mark.django_db
def test_franges_del_mateix_dia_no_col·lisionen(sonda_activa):
    _artista_b = _artista("segona")
    _canco(_artista_b, "altra-canco")
    _run("mati")
    _run("vesprada")
    posts = SocialPost.objects.filter(tipus="canco_dia")
    assert posts.count() == 2
    assert {p.slot_key for p in posts} == {
        "2026-08-18-mati",
        "2026-08-18-vesprada",
    }
    # Dos artistes diferents (mai repetir).
    assert SondaStoryIG.objects.values("artista").distinct().count() == 2


@pytest.mark.django_db
def test_run_principal_no_toca_sondes(sonda_activa):
    """El run sense franja (dimarts = nous_albums) mai processa
    slots de sonda."""
    out = _run(franja="")
    assert not SocialPost.objects.filter(tipus="canco_dia").exists()


@pytest.mark.django_db
def test_sense_candidats_omes(db):
    cfg = ConfiguracioGlobal.load()
    cfg.instagram_actiu = True
    cfg.save()
    out = _run()
    assert "cap artista elegible" in out
    post = SocialPost.objects.get(tipus="canco_dia")
    assert post.status == SocialPost.STATUS_OMES
