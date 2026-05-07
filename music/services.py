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

    Side effect when motiu == "artista_incorrecte":
    `_try_auto_unlink_homonym_deezer` may detach the wrong Deezer
    profile from the artist. The function is multi-profile aware:
    when the artista has several `ArtistaDeezer` rows (autoedit +
    label, etc.), only the *specific* profile that produced this
    canço is unlinked — the other profiles stay. With a single
    profile, the whole link is removed (legacy behaviour). See the
    function for the safety thresholds.
    """
    artista = canco.artista
    crear_historial(canco, "rebutjada", motiu)
    canco.verificada = False
    canco.activa = False
    canco.save(update_fields=["verificada", "activa"])
    if motiu == "artista_incorrecte" and artista is not None:
        _try_auto_unlink_homonym_deezer(artista, canco=canco)


def _try_auto_unlink_homonym_deezer(
    artista: Artista, canco: Canco | None = None
) -> bool:
    """Detach Deezer IDs from an artist when every track has been
    rejected as a homonym. Conservative: if anything still verified
    or active exists, or if any historial rejection used a different
    motiu, we abstain.

    Multi-profile artistes: when the artista has several
    `ArtistaDeezer` rows AND we know which profile the rejected
    canço came from (`canco.album.source_deezer_id`), only that
    profile is unlinked. The other profiles stay. Without source
    info (legacy Album rows or no canço context), we defer to
    staff to avoid wiping a legitimate profile by mistake.

    Single-profile artistes keep the legacy behaviour: when all
    conditions match, the only Deezer link is removed.

    Returns True if at least one ArtistaDeezer row was deleted.
    """
    # Any track still alive? Defer to human review.
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

    # Multi-profile path (May-2026): only kill the specific profile
    # that sourced the rejected canço. Without source info we defer.
    if len(deezer_links) > 1:
        source = None
        if canco is not None and canco.album_id is not None:
            source = getattr(canco.album, "source_deezer_id", None)
        if not source:
            logger.info(
                "Defer unlink for '%s' (pk=%s): %d Deezer profiles linked, "
                "source unknown for the rejected canço.",
                artista.nom,
                artista.pk,
                len(deezer_links),
            )
            return False
        target = artista.deezer_ids.filter(deezer_id=source).first()
        if not target:
            logger.warning(
                "Cannot unlink: source deezer_id=%s for canço pk=%s is not "
                "in artista '%s' (pk=%s) Deezer set.",
                source,
                canco.pk if canco else "?",
                artista.nom,
                artista.pk,
            )
            return False
        target.delete()
        logger.info(
            "Auto-unlinked specific Deezer profile %s from artist '%s' "
            "(pk=%s) — other %d profile(s) kept.",
            source,
            artista.nom,
            artista.pk,
            len(deezer_links) - 1,
        )
        return True

    # Single-profile path (legacy): wipe the only link. The
    # post_delete signal handles desaprovació if there's also no
    # MBID anchor left.
    artista.deezer_ids.all().delete()
    logger.info(
        "Auto-unlinked the only Deezer ID from artist '%s' (pk=%s) — "
        "every Cançó rejected as artista_incorrecte.",
        artista.nom,
        artista.pk,
    )
    return True


def processar_collaboradors_pendents(canco: Canco) -> int:
    """Materialise `canco.contributors_raw` into real Artista rows.

    Walks the deferred contributors list captured during ingest and,
    for each entry whose `deezer_id` doesn't already map to an
    Artista, creates a new `Artista(pendent_review=True,
    auto_descobert=True, font_descoberta="deezer_contributor")`
    plus the matching `ArtistaDeezer` row. All resulting Artistas
    (newly created + already-existing matched-by-Deezer-ID) are
    added to `canco.artistes_col`. The list is then cleared.

    Return: number of new Artista rows created.

    Called from `aprovar_canco` / `aprovar_canco_auto_ml` so pendents
    are only created when staff (or ML auto-approval) confirms the
    canco belongs in our catalog. See `Canco.contributors_raw`
    docstring for context (2026-05-07 audit: 76 % of song rebuigs
    are `album_incorrecte`; deferring pendent creation eliminates
    that share of the staff-review queue noise).
    """
    raw = list(canco.contributors_raw or [])
    if not raw:
        return 0

    # Late import to avoid the music ↔ ingest circular at startup.
    from music.models import ArtistaDeezer

    created = 0
    main_deezer_ids = set(canco.artista.deezer_ids.values_list("deezer_id", flat=True))
    for entry in raw:
        c_id = entry.get("deezer_id")
        c_name = (entry.get("name") or "").strip()
        if not c_id or c_id in main_deezer_ids:
            continue
        ad = (
            ArtistaDeezer.objects.filter(deezer_id=c_id)
            .select_related("artista")
            .first()
        )
        if ad:
            collab = ad.artista
        else:
            collab = Artista.objects.create(
                nom=c_name or f"deezer:{c_id}",
                lastfm_nom=c_name,
                aprovat=False,
                auto_descobert=True,
                pendent_review=True,
                font_descoberta="deezer_contributor",
            )
            ArtistaDeezer.objects.get_or_create(
                deezer_id=c_id,
                defaults={"artista": collab, "principal": True},
            )
            created += 1
            logger.info(
                "Materialised pending collab Artista '%s' (deezer_id=%d) from canco %d",
                c_name,
                c_id,
                canco.pk,
            )
        if collab.pk != canco.artista_id:
            canco.artistes_col.add(collab)

    canco.contributors_raw = []
    canco.save(update_fields=["contributors_raw"])
    return created


def aprovar_canco(canco: Canco) -> None:
    """Approve a single track: record historial, set verificada=True.

    Also materialises any deferred `contributors_raw` into real
    Artista rows + `artistes_col` links — see
    `processar_collaboradors_pendents` for context.

    Pings IndexNow so Bing/Yandex (and the rest of the consortium)
    crawl the new public URL within hours instead of waiting for our
    weekly sitemap recrawl. Fail-open — never blocks the staff flow.
    """
    crear_historial(canco, "aprovada", "ok")
    canco.verificada = True
    canco.save(update_fields=["verificada"])
    processar_collaboradors_pendents(canco)
    # Late import — avoids a circular dependency at app start
    # (web.seo.indexnow imports music models).
    from web.seo.indexnow import notify_canco

    notify_canco(canco)


def aprovar_canco_auto_ml(canco: Canco) -> None:
    """ML auto-approval (A++ blind-trust path).

    Same outcome as `aprovar_canco` (including
    `processar_collaboradors_pendents`) but tags the historial entry
    with `motiu="auto_ml"` so the training pipeline can filter these
    rows out — otherwise the model would learn from its own decisions
    and drift toward over-confidence.
    """
    from .constants import MOTIU_AUTO_ML

    crear_historial(canco, "aprovada", MOTIU_AUTO_ML)
    canco.verificada = True
    canco.save(update_fields=["verificada"])
    processar_collaboradors_pendents(canco)
    from web.seo.indexnow import notify_canco

    notify_canco(canco)


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
