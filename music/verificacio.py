from music.models import Canco, HistorialRevisio


def crear_historial(canco: Canco, decisio: str, motiu: str) -> HistorialRevisio:
    """Capture a snapshot of the canco and create an HistorialRevisio
    record. Must be called BEFORE deleting or modifying the canco.

    The snapshot includes `artista_spotify_id`, the principal
    Spotify artist id derived from the canco's SpotifyMetadata
    row when present. This is the key the per-pair rejection
    ratio feature in `music.ml` groups on; storing it at decision
    time means the feature has full historical coverage on every
    new decision and can be backfilled later for legacy rows that
    only get enriched after the fact (see
    `backfill_artista_spotify_id_in_historial` management
    command).
    """
    artista = canco.artista
    # Cap at the column's max_length (100). Defensive truncation: if a
    # future schema drift or unusually-wide territori list ever again
    # exceeds the column, we lose a couple of trailing codes instead
    # of dropping the whole row + emailing a 500. Caught 2026-05-08
    # with "CAT,VAL,BAL" (11 chars) against the previous max_length=10.
    territoris = ",".join(artista.territoris.values_list("codi", flat=True))[:100]
    isrc = canco.isrc or ""

    # Spotify artist id snapshot: read from the SpotifyMetadata
    # row tied to this canço, if one exists. We pull the principal
    # artist id (`spotify_artist_id`), not the full collaborators
    # list — the per-pair rejection-ratio feature keys on the
    # principal. Missing enrichment (still `not_attempted` or
    # `not_found`) leaves the field blank; the backfill command
    # fills it in when Process B catches up.
    artista_spotify_id = ""
    sm = getattr(canco, "spotify", None)
    if sm is not None and sm.spotify_artist_id:
        artista_spotify_id = sm.spotify_artist_id

    return HistorialRevisio.objects.create(
        canco_deezer_id=canco.deezer_id,
        canco_spotify_id=canco.spotify_id or "",
        canco_isrc=isrc,
        canco_nom=canco.nom,
        artista_nom=artista.nom,
        artista_territori=territoris,
        album_nom=canco.album.nom if canco.album_id else "",
        data_llancament=canco.data_llancament,
        isrc_prefix=isrc[:2] if len(isrc) >= 2 else "",
        artista_deezer_id=artista.deezer_id_principal,
        artista_deezer_nb_fan=artista.deezer_nb_fan,
        artista_deezer_nb_album=artista.deezer_nb_album,
        artista_nom_deezer=artista.deezer_nom,
        artista_nom_similitud=artista.deezer_nom_similitud,
        artista_spotify_id=artista_spotify_id,
        ml_classe_decisio=canco.ml_classe or "",
        ml_confianca_decisio=canco.ml_confianca,
        decisio=decisio,
        motiu=motiu,
    )
