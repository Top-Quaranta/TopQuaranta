"""Reconcile pending IG collaborator invitations against the Graph API.

# Spec: docs/decisions/0015-ig-collaborator-invitations.md §5.5

Tranche 1 (INERT): gated on `ConfiguracioGlobal.ig_collaboradors_actiu`.
While the master flag is off (the default) this command is a clean
no-op — it writes nothing and calls no API. It ships in the cron dormant
so that switching the flag on (tranche 3) needs no deploy.

When active: selects `pendent` invites of the last 14 days, groups by
`ig_media_id`, calls `GET /<media>/collaborators` once per media, and
reconciles each row. Best-effort + idempotent: a Graph hiccup leaves the
row `pendent` for the next tick; the acceptance rate written to
`MetricaPipeline` is derived from DB state (not incremented), so
re-running the same day overwrites rather than double-counts.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import MetricaPipeline
from ranking.models import ConfiguracioGlobal
from social import instagram_client
from social.models import InvitacioColaboracioIG

logger = logging.getLogger(__name__)

WINDOW_DIES = 14
METRICA_CLAU = "ig_collab_taxa_acceptacio"


def reconcile_estat(invite_status: str | None) -> str | None:
    """Map a Graph `invite_status` to our terminal estat, or None to
    leave the invite pending.

      - accepted/active            → acceptada
      - pending/requested          → None (still pending)
      - anything else, OR absent   → rebutjada (declined / removed)

    `invite_status is None` means the username was absent from the
    collaborators list of a *successful* fetch, i.e. the invite was
    declined or the collaborator removed → rebutjada."""
    if invite_status is None:
        return InvitacioColaboracioIG.ESTAT_REBUTJADA
    s = invite_status.strip().lower()
    if s in ("accepted", "acceptada", "active"):
        return InvitacioColaboracioIG.ESTAT_ACCEPTADA
    if s in ("pending", "pendent", "requested"):
        return None
    return InvitacioColaboracioIG.ESTAT_REBUTJADA


class Command(BaseCommand):
    help = "Reconcilia invitacions de col·laboració IG pendents (ADR-0015 §5.5)."

    def handle(self, *args, **opts):
        cfg = ConfiguracioGlobal.load()
        if not cfg.ig_collaboradors_actiu:
            self.stdout.write("ig_collaboradors_actiu=False → no-op.")
            return

        now = timezone.now()
        cutoff = now - timedelta(days=WINDOW_DIES)

        # (a) Expire pending invites older than the window: IG acceptance
        # is immediate-or-never, so an un-resolved invite past 14 days is a
        # soft decline. Marking `caducada` (with `data_resolucio`) closes
        # the "eternal pendent" hole — the policy then treats it like a
        # rejection (C, 90-day cooldown) so the artist can be re-invited.
        caducades = InvitacioColaboracioIG.objects.filter(
            estat=InvitacioColaboracioIG.ESTAT_PENDENT,
            data_invitacio__lt=cutoff,
        ).update(estat=InvitacioColaboracioIG.ESTAT_CADUCADA, data_resolucio=now)

        # (b) Reconcile still-fresh pending invites against the API.
        pendents = InvitacioColaboracioIG.objects.filter(
            estat=InvitacioColaboracioIG.ESTAT_PENDENT,
            data_invitacio__gte=cutoff,
        )
        by_media: dict[str, list] = defaultdict(list)
        for inv in pendents:
            by_media[inv.ig_media_id].append(inv)

        resolved = 0
        for media_id, rows in by_media.items():
            try:
                statuses = instagram_client.get_collaborators(media_id)
            except Exception:  # noqa: BLE001 — a Graph hiccup must not abort
                logger.exception(
                    "get_collaborators failed for media %s; leaving pending",
                    media_id,
                )
                continue
            if statuses is None:
                # DRY_RUN or unknown — don't misread silence as rejection.
                continue
            for inv in rows:
                nou = reconcile_estat(statuses.get(inv.username_snapshot.lower()))
                if nou is None:
                    continue
                inv.estat = nou
                inv.data_resolucio = now
                inv.save(update_fields=["estat", "data_resolucio"])
                resolved += 1

        # Rolling acceptance rate over ALL resolved invites (derived from
        # DB state → idempotent). update_or_create so re-running the same
        # day overwrites the gauge instead of adding a row. `caducada`
        # counts as a non-acceptance in the denominator (a soft decline).
        n_acc = InvitacioColaboracioIG.objects.filter(
            estat=InvitacioColaboracioIG.ESTAT_ACCEPTADA
        ).count()
        n_no = InvitacioColaboracioIG.objects.filter(
            estat__in=[
                InvitacioColaboracioIG.ESTAT_REBUTJADA,
                InvitacioColaboracioIG.ESTAT_CADUCADA,
            ]
        ).count()
        denom = n_acc + n_no
        taxa = (n_acc / denom) if denom else 0.0
        MetricaPipeline.objects.update_or_create(
            data=now.date(),
            clau=METRICA_CLAU,
            dimensio_1="",
            defaults={"valor_float": taxa},
        )
        self.stdout.write(
            f"Caducades {caducades} · resoltes {resolved} · taxa acceptació "
            f"{taxa:.3f} ({n_acc}/{denom})."
        )
