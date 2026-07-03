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
    PLATFORM_MASTODON = "mastodon"
    PLATFORM_BLUESKY = "bluesky"
    PLATFORM_TELEGRAM = "telegram"
    PLATFORM_NEWSLETTER = "newsletter"
    PLATFORM_CHOICES = [
        (PLATFORM_INSTAGRAM_FEED, "Instagram · Feed"),
        (PLATFORM_INSTAGRAM_STORY, "Instagram · Stories"),
        (PLATFORM_MASTODON, "Mastodon"),
        (PLATFORM_BLUESKY, "Bluesky"),
        (PLATFORM_TELEGRAM, "Telegram"),
        (PLATFORM_NEWSLETTER, "Newsletter"),
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

    # `db_index=False` (May-2026 audit): both fields are always
    # combined with `setmana` via `unique_together` (which already
    # creates a composite index). The standalone indexes had 0
    # idx_scan in pg_stat. Drops 4 indexes (Django adds the `_like`
    # variant for varchar) and saves write overhead.
    platform = models.CharField(max_length=30, choices=PLATFORM_CHOICES)
    tipus = models.CharField(max_length=30, choices=TIPUS_CHOICES)
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


class NarrativePhraseUsage(models.Model):
    """Anti-repetition ledger for the narrative engine (Fase 4 PR 1).

    Each row records that a given templated phrase was used on a
    given (channel, territori, setmana). The composer queries this
    table to filter out phrases used in the last N weeks for the
    same channel + territori, so the same opener doesn't appear two
    Saturdays in a row on Mastodon CAT, for example.

    `phrase_id` is the deterministic key built by `phrases.phrase_id()`
    from (scenario_code, index, length) — short string, no FK.
    Keeping it as a plain CharField (rather than a FK to a Phrase
    table) lets us edit the phrase bank freely without DB migrations.
    """

    phrase_id = models.CharField(max_length=80, db_index=True)
    territori = models.CharField(max_length=4)
    setmana = models.DateField()
    channel = models.CharField(max_length=20)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ús de frase narrativa"
        verbose_name_plural = "Usos de frases narratives"
        indexes = [
            models.Index(fields=["channel", "territori", "-setmana"]),
        ]
        ordering = ["-used_at"]

    def __str__(self) -> str:
        return f"{self.phrase_id} · {self.channel} · {self.territori} · {self.setmana}"


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


class MastodonAuth(models.Model):
    """Singleton for Mastodon credentials.

    `instance_url` is the base URL of the home instance (e.g.
    `https://mastodont.cat`). `access_token` is a permanent app
    token created from the instance's settings → developer page
    (no OAuth dance needed for a single-account bot).
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    instance_url = models.CharField(max_length=200, blank=True, default="")
    access_token = models.TextField(blank=True, default="")
    handle = models.CharField(max_length=80, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "comptes.Usuari",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "Autorització Mastodon"
        verbose_name_plural = "Autoritzacions Mastodon"

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "MastodonAuth | None":
        return cls.objects.filter(pk=1).first()


class BlueskyAuth(models.Model):
    """Singleton for Bluesky credentials.

    Bluesky uses an `app_password` (different from the account
    password) created at https://bsky.app/settings/app-passwords.
    `handle` is the user's @handle (e.g. `topquaranta.bsky.social`).
    The session JWT is fetched on demand and cached briefly in
    process memory; we never store it long-term.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    handle = models.CharField(max_length=120, blank=True, default="")
    app_password = models.CharField(max_length=120, blank=True, default="")
    did = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Decentralised identifier (resolved on first auth).",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "comptes.Usuari",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "Autorització Bluesky"
        verbose_name_plural = "Autoritzacions Bluesky"

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "BlueskyAuth | None":
        return cls.objects.filter(pk=1).first()


class TelegramAuth(models.Model):
    """Singleton for Telegram bot credentials.

    `bot_token` is created via @BotFather (`/newbot`). `chat_id` is
    the destination — typically a public channel like
    `@topquaranta_canal` (string, leading @) or a numeric supergroup
    ID. The bot must be added as an admin of the channel with
    "Post messages" permission.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    bot_token = models.CharField(max_length=200, blank=True, default="")
    chat_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Channel handle (e.g. @topquaranta) or numeric ID.",
    )
    bot_username = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Auto-resolved label (e.g. 'topquaranta_bot').",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "comptes.Usuari",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "Autorització Telegram"
        verbose_name_plural = "Autoritzacions Telegram"

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "TelegramAuth | None":
        return cls.objects.filter(pk=1).first()


class InvitacioColaboracioIG(models.Model):
    """One Instagram collaborator invite we sent for a feed post.

    Spec: docs/decisions/0015-ig-collaborator-invitations.md §5.1.

    Records every invite + its async resolution (pending →
    accepted/rejected). Keyed by `(artista, ig_media_id)`: one invite per
    artist per post. The acceptance poller (`pollar_colaboracions_ig`)
    stamps `data_resolucio` when the state leaves `pendent`. This model
    is INERT in tranche 1 — nothing writes to it until the master flag
    `ConfiguracioGlobal.ig_collaboradors_actiu` is switched on and the
    policy is wired into `publicar_social` (tranche 3).
    """

    ESTAT_PENDENT = "pendent"
    ESTAT_ACCEPTADA = "acceptada"
    ESTAT_REBUTJADA = "rebutjada"
    # `caducada`: still pending after the 14-day poll window — IG invite
    # acceptance is effectively immediate-or-never, so an un-resolved
    # invite is treated as a soft decline (the poller stamps it; the
    # policy treats it like a rejection: category C, 90-day cooldown).
    # Closes the "eternal pendent" hole where such rows blocked the
    # artist's re-invitation forever.
    ESTAT_CADUCADA = "caducada"
    ESTAT_CHOICES = [
        (ESTAT_PENDENT, "Pendent"),
        (ESTAT_ACCEPTADA, "Acceptada"),
        (ESTAT_REBUTJADA, "Rebutjada"),
        (ESTAT_CADUCADA, "Caducada"),
    ]
    # Set form for membership checks (mirrors the ADR's `ESTATS`).
    ESTATS = {ESTAT_PENDENT, ESTAT_ACCEPTADA, ESTAT_REBUTJADA, ESTAT_CADUCADA}

    artista = models.ForeignKey(
        "music.Artista",
        on_delete=models.PROTECT,
        related_name="invitacions_ig",
        help_text="Artist we invited as a collaborator.",
    )
    # The bare handle at invite time. Accounts get renamed; the snapshot
    # is what we actually sent, independent of the artist's current
    # instagram_url.
    username_snapshot = models.CharField(max_length=64)
    ig_media_id = models.CharField(max_length=40, db_index=True)
    tipus_publicacio = models.CharField(max_length=30, choices=SocialPost.TIPUS_CHOICES)
    data_invitacio = models.DateTimeField(db_index=True)
    estat = models.CharField(
        max_length=12, choices=ESTAT_CHOICES, default=ESTAT_PENDENT
    )
    data_resolucio = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Invitació de col·laboració IG"
        verbose_name_plural = "Invitacions de col·laboració IG"
        constraints = [
            models.UniqueConstraint(
                fields=["artista", "ig_media_id"],
                name="invitaciocolaboracioig_uniq_artista_media",
            ),
        ]
        indexes = [
            # Poller scan window: pending invites of the last N days.
            models.Index(fields=["estat", "data_invitacio"]),
            # Category A/C lookup: an artist's invite history by state.
            models.Index(fields=["artista", "estat"]),
        ]

    def __str__(self) -> str:
        return f"{self.username_snapshot}@{self.ig_media_id} · {self.estat}"
