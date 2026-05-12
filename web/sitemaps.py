"""SEO sitemaps for TopQuaranta.

Sprint S Block B (2026-05-06): expanded from 5 static URLs to a
sitemap-index referencing 6 sub-sitemaps that together cover every
indexable entity. Approximate total: ~2 k artistes + thousands of
albums + thousands of cançons + 8 territoris + ~52 weekly tops × 8
territoris ≈ many thousands of URLs.

Per Google's docs:
  - One sitemap-index references many sitemaps; each sitemap caps at
    50 000 URLs / 50 MiB. Django splits automatically when a single
    Sitemap subclass exceeds the limit.
  - `lastmod` is the strongest signal we send crawlers about when
    to recrawl. Source: `updated_at` (Sprint S Block A added it
    across Artista / Album / Canco; smart-backfilled by migration
    0064).

Indexability rules — must match `web/seo/views.py`:
  * Artista — `aprovat=True` AND ≥1 verified active cançó.
  * Album   — parent artista approved AND `descartat=False` AND
              ≥1 verified active cançó.
  * Canco   — `verificada=True, activa=True`.
"""

from __future__ import annotations

import datetime

from django.contrib.sitemaps import Sitemap

from music.constants import TERRITORIS_SITEMAP
from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal


class StaticSitemap(Sitemap):
    """Top-level entry points exposed by the SPA + the SEO views."""

    changefreq = "weekly"
    priority = 0.8
    protocol = "https"

    URLS = [
        ("/", 1.0, "daily"),
        ("/top", 1.0, "daily"),
        ("/artistes", 0.8, "weekly"),
        ("/mapa", 0.6, "weekly"),
        ("/com-funciona", 0.5, "monthly"),
        ("/legal/privacitat", 0.3, "yearly"),
        ("/legal/termes", 0.3, "yearly"),
        ("/legal/cookies", 0.3, "yearly"),
    ]

    def items(self):
        return self.URLS

    def location(self, obj):
        return obj[0]

    def priority(self, obj):
        return obj[1]

    def changefreq(self, obj):
        return obj[2]


class ArtistesSitemap(Sitemap):
    """One row per approved artiste that has at least one verified
    active cançó. Profiles without indexable content 404 in the SEO
    view, so listing them here would trip 'sitemap contains URLs
    blocked' warnings in GSC."""

    changefreq = "weekly"
    priority = 0.7
    protocol = "https"

    def items(self):
        return (
            Artista.objects.public()
            .filter(cancons__verificada=True, cancons__activa=True)
            .distinct()
            .only("slug", "updated_at")
        )

    def location(self, obj):
        return f"/artista/{obj.slug}"

    def lastmod(self, obj):
        return obj.updated_at


class AlbumsSitemap(Sitemap):
    """One row per non-discarded album whose parent artiste is
    approved. The destination view returns 404 if either gate
    flips, so we mirror the same filter here to keep the sitemap
    truthful and avoid 'sitemap contains URLs which are blocked'
    GSC warnings."""

    changefreq = "weekly"
    priority = 0.6
    protocol = "https"
    limit = 50_000  # Django default; explicit so it's reviewable

    def items(self):
        return (
            Album.objects.filter(
                descartat=False,
                artista__aprovat=True,
                cancons__verificada=True,
                cancons__activa=True,
            )
            .distinct()
            .only("slug", "updated_at")
        )

    def location(self, obj):
        return f"/album/{obj.slug}"

    def lastmod(self, obj):
        return obj.updated_at


class CanconsSitemap(Sitemap):
    """One row per verified active cançó."""

    changefreq = "weekly"
    priority = 0.5
    protocol = "https"
    limit = 50_000

    def items(self):
        return Canco.objects.filter(verificada=True, activa=True).only(
            "slug", "updated_at"
        )

    def location(self, obj):
        return f"/canco/{obj.slug}"

    def lastmod(self, obj):
        return obj.updated_at


class TerritorisSitemap(Sitemap):
    """`/top?territori=<codi>` per territori — distinct landing
    pages for each weekly chart."""

    changefreq = "daily"
    priority = 0.7
    protocol = "https"

    def items(self):
        return list(TERRITORIS_SITEMAP)

    def location(self, codi):
        return f"/top?territori={codi}"


