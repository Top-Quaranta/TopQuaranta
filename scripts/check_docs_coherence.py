#!/usr/bin/env python3
"""Hard gate: PR touches a documented subsystem without updating its
doc.

FASE 2 turned this script from soft (label only) into hard (exit 1
on uncovered miss). The escape hatch is an override line in the PR
body, parsed and verified against the canonical mapping at
`docs/policies/docs-map.yml`.

Override format (single line, anywhere in the PR body, repeat once
per doc to skip):

    docs-reviewed: <doc-path> : <reason>

The parser:
  - splits on the first two ":" only, so the reason may contain
    further colons.
  - strips surrounding whitespace from both fields.
  - requires the reason to be non-empty after the strip.

The verifier checks three FACTS (it does not judge the truth of the
reason):
  1. `<doc-path>` exists on disk under the repo root.
  2. `<doc-path>` is exactly the doc the mapping returns for at
     least one of the subsystems the PR touched and that triggered
     the miss. A reviewer cannot smuggle in an override naming an
     unrelated doc.
  3. `<reason>` is not empty.

Exit codes:
  0 - either no misses, or every miss has a valid override.
  1 - at least one miss remains uncovered.

Stdout markers consumed by the CI workflow:
  `needs-docs-review`     present iff there was at least one miss,
                          covered or not.
  `docs-review-skipped`   present iff at least one override fired
                          (so the workflow can apply an audit
                          label for filtering).

# Spec: docs/policies/docs-maintenance.md
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = REPO_ROOT / "docs" / "policies" / "docs-map.yml"

LABEL_NEEDS_REVIEW = "needs-docs-review"
LABEL_REVIEW_SKIPPED = "docs-review-skipped"

# Format: `docs-reviewed: <doc-path> : <reason>`. The doc-path may
# not contain whitespace or `:` (file paths in this repo never do).
# The reason captures everything after the second `:` and is stripped
# at validation time.
OVERRIDE_RE = re.compile(
    r"^\s*docs-reviewed\s*:\s*(\S+?)\s*:\s*(.+?)\s*$",
    re.MULTILINE,
)


def load_map(path: Path = MAP_PATH) -> dict:
    with path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    cfg.setdefault("mapping", [])
    cfg.setdefault("exclude", [])
    return cfg


def resolve(file: str, mapping: list[dict], exclude: list[dict]) -> str | None:
    """Longest-prefix-match resolver. Excludes win first; then the
    most specific mapping prefix wins."""
    for entry in exclude:
        if file.startswith(entry["prefix"]):
            return None
    ordered = sorted(mapping, key=lambda e: -len(e["prefix"]))
    for entry in ordered:
        if file.startswith(entry["prefix"]):
            return entry["doc"]
    return None


# Paths that never trigger the coherence gate even if they fall
# inside a mapped subsystem. Tests and migrations are
# implementation-detail churn: a PR that only touches them does
# not change the subsystem's architecture and so should not force
# a doc update. Keeping them out of the gate matches what
# `scripts/check_spec_paths.py` already does for `migrations/`,
# and avoids banalising the override (every test PR otherwise
# would need `docs-reviewed: ...`).
def _is_implementation_churn(path: str) -> bool:
    """True iff `path` is a test file, a Django migration, or a
    pytest conftest. Such a file is skipped before the resolver
    runs."""
    parts = path.split("/")
    filename = parts[-1] if parts else path
    if "tests" in parts or "migrations" in parts:
        return True
    if filename == "conftest.py":
        return True
    if filename.startswith("test_") and filename.endswith(".py"):
        return True
    if filename.endswith("_test.py"):
        return True
    return False


def find_coupled_misses(
    changed: list[str], mapping: list[dict], exclude: list[dict]
) -> list[tuple[str, str]]:
    """Returns (code_file, missing_doc) pairs in insertion order,
    deduplicated. A "miss" is a code file that resolves to a doc the
    PR does not also touch. Test files, Django migrations and
    `conftest.py` are filtered out before resolution: they are
    implementation churn, not architectural change."""
    docs_touched = {f for f in changed if f.startswith("docs/")}
    seen: set[tuple[str, str]] = set()
    misses: list[tuple[str, str]] = []
    for file in changed:
        if _is_implementation_churn(file):
            continue
        doc = resolve(file, mapping, exclude)
        if doc is None or doc in docs_touched:
            continue
        pair = (file, doc)
        if pair in seen:
            continue
        seen.add(pair)
        misses.append(pair)
    return misses


def parse_overrides(body: str) -> dict[str, str]:
    """Returns {doc_path: reason}. A repeated doc-path keeps the
    last reason (operator can edit the line and the diff is one
    instance)."""
    if not body:
        return {}
    out: dict[str, str] = {}
    for match in OVERRIDE_RE.finditer(body):
        doc_path = match.group(1)
        reason = match.group(2).strip()
        if reason:  # empty reason fails validation later; ignore here
            out[doc_path] = reason
    return out


def validate_overrides(
    misses: list[tuple[str, str]],
    overrides: dict[str, str],
    repo_root: Path = REPO_ROOT,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[str]]:
    """Returns (remaining_misses, accepted_overrides, errors).

    `accepted_overrides` is the list of (doc_path, reason) tuples that
    successfully covered at least one miss. `errors` lists override
    lines that named a doc that does not match a miss or does not
    exist on disk."""
    expected_docs = {doc for _, doc in misses}
    accepted: list[tuple[str, str]] = []
    errors: list[str] = []

    for doc_path, reason in overrides.items():
        if doc_path not in expected_docs:
            errors.append(
                f"docs-reviewed: {doc_path} does not match any doc "
                f"the PR triggered. Expected one of: "
                f"{sorted(expected_docs) or 'none'}."
            )
            continue
        if not (repo_root / doc_path).is_file():
            errors.append(f"docs-reviewed: {doc_path} does not exist on disk.")
            continue
        accepted.append((doc_path, reason))

    covered_docs = {doc for doc, _ in accepted}
    remaining = [m for m in misses if m[1] not in covered_docs]
    return remaining, accepted, errors


def main() -> int:
    changed = [line.strip() for line in sys.stdin if line.strip()]
    body = os.environ.get("PR_BODY", "")
    cfg = load_map()

    misses = find_coupled_misses(changed, cfg["mapping"], cfg["exclude"])
    if not misses:
        print("No subsystem/doc coupling triggers detected.")
        return 0

    print(LABEL_NEEDS_REVIEW)
    overrides = parse_overrides(body)
    remaining, accepted, errors = validate_overrides(misses, overrides)

    for doc_path, reason in accepted:
        print(f"  override accepted: {doc_path}  reason: {reason}")
    for err in errors:
        print(f"  override rejected: {err}")
    if accepted:
        print(LABEL_REVIEW_SKIPPED)

    if remaining:
        print("::error ::Docs gate (coherence) failed. Each subsystem")
        print("::error ::below needs either a doc update in this PR")
        print("::error ::or a `docs-reviewed: <doc> : <reason>` line")
        print("::error ::in the PR body.")
        for file, doc in remaining:
            print(f"  {file}  ->  {doc}  (no doc update, no override)")
        return 1

    print(f"All {len(misses)} miss(es) covered by override lines in the " f"PR body.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
