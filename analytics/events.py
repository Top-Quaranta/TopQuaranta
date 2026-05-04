"""Atomic event-counter helper.

Public API:
  ``register(clau, dim1="", dim2="", n=1)``

Use from anywhere in the app to bump a counter for today's date:

  from analytics.events import register
  register("registre_complet")
  register("proposta_crear", dim1="user_logged_in")
  register("social_publicat", dim1="instagram_feed", dim2="top_ppcc")

The increment is atomic via UPDATE ... SET comptador = comptador + N
so concurrent gunicorn workers won't lose counts under load.
Failures are swallowed and logged (analytics MUST NOT break a
user-facing flow). Tests can pass `force_raise=True` to surface
the exception.
"""

from __future__ import annotations

import logging
from datetime import date as date_cls

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from analytics.models import MetricaEsdeveniment

logger = logging.getLogger(__name__)


def register(
    clau: str,
    dim1: str = "",
    dim2: str = "",
    n: int = 1,
    *,
    force_raise: bool = False,
) -> None:
    """Increment today's counter for (clau, dim1, dim2) by `n`.

    Silently swallows DB errors so a misbehaving analytics layer
    never blocks a real flow (registre, publicar, etc.). Errors
    surface in `errors.log` for ops to follow up.
    """
    if n <= 0:
        return
    # `data` is "today in the server's local timezone" — same
    # convention as `tq-health` and the cron schedule. Avoids
    # mid-day roll-over surprises across midnight UTC.
    today: date_cls = timezone.localdate()
    try:
        with transaction.atomic():
            obj, created = MetricaEsdeveniment.objects.get_or_create(
                data=today,
                clau=clau,
                dimensio_1=dim1 or "",
                dimensio_2=dim2 or "",
                defaults={"comptador": n},
            )
            if not created:
                MetricaEsdeveniment.objects.filter(pk=obj.pk).update(
                    comptador=F("comptador") + n
                )
    except IntegrityError:
        # Lost race against another worker that just inserted the
        # same row. Retry with a pure UPDATE — the row exists now.
        try:
            MetricaEsdeveniment.objects.filter(
                data=today,
                clau=clau,
                dimensio_1=dim1 or "",
                dimensio_2=dim2 or "",
            ).update(comptador=F("comptador") + n)
        except Exception:
            if force_raise:
                raise
            logger.exception(
                "analytics: failed to bump %s/%s/%s after race", clau, dim1, dim2
            )
    except Exception:
        if force_raise:
            raise
        logger.exception("analytics: failed to bump %s/%s/%s", clau, dim1, dim2)
