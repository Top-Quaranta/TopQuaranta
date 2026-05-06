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


class MetricaSocialPost(models.Model):
    """Engagement snapshot for a single published `SocialPost`.

    One row per (socialpost, data). The `recollir_metrics_social`
    cron polls the source platform once a day and upserts the
    counters here — keeping the time series lets us chart the
    engagement curve (most reach happens within 24-48 h of publish,
    so the daily delta = "fresh action" while the absolute number
    is the long-term total).

    Fields are deliberately the lowest-common-denominator across
    platforms (likes / replies / shares / reach / impressions /
    clicks). When a platform doesn't expose a metric we leave it
    at 0 — the `raw` JSONB stores the full API response so the
    UI can still surface platform-specific numbers (e.g. Bluesky
    quoteCount, IG saved/total_interactions) without a schema
    change every time Meta renames a field.
    """

    socialpost = models.ForeignKey(
        "social.SocialPost",
        on_delete=models.CASCADE,
        related_name="metriques",
    )
    data = models.DateField(db_index=True)
    likes = models.PositiveIntegerField(default=0)
    replies = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)  # reblogs / reposts / RTs
    reach = models.PositiveIntegerField(default=0)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)  # link-clicks (newsletter)
    raw = models.JSONField(blank=True, default=dict)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mètrica de publicació social"
        verbose_name_plural = "Mètriques de publicacions socials"
        constraints = [
            models.UniqueConstraint(
                fields=["socialpost", "data"],
                name="metricasocialpost_uniq",
            ),
        ]
        indexes = [
            # Most queries are "show me the latest snapshot per post" —
            # this keeps the planner happy on the dashboard rollups.
            models.Index(fields=["data", "socialpost"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.data} {self.socialpost_id} "
            f"L={self.likes} R={self.replies} S={self.shares}"
        )

    @property
    def total_engagement(self) -> int:
        """Sum used for ranking the top-performing posts."""
        return self.likes + self.replies + self.shares


class MetricaSocialPlatform(models.Model):
    """Daily account-level gauge per platform.

    Examples (`metric` value):
      - `followers`     — follower count (Mastodon, Bluesky, IG, Telegram)
      - `following`     — accounts followed (Mastodon, Bluesky)
      - `posts_total`   — lifetime status count
      - `members`       — Telegram channel member count

    One row per (data, platform, metric). Letting `metric` be a
    free CharField (instead of one column per metric) means new
    KPIs ship without a migration — the UI just adds another card.
    """

    data = models.DateField(db_index=True)
    platform = models.CharField(max_length=32, db_index=True)
    metric = models.CharField(max_length=40)
    valor = models.BigIntegerField()
    raw = models.JSONField(blank=True, default=dict)

    class Meta:
        verbose_name = "Mètrica de plataforma social"
        verbose_name_plural = "Mètriques de plataformes socials"
        constraints = [
            models.UniqueConstraint(
                fields=["data", "platform", "metric"],
                name="metricasocialplatform_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["platform", "metric", "-data"]),
        ]

    def __str__(self) -> str:
        return f"{self.data} {self.platform}/{self.metric}={self.valor}"


# ── SEO monitoring (Sprint S Bloc D) ────────────────────────────────


class MetricaSEOQuery(models.Model):
    """Daily Google Search Console snapshot per (query, page).

    GSC's `searchanalytics.query` gives us, for a 1-day range with
    `dimensions=['query', 'page']`, the impressions / clicks / CTR /
    avg position for every (search-term, landing-page) pair. We
    persist a thin slice of that so the staff dashboard can chart
    "how is this query trending" without re-fetching from GSC each
    time.

    Note: GSC anonymises queries that received <10 clicks across
    very few users; those rows simply don't appear in the response.
    No PII concerns on our side.
    """

    data = models.DateField(db_index=True)
    query = models.CharField(max_length=200)
    page = models.CharField(max_length=400)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    ctr = models.FloatField(default=0.0)
    position = models.FloatField(default=0.0)

    class Meta:
        verbose_name = "Mètrica SEO per query"
        verbose_name_plural = "Mètriques SEO per query"
        constraints = [
            models.UniqueConstraint(
                fields=["data", "query", "page"],
                name="metricaseoquery_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["-data", "-clicks"]),
            models.Index(fields=["query", "-data"]),
        ]

    def __str__(self) -> str:
        return f"{self.data} '{self.query}' → {self.page} ({self.clicks}/{self.impressions})"


class MetricaCWV(models.Model):
    """Daily PageSpeed Insights snapshot per URL + form factor.

    Tracks the Core Web Vitals (LCP, INP, CLS, FCP, TTFB) for the
    representative SPA pages — homepage, /top, /artistes, a sample
    artista page, etc. The cron polls PSI's `runPagespeed` API once
    a day per URL × form-factor (mobile + desktop = 2× the URL count).

    `category` is `mobile` or `desktop` (PSI's strategy parameter).
    `score` is the overall Performance score 0-100. Per-vital fields
    are the lab values; field-data values when available go into
    `raw` for later analysis.
    """

    data = models.DateField(db_index=True)
    url = models.CharField(max_length=400)
    category = models.CharField(max_length=10)  # "mobile" | "desktop"
    score = models.PositiveIntegerField(null=True, blank=True)
    lcp_ms = models.PositiveIntegerField(null=True, blank=True)
    inp_ms = models.PositiveIntegerField(null=True, blank=True)
    cls = models.FloatField(null=True, blank=True)
    fcp_ms = models.PositiveIntegerField(null=True, blank=True)
    ttfb_ms = models.PositiveIntegerField(null=True, blank=True)
    raw = models.JSONField(blank=True, default=dict)

    class Meta:
        verbose_name = "Core Web Vitals per URL"
        verbose_name_plural = "Core Web Vitals per URL"
        constraints = [
            models.UniqueConstraint(
                fields=["data", "url", "category"],
                name="metricacwv_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["-data", "url", "category"]),
        ]

    def __str__(self) -> str:
        return f"{self.data} {self.category} {self.url} score={self.score}"
