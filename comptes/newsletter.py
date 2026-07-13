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
from comptes.newsletter_linkify import linkify_narrative
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


def _artistes_render(
    names: list[str],
    slugs: list[str | None],
    content: str,
    week: int,
    *,
    max_chars: int = 80,
) -> tuple[list[dict], bool]:
    """Per-artist template rows mirroring `_join_artists_text`'s budget.

    `slugs` is parallel to `names` (principal at index 0, then
    collaborators). Every artist with a known slug — principal AND
    collaborators (Slice 2) — carries a `/artista/{slug}` URL; the rest
    stay bold without link. Returns `(rows, truncated)` where `truncated`
    signals an appended ellipsis for an over-long list (e.g. a
    39-collaborator track), keeping the card bounded like the legacy
    joined string did."""
    if not names:
        return [{"nom": "—", "url": None}], False
    full = ", ".join(names)
    if len(full) <= max_chars:
        shown, truncated = names, False
    else:
        shown, truncated = names[:1], True
        for i in range(len(names) - 1, 0, -1):
            if len(", ".join(names[:i]) + "…") <= max_chars:
                shown, truncated = names[:i], True
                break
    rows = []
    for idx, nom in enumerate(shown):
        aslug = slugs[idx] if idx < len(slugs) else None
        url = (
            build_newsletter_url(f"{SITE}/artista/{aslug}", f"{content}_art", week)
            if aslug
            else None
        )
        rows.append({"nom": nom, "url": url})
    return rows, truncated


def _enrich_entry(e: dict, content: str, week: int, *, hero: bool, torna: bool) -> dict:
    """One top entry → template-ready row (cover, trend, UTM link)."""
    names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
    mida = 500 if hero else 250
    slug = e.get("canco_slug")
    link_base = f"{SITE}/canco/{slug}" if slug else f"{SITE}/top"
    ensure_cover_downloaded(e.get("album_deezer_id"), e.get("cover_url"))
    slugs = e.get("artistes_slugs")
    if slugs is None:  # back-compat with a pre-Slice-2 payload
        slugs = [e.get("artista_slug")]
    artistes_render, artistes_truncated = _artistes_render(names, slugs, content, week)
    return {
        **e,
        "artistes_display": _join_artists_text(names, max_chars=80),
        "artistes_render": artistes_render,
        "artistes_truncated": artistes_truncated,
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


def _name_map_from_entries(
    entries: list[dict], week: int
) -> list[tuple[str, str | None, str]]:
    """Canonical name -> (url, kind) map for the prose linkifier, built
    from the top entries. Songs link to `/canco/{slug}`, and every artist
    with a known slug — principal AND collaborators (Slice 2) — links to
    `/artista/{slug}` (UTM-tagged like the rest); names without a slug get
    `url=None` (bold without link). Each canonical string appears once;
    the first entry that introduces it (top position first) decides its
    url."""
    seen: set[str] = set()
    out: list[tuple[str, str | None, str]] = []
    for e in entries:
        cn = e.get("canco_nom")
        cs = e.get("canco_slug")
        if cn and cn != "—" and cn not in seen:
            url = (
                build_newsletter_url(f"{SITE}/canco/{cs}", "prosa_canco", week)
                if cs
                else None
            )
            out.append((cn, url, "canco"))
            seen.add(cn)
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        slugs = e.get("artistes_slugs")
        if slugs is None:  # back-compat with a pre-Slice-2 payload
            slugs = [e.get("artista_slug")]
        for idx, nom in enumerate(names):
            if not nom or nom == "—" or nom in seen:
                continue
            aslug = slugs[idx] if idx < len(slugs) else None
            url = (
                build_newsletter_url(f"{SITE}/artista/{aslug}", "prosa_artista", week)
                if aslug
                else None
            )
            out.append((nom, url, "artista"))
            seen.add(nom)
    return out


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

    # Prose linkifier map (deterministic, applied to engine + injected
    # narrative). Built from the entries, which carry the slugs.
    name_map = _name_map_from_entries(entries, week)
    if narrative_html:
        narrative_html = linkify_narrative(narrative_html, name_map)

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
        # Name map for the prose linkifier; the override paths
        # (preview / send) read it to linkify the injected narrative.
        "name_map": name_map,
        # legacy keys still read by the old template/tests:
        "heading": f"Top {territori_nom or 'Global'} · setmana {week}",
        "top_url": cta_url,
        "entries": rows,
    }
    return context, subject


