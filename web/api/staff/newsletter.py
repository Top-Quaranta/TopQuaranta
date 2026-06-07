"""Staff endpoints for the newsletter review draft (opt-out flow).

GET    /staff/newsletter/esborrany/            → draft + the entries it
                                                  will ship with + meta.
PATCH  /staff/newsletter/esborrany/            → edit subject /
                                                  narrative_html (editat=True).
POST   /staff/newsletter/esborrany/cancellar/  → estat=cancellat.

The draft is keyed by week; `?setmana=<iso>` selects one, default the
latest. See `docs/architecture/social.md` for the flow.
"""

from __future__ import annotations

import datetime

from django.db.models import Max
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import NewsletterDraft
from ranking.models import ConfiguracioGlobal, TopSetmanal
from web.api.staff._common import IsStaff

TIPUS = "top_ppcc"
TERRITORI = "PPCC"


def _resolve_setmana(request: Request):
    raw = (request.GET.get("setmana") or request.data.get("setmana") or "").strip()
    if raw:
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            return None
    return TopSetmanal.objects.filter(territori=TERRITORI).aggregate(m=Max("setmana"))[
        "m"
    ]


def _draft_payload(draft: NewsletterDraft) -> dict:
    # The entries the newsletter will ship with, rebuilt live so staff
    # can spot a mismatch between the editorial text and the actual top.
    from social import payload

    data = payload.build_top(TERRITORI, draft.setmana)
    entries = [
        {
            "posicio": e.get("posicio"),
            "canco_nom": e.get("canco_nom"),
            "artista_nom": e.get("artista_nom")
            or (e.get("artistes_noms") or [None])[0],
        }
        for e in ((data or {}).get("entries") or [])[:10]
    ]
    # Opt-out send is the Sunday after the ISO Monday `setmana`.
    send_date = draft.setmana + datetime.timedelta(days=6)
    cfg = ConfiguracioGlobal.load()
    return {
        "setmana": draft.setmana.isoformat(),
        "tipus": draft.tipus,
        "territori": draft.territori,
        "subject": draft.subject,
        "narrative_html": draft.narrative_html,
        "estat": draft.estat,
        "font": draft.font,
        "editat": draft.editat,
        "enviat_at": draft.enviat_at.isoformat() if draft.enviat_at else None,
        "send_date": send_date.isoformat(),
        "entries": entries,
        # So the UI can warn if the channel won't actually send.
        "newsletter_actiu": cfg.pot_publicar("newsletter"),
    }


@api_view(["GET", "PATCH"])
@permission_classes([IsStaff])
def esborrany(request: Request) -> Response:
    setmana = _resolve_setmana(request)
    if setmana is None:
        return Response({"error": "setmana invàlida o cap top consolidat"}, status=400)
    draft = NewsletterDraft.objects.filter(
        tipus=TIPUS, territori=TERRITORI, setmana=setmana
    ).first()
    if draft is None:
        return Response({"error": f"cap esborrany per a {setmana}"}, status=404)

    if request.method == "PATCH":
        if draft.estat != NewsletterDraft.ESTAT_PENDENT:
            return Response(
                {"error": f"esborrany {draft.estat}; només es pot editar si pendent"},
                status=409,
            )
        changed = False
        subj = request.data.get("subject")
        if subj is not None and subj.strip() and subj != draft.subject:
            draft.subject = subj.strip()[:300]
            changed = True
        nh = request.data.get("narrative_html")
        if nh is not None and nh != draft.narrative_html:
            draft.narrative_html = nh
            changed = True
        if changed:
            draft.editat = True
            draft.save(
                update_fields=["subject", "narrative_html", "editat", "updated_at"]
            )

    return Response(_draft_payload(draft))


@api_view(["POST"])
@permission_classes([IsStaff])
def esborrany_cancellar(request: Request) -> Response:
    setmana = _resolve_setmana(request)
    if setmana is None:
        return Response({"error": "setmana invàlida o cap top consolidat"}, status=400)
    draft = NewsletterDraft.objects.filter(
        tipus=TIPUS, territori=TERRITORI, setmana=setmana
    ).first()
    if draft is None:
        return Response({"error": f"cap esborrany per a {setmana}"}, status=404)
    if draft.estat == NewsletterDraft.ESTAT_ENVIAT:
        return Response({"error": "ja enviat; no es pot cancel·lar"}, status=409)
    draft.estat = NewsletterDraft.ESTAT_CANCELLAT
    draft.save(update_fields=["estat", "updated_at"])
    return Response(_draft_payload(draft))
