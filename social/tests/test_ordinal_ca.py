"""ADR-0006 — Catalan ordinal helper."""

from __future__ import annotations

import pytest

from social.narrative.utils import ordinal_ca


def test_ordinal_ca_1_to_10():
    assert ordinal_ca(1) == "1r"
    assert ordinal_ca(2) == "2n"
    assert ordinal_ca(3) == "3r"
    assert ordinal_ca(4) == "4t"
    assert ordinal_ca(5) == "5è"
    assert ordinal_ca(6) == "6è"
    assert ordinal_ca(7) == "7è"
    assert ordinal_ca(8) == "8è"
    assert ordinal_ca(9) == "9è"
    assert ordinal_ca(10) == "10è"


def test_ordinal_ca_above_10():
    # Suffix stays "è" regardless of units digit (IEC orthography).
    assert ordinal_ca(11) == "11è"
    assert ordinal_ca(12) == "12è"
    assert ordinal_ca(21) == "21è"
    assert ordinal_ca(33) == "33è"
    assert ordinal_ca(40) == "40è"
    assert ordinal_ca(99) == "99è"


def test_ordinal_ca_zero_and_negative_raise():
    with pytest.raises(ValueError):
        ordinal_ca(0)
    with pytest.raises(ValueError):
        ordinal_ca(-1)
