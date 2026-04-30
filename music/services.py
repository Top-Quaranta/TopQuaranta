"""
Business logic for track/artist/album approval and rejection.

All admin actions delegate to these functions so the logic lives in one place.
Each function operates inside the caller's transaction — the caller wraps
with transaction.atomic() as needed.
"""

import logging

from django.db import transaction

from .models import Album, Artista, Canco, HistorialRevisio
from .verificacio import crear_historial

logger = logging.getLogger(__name__)


def rebutjar_canco(canco: Canco, motiu: str) -> None:
    """
    Reject a single track: record historial, set verificada=False and activa=False.
    The track stays in DB for audit but won't appear in pending lists or rankings.

    Side effect when motiu == "artista_incorrecte": if after this
    rejection the artist has zero remaining active Cançons AND every
    rejection recorded for this artist is also "artista_incorrecte",
    we treat the whole Deezer attachment as wrong and remove every
    ArtistaDeezer row for the artist. The post_delete signal then
    desaprova the artist if no MBID remains. See
    `_try_auto_unlink_homonym_deezer` for the safety thresholds — when
    in doubt we leave the case for human review (it will surface in
    the Estat "Casos sospitosos" panel).
    """
    artista = canco.artista
    crear_historial(canco, "rebutjada", motiu)
    canco.verificada = False
    canco.activa = False
    canco.save(update_fields=["verificada", "activa"])
    if motiu == "artista_incorrecte" and artista is not None:
        _try_auto_unlink_homonym_deezer(artista)


def _try_auto_unlink_homonym_deezer(artista: Artista) -> bool:
    """Detach Deezer IDs from an artist when every track has been
    rejected as a homonym. Conservative: if anything still verified
    or active exists, or if any historial rejection used a different
    motiu, we abstain.

    Returns True if the unlink happened.
    """
    # Any track still alive? Defer to human review (e.g. some tracks
    # could be from a different — correct — Deezer ID on the same artist).
    if Canco.objects.filter(artista=artista, activa=True).exists():
        return False
    # Look at every rejection ever recorded for this artist's name.
    motius = list(
        HistorialRevisio.objects.filter(
            artista_nom=artista.nom, decisio="rebutjada"
        ).values_list("motiu", flat=True)
    )
    if not motius:
        return False
    if any(m != "artista_incorrecte" for m in motius):
        return False
    deezer_links = list(artista.deezer_ids.all())
    if not deezer_links:
        return False
    # Trigger. The post_delete signal does the desaprovació if there's
    # also no MBID anchor left.
    artista.deezer_ids.all().delete()
    logger.info(
        "Auto-unlinked %d Deezer ID(s) from artist '%s' (pk=%s) — "
        "every Cançó rejected as artista_incorrecte.",
        len(deezer_links),
        artista.nom,
        artista.pk,
    )
    return True


def aprovar_canco(canco: Canco) -> None:
    """Approve a single track: record historial, set verificada=True."""
    crear_historial(canco, "aprovada", "ok")
    canco.verificada = True
    canco.save(update_fields=["verificada"])


def aprovar_canco_auto_ml(canco: Canco) -> None:
    """ML auto-approval (A++ blind-trust path).

    Same outcome as `aprovar_canco` but tags the historial entry with
    `motiu="auto_ml"` so the training pipeline can filter these rows
    out — otherwise the model would learn from its own decisions and
    drift toward over-confidence.
    """
    from .constants import MOTIU_AUTO_ML

    crear_historial(canco, "aprovada", MOTIU_AUTO_ML)
    canco.verificada = True
    canco.save(update_fields=["verificada"])


def rebutjar_album(album: Album, motiu: str) -> int:
    """
    Reject all unverified tracks in an album, mark album as descartat.
    Returns number of tracks deleted.
    """
    cancons = Canco.objects.filter(album=album, verificada=False)
    for canco in cancons.select_related("artista", "album"):
        crear_historial(canco, "rebutjada", motiu)
    deleted = cancons.count()
    cancons.delete()
    album.descartat = True
    album.save(update_fields=["descartat"])
    return deleted


def rebutjar_artista(artista: Artista, motiu: str) -> int:
    """
    Reject an artist: delete all unverified tracks, clear the Deezer
    M2M, mark all albums as descartat.
    Returns number of tracks deleted.
    """
    cancons = Canco.objects.filter(artista=artista, verificada=False)
    for canco in cancons.select_related("album"):
        crear_historial(canco, "rebutjada", motiu)
    deleted = cancons.count()
    cancons.delete()

    # R10: ArtistaDeezer is the sole source of truth; clearing it is enough.
    artista.deezer_ids.all().delete()
    Album.objects.filter(artista=artista).update(descartat=True)

    return deleted
