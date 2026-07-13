from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from music.models import Canco

# R8: bounds on ranking coefficients. A typo (0.25 -> 25) or an accidental
# negative value could wipe out the ranking for a week. We enforce sensible
# ranges at the model level so full_clean() and admin-style edits reject
# nonsense before it persists.
#
# Conservative ranges:
#   - Factors / multipliers: [0, 5]  (defaults are all <= 1.5)
#   - Penalty coefficients:  [0, 1]  (no negative penalties; never > 100%)
#   - Exponents:             [0, 10]
#   - Smoothing:             [0, 100]
#   - Threshold counts:      [0, 10000]
#   - Day-of-week:           [0, 6]

_PENALTY_RANGE = [MinValueValidator(0), MaxValueValidator(1)]
_EXPONENT_RANGE = [MinValueValidator(0), MaxValueValidator(10)]
_COUNT_RANGE = [MinValueValidator(0), MaxValueValidator(10000)]
_DAY_RANGE = [MinValueValidator(0), MaxValueValidator(6)]
# Soft-cap multiplier: the knee is M × the territori's median top plays,
# so M must be ≥ 1 (otherwise it would compress ordinary charting songs,
# not just outliers). Upper bound is a sanity guard against a typo.
_MULTIPLIER_RANGE = [MinValueValidator(1), MaxValueValidator(100)]


