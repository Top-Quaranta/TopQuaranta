"""Read back which IG collaborator invitations were actually accepted.

# Spec: docs/architecture/social.md

ADR-0015 §5.5 closed the API route and left acceptance as a manual
click in the staff panel. Nobody clicked: on 2026-09-26 six of the nine
real acceptances were recorded as `caducada` or `pendent`, and four of
those artists were serving a 90-day cooldown for a collaboration they
had in fact accepted.

The API is still closed (`collaborators` is absent as field and as edge
on graph.instagram.com v19/v21/v23 — re-verified 2026-09-26), but an
accepted collaboration is *public*: it is the co-author line in the post
header, and `instagram.com/p/<codi>/embed/captioned/` serves that header
rendered server-side, with no session and no credentials. So we read the
public page.

**We only ever confirm, never discover.** The header is intersected with
the usernames we invited for that exact media, and nothing outside that
set can produce an acceptance. Two consequences, both deliberate:

  - the caption cannot confirm anything. Artists are routinely `@`-ed in
    the caption of the very post they were invited to, so a whole-page
    match would mark every invitation accepted. We read the header
    segment alone (`_capcalera`), and the test that matters asserts a
    caption mention is NOT enough.
  - a parse we cannot read is a no-op, never a rejection. This command
    has exactly one transition, `→ acceptada`, mirroring the staff
    button; expiry stays with `pollar_colaboracions_ig`, and "no manual
    reject" (ADR-0015 §5.5) still holds.

Instagram serves a stripped shell to a request without ordinary browser
headers (verified: 642 KB of chrome and zero content). `_CAPCALERES` is
that ordinary set, nothing more.
"""

from __future__ import annotations

import html as htmllib
import logging
import re
import time
from datetime import timedelta

import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ranking.models import ConfiguracioGlobal
from social import instagram_client as ig
from social.models import InvitacioColaboracioIG

logger = logging.getLogger(__name__)

# How far back we keep re-reading. `pendent` rows are the point; a
# recently `caducada` one is worth a second look because the expiry pass
# fires on our silence, not on the artist's. Past this there is nothing
# to rescue and the pool would grow without bound.
DIES_ENRERE = 60

# Courtesy pause between posts. We fetch one public page per post, once
# a day; there is no reason to go faster.
PAUSA_S = 0.5

_CAPCALERES = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ca-ES,ca;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

_RE_SCRIPT = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
_RE_TAG = re.compile(r"<[^>]+>")
# The header runs from the page title to the follower count / profile
# link; the caption starts after it. Anchoring on both ends is what
# keeps the caption out.
_RE_CAPCALERA = re.compile(
    r"Instagram\s+(.*?)\s+(?:[\d.,]+\s+followers|View profile)", re.S
)
_RE_ALTRES = re.compile(r"\band\s+\d+\s+others?\b", re.I)


def _capcalera(html: str) -> str | None:
    """The post header as flat text («topquaranta and cantautoret»), or
    None when the page did not render one (blocked, deleted, changed)."""
    t = _RE_SCRIPT.sub(" ", html)
    t = _RE_TAG.sub(" ", t)
    t = htmllib.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    m = _RE_CAPCALERA.search(t)
    return m.group(1).strip() if m else None


def _coautors(html: str, convidats: set[str]) -> tuple[set[str] | None, bool]:
    """`(co-authors among `convidats`, header was truncated)`.

    `None` means the header could not be read at all — the caller treats
    that as "no information", never as a rejection. The truncation flag
    is Instagram collapsing several co-authors into «and 2 others»: the
    names we cannot see stay unconfirmed and the run says so out loud.
    """
    cap = _capcalera(html)
    if cap is None:
        return None, False
    trobats = {
        u
        for u in convidats
        if re.search(
            rf"(?<![A-Za-z0-9._]){re.escape(u)}(?![A-Za-z0-9._])", cap, re.IGNORECASE
        )
    }
    return trobats, bool(_RE_ALTRES.search(cap))


def _descarrega(url: str) -> str | None:
    """The embed page of a permalink, or None on any network/HTTP error."""
    try:
        r = requests.get(
            url.rstrip("/") + "/embed/captioned/",
            headers=_CAPCALERES,
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.warning("embed %s: %s", url, exc)
        return None
    if not r.ok:
        logger.warning("embed %s: HTTP %s", url, r.status_code)
        return None
    return r.text


class Command(BaseCommand):
    help = (
        "Llig del post públic quines col·laboracions d'Instagram s'han "
        "acceptat i ho registra (ADR-0015 §5.5, revisat 2026-09-26)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dies", type=int, default=DIES_ENRERE)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        cfg = ConfiguracioGlobal.load()
        if not cfg.ig_collaboradors_actiu:
            self.stdout.write("ig_collaboradors_actiu=False → no-op.")
            self.stdout.write("WORK_DONE=0")
            return

        dry = opts["dry_run"]
        des_de = timezone.now() - timedelta(days=opts["dies"])
        pendents = list(
            InvitacioColaboracioIG.objects.exclude(
                estat=InvitacioColaboracioIG.ESTAT_ACCEPTADA
            )
            .filter(data_invitacio__gte=des_de)
            .select_related("artista")
        )
        per_media: dict[str, list[InvitacioColaboracioIG]] = {}
        for inv in pendents:
            per_media.setdefault(inv.ig_media_id, []).append(inv)

        self.stdout.write(
            f"Invitacions sense resoldre: {len(pendents)} "
            f"en {len(per_media)} publicacions (últims {opts['dies']} dies)"
        )

        marcades = 0
        illegibles = 0
        truncades = 0
        for i, (media_id, invs) in enumerate(sorted(per_media.items())):
            if i:
                time.sleep(PAUSA_S)
            url = ig.permalink(media_id)
            if not url:
                illegibles += 1
                continue
            html = _descarrega(url)
            if html is None:
                illegibles += 1
                continue
            convidats = {inv.username_snapshot for inv in invs if inv.username_snapshot}
            trobats, truncat = _coautors(html, convidats)
            if trobats is None:
                illegibles += 1
                logger.warning("capçalera il·legible a %s (%s)", url, media_id)
                continue
            if truncat:
                truncades += 1
                logger.warning(
                    "capçalera truncada («and N others») a %s: els co-autors "
                    "que no es veuen queden sense confirmar",
                    url,
                )
            for inv in invs:
                if inv.username_snapshot not in trobats:
                    continue
                anterior = inv.estat
                self.stdout.write(
                    f"  {inv.artista.nom} / {inv.username_snapshot}: "
                    f"{anterior} → acceptada  ({url})"
                )
                marcades += 1
                if dry:
                    continue
                with transaction.atomic():
                    inv.estat = InvitacioColaboracioIG.ESTAT_ACCEPTADA
                    inv.data_resolucio = timezone.now()
                    inv.save(update_fields=["estat", "data_resolucio"])

        prefix = "[dry-run] " if dry else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Acceptacions registrades: {marcades} · "
                f"publicacions il·legibles: {illegibles} · "
                f"capçaleres truncades: {truncades}"
            )
        )
        self.stdout.write(f"WORK_DONE={marcades}")
