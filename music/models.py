import re
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.utils.text import slugify

from music.constants import SOCIAL_LINK_FIELDS as _SOCIAL_LINK_FIELDS

_HOMONIM_STRIP_RE = re.compile(r"[^a-z0-9]+")


def normalitza_nom_homonim(nom: str) -> str:
    """Normalised key for homonym detection: lowercase, strip diacritics, and
    drop EVERYTHING that isn't a-z0-9 (punctuation, apostrophes, spaces). So
    "Sr. À", "sra" and "S R A" collapse to the same key. Deliberately
    aggressive — it backs a staff *heads-up* marker (possible homonym), never
    an automatic block."""
    s = unicodedata.normalize("NFKD", nom or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return _HOMONIM_STRIP_RE.sub("", s.lower())


# Same shape as `comptes.models.HTTP_ONLY_URL` — defined locally to
# avoid a music→comptes cross-app import (`comptes` already depends
# on `music` via the UserArtista FK). Used by the `imatge_url`
# upload field added in Sprint Portal Artista (2026-05-19).
HTTP_ONLY_URL = URLValidator(schemes=["http", "https"])


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


class ArtistaQuerySet(models.QuerySet):
    """Custom manager methods for Artista. May-2026 audit: the
    `aprovat=True` filter and the PPCC / has-MBID / has-localitats
    membership tests were repeated across the codebase. Centralising
    them here mirrors the `CancoQuerySet` pattern.
    """

    def public(self):
        """Approved artistes — visible to the public site."""
        return self.filter(aprovat=True)

    def pendents(self):
        """In the staff review queue (auto-discovered, awaiting triage)."""
        return self.filter(aprovat=False, pendent_review=True)

    def with_ppcc(self):
        """Artistes anchored in Països Catalans (any PPCC localitat).

        A localitat is "PPCC" when it has a non-NULL `municipi` FK
        (non-PPCC localitats use `localitat_manual` and leave municipi
        NULL). `distinct()` because the M2M-style join inflates rows.
        """
        return self.filter(localitats__municipi__isnull=False).distinct()

    def with_mbid(self):
        """Artistes with a MusicBrainz ID set."""
        return self.filter(musicbrainz_id__isnull=False).exclude(musicbrainz_id="")


class Artista(models.Model):
    """
    A music artist tracked by TopQuaranta.

    Territories are derived from ArtistaLocalitat → Municipi → Territori.
    The M2M 'territoris' is kept in sync automatically via signals.
    Artists can belong to multiple territories (e.g. Marala → CAT, VAL, BAL).
    A track appears in territory T if ANY of its artists belongs to T.

    Custom manager: use `Artista.objects.public()` for approved-only,
    `.pendents()` for the staff queue, `.with_ppcc()` for the PPCC
    subset, or `.with_mbid()` for MB-resolved artistes.
    """

    objects = ArtistaQuerySet.as_manager()

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
    # Homonym key: `normalitza_nom_homonim(nom)` (lowercase, no diacritics, no
    # punctuation/spaces). Maintained in `save()` + backfilled by migration.
    # Two artistes with the same non-empty value are homonyms → the staff UI
    # flags them so reviewers are extra careful (the Crim case: same name,
    # different bands, can't both be approved on one shared Deezer profile).
    nom_normalitzat = models.CharField(max_length=255, blank=True, db_index=True)
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

    # Manager-uploaded artist hero image (Sprint Portal Artista,
    # 2026-05-19). Stored as a URL pointing to MEDIA_ROOT under
    # `media/artista/<artista_pk>/<uuid>.webp` — the pipeline lives
    # in `web/api/_image_pipeline.py`. URLField (not ImageField)
    # mirrors the `PerfilUsuari.imatge_url` pattern: Caddy serves
    # `/media/*` directly without Django, so storing the absolute
    # URL keeps the model agnostic to the storage backend.
    imatge_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        validators=[HTTP_ONLY_URL],
        help_text=(
            "Imatge custom de l'artista. Si està buida, s'usa la "
            "del Last.fm o caratula d'album."
        ),
    )

    # Cooldown anchor for the gestor's "demanar revisió de cançons"
    # action (Sprint Portal Artista, 2026-05-19). Updated by the
    # `cancons-pendents/ping-staff/` endpoint when the gestor sends
    # a moderation ping to staff via DM. NULL = no ping ever sent;
    # endpoint refuses if (now - x) < timedelta(days=7).
    ultim_ping_revisio_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Timestamp de l'últim ping de revisió de cançons enviat "
            "pel gestor. Usat per al cooldown de 7 dies."
        ),
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

    # SEO Sprint S Bloc D (2026-05-06): canonical genre for the
    # `/genere/<slug>` programmatic-SEO surface. Auto-inferred by the
    # `inferir_genere` cron from `lastfm_tags` + `mb_tags` via the
    # mapping in `music.genere`. Staff can pin a value manually
    # (sets `genere_locked=True`) and the cron will leave it alone.
    # 16 canonical genres, alphabetical (Catalan locale). Labels are
    # single-word — no slash-separated alternatives — to keep the
    # dropdown clean. Mapping rationale (data-driven from Last.fm/MB
    # tags) lives in `music/genere.py`.
    GENERE_CANONICAL_CHOICES = [
        ("cantautor", "Cantautor"),
        ("electronica", "Electrònica"),
        ("experimental", "Experimental"),
        ("folk", "Folk"),
        ("hardcore", "Hardcore"),
        ("hip-hop", "Hip-hop"),
        ("indie", "Indie"),
        ("infantil", "Infantil"),
        ("jazz", "Jazz"),
        ("metal", "Metal"),
        ("pop", "Pop"),
        ("punk", "Punk"),
        ("reggae", "Reggae"),
        ("rock", "Rock"),
        ("ska", "Ska"),
        ("urba", "Urbà"),
    ]
    genere_canonical = models.CharField(
        max_length=20,
        choices=GENERE_CANONICAL_CHOICES,
        blank=True,
        default="",
        db_index=True,
    )
    genere_locked = models.BooleanField(default=False)

    # Spotify dispersion signal (Process B output, see ADR-0012).
    # `spotify_artist_dispersio` is the count of DISTINCT principal
    # Spotify artist IDs across all this artista's enriched Cançons.
    # 1 means every enriched track points to one Spotify artist (clean
    # mapping); >1 means Deezer probably merged two distinct artists
    # under the same Deezer ID (Crim-style collision). The triage UI
    # surfaces this as a "possible barreja" badge so staff catch it
    # before approving cançons that don't actually belong here.
    spotify_artist_dispersio = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Distinct principal spotify_artist_id count across this "
            "artist's enriched tracks. >1 suggests Deezer homonym merge."
        ),
    )
    spotify_artist_ids_distints = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Sorted list of the distinct principal Spotify artist IDs "
            "seen across enriched cançons. Mirrors dispersio for debug."
        ),
    )

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

    def homonims(self):
        """Other Artista rows whose name is the same modulo accents +
        punctuation (the homonym marker). Empty for a blank key."""
        key = self.nom_normalitzat or normalitza_nom_homonim(self.nom)
        if not key:
            return Artista.objects.none()
        return Artista.objects.filter(nom_normalitzat=key).exclude(pk=self.pk)

    def save(self, *args, **kwargs) -> None:
        self.nom_normalitzat = normalitza_nom_homonim(self.nom)
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

    # Canonical iteration order lives in music.constants. The
    # myspace_url URLField is kept on the model (legacy data may
    # still be present) but no longer surfaces in UI/serializer
    # iteration through this attribute.
    SOCIAL_LINK_FIELDS = _SOCIAL_LINK_FIELDS


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

    # Sprint Portal Artista (2026-05-19): the artist's `lastfm_nom`
    # used to be the single source of truth for the canonical
    # Last.fm name. The new convention: one of the artist's aliases
    # is marked `prioritari=True` and that row drives the canonical
    # name (mirrored to `Artista.lastfm_nom` via a post_save signal
    # on this model). Other confirmed aliases continue to contribute
    # to signal aggregation in `obtenir_senyal`.
    prioritari = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "Un sol prioritari per artista. Determina quin nom és "
            "el principal als CRUD i el mirror a Artista.lastfm_nom."
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
            # At most one prioritari row per artista. Conditional
            # constraint so rows with prioritari=False can coexist
            # freely. PostgreSQL supports partial UNIQUE indexes;
            # Django translates the `condition` into the right CREATE
            # UNIQUE INDEX ... WHERE prioritari SQL.
            models.UniqueConstraint(
                fields=["artista"],
                condition=models.Q(prioritari=True),
                name="uniq_artista_lastfm_prioritari",
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

    # Record label as reported by Deezer's `album.label` field (e.g.
    # "Halley Records", "Bankrobber", "Producciones Peligrosas",
    # autoedit names). Stored verbatim — Deezer keeps the raw label
    # string, no normalisation. Useful as ML signal (`same_label_as_
    # approved`, `label_compartit_amb_PPCC`) and as a staff-curation
    # cue. Populated by `obtenir_metadata` + `obtenir_novetats` when
    # creating/updating Albums; empty string on legacy rows or when
    # Deezer omits the field.
    label = models.CharField(max_length=200, blank=True, db_index=True)

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
    # Raw Deezer contributors that did NOT match the canco's main
    # `artista` and didn't already exist in our DB by `deezer_id`.
    # Populated by `obtenir_novetats._create_track`,
    # `obtenir_novetats._backfill_isrc`, and
    # `obtenir_metadata._upsert_track` instead of immediately creating
    # `Artista(pendent_review=True)` rows.
    #
    # This deferral is the 2026-05-07 fix for the dominant rejection
    # cause: 76 % of song rebuigs are `album_incorrecte` — Deezer
    # name-collapsed two homonymous artists into a single profile, and
    # every track from the wrong "Dept" dragged a chain of unrelated
    # collaborators into our pending review queue. By postponing the
    # pendent-Artista creation until staff verifies the canco, we
    # avoid creating pendents from cançons that end up rebutjades —
    # eliminating ~76 % of the queue noise outright.
    #
    # Shape: `[{"name": str, "deezer_id": int, "role": "main"|"secondary"}]`.
    # Processed by `music.services.processar_collaboradors_pendents`
    # on `aprovar_canco` / `aprovar_canco_auto_ml`, then cleared.
    contributors_raw = models.JSONField(default=list, blank=True)
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

    def artistes_col_ordered(self):
        """Collaborators ordered by their insertion order in the M2M
        through table (`canco_artistes_col`'s autoincremented PK).

        The M2M was declared without an explicit `through`, so the
        default through table exposes its own `id` column — that's the
        insertion order. The naive `self.artistes_col.all()` queryset
        is ordered by Artista's own Meta.ordering (alphabetical by
        `nom`), which gives unstable visual ordering on the social
        renderer week-to-week.

        Approach: hit the through-table directly to fetch the artista
        PKs in insertion order, then materialise via `Artista.objects`
        with a `Case/When` that re-applies that exact order — Django's
        `WHERE pk IN (...)` doesn't preserve order on its own, even
        when the IN list is sorted (Postgres returns rows in physical
        table order).
        """
        from django.db.models import Case, IntegerField, Value, When

        through = self.artistes_col.through
        ordered_ids = list(
            through.objects.filter(canco_id=self.pk)
            .order_by("id")
            .values_list("artista_id", flat=True)
        )
        if not ordered_ids:
            return Artista.objects.none()
        when_clauses = [When(pk=pk, then=Value(i)) for i, pk in enumerate(ordered_ids)]
        return Artista.objects.filter(pk__in=ordered_ids).order_by(
            Case(*when_clauses, output_field=IntegerField())
        )

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
    # `motiu` records the action that resolved this HR row.
    # For `decisio="aprovada"`: `ok` (manual approval) or
    # `auto_ml` (RF auto-approval). For `decisio="rebutjada"`: one
    # of the action codes in `music.constants.MOTIUS_REBUIG`. See
    # the contract each value implies in
    # `docs/architecture/staff.md` section 5; do not duplicate the
    # prose here. Action-only labels keep the choices list short
    # and unambiguous; cause/when-to-use lives in the doc.
    MOTIUS = [
        ("ok", "Aprovada"),
        ("auto_ml", "Aprovada per ML"),
        ("desvincular_canco", "Desvincular la cançó"),
        ("desvincular_album", "Desvincular l'àlbum"),
        ("desvincular_artista", "Desvincular l'artista"),
    ]

    canco_deezer_id = models.BigIntegerField(null=True, blank=True)
    canco_spotify_id = models.CharField(max_length=50, blank=True)
    canco_isrc = models.CharField(max_length=20, blank=True)

    canco_nom = models.CharField(max_length=500)
    artista_nom = models.CharField(max_length=255)
    # Comma-joined list of territoris codes for the artista at decision
    # time (`crear_historial` does ",".join). Bumped from 10 → 100 on
    # 2026-05-08 after `aprovar_canco` failed with `value too long for
    # type character varying(10)` on a multi-territori artista
    # ("CAT,VAL,BAL" = 11 chars). 100 fits every PPCC artista (10
    # codes × 4 chars + 9 commas = 49). `crear_historial` also
    # truncates defensively as a belt-and-braces guard.
    artista_territori = models.CharField(max_length=100, blank=True)
    album_nom = models.CharField(max_length=500, blank=True)
    data_llancament = models.DateField(null=True, blank=True)
    isrc_prefix = models.CharField(max_length=5, blank=True)

    artista_deezer_id = models.BigIntegerField(null=True, blank=True)
    artista_deezer_nb_fan = models.IntegerField(null=True, blank=True)
    artista_deezer_nb_album = models.IntegerField(null=True, blank=True)
    artista_nom_deezer = models.CharField(max_length=255, blank=True)
    artista_nom_similitud = models.FloatField(null=True, blank=True)
    # Snapshot of the principal Spotify artist id at decision time
    # (read from `SpotifyMetadata.spotify_artist_id` of the canço).
    # Empty when the canço had no enrichment yet; the backfill
    # command at `backfill_artista_spotify_id_in_historial` fills
    # legacy rows once Process B catches up. Keyed by the per-pair
    # rejection-ratio feature in `music.ml`; see
    # `docs/architecture/pipeline.md` section 4.
    artista_spotify_id = models.CharField(max_length=50, blank=True, db_index=True)
    # Stamped by `enriquir_spotify_rebuigs` orphan flow every time
    # an ISRC lookup is attempted for this row, regardless of
    # whether Spotify returned a match. The candidate query
    # excludes rows looked up within the last 30 days so a
    # not-found ISRC is not re-searched on every nightly run.
    # NULL = never attempted. See migration 0086.
    spotify_lookup_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Set by the rebuig backfill (`enriquir_spotify_rebuigs`) "
            "every time the orphan flow runs an ISRC lookup against "
            "Spotify for this row. NULL = never attempted. The "
            "candidate query excludes rows looked up within the "
            "last 30 days, regardless of whether the previous "
            "attempt resolved the artist or not."
        ),
    )

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

    # Sprint Workflow Sol·licituds (2026-05-20). When True, the
    # ingestion cron may re-pick up the track this row rejected —
    # i.e. it's been "reconsidered" by staff after a manager's
    # SolicitudRevisio. Default False: every existing rejected row
    # stays out of the pipeline unless explicitly re-opened.
    reconsiderada = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "Quan True, obtenir_novetats pot re-ingerir aquesta cançó "
            "(sortida del filtre de rebuigs)."
        ),
    )

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
        ("artista_sync_mb", "Artista: re-sincronitzar des de MusicBrainz"),
        ("lastfm_alias_confirm", "Last.fm alias: confirmat"),
        ("lastfm_alias_reject", "Last.fm alias: rebutjat (homònim)"),
        ("lastfm_alias_delete", "Last.fm alias: eliminat"),
        ("lastfm_alias_manual_add", "Last.fm alias: afegit manualment"),
        # Artistes pendents (auto-discovered)
        ("pendent_aprovar", "Pendent: aprovar"),
        ("pendent_descartar", "Pendent: descartar"),
        ("pendent_orphan_merged", "Pendent: fusionar òrfan amb canònic"),
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
        ("usuari_esborrar", "Usuari: esborrar (RGPD)"),
        ("usuari_reenviar_verificacio", "Usuari: reenviar email de verificació"),
        (
            "usuari_enviar_reset_password",
            "Usuari: enviar email de reset de contrasenya",
        ),
        # Feedback
        ("feedback_resolt", "Feedback: marcat com a resolt"),
        # Community moderation — deletes by someone who isn't the author.
        # Author-deletes-own are routine and not logged.
        ("comentari_esborrar", "Comentari: esborrar (moderació)"),
        # Edits performed by a verified artist manager (UserArtista.verificat)
        # via the public /compte/artista/<pk>/editar endpoint. Distinct from
        # `artista_edit` so the audit page can filter staff vs. self-service.
        ("gestor_edita_artista", "Artista: edició per gestor"),
        # Manager-triggered request for staff to review the artist's
        # unverified songs. Sprint Portal Artista Ampliat (2026-05-20).
        ("gestor_ping_revisio", "Artista: ping de revisió de cançons (gestor)"),
        # Sprint Workflow Sol·licituds (2026-05-20).
        ("sollicitud_revisio_creada", "Sol·licitud de revisió: creada"),
        ("sollicitud_revisio_resolta", "Sol·licitud de revisió: resolta"),
        ("rebutjada_reconsiderada", "Historial: rebutjada reconsiderada"),
        # Sprint I — social distribution. `social_publicat` is the
        # legacy Instagram-only label; the multi-channel cron writes
        # one of `<channel>_publicat` per CHANNELS in publicar_canal.py.
        ("social_publicat", "Social: publicat (Instagram)"),
        ("mastodon_publicat", "Social: publicat (Mastodon)"),
        ("bluesky_publicat", "Social: publicat (Bluesky)"),
        ("telegram_publicat", "Social: publicat (Telegram)"),
        ("newsletter_publicat", "Social: publicat (Newsletter)"),
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
    # FASE C (2026-05-22): the no_verificades kind sources Canco rows
    # with verificada=False, sorted by ml_confianca desc, chunked into
    # windows of 100. `chunk_index` selects which window each playlist
    # gets so staff can triage the most recently ingested tracks across
    # the triage Spotify playlists. The window is capped at 6 chunks
    # (2026-06-06): the 7th chunk was always the 0%-coverage dead tail
    # and was repurposed (see KIND_NOVETATS_PER_VERIFICAR below).
    KIND_NO_VERIFICADES = "no_verificades"
    # 2026-06-06: a single PERMANENT work-list playlist (independent of
    # backlog size) holding the most recent unverified releases, ordered
    # by data_llancament desc. Repurposed in place from the old
    # no-verif-7 row so it keeps the same spotify_playlist_id / URL. Kept
    # OUT of the coverage health alert (it is a curated work list, not a
    # synced chart): see `music.health.check_spotify_coverage`.
    KIND_NOVETATS_PER_VERIFICAR = "novetats_per_verificar"
    KIND_CHOICES = [
        (KIND_TOP, "Top provisional"),
        (KIND_NOVETATS, "Novetats"),
        (KIND_NO_VERIFICADES, "No verificades (triage)"),
        (KIND_NOVETATS_PER_VERIFICAR, "Novetats per verificar"),
    ]

    # Cadence the sync cron applies. "daily" rows source from
    # TopProvisional (rolling); "weekly" rows source from TopSetmanal
    # (the published weekly ranking). The sync command picks the
    # appropriate ranking table based on this field.
    FREQ_DAILY = "daily"
    FREQ_WEEKLY = "weekly"
    FREQ_CHOICES = [
        (FREQ_DAILY, "Diari"),
        (FREQ_WEEKLY, "Setmanal"),
    ]

    codi = models.SlugField(max_length=50, unique=True)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    # Only used when kind=top. Empty string for kind=novetats / no_verificades.
    territori = models.CharField(max_length=10, blank=True)
    spotify_playlist_id = models.CharField(max_length=100, blank=True)
    # Cadence (FASE D, 2026-05-23). daily=TopProvisional, weekly=TopSetmanal.
    # Pre-existing rows default to daily; FASE D's data migration seeds the
    # 5 weekly rows (one per ranking territori) with this set to "weekly".
    freq = models.CharField(
        max_length=10,
        choices=FREQ_CHOICES,
        default=FREQ_DAILY,
        db_index=True,
        help_text="Cadence: daily reads TopProvisional, weekly reads TopSetmanal.",
    )
    # Only used when kind=no_verificades: 0-based index into the
    # window of 700 most-recently-ingested unverified tracks, so the
    # 7 triage playlists each get a non-overlapping slice of 100.
    # NULL for top / novetats rows (where it does not apply).
    chunk_index = models.IntegerField(
        null=True,
        blank=True,
        help_text="Window chunk for no_verificades playlists (0-based).",
    )

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


