from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


class Territori(models.Model):
    """
    Territory for Catalan-language music rankings.
    Managed via data migration, not admin.
    """

    codi = models.CharField(max_length=4, primary_key=True)
    nom = models.CharField(max_length=50)

    class Meta:
        ordering = ["codi"]
        verbose_name = "Territori"
        verbose_name_plural = "Territoris"

    def __str__(self) -> str:
        return self.nom


class Municipi(models.Model):
    """
    Municipality within the Catalan-speaking territories.

    Populated from the legacy 'municipis' table. Each municipality belongs
    to a comarca and a territory. Used as FK target for ArtistaLocalitat.
    """

    nom = models.CharField(max_length=255)
    comarca = models.CharField(max_length=255)
    territori = models.ForeignKey(
        Territori,
        on_delete=models.PROTECT,
        related_name="municipis",
    )

    class Meta:
        ordering = ["nom"]
        verbose_name = "Municipi"
        verbose_name_plural = "Municipis"
        unique_together = [("nom", "comarca")]

    def __str__(self) -> str:
        return f"{self.nom} ({self.comarca})"


class Artista(models.Model):
    """
    A music artist tracked by TopQuaranta.

    Territories are derived from ArtistaLocalitat → Municipi → Territori.
    The M2M 'territoris' is kept in sync automatically via signals.
    Artists can belong to multiple territories (e.g. Marala → CAT, VAL, BAL).
    A track appears in territory T if ANY of its artists belongs to T.
    """

    PERCENTATGE_FEMENI_CHOICES = [
        ("100", "100%"),
        ("50+", "50% o més"),
        ("<50", "Menys del 50%"),
        ("0", "0%"),
    ]

    spotify_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    # R10: `deezer_id` legacy direct field removed 2026-04-16. Use the
    # ArtistaDeezer M2M exclusively (via `deezer_id_principal` property or
    # `deezer_ids` related manager).
    lastfm_nom = models.CharField(
        max_length=255,
        help_text="Exact name for Last.fm API calls (case-sensitive).",
    )
    # D2: lastfm_mbid dropped 2026-04-17 — was populated historically from
    # Last.fm but never consumed by any code path. Regenerate via a
    # Last.fm artist.getInfo call if ever needed.
    nom = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    territoris = models.ManyToManyField(
        Territori,
        related_name="artistes",
        blank=True,
        help_text="Auto-synced from ArtistaLocalitat. Do not edit directly.",
    )
    # Discovery provenance (immutable after creation).
    auto_descobert = models.BooleanField(
        default=False,
        help_text="True if the artist was auto-discovered (feat. resolution, "
        "Viasona ingest, etc.). Historical record of how the artist got "
        "into the system — NOT to be used as an 'in pendents queue' flag. "
        "Use `pendent_review` for that.",
    )
    font_descoberta = models.CharField(
        max_length=50,
        blank=True,
        help_text="Source: 'viasona', 'collaborador', 'deezer_contributor', "
        "'manual', 'legacy'.",
    )
    aprovat = models.BooleanField(
        default=True,
        db_index=True,
        help_text="False = pending human review in staff panel.",
    )
    # Staff review queue flag. Separate from `aprovat` so we can
    # distinguish "needs triage" from "already triaged and rejected":
    # - aprovat=True  pendent_review=False → live
    # - aprovat=False pendent_review=True  → at /staff/artistes/pendents/
    # - aprovat=False pendent_review=False → descartat (kept for FK integrity)
    # - aprovat=True  pendent_review=True  → forbidden by CheckConstraint
    pendent_review = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True = appears in /staff/artistes/pendents/ for review.",
    )

    # Deezer metadata (populated by obtenir_metadata)
    deezer_nb_fan = models.IntegerField(null=True, blank=True)
    deezer_nb_album = models.IntegerField(null=True, blank=True)
    deezer_nom = models.CharField(max_length=255, blank=True)
    deezer_nom_similitud = models.FloatField(null=True, blank=True)

    # Last.fm indexing status. Set True the first time obtenir_senyal
    # observes a non-zero playcount on ANY of the artist's tracks. Used
    # by the staff panel to distinguish real Last.fm errors (artist is
    # indexed but a specific track isn't) from silent tracks (artist
    # is unknown to Last.fm; errors are expected, not actionable).
    lastfm_te_scrobbles = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True iff Last.fm returned playcount>0 for at least one "
        "track by this artist. Maintained by obtenir_senyal.",
    )

    # R11: legacy location fields (localitat, comarca, provincia) dropped
    # 2026-04-16. ArtistaLocalitat is the sole source of truth. Read via
    # `localitat_principal` property or iterate `localitats.all()`.

    # Genre and gender representation
    genere = models.CharField(
        max_length=255,
        blank=True,
        help_text="Musical genre (free text).",
    )
    percentatge_femeni = models.CharField(
        max_length=10,
        blank=True,
        choices=PERCENTATGE_FEMENI_CHOICES,
        help_text="Female representation percentage.",
    )

    # Manager-authored short bio. Distinct from the Last.fm fields above
    # which are auto-synced from `obtenir_metadata_lastfm` and would
    # overwrite anything stored there. This field is owned by verified
    # gestors (UserArtista.verificat=True) via the /compte/artista/<pk>/
    # editar endpoint; staff can also edit it from the admin form.
    bio = models.TextField(
        blank=True,
        help_text="Short bio written by the artist's verified manager.",
    )

    # Social links
    spotify_url = models.URLField(blank=True)
    viasona_url = models.URLField(blank=True)
    web_url = models.URLField(blank=True)
    bandcamp_url = models.URLField(blank=True)
    myspace_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    viquipedia_url = models.URLField(blank=True)
    soundcloud_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    # X (formerly Twitter). Both x.com and twitter.com URLs land here;
    # mb_sync routes them by host.
    twitter_url = models.URLField(blank=True)

    last_checked_deezer = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time Deezer was queried for new albums.",
    )

    # ── MusicBrainz metadata ────────────────────────────────────────────
    # Populated by obtenir_metadata_musicbrainz (rate-limited to 1 req/s).
    # All fields optional — artists below MB's coverage stay empty.
    musicbrainz_id = models.CharField(
        max_length=36,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="MBID (UUID) — the authoritative ID for Crim-style collisions.",
    )
    mb_type = models.CharField(max_length=20, blank=True)  # Group / Person / Other
    mb_gender = models.CharField(max_length=20, blank=True)  # male / female / other
    mb_area = models.CharField(max_length=120, blank=True)
    mb_area_hierarchy = models.JSONField(default=list, blank=True)
    mb_begin_date = models.DateField(null=True, blank=True)
    mb_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Dissolution / cessation date. New releases past this date "
        "are almost certainly a different artist with the same name.",
    )
    mb_disambiguation = models.CharField(max_length=255, blank=True)
    mb_sort_name = models.CharField(max_length=255, blank=True)
    mb_aliases = models.JSONField(default=list, blank=True)
    mb_tags = models.JSONField(default=list, blank=True)  # genres
    mb_rating = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True
    )
    mb_discography_cache = models.JSONField(default=dict, blank=True)
    mb_last_sync = models.DateTimeField(null=True, blank=True, db_index=True)
    # Round-robin cursor into MB's release-group list (May-2026
    # ops fix). MB rate-limits at 1 req/sec and one big artist
    # (e.g. Schenker, 48 release-groups × ~1.1 s each = >50 s of
    # MB calls plus the per-track recordings) used to monopolise an
    # entire cron tick. We now process at most
    # `MB_RGS_PER_RUN` (= 20, see music.constants) release-groups
    # per call to `sync_from_mbid`; the cursor advances and resets
    # to 0 once a full pass is done. Big artists then drain over
    # several ticks predictably while small ones still finish in
    # one.
    mb_sync_cursor = models.PositiveIntegerField(default=0)
    # MBIDs that staff has explicitly rejected for this artist. The
    # auto-resolver skips any candidate whose id appears here, so a
    # homonym that matched once can't silently match again on the next
    # cron run.
    mb_blocked_mbids = models.JSONField(default=list, blank=True)
    # Stops `resolve_mbid` from proposing ANY match for this artist,
    # even one that's not in the blocklist. Use when we know MB has no
    # entry for this artist at all — avoids recurring false positives
    # on common names.
    mb_auto_match_disabled = models.BooleanField(default=False)

    # ── Last.fm artist metadata ─────────────────────────────────────────
    # Populated by `obtenir_metadata_lastfm` (daily 05:00 UTC) via
    # `artist.getInfo` + `artist.getSimilar`. Bio fields keep raw HTML
    # (Last.fm returns it that way; render with safe-strip downstream).
    # `lastfm_playcount_total` is the cumulative playcount on Last.fm
    # for this artist — distinct from the per-track per-day samples in
    # `SenyalDiari.lastfm_playcount`.
    lastfm_url = models.URLField(blank=True)
    lastfm_bio_summary = models.TextField(blank=True)
    lastfm_bio_content = models.TextField(blank=True)
    lastfm_bio_published = models.DateTimeField(null=True, blank=True)
    lastfm_listeners = models.BigIntegerField(null=True, blank=True)
    lastfm_playcount_total = models.BigIntegerField(null=True, blank=True)
    lastfm_ontour = models.BooleanField(null=True, blank=True)
    lastfm_tags = models.JSONField(default=list, blank=True)
    lastfm_image_small = models.URLField(blank=True)
    lastfm_image_medium = models.URLField(blank=True)
    lastfm_image_large = models.URLField(blank=True)
    lastfm_image_extralarge = models.URLField(blank=True)
    lastfm_last_sync = models.DateTimeField(null=True, blank=True, db_index=True)
    # Symmetric to `mb_auto_match_disabled`: stops the daily Last.fm
    # sync from touching this artist. Use when the Last.fm name slot
    # is shared with a homonym (Crim-style collision) so the listeners
    # / playcount / bio / similars would be a polluted aggregate.
    lastfm_auto_match_disabled = models.BooleanField(default=False)
    # Number of times this artist has been surfaced as a similar by
    # `artist.getSimilar` of another aprovat artist. Higher = more
    # recommended by Last.fm's network. Used as a triage score on the
    # pendents page so high-affinity discoveries float to the top.
    nb_similars_lastfm = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    # SEO Sprint S (2026-05-06): single source of truth for sitemap
    # `lastmod` and HTTP `Last-Modified` headers on the per-artist
    # SSR view. Initial migration backfills from `mb_last_sync` when
    # available, falling back to `created_at` — see migration
    # `music/0061_*` for the rationale.
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Artista"
        verbose_name_plural = "Artistes"
        constraints = [
            # An approved artist must not be sitting in the pendents queue.
            # The four (aprovat, pendent_review) states are documented on
            # the `pendent_review` field docstring.
            models.CheckConstraint(
                condition=~models.Q(aprovat=True, pendent_review=True),
                name="artista_no_aprovat_pendent_review",
            ),
        ]
        indexes = [
            models.Index(
                fields=["pendent_review", "aprovat"],
                name="artista_pendent_review_idx",
            ),
        ]

    def __str__(self) -> str:
        codis = ",".join(self.territoris.values_list("codi", flat=True))
        return f"{self.nom} ({codis})" if codis else self.nom

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base = slugify(self.nom) or "artista"
            slug = base
            n = 1
            while Artista.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        # Postgres treats two empty strings as colliding values in a
        # UNIQUE column, so any setattr path that lands "" on a
        # nullable-unique CharField would violate the constraint the
        # moment a second row had the same. Normalise to NULL —
        # Postgres allows multiple NULLs in a UNIQUE column.
        if self.musicbrainz_id == "":
            self.musicbrainz_id = None
        if self.spotify_id == "":
            self.spotify_id = None
        super().save(*args, **kwargs)

    def clean(self):
        # R11: approved artists must have at least one ArtistaLocalitat.
        # No fallback to legacy fields — they don't exist anymore.
        if self.aprovat and self.pk:
            if not self.localitats.exists():
                raise ValidationError(
                    "No es pot aprovar un artista sense almenys una localitat."
                )

    @property
    def deezer_id_principal(self) -> int | None:
        """Primary Deezer ID from ArtistaDeezer.

        R10: the direct `Artista.deezer_id` column was dropped; ArtistaDeezer
        is now the single source of truth. Returns the row flagged
        `principal=True`, or the first one if none is, or None if the
        artist has no Deezer link yet.
        """
        ad = self.deezer_ids.filter(principal=True).first()
        if ad:
            return ad.deezer_id
        ad = self.deezer_ids.first()
        return ad.deezer_id if ad else None

    @property
    def all_deezer_ids(self) -> list[int]:
        """All Deezer IDs for this artist."""
        return list(self.deezer_ids.values_list("deezer_id", flat=True))

    @property
    def localitat_principal(self) -> str:
        """Display string of the artist's primary location.

        R11: the legacy `localitat/comarca/provincia` columns were dropped;
        ArtistaLocalitat is now the sole source of truth. Reads the first
        linked location and composes "Town, Comarca" (or the manual text
        if there's no linked municipi). Empty string for artists with no
        location yet.
        """
        loc = self.localitats.select_related("municipi").first()
        if loc is None:
            return ""
        if loc.municipi is not None:
            return f"{loc.municipi.nom}, {loc.municipi.comarca}"
        return loc.localitat_manual or ""

    def get_territoris(self) -> list[str]:
        """Return list of territory codes for this artist."""
        return list(self.territoris.values_list("codi", flat=True))

    def sync_territoris_from_localitats(self) -> None:
        """Recompute M2M territoris from ArtistaLocalitat → Municipi → Territori.

        Called automatically by ArtistaLocalitat signals. Rules:

          * Every PPCC municipi contributes its territori (CAT, VAL, …).
          * Every `localitat_manual` (municipi=NULL) contributes ALT —
            even if the artist also has PPCC localitats. An artist with
            a member from outside the PPCC should show up both in their
            PPCC territori and in the catch-all Altres top.
          * Artists with zero ArtistaLocalitat rows keep their legacy
            M2M (migration safety net).
        """
        if not self.pk:
            return
        localitats_qs = self.localitats.all()
        if not localitats_qs.exists():
            return  # No ArtistaLocalitat entries — keep legacy M2M
        territori_ids = set(
            localitats_qs.filter(municipi__isnull=False).values_list(
                "municipi__territori_id", flat=True
            )
        )
        has_manual = localitats_qs.filter(municipi__isnull=True).exists()
        if has_manual:
            territori_ids.add("ALT")
        if not territori_ids:
            # Paranoia: shouldn't happen given the guards above, but keep
            # the invariant that an approved artist has ≥1 territori.
            territori_ids = {"ALT"}
        self.territoris.set(list(territori_ids))

    SOCIAL_LINK_FIELDS = [
        ("spotify_url", "Spotify"),
        ("viasona_url", "Viasona"),
        ("web_url", "Web"),
        ("bandcamp_url", "Bandcamp"),
        ("myspace_url", "Myspace"),
        ("youtube_url", "YouTube"),
        ("viquipedia_url", "Viquipèdia"),
        ("soundcloud_url", "SoundCloud"),
        ("tiktok_url", "TikTok"),
        ("facebook_url", "Facebook"),
        ("instagram_url", "Instagram"),
        ("twitter_url", "X"),
    ]


