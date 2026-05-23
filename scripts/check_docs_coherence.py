#!/usr/bin/env python3
"""Soft-signal check: does this PR touch a documented subsystem
without updating its doc?

Reads the canonical prefix-to-doc mapping from
`docs/policies/docs-map.yml` (single source of truth, shared with
the future pre-commit hook in FASE 2) and applies longest-prefix
match: the more specific `ingesta/clients/spotify.py` beats the
generic `ingesta/`, so the right doc surfaces.

Behaviour is intentionally SOFT today (FASE 1):
  - When a PR touches a code file that resolves to a doc and that
    doc is NOT also in the PR diff, this script prints a `::warning`
    annotation and emits the marker line `needs-docs-review` on
    stdout. The CI step then adds the `needs-docs-review` label.
  - Excluded prefixes (graveyard scripts, vendored code) never trip
    the check.
  - Exit code is always 0; the PR template checkbox stays the
    canonical gate. Blocking enforcement is FASE 2.

Usage:
    python3 scripts/check_docs_coherence.py < changed_files.txt
    # or
    git diff --name-only origin/main...HEAD \
        | python3 scripts/check_docs_coherence.py

# Spec: docs/policies/docs-maintenance.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = REPO_ROOT / "docs" / "policies" / "docs-map.yml"
LABEL_MARKER = "needs-docs-review"


def load_map(path: Path = MAP_PATH) -> dict:
    """Parse `docs-map.yml` into a dict with `mapping` and `exclude`
    lists. Missing keys default to empty lists so a partially-written
    file does not crash CI."""
    with path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    cfg.setdefault("mapping", [])
    cfg.setdefault("exclude", [])
    return cfg


def resolve(
    file: str,
    mapping: list[dict],
    exclude: list[dict],
) -> str | None:
    """Return the doc path that owns `file`, or None when the file
    is excluded or unmapped.

    Excludes are checked first (a file in `scripts/` never resolves
    to a doc even if a later prefix would otherwise match it).
    Mapping entries are sorted by descending prefix length so the
    most specific entry wins.
    """
    for entry in exclude:
        if file.startswith(entry["prefix"]):
            return None
    ordered = sorted(mapping, key=lambda e: -len(e["prefix"]))
    for entry in ordered:
        if file.startswith(entry["prefix"]):
            return entry["doc"]
    return None


def find_coupled_misses(
    changed: list[str], mapping: list[dict], exclude: list[dict]
) -> list[tuple[str, str]]:
    """For every changed code file that resolves to a doc, check
    whether that doc is also in `changed`. Returns the list of
    (code_file, missing_doc) pairs in insertion order, deduplicated."""
    docs_touched = {f for f in changed if f.startswith("docs/")}
    seen: set[tuple[str, str]] = set()
    misses: list[tuple[str, str]] = []
    for file in changed:
        doc = resolve(file, mapping, exclude)
        if doc is None:
            continue
        if doc in docs_touched:
            continue
        pair = (file, doc)
        if pair in seen:
            continue
        seen.add(pair)
        misses.append(pair)
    return misses


def main() -> int:
    changed = [line.strip() for line in sys.stdin if line.strip()]
    cfg = load_map()
    misses = find_coupled_misses(changed, cfg["mapping"], cfg["exclude"])
    if misses:
        formatted = "; ".join(f"{f} -> {d}" for f, d in misses)
        print(
            f"::warning ::PR touches documented subsystems without "
            f"updating their docs: {formatted}"
        )
        print(LABEL_MARKER)
    else:
        print("No subsystem/doc coupling triggers detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
