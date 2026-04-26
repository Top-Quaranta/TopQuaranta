"""Shared helpers for accent + apostrophe insensitive search.

Used both by staff list endpoints and by public-facing search (artist
directory, …). Postgres `unaccent` strips diacritics on the field side;
we mirror it in Python on the search term and additionally drop
apostrophes (straight + curly) on both sides so:

  "lhome"     matches  "L'home"
  "platja"    matches  "Plàtja"
  "L'Home"    matches  "lhome"

Implementation: annotate each row with regexp_replace(unaccent(field), …)
and ILIKE-search against a normalised term.
"""

from __future__ import annotations

import unicodedata

from django.db.models import F, Func, Value

# Straight + 4 common curly variants. Kept in sync with `_normalize_search_term`.
_APOSTROPHE_RE = "['’‘`´]"
_APOSTROPHE_CHARS = "'’‘`´"


def normalize_search_term(s: str) -> str:
    """Lower + strip diacritics + drop apostrophes. Mirrors the SQL
    expression used in `unaccent_field`, so the two sides match."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    for ap in _APOSTROPHE_CHARS:
        s = s.replace(ap, "")
    return s


def unaccent_field(field: str):
    """Build an ORM expression: regexp_replace(unaccent(lower(field)), apostrophes, '', 'g').

    Used to annotate a queryset with a normalised search column. The
    annotation is then matched against `normalize_search_term(query)`
    via __contains.
    """
    lowered = Func(F(field), function="lower")
    unaccented = Func(lowered, function="unaccent")
    no_apostrophes = Func(
        unaccented,
        Value(_APOSTROPHE_RE),
        Value(""),
        Value("g"),
        function="regexp_replace",
    )
    return no_apostrophes
