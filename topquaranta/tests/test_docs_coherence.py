"""Behaviour pin for `scripts/check_docs_coherence.py`.

FASE 1 of the docs gates centralises the prefix-to-doc mapping in
`docs/policies/docs-map.yml` and moves the docs-coherence logic from
a hardcoded bash array into this Python script. The behaviour MUST
stay identical to the bash version: soft signal only, label on
miss, no exit-code change. These tests pin that contract so a later
sprint cannot accidentally turn the check into a hard gate without
the diff explicitly saying so.
"""

# Spec: docs/policies/docs-maintenance.md

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_docs_coherence.py"


def _load_script_module():
    """Import the script as a module without requiring `scripts/`
    to be on the Python path. The script is callable as a CLI and
    as a library; tests use the library API."""
    spec = importlib.util.spec_from_file_location("check_docs_coherence", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_docs_coherence"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def script():
    return _load_script_module()


@pytest.fixture(scope="module")
def cfg(script):
    return script.load_map()


def test_yaml_loads_and_has_expected_keys(cfg):
    """Sanity: the canonical map exists and parses; the top-level
    shape is what the resolver expects."""
    assert "mapping" in cfg
    assert "exclude" in cfg
    assert cfg["mapping"], "mapping must not be empty"
    for entry in cfg["mapping"]:
        assert "prefix" in entry and "doc" in entry


def test_all_mapped_docs_exist_on_disk(cfg):
    """Every doc referenced by the mapping must point to a real
    file. A rename in `docs/` without updating `docs-map.yml` is a
    silent regression and must fail CI."""
    missing = [
        entry["doc"]
        for entry in cfg["mapping"]
        if not (REPO_ROOT / entry["doc"]).is_file()
    ]
    assert not missing, f"docs-map.yml points at missing files: {missing}"


def test_longest_prefix_wins_for_spotify(script, cfg):
    """The whole point of granular paths under `ingesta/`: a Spotify
    client file must resolve to `playlists.md`, not the generic
    `pipeline.md`."""
    doc = script.resolve(
        "ingesta/clients/spotify.py",
        cfg["mapping"],
        cfg["exclude"],
    )
    assert doc == "docs/architecture/playlists.md"


def test_generic_ingesta_falls_back_to_pipeline(script, cfg):
    """A non-Spotify ingesta file must still hit the broader doc."""
    doc = script.resolve(
        "ingesta/clients/lastfm.py",
        cfg["mapping"],
        cfg["exclude"],
    )
    assert doc == "docs/architecture/pipeline.md"


def test_excluded_prefix_returns_none(script, cfg):
    """Excluded prefixes never resolve to a doc, even if a later
    mapping entry would match. `scripts/` is the canonical example."""
    doc = script.resolve(
        "scripts/some_ad_hoc.py",
        cfg["mapping"],
        cfg["exclude"],
    )
    assert doc is None


def test_unmapped_path_returns_none(script, cfg):
    """A path that matches no mapping entry returns None (no label,
    no warning)."""
    doc = script.resolve(
        "README.md",
        cfg["mapping"],
        cfg["exclude"],
    )
    assert doc is None


def test_miss_flagged_when_code_changes_without_doc(script, cfg):
    """The canonical soft-signal case: PR touches `social/foo.py`,
    not `docs/architecture/social.md`. Must show up as a miss."""
    misses = script.find_coupled_misses(
        ["social/captions.py", "music/models.py"],
        cfg["mapping"],
        cfg["exclude"],
    )
    docs = {d for _, d in misses}
    assert "docs/architecture/social.md" in docs
    assert "docs/architecture/models.md" in docs


def test_no_miss_when_doc_is_also_in_diff(script, cfg):
    """If the PR DOES touch the doc, the corresponding code change
    does not trip the check."""
    misses = script.find_coupled_misses(
        ["social/captions.py", "docs/architecture/social.md"],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == []


def test_excluded_path_does_not_trigger(script, cfg):
    """A PR that touches only excluded paths must produce zero
    misses (`needs-docs-review` would be wrong)."""
    misses = script.find_coupled_misses(
        ["scripts/dump_something.py", "vendor/mm-design/tokens.css"],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == []


def test_web_api_staff_beats_web_api(script, cfg):
    """The mapping has both `web/api/` and `web/api/staff/`. A file
    under staff must resolve to `staff.md`, not `api-versioning.md`."""
    doc = script.resolve(
        "web/api/staff/estat.py",
        cfg["mapping"],
        cfg["exclude"],
    )
    assert doc == "docs/architecture/staff.md"
