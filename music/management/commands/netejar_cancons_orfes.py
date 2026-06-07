"""Deactivate orphan pendent cançons (recurring net).

Auditoria 2026-06-07, informe 2a + provinença. A pendent canço
(`verificada=False, activa=True`) is only reviewable when it has at
least one approved artist (main or collaborator). The de-approval hook
in `rebutjar_artista` keeps the reject path clean going forward, and
migration `music 0090` cleared the historical backlog — this command is
the recurring SAFETY NET that makes the invariant self-healing whatever
the drift source (a future contributor-materialisation episode, a manual
edit that strands a song, etc.).

It reuses the canonical predicate `music.services.orphan_pendents_qs`,
so it inherits the contributors_raw caveat (songs still awaiting deferred
collaborators are spared). On top of that it applies a GRACE WINDOW: only
orphans that have been in the system for at least `--grace-days` (default
7) are deactivated, so the sweep never races a review/approval that is
still in progress on a freshly-ingested song.

Reversible (sets `activa=False`, never deletes). Idempotent. Designed to
run weekly via cron; emits `WORK_DONE=N` for the tq-health watchdog.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from music.models import Canco
from music.services import orphan_pendents_qs

logger = logging.getLogger(__name__)

DEFAULT_GRACE_DAYS = 7


class Command(BaseCommand):
    help = "Desactiva cançons pendents òrfenes (cap artista aprovat) passada la marja."

    def add_arguments(self, parser):
        from music.management_helpers import add_dry_run

        add_dry_run(parser)
        parser.add_argument(
            "--grace-days",
            type=int,
            default=DEFAULT_GRACE_DAYS,
            help=(
                "Només desactiva orfes creats fa més de N dies, per no "
                f"córrer contra una aprovació en curs (default {DEFAULT_GRACE_DAYS})."
            ),
        )

    def handle(self, *args, **opts):
        dry_run = bool(opts.get("dry_run"))
        grace_days = int(opts.get("grace_days") or DEFAULT_GRACE_DAYS)
        cutoff = timezone.now() - timedelta(days=grace_days)

        # Canonical predicate (pendent + active + no approved artist +
        # contributors_raw empty) restricted to rows older than the grace
        # window. created_at is the only "age" signal on Canco; a song
        # younger than the cutoff may still be mid-review, so we leave it.
        qs = orphan_pendents_qs().filter(created_at__lt=cutoff)
        ids = list(qs.values_list("id", flat=True))
        n = len(ids)

        if dry_run:
            self.stdout.write(
                f"DRY-RUN: desactivaria {n} cançó(ns) orfe(s) "
                f"(creades abans de {cutoff.date()}, marja {grace_days}d)."
            )
            self.stdout.write(f"WORK_DONE={n}")
            return

        if ids:
            with transaction.atomic():
                Canco.objects.filter(id__in=ids).update(activa=False)
            logger.info(
                "netejar_cancons_orfes: deactivated %d orphan pendent canço(s) "
                "(grace %dd)",
                n,
                grace_days,
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Desactivades {n} cançó(ns) orfe(s) (marja {grace_days}d)."
            )
        )
        self.stdout.write(f"WORK_DONE={n}")
