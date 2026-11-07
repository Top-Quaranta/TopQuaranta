"""One-click actions from the daily staff mail.

Each pending song in the 07:00 mail carries an «Aprovar» link that
decides in one click. «Rebutjar» is NOT one: a rejection has a second
decision inside it (unlink the song, the album or the artist), so that
button opens the panel row instead. A link is a GET — mail clients
cannot POST — so two things keep it from being a foot-gun: the URL carries a signed token bound to
*that* song and *that* action (nothing to guess, nothing to swap), and
the view only acts for a logged-in staff session (a link scanner, a
preview fetcher or a forwarded mail has no session and gets the login
page). The action itself is the same service call the staff panel
makes, so the historial and the audit log read the same either way.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime
from urllib.parse import quote, urlencode

from django.core import signing
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from music.audit import log_staff_action
from music.models import Canco
from music.services import aprovar_canco

ACCIONS = ("aprovar",)
# A mail older than this has been superseded by fourteen newer ones.
MAX_AGE = datetime.timedelta(days=14)
LOGIN_URL = "/compte/accedir"

_signer = signing.TimestampSigner(salt="staff-correu-canco")


def enllac_accio(canco_pk: int, accio: str) -> str:
    """Site-relative URL of the one-click action for the mail."""
    assert accio in ACCIONS, accio
    token = _signer.sign(f"{canco_pk}:{accio}")
    return f"/api/v1/staff/correu/canco/{canco_pk}/{accio}/{token}/"


def _token_valid(token: str, canco_pk: int, accio: str) -> bool:
    try:
        return _signer.unsign(token, max_age=MAX_AGE) == f"{canco_pk}:{accio}"
    except signing.BadSignature:
        return False


@require_GET
def canco_accio(request: HttpRequest, pk: int, accio: str, token: str) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect(f"{LOGIN_URL}?next={quote(request.get_full_path())}")
    if not request.user.is_staff:
        return render(
            request,
            "analytics/correu_accio.html",
            {"titol": "Només per a l'staff", "detall": ""},
            status=403,
        )
    if accio not in ACCIONS or not _token_valid(token, pk, accio):
        return render(
            request,
            "analytics/correu_accio.html",
            {
                "titol": "Enllaç no vàlid",
                "detall": "L'enllaç està manipulat o té més de catorze dies. "
                "Decideix-ho des del panell.",
            },
            status=400,
        )

    canco = get_object_or_404(Canco.objects.select_related("artista"), pk=pk)
    filtre = {"q": canco.nom}
    if canco.artista_id:
        filtre["artista_pk"] = canco.artista_id
    ctx = {
        "canco": canco,
        "staff_url": "/staff/cancons?" + urlencode(filtre),
    }

    if canco.verificada:
        ctx["titol"] = "Ja estava aprovada"
    else:
        aprovar_canco(canco)
        log_staff_action(request, "canco_aprovar", target=canco, via="correu")
        ctx["titol"] = "Aprovada"
    return render(request, "analytics/correu_accio.html", ctx)


# ── Sol·licitud de revisió: «Aprovar-les totes» from the staff mail ──
# Same guards as above (signed token bound to the sol·licitud, staff
# session required), own salt so a song token can never pass here.

_signer_sollicitud = signing.TimestampSigner(salt="staff-correu-sollicitud")


def enllac_sollicitud(pk: int) -> str:
    """Site-relative one-click «approve all + resolve» URL for the mail."""
    token = _signer_sollicitud.sign(str(pk))
    return f"/api/v1/staff/correu/sollicitud/{pk}/aprovar/{token}/"


@require_GET
def sollicitud_aprovar(request: HttpRequest, pk: int, token: str) -> HttpResponse:
    from comptes.models import SolicitudRevisio
    from web.api.staff.sollicituds_revisio import aprovar_totes_i_resoldre

    if not request.user.is_authenticated:
        return redirect(f"{LOGIN_URL}?next={quote(request.get_full_path())}")
    ctx = {
        "etiqueta": "Sol·licitud de revisió",
        "staff_url": f"/staff/sollicituds-revisio/{pk}/",
    }
    if not request.user.is_staff:
        return render(
            request,
            "analytics/correu_accio.html",
            {**ctx, "titol": "Només per a l'staff", "detall": ""},
            status=403,
        )
    try:
        valid = _signer_sollicitud.unsign(token, max_age=MAX_AGE) == str(pk)
    except signing.BadSignature:
        valid = False
    if not valid:
        return render(
            request,
            "analytics/correu_accio.html",
            {
                **ctx,
                "titol": "Enllaç no vàlid",
                "detall": "L'enllaç està manipulat o té més de catorze dies. "
                "Decideix-ho des del panell.",
            },
            status=400,
        )

    s = get_object_or_404(SolicitudRevisio.objects.select_related("artista"), pk=pk)
    if s.estat == SolicitudRevisio.ESTAT_RESOLTA:
        ctx.update(titol="Ja estava resolta", detall=s.artista.nom)
    else:
        n = aprovar_totes_i_resoldre(request, s, via="correu")
        ctx.update(
            titol="Aprovada",
            detall=f"{s.artista.nom} · {n} cançons aprovades. El gestor rebrà un correu.",
        )
    return render(request, "analytics/correu_accio.html", ctx)
