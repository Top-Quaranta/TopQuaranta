from django.urls import path
from django.views.generic import RedirectView

from . import (
    album_views,
    artistes_views,
    auth_views,
    canco_views,
    compte_views,
    comunitat_views,
    home_views,
    mapa_views,
    social_public,
    staff_views,
    top_views,
)

app_name = "api"

urlpatterns = [
    # Auth (consumed by the React SPA)
    path("auth/me/", auth_views.me, name="auth_me"),
    path("auth/login/", auth_views.login_view, name="auth_login"),
    path("auth/logout/", auth_views.logout_view, name="auth_logout"),
    path("auth/register/", auth_views.register_view, name="auth_register"),
    # Authenticated user area
    path("compte/dashboard/", compte_views.dashboard, name="compte_dashboard"),
    path("compte/perfil/", compte_views.perfil, name="compte_perfil"),
    path(
        "compte/propostes/",
        compte_views.proposta_crear,
        name="compte_proposta_crear",
    ),
    path(
        "compte/solicituds/",
        compte_views.solicitud_crear,
        name="compte_solicitud_crear",
    ),
    # Manager self-service: GET snapshot + PATCH non-critical fields.
    # Permission: requires UserArtista(usuari, artista, verificat=True).
    path(
        "compte/artista/<int:pk>/editar/",
        compte_views.gestor_artista_editar,
        name="compte_gestor_artista_editar",
    ),
    # Public feedback (authenticated, any user)
    path("feedback/", compte_views.feedback_crear, name="feedback_crear"),
    # Account deletion (self-service): request sends a confirmation email.
    path(
        "compte/esborrar-sollicitud/",
        compte_views.compte_esborrar_sollicitar,
        name="compte_esborrar_sollicitar",
    ),
    # ── Sprint J — RGPD ──
    path(
        "compte/exportar-dades/",
        compte_views.exportar_dades,
        name="compte_exportar_dades",
    ),
    path(
        "compte/baixa-newsletter/",
        compte_views.baixa_newsletter,
        name="compte_baixa_newsletter",
    ),
    # ── Staff (is_staff required) ──
    path("staff/dashboard/", staff_views.dashboard, name="staff_dashboard"),
    path("staff/estat/", staff_views.estat, name="staff_estat"),
    # Pendents
    path("staff/pendents/", staff_views.pendents_list, name="staff_pendents_list"),
    path(
        "staff/pendents/<int:pk>/aprovar/",
        staff_views.pendent_aprovar,
        name="staff_pendent_aprovar",
    ),
    path(
        "staff/pendents/<int:pk>/descartar/",
        staff_views.pendent_descartar,
        name="staff_pendent_descartar",
    ),
    # Artistes
    path("staff/artistes/", staff_views.artistes_list, name="staff_artistes_list"),
    path(
        "staff/artistes/fusionar/",
        staff_views.artistes_fusionar,
        name="staff_artistes_fusionar",
    ),
    path(
        "staff/artistes/search/",
        staff_views.artistes_search,
        name="staff_artistes_search",
    ),
    path(
        "staff/artistes/crear/",
        staff_views.artista_crear,
        name="staff_artista_crear",
    ),
    path(
        "staff/artistes/<int:pk>/",
        staff_views.artista_detail,
        name="staff_artista_detail",
    ),
    path(
        "staff/artistes/<int:pk>/mb-clear/",
        staff_views.artista_mb_clear,
        name="staff_artista_mb_clear",
    ),
    path(
        "staff/artistes/<int:pk>/lastfm-aliases/",
        staff_views.artista_lastfm_alias_create,
        name="staff_artista_lastfm_alias_create",
    ),
    path(
        "staff/artistes/<int:pk>/lastfm-aliases/<int:alias_pk>/",
        staff_views.artista_lastfm_alias_action,
        name="staff_artista_lastfm_alias_action",
    ),
    path(
        "staff/artistes/<int:pk>/sync-mb/",
        staff_views.artista_sync_mb,
        name="staff_artista_sync_mb",
    ),
    # Cançons
    path("staff/cancons/", staff_views.cancons_list, name="staff_cancons_list"),
    path("staff/cancons/accio/", staff_views.cancons_accio, name="staff_cancons_accio"),
    path(
        "staff/cancons/<int:pk>/",
        staff_views.canco_detail,
        name="staff_canco_detail",
    ),
    path(
        "staff/cancons/<int:pk>/refetch-senyal/",
        staff_views.canco_refetch_senyal,
        name="staff_canco_refetch_senyal",
    ),
    path(
        "staff/cancons/<int:pk>/top/",
        staff_views.canco_top_breakdown,
        name="staff_canco_top_breakdown",
    ),
    # Legacy alias — kept alive for any in-flight SPA bundle. Same view
    # at both URLs (cleaner than 301 because the staff endpoints support
    # POST/PATCH where 301 → method downgrade is unsafe).
    path(
        "staff/cancons/<int:pk>/ranking/",
        staff_views.canco_top_breakdown,
        name="staff_canco_ranking_breakdown",
    ),
    # Albums
    path("staff/albums/", staff_views.albums_list, name="staff_albums_list"),
    path(
        "staff/albums/<int:pk>/",
        staff_views.album_detail,
        name="staff_album_detail",
    ),
    # Top provisional (canonical) + legacy ranking aliases.
    path("staff/top/", staff_views.top_list, name="staff_top_list"),
    path("staff/top/accio/", staff_views.top_accio, name="staff_top_accio"),
    # Legacy aliases (POST-safe — same view, no redirect).
    path("staff/ranking/", staff_views.top_list, name="staff_ranking_list"),
    path("staff/ranking/accio/", staff_views.top_accio, name="staff_ranking_accio"),
    # Propostes
    path("staff/propostes/", staff_views.propostes_list, name="staff_propostes_list"),
    path(
        "staff/propostes/<int:pk>/",
        staff_views.proposta_detail,
        name="staff_proposta_detail",
    ),
    path(
        "staff/propostes/<int:pk>/aprovar/",
        staff_views.proposta_aprovar,
        name="staff_proposta_aprovar",
    ),
    path(
        "staff/propostes/<int:pk>/fusionar/",
        staff_views.proposta_fusionar,
        name="staff_proposta_fusionar",
    ),
    path(
        "staff/propostes/<int:pk>/rebutjar/",
        staff_views.proposta_rebutjar,
        name="staff_proposta_rebutjar",
    ),
    # Sol·licituds de gestió
    path(
        "staff/solicituds/", staff_views.solicituds_list, name="staff_solicituds_list"
    ),
    path(
        "staff/solicituds/<int:pk>/toggle/",
        staff_views.solicitud_toggle,
        name="staff_solicitud_toggle",
    ),
    path(
        "staff/solicituds/<int:pk>/rebutjar/",
        staff_views.solicitud_rebutjar,
        name="staff_solicitud_rebutjar",
    ),
    # Senyal diari
    path("staff/senyal/", staff_views.senyal_list, name="staff_senyal_list"),
    path(
        "staff/senyal/<int:canco_pk>/acceptar-correccio/",
        staff_views.senyal_acceptar_correccio,
        name="staff_senyal_acceptar_correccio",
    ),
    # Historial
    path("staff/historial/", staff_views.historial_list, name="staff_historial_list"),
    # Configuració
    path("staff/configuracio/", staff_views.configuracio, name="staff_configuracio"),
    # Auditoria
    path("staff/auditlog/", staff_views.auditlog, name="staff_auditlog"),
    # ── Sprint I — public PNG endpoint Meta can fetch from ──
    # See web/api/social_public.py for the rationale. NB: no trailing
    # slash — Meta's image fetcher dislikes URLs that end in a slash
    # right after the .png extension.
    path(
        "social/render/<str:filename>",
        social_public.render_public,
        name="social_render_public",
    ),
    # ── Sprint I — social distribution (staff) ──
    path("staff/social/", staff_views.social_list, name="staff_social_list"),
    path(
        "staff/social/preview/", staff_views.social_preview, name="staff_social_preview"
    ),
    path(
        "staff/social/preview-all/",
        staff_views.social_preview_all,
        name="staff_social_preview_all",
    ),
    path(
        "staff/social/publicar-ara/",
        staff_views.social_publicar_ara,
        name="staff_social_publicar_ara",
    ),
    path(
        "staff/social/reset/",
        staff_views.social_reset,
        name="staff_social_reset",
    ),
    path(
        "staff/social/eliminar-instagram/",
        staff_views.social_eliminar_instagram,
        name="staff_social_eliminar_instagram",
    ),
    path(
        "staff/social/eliminar-remot/",
        staff_views.social_eliminar_remot,
        name="staff_social_eliminar_remot",
    ),
    path("staff/social/toggle/", staff_views.social_toggle, name="staff_social_toggle"),
    path("staff/social/fase/", staff_views.social_fase, name="staff_social_fase"),
    path(
        "staff/social/story-cap/",
        staff_views.social_story_cap,
        name="staff_social_story_cap",
    ),
    path(
        "staff/social/credentials/",
        staff_views.social_credentials_save,
        name="staff_social_credentials_save",
    ),
    path(
        "staff/social/credentials/test/",
        staff_views.social_credentials_test,
        name="staff_social_credentials_test",
    ),
    path(
        "staff/social/credentials/clear/",
        staff_views.social_credentials_clear,
        name="staff_social_credentials_clear",
    ),
    # Mastodon
    path(
        "staff/social/mastodon/",
        staff_views.social_mastodon_save,
        name="staff_social_mastodon_save",
    ),
    path(
        "staff/social/mastodon/test/",
        staff_views.social_mastodon_test,
        name="staff_social_mastodon_test",
    ),
    path(
        "staff/social/mastodon/clear/",
        staff_views.social_mastodon_clear,
        name="staff_social_mastodon_clear",
    ),
    # Bluesky
    path(
        "staff/social/bluesky/",
        staff_views.social_bluesky_save,
        name="staff_social_bluesky_save",
    ),
    path(
        "staff/social/bluesky/test/",
        staff_views.social_bluesky_test,
        name="staff_social_bluesky_test",
    ),
    path(
        "staff/social/bluesky/clear/",
        staff_views.social_bluesky_clear,
        name="staff_social_bluesky_clear",
    ),
    # Telegram
    path(
        "staff/social/telegram/",
        staff_views.social_telegram_save,
        name="staff_social_telegram_save",
    ),
    path(
        "staff/social/telegram/test/",
        staff_views.social_telegram_test,
        name="staff_social_telegram_test",
    ),
    path(
        "staff/social/telegram/clear/",
        staff_views.social_telegram_clear,
        name="staff_social_telegram_clear",
    ),
    path(
        "staff/social/slides/",
        staff_views.social_slides_for,
        name="staff_social_slides_for",
    ),
    path(
        "staff/social/render/<str:filename>/",
        staff_views.social_render_serve,
        name="staff_social_render_serve",
    ),
    # Feedback (user-filed corrections)
    path(
        "staff/feedback/",
        staff_views.feedback_list,
        name="staff_feedback_list",
    ),
    path(
        "staff/feedback/<int:pk>/resolve/",
        staff_views.feedback_resolve,
        name="staff_feedback_resolve",
    ),
    # Usuaris
    path("staff/usuaris/", staff_views.usuaris_list, name="staff_usuaris_list"),
    path(
        "staff/usuaris/<int:pk>/",
        staff_views.usuari_detail,
        name="staff_usuari_detail",
    ),
    path(
        "staff/usuaris/<int:pk>/toggle-actiu/",
        staff_views.usuari_toggle_actiu,
        name="staff_usuari_toggle_actiu",
    ),
    path(
        "staff/usuaris/<int:pk>/reset-2fa/",
        staff_views.usuari_reset_2fa,
        name="staff_usuari_reset_2fa",
    ),
    path(
        "staff/usuaris/<int:pk>/enviar-reset-password/",
        staff_views.usuari_enviar_reset_password,
        name="staff_usuari_enviar_reset_password",
    ),
    path(
        "staff/usuaris/<int:pk>/reenviar-verificacio/",
        staff_views.usuari_reenviar_verificacio,
        name="staff_usuari_reenviar_verificacio",
    ),
    path(
        "staff/usuaris/<int:pk>/esborrar/",
        staff_views.usuari_esborrar,
        name="staff_usuari_esborrar",
    ),
    # ── HomePage feed (Sprint I) ──
    path("stats/", home_views.stats, name="home_stats"),
    # Sprint I bis: replaced "nova de la setmana" with "destacada
    # (most-climbed)" semantics. URL renamed; no legacy alias kept
    # because the SPA bundle is rebuilt in lockstep.
    path(
        "top/canco-destacada/",
        home_views.top_canco_destacada,
        name="home_canco_destacada",
    ),
    path(
        "artistes/destacat/",
        home_views.artista_destacat,
        name="home_artista_destacat",
    ),
    path(
        "artistes/descoberta/",
        home_views.artistes_descoberta,
        name="home_artistes_descoberta",
    ),
    # Albums list (Sprint I) — placed before any /albums/<slug>/ to keep
    # the URL resolver from misinterpreting "list" as a slug.
    path("albums/", album_views.album_list, name="album_list"),
    # Ranking (top 40 per territory + week)
    path("top/", top_views.ranking, name="top"),
    # Legacy public path → permanent redirect to the canonical /api/v1/top/.
    # GET-only endpoint, so 301 with query-string preservation is safe.
    path(
        "ranking/",
        RedirectView.as_view(pattern_name="api:top", permanent=True, query_string=True),
        name="ranking",
    ),
    # Artistes
    path("artistes/", artistes_views.artistes_list, name="artistes_list"),
    path("artistes/<slug:slug>/", artistes_views.artista_detail, name="artista_detail"),
    # Albums
    path("albums/<slug:slug>/", album_views.album_detail, name="album_detail"),
    # Cançons
    path("cancons/<slug:slug>/", canco_views.canco_detail, name="canco_detail"),
    path(
        "cancons/<slug:slug>/top-breakdown/",
        canco_views.canco_top_breakdown,
        name="canco_top_breakdown_public",
    ),
    # Mapa (existing + drill-down)
    path("mapa/artistes/", mapa_views.mapa_artistes, name="mapa_artistes"),
    path("mapa/stats/", mapa_views.mapa_stats, name="mapa_stats"),
    path(
        "mapa/municipi-artistes/",
        mapa_views.mapa_municipi_artistes,
        name="mapa_municipi_artistes",
    ),
    path(
        "mapa/artistes-top/",
        mapa_views.mapa_artistes_top,
        name="mapa_artistes_top",
    ),
    # Location API — reference data, no auth required
    path("localitzacio/territoris/", mapa_views.api_territoris, name="api_territoris"),
    path("localitzacio/comarques/", mapa_views.api_comarques, name="api_comarques"),
    path("localitzacio/municipis/", mapa_views.api_municipis, name="api_municipis"),
    path(
        "localitzacio/municipi-lookup/",
        mapa_views.api_municipi_lookup,
        name="api_municipi_lookup",
    ),
    # Image upload (publication editor + profile photo)
    path("upload/imatge/", comunitat_views.upload_imatge, name="upload_imatge"),
    # Missatgeria interna
    path(
        "missatges/",
        comunitat_views.missatges_inbox,
        name="missatges_inbox",
    ),
    path(
        "missatges/nou/",
        comunitat_views.missatge_crear,
        name="missatge_crear",
    ),
    path(
        "missatges/amb/<int:altre_pk>/",
        comunitat_views.missatges_amb_usuari,
        name="missatges_amb_usuari",
    ),
    # Comentaris a publicacions
    path(
        "comunitat/publicacions/<int:pk>/comentaris/",
        comunitat_views.publicacio_comentaris,
        name="publicacio_comentaris",
    ),
    path(
        "comunitat/comentaris/<int:pk>/",
        comunitat_views.comentari_esborrar,
        name="comentari_esborrar",
    ),
    # ── Grup C · Community platform ──
    # User profile (own, authenticated)
    path(
        "compte/perfil-usuari/",
        comunitat_views.perfil_usuari,
        name="compte_perfil_usuari",
    ),
    # Directori (registered users only)
    path("comunitat/directori/", comunitat_views.directori, name="comunitat_directori"),
    # Publicacions feed (authenticated view) + public-only feed
    path(
        "comunitat/publicacions/",
        comunitat_views.publicacions,
        name="comunitat_publicacions",
    ),
    path(
        "comunitat/publicacions/<int:pk>/",
        comunitat_views.publicacio_detail,
        name="comunitat_publicacio_detail",
    ),
    path(
        "comunitat/publicacions-publiques/",
        comunitat_views.publicacions_publiques,
        name="comunitat_publicacions_publiques",
    ),
    # Staff moderation surfaces
    path(
        "staff/publicacions/",
        comunitat_views.staff_publicacions,
        name="staff_publicacions",
    ),
    path(
        "staff/publicacions/<int:pk>/decidir/",
        comunitat_views.staff_publicacio_decidir,
        name="staff_publicacio_decidir",
    ),
    path(
        "staff/directori-usuaris/",
        comunitat_views.staff_directori_usuaris,
        name="staff_directori_usuaris",
    ),
    path(
        "staff/directori-usuaris/<int:usuari_id>/toggle/",
        comunitat_views.staff_directori_toggle_visible,
        name="staff_directori_toggle_visible",
    ),
]