class TopHistoricSitemap(Sitemap):
    """Last 52 weeks × 8 territoris of historical top — long-tail
    value for queries like 'top música català setmana 35 2025'.

    The URL pattern `/top/<territori>/setmana/<YYYY-WW>` is
    introduced in Block C; until then this is forward-compatible
    (the link 404s for now, which is fine — Google retries).
    """

    changefreq = "yearly"  # the row never changes once locked
    priority = 0.4
    protocol = "https"

    def items(self):
        cutoff = datetime.date.today() - datetime.timedelta(days=365)
        rows = (
            TopSetmanal.objects.filter(setmana__gte=cutoff)
            .values_list("territori", "setmana")
            .distinct()
            .order_by("-setmana", "territori")
        )
        return list(rows)

    def location(self, obj):
        territori, setmana = obj
        return f"/top/{territori}/setmana/{setmana.strftime('%G-W%V')}"

    def lastmod(self, obj):
        _, setmana = obj
        return setmana


class TerritorisLandingSitemap(Sitemap):
    """`/territori/<codi>` landing pages — 8 long-tail entry points
    that aggregate artistes by territori (Sprint S Block C)."""

    changefreq = "weekly"
    priority = 0.6
    protocol = "https"

    def items(self):
        return list(TERRITORIS_SITEMAP)

    def location(self, codi):
        return f"/territori/{codi}"


class ComarquesSitemap(Sitemap):
    """`/comarca/<slug>` for every comarca with ≥3 approved artistes
    (Sprint S Block C). Comarca isn't a model — it's a free-text
    field on Municipi — so we slugify distinct values on the fly."""

    changefreq = "monthly"
    priority = 0.5
    protocol = "https"

    def items(self):
        from collections import Counter

        from django.utils.text import slugify

        from music.models import Municipi

        # Count approved artistes per comarca; expose only those
        # with ≥3 to avoid thin pages.
        rows = Artista.objects.public().values_list(
            "localitats__municipi__comarca", flat=True
        )
        counter = Counter(c for c in rows if c)
        out = []
        seen = set()
        for nom, n in counter.items():
            if n < 3:
                continue
            slug = slugify(nom)
            if slug and slug not in seen:
                seen.add(slug)
                out.append(slug)
        return sorted(out)

    def location(self, slug):
        return f"/comarca/{slug}"


class DecadesSitemap(Sitemap):
    """`/decada/<XXX0>` for every decade with ≥5 verified cançons
    (Sprint S Block C)."""

    changefreq = "monthly"
    priority = 0.4
    protocol = "https"

    def items(self):
        from django.db.models import Count

        years = Canco.objects.filter(
            verificada=True, activa=True, data_llancament__isnull=False
        ).values_list("data_llancament__year", flat=True)
        from collections import Counter

        decades = Counter()
        for y in years:
            if y:
                decades[(y // 10) * 10] += 1
        return [str(d) for d, n in sorted(decades.items()) if n >= 5]

    def location(self, decada):
        return f"/decada/{decada}"


class GeneresSitemap(Sitemap):
    """`/genere/<slug>` for every canonical genre with ≥3 approved
    artistes (Sprint S Bloc D, 2026-05-06)."""

    changefreq = "weekly"
    priority = 0.5
    protocol = "https"

    def items(self):
        from django.db.models import Count

        rows = (
            Artista.objects.public()
            .exclude(genere_canonical="")
            .values("genere_canonical")
            .annotate(n=Count("id"))
            .filter(n__gte=3)
        )
        return [r["genere_canonical"] for r in rows]

    def location(self, slug):
        return f"/genere/{slug}"


sitemaps = {
    "static": StaticSitemap,
    "artistes": ArtistesSitemap,
    "albums": AlbumsSitemap,
    "cancons": CanconsSitemap,
    "territoris": TerritorisSitemap,
    "territoris_landing": TerritorisLandingSitemap,
    "comarques": ComarquesSitemap,
    "decades": DecadesSitemap,
    "generes": GeneresSitemap,
    "top_historic": TopHistoricSitemap,
}
