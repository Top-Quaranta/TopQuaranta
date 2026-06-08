"""Token-authed endpoints for the newsletter cloud routine (2026-06-07).

Two narrow endpoints so a cloud routine can READ a weekly brief and LEAVE
a draft — never send. Authenticated by a dedicated static bearer token
(`settings.NEWSLETTER_ROUTINE_TOKEN`, from the server environment), NOT
by a staff session. The engine (`generar_esborrany_newsletter`) stays as
the fallback.

  GET  /api/v1/newsletter-routine/brief/       → grounded weekly brief
  POST /api/v1/newsletter-routine/esborrany/   → upsert the week's draft
                                                  (font=llm, estat=pendent)

# Spec: docs/architecture/comptes.md
"""

from __future__ import annotations

import functools
import hmac

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import NewsletterDraft
from comptes.newsletter_brief import build_brief, current_monday

TIPUS = "top_ppcc"
TERRITORI = "PPCC"


def _token_ok(request: Request) -> bool:
    """`Authorization: Bearer <token>` compared in constant time against
    `settings.NEWSLETTER_ROUTINE_TOKEN`. A blank setting denies every
    request, so a misconfigured deploy never accepts an empty bearer."""
    expected = getattr(settings, "NEWSLETTER_ROUTINE_TOKEN", "") or ""
    if not expected:
        return False
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return False
    presented = header[len(prefix) :].strip()
    return bool(presented) and hmac.compare_digest(presented, expected)


def require_routine_token(view_func):
    """Gate a view on the routine bearer token. Invalid/missing → 401
    (not 403): this is an auth boundary, not a staff-permission one."""

    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _token_ok(request):
            return Response(
                {"error": "invalid or missing newsletter routine token"}, status=401
            )
        return view_func(request, *args, **kwargs)

    return _wrapped


@api_view(["GET"])
@require_routine_token
def brief(request: Request) -> Response:
    """Weekly brief for Global. Default = this week (production path,
    unchanged). Optional `?setmana=<iso Monday>` requests a specific
    week's brief; an unparseable value falls back to this week, and a
    not-yet-consolidated week returns 200 `{"status": "not_ready"}` so
    the routine retries later rather than treating it as an error."""
    from django.utils.dateparse import parse_date

    raw = (request.GET.get("setmana") or "").strip()
    setmana = parse_date(raw) if raw else None
    return Response(build_brief(setmana))


@api_view(["POST"])
@require_routine_token
def esborrany(request: Request) -> Response:
    """Upsert a week's draft from the routine: subject + narrative_html,
    `font=llm`, `estat=pendent`. The routine can NEVER mark a draft
    approved/sent — any `estat` other than `pendent` is rejected, and a
    draft already `enviat`/`cancellat` is terminal.

    Target week: optional `?setmana=<iso Monday>`. Absent → this week
    (the automatic Saturday routine, unchanged). Present → that week,
    with the same guards as the staff on-demand path: the week's PPCC
    top must be consolidated (409 otherwise), so the refinement loop
    (read `brief?setmana=X`, write here for the same X) lands on X."""
    estat_req = (request.data.get("estat") or "").strip()
    if estat_req and estat_req != NewsletterDraft.ESTAT_PENDENT:
        return Response(
            {"error": "la rutina només pot deixar estat=pendent"}, status=400
        )

    subject = (request.data.get("subject") or "").strip()
    if not subject:
        return Response({"error": "subject obligatori"}, status=400)
    narrative_html = request.data.get("narrative_html") or ""

    raw = (request.GET.get("setmana") or request.data.get("setmana") or "").strip()
    if raw:
        from django.utils.dateparse import parse_date

        from ranking.models import TopSetmanal

        setmana = parse_date(raw)
        if setmana is None:
            return Response({"error": "setmana invàlida"}, status=400)
        if not TopSetmanal.objects.filter(
            territori=TERRITORI, setmana=setmana
        ).exists():
            return Response(
                {
                    "error": (
                        f"el top {TERRITORI} de la setmana {setmana} "
                        "no està consolidat"
                    )
                },
                status=409,
            )
    else:
        setmana = current_monday()
    existing = NewsletterDraft.objects.filter(
        tipus=TIPUS, territori=TERRITORI, setmana=setmana
    ).first()
    if existing and existing.estat in (
        NewsletterDraft.ESTAT_ENVIAT,
        NewsletterDraft.ESTAT_CANCELLAT,
    ):
        return Response(
            {"error": f"esborrany {existing.estat}; no es pot reemplaçar"}, status=409
        )
    # Don't clobber a human edit: once staff has touched the draft
    # (`editat=True`), the routine must not overwrite it.
    if existing and existing.editat:
        return Response(
            {"error": "esborrany editat per l'staff; no es pot reemplaçar"}, status=409
        )

    draft, created = NewsletterDraft.objects.update_or_create(
        tipus=TIPUS,
        territori=TERRITORI,
        setmana=setmana,
        defaults={
            "subject": subject[:300],
            "narrative_html": narrative_html,
            "font": NewsletterDraft.FONT_LLM,
            "estat": NewsletterDraft.ESTAT_PENDENT,
            # The routine's text is the authoritative draft, not a human
            # edit of an engine draft.
            "editat": False,
        },
    )
    return Response(
        {
            "status": "ok",
            "created": created,
            "setmana": setmana.isoformat(),
            "estat": draft.estat,
            "font": draft.font,
        },
        status=201 if created else 200,
    )