class ConfiguracioGlobal(models.Model):
    """
    Ranking algorithm coefficients. Single-row table.

    Simplified 2026-04-23 (algorithm v2.0): dropped `penalitzacio_descens`,
    `penalitzacio_setmana_0..2`, `suavitat` and the `max_factor_*` clamps.
    The new algorithm uses weekly Last.fm play deltas directly and applies
    just three penalties: age (exponential), cumulative past-top-position
    penalty, and monopoly (album + artist) multipliers.
    """

    # Defaults are Decimal(str) — never float — so full_clean() doesn't trip
    # on imprecise float → Decimal round-tripping.
    exponent_penalitzacio_antiguitat = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.5"),
        validators=_EXPONENT_RANGE,
        help_text="Antiguitat: penalty = min(1, (dies/365)^exponent).",
    )
    penalitzacio_album_per_canco = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal("0.25"),
        validators=_PENALTY_RANGE,
        help_text="Monopoli àlbum: per cada cançó anterior del mateix àlbum, "
        "multiplica el score per (1 - valor). 0.25 → x0.75 per cançó.",
    )
    penalitzacio_artista_per_canco = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal("0.2"),
        validators=_PENALTY_RANGE,
        help_text="Monopoli artista: per cada cançó anterior del mateix "
        "artista al rànquing, multiplica el score per (1 - valor). 0.2 → x0.8.",
    )
    coeficient_penalitzacio_top = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal("0.04"),
        validators=_PENALTY_RANGE,
        help_text="Penalització per setmanes anteriors al top. Per cada "
        "aparició a la posició N acumula: coeficient_base / 2^(N-1). "
        "Ex amb 0.04: pos 1 = 4%, pos 2 = 2%, pos 3 = 1%…",
    )
    min_cancons_ranking_propi = models.IntegerField(
        default=20,
        validators=_COUNT_RANGE,
    )
    # Minimum weekly_plays a Cançó must reach to enter the top at all.
    # Below this floor the algorithm treats the song as noise and
    # excludes it — preferring a shorter top over filling the tail
    # with 1-2 plays/week entries that round to score zero. Editorial
    # rule (2026-04-26): "el top no arriba a 40 i ja està" if the
    # eligible material doesn't pass this floor.
    min_escoltes_top = models.IntegerField(
        default=5,
        validators=_COUNT_RANGE,
        help_text="Cançons amb menys d'aquestes escoltes setmanals "
        "queden fora del top. Si això fa que un territori no arribi "
        "a 40 cançons, el top és més curt — no s'omple amb soroll.",
    )
    # PPCC aggregator weight per source position. Was a module-level
    # constant in `ranking/algorisme.py`; promoted to the configurable
    # surface 2026-04-25 (Sprint A) so editorial tuning doesn't require
    # a code change. Default 0.04 matches the previous hardcoded value.
    ppcc_penalitzacio_per_posicio = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal("0.04"),
        validators=_PENALTY_RANGE,
        help_text="PPCC: penalització per posició a la llista d'origen. "
        "Cada cançó d'un top territorial entra a PPCC amb un score "
        "multiplicat per (1 - (posició - 1) × valor). Ex amb 0.04: la "
        "#1 entra al 100 %, la #2 al 96 %, la #25 al 4 %.",
    )

    # ── Outlier soft-cap on weekly plays (2026-06-09) ───────────────
    # Targets the magnitude outlier (e.g. a mainstream artist with ~20×
    # the scrobbles of any PPCC act) WITHOUT touching ordinary charting
    # songs. The knee is adaptive PER TERRITORI:
    #     K_t = max(floor, multiplicador × median(top plays, last weeks))
    # and plays above the knee are compressed logarithmically:
    #     plays_eff = K_t · (1 + ln(plays / K_t))   for plays > K_t
    # Songs at or below K_t keep their raw plays — the normal top is
    # untouched. Default OFF so deploying changes nothing; staff opts in.
    # See docs/architecture/algorithm.md §2.1bis.
    soft_cap_actiu = models.BooleanField(
        default=False,
        help_text="Activa el sostre suau d'escoltes per a outliers. Si "
        "False, l'algorisme usa les escoltes brutes (comportament "
        "previ). El sostre és per territori i no afecta les cançons "
        "per sota del genoll.",
    )
    soft_cap_multiplicador = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("3"),
        validators=_MULTIPLIER_RANGE,
        help_text="Genoll del sostre = valor × mediana d'escoltes del "
        "top del territori (últimes setmanes). Per damunt del genoll les "
        "escoltes es comprimeixen. 3 → es considera outlier qui supera 3× "
        "el charting típic del seu territori.",
    )
    soft_cap_floor_escoltes = models.IntegerField(
        default=500,
        validators=_COUNT_RANGE,
        help_text="Genoll mínim del sostre, en escoltes. Protegeix els "
        "territoris menuts o sense prou historial (mediana inestable): "
        "si multiplicador × mediana queda per sota, s'usa aquest terra. "
        "També és el genoll de seguretat quan encara no hi ha historial.",
    )
    # The population the median is taken over: the top-N head of the
    # territori's rolling chart (NOT the whole top — the near-floor tail
    # would drag the median down and compress ordinary hits). Configurable
    # so the base isn't hardcoded; default 10 reproduces the recommended
    # "median of the top ~10" behaviour. Range 1-40 (the top caps at 40).
    soft_cap_base_top_n = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(40)],
        help_text="Població per a la mediana del genoll: el cap top-N del "
        "top rodant del territori (NO tot el top — la cua arrossegaria la "
        "mediana avall). 10 → mediana del top ~10. Rang 1-40.",
    )

    # ── Newsletter → Publicació bridge gate (additive, 2026-06-10) ──
    # When True, staff may mirror a NewsletterDraft into a public
    # community Publicació (admin pseudo-user as author). Default False:
    # the bridge endpoint refuses while off, nothing fires automatically,
    # and no real publication is ever triggered by deploying this.
    newsletter_publicacio_pont_actiu = models.BooleanField(
        default=False,
        help_text="Si True, l'staff pot publicar un esborrany de "
        "newsletter com a Publicació pública a la comunitat. Si False "
        "(per defecte), el pont està desactivat i l'endpoint el rebutja. "
        "Cap automatisme; res no es dispara sol.",
    )

    # ── Master distribution switch (2026-06-07) ─────────────────────
    # The REAL global pause: gates every channel via `pot_publicar`.
    # Default True so deploying changes nothing (the existing
    # per-channel state, e.g. instagram_actiu=False, is preserved).
    # Distinct from the per-channel `*_actiu` switches.
    distribucio_activa = models.BooleanField(
        default=True,
        help_text="Interruptor mestre de distribució. Si False, cap dels "
        "sis canals publica (IG, Mastodon, Bluesky, Telegram, newsletter, "
        "RSS). Independent dels switches per canal.",
    )

    # ── Sprint I: Instagram distribution controls ───────────────────────
    instagram_actiu = models.BooleanField(
        default=True,
        help_text="Switch per canal d'Instagram. Si False (o el mestre "
        "`distribucio_activa` False), `publicar_social` surt sense fer res. "
        "NO és el switch global; per a això hi ha `distribucio_activa`.",
    )

    # ── Sprint I bis: multi-channel distribution kill switches ──────
    # Each channel has its own switch so we can pause one without
    # touching the others (e.g. Mastodon instance is down, or we
    # want to skip a newsletter week without disabling the cron).
    mastodon_actiu = models.BooleanField(
        default=False,
        help_text="Kill switch per al cron de Mastodon. Si False, "
        "`publicar_mastodon` surt sense fer res.",
    )
    bluesky_actiu = models.BooleanField(
        default=False,
        help_text="Kill switch per al cron de Bluesky. Si False, "
        "`publicar_bluesky` surt sense fer res.",
    )
    telegram_actiu = models.BooleanField(
        default=False,
        help_text="Kill switch per al cron de Telegram. Si False, "
        "`publicar_canal --channel telegram` surt sense fer res.",
    )
    newsletter_actiu = models.BooleanField(
        default=False,
        help_text="Kill switch per al cron de newsletter setmanal. "
        "Si False, `enviar_newsletter` surt sense fer res.",
    )
    rss_actiu = models.BooleanField(
        default=True,
        help_text="Si False, els feeds /rss/*.xml retornen 503 (per a "
        "casos d'emergència — habitualment està sempre actiu).",
    )

    # ── Sprint Distribució v2 lot B: per-channel publish delay ──────
    # Cron fires each channel at its base time (see deploy/cron.topquaranta).
    # Each command sleeps `delay_<channel>_min` minutes before doing
    # work, so staff can spread the schedule wider WITHOUT editing
    # crontab. To compress below the cron base, the cron file itself
    # has to be edited and reinstalled — these fields are additive.
    # Capped at 180 min as a sanity guard (a worker holds a slot
    # idle for the duration; longer than 3 h is almost certainly an
    # operator typo).
    delay_instagram_min = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Minuts de retard addicional per a publicar_social (IG). "
            "0 = publica al moment cron. Tope 180."
        ),
    )
    delay_mastodon_min = models.PositiveSmallIntegerField(
        default=0,
        help_text="Minuts de retard addicional per a Mastodon. Tope 180.",
    )
    delay_bluesky_min = models.PositiveSmallIntegerField(
        default=0,
        help_text="Minuts de retard addicional per a Bluesky. Tope 180.",
    )
    delay_telegram_min = models.PositiveSmallIntegerField(
        default=0,
        help_text="Minuts de retard addicional per a Telegram. Tope 180.",
    )
    delay_newsletter_min = models.PositiveSmallIntegerField(
        default=0,
        help_text="Minuts de retard addicional per a newsletter. Tope 180.",
    )
    editorial_veu = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Prompt de veu editorial per a la rutina de newsletter. "
            "Servit dins el brief; editable des de Configuració. "
            "Buit = la rutina no genera res."
        ),
    )
    # Dedicated voice for the SEO landing prose routine. Kept SEPARATE
    # from `editorial_veu` (newsletter) so the two tones don't collide:
    # a landing answer-paragraph reads nothing like a weekly newsletter.
    # Empty = the landing routine generates nothing (clean STOP).
    landing_editorial_veu = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Prompt de veu editorial per a la rutina de prosa de landings "
            "SEO (territoris, generes, decades). Independent de la veu del "
            "newsletter. Servit dins el brief de landing-routine; editable "
            "des de Configuració. Buit = la rutina no genera res."
        ),
    )

    # How many novetats releases fit on each Instagram novetats story
    # before it spills to the next one. The novetats set is paginated
    # into ceil(N/per_page) stories so every release surfaces (was a
    # single 3-item slide). Staff-editable from Configuració. Clamped to
    # 1..8 by the renderer (`social/renderer.py::render_stories_novetats`);
    # 4 keeps the item scale close to the old 3-per-slide look.
    novetats_stories_per_pagina = models.PositiveSmallIntegerField(
        default=4,
        help_text=(
            "Novetats per story d'Instagram abans de passar a la següent "
            "(paginació). Les novetats es reparteixen en diverses stories "
            "perquè apareguen totes. Inicial 4; el renderer el limita a 1-8."
        ),
    )

    # ── IG collaborator invitations (ADR-0015, tranche 1 — INERT) ────
    # All dormant until `ig_collaboradors_actiu` is switched on. The
    # slot policy (`social/collaboradors.py`) and the acceptance poller
    # (`pollar_colaboracions_ig`) read these; nothing is wired into the
    # publisher yet. See docs/decisions/0015-ig-collaborator-invitations.md.
    ig_collaboradors_actiu = models.BooleanField(
        default=False,
        help_text=(
            "Flag mestre del sistema d'invitacions de col·laboradors "
            "d'Instagram (feed). Apagat = capa dormida: cap invitació, "
            "cap fila escrita, el poller fa no-op."
        ),
    )
    ig_collab_slots_total = models.PositiveSmallIntegerField(
        default=3,
        help_text=(
            "Slots de col·laborador per publicació de feed. Límit dur de "
            "la Graph API = 3; la política aplica min(valor, 3)."
        ),
    )
    ig_collab_slots_acceptats = models.PositiveSmallIntegerField(
        default=2,
        help_text="Slots reservats a artistes que ja han acceptat abans (categoria A).",
    )
    ig_collab_cooldown_a_dies = models.PositiveSmallIntegerField(
        default=15,
        help_text="Dies abans de reinvitar un artista de categoria A (ja acceptador).",
    )
    ig_collab_cooldown_c_dies = models.PositiveSmallIntegerField(
        default=90,
        help_text="Dies abans de reinvitar un artista rebutjat (categoria C).",
    )

    # Channel arg → its per-channel `*_actiu` field. Single source of
    # truth for the set of distribution channels the master gates.
    CHANNEL_SWITCH_FIELDS = {
        "instagram": "instagram_actiu",
        "mastodon": "mastodon_actiu",
        "bluesky": "bluesky_actiu",
        "telegram": "telegram_actiu",
        "newsletter": "newsletter_actiu",
        "rss": "rss_actiu",
    }

    def pot_publicar(self, canal: str) -> bool:
        """True iff `canal` may publish: the master switch
        (`distribucio_activa`) AND the channel's own `*_actiu`.

        Does NOT consider the per-(canal × tipus) matrix — that's the
        third gate (`MatriuPublicacio.actiu_per`), applied separately in
        the publishers. Single gate shared by every publisher so the
        master truly stops all six channels."""
        field = self.CHANNEL_SWITCH_FIELDS.get(canal)
        if field is None:
            raise ValueError(f"unknown canal {canal!r}")
        return bool(self.distribucio_activa and getattr(self, field))

    def pot_publicar_tipus(self, canal: str, tipus: str) -> bool:
        """`pot_publicar(canal)` AND the `(canal × tipus)` matrix cell.

        The THIRD distribution gate, after the master switch and the
        per-channel switch: an `actiu=False` row in `MatriuPublicacio`
        means this channel does not distribute this content type. The
        website and RSS are never gated by the matrix. For Instagram this
        is an ADDITIONAL gate over the per-slot phase gating, which stays
        intact (an off-phase slot is still 'omès' on its own)."""
        if not self.pot_publicar(canal):
            return False
        return MatriuPublicacio.actiu_per(canal, tipus)

    class Meta:
        verbose_name = "Configuració global"
        verbose_name_plural = "Configuració global"

    def save(self, *args, **kwargs):
        self.pk = 1
        # R8: ensure validators run on every save, including admin-form saves.
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SenyalDiari(models.Model):
    """
    Daily Last.fm snapshot per track.
    Stores raw cumulative values. One row per (canco, data).
    """

    # R2: SET_NULL so historical signal survives artist / track deletions.
    # A null canco row becomes an anonymous data point; it's raw Last.fm
    # telemetry, there's no snapshot name to preserve here.
    canco = models.ForeignKey(
        Canco,
        on_delete=models.SET_NULL,
        null=True,
        related_name="senyals",
    )
    data = models.DateField()

    lastfm_playcount = models.BigIntegerField(null=True)
    lastfm_listeners = models.IntegerField(null=True)

    # R5: Last.fm with autocorrect=1 can silently return a different track —
    # we ask for "Mira / Artist X", Last.fm answers with "Mira / Artist Y"
    # data because it "thinks" we meant them. Store what the API actually
    # returned so we can flag silent drift. `corregit` is set at ingest
    # time when the returned names diverge significantly from what we
    # asked for (see obtenir_senyal._detect_drift).
    lastfm_returned_track = models.CharField(max_length=500, blank=True)
    lastfm_returned_artista = models.CharField(max_length=255, blank=True)
    corregit = models.BooleanField(default=False, db_index=True)

    # 2026-04-23: the old percentile-normalised `score_entrada` field has
    # been dropped. Algorithm v2.0 operates directly on `lastfm_playcount`
    # deltas (plays this week vs. a week ago) so normalisation is unused.

    error = models.BooleanField(default=False)
    error_msg = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("canco", "data")]
        ordering = ["-data"]
        indexes = [
            models.Index(fields=["canco", "data"]),
            models.Index(fields=["data", "error"]),
            models.Index(fields=["data", "corregit"]),
        ]

    def __str__(self) -> str:
        return f"{self.canco} — {self.data}"