def build_draft_text(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    publish_date: datetime.date,
    entries: list[dict],
) -> tuple[str, str]:
    """Compose the newsletter's editorial text WITHOUT sending.

    Returns `(subject, narrative_html)` from the narrative engine via
    `_build_top_context`. Side-effect-free: the anti-repeat registry's
    `mark_used` is never called here (it fires only on a real publish),
    so generating a draft never poisons future phrase selection. This is
    the seam the Saturday draft-generation step uses."""
    context, subject = _build_top_context(
        tipus, territori, setmana, publish_date, entries
    )
    return subject, context.get("narrative_html", "")


def build_newsletter_context(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    publish_date: datetime.date,
    entries: list[dict],
    *,
    subject_override: str | None = None,
    narrative_html_override: str | None = None,
) -> tuple[dict, str]:
    """Assemble the recipient-independent body context + subject, applying
    the draft-review overrides. Shared by the real send and the admin
    preview so both render byte-for-byte the same body (only `unsub_url`
    and the optional management block vary per render).

    `subject_override` / `narrative_html_override` (the draft-review flow):
    when given, the editorial text shipped is the (possibly human-edited)
    draft, while the rest of the context — podi, top 40, covers — is still
    rebuilt fresh from `entries` (the FINAL top at send time). Pass
    `narrative_html_override=""` to ship an empty editorial block."""
    base_context, subject = _build_top_context(
        tipus, territori, setmana, publish_date, entries
    )
    if subject_override:
        subject = subject_override
        base_context["subject"] = subject_override
    if narrative_html_override is not None:
        base_context["narrative_html"] = linkify_narrative(
            narrative_html_override, base_context.get("name_map") or []
        )
    return base_context, subject


def render_newsletter_html(
    base_context: dict,
    *,
    unsub_url: str,
    gestio_url: str | None = None,
) -> str:
    """Render the full email HTML from a prebuilt context. `unsub_url` is
    the per-recipient unsubscribe link; `gestio_url`, when set, adds the
    admin-only management block (link to edit/cancel the draft) that the
    subscriber copy MUST never carry."""
    return render_to_string(
        "comptes/email_newsletter_top.html",
        {**base_context, "unsub_url": unsub_url, "gestio_url": gestio_url},
    )


def send_top_newsletter(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    publish_date: datetime.date,
    entries: list[dict],
    *,
    subject_override: str | None = None,
    narrative_html_override: str | None = None,
) -> str:
    """Send the weekly newsletter to every opted-in user. Returns a summary
    string (e.g. "sent=42 fail=1") that the calling command stores in the
    SocialPost.metadata for traceability.

    The body context is built ONCE; only `unsub_url` varies per recipient.
    The subscriber copy never carries the management block (`gestio_url`
    stays None)."""
    base_context, subject = build_newsletter_context(
        tipus,
        territori,
        setmana,
        publish_date,
        entries,
        subject_override=subject_override,
        narrative_html_override=narrative_html_override,
    )

    qs = Usuari.objects.filter(perfil__vol_newsletter=True).select_related("perfil")
    sent = 0
    failed = 0
    for user in qs.iterator():
        if not user.email:
            continue
        try:
            unsub = _unsub_url(user)
            html = render_newsletter_html(base_context, unsub_url=unsub)
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
            msg.extra_headers["List-Unsubscribe"] = f"<{unsub}>"
            msg.extra_headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
            msg.send(fail_silently=False)
            sent += 1
        except Exception:  # noqa: BLE001
            logger.exception("newsletter send failed for user %s", user.pk)
            failed += 1

    return f"sent={sent} fail={failed}"


def render_newsletter_preview(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    publish_date: datetime.date,
    entries: list[dict],
    *,
    subject_override: str | None = None,
    narrative_html_override: str | None = None,
    unsub_url: str | None = None,
    gestio_url: str | None = None,
) -> str:
    """Render the FULL newsletter HTML exactly as it would be sent, for a
    staff preview or the admin notification. Same path as
    `send_top_newsletter` (shared `build_newsletter_context` +
    `render_newsletter_html` + the same template), so the preview is
    byte-for-byte the body subscribers receive.

    Pure render: no `mark_used`, no send, no DB write (it never iterates
    recipients). `unsub_url` defaults to a non-functional `/compte/perfil`
    placeholder (no recipient in a preview); pass a real one to mirror a
    single subscriber. `gestio_url`, when set, adds the admin-only
    management block."""
    base_context, _subject = build_newsletter_context(
        tipus,
        territori,
        setmana,
        publish_date,
        entries,
        subject_override=subject_override,
        narrative_html_override=narrative_html_override,
    )
    return render_newsletter_html(
        base_context,
        unsub_url=unsub_url or f"{SITE}/compte/perfil",
        gestio_url=gestio_url,
    )


