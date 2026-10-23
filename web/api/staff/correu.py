"""One-click actions from the daily staff mail.

Each pending song in the 07:00 mail carries two links, «Aprovar» and
«Rebutjar». A link is a GET — mail clients cannot POST — so two things
keep it from being a foot-gun: the URL carries a signed token bound to
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
from music.services import aprovar_canco, rebutjar_canco

ACCIONS = ("aprovar", "rebutjar")
# A mail older than this has been superseded by fourteen newer ones.
MAX_AGE = datetime.timedelta(days=14)
# Rejecting from the mail means «this song is not Catalan»: the song
# alone is unlinked, never its album or artist (those need a human look
# at more than one row, and the panel is where that happens).
MOTIU_REBUIG_CORREU = "desvincular_canco"
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

    if accio == "aprovar":
        if canco.verificada:
            ctx["titol"] = "Ja estava aprovada"
        else:
            aprovar_canco(canco)
            log_staff_action(request, "canco_aprovar", target=canco, via="correu")
            ctx["titol"] = "Aprovada"
    else:
        if not canco.activa:
            ctx["titol"] = "Ja estava rebutjada"
        else:
            rebutjar_canco(canco, MOTIU_REBUIG_CORREU)
            log_staff_action(
                request,
                "canco_rebutjar",
                target=canco,
                motiu=MOTIU_REBUIG_CORREU,
                via="correu",
            )
            ctx["titol"] = "Rebutjada"
    return render(request, "analytics/correu_accio.html", ctx)
