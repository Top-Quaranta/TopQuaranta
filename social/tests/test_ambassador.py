"""Guards for the ambassador "has entrat al top" share caption (Fase 2 E)."""

from __future__ import annotations

import re

from social.ambassador import ambassador_top_caption


def test_caption_includes_name_and_url():
    cap = ambassador_top_caption("Manel", "manel")
    assert "Manel" in cap
    assert "/artista/manel" in cap
    assert "TopQuaranta" in cap


def test_caption_weaves_position_when_known():
    assert "1r lloc" in ambassador_top_caption("Manel", "manel", posicio=1)
    assert "5è lloc" in ambassador_top_caption("Manel", "manel", posicio=5)


def test_caption_no_positional_hashtag():
    # Same discipline as the weekly captions: never a "#<digit>" form
    # (audience-leak guard, ADR-0006).
    cap = ambassador_top_caption("Manel", "manel", posicio=3)
    assert not re.search(r"#\d", cap)


def test_caption_without_position_omits_ordinal():
    cap = ambassador_top_caption("Manel", "manel")
    assert "lloc" not in cap
    assert "Manel entra al Top" in cap
