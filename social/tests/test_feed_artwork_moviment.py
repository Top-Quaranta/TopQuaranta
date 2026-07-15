"""Feed artwork covers + the moviment tipus (2026-07).

Covers: duotone invariants; the no-regression pins (with the flags off
the covers never touch the duotone code and are byte-identical to the
explicit no-op params); the moviment selection rule; and the moviment
gate (flag off → no SocialPost row at all).
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from django.core.management import call_command
from PIL import Image

from social import duotone, feed_redesign, payload, top_redesign
from social.models import SocialPost

SM = datetime.date(2026, 6, 29)
THURSDAY = "2026-07-02"  # weekday() == 3
W, H = 1080, 1350


def _dummy_cover(color=(160, 110, 80)) -> Image.Image:
    return Image.new("RGB", (500, 500), color)


# ── duotone invariants ───────────────────────────────────────────────


def test_duotone_veil_stops_and_size():
    out = duotone.duotone_photo(_dummy_cover(), "rgb(250, 204, 21)", "#427c42", (W, H))
    assert out.size == (W, H) and out.mode == "RGBA"
    veil = duotone._veil((W, H))
    assert abs(veil.getpixel((W // 2, 0))[3] - round(0.66 * 255)) <= 1
    assert abs(veil.getpixel((W // 2, int(H * 0.43)))[3] - round(0.16 * 255)) <= 1
    assert abs(veil.getpixel((W // 2, H - 1))[3] - round(0.72 * 255)) <= 1


def test_duotone_mosaic_needs_two():
    with pytest.raises(ValueError):
        duotone.duotone_mosaic([_dummy_cover()], "rgb(250,204,21)", "#3a5a34", (W, H))


def test_duotone_mosaic_grid_shape():
    assert duotone._grid_shape(4) == (2, 2, 4)
    assert duotone._grid_shape(5) == (2, 2, 4)
    assert duotone._grid_shape(6) == (2, 3, 6)
    assert duotone._grid_shape(9) == (2, 3, 6)


# ── no-regression: flags off → untouched ─────────────────────────────


def test_top_cover_default_never_calls_duotone():
    """The default (flag-off) cover must not invoke the artwork code and
    must be byte-identical to the explicit no-op params."""
    with patch("social.duotone.duotone_photo", side_effect=AssertionError("called")):
        img = top_redesign.build_top_cover(SM, "ppcc")
    assert img.size == (W, H)
    assert (
        top_redesign.build_top_cover(SM, "ppcc").tobytes()
        == top_redesign.build_top_cover(SM, "ppcc", artwork=None, credit=None).tobytes()
    )


def test_novetats_cover_default_never_calls_duotone():
    with patch("social.duotone.duotone_mosaic", side_effect=AssertionError("called")):
        img = feed_redesign.build_cover("nous_albums", SM)
    assert img.size == (W, H)
    assert (
        feed_redesign.build_cover("nous_albums", SM).tobytes()
        == feed_redesign.build_cover("nous_albums", SM, covers=None).tobytes()
    )


# ── artwork path renders + credit truncation ─────────────────────────


def test_top_cover_artwork_differs_and_renders():
    default = top_redesign.build_top_cover(SM, "ppcc").tobytes()
    art = top_redesign.build_top_cover(
        SM, "ppcc", artwork=_dummy_cover(), credit=("Nº1", "Rosalía", "Divinize")
    )
    assert art.size == (W, H)
    assert art.tobytes() != default


def test_credit_megacollab_truncates_without_error():
    long_artist = ", ".join(f"Artista {i}" for i in range(40))
    img = top_redesign.build_top_cover(
        SM,
        "VAL",
        artwork=_dummy_cover(),
        credit=("Nº1", long_artist, "La Gent de la Mediterrània"),
    )
    assert img.size == (W, H)


def test_moviment_cover_renders_both_kinds():
    puja = {
        "kind": "pujada",
        "pos": 10,
        "pos_ant": 38,
        "delta": 28,
        "artist": "Maria Jaume",
        "title": "Es Teus Besos",
        "phrase": "del 38 al 10",
        "reentrada": False,
    }
    entr = {
        "kind": "entrada",
        "pos": 2,
        "pos_ant": None,
        "delta": None,
        "artist": "The Tyets",
        "title": "Era Això!",
        "phrase": "directa al 2",
        "reentrada": False,
    }
    for sel in (puja, entr):
        img = top_redesign.build_moviment_cover(SM, sel, artwork=_dummy_cover())
        assert img.size == (W, H)
    # renders even without artwork (plain global field fallback)
    assert top_redesign.build_moviment_cover(SM, puja, artwork=None).size == (W, H)


# ── moviment selection ───────────────────────────────────────────────


def _entry(pos, pos_ant, *, re=False, nom="C", artist="A", dz=1):
    return {
        "posicio": pos,
        "posicio_anterior": pos_ant,
        "reentrada": re,
        "canco_nom": nom,
        "artistes_noms": [artist],
        "artista_nom": artist,
        "cover_url": None,
        "album_deezer_id": dz,
    }


def test_moviment_entry_top10_wins_over_rise():
    entries = [
        _entry(1, 1),
        _entry(2, None, nom="Era Això!", artist="The Tyets"),
        _entry(10, 38, nom="Es Teus Besos", artist="Maria Jaume"),
    ]
    with patch("social.payload.build_top", return_value={"entries": entries}):
        sel = payload.build_moviment(SM, 5)
    assert sel["kind"] == "entrada"
    assert sel["pos"] == 2 and sel["title"] == "Era Això!"
    assert sel["phrase"] == "directa al 2"


def test_moviment_rise_when_no_top10_entry():
    entries = [
        _entry(1, 1),
        _entry(17, 31, nom="Sant Domingo Forever", artist="Maria Jaume"),
        _entry(19, None, nom="new outside top10"),  # new but pos > 10
    ]
    with patch("social.payload.build_top", return_value={"entries": entries}):
        sel = payload.build_moviment(SM, 5)
    assert sel["kind"] == "pujada" and sel["delta"] == 14
    assert sel["phrase"] == "del 31 al 17"


def test_moviment_rise_below_min_omits():
    entries = [_entry(1, 1), _entry(10, 12)]  # rise of 2 < 5
    with patch("social.payload.build_top", return_value={"entries": entries}):
        assert payload.build_moviment(SM, 5) is None


def test_moviment_no_data_returns_none():
    with patch("social.payload.build_top", return_value=None):
        assert payload.build_moviment(SM, 5) is None


# ── moviment gate at the command ─────────────────────────────────────


@pytest.fixture
def cfg(db):
    from ranking.models import ConfiguracioGlobal

    c = ConfiguracioGlobal.load()
    c.distribucio_activa = True
    c.instagram_actiu = True
    c.save()
    return c


def test_moviment_flag_off_creates_no_row(cfg):
    assert not cfg.moviment_actiu  # default
    call_command(
        "publicar_social",
        "--data",
        THURSDAY,
        "--tipus",
        "moviment",
        "--platform",
        "instagram_feed",
    )
    assert not SocialPost.objects.filter(tipus=SocialPost.TIPUS_MOVIMENT).exists()


def test_moviment_flag_on_no_content_omits(cfg):
    cfg.moviment_actiu = True
    cfg.save()
    with patch("social.payload.build_moviment", return_value=None):
        call_command(
            "publicar_social",
            "--data",
            THURSDAY,
            "--tipus",
            "moviment",
            "--platform",
            "instagram_feed",
        )
    post = SocialPost.objects.get(tipus=SocialPost.TIPUS_MOVIMENT)
    assert post.status == SocialPost.STATUS_OMES


# ── moviment tags + collaborator invitation (parity with tops) ───────
# The protagonist is tagged on its cover via the SAME primitive as the
# tops (`_tags_for_entries`) and is an invitation candidate via the SAME
# ADR-0015 policy (`_collaborator_plan`, gated by `ig_collaboradors_actiu`).


class _CapUpload:
    """Captures the single-image upload's user_tags + collaborators."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(
        self, url, caption, *, user_tags=None, alt_text=None, collaborators=None
    ):
        self.calls.append({"user_tags": user_tags, "collaborators": collaborators})
        return "img-cid"

    @property
    def tag_usernames(self):
        return [t["username"] for t in (self.calls[-1]["user_tags"] or [])]

    @property
    def collaborators(self):
        return list(self.calls[-1]["collaborators"] or [])