class ArtistaDeezer(models.Model):
    """Links an Artista to one or more Deezer artist IDs."""

    artista = models.ForeignKey(
        Artista,
        on_delete=models.CASCADE,
        related_name="deezer_ids",
    )
    deezer_id = models.BigIntegerField(unique=True)
    principal = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Artista Deezer ID"
        verbose_name_plural = "Artista Deezer IDs"

    def __str__(self) -> str:
        return f"{self.artista.nom} → {self.deezer_id}"


class ArtistaLastfmAlias(models.Model):
    """Additional Last.fm name(s) for an artist whose scrobbles are
    fragmented across multiple Last.fm pages (typographic apostrophe
    vs ASCII, missing diacritics, casing — typical for PPCC artists).

    The signal collector (`obtenir_senyal`) sums playcounts/listeners
    across the canonical `Artista.lastfm_nom` AND every confirmed
    alias. A track that scrobbled as 'Boira' (1 681 plays) and
    'Böira' (21 487 plays) becomes a single 23 168-play signal in
    our DB.

    Lifecycle:
      * `detectar_lastfm_aliases` populates rows with confirmat=False
        for every candidate found via top-tracks overlap (≥50% top-5
        match). The detector NEVER auto-confirms — homonyms can leak
        through if their top tracks happen to coincide.
      * Staff confirms (or rejects) each candidate at
        /staff/artistes/<pk>. Confirmation flips `confirmat=True`
        and the alias starts contributing to the signal sum from
        the next `obtenir_senyal` run.
      * Rejected aliases stay in the table with `confirmat=False`
        + `rebutjat=True`, so re-running the detector doesn't
        re-propose the same homonym.

    Caught 2026-05-01 from the Delên case + audit; see
    `scripts/lastfm_alias_audit.py` and roadmap entry for context.
    """

    artista = models.ForeignKey(
        Artista,
        on_delete=models.CASCADE,
        related_name="lastfm_aliases",
    )
    nom = models.CharField(
        max_length=255,
        help_text=(
            "Variant Last.fm name (e.g. 'Böira' alongside 'Boira'). "
            "Stored case-sensitive — Last.fm's URL is case-insensitive "
            "but the API requires the exact spelling for `autocorrect=0` "
            "queries."
        ),
    )
    descobert_at = models.DateTimeField(auto_now_add=True)
    confirmat = models.BooleanField(
        default=False,
        help_text="Staff has confirmed this alias is the same artist.",
    )
    confirmat_at = models.DateTimeField(null=True, blank=True)
    confirmat_per = models.ForeignKey(
        "comptes.Usuari",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    rebutjat = models.BooleanField(
        default=False,
        help_text=(
            "Staff has explicitly rejected this candidate as a homonym. "
            "Kept in DB so re-running the detector doesn't re-propose it."
        ),
    )
    # Detection-time evidence — useful for staff to evaluate the
    # candidate without leaving the page.
    playcount_canonical = models.IntegerField(
        null=True,
        blank=True,
        help_text="Last.fm playcount of the canonical page at detection time.",
    )
    playcount_variant = models.IntegerField(
        null=True,
        blank=True,
        help_text="Last.fm playcount of this variant at detection time.",
    )
    top_tracks_overlap = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Share of top-5 tracks that match between the two pages "
            "(0..1). Higher is more confident; the detector requires "
            "≥0.5."
        ),
    )

    class Meta:
        verbose_name = "Artista Last.fm alias"
        verbose_name_plural = "Artista Last.fm aliases"
        constraints = [
            models.UniqueConstraint(
                fields=["artista", "nom"],
                name="uniq_artista_lastfm_alias_nom",
            ),
        ]

    def __str__(self) -> str:
        state = (
            "confirmat"
            if self.confirmat
            else "rebutjat" if self.rebutjat else "pendent"
        )
        return f"{self.artista.nom} ↔ {self.nom} [{state}]"


