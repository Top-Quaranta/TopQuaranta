"""Social distribution models (Sprint I).

`SocialPost` is the audit + idempotency anchor for every published
piece of content. One row per (platform, tipus, territori, setmana).

`InstagramAuth` is the singleton holding the long-lived access token
+ user ID + expiry. Same pattern as `music.SpotifyAuth`. Lets us
rotate the token from the staff panel without SSH'ing into the box
to edit `.env`. The settings `INSTAGRAM_ACCESS_TOKEN` etc. remain
as a fallback when the DB row is empty (handy for first-boot, tests
and the autoritzar_instagram command's output).
"""

from django.db import models


class SocialPost(models.Model):
    PLATFORM_INSTAGRAM_FEED = "instagram_feed"
    PLATFORM_INSTAGRAM_STORY = "instagram_story"
    PLATFORM_CHOICES = [
        (PLATFORM_INSTAGRAM_FEED, "Instagram · Feed"),
        (PLATFORM_INSTAGRAM_STORY, "Instagram · Stories"),
    ]

    # Content type. Each renderer + caption template lives keyed by
    # this string. Add new types as the calendari grows.
    TIPUS_TOP_PPCC = "top_ppcc"
    TIPUS_TOP_TERRITORIAL = "top_territorial"
    TIPUS_NOUS_ALBUMS = "nous_albums"
    TIPUS_NOUS_SINGLES = "nous_singles"
    TIPUS_CHOICES = [
        (TIPUS_TOP_PPCC, "Top global"),
        (TIPUS_TOP_TERRITORIAL, "Top territorial"),
        (TIPUS_NOUS_ALBUMS, "Nous àlbums"),
        (TIPUS_NOUS_SINGLES, "Nous singles"),
    ]

    STATUS_PENDENT = "pendent"
    STATUS_PUBLICAT = "publicat"
    STATUS_ERROR = "error"
    STATUS_OMES = "omes"
    STATUS_CHOICES = [
        (STATUS_PENDENT, "Pendent"),
        (STATUS_PUBLICAT, "Publicat"),
        (STATUS_ERROR, "Error"),
        (STATUS_OMES, "Omès"),  # fase no l'inclou OR no hi ha contingut
    ]

    platform = models.CharField(max_length=30, choices=PLATFORM_CHOICES, db_index=True)
    tipus = models.CharField(max_length=30, choices=TIPUS_CHOICES, db_index=True)
    # Empty for non-territorial types (top_ppcc, nous_*).
    territori = models.CharField(max_length=4, blank=True, default="")
    setmana = models.DateField(db_index=True, help_text="Monday of the ISO week.")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDENT,
        db_index=True,
    )
    # Container/media IDs returned by the Graph API. JSON to keep
    # carousel item IDs alongside the final published media ID.
    instagram_media_id = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(blank=True, null=True)

    error_msg = models.TextField(blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Publicació social"
        verbose_name_plural = "Publicacions socials"
        unique_together = [("platform", "tipus", "territori", "setmana")]
        ordering = ["-setmana", "platform", "tipus"]

    def __str__(self) -> str:
        ter = f" · {self.territori}" if self.territori else ""
        return f"{self.platform} · {self.tipus}{ter} · {self.setmana} ({self.status})"


class InstagramAuth(models.Model):
    """Singleton holding the live Instagram credentials.

    Populated either by `autoritzar_instagram` (interactive OAuth)
    or by the staff panel form. The IG client checks this row first;
    if empty, falls back to the `INSTAGRAM_*` settings — that
    fallback path keeps the local dev workflow working without a DB
    write.

    `expires_at` is informational (we use it for the days-until
    expiry alarm). Refresh of the long-lived token resets it +60d.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    access_token = models.TextField(blank=True, default="")
    instagram_user_id = models.CharField(max_length=40, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "comptes.Usuari",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "Autorització Instagram"
        verbose_name_plural = "Autoritzacions Instagram"

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "InstagramAuth | None":
        return cls.objects.filter(pk=1).first()

    def __str__(self) -> str:
        if not self.access_token:
            return "Instagram auth (buit)"
        masked = self.access_token[:4] + "…" + self.access_token[-4:]
        return f"Instagram auth ({masked})"
