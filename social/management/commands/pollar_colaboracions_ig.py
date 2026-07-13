"""Expire stale IG collaborator invitations + refresh the acceptance metric.

# Spec: docs/decisions/0015-ig-collaborator-invitations.md §5.5

Definitive cycle (2026-07-13, ADR-0015 §5.5): programmatic acceptance
reads are unviable with the app's API flavour (Instagram Login lacks
the `/collaborators` edge; a Facebook-Login user token returns it
empty for pending invitations; a Page token is inaccessible to the
app type), so this command calls no Graph API at all. Acceptances are
marked manually from the staff social panel
(`POST /staff/social/invitacions/acceptar/`); this cron keeps the two
automatic duties:

  (a) expire `pendent` invites older than the 14-day window to
      `caducada` (IG acceptance is immediate-or-never; the policy
      treats it like a rejection: category C, 90-day cooldown), and
  (b) write the rolling acceptance rate to `MetricaPipeline`, derived
      from registry state (update_or_create → idempotent per day).

Gated on `ConfiguracioGlobal.ig_collaboradors_actiu` — a clean no-op
while the master flag is off.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import MetricaPipeline
from ranking.models import ConfiguracioGlobal
from social.models import InvitacioColaboracioIG

WINDOW_DIES = 14
METRICA_CLAU = "ig_collab_taxa_acceptacio"


class Command(BaseCommand):
    help = (
        "Caduca invitacions de col·laboració IG pendents de >14 dies i "
        "actualitza la taxa d'acceptació (ADR-0015 §5.5)."
    )

    def handle(self, *args, **opts):
        cfg = ConfiguracioGlobal.load()
        if not cfg.ig_collaboradors_actiu:
            self.stdout.write("ig_collaboradors_actiu=False → no-op.")
            return

        now = timezone.now()
        cutoff = now - timedelta(days=WINDOW_DIES)

        caducades = InvitacioColaboracioIG.objects.filter(
            estat=InvitacioColaboracioIG.ESTAT_PENDENT,
            data_invitacio__lt=cutoff,
        ).update(estat=InvitacioColaboracioIG.ESTAT_CADUCADA, data_resolucio=now)

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
            f"Caducades {caducades} · taxa acceptació {taxa:.3f} ({n_acc}/{denom})."
        )
