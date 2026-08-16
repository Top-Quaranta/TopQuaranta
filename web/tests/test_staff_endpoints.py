"""Smoke tests for the post-Sprint-C staff endpoints.

These don't replace endpoint-by-endpoint coverage — they're a guard
against the kind of breakage that hits when the package is split or
re-organised. We hit a representative endpoint from each major module
(estat, ranking_list, cancons_list) plus the `IsStaff` gate.

`IsStaff` requires `is_staff` AND `user.is_verified()` (django-otp).
We use `force_authenticate` and short-circuit `is_verified` by
deleting the attr — DRF then treats the user as exempt (the gate
returns True when `is_verified` is None to support test suites that
don't wire OTP middleware).
"""

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="sprint_c_tester",
        email="sc@example.com",
        password="x",
        is_staff=True,
    )
    # Defeat the django-otp gate. The IsStaff permission falls through
    # to True when the user has no `is_verified` attribute (no OTP
    # middleware in tests).
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


def test_staff_endpoints_require_auth(anon_client):
    """Anonymous requests must be rejected. Bound to the sprint-C
    refactor: if the IsStaff import wiring breaks, this is the first
    test to fall over."""
    for path in (
        "/api/v1/staff/dashboard/",
        "/api/v1/staff/estat/",
        "/api/v1/staff/ranking/",
        "/api/v1/staff/cancons/",
        "/api/v1/staff/artistes/",
    ):
        r = anon_client.get(path)
        assert r.status_code in (401, 403), (path, r.status_code)


def test_staff_estat_returns_full_payload(staff_client):
    """Estat is the dashboard's data source. It composes counts from
    every module — if any helper is mis-imported across the package
    boundary the call 500s. We only assert the top-level shape."""
    r = staff_client.get("/api/v1/staff/estat/")
    assert r.status_code == 200, r.content
    data = r.json()
    for key in (
        "bd",
        "flux",
        "whisper",
        "musicbrainz",
        "homonimia",
        "ranking",
        "senyal",
        "comunitat",
        "ml",
        "crons",
    ):
        assert key in data, f"Missing top-level key: {key}"
    assert "casos_sospitosos" in data["homonimia"]
    assert "casos" in data["homonimia"]
    # Sub-tier accuracy block (2026-04-30).
    assert "subtiers" in data["ml"]
    sub = data["ml"]["subtiers"]
    rows = sub["rows"]
    # 12 sub-tiers (4 per class), ordered high-to-low confidence.
    assert len(rows) == 12
    expected_order = [
        "A++",
        "A+",
        "A-",
        "A--",
        "B++",
        "B+",
        "B-",
        "B--",
        "C++",
        "C+",
        "C-",
        "C--",
    ]
    assert [r["label"] for r in rows] == expected_order
    for r in rows:
        for k in (
            "label",
            "tier",
            "conf_lo",
            "conf_hi",
            "n",
            "verif",
            "rej",
            "approve_accuracy",
            "reject_accuracy",
            "status",
        ):
            assert k in r
    # No auto-decision is currently graduated — the original 100%
    # claim was a target-leakage artifact (live Canco fields).
    assert sub["auto_approved"] == []
    assert sub["auto_rejected"] == []


def test_staff_top_list_responds(staff_client):
    """Ranking list. Empty DB → empty entries; 200 either way."""
    r = staff_client.get("/api/v1/staff/ranking/?territori=CAT")
    assert r.status_code == 200, r.content
    data = r.json()
    assert "entries" in data
    assert data["territori"] == "CAT"


@pytest.fixture
def top_with_softcap(db):
    """Two CAT TopProvisional rows: one the soft-cap compressed (the
    persisted score implies plays_eff < raw), one it left untouched.

    Factors are all 1.0 so `_derive_plays_eff` recovers plays_eff =
    score_setmanal exactly — making the expected effective value explicit
    in the test without coupling to the live knee.
    """
    from datetime import date

    from music.models import Album, Artista, Canco, Territori
    from ranking.models import TopProvisional

    Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Catalunya"})
    artista = Artista.objects.create(nom="Cap Outlier", lastfm_nom="Cap Outlier")
    album = Album.objects.create(artista=artista, nom="Album")
    capped = Canco.objects.create(
        artista=artista,
        album=album,
        nom="Outlier",
        slug="outlier-track",
        data_llancament=date(2026, 1, 1),
        verificada=True,
    )
    TopProvisional.objects.create(
        canco=capped,
        territori="CAT",
        posicio=1,
        escoltes_setmanals=22167,
        score_setmanal=8116.0,
        age_factor=1.0,
        past_top_factor=1.0,
        monopoli_factor=1.0,
    )
    plain = Canco.objects.create(
        artista=artista,
        album=album,
        nom="Plain",
        slug="plain-track",
        data_llancament=date(2026, 1, 1),
        verificada=True,
    )
    TopProvisional.objects.create(
        canco=plain,
        territori="CAT",
        posicio=2,
        escoltes_setmanals=900,
        score_setmanal=900.0,
        age_factor=1.0,
        past_top_factor=1.0,
        monopoli_factor=1.0,
    )
    return {"capped": capped, "plain": plain}