def _sel(**over):
    """A realistic `build_moviment` result (a 'pujada'); override at will."""
    sel = {
        "kind": "pujada",
        "artist": "Maria Jaume",
        "title": "Es Teus Besos",
        "pos": 10,
        "pos_ant": 38,
        "delta": 28,
        "phrase": "del 38 al 10",
        "cover_url": None,
        "album_deezer_id": None,
        "reentrada": False,
        "artistes_instagram_urls": [],
        "artistes_pool": [],
    }
    sel.update(over)
    return sel


def _run_moviment(sel, cfg):
    """Run the Thursday moviment publish with build_moviment→sel and the
    IG client mocked. Returns the capturing upload fake."""
    import pathlib

    fake = _CapUpload()
    with (
        patch("social.payload.build_moviment", return_value=sel),
        patch(
            "social.management.commands.publicar_social.renderer.render_feed_moviment",
            return_value=[pathlib.Path("moviment.jpg")],
        ),
        patch(
            "social.management.commands.publicar_social._public_url_for",
            side_effect=lambda p: f"https://x/{p.name}",
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.upload_image",
            new=fake,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.wait_until_finished",
            return_value=None,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.publish_container",
            side_effect=lambda cid: "media-mov",
        ),
    ):
        call_command(
            "publicar_social",
            "--data",
            THURSDAY,
            "--tipus",
            "moviment",
            "--platform",
            "instagram_feed",
        )
    return fake