class SpotifyMetadata(models.Model):
    """Per-Canço Spotify enrichment row, populated by Process B.

    Architectural split (see docs/architecture/playlists.md "Spotify
    enrichment (Process B)" and ADR-0012):

      Process A — actualitzar_playlists_spotify, cache-only sync to
                  Spotify playlists. Reads `spotify_id` from this
                  table. NEVER calls /search.
      Process B — enriquir_spotify, one-shot per Canço. Hits
                  /v1/search (ISRC lookup), then /v1/tracks/{id} and
                  /v1/artists/{id}. Fills this row. Throttled.

    This table is the ONLY place we cache Spotify identifiers and the
    handful of metadata fields the post-2026 API still gives us.
    Spotify is identifier + disambiguation source, not metadata source
    (per ADR-0012). Rich metadata stays Deezer / Last.fm / MB.

    The `spotify_artist_id` (principal artist on the Spotify track) is
    the key to the dispersion signal: when several Cançons of the same
    `Artista` resolve to different `spotify_artist_id`, Deezer probably
    collapsed two distinct artists under one row and staff should split
    them. See `music.spotify_dispersio.recalcular_dispersio`.
    """

    STATUS_NOT_ATTEMPTED = "not_attempted"
    STATUS_FOUND = "found"
    STATUS_NOT_FOUND = "not_found"
    # Staff pasted a Spotify track URL by hand (store-and-trust: format
    # validated, no API call). Distinct from `found` so the id is never
    # re-resolved via /search; Process B still hydrates the row from the
    # known id (get_track + get_artist). See docs/architecture/playlists.md.
    STATUS_MANUAL = "manual"
    STATUS_CHOICES = [
        (STATUS_NOT_ATTEMPTED, "Encara no provada"),
        (STATUS_FOUND, "Trobada"),
        (STATUS_NOT_FOUND, "ISRC no a Spotify"),
        (STATUS_MANUAL, "Manual (staff)"),
    ]
    # Statuses that already carry a trusted Spotify id. Process A
    # (actualitzar_playlists_spotify) puts them in playlists; Process B's
    # /search queue (enriquir_spotify / enriquir_spotify_rebuigs) never
    # re-resolves them. `not_attempted` / `not_found` are the only
    # /search-enrichable states. (A `manual` row is still hydrated from
    # its id by enriquir_spotify phase 2 — fields filled, id untouched.)
    LOCKED_STATUSES = (STATUS_FOUND, STATUS_MANUAL)

    canco = models.OneToOneField(
        Canco,
        on_delete=models.CASCADE,
        related_name="spotify",
    )
    # Spotify track ID (22 chars). Indexed because Process A filters
    # by `enrichment_status="found"` AND non-empty spotify_id.
    spotify_id = models.CharField(max_length=64, blank=True, db_index=True)
    # Principal Spotify artist (artists[0].id from /v1/tracks). The
    # disambiguation anchor for dispersion calculation.
    spotify_artist_id = models.CharField(max_length=64, blank=True, db_index=True)
    # Every Spotify artist on the track (collaborators included).
    # JSONField list of ID strings, preserving order from Spotify.
    spotify_artist_ids = models.JSONField(default=list, blank=True)
    # Display name of the principal artist (canonical Spotify spelling
    # vs Deezer's). Surfaced in the staff triage workbench so reviewers
    # can spot a Deezer-vs-Spotify name divergence at a glance.
    spotify_artist_name = models.CharField(max_length=255, blank=True)
    # album.album_type: "single" / "album" / "ep".
    album_type = models.CharField(max_length=32, blank=True)
    # album.release_date as string (Spotify returns YYYY / YYYY-MM /
    # YYYY-MM-DD depending on `release_date_precision`).
    release_date = models.CharField(max_length=10, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    explicit = models.BooleanField(null=True)
    is_playable = models.BooleanField(null=True)
    # album.images: list of {url, width, height}. Spotify returns 3
    # sizes (640, 300, 64) for every album.
    images = models.JSONField(default=list, blank=True)
    # artist.genres: usually empty on Wave-One-restricted apps but kept
    # for completeness in case Spotify ever re-enables them.
    genres = models.JSONField(default=list, blank=True)

    enrichment_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NOT_ATTEMPTED,
        db_index=True,
    )
    enriched_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Spotify metadata"
        verbose_name_plural = "Spotify metadata"

    def __str__(self) -> str:
        return f"SpotifyMetadata({self.canco_id}, {self.enrichment_status})"
