"""Staff endpoints package — split from the historical
`web/api/staff_views.py` (3 300-LoC monolith) on 2026-04-25 (Sprint C).

Each module covers one staff area; the package re-exports every public
endpoint here so callers can keep importing as before:

    from web.api.staff import dashboard          # works
    from web.api.staff_views import dashboard    # works (shim)
    from web.api import staff_views              # works (urls.py)

When you add a new endpoint, define it in the right module, then add
the name to the explicit re-export list below. New modules go through
this file too so `staff_views.py` doesn't need touching.
"""

from web.api.staff._common import IsStaff, _paginate  # noqa: F401
from web.api.staff.albums import album_detail, albums_list  # noqa: F401
from web.api.staff.analytics import (  # noqa: F401
    analytics_seo,
    analytics_summary,
    goaccess_report,
)
from web.api.staff.artistes import (  # noqa: F401
    artista_crear,
    artista_detail,
    artista_lastfm_alias_action,
    artista_lastfm_alias_create,
    artista_lastfm_clear,
    artista_mb_clear,
    artista_sync_mb,
    artistes_fusionar,
    artistes_list,
    artistes_search,
)
from web.api.staff.audit import auditlog  # noqa: F401
from web.api.staff.cancons import (  # noqa: F401
    _canco_row,
    canco_detail,
    cancons_accio,
    cancons_list,
)
from web.api.staff.configuracio import configuracio  # noqa: F401

# Per-area modules — each adds its endpoints to the package namespace.
from web.api.staff.dashboard import dashboard  # noqa: F401
from web.api.staff.estat import (  # noqa: F401
    _homonym_suspects_details,
    _homonym_suspects_qs,
    _musicbrainz_stats,
    _top_artistes_backlog,
    estat,
)
from web.api.staff.feedback import (  # noqa: F401
    _feedback_row,
    feedback_list,
    feedback_resolve,
)
from web.api.staff.historial import historial_list  # noqa: F401
from web.api.staff.newsletter import esborrany as newsletter_esborrany  # noqa: F401
from web.api.staff.newsletter import (  # noqa: F401
    esborrany_cancellar as newsletter_esborrany_cancellar,
)
from web.api.staff.newsletter import (  # noqa: F401
    esborrany_generar as newsletter_esborrany_generar,
)
from web.api.staff.newsletter import (  # noqa: F401
    esborrany_preview as newsletter_esborrany_preview,
)
from web.api.staff.newsletter import setmanes as newsletter_setmanes  # noqa: F401
from web.api.staff.pendents import (  # noqa: F401
    _artista_card,
    _compute_propostes_per_artista_map,
    pendent_aprovar,
    pendent_descartar,
    pendents_list,
)
from web.api.staff.propostes import (  # noqa: F401
    _proposta_row,
    proposta_aprovar,
    proposta_detail,
    proposta_fusionar,
    proposta_rebutjar,
    propostes_list,
)
from web.api.staff.senyal import (  # noqa: F401
    canco_refetch_senyal,
    senyal_acceptar_correccio,
    senyal_list,
)
from web.api.staff.social import (  # noqa: F401
    social_bluesky_clear,
    social_bluesky_save,
    social_bluesky_test,
    social_credentials_clear,
    social_credentials_save,
    social_credentials_test,
    social_delay,
    social_eliminar_instagram,
    social_eliminar_remot,
    social_estat_canals,
    social_fase,
    social_list,
    social_mastodon_clear,
    social_mastodon_save,
    social_mastodon_test,
    social_preview,
    social_preview_all,
    social_publicar_ara,
    social_render_serve,
    social_republicar,
    social_reset,
    social_slides_for,
    social_story_cap,
    social_telegram_clear,
    social_telegram_save,
    social_telegram_test,
    social_toggle,
    spotify_estat,
    spotify_oauth_callback,
    spotify_oauth_start,
    spotify_sync,
)
from web.api.staff.solicituds import (  # noqa: F401
    _solicitud_row,
    solicitud_rebutjar,
    solicitud_toggle,
    solicituds_list,
)
from web.api.staff.top import (  # noqa: F401
    TOP_TERRITORIS,
    canco_top_breakdown,
    top_accio,
    top_list,
)
from web.api.staff.usuaris import (  # noqa: F401
    usuari_detail,
    usuari_enviar_reset_password,
    usuari_esborrar,
    usuari_reenviar_verificacio,
    usuari_reset_2fa,
    usuari_toggle_actiu,
    usuaris_list,
)

# Backward-compat aliases (Sprint Naming, 2026-04-25). External callers
# may have imported the old names — keep them resolving to the new
# definitions until we're confident nobody references them.
ranking_list = top_list
ranking_accio = top_accio
canco_ranking_breakdown = canco_top_breakdown
RANKING_TERRITORIS = TOP_TERRITORIS
