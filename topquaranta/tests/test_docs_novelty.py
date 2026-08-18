"""Behaviour pins for `scripts/check_docs_novelty.py`.

Gate 2 of FASE 2: a top-level code directory must be declared in
`docs-map.yml` either under `mapping:` or under `exclude:`.

Tests exercise the resolver on synthetic `tmp_path` repo layouts so
they do not depend on the real repo's current state.
"""

# Spec: docs/policies/docs-maintenance.md

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_docs_novelty.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_docs_novelty", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_docs_novelty"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def script():
    return _load_script_module()


# ---------------------------------------------------------------------
# Helpers to build a tiny synthetic repo
# ---------------------------------------------------------------------


def _mkapp(root: Path, name: str, *, has_apps_py: bool = False) -> Path:
    """Create a top-level dir under root with a `.py` inside (or
    `apps.py` if `has_apps_py`)."""
    d = root / name
    d.mkdir()
    if has_apps_py:
        (d / "apps.py").write_text("# stub\n")
    else:
        (d / "foo.py").write_text("# stub\n")
    return d


def _mkdir_no_py(root: Path, name: str) -> Path:
    d = root / name
    d.mkdir()
    (d / "README.md").write_text("# data\n")
    return d


def _mkroot_file(root: Path, name: str) -> Path:
    p = root / name
    p.write_text("# root file\n")
    return p


# ---------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------


def test_is_code_dir_true_for_dir_with_py(script, tmp_path):
    d = _mkapp(tmp_path, "myapp")
    assert script.is_code_dir(d) is True


def test_is_code_dir_false_for_dir_without_py(script, tmp_path):
    d = _mkdir_no_py(tmp_path, "mydata")
    assert script.is_code_dir(d) is False


def test_is_covered_handles_prefix_with_and_without_slash(script):
    mapping = [{"prefix": "music/", "doc": "x"}]
    assert script.is_covered("music", mapping) is True


def test_is_covered_handles_finegrained_prefix(script):
    # An entry like `ingesta/clients/spotify.py` covers `ingesta`.
    mapping = [
        {"prefix": "ingesta/clients/spotify.py", "doc": "x"},
    ]
    assert script.is_covered("ingesta", mapping) is True


def test_is_covered_false_when_no_prefix_matches(script):
    mapping = [{"prefix": "music/", "doc": "x"}]
    assert script.is_covered("ranking", mapping) is False


def test_is_covered_works_via_exclude_list(script):
    exclude = [{"prefix": "scripts/", "reason": "graveyard"}]
    assert script.is_covered("scripts", exclude) is True


# ---------------------------------------------------------------------
# End-to-end: synthetic repos
# ---------------------------------------------------------------------


def test_uncovered_new_code_dir_is_flagged(script, tmp_path):
    _mkapp(tmp_path, "newapp")
    mapping = [{"prefix": "music/", "doc": "x"}]
    exclude = [{"prefix": "scripts/", "reason": "graveyard"}]
    found = script.find_uncovered_code_dirs(tmp_path, mapping, exclude)
    assert found == ["newapp"]


def test_covered_dir_is_not_flagged(script, tmp_path):
    _mkapp(tmp_path, "newapp")
    mapping = [{"prefix": "newapp/", "doc": "docs/architecture/newapp.md"}]
    found = script.find_uncovered_code_dirs(tmp_path, mapping, [])
    assert found == []


def test_excluded_dir_is_not_flagged(script, tmp_path):
    _mkapp(tmp_path, "newapp")
    exclude = [{"prefix": "newapp/", "reason": "vendored"}]
    found = script.find_uncovered_code_dirs(tmp_path, [], exclude)
    assert found == []


def test_gitignored_dir_is_not_flagged(script, tmp_path):
    """A gitignored tree is a local artefact, not a subsystem.

    Caught 2026-08-10: a downloaded Instagram DYI export sitting at the
    repo root (gitignored, invisible to CI) failed this gate on the
    operator's laptop only — the fastest way to teach everyone that a
    red hard gate means nothing.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _mkapp(tmp_path, "instagram-export-2026-06-15")
    _mkapp(tmp_path, "realapp")
    (tmp_path / ".gitignore").write_text("instagram-*/\n")

    found = script.find_uncovered_code_dirs(tmp_path, [], [])

    assert found == ["realapp"]


def test_uncovered_dir_still_flagged_without_git(script, tmp_path):
    """No git (tarball, sandbox) → we can't tell, so we stay strict."""
    _mkapp(tmp_path, "newapp")
    assert script.find_uncovered_code_dirs(tmp_path, [], []) == ["newapp"]


def test_root_file_is_not_flagged(script, tmp_path):
    _mkroot_file(tmp_path, "README.md")
    _mkroot_file(tmp_path, "CONFIG.toml")
    found = script.find_uncovered_code_dirs(tmp_path, [], [])
    assert found == []


def test_hidden_dir_is_skipped(script, tmp_path):
    d = tmp_path / ".github"
    d.mkdir()
    (d / "workflows.py").write_text("# stub\n")
    found = script.find_uncovered_code_dirs(tmp_path, [], [])
    assert found == []


def test_skiplist_dir_is_skipped(script, tmp_path):
    d = tmp_path / "node_modules"
    d.mkdir()
    (d / "some_pkg.py").write_text("# stub\n")
    d2 = tmp_path / "__pycache__"
    d2.mkdir()
    (d2 / "x.py").write_text("# stub\n")
    found = script.find_uncovered_code_dirs(tmp_path, [], [])
    assert found == []


# ---------------------------------------------------------------------
# Real-repo guard: the current state must pass.
# ---------------------------------------------------------------------


def test_current_repo_state_is_fully_covered(script):
    cfg = __import__("check_docs_novelty").load_map()
    found = script.find_uncovered_code_dirs(REPO_ROOT, cfg["mapping"], cfg["exclude"])
    assert found == [], (
        f"Top-level code dirs not in docs-map.yml: {found}. "
        "Add them to mapping: or exclude: before merging."
    )
