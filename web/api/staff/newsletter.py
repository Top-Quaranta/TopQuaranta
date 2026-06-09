"""Staff endpoints for the newsletter review draft (opt-out flow).

GET    /staff/newsletter/esborrany/            → draft + the entries it
                                                  will ship with + meta.
PATCH  /staff/newsletter/esborrany/            → edit subject /
                                                  narrative_html (editat=True).
POST   /staff/newsletter/esborrany/cancellar/  → estat=cancellat.
POST   /staff/newsletter/esborrany/preview/    → full email HTML (render
                                                  only; honours editor
                                                  overrides; no DB write).

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
        # Newsletter→Comunitat bridge: id of the mirrored public Publicació
        # (null until staff publishes it). Drives the editor's button state.
        "publicacio_id": draft.publicacio_id,
        "pont_comunitat_actiu": cfg.newsletter_publicacio_pont_actiu,
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


@api_view(["POST"])
@permission_classes([IsStaff])
def esborrany_publicar_comunitat(request: Request) -> Response:
    """Mirror the draft into a PUBLIC community Publicació (additive bridge).

    Gated by `ConfiguracioGlobal.newsletter_publicacio_pont_actiu`: 409 while
    off. Idempotent (returns the existing post on re-call). Creates ONLY a
    Publicació row — no email, no distribution, no newsletter send.
    """
    from comptes import community_bridge

    setmana = _resolve_setmana(request)
    if setmana is None:
        return Response({"error": "setmana invàlida o cap top consolidat"}, status=400)
    draft = NewsletterDraft.objects.filter(
        tipus=TIPUS, territori=TERRITORI, setmana=setmana
    ).first()
    if draft is None:
        return Response({"error": f"cap esborrany per a {setmana}"}, status=404)
    try:
        pub = community_bridge.publicar_draft_a_comunitat(draft)
    except community_bridge.PontDesactivat:
        return Response(
            {
                "error": "pont Newsletter→Comunitat desactivat "
                "(newsletter_publicacio_pont_actiu=False)"
            },
            status=409,
        )
    except community_bridge.AdminInaccessible:
        return Response({"error": "usuari admin no disponible"}, status=500)
    return Response(
        {
            "publicacio_id": pub.id,
            "estat": pub.estat,
            "visibilitat": pub.visibilitat,
            "titol": pub.titol,
        },
        status=200,
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def esborrany_preview(request: Request) -> Response:
    """Render the FULL newsletter HTML as it would be sent, honouring the
    editor's live `subject`/`narrative_html` overrides (so unsaved edits
    show). Render-only: no `mark_used`, no send, no DB write; the list +
    covers are rebuilt from the consolidated top exactly like the send.
    Returns `{"html": "<full email>"}` for an iframe `srcdoc`."""
    from comptes.newsletter import render_newsletter_preview
    from social import payload

    setmana = _resolve_setmana(request)
    if setmana is None:
        return Response({"error": "setmana invàlida o cap top consolidat"}, status=400)
    data = payload.build_top(TERRITORI, setmana)
    if not data:
        return Response(
            {"error": f"top {TERRITORI} de la setmana {setmana} no consolidat"},
            status=409,
        )

    # Overrides: only apply when the key is present in the request, so an
    # absent field falls back to the engine/draft text.
    subject_override = request.data.get("subject")
    narrative_override = request.data.get("narrative_html")
    publish_date = setmana + datetime.timedelta(days=5)
    html = render_newsletter_preview(
        TIPUS,
        TERRITORI,
        setmana,
        publish_date,
        data["entries"],
        subject_override=(subject_override or None),
        narrative_html_override=(
            narrative_override if narrative_override is not None else None
        ),
    )
    return Response({"html": html, "setmana": setmana.isoformat()})


@api_view(["GET"])
@permission_classes([IsStaff])
def setmanes(request: Request) -> Response:
    """Weeks with a consolidated PPCC `TopSetmanal` (the on-demand
    generation selector) + a live can-generate indicator for THIS week.

    Each listed week is by definition consolidated, so generatable;
    `has_draft`/`estat` let the UI flag which already have a draft. The
    `current` block calls `build_brief()` (the routine's own readiness
    function) so staff sees whether the automatic Saturday routine could
    generate the current week right now (status=ready) or not."""
    from comptes.newsletter_brief import build_brief, current_monday

    weeks = list(
        TopSetmanal.objects.filter(territori=TERRITORI)
        .values_list("setmana", flat=True)
        .distinct()
        .order_by("-setmana")[:52]
    )
    estats = {
        d["setmana"]: d["estat"]
        for d in NewsletterDraft.objects.filter(
            tipus=TIPUS, territori=TERRITORI, setmana__in=weeks
        ).values("setmana", "estat")
    }
    setmanes_out = [
        {
            "setmana": w.isoformat(),
            "has_draft": w in estats,
            "estat": estats.get(w),
        }
        for w in weeks
    ]
    brief = build_brief()  # this week; cheap when not consolidated
    current = {
        "setmana": current_monday().isoformat(),
        "status": brief.get("status"),
        "motiu": brief.get("motiu", ""),
    }
    return Response({"setmanes": setmanes_out, "current": current})


@api_view(["POST"])
@permission_classes([IsStaff])
def esborrany_generar(request: Request) -> Response:
    """Generate an ENGINE draft on demand for a chosen consolidated week.

    Uses the side-effect-free generator (`build_draft_text` — no
    `mark_used`, no send). Guards: the week's PPCC top must be
    consolidated (409 otherwise); never clobbers a terminal
    (`enviat`/`cancellat`) or staff-edited (`editat=True`) draft (409).
    A `pendent` engine/LLM draft is regenerated in place. NEVER sends."""
    setmana = _resolve_setmana(request)
    if setmana is None:
        return Response({"error": "setmana invàlida o cap top consolidat"}, status=400)
    if not TopSetmanal.objects.filter(territori=TERRITORI, setmana=setmana).exists():
        return Response(
            {"error": f"el top {TERRITORI} de la setmana {setmana} no està consolidat"},
            status=409,
        )

    existing = NewsletterDraft.objects.filter(
        tipus=TIPUS, territori=TERRITORI, setmana=setmana
    ).first()
    if existing and existing.estat in (
        NewsletterDraft.ESTAT_ENVIAT,
        NewsletterDraft.ESTAT_CANCELLAT,
    ):
        return Response(
            {"error": f"esborrany {existing.estat}; no es pot regenerar"}, status=409
        )
    if existing and existing.editat:
        return Response(
            {"error": "esborrany editat per l'staff; no es pot regenerar"}, status=409
        )

    from comptes.newsletter import build_draft_text
    from social import payload

    data = payload.build_top(TERRITORI, setmana)
    if not data or not data.get("entries"):
        return Response(
            {"error": f"el top {TERRITORI} de {setmana} no té entrades"}, status=409
        )
    publish_date = setmana + datetime.timedelta(days=5)
    subject, narrative_html = build_draft_text(
        TIPUS, TERRITORI, setmana, publish_date, data["entries"]
    )

    draft, created = NewsletterDraft.objects.update_or_create(
        tipus=TIPUS,
        territori=TERRITORI,
        setmana=setmana,
        defaults={
            "subject": subject[:300],
            "narrative_html": narrative_html,
            "font": NewsletterDraft.FONT_MOTOR,
            "estat": NewsletterDraft.ESTAT_PENDENT,
            "editat": False,
        },
    )
    return Response(_draft_payload(draft), status=201 if created else 200)