class ArtistaLastfmSimilar(models.Model):
    """One row per (source_artist → target_artist) recommendation
    seen at Last.fm's `artist.getSimilar`.

    Why a row-per-recommendation rather than the previous integer
    counter `Artista.nb_similars_lastfm`:

    Two design issues with the integer:

      1. **Double-counting variants**: if Manel's similars include
         both 'Delên' and 'dêlen' (the same artist with different
         spellings), the old counter went up by 2 when the actual
         signal is 1 unique recommender. With this table we dedup
         per `source_artist` — multiple variant names resolving to
         the same target collapse into one row.

      2. **No way to recompute**: a fresh-pull from Last.fm couldn't
         correct over-counted targets without remembering who had
         recommended whom. The integer was append-only. This table
         lets each source's recommendation set be REPLACED on every
         re-pull, so the count stays honest.

    Caught 2026-05-01 in the same investigation as
    `ArtistaLastfmAlias` (Boira/Böira → 14× signal loss for the
    canonical, similar inflation on the targets it recommends).

    The integer `Artista.nb_similars_lastfm` is kept as a denorm
    cache (= COUNT(*) FROM this table WHERE target_id=…) to avoid
    a JOIN on every artistes-list query.
    """

    source = models.ForeignKey(
        Artista,
        on_delete=models.CASCADE,
        related_name="similars_recomanats",
        help_text="Artist whose getSimilar response surfaced this row.",
    )
    target = models.ForeignKey(
        Artista,
        on_delete=models.CASCADE,
        related_name="recomanat_per",
        help_text=(
            "Artist being recommended (resolved through the alias table "
            "so 'Delên' and 'dêlen' map to the same target)."
        ),
    )
    last_seen = models.DateTimeField(auto_now=True)
    match = models.FloatField(
        null=True,
        blank=True,
        help_text="Last.fm's similarity score for this pair (0–1).",
    )

    class Meta:
        verbose_name = "Last.fm similar (source→target)"
        verbose_name_plural = "Last.fm similars (source→target)"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target"],
                name="uniq_lastfm_similar_source_target",
            ),
        ]
        indexes = [
            models.Index(fields=["target"]),
        ]

    def __str__(self) -> str:
        return f"{self.source.nom} → {self.target.nom}"


