"""Tests for analytics.events.register()."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from analytics.events import register
from analytics.models import MetricaEsdeveniment


@pytest.mark.django_db
def test_register_creates_row():
    register("registre_complet")
    row = MetricaEsdeveniment.objects.get(clau="registre_complet")
    assert row.comptador == 1
    assert row.dimensio_1 == ""
    assert row.dimensio_2 == ""


@pytest.mark.django_db
def test_register_increments_existing():
    register("pageview", dim1="/")
    register("pageview", dim1="/")
    register("pageview", dim1="/", n=3)
    row = MetricaEsdeveniment.objects.get(clau="pageview", dimensio_1="/")
    assert row.comptador == 5


@pytest.mark.django_db
def test_register_separate_dims_are_distinct_rows():
    register("pageview", dim1="/")
    register("pageview", dim1="/top")
    assert MetricaEsdeveniment.objects.filter(clau="pageview").count() == 2


@pytest.mark.django_db
def test_register_skips_zero_n():
    register("noop", n=0)
    register("noop", n=-5)
    assert not MetricaEsdeveniment.objects.filter(clau="noop").exists()


@pytest.mark.django_db
def test_register_swallows_db_error_silently():
    """Analytics MUST NOT propagate DB errors to the caller."""
    with patch.object(
        MetricaEsdeveniment.objects, "get_or_create", side_effect=RuntimeError("boom")
    ):
        # Should not raise.
        register("kaboom")
    # And nothing was written.
    assert not MetricaEsdeveniment.objects.filter(clau="kaboom").exists()


@pytest.mark.django_db
def test_register_force_raise_propagates():
    with patch.object(
        MetricaEsdeveniment.objects, "get_or_create", side_effect=RuntimeError("boom")
    ):
        with pytest.raises(RuntimeError):
            register("kaboom", force_raise=True)