class TopSetmanal(models.Model):
    """Weekly ranking result. setmana = Monday of the ranking week (ISO).

    This is the cultural archive. Once a row is written it must remain
    reproducible and displayable forever, so we:

    - R2: keep the row even if the Canco/Artista that produced it is
      deleted (on_delete=SET_NULL + name/artist snapshots).
    - R1: freeze the algorithm identity (algorithm_version) and the
      coefficient set used (config_snapshot) so future code changes can
      never silently alter what this week's ranking was.
    """

    # R2: SET_NULL so deleting an artist or track does not wipe their
    # historical chart positions. unique_together is per (canco, ...),
    # which tolerates null canco because Postgres treats NULLs as distinct.
    canco = models.ForeignKey(
        Canco,
        on_delete=models.SET_NULL,
        null=True,
        related_name="rankings",
    )
    territori = models.CharField(max_length=4)
    setmana = models.DateField()
    posicio = models.PositiveSmallIntegerField()
    score_setmanal = models.FloatField()

    # Raw weekly_plays (rolling 7-day delta) that produced this row.
    # Persisted since 2026-06-09 so the adaptive soft-cap can read the
    # territori's historical median plays cheaply (no signal recompute).
    # Nullable: rows written before this field existed stay NULL and are
    # simply skipped by the median query (the floor fallback covers it).
    weekly_plays = models.FloatField(null=True, blank=True)

    # R2: snapshots so the row remains self-describing if canco is NULL.
    canco_nom_snapshot = models.CharField(max_length=500, blank=True)
    artista_nom_snapshot = models.CharField(max_length=255, blank=True)

    # R1: algorithm provenance. algorithm_version is a semantic tag we
    # bump when the ranking formula changes in a user-visible way.
    # config_snapshot is the set of coefficients (ConfiguracioGlobal)
    # that produced this row. Both let us recompute a historical ranking
    # deterministically — or at least prove what computed it.
    algorithm_version = models.CharField(max_length=20, default="v1.0")
    config_snapshot = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("canco", "territori", "setmana")]
        ordering = ["territori", "posicio"]
        indexes = [
            models.Index(fields=["setmana", "territori"]),
            # D6: hot path for homepage + /ranking/?t=X is
            # `filter(territori=X, setmana=Y).order_by("posicio")[:40]`.
            # A composite (territori, setmana, posicio) lets PostgreSQL
            # seek to the exact slice and read rows already sorted by
            # posicio — zero sort work. At 130k rows (~5 years out) this
            # turns a ~200 ms query into ~1 ms.
            models.Index(fields=["territori", "setmana", "posicio"]),
        ]

    def __str__(self) -> str:
        nom = self.canco.nom if self.canco_id else (self.canco_nom_snapshot or "?")
        return f"#{self.posicio} {nom} ({self.territori}) — {self.setmana}"