class ArtistaLocalitat(models.Model):
    """Links an artist to one or more municipalities (locations).

    Each entry represents one location the artist is associated with.
    Territories are derived automatically from municipi → territori.
    For non-PPCC artists, municipi is NULL and localitat_manual is used.
    """

    artista = models.ForeignKey(
        Artista,
        on_delete=models.CASCADE,
        related_name="localitats",
    )
    municipi = models.ForeignKey(
        Municipi,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="artistes_localitat",
        help_text="NULL for non-PPCC artists (Altres).",
    )
    localitat_manual = models.CharField(
        max_length=255,
        blank=True,
        help_text="Free text for non-PPCC locations or display override.",
    )
    descripcio = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional qualifier, e.g. 'nascut a' or 'resident a'.",
    )

    class Meta:
        verbose_name = "Localitat d'artista"
        verbose_name_plural = "Localitats d'artista"

    def __str__(self) -> str:
        if self.municipi:
            return f"{self.artista.nom} → {self.municipi.nom}"
        return f"{self.artista.nom} → {self.localitat_manual} (Altres)"

    @property
    def nom_display(self) -> str:
        """Human-readable location name."""
        if self.municipi:
            return self.municipi.nom
        return self.localitat_manual or "Altres"

    @property
    def comarca_display(self) -> str:
        """Human-readable comarca."""
        if self.municipi:
            return self.municipi.comarca
        return ""

    @property
    def territori_display(self) -> str:
        """Territory code derived from municipi."""
        if self.municipi:
            return self.municipi.territori_id
        return "ALT"


