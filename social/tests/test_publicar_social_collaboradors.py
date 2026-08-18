"""Gated collaborator wiring in publicar_social (ADR-0015 tranche 3a).

Flag OFF = byte-identical no-collab path (no-regression). Flag ON = pool
→ policy → collaborators on the parent container, non-blocking guard,
registry rows only after publish. The IG client is fully mocked.
"""

from __future__ import annotations

import datetime
import io
import pathlib
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from music.models import Album, Artista, Canco
from ranking.models import ConfiguracioGlobal, TopSetmanal
from social.models import InvitacioColaboracioIG, SocialPost

SETMANA = datetime.date(2026, 4, 20)
SATURDAY = "2026-04-25"


@pytest.fixture
def top_with_handles(db):
    """PPCC top of 4 cançons; artists P1(+collab C1), P2, P3(no ig), P4.
    Pool order (by posicio, deduped, only handled) = [p1, c1, p2, p4]."""

    def _art(nom, handle):
        return Artista.objects.create(
            nom=nom,
            slug=nom.lower(),
            aprovat=True,
            instagram_url=(f"https://instagram.com/{handle}/" if handle else ""),
        )

    p1, c1, p2, p3, p4 = (
        _art("P1", "p1"),
        _art("C1", "c1"),
        _art("P2", "p2"),
        _art("P3", ""),
        _art("P4", "p4"),
    )
    alb = Album.objects.create(nom="Alb", slug="alb", artista=p1)
    specs = [(p1, [c1]), (p2, []), (p3, []), (p4, [])]
    for i, (principal, cols) in enumerate(specs, start=1):
        c = Canco.objects.create(
            nom=f"Cançó {i}",
            slug=f"canco-{i}",
            artista=principal,
            album=alb,
            verificada=True,
            activa=True,
        )
        if cols:
            c.artistes_col.add(*cols)
        TopSetmanal.objects.create(
            canco=c, territori="PPCC", setmana=SETMANA, posicio=i, score_setmanal=10 - i
        )
    return {"p1": p1, "c1": c1, "p2": p2, "p3": p3, "p4": p4}


def _cfg(*, collab: bool, slots_total: int = 3):
    cfg = ConfiguracioGlobal.load()
    cfg.instagram_actiu = True
    cfg.ig_collaboradors_actiu = collab
    cfg.ig_collab_slots_total = slots_total
    cfg.save()
    return cfg


class _FakeCarousel:
    """Captures create_carousel(collaborators=…) calls; raises on any
    username in `bad` (simulating Meta rejecting a handle)."""

    def __init__(self, bad=frozenset()):
        self.bad = set(bad)
        self.calls: list[list[str]] = []

    def __call__(self, child_ids, caption, collaborators=None):
        self.calls.append(list(collaborators or []))
        for u in collaborators or []:
            if u in self.bad:
                raise RuntimeError(f"IG API 400: invalid collaborator {u}")
        return "parent-cid"

    @property
    def last(self):
        return self.calls[-1] if self.calls else None


def _run_feed(fake_carousel, publish_side_effect="media-123"):
    """Run a Saturday PPCC feed publish with the IG client mocked."""
    with (
        patch(
            "social.management.commands.publicar_social.renderer.render_feed_top",
            return_value=[pathlib.Path("cover.jpg"), pathlib.Path("s1.jpg")],
        ),
        patch(
            "social.management.commands.publicar_social._public_url_for",
            side_effect=lambda p: f"https://x/{p.name}",
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.upload_carousel_item",
            side_effect=lambda *a, **k: f"child-{a[0][-6:]}",
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.wait_until_finished",
            return_value=None,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.create_carousel",
            new=fake_carousel,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.publish_container",
            side_effect=(
                publish_side_effect
                if isinstance(publish_side_effect, Exception)
                else lambda cid: publish_side_effect
            ),
        ),
    ):
        out = io.StringIO()
        with redirect_stdout(out):
            call_command(
                "publicar_social",
                "--data",
                SATURDAY,
                "--platform",
                "instagram_feed",
                "--tipus",
                "top_ppcc",
            )
        return out.getvalue()


