#!/usr/bin/env python3
"""Hard gate: a doc inside `size.scope` exceeds `size.threshold_lines`
without being on the `exempt_permanent` or `grandfathered` allow-list
of `docs/policies/docs-map.yml`.

The allow-lists make the threshold practical instead of theoretical:
some files (`roadmap.md`) grow forever by design; some currently
exceed the limit but are scheduled for a split (Rule 3 of
`docs-maintenance.md`). When a grandfathered file is finally split,
its entry is removed from the YAML and the gate enforces the limit
from then on. A drift upwards (new file growing past the limit) is
the case we want to fail loudly.

Exit codes:
  0 - every doc inside `scope` is under the threshold, or covered
      by one of the allow-lists.
  1 - at least one offender exists; the message lists offenders
      with line counts.

# Spec: docs/policies/conventions.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = REPO_ROOT / "docs" / "policies" / "docs-map.yml"


def load_map(path: Path = MAP_PATH) -> dict:
    with path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg


def _count_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def find_oversize_docs(repo_root: Path, cfg: dict) -> list[tuple[str, int]]:
    """Returns [(rel_path, line_count), ...] for every doc inside
    `size.scope` that exceeds `size.threshold_lines` and is not on
    `exempt_permanent` or `grandfathered`. Empty `size` block means
    no enforcement."""
    size = cfg.get("size") or {}
    threshold = size.get("threshold_lines")
    scopes: list[str] = size.get("scope") or []
    if not threshold or not scopes:
        return []

    exempt = {entry["path"] for entry in size.get("exempt_permanent") or []}
    grandfathered = {entry["path"] for entry in size.get("grandfathered") or []}

    offenders: list[tuple[str, int]] = []
    for scope in scopes:
        root = repo_root / scope
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            rel = str(path.relative_to(repo_root))
            if rel in exempt or rel in grandfathered:
                continue
            lines = _count_lines(path)
            if lines > threshold:
                offenders.append((rel, lines))
    return offenders


def main(repo_root: Path = REPO_ROOT) -> int:
    cfg = load_map()
    offenders = find_oversize_docs(repo_root, cfg)
    if offenders:
        threshold = cfg["size"]["threshold_lines"]
        print(
            f"::error ::Docs gate (size) failed. The following docs "
            f"exceed the {threshold}-line threshold and are not on "
            f"`size.exempt_permanent` or `size.grandfathered` in "
            f"docs/policies/docs-map.yml:"
        )
        for path, lines in offenders:
            print(f"  {path}: {lines} lines (> {threshold})")
        print(
            "Either split per docs-maintenance.md Rule 3, or add a "
            "`grandfathered:` entry with a `reason:` and `current_lines:`."
        )
        return 1
    print("All docs under the configured scopes respect the size " "threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
