"""Shared compact serializers for the public REST surface.

Centralises the small dict shapes that were repeated across endpoints.
Each helper is intentionally narrow — they're for *list contexts*
where we only want a label + URL handle. Detail endpoints build their
own richer payloads inline (the field set there is page-specific and
inlining keeps the SQL → response mapping legible).

Pattern: helpers take a Django model instance and return a JSON-safe
dict. They never raise; missing optional fields fall back to None or
empty strings to match the historical inline shape.
"""

from __future__ import annotations

from typing import Any


def artista_minimal(artista) -> dict[str, Any]:
    """`{nom, slug}` — the shape used for collab lists, breadcrumbs,
    "veure'n més" links, and any other context where we only need the
    artist's identity, not their full profile."""
    return {"nom": artista.nom, "slug": artista.slug}


def album_card(album) -> dict[str, Any]:
    """Standard album shape for grid/list contexts. Includes the
    cover URL (the most-used field after slug) and the release date
    in ISO format. The artiste is intentionally NOT embedded — most
    callers already have it from the queryset's `select_related`."""
    return {
        "pk": album.pk,
        "slug": album.slug,
        "nom": album.nom,
        "data_llancament": (
            album.data_llancament.isoformat() if album.data_llancament else None
        ),
        "imatge_url": getattr(album, "imatge_url", None) or None,
    }


def canco_card(canco, *, ranked_ids: set | None = None) -> dict[str, Any]:
    """Standard canço shape for track lists.

    `ranked_ids`: optional set of canço pks that have ever appeared in
    a top. When provided, an `al_top` boolean is added — saves the
    caller from doing the membership test inline.
    """
    payload: dict[str, Any] = {
        "pk": canco.pk,
        "slug": canco.slug,
        "nom": canco.nom,
        "isrc": canco.isrc or None,
        "durada_ms": canco.durada_ms,
        "preview_url": canco.preview_url or None,
        "deezer_id": canco.deezer_id,
        "artistes_col": [artista_minimal(a) for a in canco.artistes_col.all()],
    }
    if ranked_ids is not None:
        payload["al_top"] = canco.pk in ranked_ids
    return payload
