# Spec: docs/architecture/social.md
"""Verified-recent-release fact for the narrative engine.

Computes a single boolean — *is this `Canço` a verified recent release* —
by combining `data_llancament` recency with a plausibility check that the
stored release date is not obviously a reissue / alternate-version date.

Motivation (2026-06-05 measurement, `mesura-capa2-3`): `data_llancament`
is the Deezer/MusicBrainz release date we hold, which for catalogue is
frequently the **reissue** date, not the original studio release. The
`age_factor` in `ranking/algorisme.py` therefore treats a reissued 1971
song as fresh, and the narrative freshness beats (a4/a6) inherit that.
This module isolates a conservative "we have no reason to doubt this is a
genuinely new release" fact so a future, product-decided wiring can gate
freshness phrasing on it.

SCAFFOLDING ONLY: this fact is computed and exposed but **not consumed**
by any caption template or detector yet. Wiring it into the composer is
a pending editorial decision and deliberately out of scope here.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

# Title markers that flag a non-original recording (live / remix /
# remaster / reissue / acoustic / generic "version"). Catalan, Spanish
# and English surface forms — matched case-insensitively against the
# track title. This mirrors the title heuristic used in the 2a
# measurement; it is intentionally conservative (a marked title is
# strong evidence the recording is not a fresh original).
_VERSION_MARKER = re.compile(
    r"\b("
    r"live|en directe|directo|en viu|"
    r"remix|remaster|remasteritza(?:t|da)|remasteriza(?:do|da)|"
    r"ac[uú]stic[ao]?|unplugged|"
    r"reissue|reedici[oó]|versi[oó]|edici[oó]"
    r")\b",
    re.IGNORECASE,
)

# A release dated within this many days of the reference date is "recent"
# enough to be a candidate for a freshness claim. Matches a6's 30-day
# window so the two notions stay aligned if wired together later.
DEFAULT_MAX_AGE_DAYS = 30


@dataclass(frozen=True)
class FreshnessVerdict:
    """Result of `assess_recent_release`.

    `is_verified_recent_release` is the headline fact. `age_days` is the
    release age at `ref_date` (None when `data_llancament` is unknown;
    clamped to 0 for not-yet/just-released dates). `reasons` lists the
    checks that FAILED — empty when the verdict is True."""

    is_verified_recent_release: bool
    age_days: int | None
    reasons: tuple[str, ...]


def assess_recent_release(
    canco,
    *,
    ref_date: datetime.date,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> FreshnessVerdict:
    """Assess whether `canco` is a *verified* recent release at `ref_date`.

    A release is verified-recent when ALL hold:
      1. `data_llancament` is known and within `max_age_days` of
         `ref_date` (future / same-day dates count as age 0).
      2. The title carries no version marker (live / remix / remaster /
         reissue / acoustic / version).
      3. The artist was not deceased before the release date — a release
         dated after `Artista.mb_end_date` is a posthumous reissue, not a
         new release.

    Pure function: reads `canco` (+ its related `artista`) and never
    writes. Designed to be called against stored `TopSetmanal` rows
    read-only as well as in the live pipeline."""
    reasons: list[str] = []

    dl: datetime.date | None = getattr(canco, "data_llancament", None)
    if dl is None:
        return FreshnessVerdict(False, None, ("no_release_date",))

    age_days = (ref_date - dl).days
    if age_days < 0:
        age_days = 0  # not-yet / just-released → maximally fresh
    if age_days > max_age_days:
        reasons.append("older_than_window")

    if _VERSION_MARKER.search(canco.nom or ""):
        reasons.append("version_marker_in_title")

    artista = getattr(canco, "artista", None)
    mb_end = getattr(artista, "mb_end_date", None) if artista else None
    if mb_end is not None and mb_end < dl:
        reasons.append("artist_deceased_before_release")

    return FreshnessVerdict(not reasons, age_days, tuple(reasons))


def is_verified_recent_release(
    canco,
    *,
    ref_date: datetime.date,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> bool:
    """Boolean convenience wrapper over `assess_recent_release`."""
    return assess_recent_release(
        canco, ref_date=ref_date, max_age_days=max_age_days
    ).is_verified_recent_release
