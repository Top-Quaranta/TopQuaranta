"""Aggregate metric models.

Two tables, both **append-but-never-PII**:

* `MetricaEsdeveniment` — counter rows keyed by (data, clau,
  dimensio_1, dimensio_2). Used for everything that's "+1 per
  occurrence": pageviews, register completions, proposta submissions,
  feedback, social-publish events, UTM landings, etc.
  Increments are atomic via `update_or_create` + `F("comptador")+1`,
  so concurrent gunicorn workers can't race past each other.

* `MetricaPipeline` — daily snapshots of a named gauge. Used for
  "how many cançons verificades exist on day X" style metrics.
  One row per (data, clau, dimensio_1); the cron `snapshot_pipeline`
  writes ~30 of these once a day at 23:00 UTC.

Neither model stores user identifiers, IPs, or session keys. The
`dimensio_*` slots hold low-cardinality enums only (territori,
canal, tipus, source). If a metric ever needs more dimensions we
add a third column rather than overloading.
"""

from __future__ import annotations

from django.db import models


class MetricaEsdeveniment(models.Model):
    """Aggregate event counter.

    Lifecycle: rows are inserted by `analytics.events.register()`
    on the first occurrence of a (data, clau, dim1, dim2) tuple
    and incremented atomically thereafter. We never delete; old
    rows are pruned by a retention cron when (and if) we ever
    accumulate years of data — at the current scale (~thousands
    of rows/day worst case) we have years of headroom.
    """

    data = models.DateField(db_index=True)
    clau = models.CharField(
        max_length=80,
        db_index=True,
        help_text="Snake-case event name, e.g. 'pageview', 'registre_complet'.",
    )
    dimensio_1 = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text=(
            "Optional low-cardinality discriminator. For 'pageview' "
            "this is the URL path; for 'utm_landing' the source; "
            "for 'social_publicat' the channel."
        ),
    )
    dimensio_2 = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Second discriminator slot. Use sparingly.",
    )
    comptador = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Esdeveniment agregat"
        verbose_name_plural = "Esdeveniments agregats"
        constraints = [
            models.UniqueConstraint(
                fields=["data", "clau", "dimensio_1", "dimensio_2"],
                name="metricaesdeveniment_uniq",
            ),
        ]
        indexes = [
            # Most queries are "give me the last N days of clau X" —
            # this composite covers them without forcing the planner
            # to fall back on the unique constraint's btree.
            models.Index(fields=["clau", "-data"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.data} {self.clau}/{self.dimensio_1}/{self.dimensio_2}="
            f"{self.comptador}"
        )


class MetricaPipeline(models.Model):
    """Daily gauge snapshot of a pipeline-state metric.

    Examples of `clau`:
      - `cancons_verificades` (int)
      - `cancons_pendents` (int)
      - `cancons_rebutjades_acumulades` (int)
      - `taxa_rebuig_setmana` (float, percentage)
      - `cobertura_whisper` (float, % cançons amb LID)
      - `cobertura_mb` (float, % artistes amb MBID)
      - `artistes_aprovats` (int)
      - `cancons_per_territori` (int, dimensio_1=territori_codi)

    Both `valor_int` and `valor_float` exist so a single table
    serves both gauge types — pick whichever fits, leave the other
    NULL. Avoids JSON for trivially-typed values.
    """

    data = models.DateField(db_index=True)
    clau = models.CharField(max_length=80, db_index=True)
    dimensio_1 = models.CharField(max_length=80, blank=True, default="")
    valor_int = models.BigIntegerField(null=True, blank=True)
    valor_float = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Snapshot del pipeline"
        verbose_name_plural = "Snapshots del pipeline"
        constraints = [
            models.UniqueConstraint(
                fields=["data", "clau", "dimensio_1"],
                name="metricapipeline_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["clau", "-data"]),
        ]

    def __str__(self) -> str:
        v = self.valor_int if self.valor_int is not None else self.valor_float
        return f"{self.data} {self.clau}/{self.dimensio_1}={v}"
