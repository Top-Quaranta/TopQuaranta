"""El brief diari diu quines cues de l'staff esperen algú.

La promesa: les tasques ixen dels mateixos comptadors que el panell
(`comptadors()`), només les que no són a zero, i l'assumpte del correu
resumeix el que hi ha per fer.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime

import pytest

from analytics.management.commands import enviar_informe_youtube as cmd

AVUI = datetime.date(2026, 10, 23)


def _ctx(monkeypatch, comptadors):
    monkeypatch.setattr(cmd, "comptadors", lambda: comptadors)
    monkeypatch.setattr(
        cmd, "flux_cancons", lambda today: {"target_verificacio_setmanal": 0}
    )
    return cmd.build_context(AVUI)


@pytest.mark.django_db
def test_only_the_queues_above_zero_are_tasks_and_the_subject_counts_them(
    monkeypatch,
):
    ctx = _ctx(
        monkeypatch,
        {
            "propostes_obertes": 2,
            "solicituds_gestio_obertes": 0,
            "sollicituds_revisio_pendents": 1,
            "feedback_obert": 0,
            "publicacions_pendents": 0,
        },
    )
    assert [(t["n"], t["on"]) for t in ctx["tasques"]] == [
        (2, "/staff/propostes"),
        (1, "/staff/sollicituds-revisio"),
    ]
    assert ctx["subject"].startswith("[TopQuaranta] Brief diari · 23/10")
    assert "3 tasques" in ctx["subject"]
    text = cmd.render_text(ctx)
    assert "TASQUES PENDENTS" in text and "/staff/propostes" in text


@pytest.mark.django_db
def test_no_open_queue_means_no_task_block_and_no_count_in_the_subject(monkeypatch):
    ctx = _ctx(monkeypatch, {k: 0 for k, _, _ in cmd._TASQUES})
    assert ctx["tasques"] == []
    assert "tasques" not in ctx["subject"]
    assert "TASQUES PENDENTS" not in cmd.render_text(ctx)
