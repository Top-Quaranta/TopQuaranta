"""Seed Instagram suggestions for artists entering the staff queue.

The steady state this exists for: once the backlog is cleaned, the only
artists in `/staff/artistes/sense-instagram` are the ones who just
released a song — and by the time the operator opens the queue, each row
should already carry a candidate to eyeball, not a blank Google search.

Sources, in order of trust, first hit wins:

  1. the artist's OWN pages (web_url / bandcamp_url) — the artist
     linking themselves;
  2. Viasona — an aggregator, NOT a curated source (caught 2026-08-12:
     of 85 YouTube links it carried, only 28 survived corroboration).
     Good enough for a *suggestion* precisely because a human eyeballs
     the profile before accepting; never good enough to apply.

Suggestions only — this command never writes `instagram_url`. Artists
with a suggestion already, a URL, or `instagram_revisat=True` are left
alone. Dismissed candidates live in `instagram_suggerits_descartats`
and are never proposed again — clearing the field alone was NOT enough
(caught 2026-08-13: the nightly run re-found the same handles at the
same sources and put them straight back).

    python manage.py suggerir_instagram [--limit N] [--dry-run]

# Spec: docs/architecture/pipeline.md
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata

import requests
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q

from music.models import Artista, Canco

logger = logging.getLogger(__name__)

UA = {
    "User-Agent": "Mozilla/5.0 (compatible; TopQuaranta/1.0; +https://topquaranta.cat)"
}
IG_RE = re.compile(r"instagram\.com/([\w.]+)", re.I)
IG_JUNK = {"p", "reel", "reels", "explore", "stories", "accounts", "tv", "viasona"}
TIMEOUT = 8


def _slug(nom: str) -> str:
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("'", "").replace("·", "").replace("&", "i")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _handles_de(url: str) -> list[str]:
    try:
        html = requests.get(url, headers=UA, timeout=TIMEOUT).text[:250000]
    except requests.RequestException:
        return []
    return [
        h.rstrip(".").lower()
        for h in dict.fromkeys(IG_RE.findall(html))
        if h.lower() not in IG_JUNK and len(h) > 2 and not h.startswith("viasona")
    ]


class Command(BaseCommand):
    help = "Sembra suggeriments d'Instagram per als artistes pendents de la cua."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=40)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts) -> None:
        viva = {"verificada": True, "activa": True}
        pendents = (
            Artista.objects.filter(
                aprovat=True,
                instagram_revisat=False,
                instagram_suggerit="",
            )
            .filter(Q(instagram_url="") | Q(instagram_url__isnull=True))
            .filter(
                Q(Exists(Canco.objects.filter(artista=OuterRef("pk"), **viva)))
                | Q(Exists(Canco.objects.filter(artistes_col=OuterRef("pk"), **viva)))
            )
            # Newest artists first: the whole point is covering releases
            # before their "nous singles" post goes out.
            .order_by("-created_at")[: opts["limit"]]
        )

        sembrats = 0
        for a in pendents:
            descartats = {h.lower() for h in (a.instagram_suggerits_descartats or [])}
            handle = None
            font = ""
            for url in (a.web_url, a.bandcamp_url):
                if not url:
                    continue
                trobats = [h for h in _handles_de(url) if h not in descartats]
                if trobats:
                    handle, font = trobats[0], "el seu web"
                    break
                time.sleep(0.3)
            if handle is None:
                trobats = [
                    h
                    for h in _handles_de(f"https://www.viasona.cat/grup/{_slug(a.nom)}")
                    if h not in descartats
                ]
                if trobats:
                    handle, font = trobats[0], "viasona (agregador)"
                time.sleep(0.3)
            if handle is None:
                continue
            if opts["dry_run"]:
                self.stdout.write(f"  [dry] {a.nom} → @{handle} ({font})")
                continue
            a.instagram_suggerit = handle[:64]
            a.save(update_fields=["instagram_suggerit"])
            logger.info("suggeriment IG per a %s: @%s (%s)", a.nom, handle, font)
            sembrats += 1

        self.stdout.write(self.style.SUCCESS(f"Suggeriments sembrats: {sembrats}"))
        self.stdout.write(f"WORK_DONE={sembrats}")
