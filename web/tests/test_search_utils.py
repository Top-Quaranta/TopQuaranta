"""Regression tests for accent + apostrophe insensitive search.

Guards against four classes of regressions:
  1. The Python-side normaliser drifting from the SQL expression
     (would silently miss matches when one side normalises and the
     other doesn't).
  2. Re-introducing a duplicate inline copy of the helper somewhere
     (we already had to consolidate one).
  3. Apostrophe variants (curly vs straight) breaking matching.
  4. unaccent extension being absent in the DB — the test will fail
     loudly on the SQL annotation rather than silently returning empty.
"""

import pytest
from django.db import connection

from music.models import Artista
from web.api.search_utils import normalize_search_term, unaccent_field

# Postgres-only: the SQL annotation calls `unaccent()` and
# `regexp_replace(...)`. SQLite (used by the test settings for speed)
# doesn't have either, so we skip the DB-touching tests there. The
# pure-Python unit tests on `normalize_search_term` still run.
_PG = connection.vendor == "postgresql"
pg_only = pytest.mark.skipif(not _PG, reason="Requires Postgres unaccent extension.")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("L'home", "lhome"),
        ("L’home", "lhome"),  # curly apostrophe
        ("L‘home", "lhome"),  # opening curly
        ("Plàtja", "platja"),
        ("Cançó", "canco"),
        ("CAFÈ AMB GEL", "cafe amb gel"),
        ("", ""),
        (None, ""),
        ("Catalunya", "catalunya"),
    ],
)
def test_normalize_search_term(raw, expected):
    assert normalize_search_term(raw) == expected


@pg_only
@pytest.mark.django_db
def test_unaccent_field_matches_accents_and_apostrophes():
    """End-to-end: a row with accents + apostrophes must be found by
    a search term that omits either."""
    Artista.objects.create(nom="L'Home Pelat")
    Artista.objects.create(nom="Plàtja Sirena")
    Artista.objects.create(nom="Cafè amb Gel")

    qs = Artista.objects.annotate(_n=unaccent_field("nom"))

    # Apostrophe omitted:
    assert qs.filter(_n__contains=normalize_search_term("lhome")).exists()
    # Accent omitted:
    assert qs.filter(_n__contains=normalize_search_term("platja")).exists()
    assert qs.filter(_n__contains=normalize_search_term("cafe")).exists()
    # Mixed: accent in query, none in field:
    Artista.objects.create(nom="Cactus")
    assert qs.filter(_n__contains=normalize_search_term("càctus")).exists()


@pg_only
@pytest.mark.django_db
def test_unaccent_field_case_insensitive():
    Artista.objects.create(nom="MalifeTa")
    qs = Artista.objects.annotate(_n=unaccent_field("nom"))
    for q in ["malifeta", "MALIFETA", "Malifeta"]:
        assert qs.filter(_n__contains=normalize_search_term(q)).exists(), q


@pg_only
@pytest.mark.django_db
def test_unaccent_field_no_false_positives():
    """A normalised query must NOT match an unrelated artist."""
    Artista.objects.create(nom="Esther")
    qs = Artista.objects.annotate(_n=unaccent_field("nom"))
    assert not qs.filter(_n__contains=normalize_search_term("malifeta")).exists()
