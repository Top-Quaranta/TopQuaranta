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


def apostrof_de(nom: str) -> str:
    """Return `de {nom}` or `d'{nom}` depending on the first
    letter of `nom`. Pragmatic ruleset:

    - a/e/o/h (case-insensitive) → elide: `d'Anna`, `d'OBESES`,
      `d'Helena`. Catalan elides before `h` because the `h` is
      mute and the vowel that follows triggers the elision.
    - i/u/consonant → no elision: `de Iván`, `de Manel`,
      `de Lluís`, `de Maria Jaume`.

    Notes on edge cases we accept:
    - `Í` (accentuated `i`) doesn't elide in standard Catalan;
      `de Ítaca`. Our rule respects this.
    - `Ú` stressed: same, `de Úrsula`. Same outcome.
    - All-caps band names (`OBESES`, `OQUES GRASSES`) fall under
      the same vowel rule via `.lower()`.
    - Empty/None input falls back to `de {nom}` (safe default —
      caller is responsible for non-empty names).
    """
    if not nom:
        return f"de {nom}"
    primera = nom[0].lower()
    if primera in "aeoh":
        return f"d'{nom}"
    return f"de {nom}"


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
