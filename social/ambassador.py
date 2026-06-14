"""Ambassador share assets: a ready-to-share "has entrat al top" caption
for an artist (Fase 2 E).

This is the text an artist (or the team) pastes when celebrating a new
top entry — the move that drove the best organic reach we've measured
(the 886-reach post, investigation 2026-06). It is DELIBERATELY decoupled
from the publication pipeline: it touches no gating
(`ConfiguracioGlobal` / `MatriuPublicacio`) and is never auto-posted. The
weekly social posts keep their own captions in `social/captions.py`.

Message stays cohesive with `docs/outreach/press-kit-2026.md`: artist +
"Top de música en català de TopQuaranta" + the canonical artist URL.

# Spec: docs/architecture/social.md
"""

from __future__ import annotations

from django.conf import settings

# Ordinal-safe position label (Catalan), never a "#<digit>" form — the
# narrative-engine post-mortem (2026-05-20) showed positional hashtags
# leak audience on IG/Telegram. We mirror that discipline here.
_BASE_HASHTAGS = "#MúsicaEnCatalà #TopQuaranta"


def _posicio_label(posicio: int | None) -> str:
    if not posicio:
        return ""
    # Catalan ordinals: 1r, 2n, 3r, 4t, else Nè.
    special = {1: "1r", 2: "2n", 3: "3r", 4: "4t"}
    return special.get(posicio, f"{posicio}è")


def ambassador_top_caption(
    artista_nom: str,
    slug: str,
    posicio: int | None = None,
) -> str:
    """Return a shareable caption for an artist that has entered the
    weekly top. Always includes the artist name + canonical URL; the
    position is woven in only when known. No positional `#<digit>`
    hashtag (audience-leak guard)."""
    url = f"{settings.SITE_URL}/artista/{slug}"
    pos = _posicio_label(posicio)
    if pos:
        head = (
            f"🎉 {artista_nom} entra al {pos} lloc del Top de música en "
            f"català de TopQuaranta!"
        )
    else:
        head = f"🎉 {artista_nom} entra al Top de música en català de " f"TopQuaranta!"
    return f"{head}\n\n{url}\n\n{_BASE_HASHTAGS}"
