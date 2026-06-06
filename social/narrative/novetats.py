"""Novetats detectors (audit #5, 2026-06-01).

# Spec: docs/architecture/social-narrative.md

Parallel to `scenarios.py` (the top detectors) but for the weekly
new-release roundups. Each detector scans the enriched `items` list
from `payload.build_novetats` (no DB access here — the flags are
batch-computed upstream in `payload._novetats_flags`) and returns at
most one `Scenario`, the strongest case of its kind. `detect_novetats`
collects them sorted by severity desc, so the composer picks the
headline release first and dedups by artist via `scenarios.select_slots`.

Implemented detectors and triggers:
  * n1_debut_artist_known — release by an artist already in the recent
    top (`artista_en_top`). Severity 6.
  * n2_first_release       — artist's first catalogued release
    (`primer_release`). Severity 5.
  * n3_collaboration       — release whose tracks carry a featuring
    (`te_collab`). Severity 4. (Generic copy — we don't store the guest
    names, so the templates note the collaboration without naming it.)
  * n4_label_release       — release on a label shared by >= 2 distinct
    top artists (`segell_compartit`). Severity 3.

A `fallback_novetat` scenario is emitted for the most recent release
when no detector fires, so a roundup always has a headline.
"""

from __future__ import annotations

from social.narrative.scenarios import Scenario
from social.narrative.utils import dies_str, with_preposition

_TIPUS_PARAULA = {"album": "àlbum", "single": "single", "ep": "EP"}


def _novetat_data(item: dict, n_total: int) -> dict:
    artista = item.get("artista_nom") or "—"
    dies = item.get("dies")
    return {
        "artista": artista,
        "de_artista": with_preposition(artista, "de"),
        "per_artista": with_preposition(artista, "per"),
        "titol": item.get("nom") or "—",
        "tipus_paraula": _TIPUS_PARAULA.get(
            (item.get("tipus") or "").lower(), "novetat"
        ),
        "dies_str": dies_str(dies) if isinstance(dies, int) else "pocs dies",
        "segell": item.get("segell") or "",
        "n_total": n_total,
        # Subjects for `scenarios.select_slots`: novetats are album-level,
        # so there is no canco_id — they dedup by artist.
        "canco_id": None,
        "artista_id": item.get("artista_id"),
    }


def _pick_recent(items: list[dict], pred) -> dict | None:
    """First item (already ordered newest-first) matching `pred`."""
    for it in items:
        if pred(it):
            return it
    return None


def detect_n1_debut_artist_known(items, n_total):
    it = _pick_recent(items, lambda i: i.get("artista_en_top"))
    if not it:
        return None
    return Scenario("n1_debut_artist_known", 6, _novetat_data(it, n_total))


def detect_n2_first_release(items, n_total):
    it = _pick_recent(items, lambda i: i.get("primer_release"))
    if not it:
        return None
    return Scenario("n2_first_release", 5, _novetat_data(it, n_total))


def detect_n3_collaboration(items, n_total):
    it = _pick_recent(items, lambda i: i.get("te_collab"))
    if not it:
        return None
    return Scenario("n3_collaboration", 4, _novetat_data(it, n_total))


def detect_n4_label_release(items, n_total):
    it = _pick_recent(items, lambda i: i.get("segell_compartit") and i.get("segell"))
    if not it:
        return None
    return Scenario("n4_label_release", 3, _novetat_data(it, n_total))


def fallback_novetat(items, n_total):
    """Generic headline for the most recent release (always available
    when there is at least one item)."""
    if not items:
        return None
    return Scenario("fallback_novetat", 0, _novetat_data(items[0], n_total))


_NOVETATS_DETECTORS = (
    detect_n1_debut_artist_known,
    detect_n2_first_release,
    detect_n3_collaboration,
    detect_n4_label_release,
)


def detect_novetats(items: list[dict]) -> list[Scenario]:
    """Run every novetats detector over `items` and return the scenarios
    sorted by severity desc. Always includes a `fallback_novetat` for the
    most recent release, so a roundup never lacks a headline."""
    n_total = len(items)
    out: list[Scenario] = []
    for det in _NOVETATS_DETECTORS:
        try:
            s = det(items, n_total)
        except Exception:  # a detector bug must not poison the post
            continue
        if s is not None:
            out.append(s)
    fb = fallback_novetat(items, n_total)
    if fb is not None:
        out.append(fb)
    out.sort(key=lambda s: -s.severity)
    return out