def test_top_list_escoltes_efectives_reconciles_with_breakdown(
    staff_client, anon_client, top_with_softcap
):
    """NON-REGRESSION: the staff list `escoltes_efectives` must equal, to
    the unit, the `weekly_plays_eff` the per-cançó breakdown panel shows
    for the same row — both go through the SAME `_derive_plays_eff`."""
    capped = top_with_softcap["capped"]

    r = staff_client.get("/api/v1/staff/ranking/?territori=CAT")
    assert r.status_code == 200, r.content
    list_entry = {e["canco_pk"]: e for e in r.json()["entries"]}[capped.pk]
    assert list_entry["soft_cap_aplicat"] is True
    assert list_entry["escoltes_setmanals"] == 22167
    assert list_entry["escoltes_efectives"] == 8116

    # Same source the TopBreakdownPanel reads (public, slug-based).
    rb = anon_client.get(f"/api/v1/cancons/{capped.slug}/top-breakdown/")
    assert rb.status_code == 200, rb.content
    cat = next(e for e in rb.json()["entries"] if e["territori"] == "CAT")
    assert cat["weekly_plays_eff"] == list_entry["escoltes_efectives"]
    assert cat["soft_cap_aplicat"] == list_entry["soft_cap_aplicat"]


def test_top_list_uncompressed_row_eff_equals_raw(staff_client, top_with_softcap):
    """When the soft-cap doesn't compress a row, effective == raw."""
    plain = top_with_softcap["plain"]
    r = staff_client.get("/api/v1/staff/ranking/?territori=CAT")
    e = {x["canco_pk"]: x for x in r.json()["entries"]}[plain.pk]
    assert e["soft_cap_aplicat"] is False
    assert e["escoltes_efectives"] == e["escoltes_setmanals"] == 900


def test_top_list_is_read_only(staff_client, top_with_softcap):
    """The list endpoint must not mutate TopProvisional: no score drift,
    no rows written or deleted."""
    from ranking.models import TopProvisional

    before = dict(TopProvisional.objects.values_list("pk", "score_setmanal"))
    staff_client.get("/api/v1/staff/ranking/?territori=CAT")
    after = dict(TopProvisional.objects.values_list("pk", "score_setmanal"))
    assert after == before
    assert TopProvisional.objects.count() == len(before)


def test_staff_cancons_list_responds(staff_client):
    """Cançons list with default filters. Empty DB → empty results."""
    r = staff_client.get("/api/v1/staff/cancons/")
    assert r.status_code == 200, r.content
    data = r.json()
    assert "results" in data
    assert "total" in data


def test_staff_artistes_list_responds(staff_client):
    """Artistes list — exercises the cross-module import chain
    (artistes → pendents._artista_card → estat._homonym_suspects_qs)."""
    r = staff_client.get("/api/v1/staff/artistes/")
    assert r.status_code == 200, r.content
    data = r.json()
    assert "results" in data


def test_staff_artistes_list_n_top_opt_in(staff_client, db):
    """Fase 2 (2026-05-18): the `n_top` annotation is gated by
    `?include_n_top=1`. By default the field stays None; opting in
    exposes the integer + supports `?sort=-n_top`."""
    import datetime

    from music.models import Album, Artista, Canco
    from ranking.models import TopSetmanal

    a_low = Artista.objects.create(nom="LowTop", slug="lowtop", aprovat=True)
    a_high = Artista.objects.create(nom="HighTop", slug="hightop", aprovat=True)
    al = Album.objects.create(nom="A", slug="a", artista=a_high, descartat=False)
    c1 = Canco.objects.create(
        nom="C1",
        slug="c1",
        artista=a_high,
        album=al,
        verificada=True,
        activa=True,
    )
    c2 = Canco.objects.create(
        nom="C2",
        slug="c2",
        artista=a_high,
        album=al,
        verificada=True,
        activa=True,
    )
    monday = datetime.date(2026, 5, 11)
    for i, canco in enumerate((c1, c2), start=1):
        TopSetmanal.objects.create(
            canco=canco,
            territori="CAT",
            setmana=monday,
            posicio=i,
            score_setmanal=100.0,
        )

    # Default: no n_top exposed.
    r = staff_client.get("/api/v1/staff/artistes/")
    assert r.status_code == 200, r.content
    rows = r.json()["results"]
    for row in rows:
        assert row.get("n_top") is None, row

    # Opt in: n_top exposed.
    r = staff_client.get("/api/v1/staff/artistes/?include_n_top=1&sort=-n_top")
    assert r.status_code == 200, r.content
    rows = r.json()["results"]
    by_name = {row["nom"]: row for row in rows}
    assert by_name["HighTop"]["n_top"] == 2
    assert by_name["LowTop"]["n_top"] == 0
    # Sort: HighTop (n_top=2) must come before LowTop (n_top=0).
    high_idx = next(i for i, row in enumerate(rows) if row["nom"] == "HighTop")
    low_idx = next(i for i, row in enumerate(rows) if row["nom"] == "LowTop")
    assert high_idx < low_idx, [row["nom"] for row in rows]