def _artista(handle="maria"):
    from music.models import Artista

    return Artista.objects.create(
        nom="Maria Jaume",
        slug="maria-jaume",
        aprovat=True,
        instagram_url=f"https://instagram.com/{handle}/",
    )


def test_moviment_flag_off_no_invitation(cfg):
    """The existing no-row pin, extended: no invitation either."""
    from social.models import InvitacioColaboracioIG

    assert not cfg.moviment_actiu
    call_command(
        "publicar_social",
        "--data",
        THURSDAY,
        "--tipus",
        "moviment",
        "--platform",
        "instagram_feed",
    )
    assert not SocialPost.objects.filter(tipus=SocialPost.TIPUS_MOVIMENT).exists()
    assert not InvitacioColaboracioIG.objects.exists()


def test_moviment_tags_and_invites_with_username(cfg):
    """Protagonist with a handle + collab system on → tag on the cover,
    invitation candidate, and one registry row (tipus=moviment)."""
    from social.models import InvitacioColaboracioIG

    art = _artista("maria")
    cfg.moviment_actiu = True
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    sel = _sel(
        artistes_instagram_urls=["https://instagram.com/maria/"],
        artistes_pool=[{"id": art.id, "username": "maria"}],
    )
    fake = _run_moviment(sel, cfg)

    post = SocialPost.objects.get(tipus=SocialPost.TIPUS_MOVIMENT)
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert fake.tag_usernames == ["maria"]  # tagged on the cover
    assert fake.collaborators == ["maria"]  # invited
    inv = InvitacioColaboracioIG.objects.get(artista=art)
    assert inv.tipus_publicacio == SocialPost.TIPUS_MOVIMENT
    assert inv.estat == InvitacioColaboracioIG.ESTAT_PENDENT


def test_moviment_no_username_clean(cfg):
    """No handle → no tag, no invitation, but the post still publishes."""
    from social.models import InvitacioColaboracioIG

    cfg.moviment_actiu = True
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    fake = _run_moviment(_sel(), cfg)  # empty urls + pool

    post = SocialPost.objects.get(tipus=SocialPost.TIPUS_MOVIMENT)
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert fake.calls[-1]["user_tags"] is None
    assert fake.calls[-1]["collaborators"] is None
    assert not InvitacioColaboracioIG.objects.exists()


def test_moviment_cooldown_no_invite_but_tagged(cfg):
    """Protagonist in category-A cooldown (recent acceptance): still
    tagged, but NOT re-invited; post publishes clean."""
    from django.utils import timezone

    from social.models import InvitacioColaboracioIG

    art = _artista("maria")
    # A recent acceptance → category A. Cooldown A is measured from the
    # last invite vs `timezone.now()` (NOT --data), so seed it 2 days ago
    # to sit safely inside the 15-day window.
    recent = timezone.now() - datetime.timedelta(days=2)
    InvitacioColaboracioIG.objects.create(
        artista=art,
        username_snapshot="maria",
        ig_media_id="old-media",
        tipus_publicacio=SocialPost.TIPUS_TOP_PPCC,
        data_invitacio=recent,
        estat=InvitacioColaboracioIG.ESTAT_ACCEPTADA,
        data_resolucio=recent,
    )
    cfg.moviment_actiu = True
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    sel = _sel(
        artistes_instagram_urls=["https://instagram.com/maria/"],
        artistes_pool=[{"id": art.id, "username": "maria"}],
    )
    fake = _run_moviment(sel, cfg)

    post = SocialPost.objects.get(tipus=SocialPost.TIPUS_MOVIMENT)
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert fake.tag_usernames == ["maria"]  # tag never depends on cooldown
    assert fake.collaborators == []  # in cooldown → not invited
    # No NEW registry row for the moviment post (only the seeded one stays).
    assert InvitacioColaboracioIG.objects.count() == 1
    assert not InvitacioColaboracioIG.objects.filter(
        tipus_publicacio=SocialPost.TIPUS_MOVIMENT
    ).exists()
