"""Catalan article-stripping + preposition contraction tests
(Tasca C, 2026-05-18).

The contraction matrix the helper implements:

  | de + el     → del         | a + el     → al    | per + el   → pel
  | de + els    → dels        | a + els    → als   | per + els  → pels
  | de + la     → de la       | a + la     → a la  | per + la   → per la
  | de + les    → de les      | a + les    → a les | per + les  → per les
  | de + l'     → de l'       | a + l'     → a l'  | per + l'   → per l'
  | amb + *     → amb {name}  (article preserved, never contracts)

`per_a` (the compound "per a", meaning "for the sake of") shares
the `el`/`els` contraction with `per` (so "per a Els Catarres"
collapses to "pels Catarres") but renders as two literal words
when no article is present ("per a Rosalía")."""

from __future__ import annotations

from social.narrative.utils import _split_article, with_preposition

# ── articles + de ─────────────────────────────────────────────────


def test_de_with_els_contracts():
    assert with_preposition("Els Catarres", "de") == "dels Catarres"


def test_de_with_el_contracts():
    assert with_preposition("El Diluvi", "de") == "del Diluvi"


def test_de_with_la_keeps_separate():
    assert with_preposition("La Fúmiga", "de") == "de la Fúmiga"


def test_de_with_les_keeps_separate():
    assert with_preposition("Les Anxovetes", "de") == "de les Anxovetes"


def test_de_with_apostrophe_l_keeps_apostrophe():
    assert with_preposition("L'Atzar", "de") == "de l'Atzar"


def test_de_with_no_article_falls_back_to_apostrof_de():
    assert with_preposition("Rosalía", "de") == "de Rosalía"
    assert with_preposition("Anna", "de") == "d'Anna"
    assert with_preposition("OBESES", "de") == "d'OBESES"
    assert with_preposition("Helena", "de") == "d'Helena"


# ── articles + a ──────────────────────────────────────────────────


def test_a_with_articles():
    assert with_preposition("Els Catarres", "a") == "als Catarres"
    assert with_preposition("El Diluvi", "a") == "al Diluvi"
    assert with_preposition("La Fúmiga", "a") == "a la Fúmiga"
    assert with_preposition("Les Anxovetes", "a") == "a les Anxovetes"
    assert with_preposition("L'Atzar", "a") == "a l'Atzar"
    assert with_preposition("Rosalía", "a") == "a Rosalía"


# ── articles + per ────────────────────────────────────────────────


def test_per_with_articles():
    assert with_preposition("Els Catarres", "per") == "pels Catarres"
    assert with_preposition("El Diluvi", "per") == "pel Diluvi"
    assert with_preposition("La Fúmiga", "per") == "per la Fúmiga"
    assert with_preposition("Les Anxovetes", "per") == "per les Anxovetes"
    assert with_preposition("L'Atzar", "per") == "per l'Atzar"
    assert with_preposition("Rosalía", "per") == "per Rosalía"


# ── per_a (compound, "for the sake of") ───────────────────────────


def test_per_a_with_articles_contracts_same_as_per():
    """`per a + els/el` → `pels/pel`. The "a" is absorbed into
    the contraction in the standard normative form."""
    assert with_preposition("Els Catarres", "per_a") == "pels Catarres"
    assert with_preposition("El Diluvi", "per_a") == "pel Diluvi"


def test_per_a_without_article_keeps_per_a():
    """`per a Rosalía` — the compound preposition stays literal
    when there's no article to contract with."""
    assert with_preposition("Rosalía", "per_a") == "per a Rosalía"
    assert with_preposition("Maria Jaume", "per_a") == "per a Maria Jaume"


def test_per_a_with_la_keeps_separate():
    assert with_preposition("La Fúmiga", "per_a") == "per a la Fúmiga"


# ── amb (never contracts) ─────────────────────────────────────────


def test_amb_never_contracts():
    assert with_preposition("Els Catarres", "amb") == "amb Els Catarres"
    assert with_preposition("La Fúmiga", "amb") == "amb La Fúmiga"
    assert with_preposition("OBESES", "amb") == "amb OBESES"
    assert with_preposition("Rosalía", "amb") == "amb Rosalía"


# ── _split_article internals ──────────────────────────────────────


def test_split_article_detects_titlecase():
    assert _split_article("Els Catarres") == ("els", "Catarres")
    assert _split_article("El Diluvi") == ("el", "Diluvi")
    assert _split_article("La Fúmiga") == ("la", "Fúmiga")
    assert _split_article("Les Anxovetes") == ("les", "Anxovetes")
    assert _split_article("L'Atzar") == ("l'", "Atzar")


def test_split_article_ignores_non_articles():
    assert _split_article("Rosalía") == (None, "Rosalía")
    assert _split_article("Maria Jaume") == (None, "Maria Jaume")


def test_split_article_does_not_detect_all_caps():
    """Edge case: deezer occasionally returns all-caps names like
    'LA FÚMIGA'. We intentionally don't strip the article in that
    case — applying a contraction on top of an all-caps token would
    look broken ('dels FÚMIGA'). The pragmatic interpretation is
    that the upstream upper-cased the whole string, so we treat it
    as a name without an article-as-particle."""
    assert _split_article("LA FÚMIGA") == (None, "LA FÚMIGA")
    assert with_preposition("LA FÚMIGA", "de") == "de LA FÚMIGA"


def test_split_article_does_not_detect_lowercase():
    """Lowercase 'el' / 'la' could be article-like but might also
    be the start of a regular word ('elsa', 'la-la-la'). Stay
    conservative — only TitleCase triggers detection."""
    assert _split_article("elsa") == (None, "elsa")
    assert _split_article("la la") == (None, "la la")


# ── edge cases ───────────────────────────────────────────────────


def test_empty_name():
    assert with_preposition("", "de") == "de "
    assert with_preposition("", "amb") == "amb "


def test_bare_article_token_falls_back_to_apostrof_elision():
    """'El' alone — no name after the article — isn't detected as
    an article (the splitter requires a non-empty rest). The
    apostrof_de fallback fires on the leading 'E' and produces
    'd'El'. Pin the behaviour."""
    assert with_preposition("El", "de") == "d'El"
