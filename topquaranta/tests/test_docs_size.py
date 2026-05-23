"""Behaviour pins for `scripts/check_docs_size.py`.

Gate 3 of FASE 2: docs inside `size.scope` of docs-map.yml must
stay under `threshold_lines` unless allow-listed.

Tests use synthetic configs + tmp_path repos so they do not depend
on the real repo's current state, plus one real-repo guard.
"""

# Spec: docs/policies/docs-maintenance.md

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_docs_size.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_docs_size", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_docs_size"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def script():
    return _load_script_module()


def _mkdoc(root: Path, rel: str, lines: int) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f"line {i}" for i in range(lines)) + "\n")
    return p


# ---------------------------------------------------------------------
# Synthetic
# ---------------------------------------------------------------------


def _cfg(scope, threshold=400, exempt=None, grandfathered=None):
    return {
        "size": {
            "threshold_lines": threshold,
            "scope": scope,
            "exempt_permanent": [{"path": p, "reason": "x"} for p in (exempt or [])],
            "grandfathered": [
                {"path": p, "reason": "x", "current_lines": 0}
                for p in (grandfathered or [])
            ],
        }
    }


def test_doc_over_threshold_is_flagged(script, tmp_path):
    _mkdoc(tmp_path, "docs/architecture/big.md", 500)
    cfg = _cfg(["docs/architecture/"])
    offenders = script.find_oversize_docs(tmp_path, cfg)
    assert offenders == [("docs/architecture/big.md", 500)]


def test_doc_under_threshold_passes(script, tmp_path):
    _mkdoc(tmp_path, "docs/architecture/small.md", 50)
    cfg = _cfg(["docs/architecture/"])
    assert script.find_oversize_docs(tmp_path, cfg) == []


def test_grandfathered_doc_is_not_flagged_even_if_over(script, tmp_path):
    _mkdoc(tmp_path, "docs/architecture/big.md", 500)
    cfg = _cfg(
        ["docs/architecture/"],
        grandfathered=["docs/architecture/big.md"],
    )
    assert script.find_oversize_docs(tmp_path, cfg) == []


def test_exempt_permanent_doc_is_not_flagged_even_if_over(script, tmp_path):
    _mkdoc(tmp_path, "docs/history/roadmap.md", 1500)
    cfg = _cfg(
        ["docs/history/"],
        exempt=["docs/history/roadmap.md"],
    )
    assert script.find_oversize_docs(tmp_path, cfg) == []


def test_doc_outside_scope_is_ignored(script, tmp_path):
    _mkdoc(tmp_path, "docs/post-mortems/big.md", 800)
    cfg = _cfg(["docs/architecture/"])
    assert script.find_oversize_docs(tmp_path, cfg) == []


def test_multiple_offenders_are_all_returned(script, tmp_path):
    _mkdoc(tmp_path, "docs/architecture/a.md", 500)
    _mkdoc(tmp_path, "docs/ops/b.md", 600)
    cfg = _cfg(["docs/architecture/", "docs/ops/"])
    offenders = script.find_oversize_docs(tmp_path, cfg)
    assert sorted(offenders) == [
        ("docs/architecture/a.md", 500),
        ("docs/ops/b.md", 600),
    ]


def test_empty_size_block_disables_check(script, tmp_path):
    _mkdoc(tmp_path, "docs/architecture/big.md", 500)
    assert script.find_oversize_docs(tmp_path, {}) == []
    assert script.find_oversize_docs(tmp_path, {"size": {}}) == []


def test_at_threshold_exactly_passes(script, tmp_path):
    """`> threshold`, not `>=`, so a doc at exactly the line count
    passes. Documenting via test to lock the semantics."""
    _mkdoc(tmp_path, "docs/architecture/edge.md", 400)
    cfg = _cfg(["docs/architecture/"], threshold=400)
    assert script.find_oversize_docs(tmp_path, cfg) == []


# ---------------------------------------------------------------------
# Real-repo guard: the current state must pass.
# ---------------------------------------------------------------------


def test_current_repo_state_respects_size_threshold(script):
    cfg = __import__("check_docs_size").load_map()
    offenders = script.find_oversize_docs(REPO_ROOT, cfg)
    assert offenders == [], (
        f"Docs over the size threshold not in allow-list: {offenders}. "
        "Either split per docs-maintenance.md Rule 3, or add to "
        "size.grandfathered."
    )
