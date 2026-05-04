"""Tests for snapshot_pipeline command."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.utils import timezone

from analytics.models import MetricaPipeline


@pytest.mark.django_db
def test_snapshot_runs_and_is_idempotent():
    call_command("snapshot_pipeline")
    today = timezone.localdate()
    keys = set(
        MetricaPipeline.objects.filter(data=today).values_list("clau", flat=True)
    )
    # Core gauges always written.
    expected = {
        "cancons_verificades",
        "cancons_pendents",
        "cancons_rebutjades_acumulades",
        "artistes_aprovats",
        "artistes_pendents",
        "cobertura_whisper",
        "cobertura_mb",
        "usuaris_actius",
        "newsletter_subscriptors",
        "directori_visibles",
    }
    assert expected.issubset(keys)

    # Re-run on same day must not duplicate rows (UNIQUE on data,clau,dim1).
    call_command("snapshot_pipeline")
    for k in expected:
        assert (
            MetricaPipeline.objects.filter(data=today, clau=k, dimensio_1="").count()
            == 1
        ), f"snapshot duplicated row for {k}"
