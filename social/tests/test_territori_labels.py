"""Territorial label correctness (2026-05-31 refactor).

Pins: the genitive form (`TERRITORI_DE`, used after "Top …"/"al Nè …")
and the short form (`TERRITORI_SHORT`, story pills/OG/hashtags); no bare
"Illes" / article-less names; no "PPCC" / "Països Catalans" ever
user-visible; and no narrative phrase template double-prefixes a
preposition before `{territori_label}` now that the placeholder carries
the genitive form.
"""

from __future__ import annotations

import pytest

import social.narrative.banks.connectors as conn_bank
import social.narrative.banks.cta as cta_bank
import social.narrative.banks.hero as hero_bank
import social.narrative.banks.top5 as top5_bank
import social.narrative.banks.transitions as trans_bank
from social.narrative.banks.hashtags import TERRITORY_HASHTAGS
from social.narrative.utils import (
    TERRITORI_DE,
    TERRITORI_SHORT,
    territori_label,
    territori_short,
)

ALL_SLUGS = ("PPCC", "CAT", "VAL", "BAL", "AND", "CNO", "FRA", "ALG", "CAR", "ALT")


# ── label dicts (source of truth) ────────────────────────────────────


def test_genitive_forms():
    assert territori_label("PPCC") == "Global"  # no preposition
    assert territori_label("CAT") == "de Catalunya"
    assert territori_label("VAL") == "del País Valencià"
    assert territori_label("BAL") == "de les Illes Balears"
    assert territori_label("CNO") == "de Catalunya Nord"
    assert territori_label("ALG") == "de l'Alguer"
    assert territori_label("FRA") == "de la Franja"


def test_short_forms():
    assert territori_short("PPCC") == "Global"
    assert territori_short("BAL") == "Balears"  # not "Illes"
    assert territori_short("CAT") == "Catalunya"


def test_no_bare_illes_and_full_coverage():
    for slug in ALL_SLUGS:
        assert slug in TERRITORI_DE and slug in TERRITORI_SHORT
    # "Illes" must never appear without "les Illes Balears".
    for d in (TERRITORI_DE, TERRITORI_SHORT):
        for val in d.values():
            assert val != "Illes"
            if "Illes" in val:
                assert "les Illes Balears" in val


def test_no_ppcc_or_paisos_catalans_visible():
    for d in (TERRITORI_DE, TERRITORI_SHORT):
        for val in d.values():
            low = val.lower()
            assert "ppcc" not in low
            assert "països catalans" not in low
            assert "paisos catalans" not in low


# ── hashtags ─────────────────────────────────────────────────────────


def test_no_paisos_catalans_hashtag():
    for tags in TERRITORY_HASHTAGS.values():
        for t in tags:
            assert "païsoscatalans" not in t.lower()
            assert "paisoscatalans" not in t.lower()
    # PPCC keeps only neutral hashtags, no global-territory tag.
    assert TERRITORY_HASHTAGS["PPCC"] == ["#TopQuaranta", "#MúsicaEnCatalà"]


# ── phrase templates: no double preposition ──────────────────────────


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def _templates_with_label():
    out: list[str] = []
    for m in (hero_bank, top5_bank, trans_bank, conn_bank, cta_bank):
        for name, val in vars(m).items():
            if name.startswith("_"):
                continue
            out.extend(_strings(val))
    return sorted({t for t in out if "{territori_label}" in t})


class _AnyDict(dict):
    """Returns a dummy for any unset placeholder so a template renders."""

    def __missing__(self, key):  # noqa: D401
        return "X"


@pytest.mark.parametrize(
    "de_form", ["de les Illes Balears", "del País Valencià", "de Catalunya"]
)
def test_no_double_preposition_before_label(de_form):
    """Every `{territori_label}` now carries the genitive form, so no
    template may place `de/a/del` immediately before it (would render
    'de de Catalunya')."""
    templates = _templates_with_label()
    assert templates, "no templates with {territori_label} found"
    for tpl in templates:
        rendered = tpl.format_map(_AnyDict(territori_label=de_form)).lower()
        for bad in (
            " de de ",
            " a de ",
            " del de ",
            " de del ",
            " a del ",
            " de de l'",
        ):
            assert bad not in rendered, f"double preposition in: {tpl!r}"
