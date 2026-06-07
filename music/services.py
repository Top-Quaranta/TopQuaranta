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


def has_approved_artist(canco: Canco) -> bool:
    """True if the canço has at least one approved artist — the main
    `artista` or any `artistes_col` collaborator.

    Single source of truth for "is this song reviewable" (auditoria
    2026-06-07, informe 2a): a pendent canço whose main and every
    collaborator are still pendent has no approved anchor and must not
    sit in the verification queue. Callers iterating many rows should
    `prefetch_related("artistes_col")` (or use `orphan_pendents_qs`)."""
    if canco.artista_id and canco.artista and canco.artista.aprovat:
        return True
    return any(c.aprovat for c in canco.artistes_col.all())


def orphan_pendents_qs(base=None):
    """Queryset of *orphan* pendent cançons: `verificada=False`,
    `activa=True`, NO approved artist (main or collab), AND no pending
    deferred collaborators (`contributors_raw` empty).

    Mirrors `has_approved_artist` at the SQL level for bulk operations
    (the de-approval hook, the recurring net, the backfill migration).
    Songs that still carry deferred contributors in `contributors_raw`
    are SPARED: resolving them on approval may yet attach an approved
    artist, so deactivating them now would be premature (caught as the
    explicit caveat of the 2026-06-07 ingest-hole fix)."""
    qs = base if base is not None else Canco.objects.all()
    return (
        qs.filter(verificada=False, activa=True, contributors_raw=[])
        .exclude(artista__aprovat=True)
        .exclude(artistes_col__aprovat=True)
        .distinct()
    )


def rebutjar_canco(canco: Canco, motiu: str) -> None:
    """
    Reject a single track: record historial, set verificada=False and activa=False.
    The track stays in DB for audit but won't appear in pending lists or rankings.

    Side effect when motiu == "desvincular_artista":
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
    if motiu == "desvincular_artista" and artista is not None:
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
    # Sprint Workflow Sol·licituds (2026-05-20): rows the staff has
    # reconsiderat via the workbench shouldn't count as evidence
    # against the artist-Deezer link any more — if the canço is
    # being re-opened the link should stay live until the canço is
    # rejected again with a fresh row (reconsiderada=False by default).
    motius = list(
        HistorialRevisio.objects.filter(
            artista_nom=artista.nom,
            decisio="rebutjada",
            reconsiderada=False,
        ).values_list("motiu", flat=True)
    )
    if not motius:
        return False
    if any(m != "desvincular_artista" for m in motius):
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

    # Single-profile path: wipe the only link. The post_delete signal
    # on ArtistaDeezer runs (`unapprove_on_last_deezer_removed`) and
    # would normally either keep the artista aprovat (if MBID) or
    # drop it to `aprovat=False, pendent_review=False` (limbo). The
    # explicit override below forces `pendent_review=True,
    # aprovat=False` regardless of MBID: we have just lost our only
    # Deezer source for new releases, the operator still needs to
    # find the right Deezer profile, and that work belongs in the
    # pendents queue.
    artista.deezer_ids.all().delete()
    Artista.objects.filter(pk=artista.pk).update(aprovat=False, pendent_review=True)
    logger.info(
        "Auto-unlinked the only Deezer ID from artist '%s' (pk=%s) "
        "and queued for pendent review.",
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
    were `album_incorrecte` (now `desvincular_album`); deferring
    pendent creation eliminates that share of the staff-review
    queue noise).
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
    """Reject an artista: delete all unverified tracks, clear the
    Deezer M2M, mark all albums as descartat, and explicitly queue
    the artista for `pendent_review`.

    The pendent_review override (2026-05-25) replaces the previous
    "limbo" outcome where the post_delete signal on ArtistaDeezer
    set `aprovat=False, pendent_review=False` only when no MBID
    anchored the artista. Even with an MBID, after a
    `desvincular_artista` action the artista has lost its only
    Deezer source for new releases and the operator still needs to
    find the correct Deezer profile; that work belongs in the
    pendents queue, regardless of MBID. The signal still runs (no
    way to suppress it cheaply) but the explicit `update()` below
    overrides whatever state it left.

    Returns number of tracks deleted.
    """
    cancons = Canco.objects.filter(artista=artista, verificada=False)
    for canco in cancons.select_related("album"):
        crear_historial(canco, "rebutjada", motiu)
    deleted = cancons.count()
    cancons.delete()

    # R10: ArtistaDeezer is the sole source of truth; clearing it
    # is enough to detach the Deezer pipeline.
    artista.deezer_ids.all().delete()
    Album.objects.filter(artista=artista).update(descartat=True)
    Artista.objects.filter(pk=artista.pk).update(aprovat=False, pendent_review=True)

    # De-approval hook (2026-06-07, informe 2a): rejecting this artista
    # demotes it to pendent. Cançons where it was a *collaborator* (the
    # main unverified ones were just deleted above) may now be left with
    # NO approved artist — exactly the Irokz case, where rejecting the
    # collaborator left "Love Me (Slowed)" active in the verify queue
    # with every artist pendent. Deactivate those orphans instead of
    # leaving them as active "victims". `orphan_pendents_qs` spares songs
    # still awaiting deferred-collaborator resolution.
    orphan_ids = list(
        orphan_pendents_qs(Canco.objects.filter(artistes_col=artista)).values_list(
            "id", flat=True
        )
    )
    if orphan_ids:
        Canco.objects.filter(id__in=orphan_ids).update(activa=False)
        logger.info(
            "rebutjar_artista(%s): deactivated %d orphan pendent canço(s) "
            "left with no approved artist",
            artista.pk,
            len(orphan_ids),
        )

    return deleted
