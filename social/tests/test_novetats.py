"""Novetats narrative engine (audit #5, PR β). Pure-stdlib.

Run in isolation with
    python3 -m pytest social/tests/test_novetats.py -q -c /dev/null
"""

from __future__ import annotations

import datetime
import random

from social.narrative import novetats as nov
from social.narrative.banks.novetats import NOVETATS
from social.narrative.composers import nous_albums, nous_singles
from social.narrative.composers import novetats as comp


def _item(nom, aid, artista, **flags):
    base = {
        "nom": nom,
        "tipus": flags.pop("tipus", "single"),
        "artista_id": aid,
        "artista_nom": artista,
        "artista_instagram_url": flags.pop("ig", None),
        "dies": flags.pop("dies", 3),
        "segell": flags.pop("segell", ""),
        "artista_en_top": False,
        "primer_release": False,
        "te_collab": False,
        "segell_compartit": False,
    }
    base.update(flags)
    return base


# ── detectors ────────────────────────────────────────────────────────


def test_n1_fires_for_known_artist():
    items = [_item("X", 1, "A", artista_en_top=True)]
    scs = nov.detect_novetats(items)
    codes = [s.code for s in scs]
    assert "n1_debut_artist_known" in codes
    assert scs[0].code == "n1_debut_artist_known"  # highest severity


def test_n2_fires_for_first_release():
    items = [_item("X", 1, "A", primer_release=True)]
    assert any(s.code == "n2_first_release" for s in nov.detect_novetats(items))


def test_n3_fires_for_collaboration():
    items = [_item("X", 1, "A", te_collab=True)]
    assert any(s.code == "n3_collaboration" for s in nov.detect_novetats(items))


def test_n4_fires_for_shared_label():
    items = [_item("X", 1, "A", segell="Halley", segell_compartit=True)]
    assert any(s.code == "n4_label_release" for s in nov.detect_novetats(items))


def test_fallback_always_present():
    items = [_item("X", 1, "A")]  # no flags
    scs = nov.detect_novetats(items)
    assert scs and scs[-1].code == "fallback_novetat"


# ── composer ─────────────────────────────────────────────────────────

WK = datetime.date(2026, 5, 25)


def test_composer_is_narrative_not_skeleton():
    items = [
        _item("Backstage", 1, "Llum", artista_en_top=True, dies=2, tipus="album"),
        _item("Primer", 2, "Nova Veu", primer_release=True, dies=1),
    ]
    r = comp.compose(
        "instagram_feed", "nous_albums", items, setmana=WK, rng=random.Random(0)
    )
    txt = r["text"]
    # Editorial context, not the legacy "Nous àlbums · Setmana N / · …".
    assert "Setmana" not in txt.split("\n")[0]
    assert "Llum" in txt and "Nova Veu" in txt
    assert r["hashtags"] == ["#TopQuaranta", "#MúsicaEnCatalà", "#Novetats"]


def test_composer_dedups_by_artist():
    # Same artist triggers n1 + n2 → only one slot for that artist.
    items = [
        _item("A1", 1, "Solo", artista_en_top=True, primer_release=True),
        _item("B1", 2, "Altre", dies=4),
    ]
    r = comp.compose(
        "newsletter", "nous_singles", items, setmana=WK, rng=random.Random(0)
    )
    assert r["text"].count("Solo") <= 2  # named once in a slot, maybe once in list


def test_composer_respects_channel_ceiling():
    items = [_item(f"T{i}", i, f"Art{i}", dies=i + 1) for i in range(8)]
    for ch, cap in [("mastodon", 480), ("bluesky", 280), ("telegram", 900)]:
        r = comp.compose(ch, "nous_albums", items, setmana=WK, rng=random.Random(2))
        assert len(r["text"]) <= cap, (ch, len(r["text"]))


def test_one_dia_agreement_in_novetats():
    items = [_item("X", 1, "A", primer_release=True, dies=1)]
    r = comp.compose(
        "telegram", "nous_singles", items, setmana=WK, rng=random.Random(0)
    )
    assert "1 dia" in r["text"] and "1 dies" not in r["text"]


def test_bank_all_codes_have_three_tiers():
    for code, tiers in NOVETATS.items():
        for tier in ("short", "medium", "long"):
            assert tier in tiers and len(tiers[tier]) >= 2, (code, tier)
