from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from web.feeds import novetats_feed, top_feed
from web.sitemaps import sitemaps

# Post Sprint-4 + cleanup: Django serves only API, auth flows that
# aren't in React yet (2FA, registre, email activation) and the two
# SEO files. Everything else at the domain root is served by Caddy
# from the React dist bundle and is unreachable via Django.
urlpatterns = [
    path("api/v1/", include("web.api.urls")),
    path("compte/", include("comptes.urls")),
    # SEO surfaces.
    path(
        "sitemap.xml",
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
    # Atom feeds. Caddy passes /rss/* through to Django (see
    # deploy/Caddyfile).
    path("rss/top.xml", top_feed, name="rss_top"),
    path("rss/novetats.xml", novetats_feed, name="rss_novetats"),
]

# S13: custom branded error pages (only used when DEBUG=False).
handler404 = "web.views.handler_404"
handler500 = "web.views.handler_500"
handler403 = "web.views.handler_403"
