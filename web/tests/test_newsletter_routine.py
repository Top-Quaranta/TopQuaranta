"""Guards for the newsletter cloud-routine endpoints (2026-06-07).

Token auth (valid passes / invalid 401), the not-ready brief guard, and
the draft upsert that can never mark approved/sent. VilaWeb RSS is mocked
so no network is hit.
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from comptes.models import NewsletterDraft
from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal

TOKEN = "secret-routine-token"
BRIEF_URL = "/api/v1/newsletter-routine/brief/"
DRAFT_URL = "/api/v1/newsletter-routine/esborrany/"


def _monday():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _seed_top():
    a = Artista.objects.create(nom="Art X", lastfm_nom="Art X", aprovat=True)
    al = Album.objects.create(
        artista=a, nom="Al X", data_llancament=datetime.date(2026, 1, 1)
    )
    c = Canco.objects.create(
        artista=a,
        album=al,
        nom="Tema X",
        verificada=True,
        activa=True,
        data_llancament=datetime.date(2026, 1, 1),
    )
    TopSetmanal.objects.create(
        canco=c, territori="PPCC", setmana=_monday(), posicio=1, score_setmanal=10.0
    )
    return c


@pytest.fixture
def client_with_token(settings):
    settings.NEWSLETTER_ROUTINE_TOKEN = TOKEN
    return APIClient()


def _auth(token=TOKEN):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


# ── token auth ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_valid_token_passes(client_with_token):
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.status_code == 200, r.content


@pytest.mark.django_db
def test_invalid_token_401(client_with_token):
    r = client_with_token.get(BRIEF_URL, **_auth("wrong"))
    assert r.status_code == 401


@pytest.mark.django_db
def test_missing_token_401(client_with_token):
    r = client_with_token.get(BRIEF_URL)
    assert r.status_code == 401


@pytest.mark.django_db
def test_blank_setting_denies_even_with_header(settings):
    settings.NEWSLETTER_ROUTINE_TOKEN = ""
    r = APIClient().get(BRIEF_URL, **{"HTTP_AUTHORIZATION": "Bearer "})
    assert r.status_code == 401
    r2 = APIClient().get(BRIEF_URL, **_auth("anything"))
    assert r2.status_code == 401


# ── brief ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_brief_not_ready_without_consolidated_top(client_with_token):
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.status_code == 200
    assert r.data["status"] == "not_ready"


@pytest.mark.django_db
def test_brief_ready_shape(client_with_token):
    _seed_top()
    with patch(
        "comptes.newsletter_brief._fetch_vilaweb",
        return_value=[{"titol": "Notícia", "font": "VilaWeb", "data": "x"}],
    ):
        r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.status_code == 200
    d = r.data
    assert d["status"] == "ready"
    assert d["context"]["edicio"] == "Global"
    assert d["context"]["antiguitat_top_setmanes"] >= 1
    assert len(d["top10"]) == 1
    e = d["top10"][0]
    assert "can_call_new" in e and "moviment" in e
    assert "primera_aparicio" in e and "historial" in e
    assert d["fets_grup_top5"][0]["data_llancament"] == "2026-01-01"
    # Low-confidence section is separate from facts.
    assert "lastfm_tags_top5" in d["baixa_confianca"]
    assert d["actualitat"][0]["font"] == "VilaWeb"


# ── brief top-40 additive expansion (2026-06-08) ─────────────────────


def _seed_topN(n, *, with_collab=False, prev=False):
    """Seed an N-row PPCC top for this week. Every artista gets a
    municipi-backed localitat (so `origen` is populated and the prefetch
    path is exercised); optionally a collaborator on row 3 and a previous
    week so the movement / debut detectors have a baseline."""
    from music.models import ArtistaLocalitat, Municipi, Territori

    terr, _ = Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Principat"})
    muni = Municipi.objects.create(nom="Vila", comarca="Comarca", territori=terr)
    monday = _monday()
    cancons = []
    for i in range(1, n + 1):
        a = Artista.objects.create(nom=f"Art {i}", lastfm_nom=f"Art {i}", aprovat=True)
        ArtistaLocalitat.objects.create(artista=a, municipi=muni)
        al = Album.objects.create(
            artista=a, nom=f"Al {i}", data_llancament=datetime.date(2026, 1, 1)
        )
        c = Canco.objects.create(
            artista=a,
            album=al,
            nom=f"Tema {i}",
            verificada=True,
            activa=True,
            data_llancament=datetime.date(2026, 1, 1),
        )
        if with_collab and i == 3:
            col = Artista.objects.create(nom="Col", lastfm_nom="Col", aprovat=True)
            ArtistaLocalitat.objects.create(artista=col, municipi=muni)
            c.artistes_col.add(col)
        TopSetmanal.objects.create(
            canco=c,
            territori="PPCC",
            setmana=monday,
            posicio=i,
            score_setmanal=float(100 - i),
        )
        if prev:
            TopSetmanal.objects.create(
                canco=c,
                territori="PPCC",
                setmana=monday - datetime.timedelta(days=7),
                posicio=((i % n) + 1),
                score_setmanal=float(100 - i),
            )
        cancons.append(c)
    return cancons


@pytest.mark.django_db
def test_brief_exposes_top40_with_intact_old_keys(client_with_token):
    """The dict gains `top40`/`fets_grup`/`fets_destacats` while every
    legacy key the routine token consumes stays present and unchanged."""
    _seed_topN(12, with_collab=True, prev=True)
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.status_code == 200
    d = r.data
    # Every legacy key still here.
    for key in (
        "status",
        "context",
        "top10",
        "fets_grup_top5",
        "fet_lider",
        "actualitat",
        "baixa_confianca",
        "notes",
    ):
        assert key in d, key
    assert "lastfm_tags_top5" in d["baixa_confianca"]
    # New additive keys.
    assert len(d["top40"]) == 12
    assert "fets_grup" in d and len(d["fets_grup"]) == 12
    assert "fets_destacats" in d and isinstance(d["fets_destacats"], list)


@pytest.mark.django_db
def test_brief_aliases_are_identical_slices(client_with_token):
    """top10 == top40[:10]; fets_grup_top5 == fets_grup[:5]; fet_lider is
    the first highlighted fact (same shape + content as before)."""
    _seed_topN(12, with_collab=True, prev=True)
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    d = r.data
    assert d["top10"] == d["top40"][:10]
    assert d["fets_grup_top5"] == d["fets_grup"][:5]
    # fet_lider keeps its exact shape.
    if d["fet_lider"] is not None:
        assert set(d["fet_lider"]) == {"code", "severity", "data", "freshness_blocked"}
        # ...and equals the first highlighted fact.
        assert d["fets_destacats"][0] == d["fet_lider"]


@pytest.mark.django_db
def test_brief_fets_destacats_distinct_subjects(client_with_token):
    """`fets_destacats` never repeats a song or artist subject and never
    exceeds the configured cap."""
    from comptes.newsletter_brief import FETS_DESTACATS_K

    _seed_topN(12, with_collab=True, prev=True)
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    fets = r.data["fets_destacats"]
    assert len(fets) <= FETS_DESTACATS_K
    seen_canco, seen_art = set(), set()
    for f in fets:
        cid = f["data"].get("canco_id")
        aid = f["data"].get("artista_id")
        assert cid is None or cid not in seen_canco
        assert aid is None or aid not in seen_art
        if cid is not None:
            seen_canco.add(cid)
        if aid is not None:
            seen_art.add(aid)


@pytest.mark.django_db
def test_brief_query_budget_bounded_no_n_plus_1(django_assert_max_num_queries):
    """Assembling the 40-row facts must NOT scale per-row: origen +
    collaborators are prefetched/batched. `detect_all` is stubbed out so
    the ceiling measures only the data-assembly cost (the N+1 risk)."""
    from comptes.newsletter_brief import build_brief

    _seed_topN(12, with_collab=True, prev=True)
    with (
        patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]),
        patch("social.narrative.detect_all", return_value=[]),
    ):
        # Assembly is constant in N (prefetch + batch); the +1/+2 from
        # ConfiguracioGlobal.load() (editorial_veu) is also constant. An
        # origen/collaborator N+1 across 12 rows would push it past 20, so
        # this 16 ceiling is the regression tripwire.
        with django_assert_max_num_queries(16):
            build_brief(_monday())


# ── old==new equivalence pins for the rewritten reads ────────────────


@pytest.mark.django_db
def test_collaborator_order_matches_legacy_method(client_with_token):
    """The batched collaborator lookup must reproduce the EXACT order of
    `Canco.artistes_col_ordered()` (through-table insertion id), NOT the
    alphabetical Artista.Meta.ordering. Collaborators are inserted in an
    order that is deliberately NOT alphabetical, so a regression to the
    naive M2M ordering would flip them and fail this pin."""
    from comptes.newsletter_brief import _collaborators_by_canco

    c = _seed_top()  # main artist "Art X" at posició 1
    z = Artista.objects.create(nom="Zeta", lastfm_nom="Zeta", aprovat=True)
    a = Artista.objects.create(nom="Alfa", lastfm_nom="Alfa", aprovat=True)
    c.artistes_col.add(z)  # inserted first
    c.artistes_col.add(a)  # inserted second
    expected = ["Zeta", "Alfa"]  # insertion order, NOT alphabetical
    # Sanity: the order under test is genuinely non-alphabetical.
    assert expected != sorted(expected)
    # 1) the batch helper equals the legacy model method, value-by-value.
    batched = [art.nom for art in _collaborators_by_canco([c])[c.id]]
    legacy = [art.nom for art in c.artistes_col_ordered()]
    assert batched == legacy == expected
    # 2) the brief surfaces that same order in both top entries and facts.
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.data["top40"][0]["artistes"] == ["Art X", "Zeta", "Alfa"]
    collabs = r.data["fets_grup"][0]["collaboradors"]
    assert [x["nom"] for x in collabs] == expected


# ── draft upsert ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_post_creates_draft_llm_pendent(client_with_token):
    _seed_top()
    r = client_with_token.post(
        DRAFT_URL,
        {"subject": "Subj", "narrative_html": "<p>n</p>"},
        format="json",
        **_auth(),
    )
    assert r.status_code == 201, r.content
    d = NewsletterDraft.objects.get(setmana=_monday())
    assert d.font == NewsletterDraft.FONT_LLM
    assert d.estat == NewsletterDraft.ESTAT_PENDENT
    assert d.subject == "Subj"


@pytest.mark.django_db
def test_post_llm_sends_admin_preview(client_with_token, mailoutbox):
    """A successful LLM upsert fires exactly one admin mail whose HTML body
    is the FULL preview (shared render) + the management block + the staff
    editor link, with deliverability headers. There is no separate full
    1-40 ranking section."""
    _seed_topN(12, prev=True)
    r = client_with_token.post(
        DRAFT_URL,
        {"subject": "Subj LLM", "narrative_html": "<p>n</p>"},
        format="json",
        **_auth(),
    )
    assert r.status_code == 201, r.content
    assert len(mailoutbox) == 1
    m = mailoutbox[0]
    assert "Subj LLM" in m.body
    gestio = f"/staff/social/esborrany?setmana={_monday().isoformat()}"
    assert gestio in m.body
    html = m.alternatives[0][0]
    # Full preview body: management block + staff link, highlighted top 10.
    assert "Còpia de gestió" in html
    assert gestio in html
    assert "Del 4 al 10" in html
    # No separate full 1-40 ranking section.
    assert "El Top 40 complet" not in html
    # Deliverability headers present.
    assert m.extra_headers.get("List-Unsubscribe")
    assert m.extra_headers.get("Auto-Submitted") == "auto-generated"
    # Default recipients: settings.ADMINS only (newsletter_desti_prova buit).
    from django.conf import settings as dj_settings

    assert m.to == list(dj_settings.ADMINS)


@pytest.mark.django_db
def test_post_llm_preview_adds_desti_prova_when_set(client_with_token, mailoutbox):
    """`ConfiguracioGlobal.newsletter_desti_prova` set → the routine's
    admin preview carries the extra render-testing recipient too."""
    from django.conf import settings as dj_settings

    from ranking.models import ConfiguracioGlobal

    cfg = ConfiguracioGlobal.load()
    cfg.newsletter_desti_prova = "prova.render@example.com"
    cfg.save()
    _seed_topN(12, prev=True)
    r = client_with_token.post(
        DRAFT_URL,
        {"subject": "Subj LLM", "narrative_html": "<p>n</p>"},
        format="json",
        **_auth(),
    )
    assert r.status_code == 201, r.content
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == list(dj_settings.ADMINS) + ["prova.render@example.com"]


@pytest.mark.django_db
def test_post_no_subject_does_not_send(client_with_token, mailoutbox):
    """A parada (missing subject, 400) creates no draft and sends no mail."""
    _seed_top()
    r = client_with_token.post(
        DRAFT_URL, {"narrative_html": "<p>x</p>"}, format="json", **_auth()
    )
    assert r.status_code == 400
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_post_terminal_draft_does_not_send(client_with_token, mailoutbox):
    """A 409 on a terminal draft sends no mail (no successful upsert)."""
    _seed_top()
    NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=_monday(),
        subject="s",
        estat=NewsletterDraft.ESTAT_ENVIAT,
    )
    r = client_with_token.post(DRAFT_URL, {"subject": "X"}, format="json", **_auth())
    assert r.status_code == 409
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_subscriber_copy_has_no_management_block(
    client_with_token, mailoutbox, django_user_model
):
    """The real send to subscribers must NEVER carry the admin management
    block, even though the admin preview does."""
    from comptes.models import PerfilUsuari
    from comptes.newsletter import send_top_newsletter
    from social import payload

    _seed_topN(12, prev=True)
    user = django_user_model.objects.create_user(
        username="sub1", email="sub1@x.cat", password="x"
    )
    PerfilUsuari.objects.filter(usuari=user).update(vol_newsletter=True)

    setmana = _monday()
    data = payload.build_top("PPCC", setmana)
    summary = send_top_newsletter(
        "top_ppcc",
        "PPCC",
        setmana,
        setmana + datetime.timedelta(days=5),
        data["entries"],
        subject_override="Subj",
        narrative_html_override="<p>n</p>",
    )
    assert summary == "sent=1 fail=0"
    assert len(mailoutbox) == 1
    html = mailoutbox[0].alternatives[0][0]
    assert "Del 4 al 10" in html  # same rich layout
    assert "Còpia de gestió" not in html  # but no management block
    assert "/staff/social/esborrany" not in html


@pytest.mark.django_db
def test_post_idempotent_replaces(client_with_token):
    _seed_top()
    client_with_token.post(DRAFT_URL, {"subject": "A"}, format="json", **_auth())
    r = client_with_token.post(DRAFT_URL, {"subject": "B"}, format="json", **_auth())
    assert r.status_code == 200
    assert NewsletterDraft.objects.filter(setmana=_monday()).count() == 1
    assert NewsletterDraft.objects.get(setmana=_monday()).subject == "B"


@pytest.mark.django_db
def test_post_rejects_non_pendent_estat(client_with_token):
    _seed_top()
    r = client_with_token.post(
        DRAFT_URL, {"subject": "X", "estat": "enviat"}, format="json", **_auth()
    )
    assert r.status_code == 400
    assert not NewsletterDraft.objects.exists()


@pytest.mark.django_db
def test_post_does_not_clobber_human_edit(client_with_token):
    """A pendent draft the staff has edited (`editat=True`) is protected:
    the routine gets 409 and the edit survives."""
    _seed_top()
    NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=_monday(),
        subject="Editat per staff",
        narrative_html="<p>humà</p>",
        estat=NewsletterDraft.ESTAT_PENDENT,
        editat=True,
    )
    r = client_with_token.post(
        DRAFT_URL, {"subject": "ROUTINE"}, format="json", **_auth()
    )
    assert r.status_code == 409
    d = NewsletterDraft.objects.get(setmana=_monday())
    assert d.subject == "Editat per staff"
    assert d.editat is True


# ── engine fallback does not overwrite a routine draft ───────────────


@pytest.mark.django_db
@patch("comptes.management.commands.generar_esborrany_newsletter.mail_admins")
@patch("comptes.management.commands.generar_esborrany_newsletter.build_draft_text")
def test_engine_fallback_does_not_overwrite_routine_draft(mock_build, mock_mail):
    from io import StringIO

    from django.core.management import call_command

    _seed_top()
    # Routine already left an LLM draft for the week.
    NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=_monday(),
        subject="LLM subject",
        narrative_html="<p>llm</p>",
        font=NewsletterDraft.FONT_LLM,
    )
    mock_build.return_value = ("ENGINE subject", "<p>engine</p>")
    call_command("generar_esborrany_newsletter", stdout=StringIO())
    d = NewsletterDraft.objects.get(setmana=_monday())
    assert d.font == NewsletterDraft.FONT_LLM  # untouched
    assert d.subject == "LLM subject"
    assert not mock_build.called  # never even composed


# ── brief enrichment: actualitat (6-8) + language-commitment flag ────


@pytest.mark.django_db
def test_brief_actualitat_carries_multiple_headlines(client_with_token):
    _seed_top()
    many = [
        {"titol": f"Titular {i}", "font": "VilaWeb", "data": f"d{i}"} for i in range(8)
    ]
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=many):
        r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.status_code == 200
    assert len(r.data["actualitat"]) == 8
    assert r.data["actualitat"][0]["font"] == "VilaWeb"


@pytest.mark.django_db
def test_brief_actualitat_best_effort_on_feed_failure(client_with_token, settings):
    """If the feed fetch fails, the brief still builds with empty
    actualitat (best-effort)."""
    _seed_top()
    settings.VILAWEB_RSS_URL = "http://127.0.0.1:9/does-not-exist"
    # Real _fetch_vilaweb (not mocked) must swallow the connection error.
    r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.status_code == 200
    assert r.data["status"] == "ready"
    assert r.data["actualitat"] == []


@pytest.mark.django_db
def test_brief_llengua_flag_present_and_false_without_rejects(client_with_token):
    _seed_top()
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    fet = r.data["fets_grup_top5"][0]
    assert fet["compromis_llengua"]["te_obra_no_catala"] is False
    assert fet["compromis_llengua"]["n_cancons_desvinculades"] == 0
    assert "compromis_llengua" in r.data["notes"]


@pytest.mark.django_db
def test_brief_llengua_flag_true_with_desvincular_canco(client_with_token):
    from music.models import HistorialRevisio

    c = _seed_top()
    nom = c.artista.nom
    # Two non-Catalan song rejections recorded against this artist.
    for i in range(2):
        HistorialRevisio.objects.create(
            artista_nom=nom,
            decisio="rebutjada",
            motiu="desvincular_canco",
            canco_nom=f"Other-lang {i}",
        )
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    fet = next(f for f in r.data["fets_grup_top5"] if f["artista"] == nom)
    assert fet["compromis_llengua"]["te_obra_no_catala"] is True
    assert fet["compromis_llengua"]["n_cancons_desvinculades"] == 2


@pytest.mark.django_db
def test_brief_exposes_editorial_veu_from_singleton():
    """The brief carries `editorial_veu`, reflecting ConfiguracioGlobal."""
    from comptes.newsletter_brief import build_brief
    from ranking.models import ConfiguracioGlobal

    _seed_top()

    # Default singleton → blank string (the routine falls back to its own).
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        brief = build_brief(_monday())
    assert brief["status"] == "ready"
    assert brief["editorial_veu"] == ""

    # A staff-set voice is surfaced verbatim.
    cfg = ConfiguracioGlobal.load()
    cfg.editorial_veu = "Veu càlida, propera, mai cursi."
    cfg.save()
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        brief2 = build_brief(_monday())
    assert brief2["editorial_veu"] == "Veu càlida, propera, mai cursi."
