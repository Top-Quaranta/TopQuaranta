"""FASE D — the `reconsiderada=True` flag escapes the rejection
filter inside `_previously_rejected` (both `obtenir_novetats` and
`obtenir_metadata` share the same helper shape).

We exercise the underlying query — no Deezer mock needed because the
helper takes plain `(isrc, deezer_id)` arguments and returns a bool.
"""

from __future__ import annotations

import pytest

from ingesta.management.commands.obtenir_metadata import (
    _previously_rejected as _prev_meta,
)
from ingesta.management.commands.obtenir_novetats import (
    _previously_rejected as _prev_nov,
)
from music.models import HistorialRevisio


@pytest.fixture
def reject(db):
    """Factory for HistorialRevisio rebutjada rows."""

    def _factory(*, isrc="", deezer_id=None, reconsiderada=False, motiu="no_catala"):
        return HistorialRevisio.objects.create(
            canco_nom="x",
            artista_nom="x",
            canco_isrc=isrc,
            canco_deezer_id=deezer_id,
            decisio="rebutjada",
            motiu=motiu,
            reconsiderada=reconsiderada,
        )

    return _factory


# ── obtenir_novetats ─────────────────────────────────────────────


def test_cron_excludes_rejected_by_default(reject):
    """Vanilla rejection (reconsiderada=False) still blocks."""
    reject(isrc="ES12345", deezer_id=111)
    assert _prev_nov(isrc="ES12345", deezer_id=None) is True
    assert _prev_nov(isrc="", deezer_id=111) is True


def test_cron_includes_when_reconsiderada_true(reject):
    """A single reconsiderada=True row opens the track."""
    reject(isrc="ES99999", deezer_id=999, reconsiderada=True)
    assert _prev_nov(isrc="ES99999", deezer_id=None) is False
    assert _prev_nov(isrc="", deezer_id=999) is False


def test_cron_re_excludes_after_second_rejection(reject):
    """A second rejection after reconsideration must re-block.

    Workflow: staff reconsiders an old rebuig → cron re-ingereix
    la cançó → staff la rebutja de nou → es crea un row fresc amb
    reconsiderada=False, que torna a bloquejar el filtre."""
    reject(isrc="EX0001", deezer_id=42, reconsiderada=True)
    # Re-rejected later — fresh row, default reconsiderada=False.
    reject(isrc="EX0001", deezer_id=42, reconsiderada=False)
    assert _prev_nov(isrc="EX0001", deezer_id=None) is True
    assert _prev_nov(isrc="", deezer_id=42) is True


def test_cron_only_matches_by_isrc_or_deezer(reject):
    """The Q is OR-joined; ISRC alone is enough to block."""
    reject(isrc="OR0001", deezer_id=None)
    assert _prev_nov(isrc="OR0001", deezer_id=999) is True
    assert _prev_nov(isrc="OTHER", deezer_id=None) is False


def test_cron_empty_query_returns_false(reject):
    """No ISRC + no deezer_id = early-return False (avoid full table scan)."""
    reject(isrc="X", deezer_id=1)
    assert _prev_nov(isrc="", deezer_id=None) is False


# ── obtenir_metadata (shares the same semantics) ────────────────


def test_metadata_excludes_rejected_by_default(reject):
    reject(isrc="MTA001", deezer_id=200)
    assert _prev_meta(isrc="MTA001", deezer_id=None) is True


def test_metadata_includes_when_reconsiderada_true(reject):
    reject(isrc="MTA002", deezer_id=300, reconsiderada=True)
    assert _prev_meta(isrc="MTA002", deezer_id=300) is False
