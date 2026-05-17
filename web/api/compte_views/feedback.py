"""User-filed feedback / correction reports."""

from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import Feedback

from ._common import _FeedbackCreateThrottle

VALID_TARGETS = {t for t, _ in Feedback.TARGET_CHOICES}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([_FeedbackCreateThrottle])
def feedback_crear(request: Request) -> Response:
    """File a feedback/correction report from a public page.

    Body:
      url           str, required    — absolute or path-only, max 500 chars
      target_type   str, optional    — one of {artista, album, canco, altres}
      target_pk     int, optional
      target_slug   str, optional
      target_label  str, optional    — display name snapshot
      missatge      str, required    — the actual comment/correction
    """
    data = request.data or {}
    errors: dict[str, str] = {}

    url = (data.get("url") or "").strip()
    if not url:
        errors["url"] = "Falta la URL de la pàgina."
    elif len(url) > 500:
        errors["url"] = "URL massa llarga."

    missatge = (data.get("missatge") or "").strip()
    if not missatge:
        errors["missatge"] = "Escriu què cal corregir."
    elif len(missatge) > 5000:
        errors["missatge"] = "Missatge massa llarg (màxim 5000 caràcters)."

    target_type = (data.get("target_type") or Feedback.TARGET_ALTRES).strip()
    if target_type not in VALID_TARGETS:
        target_type = Feedback.TARGET_ALTRES

    target_pk_raw = data.get("target_pk")
    target_pk = None
    if target_pk_raw not in (None, ""):
        try:
            target_pk = int(target_pk_raw)
        except (TypeError, ValueError):
            pass

    if errors:
        return Response({"errors": errors}, status=400)

    fb = Feedback.objects.create(
        usuari=request.user,
        url=url,
        target_type=target_type,
        target_pk=target_pk,
        target_slug=(data.get("target_slug") or "").strip()[:550],
        target_label=(data.get("target_label") or "").strip()[:500],
        missatge=missatge,
    )
    # K1 analytics: counter dim1=target_type so we can chart which
    # surfaces (artista/album/canco) attract most corrections.
    from analytics.events import register as _register_event

    _register_event("feedback_crear", dim1=target_type)
    # Notify staff via the central transactional layer (best-effort).
    from comptes.notifications import notify_admins_nou_feedback

    notify_admins_nou_feedback(fb)
    return Response({"ok": True, "pk": fb.pk}, status=201)