def test_staff_artistes_list_instagram_no_filter(staff_client, db):
    """The `instagram=no` filter (Fase 2 prerequisite) only returns
    rows with empty `instagram_url`. Smoke test that the filter wires
    together with `include_n_top=1` for the new workflow page."""
    from music.models import Artista

    Artista.objects.create(
        nom="WithIG",
        slug="with-ig",
        aprovat=True,
        instagram_url="https://www.instagram.com/foo/",
    )
    Artista.objects.create(nom="WithoutIG", slug="without-ig", aprovat=True)

    r = staff_client.get(
        "/api/v1/staff/artistes/?aprovat=1&instagram=no&include_n_top=1"
    )
    assert r.status_code == 200, r.content
    noms = {row["nom"] for row in r.json()["results"]}
    assert "WithoutIG" in noms
    assert "WithIG" not in noms


def test_legacy_staff_views_shim_still_exposes_names():
    """Anything that did `from web.api import staff_views` must keep
    finding the old names. Guards against a future cleanup that
    removes the shim before everyone has migrated."""
    from web.api import staff_views

    for attr in ("dashboard", "estat", "top_list", "IsStaff"):
        assert hasattr(staff_views, attr), attr


# ── social_republicar (Lot C — re-publicar amb correcció) ───────────


@pytest.fixture
def published_post(db):
    """A SocialPost in PUBLICAT state on Mastodon (the cheapest
    platform to mock — no Meta Graph dance)."""
    import datetime

    from social.models import SocialPost

    return SocialPost.objects.create(
        platform=SocialPost.PLATFORM_MASTODON,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="PPCC",
        setmana=datetime.date(2026, 4, 27),  # Monday
        status=SocialPost.STATUS_PUBLICAT,
        instagram_media_id="https://mastodon.social/@tq/123456789",
        scheduled_at="2026-04-25T09:40:00Z",
        published_at="2026-04-25T09:40:00Z",
    )


def test_republicar_requires_pk(staff_client):
    r = staff_client.post("/api/v1/staff/social/republicar/", {}, format="json")
    assert r.status_code == 400
    assert "pk required" in r.data.get("error", "")


def test_republicar_404_when_post_missing(staff_client):
    r = staff_client.post(
        "/api/v1/staff/social/republicar/", {"pk": 999999}, format="json"
    )
    assert r.status_code == 404


def test_republicar_400_when_post_not_published(staff_client, db):
    """A post still PENDENT can't be re-published — there's nothing
    remote to delete first."""
    import datetime

    from social.models import SocialPost

    post = SocialPost.objects.create(
        platform=SocialPost.PLATFORM_MASTODON,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="PPCC",
        setmana=datetime.date(2026, 4, 27),
        status=SocialPost.STATUS_PENDENT,
        instagram_media_id="",
        scheduled_at="2026-04-25T09:40:00Z",
    )
    r = staff_client.post(
        "/api/v1/staff/social/republicar/", {"pk": post.pk}, format="json"
    )
    assert r.status_code == 400
    assert "no està publicat" in r.data.get("error", "")