@pytest.mark.django_db
def test_flag_off_no_collaborators_and_no_rows(top_with_handles):
    """No-regression: with the flag OFF the container is created with NO
    collaborators (identical payload) and no registry rows are written."""
    _cfg(collab=False)
    fake = _FakeCarousel()
    _run_feed(fake)
    # create_carousel called exactly once, with no collaborators.
    assert fake.calls == [[]]
    assert InvitacioColaboracioIG.objects.count() == 0


@pytest.mark.django_db
def test_flag_on_attaches_pool_and_writes_rows(top_with_handles):
    # Property: with the flag ON the container carries the configured
    # number of collaborators (3), every one drawn from the pool of
    # handled artists in the top, and the registry rows written after
    # publish are exactly the collaborators sent (same media, tipus,
    # pendent) — the cold-start selection ORDER is the policy's business
    # (covered by test_collab_policy), not pinned here.
    _cfg(collab=True)
    fake = _FakeCarousel()
    _run_feed(fake)
    pool = {"p1", "c1", "p2", "p4"}  # every handled artist in the top
    sent = fake.last
    assert sent is not None and len(sent) == 3
    assert len(set(sent)) == 3  # no duplicates
    assert set(sent) <= pool
    rows = {r.username_snapshot: r for r in InvitacioColaboracioIG.objects.all()}
    assert set(rows) == set(sent)
    for r in rows.values():
        assert r.ig_media_id == "media-123"
        assert r.tipus_publicacio == "top_ppcc"
        assert r.estat == InvitacioColaboracioIG.ESTAT_PENDENT
    post = SocialPost.objects.get(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED, tipus="top_ppcc"
    )
    assert post.status == SocialPost.STATUS_PUBLICAT


@pytest.mark.django_db
def test_clamp_never_more_than_three(top_with_handles):
    _cfg(collab=True, slots_total=5)  # config asks 5, pool has 4 handles
    fake = _FakeCarousel()
    _run_feed(fake)
    assert len(fake.last) == 3  # clamp to the Graph max
    assert InvitacioColaboracioIG.objects.count() == 3


@pytest.mark.django_db
def test_guard_substitutes_bad_handle(top_with_handles):
    """c1 rejected by Meta → dropped, substituted by the next pool
    candidate (p4), post still publishes; rows reflect the used set.

    Property: the guard is non-blocking — the bad handle is absent from
    the final container, the slot count is preserved by pulling from the
    reserve, the post ends `publicat`, and the registry rows equal the
    collaborators actually sent (no row for the rejected one)."""
    _cfg(collab=True)
    fake = _FakeCarousel(bad={"c1"})
    _run_feed(fake)
    sent = fake.last
    assert "c1" not in sent  # bad handle dropped
    assert len(sent) == 3 and len(set(sent)) == 3  # slot count preserved
    assert set(sent) <= {"p1", "p2", "p4"}  # only good pool handles
    assert any("c1" in call for call in fake.calls)  # it WAS tried first
    assert set(
        InvitacioColaboracioIG.objects.values_list("username_snapshot", flat=True)
    ) == set(sent)
    post = SocialPost.objects.get(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED, tipus="top_ppcc"
    )
    assert post.status == SocialPost.STATUS_PUBLICAT


@pytest.mark.django_db
def test_guard_pool_exhausted_publishes_without_collaborators(top_with_handles):
    _cfg(collab=True)
    fake = _FakeCarousel(bad={"p1", "c1", "p2", "p4"})  # every handle bad
    _run_feed(fake)
    assert fake.last == []  # final attempt has no collaborators
    assert InvitacioColaboracioIG.objects.count() == 0  # nothing sent
    post = SocialPost.objects.get(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED, tipus="top_ppcc"
    )
    assert post.status == SocialPost.STATUS_PUBLICAT  # never blocked


@pytest.mark.django_db
def test_no_orphan_rows_when_publish_fails_after_container(top_with_handles):
    """Container accepted (collaborators attached) but media_publish
    raises → NO registry rows (they'd be orphans), post marked ERROR."""
    _cfg(collab=True)
    fake = _FakeCarousel()
    # The publish failure now also makes the command exit non-zero
    # (2026-07 exit-code fix); the invariants below still hold.
    with pytest.raises(CommandError):
        _run_feed(fake, publish_side_effect=RuntimeError("IG API 500 on publish"))
    assert InvitacioColaboracioIG.objects.count() == 0
    post = SocialPost.objects.get(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED, tipus="top_ppcc"
    )
    assert post.status == SocialPost.STATUS_ERROR
