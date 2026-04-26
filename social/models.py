"""Social distribution models (Sprint I).

`SocialPost` is the audit + idempotency anchor for every published
piece of content. One row per (platform, tipus, territori, setmana).
The same row tracks `pendent` → `publicat`/`omès`/`error` so the
publication command is naturally re-runnable: a row already in the
`publicat` state short-circuits unless `--force` is passed.
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