class Album(models.Model):
    TIPUS_CHOICES = [
        ("album", "Àlbum"),
        ("single", "Single"),
        ("ep", "EP"),
    ]

    spotify_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    deezer_id = models.BigIntegerField(unique=True, null=True, blank=True)
    artista = models.ForeignKey(
        Artista, on_delete=models.CASCADE, related_name="albums"
    )
    nom = models.CharField(max_length=500)
    slug = models.SlugField(max_length=550, unique=True, blank=True)
    data_llancament = models.DateField(null=True, blank=True)
    tipus = models.CharField(max_length=10, choices=TIPUS_CHOICES, default="album")
    imatge_url = models.URLField(blank=True)
    cancons_obtingudes = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "DEPRECATED (May 2026). The hourly cron used to skip albums "
            "with this flag set, which produced ~3.7k 'phantom' albums "
            "marked OK but holding zero tracks (Deezer flake + the "
            "`album_old` shortcut). Replaced by `last_album_check` + "
            "an age-based cooldown so every non-discarded album is "
            "re-scanned periodically and missing tracks recover on the "
            "next tick. Field kept for backward compat; do not filter on it."
        ),
    )
    last_album_check = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Last time obtenir_novetats P2 fetched this album's tracks "
            "from Deezer. Cooldown gate: recent albums (<30 days since "
            "release) re-checked daily, mid-aged (30-365 days) weekly, "
            "old (>1 year) monthly. NULL means never checked → highest "
            "priority."
        ),
    )
    descartat = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if all tracks were rejected. Skipped by obtenir_novetats.",
    )
    source_deezer_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Which `ArtistaDeezer.deezer_id` of the album's artista this row "
            "was originally fetched from. Set by `_create_album` (cron) and "
            "`_upsert_album` (--force). Used by `_try_auto_unlink_homonym_deezer` "
            "to scope the homonym unlink to one specific Deezer profile when "
            "the artista has several. NULL on legacy rows (pre-2026-05-03); "
            "the smart unlink falls back to a defer-to-staff path in that case."
        ),
    )

    # MusicBrainz cross-reference. `mbrainz_confirmed=True` means MB has a
    # release-group attributed to the Artista's MBID that matches this album.
    mb_release_group_id = models.CharField(max_length=36, blank=True, db_index=True)
    mb_type_secondary = models.CharField(
        max_length=30, blank=True
    )  # Live/Remix/Compilation…
    mb_status = models.CharField(
        max_length=30, blank=True
    )  # Official/Bootleg/Promotion…
    mbrainz_confirmed = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    # SEO Sprint S (2026-05-06). See Artista.updated_at note. Initial
    # backfill uses `last_album_check` when set (which Cron P2 touches
    # on every Deezer re-scan).
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-data_llancament"]

    def __str__(self) -> str:
        return f"{self.nom} — {self.artista.nom}"

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base = slugify(self.nom) or "album"
            slug = base
            n = 1
            while Album.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        # Mirror of the Artista.save normalisation — see comment there.
        if self.spotify_id == "":
            self.spotify_id = None
        super().save(*args, **kwargs)


