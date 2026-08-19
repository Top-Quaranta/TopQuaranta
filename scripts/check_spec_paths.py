#!/usr/bin/env python3
"""Validate `# Spec: docs/<path>.md` backlinks in Python modules.

Every line of the form `# Spec: docs/<path>.md` (with optional `:` and
fragment) found in a Python source file under the repo root must point
to a real file on disk. Renaming a doc without updating its spec
backlinks is a commit-time error, not a runtime discovery.

Used both by the pre-commit hook (id: check-spec-paths) and the CI
workflow (.github/workflows/ci-docs.yml). Exits 0 when everything
resolves; exits 1 with a list of misses otherwise.

See `docs/policies/conventions.md` Rule 1.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The pattern matches lines like:
#   # Spec: docs/architecture/social.md
#   # Spec: docs/policies/conventions.md#migrations
# Both `#` and `#:` are accepted in front of "Spec". Anchors (the
# `#anchor` suffix) are stripped before resolution.
# Path body must not contain `<` (placeholder syntax in docstrings) so
# the script's own example lines don't trip its own check.
SPEC_RE = re.compile(r"#\s*Spec:\s*(docs/[^\s#`<>]+\.md)(?:#[^\s`]*)?")

# Where to look. We scan everything tracked, except virtualenvs,
# node_modules, build outputs, and migrations (migrations are
# auto-generated; spec lines there would be noise).
SKIP_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "__pycache__",
    "migrations",
}


def python_files(root: Path):
    for p in root.rglob("*.py"):
        if any(part in SKIP_DIR_PARTS for part in p.parts):
            continue
        yield p


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    misses: list[tuple[Path, int, str]] = []
    seen = 0
    for src in python_files(root):
        try:
            text = src.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = SPEC_RE.search(line)
            if not m:
                continue
            seen += 1
            target = root / m.group(1)
            if not target.is_file():
                misses.append((src.relative_to(root), lineno, m.group(1)))

    if misses:
        print("# Spec: backlinks pointing at missing docs:", file=sys.stderr)
        for src, lineno, target in misses:
            print(f"  {src}:{lineno}  →  {target}  (file not found)", file=sys.stderr)
        print(
            f"\n{len(misses)} broken backlink(s); see "
            f"docs/policies/conventions.md Rule 1.",
            file=sys.stderr,
        )
        return 1

    print(f"check-spec-paths: {seen} backlink(s) validated, all resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
