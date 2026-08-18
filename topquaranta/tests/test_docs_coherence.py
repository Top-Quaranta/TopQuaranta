"""Behaviour pins for `scripts/check_docs_coherence.py`.

FASE 2 turned the gate from soft (label-only) into hard (exit !=0
on uncovered miss). The PR body can carry one or more
`docs-reviewed: <doc> : <reason>` override lines; the verifier
checks that the named doc exists on disk and matches a doc the
mapping resolved for one of the touched subsystems.
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


# ---------------------------------------------------------------------
# Mapping sanity
# ---------------------------------------------------------------------


def test_yaml_loads_and_has_expected_keys(cfg):
    assert "mapping" in cfg
    assert "exclude" in cfg
    assert cfg["mapping"], "mapping must not be empty"
    for entry in cfg["mapping"]:
        assert "prefix" in entry and "doc" in entry


def test_all_mapped_docs_exist_on_disk(cfg):
    missing = [
        entry["doc"]
        for entry in cfg["mapping"]
        if not (REPO_ROOT / entry["doc"]).is_file()
    ]
    assert not missing, f"docs-map.yml points at missing files: {missing}"


# ---------------------------------------------------------------------
# Resolver: longest-prefix-match + exclude semantics
# ---------------------------------------------------------------------


# Synthetic mapping for the resolver-semantics tests below: what is
# pinned is HOW `resolve()` picks (longest prefix, prefix-not-substring,
# dir-or-file prefix), not which live doc a given path lands on today.
_GENERIC = "docs/GENERIC.md"
_SPECIFIC = "docs/SPECIFIC.md"
_SYNTH_MAPPING = [
    {"prefix": "ingesta/", "doc": _GENERIC},
    {"prefix": "ingesta/clients/spotify.py", "doc": _SPECIFIC},
    {"prefix": "spotify.py", "doc": "docs/NEVER.md"},  # substring bait
]


def test_longest_prefix_wins_for_spotify(script):
    # Property asserted: the most specific (longest) matching prefix wins
    # regardless of the order entries appear in the mapping.
    path = "ingesta/clients/spotify.py"
    assert script.resolve(path, _SYNTH_MAPPING, []) == _SPECIFIC
    assert script.resolve(path, list(reversed(_SYNTH_MAPPING)), []) == _SPECIFIC


def test_enriquir_spotify_resolves_to_pipeline(script):
    # Property asserted: matching is by PREFIX, not substring — a path
    # that merely contains "spotify" falls back to its directory's doc,
    # and a bare-filename entry never matches mid-path.
    doc = script.resolve(
        "ingesta/management/commands/enriquir_spotify.py", _SYNTH_MAPPING, []
    )
    assert doc == _GENERIC


def test_excluded_prefix_returns_none(script, cfg):
    doc = script.resolve("scripts/some_ad_hoc.py", cfg["mapping"], cfg["exclude"])
    assert doc is None


def test_unmapped_path_returns_none(script, cfg):
    doc = script.resolve("README.md", cfg["mapping"], cfg["exclude"])
    assert doc is None


def test_web_seo_matches_both_dir_and_hypothetical_file(script):
    # Property asserted: a prefix without a trailing slash covers both the
    # directory `web/seo/<file>` and a same-named module `web/seo.py`,
    # and beats the generic `web/` entry for both.
    mapping = [
        {"prefix": "web/", "doc": _GENERIC},
        {"prefix": "web/seo", "doc": _SPECIFIC},
    ]
    assert script.resolve("web/seo/meta.py", mapping, []) == _SPECIFIC
    assert script.resolve("web/seo.py", mapping, []) == _SPECIFIC
    assert script.resolve("web/feeds.py", mapping, []) == _GENERIC


# ---------------------------------------------------------------------
# Miss detection
# ---------------------------------------------------------------------


def test_miss_flagged_when_code_changes_without_doc(script, cfg):
    misses = script.find_coupled_misses(
        ["social/captions.py", "music/models.py"],
        cfg["mapping"],
        cfg["exclude"],
    )
    docs = {d for _, d in misses}
    assert "docs/architecture/social.md" in docs
    assert "docs/architecture/models.md" in docs


def test_no_miss_when_doc_is_also_in_diff(script, cfg):
    misses = script.find_coupled_misses(
        ["social/captions.py", "docs/architecture/social.md"],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == []


def test_excluded_path_does_not_trigger(script, cfg):
    misses = script.find_coupled_misses(
        ["scripts/dump_something.py", "vendor/mm-design/tokens.css"],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == []


# ---------------------------------------------------------------------
# Implementation-churn filter: tests + migrations + conftest do not
# trip the coherence gate. A PR that only touches them must not
# require a docs override.
# ---------------------------------------------------------------------


def test_test_file_under_mapped_subsystem_is_not_a_miss(script, cfg):
    """`social/tests/test_x.py` lives under social/ (mapped to
    social.md) but is implementation churn, not architecture."""
    misses = script.find_coupled_misses(
        ["social/tests/test_renderer.py"],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == []


def test_django_migration_under_mapped_subsystem_is_not_a_miss(script, cfg):
    """`music/migrations/0099_foo.py` is autogenerated; no doc update
    should be required."""
    misses = script.find_coupled_misses(
        ["music/migrations/0099_add_field.py"],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == []


def test_topquaranta_tests_only_is_not_a_miss(script, cfg):
    """The case that broke PR #82: this whole repo's docs-gate test
    suite lives under `topquaranta/tests/`, mapped to infra.md, but
    is pure test work."""
    misses = script.find_coupled_misses(
        [
            "topquaranta/tests/test_docs_coherence.py",
            "topquaranta/tests/test_docs_novelty.py",
            "topquaranta/tests/test_docs_size.py",
        ],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == []


def test_source_code_under_mapped_subsystem_still_triggers(script, cfg):
    """The positive case must not regress: changing real source code
    of a mapped subsystem still requires the doc to move."""
    misses = script.find_coupled_misses(
        ["social/captions.py"],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == [("social/captions.py", "docs/architecture/social.md")]


def test_mixed_diff_only_keeps_real_source_misses(script, cfg):
    """Source + tests together: only the source counts."""
    misses = script.find_coupled_misses(
        [
            "social/captions.py",
            "social/tests/test_captions.py",
            "music/migrations/0099_add.py",
        ],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == [("social/captions.py", "docs/architecture/social.md")]


def test_is_implementation_churn_unit(script):
    """Pin the predicate directly so the filename rules stay
    explicit (any pytest-discovery edge case shows here, not in a
    failing end-to-end test)."""
    assert script._is_implementation_churn("music/tests/test_x.py")
    assert script._is_implementation_churn("music/migrations/0001_x.py")
    assert script._is_implementation_churn("music/conftest.py")
    assert script._is_implementation_churn("music/tests_helpers/test_y.py")
    assert script._is_implementation_churn("test_top_level.py")
    assert script._is_implementation_churn("music/factory_test.py")
    # Dependency manifests/lockfiles (2026-07-13): version bumps are
    # churn — dependabot PRs must not need a docs override.
    assert script._is_implementation_churn("web-react/package.json")
    assert script._is_implementation_churn("web-react/package-lock.json")
    assert script._is_implementation_churn("requirements.txt")
    assert script._is_implementation_churn("requirements-dev.txt")
    # negatives: real source under a mapped subsystem must NOT match
    assert not script._is_implementation_churn("music/models.py")
    assert not script._is_implementation_churn("music/ml.py")
    assert not script._is_implementation_churn("social/captions.py")
    # `testimoni.py` is not a test file. Filename rule requires
    # `test_` prefix or `_test.py` suffix.
    assert not script._is_implementation_churn("music/testimoni.py")
    assert not script._is_implementation_churn("web-react/vite.config.js")


def test_dependabot_lockfile_bump_is_not_a_miss(script, cfg):
    """A dependabot bump under web-react/ (package.json +
    package-lock.json only) must not trip the gate — dependabot
    cannot add a `docs-reviewed:` override to its own PRs."""
    misses = script.find_coupled_misses(
        ["web-react/package.json", "web-react/package-lock.json"],
        cfg["mapping"],
        cfg["exclude"],
    )
    assert misses == []


# ---------------------------------------------------------------------
# Override parser
# ---------------------------------------------------------------------


def test_parse_overrides_extracts_single_line(script):
    body = (
        "## Summary\n"
        "Refactor.\n\n"
        "docs-reviewed: docs/architecture/social.md : "
        "internal refactor, no conceptual change\n"
    )
    overrides = script.parse_overrides(body)
    assert overrides == {
        "docs/architecture/social.md": ("internal refactor, no conceptual change")
    }


def test_parse_overrides_handles_multiple_lines(script):
    body = (
        "docs-reviewed: docs/architecture/social.md : x\n"
        "docs-reviewed: docs/architecture/models.md : y\n"
    )
    assert script.parse_overrides(body) == {
        "docs/architecture/social.md": "x",
        "docs/architecture/models.md": "y",
    }


def test_parse_overrides_allows_colon_in_reason(script):
    body = (
        "docs-reviewed: docs/architecture/social.md : "
        "see ADR 0008: detectors expanded\n"
    )
    assert script.parse_overrides(body) == {
        "docs/architecture/social.md": "see ADR 0008: detectors expanded"
    }


def test_parse_overrides_drops_empty_reason(script):
    body = "docs-reviewed: docs/architecture/social.md :   \n"
    assert script.parse_overrides(body) == {}


def test_parse_overrides_returns_empty_on_no_body(script):
    assert script.parse_overrides("") == {}
    assert script.parse_overrides(None) == {}


# ---------------------------------------------------------------------
# Override validator (does what the CI gate enforces)
# ---------------------------------------------------------------------


def test_override_covers_miss_when_doc_matches_and_exists(script):
    misses = [("social/captions.py", "docs/architecture/social.md")]
    overrides = {"docs/architecture/social.md": "refactor intern, no conceptual"}
    remaining, accepted, errors = script.validate_overrides(misses, overrides)
    assert remaining == []
    assert accepted == [
        (
            "docs/architecture/social.md",
            "refactor intern, no conceptual",
        )
    ]
    assert errors == []


def test_override_rejected_when_doc_does_not_match_any_miss(script):
    misses = [("social/captions.py", "docs/architecture/social.md")]
    overrides = {"docs/architecture/models.md": "wrong doc, this is models not social"}
    remaining, accepted, errors = script.validate_overrides(misses, overrides)
    assert remaining == misses  # still uncovered
    assert accepted == []
    assert errors and "does not match any doc" in errors[0]


def test_override_rejected_when_doc_does_not_exist_on_disk(script, tmp_path):
    misses = [("social/captions.py", "docs/architecture/social.md")]
    overrides = {"docs/architecture/social.md": "valid reason"}
    # Pretend the repo root has no such file.
    remaining, accepted, errors = script.validate_overrides(
        misses, overrides, repo_root=tmp_path
    )
    assert remaining == misses
    assert accepted == []
    assert errors and "does not exist on disk" in errors[0]


def test_override_partial_coverage_leaves_uncovered_misses(script):
    misses = [
        ("social/captions.py", "docs/architecture/social.md"),
        ("music/models.py", "docs/architecture/models.md"),
    ]
    overrides = {"docs/architecture/social.md": "covered"}
    remaining, accepted, errors = script.validate_overrides(misses, overrides)
    assert remaining == [("music/models.py", "docs/architecture/models.md")]
    assert accepted == [("docs/architecture/social.md", "covered")]
    assert errors == []


# ---------------------------------------------------------------------
# End-to-end: stdin + PR_BODY through main()
# ---------------------------------------------------------------------


def _run_main(script, monkeypatch, changed_files: list[str], body: str) -> int:
    """Drive the script's main() with synthetic stdin + body."""
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(changed_files) + "\n"))
    monkeypatch.setenv("PR_BODY", body)
    return script.main()


def test_main_passes_when_no_misses(script, monkeypatch, capsys):
    rc = _run_main(
        script,
        monkeypatch,
        ["docs/README.md", "MANIFEST.md"],
        "",
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "No subsystem/doc coupling" in out


def test_main_fails_on_miss_without_override(script, monkeypatch, capsys):
    rc = _run_main(script, monkeypatch, ["social/captions.py"], "Summary line.")
    out = capsys.readouterr().out
    assert rc == 1
    assert "needs-docs-review" in out
    assert "docs-review-skipped" not in out
    assert "no doc update, no override" in out


def test_main_passes_with_valid_override(script, monkeypatch, capsys):
    body = (
        "docs-reviewed: docs/architecture/social.md : "
        "internal refactor, no conceptual change\n"
    )
    rc = _run_main(script, monkeypatch, ["social/captions.py"], body)
    out = capsys.readouterr().out
    assert rc == 0
    assert "needs-docs-review" in out
    assert "docs-review-skipped" in out
    assert "override accepted" in out