class TopProvisional(models.Model):
    """
    Rolling daily ranking. Recalculated every day at 07:00.
    Truncated and rebuilt on each run — not a historical record.
    """

    # R2: SET_NULL for consistency with the rest of the ranking stack,
    # though provisional rows are rebuilt daily so the guarantee is
    # weaker here. No snapshot — a null canco is effectively a tombstone
    # that the next rebuild will replace.
    canco = models.ForeignKey(
        Canco,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ranking_provisional",
    )
    territori = models.CharField(max_length=4)
    posicio = models.PositiveSmallIntegerField()
    score_setmanal = models.FloatField()
    # v2.0: rolling 7-day plays delta (algorithm output `weekly_plays`).
    # Renamed from the historic `lastfm_playcount` (which used to mean
    # the cumulative total) on 2026-04-25 (Sprint A) so the semantics
    # match the column name. The legacy `dies_en_top` companion column
    # was dropped at the same time — it had been NULL since v2.0.
    escoltes_setmanals = models.IntegerField(null=True)
    # Per-cançó algorithm breakdown, for staff diagnostics.
    age_factor = models.FloatField(null=True)
    past_top_factor = models.FloatField(null=True)
    monopoli_factor = models.FloatField(null=True)
    data_calcul = models.DateField(auto_now=True)

    class Meta:
        unique_together = [("canco", "territori")]
        ordering = ["territori", "posicio"]
        indexes = [models.Index(fields=["territori", "posicio"])]

    def __str__(self) -> str:
        return f"#{self.posicio} {self.canco.nom} ({self.territori})"