def staff_draft_url(setmana: datetime.date) -> str:
    """Staff editor link for a draft week (edit subject/narrative or cancel
    the send). The admin notification points here; no token, no public
    endpoint — it is the IsStaff-gated SPA view."""
    return f"{SITE}/staff/social/esborrany?setmana={setmana.isoformat()}"


def _admin_notice_headers() -> dict:
    """Deliverability headers for the admin notification: marks it as an
    automated list message so spam filters score it lower and clients never
    auto-reply."""
    return {
        "List-Id": "TopQuaranta newsletter <newsletter.topquaranta.cat>",
        "List-Unsubscribe": f"<{SITE}/compte/perfil>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        "Auto-Submitted": "auto-generated",
        "X-Auto-Response-Suppress": "All",
    }


def preview_extra_recipient() -> str:
    """Optional EXTRA draft-preview recipient from
    `ConfiguracioGlobal.newsletter_desti_prova` (email-client render
    testing). Returns "" when unset — the caller then keeps the exact
    pre-field behaviour. Read defensively so a config hiccup can never
    break the notification path."""
    try:
        from ranking.models import ConfiguracioGlobal

        return (ConfiguracioGlobal.load().newsletter_desti_prova or "").strip()
    except Exception:  # noqa: BLE001
        logger.exception("preview_extra_recipient: config read failed")
        return ""


def notify_admins_draft_preview(draft, recipients: list[str] | None = None) -> None:
    """Best-effort: email `settings.ADMINS` the FULL newsletter preview for a
    pending draft — byte-for-byte the body subscribers will receive, plus the
    admin-only management block linking to the staff editor. Rendered through
    the shared `render_newsletter_preview`. Deliverability headers (List-Id,
    List-Unsubscribe, Auto-Submitted) are attached so the automated message
    scores low with spam filters.

    `recipients` overrides the default list (`settings.ADMINS` plus, when
    set, `ConfiguracioGlobal.newsletter_desti_prova` — the render-testing
    address). This is a DRAFT preview path only; it never touches the
    subscriber send in `send_top_newsletter`.

    Never raises: any failure (build, render, mail) logs and is swallowed so
    it cannot block the draft write that triggered it."""
    from django.core.mail import EmailMultiAlternatives

    from social import payload

    try:
        if recipients is None:
            recipients = list(settings.ADMINS)
            extra = preview_extra_recipient()
            if extra:
                recipients.append(extra)
        data = payload.build_top(draft.territori, draft.setmana)
        entries = (data or {}).get("entries") or []
        publish_date = draft.setmana + datetime.timedelta(days=5)
        gestio_url = staff_draft_url(draft.setmana)
        html = render_newsletter_preview(
            draft.tipus,
            draft.territori,
            draft.setmana,
            publish_date,
            entries,
            subject_override=draft.subject,
            narrative_html_override=draft.narrative_html,
            gestio_url=gestio_url,
        )
        text = (
            "Esborrany de la newsletter setmanal a punt per revisar.\n\n"
            f"Setmana: {draft.setmana}\n"
            f"Assumpte: {draft.subject}\n\n"
            "Preview complet a sota. Editar o paralitzar l'enviament:\n"
            f"{gestio_url}\n\n"
            "S'enviarà diumenge tret que el modifiquis o el cancel·lis.\n"
        )
        msg = EmailMultiAlternatives(
            subject=f"[TopQuaranta] Esborrany newsletter setmana {draft.setmana}",
            body=text,
            from_email=FROM_EMAIL,
            to=recipients,
            headers=_admin_notice_headers(),
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
    except Exception:  # noqa: BLE001
        logger.exception(
            "notify_admins_draft_preview failed for setmana %s",
            getattr(draft, "setmana", "?"),
        )
