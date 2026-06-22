"""Atom feeds for the public site.

Two feeds:
  /rss/top.xml      — last 12 weeks of the PPCC top, one item per week
                      with the top-10 entries inline.
  /rss/novetats.xml — last 30 days of newly verified releases.

Both honour `ConfiguracioGlobal.rss_actiu` — a hard kill switch that
returns 503 (Service Unavailable) if flipped to False. Useful for
emergencies; under normal operation it stays True.

We use Django's `Feed` class (Atom 1.0) instead of hand-rolled XML
because:
  * It auto-handles ETag/Last-Modified for free, which matters for
    feed readers that poll every hour.
  * The `Atom1Feed` writer escapes Unicode + special chars properly
    (the legacy Catalan chars are common in artist names).
"""

from __future__ import annotations

import datetime

from django.contrib.syndication.views import Feed
from django.http import HttpResponse
from django.utils.feedgenerator import Atom1Feed

from music.models import Canco
from ranking.models import ConfiguracioGlobal, TopSetmanal

# Per-feed item cap — keep payloads small and predictable.
TOP_WEEKS = 12
TOP_ENTRIES_PER_WEEK = 10
NOVETATS_DAYS = 30
NOVETATS_MAX = 50

SITE = "https://www.topquaranta.cat"


def _kill_switch_or(view, *, name: str):
    """Wrap a `Feed` instance in a callable that honours the shared
    distribution gate `ConfiguracioGlobal.pot_publicar("rss")` (the
    master switch `distribucio_activa` AND `rss_actiu`) — returns 503
    when off.

    `Feed.__call__` is the regular view entry point; we just front
    it with a kill-switch check.
    """

    def wrapped(request, *a, **kw):
        if not ConfiguracioGlobal.load().pot_publicar("rss"):
            return HttpResponse(
                "RSS temporalment desactivat", status=503, content_type="text/plain"
            )
        return view(request, *a, **kw)

    wrapped.__name__ = name
    return wrapped


class _AtomNoLink(Atom1Feed):
    """Tiny tweak: don't emit a `<link rel='hub'>` (we don't run a
    PubSubHubbub hub) and use UTF-8 explicitly."""

    content_type = "application/atom+xml; charset=utf-8"


class TopFeed(Feed):
    """Weekly PPCC top — one Atom entry per setmana, with the top-10
    rendered as plain HTML inside the entry body."""

    feed_type = _AtomNoLink
    title = "TopQuaranta — Top setmanal"
    description = (
        "Els 10 primers del Top 40 PPCC de cada setmana. Música en català, "
        "rànquing setmanal independent."
    )
    language = "ca"

    def link(self):
        return f"{SITE}/top"

    def feed_url(self):
        return f"{SITE}/rss/top.xml"

    def items(self):
        # Order by setmana desc; pick the most recent N. We list ONLY
        # the PPCC chart — territorials would multiply item count and
        # most readers want "the headline" feed.
        setmanes = list(
            TopSetmanal.objects.filter(territori="PPCC")
            .values_list("setmana", flat=True)
            .distinct()
            .order_by("-setmana")[:TOP_WEEKS]
        )
        # Pre-fetch all rows for those setmanes in one shot to avoid
        # N+1 lookups in `item_description`.
        rows = (
            TopSetmanal.objects.filter(territori="PPCC", setmana__in=setmanes)
            .select_related("canco", "canco__artista")
            .order_by("setmana", "posicio")
        )
        per_week: dict[datetime.date, list] = {}
        for r in rows:
            per_week.setdefault(r.setmana, []).append(r)
        return [(s, per_week.get(s, [])) for s in setmanes]

    def item_title(self, item):
        from music.dates import project_week_number

        setmana, _ = item
        # The TQ-week opens on Saturday = setmana + 5d.
        sat = setmana + datetime.timedelta(days=5)
        return f"Top — Setmana {project_week_number(sat)}"

    def item_link(self, item):
        return f"{SITE}/top"

    def item_description(self, item):
        _setmana, entries = item
        if not entries:
            return "No hi ha cap entrada per a aquesta setmana."
        lines = ["<ol>"]
        for r in entries[:TOP_ENTRIES_PER_WEEK]:
            canco = r.canco
            artista = canco.artista if canco else None
            lines.append(
                f"<li><strong>{canco.nom if canco else '—'}</strong>"
                f" — {artista.nom if artista else '—'}</li>"
            )
        lines.append("</ol>")
        return "".join(lines)

    def item_pubdate(self, item):
        from django.utils.timezone import make_aware

        setmana, _ = item
        # Publish date = the Saturday this top covers, at 09:00 UTC.
        sat = setmana + datetime.timedelta(days=5)
        return make_aware(datetime.datetime.combine(sat, datetime.time(9, 0)))

    def item_guid(self, item):
        setmana, _ = item
        return f"{SITE}/top?setmana={setmana.isoformat()}"


class NovetatsFeed(Feed):
    """New releases (singles + albums) verified in the last 30 days,
    one item per release."""

    feed_type = _AtomNoLink
    title = "TopQuaranta — Noves cançons en català"
    description = (
        "Noves cançons i àlbums en català detectats al sistema en els "
        "últims 30 dies."
    )
    language = "ca"

    def link(self):
        return f"{SITE}/"

    def feed_url(self):
        return f"{SITE}/rss/novetats.xml"

    def items(self):
        cutoff = datetime.date.today() - datetime.timedelta(days=NOVETATS_DAYS)
        # Use Canco (not Album) so the feed reflects what listeners
        # actually consume; also covers singles released without a
        # parent album row.
        return (
            Canco.objects.filter(
                verificada=True,
                activa=True,
                data_llancament__gte=cutoff,
            )
            .select_related("artista", "album")
            .order_by("-data_llancament", "-id")[:NOVETATS_MAX]
        )

    def item_title(self, c):
        artista = c.artista.nom if c.artista else "—"
        return f"{c.nom} — {artista}"

    def item_link(self, c):
        if c.slug:
            return f"{SITE}/canco/{c.slug}"
        return f"{SITE}/"

    def item_description(self, c):
        bits = []
        if c.album and c.album.nom and c.album.nom != c.nom:
            bits.append(f"Àlbum: <em>{c.album.nom}</em>")
        if c.data_llancament:
            bits.append(f"Llançada: {c.data_llancament.isoformat()}")
        return " · ".join(bits) or "Nova cançó en català."

    def item_pubdate(self, c):
        from django.utils.timezone import make_aware

        if c.data_llancament:
            return make_aware(
                datetime.datetime.combine(c.data_llancament, datetime.time(0, 0))
            )
        return None

    def item_guid(self, c):
        if c.slug:
            return f"{SITE}/canco/{c.slug}"
        return f"{SITE}/canco/{c.pk}"


# Public view callables (urlconf imports these). Wrap the Feed
# instances with the kill-switch decorator.
top_feed = _kill_switch_or(TopFeed(), name="rss_top")
novetats_feed = _kill_switch_or(NovetatsFeed(), name="rss_novetats")
