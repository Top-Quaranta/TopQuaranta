from django.contrib.sitemaps.views import index as sitemap_index
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from web.feeds import novetats_feed, top_feed
from web.seo import ogimage as seo_ogimage
from web.seo import views as seo_views
from web.sitemaps import sitemaps

# Post Sprint-4 + cleanup: Django serves only API, auth flows that
# aren't in React yet (2FA, registre, email activation) and the two
# SEO files. Everything else at the domain root is served by Caddy
# from the React dist bundle and is unreachable via Django.
urlpatterns = [
    path("api/v1/", include("web.api.urls")),
    path("compte/", include("comptes.urls")),
    # SEO surfaces. Sprint S Block B (2026-05-06): expanded to a
    # proper sitemap-index referencing per-entity sub-sitemaps so
    # crawlers can fetch only the slice they care about.
    path(
        "sitemap.xml",
        sitemap_index,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.index",
    ),
    path(
        "sitemap-<section>.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path(
        "robots.txt",
        TemplateView.as_view(
            template_name="web/robots.txt",
            content_type="text/plain",
        ),
    ),
    # IndexNow ownership verification. Bing/Yandex GET the key
    # file at `https://<host>/<key>.txt` and check it equals the
    # `key` we submit alongside URLs. See web/seo/indexnow.py.
    path(
        "8f4c2e5b3a9d7c1f6e0b8a5d4c2e9f7b.txt",
        TemplateView.as_view(
            template_name="seo/indexnow_key.txt",
            content_type="text/plain",
        ),
    ),
    # Bing Webmaster Tools ownership verification. Bing GETs
    # `https://<host>/BingSiteAuth.xml` and checks the <user> code.
    path(
        "BingSiteAuth.xml",
        TemplateView.as_view(
            template_name="seo/bingsiteauth.xml",
            content_type="application/xml",
        ),
    ),
    # Atom feeds. Caddy passes /rss/* through to Django (see
    # deploy/Caddyfile).
    path("rss/top.xml", top_feed, name="rss_top"),
    path("rss/novetats.xml", novetats_feed, name="rss_novetats"),
    # ────────────────────────────────────────────────────────────────
    # SEO / SSR surface. Caddy reverse-proxies these paths to Django
    # only when the request UA matches `@bot` (see deploy/Caddyfile).
    # Humans with a real browser keep going to the React SPA. Both
    # render from the same data — see web/seo/meta.py.
    # ────────────────────────────────────────────────────────────────
    path("", seo_views.homepage_seo, name="seo_homepage"),
    path("top", seo_views.top_seo, name="seo_top"),
    path("artistes", seo_views.artistes_list_seo, name="seo_artistes"),
    path("artista/<slug:slug>", seo_views.artista_seo, name="seo_artista"),
    path("artista/<slug:slug>/", seo_views.artista_seo),
    path("album/<slug:slug>", seo_views.album_seo, name="seo_album"),
    path("album/<slug:slug>/", seo_views.album_seo),
    path("canco/<slug:slug>", seo_views.canco_seo, name="seo_canco"),
    path("canco/<slug:slug>/", seo_views.canco_seo),
    path("mapa", seo_views.mapa_seo, name="seo_mapa"),
    path("com-funciona", seo_views.com_funciona_seo, name="seo_com_funciona"),
    # Long-tail SEO surfaces (Sprint S Block C).
    path(
        "top/<str:territori>/setmana/<str:year_week>",
        seo_views.top_historic_seo,
        name="seo_top_historic",
    ),
    path(
        "territori/<str:codi>",
        seo_views.territori_seo,
        name="seo_territori",
    ),
    path(
        "comarca/<slug:slug>",
        seo_views.comarca_seo,
        name="seo_comarca",
    ),
    path(
        "decada/<str:decada>",
        seo_views.decada_seo,
        name="seo_decada",
    ),
    path(
        "genere/<slug:slug>",
        seo_views.genere_seo,
        name="seo_genere",
    ),
    # SPA Helmet hook — matches the SSR templates exactly.
    path(
        "api/v1/seo/<str:entity>/",
        seo_views.seo_api,
        {"slug": ""},
        name="seo_api_root",
    ),
    path(
        "api/v1/seo/<str:entity>/<slug:slug>/",
        seo_views.seo_api,
        name="seo_api",
    ),
    # Dynamic Open Graph card images (1200x630) per entity.
    path("og/home.png", seo_ogimage.serve_og, {"kind": "home"}),
    path("og/default.png", seo_ogimage.serve_og, {"kind": "default"}),
    path(
        "og/top/<str:slug>",
        seo_ogimage.serve_og,
        {"kind": "top"},
        name="og_top",
    ),
    path(
        "og/artista/<str:slug>",
        seo_ogimage.serve_og,
        {"kind": "artista"},
        name="og_artista",
    ),
    path(
        "og/album/<str:slug>",
        seo_ogimage.serve_og,
        {"kind": "album"},
        name="og_album",
    ),
    path(
        "og/canco/<str:slug>",
        seo_ogimage.serve_og,
        {"kind": "canco"},
        name="og_canco",
    ),
]

# S13: custom branded error pages (only used when DEBUG=False).
handler404 = "web.views.handler_404"
handler500 = "web.views.handler_500"
handler403 = "web.views.handler_403"
