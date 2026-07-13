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
    cfg = C.PolicyConfig()
    # B — never invited.
    assert C.candidate_status([], cfg, NOW) == (C.CAT_B, True, "mai convidat (B)")
    # A on cooldown.
    recs = [C.InviteRecord("acceptada", NOW - datetime.timedelta(days=5))]
    cat, elig, motiu = C.candidate_status(recs, cfg, NOW)
    assert (cat, elig) == (C.CAT_A, False) and "cooldown A" in motiu
    # Pending blocks.
    recs = [C.InviteRecord("pendent", NOW - datetime.timedelta(days=1))]
    cat, elig, motiu = C.candidate_status(recs, cfg, NOW)
    assert elig is False and "pendent" in motiu
    # C past cooldown.
    recs = [
        C.InviteRecord(
            "rebutjada",
            NOW - datetime.timedelta(days=120),
            data_resolucio=NOW - datetime.timedelta(days=100),
        )
    ]
    cat, elig, motiu = C.candidate_status(recs, cfg, NOW)
    assert (cat, elig) == (C.CAT_C, True)


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
    # Flag OFF on purpose — dry-run is read-only, independent of the gate.
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = False
    cfg.save()

    out = io.StringIO()
    with redirect_stdout(out):
        call_command("simular_colaboradors_ig", "--tipus", "top_ppcc", "--json")
    report = json.loads(out.getvalue())
    assert report["flag_actiu"] is False
    assert report["slots_efectius"] == 3
    post = report["posts"][0]
    # Cold start → first 3 of the pool.
    assert post["seleccionats"] == ["p1", "c1", "p2"]
    cats = {c["username"]: c for c in post["candidats"]}
    assert cats["p1"]["categoria"] == C.CAT_B and cats["p1"]["seleccionat"]
    # P3 has no handle → surfaced as sense_username, not in the pool.
    assert "P3" in post["sense_username"]
    # Absolutely nothing written.
    assert InvitacioColaboracioIG.objects.count() == 0
