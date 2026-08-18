"""`simular_colaboradors_ig` dry-run command — read-only, writes nothing.

Also covers `collaboradors.candidate_status` reasons.
"""

from __future__ import annotations

import datetime
import io
import json
from contextlib import redirect_stdout

import pytest
from django.core.management import call_command

from music.models import Album, Artista, Canco
from ranking.models import ConfiguracioGlobal, TopSetmanal
from social import collaboradors as C
from social.models import InvitacioColaboracioIG

SETMANA = datetime.date(2026, 4, 20)
NOW = datetime.datetime(2026, 4, 25, tzinfo=datetime.timezone.utc)


def test_candidate_status_reasons():
    # Property: category + eligibility per situation (B never invited →
    # eligible; A inside cooldown → blocked; any pending → blocked; C past
    # cooldown → eligible), and the reason is a non-empty human string —
    # its exact copy is not pinned.
    cfg = C.PolicyConfig()
    # B — never invited.
    cat, elig, motiu = C.candidate_status([], cfg, NOW)
    assert (cat, elig) == (C.CAT_B, True) and motiu
    # A on cooldown.
    recs = [C.InviteRecord("acceptada", NOW - datetime.timedelta(days=5))]
    cat, elig, motiu = C.candidate_status(recs, cfg, NOW)
    assert (cat, elig) == (C.CAT_A, False) and motiu
    # A past cooldown → eligible again.
    recs = [
        C.InviteRecord(
            "acceptada", NOW - datetime.timedelta(days=cfg.cooldown_a_dies + 1)
        )
    ]
    cat, elig, motiu = C.candidate_status(recs, cfg, NOW)
    assert (cat, elig) == (C.CAT_A, True) and motiu
    # Pending blocks.
    recs = [C.InviteRecord("pendent", NOW - datetime.timedelta(days=1))]
    cat, elig, motiu = C.candidate_status(recs, cfg, NOW)
    assert elig is False and motiu
    # C inside cooldown → blocked.
    recs = [
        C.InviteRecord(
            "rebutjada",
            NOW - datetime.timedelta(days=cfg.cooldown_c_dies - 5),
            data_resolucio=NOW - datetime.timedelta(days=cfg.cooldown_c_dies - 10),
        )
    ]
    cat, elig, motiu = C.candidate_status(recs, cfg, NOW)
    assert (cat, elig) == (C.CAT_C, False) and motiu
    # C past cooldown.
    recs = [
        C.InviteRecord(
            "rebutjada",
            NOW - datetime.timedelta(days=cfg.cooldown_c_dies + 30),
            data_resolucio=NOW - datetime.timedelta(days=cfg.cooldown_c_dies + 10),
        )
    ]
    cat, elig, motiu = C.candidate_status(recs, cfg, NOW)
    assert (cat, elig) == (C.CAT_C, True) and motiu


@pytest.fixture
def top(db):
    def _art(nom, handle):
        return Artista.objects.create(
            nom=nom,
            slug=nom.lower(),
            aprovat=True,
            instagram_url=(f"https://instagram.com/{handle}/" if handle else ""),
        )

    p1, c1, p2, p3 = (
        _art("P1", "p1"),
        _art("C1", "c1"),
        _art("P2", "p2"),
        _art("P3", ""),
    )
    alb = Album.objects.create(nom="Alb", slug="alb", artista=p1)
    for i, (principal, cols) in enumerate([(p1, [c1]), (p2, []), (p3, [])], start=1):
        c = Canco.objects.create(
            nom=f"C{i}",
            slug=f"c-{i}",
            artista=principal,
            album=alb,
            verificada=True,
            activa=True,
        )
        if cols:
            c.artistes_col.add(*cols)
        TopSetmanal.objects.create(
            canco=c, territori="PPCC", setmana=SETMANA, posicio=i, score_setmanal=9 - i
        )
    return {"p1": p1, "c1": c1, "p2": p2, "p3": p3}


@pytest.mark.django_db
def test_dry_run_reports_and_writes_nothing(top):
    # Property: the dry-run reports the flag state + the effective slot
    # count, selects `slots_efectius` distinct handled candidates from the
    # pool (cold start → all category B), surfaces the handle-less artist
    # as `sense_username` (never in the pool), and writes NOTHING. The
    # exact selection order is the policy's business (test_collab_policy).
    # Flag OFF on purpose — dry-run is read-only, independent of the gate.
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = False
    cfg.save()

    out = io.StringIO()
    with redirect_stdout(out):
        call_command("simular_colaboradors_ig", "--tipus", "top_ppcc", "--json")
    report = json.loads(out.getvalue())
    assert report["flag_actiu"] is False
    assert report["slots_efectius"] == C.effective_slots(C.PolicyConfig())
    post = report["posts"][0]
    pool = {"p1", "c1", "p2"}
    selected = post["seleccionats"]
    assert len(selected) == min(report["slots_efectius"], len(pool))
    assert set(selected) <= pool and len(set(selected)) == len(selected)
    cats = {c["username"]: c for c in post["candidats"]}
    assert set(cats) == pool
    for u in pool:
        assert cats[u]["categoria"] == C.CAT_B  # cold start
        assert cats[u]["seleccionat"] is (u in selected)
    # P3 has no handle → surfaced as sense_username, not in the pool.
    assert "P3" in post["sense_username"]
    assert "p3" not in cats
    # Absolutely nothing written.
    assert InvitacioColaboracioIG.objects.count() == 0
