"""Bulk newsletter sender for the weekly top.

Called from `publicar_canal --channel newsletter`. Iterates every
`Usuari` with `vol_newsletter=True`, renders the HTML template,
includes a personalised unsubscribe link, and sends in batches via
the configured SMTP backend (cdmon in production).

The unsubscribe URL uses the same `signing.dumps(..., salt=
"newsletter-baixa")` token + `/api/v1/compte/baixa-newsletter/`
endpoint that `web/api/compte_views.py` already exposes — Sprint J
shipped that part, this file just consumes it.

Per-user errors are logged but never abort the run; the cron has
to keep going so a single bouncing address doesn't block the rest.
"""

from __future__ import annotations

import datetime
import logging

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from comptes.models import Usuari
from music.dates import project_week_number
from social.captions import TERRITORI_NOM, utm_url

logger = logging.getLogger(__name__)

UNSUB_BASE = f"{settings.SITE_URL}/api/v1/compte/baixa-newsletter/"
FROM_EMAIL = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@topquaranta.cat")


def _unsub_url(user: Usuari) -> str:
    token = signing.dumps({"u": user.pk}, salt="newsletter-baixa")
    return f"{UNSUB_BASE}?token={token}"


def send_top_newsletter(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    publish_date: datetime.date,
    entries: list[dict],
) -> str:
    """Send the weekly newsletter to every opted-in user. Returns
    a summary string (e.g. "sent=42 fail=1") that the calling
    command stores in the SocialPost.metadata for traceability.
    """
    territori_nom = TERRITORI_NOM.get(territori, territori or "")
    sat = setmana + datetime.timedelta(days=5)
    project_week = project_week_number(sat)
    if tipus in ("nous_albums", "nous_singles"):
        title = "Nous àlbums" if tipus == "nous_albums" else "Nous singles"
        heading = f"{title} d'aquesta setmana"
        subject = f"TopQuaranta · {title} · setmana {project_week}"
    else:
        heading = f"Top {territori_nom} · setmana {project_week}"
        subject = f"TopQuaranta · Top {territori_nom} · setmana {project_week}"

    # K1+ analytics: UTM-tag the "Veure el top complet" CTA so the
    # staff dashboard attributes the resulting landings to the
    # newsletter campaign instead of the bare-URL bucket. Same
    # convention as the other channels (`utm_url` in social.captions).
    top_url = utm_url(
        "newsletter",
        tipus,
        setmana,
        base=f"{settings.SITE_URL}/top",
        territori=territori,
    )
    # Narrative engine: compose the editorial paragraph block ONCE
    # per run (same for every recipient). The HTML template uses it
    # as a `narrative_html` block before the listing. Best-effort:
    # if the engine fails, the template falls back to its pre-list
    # legacy intro ("Aquesta setmana al Top de …"). The phrase ids
    # are NOT marked here — the calling command (`publicar_canal`)
    # handles `mark_used` from the engine result it gets, this is
    # purely for content.
    narrative_html = ""
    if tipus in ("top_ppcc", "top_territorial"):
        try:
            from social.narrative import detect_all
            from social.narrative.composers import newsletter as newsletter_composer

            scenarios = detect_all(territori, setmana)
            engine_out = newsletter_composer.compose(
                scenarios,
                entries,
                territori=territori,
                setmana=setmana,
            )
            # Wrap each paragraph in <p> for the email-safe HTML.
            paragraphs = [
                p.strip()
                for p in engine_out["narrative_part"].split("\n\n")
                if p.strip()
            ]
            # The first line is the "Top X · Setmana N" header — the
            # template's <h1> already shows that, skip it.
            if paragraphs and paragraphs[0].lower().startswith("top "):
                paragraphs = paragraphs[1:]
            narrative_html = "".join(
                f'<p style="margin:0 0 16px;color:#d4d4d4;line-height:1.55;">'
                f"{p}</p>"
                for p in paragraphs
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "newsletter narrative engine failed; falling back to legacy intro"
            )
            narrative_html = ""

    # Tasca B2: precompute `artistes_display` per entry so the
    # template doesn't need string surgery. `_join_artists_text`
    # owns the truncation rule (80 chars, whole-name drops, ellipsis
    # at the last fitting name).
    from social.captions import _join_artists_text

    entries_with_display = []
    for e in entries[:10]:
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        entries_with_display.append(
            {**e, "artistes_display": _join_artists_text(names, max_chars=80)}
        )

    qs = Usuari.objects.filter(perfil__vol_newsletter=True).select_related("perfil")
    sent = 0
    failed = 0
    for user in qs.iterator():
        if not user.email:
            continue
        try:
            html = render_to_string(
                "comptes/email_newsletter_top.html",
                {
                    "subject": subject,
                    "heading": heading,
                    "territori_nom": territori_nom or "Global",
                    "project_week": project_week,
                    "entries": entries_with_display,
                    "narrative_html": narrative_html,
                    "unsub_url": _unsub_url(user),
                    "top_url": top_url,
                },
            )
            text_body = strip_tags(html)
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=FROM_EMAIL,
                to=[user.email],
            )
            msg.attach_alternative(html, "text/html")
            # List-Unsubscribe header lets Gmail/Apple Mail surface
            # a one-click unsubscribe button — RFC 8058.
            msg.extra_headers["List-Unsubscribe"] = f"<{_unsub_url(user)}>"
            msg.extra_headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
            msg.send(fail_silently=False)
            sent += 1
        except Exception:  # noqa: BLE001
            logger.exception("newsletter send failed for user %s", user.pk)
            failed += 1

    return f"sent={sent} fail={failed}"