class CancoQuerySet(models.QuerySet):
    """Custom manager methods for Canco. May-2026 audit: the
    `verificada=True, activa=True` filter pair was repeated in 33
    locations across the codebase; centralising it here prevents
    drift when a third "publishable" flag ever needs to be added."""

    def public(self):
        """Tracks visible to the public site / counted by the ranking."""
        return self.filter(verificada=True, activa=True)

    def pendents(self):
        """Live but undecided — the staff review queue."""
        return self.filter(verificada=False, activa=True)


class Canco(models.Model):
    """
    A single track. Only tracks released within the last 12 months are ingested.

    In the new model, a track exists ONCE (not duplicated per territory like legacy).
    Territory is derived from the artists:
      - artista: main artist (FK, for display and default lookups)
      - artistes_col: collaborating artists (M2M)
    A track appears in territory T if ANY artist (main or collaborator) belongs to T.

    Custom manager: use `Canco.objects.public()` or `.pendents()` to
    avoid hand-rolling the verificada/activa filter pair.
    """

    objects = CancoQuerySet.as_manager()

    spotify_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    deezer_id = models.BigIntegerField(unique=True, null=True, blank=True)
    isrc = models.CharField(
        max_length=15,
        blank=True,
        help_text="International Standard Recording Code.",
    )
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="cancons")
    artista = models.ForeignKey(
        Artista,
        on_delete=models.CASCADE,
        related_name="cancons",
        help_text="Main artist (for display). Territory also from collaborators.",
    )
    artistes_col = models.ManyToManyField(
        Artista,
        related_name="participacions",
        blank=True,
        help_text="Collaborating artists. Track appears in their territories too.",
    )
    nom = models.CharField(max_length=500)
    # URL slug for SEO-friendly public URLs. Globally unique; generated
    # in save() from `nom` with a numeric suffix when collisions happen.
    # Prefixed by artist slug gives the SPA `/artista/<a>/<album>/<canco>`
    # style nesting, but the authoritative lookup is this slug alone.
    slug = models.SlugField(max_length=560, unique=True, blank=True)
    lastfm_nom = models.CharField(
        max_length=500,
        blank=True,
        help_text="Track name as returned by Last.fm (may differ from Spotify).",
    )
    # D2: lastfm_mbid + lastfm_verificat dropped 2026-04-17 — both had
    # zero populated rows and zero consumers. See Canco model above /
    # docs/history/roadmap.md (sprint A) for context.
    # R5: "Last.fm's autocorrect of our query IS the correct track".
    # When True, obtenir_senyal stops flagging SenyalDiari rows for this
    # track as corrected even when the returned names differ from what
    # we sent. Flipped by staff from /staff/senyal/ after reviewing a
    # drift flag and deciding Last.fm was right.
    lastfm_confirmed = models.BooleanField(default=False)
    durada_ms = models.IntegerField(null=True, blank=True)
    preview_url = models.URLField(max_length=500, blank=True)
    data_llancament = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Tracks older than 12 months are excluded from ingestion.",
    )
    activa = models.BooleanField(default=True, db_index=True)
    verificada = models.BooleanField(
        default=False,
        db_index=True,
        help_text="False = pending admin review. Only verified tracks enter the ranking.",
    )
    ml_classe = models.CharField(max_length=1, blank=True, db_index=True)
    ml_confianca = models.FloatField(null=True, blank=True)
    # Whisper large-v3 language identification over the Deezer preview.
    # Populated nightly by `analitzar_whisper`; leave NULL → not yet analysed
    # so the next run picks it up. `whisper_lang` is a 2-letter ISO code
    # (ca, es, en, fr, it, pt, …) or empty string on model failure.
    # `whisper_p` is the top-1 language probability in [0, 1].
    whisper_lang = models.CharField(max_length=3, blank=True, db_index=True)
    whisper_p = models.FloatField(null=True, blank=True)
    # Full language → probability map over Whisper's 99 languages. Richer
    # signal than (lang, p): a prediction it=0.50 ca=0.45 vs it=0.95 ca=0.01
    # tell the classifier very different stories. Stored as JSONB.
    whisper_all_probs = models.JSONField(null=True, blank=True)
    whisper_processat_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # MusicBrainz cross-reference.
    mb_recording_id = models.CharField(max_length=36, blank=True, db_index=True)
    mb_work_id = models.CharField(max_length=36, blank=True)
    mb_lyrics_language = models.CharField(
        max_length=3,
        blank=True,
        help_text="Work.language from MusicBrainz ('cat' = strong Catalan signal).",
    )
    mbrainz_confirmed = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    # SEO Sprint S (2026-05-06). See Artista.updated_at note. No
    # better proxy than created_at on Canco — `auto_now=True` from
    # this point captures every staff edit / verification flip /
    # ML reclassification going forward.
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Cançó"
        verbose_name_plural = "Cançons"
        indexes = [
            # D6: obtenir_senyal filters `activa + verificada + artista +
            # data_llancament`. `verificada` + `activa` already carry
            # db_index=True each, but the combination (verificada,
            # artista) matches the most common shape and lets the planner
            # avoid an index intersection step.
            models.Index(fields=["verificada", "artista"]),
        ]
        constraints = [
            # D1: ISRC is the universal track key — once it's set, no two
            # Cancons may share it. Empty string is allowed for legacy
            # Last.fm-only entries that never got Deezer metadata.
            models.UniqueConstraint(
                fields=["isrc"],
                condition=~models.Q(isrc=""),
                name="canco_isrc_unique_when_set",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.nom} — {self.artista.nom}"

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            # Base: "<artist>-<track>" — gives search engines both
            # keywords on the URL. Fall back to "canco-<pk>" if name
            # slugifies empty (unusual but possible with all-accent
            # titles after ASCII folding fails).
            artist_bit = slugify(self.artista.nom) if self.artista_id else ""
            track_bit = slugify(self.nom) or f"canco-{self.pk or 'nova'}"
            base = f"{artist_bit}-{track_bit}".strip("-") if artist_bit else track_bit
            base = base[:550]  # leave headroom for the "-N" suffix
            slug = base
            n = 1
            while Canco.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        # Mirror of the Artista.save normalisation — see comment there.
        if self.spotify_id == "":
            self.spotify_id = None
        super().save(*args, **kwargs)

    @property
    def lastfm_lookup_nom(self) -> str:
        """Return the best name for Last.fm API calls."""
        return self.lastfm_nom if self.lastfm_nom else self.nom

    def get_territoris(self) -> set[str]:
        """
        Return all territories this track should appear in.
        Union of main artist's territories + all collaborators' territories.
        """
        codis = set(self.artista.territoris.values_list("codi", flat=True))
        codis.update(
            Territori.objects.filter(artistes__participacions=self).values_list(
                "codi", flat=True
            )
        )
        return codis


class HistorialRevisio(models.Model):
    DECISIONS = [
        ("aprovada", "Aprovada"),
        ("rebutjada", "Rebutjada"),
    ]
    MOTIUS = [
        ("ok", "En català i correcte"),
        ("no_catala", "La cançó no és en català"),
        ("artista_incorrecte", "El perfil Deezer no és el nostre artista"),
        ("album_incorrecte", "L'àlbum sencer no pertany al nostre artista"),
        ("no_musica", "No és música (podcast, audiollibre...)"),
    ]

    canco_deezer_id = models.BigIntegerField(null=True, blank=True)
    canco_spotify_id = models.CharField(max_length=50, blank=True)
    canco_isrc = models.CharField(max_length=20, blank=True)

    canco_nom = models.CharField(max_length=500)
    artista_nom = models.CharField(max_length=255)
    artista_territori = models.CharField(max_length=10, blank=True)
    album_nom = models.CharField(max_length=500, blank=True)
    data_llancament = models.DateField(null=True, blank=True)
    isrc_prefix = models.CharField(max_length=5, blank=True)

    artista_deezer_id = models.BigIntegerField(null=True, blank=True)
    artista_deezer_nb_fan = models.IntegerField(null=True, blank=True)
    artista_deezer_nb_album = models.IntegerField(null=True, blank=True)
    artista_nom_deezer = models.CharField(max_length=255, blank=True)
    artista_nom_similitud = models.FloatField(null=True, blank=True)

    ml_classe_decisio = models.CharField(
        max_length=1,
        blank=True,
        help_text="ML class at the time of decision.",
    )
    ml_confianca_decisio = models.FloatField(
        null=True,
        blank=True,
        help_text="ML confidence at the time of decision.",
    )

    decisio = models.CharField(max_length=20, choices=DECISIONS)
    motiu = models.CharField(max_length=50, choices=MOTIUS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Historial de revisió"
        verbose_name_plural = "Historial de revisions"
        indexes = [
            models.Index(fields=["decisio", "motiu"]),
            models.Index(fields=["canco_isrc"]),
            models.Index(fields=["artista_deezer_id"]),
            # P3: ml.py hot paths run per track during recalcular_ml.
            # Each pair (artista_nom|isrc_prefix, decisio) is queried
            # both alone and with decisio="rebutjada". Composite index
            # serves both the full-match lookup and the single-column
            # lookup on the leading field.
            models.Index(fields=["artista_nom", "decisio"]),
            models.Index(fields=["isrc_prefix", "decisio"]),
        ]

    def __str__(self) -> str:
        return f"{self.canco_nom} — {self.decisio} ({self.motiu})"


class StaffAuditLog(models.Model):
    """R9: immutable record of every destructive or consequential staff action.

    Append-only log. The UI at /staff/auditlog/ is read-only; by convention,
    nothing in the codebase deletes or mutates rows after creation. Actor,
    action, and target snapshot are captured so the log remains meaningful
    even if the target record is later deleted.

    `metadata` is a JSON blob for action-specific context — e.g. motiu of
    a rejection, the field diff of a config change, the source/target of a
    merge. Keep keys stable (documented where each action site creates
    them) so the audit view can format them consistently.
    """

    # Action taxonomy. Extend conservatively — every new value should be
    # usable as a filter on the audit page.
    ACTION_CHOICES = [
        # Cançons
        ("canco_aprovar", "Cançó: aprovar"),
        ("canco_rebutjar", "Cançó: rebutjar"),
        ("canco_rebutjar_album", "Cançó: rebutjar àlbum sencer"),
        ("canco_edit", "Cançó: edició"),
        # Artistes
        ("artista_aprovar", "Artista: aprovar"),
        ("artista_rebutjar", "Artista: rebutjar"),
        ("artista_marcar_sense_deezer", "Artista: marcar sense Deezer"),
        ("artista_fusionar", "Artista: fusionar"),
        ("artista_crear", "Artista: crear"),
        ("artista_edit", "Artista: edició"),
        ("artista_mbid_auto_unassign", "Artista: MBID auto-rebutjat"),
        ("artista_mbid_auto_restore", "Artista: MBID restaurat (correcció)"),
        ("lastfm_alias_confirm", "Last.fm alias: confirmat"),
        ("lastfm_alias_reject", "Last.fm alias: rebutjat (homònim)"),
        ("lastfm_alias_delete", "Last.fm alias: eliminat"),
        ("lastfm_alias_manual_add", "Last.fm alias: afegit manualment"),
        # Artistes pendents (auto-discovered)
        ("pendent_aprovar", "Pendent: aprovar"),
        ("pendent_descartar", "Pendent: descartar"),
        # Àlbums
        ("album_edit", "Àlbum: edició"),
        ("album_descartar", "Àlbum: descartar"),
        # Propostes d'artistes nous
        ("proposta_aprovar", "Proposta: aprovar"),
        ("proposta_rebutjar", "Proposta: rebutjar"),
        # Sol·licituds de gestió
        ("sollicitud_aprovar", "Sol·licitud: aprovar"),
        ("sollicitud_rebutjar", "Sol·licitud: rebutjar"),
        # Configuració global
        ("config_update", "Configuració global: actualitzada"),
        # Usuaris
        ("usuari_desactivar", "Usuari: desactivar"),
        ("usuari_reactivar", "Usuari: reactivar"),
        ("usuari_reset_2fa", "Usuari: reset 2FA"),
        # Edits performed by a verified artist manager (UserArtista.verificat)
        # via the public /compte/artista/<pk>/editar endpoint. Distinct from
        # `artista_edit` so the audit page can filter staff vs. self-service.
        ("gestor_edita_artista", "Artista: edició per gestor"),
        # Sprint I — social distribution.
        ("social_publicat", "Social: publicat (Instagram)"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_audit_entries",
        help_text="Staff user who performed the action. NULL if actor was "
        "deleted — the action itself is still in the record.",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)

    # Target snapshot — so the row remains meaningful after the target goes.
    target_type = models.CharField(
        max_length=30,
        blank=True,
        help_text='e.g. "Canco", "Artista", "Album", "Proposta", "Config".',
    )
    target_id = models.BigIntegerField(null=True, blank=True)
    target_label = models.CharField(
        max_length=500,
        blank=True,
        help_text="Human-readable identifier of the target at action time.",
    )

    # Action-specific context (reason, diff, counts, …). No schema.
    metadata = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Entrada d'auditoria staff"
        verbose_name_plural = "Auditoria staff"
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self) -> str:
        who = self.actor.email if self.actor_id else "(deleted user)"
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {who} · {self.action} · {self.target_label}"


class SpotifyAuth(models.Model):
    """Singleton row storing the admin's Spotify OAuth refresh token.

    Populated once by the `autoritzar_spotify` management command after
    the admin walks through Spotify's Authorization Code flow. The
    refresh token is long-lived (no expiry unless the user revokes it
    from Spotify's dashboard) so the daily cron can keep rolling over
    access tokens without any human intervention.

    Single-row invariant enforced by always using pk=1.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    refresh_token = models.TextField()
    scope = models.CharField(max_length=500, blank=True)
    spotify_user_id = models.CharField(max_length=100)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Autorització Spotify"
        verbose_name_plural = "Autoritzacions Spotify"

    def save(self, *args, **kwargs):
        # Enforce singleton even if someone tries to create a second row.
        self.id = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SpotifyAuth | None":
        return cls.objects.filter(pk=1).first()

    def __str__(self) -> str:
        return f"Spotify auth for @{self.spotify_user_id}"


class SpotifyPlaylist(models.Model):
    """A Spotify playlist we sync from the data.

    `spotify_playlist_id` is pre-set by `configurar_spotify_playlists`
    (the admin passes the existing Spotify playlist IDs they already
    own). The daily sync command replaces the tracklist in place so
    subscribers keep the same URL and follower count.
    """

    KIND_TOP = "top"
    KIND_NOVETATS = "novetats"
    KIND_CHOICES = [
        (KIND_TOP, "Top provisional"),
        (KIND_NOVETATS, "Novetats"),
    ]

    codi = models.SlugField(max_length=50, unique=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    # Only used when kind=top. Empty string for kind=novetats.
    territori = models.CharField(max_length=10, blank=True)
    spotify_playlist_id = models.CharField(max_length=100, blank=True)

    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_ok = models.BooleanField(default=True)
    last_sync_msg = models.TextField(blank=True)
    last_n_tracks = models.IntegerField(default=0)
    last_n_matched = models.IntegerField(default=0)

    class Meta:
        ordering = ["codi"]
        verbose_name = "Playlist Spotify"
        verbose_name_plural = "Playlists Spotify"

    def __str__(self) -> str:
        return f"{self.codi} ({self.kind}:{self.territori or '-'})"
