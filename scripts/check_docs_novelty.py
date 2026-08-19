#!/usr/bin/env python3
"""Hard gate: a top-level code directory exists that is neither
mapped nor explicitly excluded in `docs/policies/docs-map.yml`.

The intent is to catch the case where a new Django app, a new
clients/ tree, or any new top-level Python package is introduced
without anyone deciding whether it deserves an architecture doc.
The fix is one of:

  - add the new top-level to `mapping:` pointing at its doc, OR
  - add it to `exclude:` with a `reason` explaining why no doc is
    needed (graveyard, vendored, etc.).

Definition of "top-level code directory":
  - lives at the repo root,
  - is a directory (root files are ignored),
  - is not hidden (`.git`, `.github`, `.claude`, ...),
  - is not in the static skip-list of build/cache directories
    (`node_modules`, `.venv`, `dist`, ...),
  - is not gitignored (a local artefact isn't a subsystem),
  - either contains an `apps.py` at the top (Django app marker) OR
    contains at least one `*.py` anywhere recursively (Python
    package).

A top-level X is "covered" iff there is at least one entry in
`mapping` or `exclude` whose `prefix` either equals `X` or starts
with `X` + `/`. This matches both flat entries like `social/` and
fine-grained ones like `ingesta/clients/spotify.py`.

Exit codes:
  0 - every top-level code directory is mapped or excluded.
  1 - at least one is uncovered; the message lists which.

# Spec: docs/policies/conventions.md
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = REPO_ROOT / "docs" / "policies" / "docs-map.yml"

# Directories that look like code but are not first-class subsystems
# of this repo. The hidden-prefix rule (`.`) takes care of `.git`,
# `.github`, `.claude`, etc.; this list catches build artefacts and
# tool caches that may live without a leading dot.
SKIP_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "staticfiles",
    }
)


def load_map(path: Path = MAP_PATH) -> dict:
    with path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    cfg.setdefault("mapping", [])
    cfg.setdefault("exclude", [])
    return cfg


def is_code_dir(path: Path) -> bool:
    """Returns True iff the directory looks like code we should
    require coverage for. Django app marker takes precedence (the
    sentinel is cheap); otherwise any *.py file in the tree wins."""
    if (path / "apps.py").is_file():
        return True
    for _ in path.rglob("*.py"):
        return True
    return False


def is_covered(topdir: str, entries: list[dict]) -> bool:
    """A top-level is covered if any mapping/exclude prefix starts
    with `<topdir>/` or equals `<topdir>`. `<topdir>` alone (no
    slash) is accepted for symmetry with the `web/seo` style entry."""
    needle_slash = topdir + "/"
    for entry in entries:
        prefix = entry["prefix"]
        if prefix == topdir or prefix.startswith(needle_slash):
            return True
    return False


def gitignored(repo_root: Path, names: list[str]) -> set[str]:
    """Of `names`, the ones git is told to ignore.

    A gitignored directory is not part of the repo, so it cannot be a
    subsystem that needs a doc: it's a local artefact (a downloaded DYI
    export, a scratch tree). CI checks out a clean tree and never sees
    them, so without this filter the gate goes red *only* on the
    operator's laptop — which is exactly how a hard gate gets trained
    into background noise. No git available (a tarball, a sandbox) →
    empty set, i.e. the old stricter behaviour.
    """
    if not names:
        return set()
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "--stdin"],
            cwd=repo_root,
            input="\n".join(names),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    # 0 = at least one ignored, 1 = none ignored. Anything else (128 =
    # not a git repo) means we can't tell, so we don't filter.
    if proc.returncode not in (0, 1):
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def find_uncovered_code_dirs(
    repo_root: Path, mapping: list[dict], exclude: list[dict]
) -> list[str]:
    entries = mapping + exclude
    candidates = [
        child.name
        for child in sorted(repo_root.iterdir(), key=lambda p: p.name)
        if child.is_dir()
        and not child.name.startswith(".")
        and child.name not in SKIP_DIRS
    ]
    # Filtered before `is_code_dir`, which recurses: no point walking a
    # directory git has already told us isn't ours.
    ignored = gitignored(repo_root, candidates)
    return [
        name
        for name in candidates
        if name not in ignored
        and is_code_dir(repo_root / name)
        and not is_covered(name, entries)
    ]


def main(repo_root: Path = REPO_ROOT) -> int:
    cfg = load_map()
    uncovered = find_uncovered_code_dirs(repo_root, cfg["mapping"], cfg["exclude"])
    if uncovered:
        print(
            "::error ::Docs gate (novelty) failed. Top-level code "
            "directories without a mapping or exclude entry in "
            "docs/policies/docs-map.yml:"
        )
        for name in uncovered:
            print(f"  {name}/")
        print(
            "Add each to docs/policies/docs-map.yml under `mapping:` "
            "with its doc, or under `exclude:` with a `reason:` field."
        )
        return 1
    print("All top-level code directories are covered by docs-map.yml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
