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
from comptes.newsletter_covers import album_cover_url, ensure_cover_downloaded
from comptes.newsletter_meta import derive_subject, trend_indicator
from comptes.newsletter_utm import build_newsletter_url
from music.dates import project_week_number
from social.captions import TERRITORI_NOM, _join_artists_text

logger = logging.getLogger(__name__)

UNSUB_BASE = f"{settings.SITE_URL}/api/v1/compte/baixa-newsletter/"
FROM_EMAIL = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@topquaranta.cat")
SITE = settings.SITE_URL.rstrip("/")

# Territorials shown as mini-cards (one per territori, the current #1).
_TERRITORIALS = ("CAT", "VAL", "BAL")
# Share buttons (channel → public profile URL).
_SHARE = {
    "instagram": "https://instagram.com/topquaranta",
    "mastodon": "https://mastodon.social/@topquaranta",
    "bluesky": "https://bsky.app/profile/topquaranta.bsky.social",
    "telegram": "https://t.me/topquaranta",
}


def _unsub_url(user: Usuari) -> str:
    token = signing.dumps({"u": user.pk}, salt="newsletter-baixa")
    return f"{UNSUB_BASE}?token={token}"


def _enrich_entry(e: dict, content: str, week: int, *, hero: bool, torna: bool) -> dict:
    """One top entry → template-ready row (cover, trend, UTM link)."""
    names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
    mida = 500 if hero else 250
    slug = e.get("canco_slug")
    link_base = f"{SITE}/canco/{slug}" if slug else f"{SITE}/top"
    ensure_cover_downloaded(e.get("album_deezer_id"), e.get("cover_url"))
    return {
        **e,
        "artistes_display": _join_artists_text(names, max_chars=80),
        "cover": album_cover_url(e.get("album_deezer_id"), mida),
        "trend": trend_indicator(
            e.get("posicio"), e.get("posicio_anterior"), is_return=torna
        ),
        "url": build_newsletter_url(link_base, content, week),
    }


def _territorial_cards(setmana: datetime.date, week: int) -> list[dict]:
    """Current-week #1 for CAT/VAL/BAL as mini-cards."""
    from social import payload

    cards = []
    for terr in _TERRITORIALS:
        data = payload.build_top(terr, setmana)
        if not data or not data["entries"]:
            continue
        top1 = data["entries"][0]
        names = top1.get("artistes_noms") or [top1.get("artista_nom") or "—"]
        ensure_cover_downloaded(top1.get("album_deezer_id"), top1.get("cover_url"))
        cards.append(
            {
                "territori": terr,
                "territori_nom": TERRITORI_NOM.get(terr, terr),
                "canco_nom": top1.get("canco_nom") or "—",
                "artistes_display": _join_artists_text(names, max_chars=60),
                "cover": album_cover_url(top1.get("album_deezer_id"), 250),
                "url": build_newsletter_url(
                    f"{SITE}/top?territori={terr}", f"territorial_{terr.lower()}", week
                ),
            }
        )
    return cards


def _novetats_cards(setmana: datetime.date, publish_date: datetime.date, week: int):
    """2-3 of the week's new releases (singles + albums merged)."""
    from social import payload

    items: list[dict] = []
    for tipus in ("nous_singles", "nous_albums"):
        data = payload.build_novetats(tipus, setmana, publish_date=publish_date)
        if data:
            items.extend(data["items"])
    cards = []
    for i, it in enumerate(items[:3], start=1):
        slug = it.get("artista_slug")
        link_base = f"{SITE}/artista/{slug}" if slug else f"{SITE}/"
        ensure_cover_downloaded(it.get("album_deezer_id"), it.get("cover_url"))
        cards.append(
            {
                "nom": it.get("nom") or "—",
                "artista_nom": it.get("artista_nom") or "—",
                "cover": album_cover_url(it.get("album_deezer_id"), 250),
                "url": build_newsletter_url(link_base, f"novetat_{i}", week),
            }
        )
    return cards


def _share_links(week: int) -> list[dict]:
    return [
        {
            "canal": canal,
            "url": build_newsletter_url(url, f"compartir_{canal}", week),
        }
        for canal, url in _SHARE.items()
    ]


def _build_top_context(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    publish_date: datetime.date,
    entries: list[dict],
) -> tuple[dict, str]:
    """Assemble the shared (per-run, recipient-independent) context for
    the weekly Global newsletter, plus the derived subject line.

    One newsletter per week, Global edition. The body carries: podi
    (#1-3), editorial paragraphs, top 4-10, territorial mini-cards,
    novetats mini-cards, share buttons. Every link is UTM-tagged."""
    territori_nom = TERRITORI_NOM.get(territori, territori or "")
    sat = setmana + datetime.timedelta(days=5)
    week = project_week_number(sat)

    # Scenarios drive both the editorial paragraphs and the subject;
    # a13 marks a returning #1 (TORNA trend override).
    hero = None
    narrative_html = ""
    torna_cancons: set = set()
    if tipus in ("top_ppcc", "top_territorial"):
        try:
            from social.narrative import detect_all
            from social.narrative.composers import newsletter as nl_composer

            scenarios = detect_all(territori, setmana)
            hero = scenarios[0] if scenarios else None
            # a13_top1_return is by definition about THIS week's #1, so a
            # single flag is enough (no canco_id matching against entries,
            # which don't carry the id).
            torna_cancons = {True for s in scenarios if s.code == "a13_top1_return"}
            engine_out = nl_composer.compose(
                scenarios, entries, territori=territori, setmana=setmana
            )
            paragraphs = [
                p.strip()
                for p in engine_out["narrative_part"].split("\n\n")
                if p.strip()
            ]
            if paragraphs and paragraphs[0].lower().startswith("top "):
                paragraphs = paragraphs[1:]
            narrative_html = "".join(
                f'<p class="np" style="margin:0 0 16px;line-height:1.6;">{p}</p>'
                for p in paragraphs
            )
        except Exception:  # noqa: BLE001
            logger.exception("newsletter narrative engine failed; legacy intro")

    subject = (
        derive_subject(hero, week)
        if hero is not None
        else (f"Setmana {week} · Top Global")
    )

    # Enriched top rows: podi (1-3) + the rest (4-10).
    rows = []
    for i, e in enumerate(entries[:10]):
        pos = e.get("posicio") or (i + 1)
        if pos <= 3:
            content = f"podi_{pos}"
        else:
            content = f"top_{pos}"
        rows.append(
            _enrich_entry(
                e,
                content,
                week,
                hero=(pos == 1),
                torna=(pos == 1 and bool(torna_cancons)),
            )
        )
    podi = rows[:3]
    resta = rows[3:10]

    browser_url = build_newsletter_url(f"{SITE}/top", "veure_navegador", week)
    cta_url = build_newsletter_url(f"{SITE}/top", "cta_top", week)

    context = {
        "subject": subject,
        "site_url": SITE,
        "territori_nom": territori_nom or "Global",
        "project_week": week,
        "podi": podi,
        "resta": resta,
        "narrative_html": narrative_html,
        "territorials": _territorial_cards(setmana, week),
        "novetats": _novetats_cards(setmana, publish_date, week),
        "share_links": _share_links(week),
        "browser_url": browser_url,
        "cta_url": cta_url,
        # legacy keys still read by the old template/tests:
        "heading": f"Top {territori_nom or 'Global'} · setmana {week}",
        "top_url": cta_url,
        "entries": rows,
    }
    return context, subject


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
    base_context, subject = _build_top_context(
        tipus, territori, setmana, publish_date, entries
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
                {**base_context, "unsub_url": _unsub_url(user)},
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
