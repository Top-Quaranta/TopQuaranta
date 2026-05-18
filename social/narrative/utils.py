"""Shared helpers for the narrative engine (Fase 4 reset, 2026-05-18).

Three primitives the rest of the package leans on:

* `apostrof_de(nom)` — Catalan "de {N}" vs "d'{N}" decision. The
  full surface is messier than the rule of thumb (h muda, atones
  in í/ú, capitalisation quirks) but the practical rule below is
  what a periodista would actually write.
* `llista_amb_i(items)` — natural Catalan list joiner ("X, Y i Z").
* `territori_label(codi)` — single source of truth for the
  user-facing territori name (PPCC → "Global" decision, see CLAUDE.md).
"""

from __future__ import annotations

_ARTICLE_TOKENS = {"El", "Els", "La", "Les"}  # whole-word articles
# Apostrophe article "L'" — we match the literal prefix in the
# unsplit name because "L'Atzar" has no space after "L'".


def _split_article(nom: str) -> tuple[str | None, str]:
    """Detect a leading Catalan article in `nom`.

    Returns `(article_lower, rest)` where:
      * `article_lower` is one of `'el'`, `'els'`, `'la'`, `'les'`,
        `'l\\''` (with the apostrophe) or `None` if no article.
      * `rest` is the rest of the name (no leading article token).
        For `L'Atzar` → `("l'", "Atzar")`.

    Title-case sensitive: only matches TitleCase articles. All-caps
    band names like `LA FÚMIGA` are intentionally NOT detected — the
    pragmatic interpretation is that an upstream upper-cased name
    has lost the article-as-grammatical-particle signal, and adding
    a contraction on top of an all-caps token would look broken
    (`dels FÚMIGA`). Same for lowercase-only inputs."""
    if not nom:
        return None, nom
    # L' + (no space, uppercase letter) like "L'Atzar"
    if len(nom) >= 3 and nom[:2] == "L'" and nom[2].isalpha():
        return "l'", nom[2:]
    # Articles separated by a space.
    head, _, rest = nom.partition(" ")
    if head in _ARTICLE_TOKENS and rest:
        return head.lower(), rest
    return None, nom


# Contraction table: (preposition, article_lower) → joined prefix.
# Articles not present in the table → preposition + " " + article
# (e.g. "de la Fúmiga" stays uncontracted).
#
# `per_a` is the compound preposition "per a" (meaning "for the
# sake of"). It contracts the same as `per` does with `el`/`els`
# (so `per a els Catarres` → `pels Catarres`), and stays as
# `per a` otherwise. We expose it as a separate key so callers
# can distinguish "Setmana redona per a Rosalía" (uncontracted,
# semantically "per a") from "Top monopolitzat pels Catarres"
# (contracted, semantically "per [a] els").
_CONTRACTIONS = {
    ("de", "el"): "del",
    ("de", "els"): "dels",
    ("a", "el"): "al",
    ("a", "els"): "als",
    ("per", "el"): "pel",
    ("per", "els"): "pels",
    ("per_a", "el"): "pel",
    ("per_a", "els"): "pels",
}


def with_preposition(nom: str, preposition: str) -> str:
    """Render `<preposition> <nom>` with Catalan contractions and
    apostrophe-elision applied at the article boundary.

    * `with_preposition("Els Catarres", "de")` → `"dels Catarres"`
    * `with_preposition("El Diluvi", "a")` → `"al Diluvi"`
    * `with_preposition("La Fúmiga", "de")` → `"de la Fúmiga"`
    * `with_preposition("L'Atzar", "per")` → `"per l'Atzar"`
    * `with_preposition("Rosalía", "de")` → `"de Rosalía"`
    * `with_preposition("Anna", "de")` → `"d'Anna"` (apostrophe
      elision on vowel-initial names without an article)
    * `with_preposition("OBESES", "amb")` → `"amb OBESES"` (the
      preposition `amb` never contracts).

    Detection notes:
    * Only TitleCase articles are detected (`Els`, `El`, `La`,
      `Les`, `L'`). All-caps inputs like `LA FÚMIGA` are treated
      as plain names — contracting on an all-caps token would
      look broken (`dels FÚMIGA`). If the upstream feeds us those,
      decide editorially whether to normalise the name itself.
    * `amb` always returns `"amb {nom}"` — the article stays.
    """
    if not nom:
        return f"{preposition} {nom}"

    if preposition == "amb":
        return f"amb {nom}"

    # `per_a` is the compound preposition "per a" — internal key
    # for the contraction table but rendered as the literal two
    # words when no article is present.
    rendered_prep = "per a" if preposition == "per_a" else preposition

    article, rest = _split_article(nom)

    if article is not None:
        contraction = _CONTRACTIONS.get((preposition, article))
        if contraction:
            # `del Diluvi`, `dels Catarres`, `al Diluvi`, …
            return f"{contraction} {rest}"
        # No contraction defined for (preposition, article):
        # render the article in lowercase form ("la", "les", "l'")
        # so we get "de la Fúmiga", "a les Anxovetes", "per l'Atzar".
        if article == "l'":
            return f"{rendered_prep} l'{rest}"
        return f"{rendered_prep} {article} {rest}"

    # No article. Apostrophe-elision for `de` on vowel/h-mute
    # initials. The other prepositions (`a`, `per`, `per a`)
    # don't elide in Catalan.
    if preposition == "de":
        primera = nom[0].lower()
        if primera in "aeoh":
            return f"d'{nom}"
    return f"{rendered_prep} {nom}"


def apostrof_de(nom: str) -> str:
    """Backwards-compatible wrapper. `apostrof_de(X)` is identical
    to `with_preposition(X, "de")` — keep the older name because
    `Scenario.data["de_artista"]` is used by every hero template
    via `{de_artista}` interpolation."""
    return with_preposition(nom, "de")


def llista_amb_i(items: list[str]) -> str:
    """Join a list in Catalan: `X`, `X i Y`, `X, Y i Z`, …

    No serial comma — Catalan doesn't take it. Empty list returns
    empty string; single item is itself."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} i {items[1]}"
    return ", ".join(items[:-1]) + f" i {items[-1]}"


_TERRITORI_LABELS = {
    "PPCC": "Global",  # public-facing rename — see CLAUDE.md §5
    "CAT": "Catalunya",
    "VAL": "País Valencià",
    "BAL": "Illes",
    "AND": "Andorra",
    "CNO": "Catalunya Nord",
    "FRA": "Franja",
    "ALG": "Alguer",
    "ALT": "Altres",
}


def territori_label(codi: str) -> str:
    """Single source of truth for the user-facing territori name.
    Unknown codes fall through to the raw code (defensive — the
    composer should never crash because a new territori was added
    upstream without updating this map)."""
    return _TERRITORI_LABELS.get(codi, codi)
