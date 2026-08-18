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
    TERRITORI_ORDINAL,
    TERRITORI_SHORT,
    territori_label,
    territori_ordinal,
    territori_short,
)

# Public top territoris — the ones with a published top, hence a label.
# `ALT` ("Altres") is intentionally NOT here: it never surfaces as a top,
# so its lookups must raise KeyError (see test_alt_raises_keyerror).
PUBLIC_SLUGS = ("PPCC", "CAT", "VAL", "BAL", "AND", "CNO", "FRA", "ALG", "CAR")


# ── label dicts (source of truth) ────────────────────────────────────


def test_genitive_forms():
    assert territori_label("PPCC") == "Global"  # no preposition
    assert territori_label("CAT") == "de Catalunya"
    assert territori_label("VAL") == "del País Valencià"
    assert territori_label("BAL") == "de les Illes Balears"
    assert territori_label("AND") == "d'Andorra"
    assert territori_label("CAR") == "del Carxe"
    assert territori_label("CNO") == "de Catalunya Nord"
    assert territori_label("ALG") == "de l'Alguer"
    assert territori_label("FRA") == "de la Franja"


def test_short_forms():
    assert territori_short("PPCC") == "Global"
    assert territori_short("BAL") == "Balears"  # not "Illes"
    assert territori_short("CAT") == "Catalunya"
    assert territori_short("AND") == "Andorra"
    assert territori_short("CAR") == "el Carxe"
    assert territori_short("CNO") == "Catalunya Nord"


def test_ordinal_forms():
    # PPCC overrides to the genitive locative form ("al 1r del top general").
    assert territori_ordinal("PPCC") == "del top general"
    assert TERRITORI_ORDINAL == {"PPCC": "del top general"}
    # Every other territori falls back to its TERRITORI_DE form — no-op.
    for slug in PUBLIC_SLUGS:
        if slug == "PPCC":
            continue
        assert territori_ordinal(slug) == TERRITORI_DE[slug]


def test_alt_raises_keyerror():
    # ALT is deliberately omitted from both dicts; lookups must fail loud.
    assert "ALT" not in TERRITORI_DE
    assert "ALT" not in TERRITORI_SHORT
    for fn in (territori_label, territori_short, territori_ordinal):
        with pytest.raises(KeyError):
            fn("ALT")


def test_no_bare_illes_and_full_coverage():
    for slug in PUBLIC_SLUGS:
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


def _templates_with(placeholder: str):
    out: list[str] = []
    for m in (hero_bank, top5_bank, trans_bank, conn_bank, cta_bank):
        for name, val in vars(m).items():
            if name.startswith("_"):
                continue
            out.extend(_strings(val))
    return sorted({t for t in out if placeholder in t})


class _AnyDict(dict):
    """Returns a dummy for any unset placeholder so a template renders."""

    def __missing__(self, key):  # noqa: D401
        return "X"


_BAD_SEQUENCES = (
    " de de ",
    " a de ",
    " del de ",
    " de del ",
    " a del ",
    " de de l'",
    " del del ",
    " al del ",
    " al de ",
)


@pytest.mark.parametrize(
    "placeholder,forms",
    [
        # {territori_label} carries the genitive ("de Catalunya"); PPCC is
        # the bare "Global" (no leading preposition to double).
        (
            "{territori_label}",
            ["de les Illes Balears", "del País Valencià", "de Catalunya", "Global"],
        ),
        # {territori_ordinal} carries the genitive too; PPCC → "del top
        # general" (still genitive — must not double with a preceding prep).
        (
            "{territori_ordinal}",
            [
                "de les Illes Balears",
                "del País Valencià",
                "de Catalunya",
                "del top general",
            ],
        ),
    ],
)
def test_no_double_preposition_before_placeholder(placeholder, forms):
    """No template may place `de/a/del` immediately before a territori
    placeholder that already carries the genitive (would render
    'de de Catalunya' / 'al del top general')."""
    templates = _templates_with(placeholder)
    assert templates, f"no templates with {placeholder} found"
    for form in forms:
        for tpl in templates:
            rendered = tpl.format_map(
                _AnyDict(**{placeholder.strip("{}"): form})
            ).lower()
            for bad in _BAD_SEQUENCES:
                assert bad not in rendered, f"double preposition ({form!r}) in: {tpl!r}"


# ── render checks: PPCC ordinal vs Top context + no regression ───────


def test_ppcc_ordinal_templates_say_top_general():
    """At least one ordinal/locative hero template must exist and, with
    PPCC, render the genitive "del top general" rather than a terse bare
    "Global"."""
    ordinal_templates = _templates_with("{territori_ordinal}")
    assert ordinal_templates
    de = territori_label("PPCC")  # "Global"
    ordinal = territori_ordinal("PPCC")  # "del top general"
    saw_top_general = False
    for tpl in ordinal_templates:
        rendered = tpl.format_map(
            _AnyDict(territori_ordinal=ordinal, territori_label=de)
        )
        assert "del top general" in rendered
        saw_top_general = True
    assert saw_top_general