def test_republicar_calls_delete_then_publish(
    staff_client, published_post, monkeypatch
):
    """The endpoint must invoke delete first (resetting local state),
    then call_command for re-publish. Both pieces stubbed; we assert
    the order + payload."""
    calls: list[str] = []

    def fake_delete(post):
        calls.append(f"delete:{post.pk}")
        post.status = post.STATUS_PENDENT
        post.instagram_media_id = ""
        post.metadata = {}
        post.published_at = None
        post.save()
        return True, "DRY-RUN: deleted"

    def fake_call_command(*args, **kwargs):
        calls.append("publish:" + " ".join(args))

    monkeypatch.setattr(
        "web.api.staff.social.posts._delete_remote_and_reset", fake_delete
    )
    monkeypatch.setattr("web.api.staff.social.posts.call_command", fake_call_command)

    r = staff_client.post(
        "/api/v1/staff/social/republicar/",
        {"pk": published_post.pk},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["ok"] is True
    # Order matters — delete BEFORE publish.
    assert calls[0] == f"delete:{published_post.pk}"
    assert calls[1].startswith("publish:publicar_canal")
    assert "--channel mastodon" in calls[1]
    assert "--force" in calls[1]


def test_republicar_502_when_delete_fails(staff_client, published_post, monkeypatch):
    """If the remote delete fails the publish step must NOT run —
    otherwise we'd duplicate the broken post."""
    publish_called = False

    def fake_delete(post):
        return False, "remote API gave 500"

    def fake_call_command(*args, **kwargs):
        nonlocal publish_called
        publish_called = True

    monkeypatch.setattr(
        "web.api.staff.social.posts._delete_remote_and_reset", fake_delete
    )
    monkeypatch.setattr("web.api.staff.social.posts.call_command", fake_call_command)

    r = staff_client.post(
        "/api/v1/staff/social/republicar/",
        {"pk": published_post.pk},
        format="json",
    )
    assert r.status_code == 502
    assert r.data["ok"] is False
    assert r.data["step"] == "delete"
    assert publish_called is False


# ── social_delay (Lot B — programació flexible) ─────────────────────


def test_social_delay_sets_field(staff_client, db):
    from ranking.models import ConfiguracioGlobal

    cfg = ConfiguracioGlobal.load()
    assert cfg.delay_mastodon_min == 0  # default
    r = staff_client.post(
        "/api/v1/staff/social/delay/",
        {"channel": "mastodon", "min": 25},
        format="json",
    )
    assert r.status_code == 200
    cfg.refresh_from_db()
    assert cfg.delay_mastodon_min == 25


def test_social_delay_rejects_unknown_channel(staff_client, db):
    r = staff_client.post(
        "/api/v1/staff/social/delay/",
        {"channel": "tiktok", "min": 10},
        format="json",
    )
    assert r.status_code == 400
    assert "unknown channel" in r.data["error"]


def test_social_delay_rejects_out_of_range(staff_client, db):
    for bad in (-5, 200, "abc"):
        r = staff_client.post(
            "/api/v1/staff/social/delay/",
            {"channel": "instagram", "min": bad},
            format="json",
        )
        assert r.status_code == 400, (bad, r.status_code)


def test_social_delay_caps_in_command(db, monkeypatch):
    """The publicar_canal command must respect ConfiguracioGlobal's
    delay value at start. Verifies the integration: setting a delay
    in the DB → command sleeps that many minutes before doing work.
    Uses --dry-run path so the actual sleep is skipped (the gate
    `not opts['dry_run']` short-circuits)."""
    from io import StringIO

    from django.core.management import call_command

    from ranking.models import ConfiguracioGlobal

    cfg = ConfiguracioGlobal.load()
    cfg.mastodon_actiu = True
    cfg.delay_mastodon_min = 30
    cfg.save()

    sleep_calls = []
    import time

    monkeypatch.setattr(time, "sleep", lambda s: sleep_calls.append(s))

    out = StringIO()
    # --dry-run: the delay branch is gated on `not dry_run`.
    call_command("publicar_canal", "--channel", "mastodon", "--dry-run", stdout=out)
    assert sleep_calls == []

    # …and the half the docstring is actually about, which nothing
    # checked: a real run DOES sleep. Deleting the whole delay block
    # left this test green, because it only ever exercised the path
    # where the block is switched off (audit 2026-08-15). There are no
    # slots to publish here, and that is fine — the sleep happens before
    # the slots are read.
    call_command("publicar_canal", "--channel", "mastodon", stdout=StringIO())
    assert sleep_calls == [30 * 60], sleep_calls

    # The 180-minute cap: a fat-fingered config must not park a worker
    # for the rest of the day.
    sleep_calls.clear()
    cfg.delay_mastodon_min = 999
    cfg.save()
    call_command("publicar_canal", "--channel", "mastodon", stdout=StringIO())
    assert sleep_calls == [180 * 60], sleep_calls

    # `--force` is the operator saying "now": it must override the delay.
    sleep_calls.clear()
    call_command(
        "publicar_canal", "--channel", "mastodon", "--force", stdout=StringIO()
    )
    assert sleep_calls == []