# Backward-compat aliases (Sprint Naming, 2026-04-25). External code
# may still import the old class names; keep them resolvable until the
# whole codebase has migrated. The DB tables will be renamed by the
# next migration; the aliases just point to the new classes.
RankingSetmanal = TopSetmanal
RankingProvisional = TopProvisional


class MatriuPublicacio(models.Model):
    """Per-(canal × tipus) distribution toggle.

    A THIRD gate on top of `ConfiguracioGlobal.distribucio_activa`
    (master) and `<canal>_actiu` (per-channel): with `actiu=False`, that
    channel does NOT distribute that content type that week. Seeded
    (migration 0020) with one active row per (canal × tipus) combination
    actually published today, so the default behaviour is identical to
    before the matrix existed.

    Conceptual model: the website generates and shows the top regardless
    and is NEVER governed here; RSS (pull-based) is likewise out. Only the
    five push channels are: instagram, mastodon, bluesky, telegram,
    newsletter. A content type (top global / top territorial / nous
    singles / nous albums) is NOT a channel — it is distributed across
    several channels, and the newsletter is just one of them.
    """

    CANAL_INSTAGRAM = "instagram"
    CANAL_MASTODON = "mastodon"
    CANAL_BLUESKY = "bluesky"
    CANAL_TELEGRAM = "telegram"
    CANAL_NEWSLETTER = "newsletter"
    CANALS = [
        (CANAL_INSTAGRAM, "Instagram"),
        (CANAL_MASTODON, "Mastodon"),
        (CANAL_BLUESKY, "Bluesky"),
        (CANAL_TELEGRAM, "Telegram"),
        (CANAL_NEWSLETTER, "Newsletter"),
    ]

    canal = models.CharField(max_length=20, choices=CANALS)
    # A `SocialPost.TIPUS_*` value (top_ppcc / top_territorial /
    # nous_singles / nous_albums). Kept as a plain CharField (no FK) to
    # avoid a cross-app constraint; the seed only inserts real combos.
    tipus = models.CharField(max_length=20)
    actiu = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Matriu de publicació"
        verbose_name_plural = "Matriu de publicació"
        ordering = ["canal", "tipus"]
        constraints = [
            models.UniqueConstraint(
                fields=["canal", "tipus"], name="matriu_canal_tipus_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.canal} × {self.tipus} = {'on' if self.actiu else 'off'}"

    @classmethod
    def actiu_per(cls, canal: str, tipus: str) -> bool:
        """True iff `(canal, tipus)` may distribute.

        A MISSING row defaults to True: that is the fail-open default
        matching the pre-matrix world (no per-tipus gate existed), so a
        combo nobody seeded never silently blocks. The matrix only ever
        BLOCKS via an explicit `actiu=False` row."""
        row = cls.objects.filter(canal=canal, tipus=tipus).only("actiu").first()
        return True if row is None else row.actiu
