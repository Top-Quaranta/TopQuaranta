"""Auth, profile, gestor↔artista, community, workflow sol·licituds.

# Spec: docs/architecture/comptes.md
"""

from django.contrib.auth.models import AbstractUser
from django.core.validators import URLValidator
from django.db import models

from music.constants import SOCIAL_LINK_FIELDS as _SOCIAL_LINK_FIELDS

# S8: accept only http(s) in user-submitted URL fields. Django's default
# URLValidator also allows ftp/ftps; restrict to web schemes explicitly
# so a typo or malicious entry can't land with e.g. ftp:// data.
HTTP_ONLY_URL = URLValidator(schemes=["http", "https"])


class Usuari(AbstractUser):
    """Custom user model for TopQuaranta.

    Extends AbstractUser without extra fields for now. This allows adding
    fields later (e.g. artist verification status) without changing
    AUTH_USER_MODEL again.
    """

    class Meta(AbstractUser.Meta):
        db_table = "auth_user"
        verbose_name = "Usuari"
        verbose_name_plural = "Usuaris"


class UserArtista(models.Model):
    """Request to manage an existing artist's profile.

    A user can have multiple management requests (ForeignKey, not OneToOne).
    Each request links to an existing approved artist.
    """

    ESTAT_PENDENT = "pendent"
    ESTAT_APROVAT = "aprovat"
    ESTAT_REBUTJAT = "rebutjat"
    ESTAT_CHOICES = [
        (ESTAT_PENDENT, "Pendent"),
        (ESTAT_APROVAT, "Aprovat"),
        (ESTAT_REBUTJAT, "Rebutjat"),
    ]

    usuari = models.ForeignKey(
        Usuari,
        on_delete=models.CASCADE,
        related_name="artistes_vinculats",
    )
    artista = models.ForeignKey(
        "music.Artista",
        on_delete=models.CASCADE,
    )
    verificat = models.BooleanField(default=False)
    estat = models.CharField(
        max_length=10,
        choices=ESTAT_CHOICES,
        default=ESTAT_PENDENT,
    )
    sollicitud_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Audit trail (Fase 1.5.A, 2026-05-17). Until now, approval date
    # and approver were only recoverable via StaffAuditLog. These
    # explicit fields make the model self-describing and remove the
    # dependency on an audit table for first-order queries.
    aprovat_at = models.DateTimeField(null=True, blank=True)
    aprovat_per = models.ForeignKey(
        Usuari,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    motiu_rebuig = models.TextField(blank=True)

    # Fase 1.5.C (2026-05-18). Stamp when the "you're verified" email
    # has been dispatched, so the retroactive notifier
    # (`notificar_gestors_retroactiu`) can pick up users approved
    # before the notification layer existed without double-sending to
    # anyone whose approval was processed under the new flow.
    email_aprovacio_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Vinculació usuari-artista"
        verbose_name_plural = "Vinculacions usuari-artista"
        indexes = [
            # Hot lookup: SPA `/compte` shows the user's managed
            # artists; backoffice queries `UserArtista.objects.filter(
            # usuari=u)` repeatedly. Without this index pg_stat showed
            # 2.363 seq_scan vs 4 idx_scan (May-2026 audit).
            models.Index(fields=["usuari", "-created_at"]),
        ]

    def __str__(self) -> str:
        status = "verificat" if self.verificat else self.estat
        return f"{self.usuari} → {self.artista.nom} ({status})"


class PropostaArtista(models.Model):
    """Proposal to add a new artist not yet in the system.

    Stores all relevant info the user provides. When staff approves,
    an Artista is created and optionally linked via UserArtista.
    """

    ESTAT_PENDENT = "pendent"
    ESTAT_APROVAT = "aprovat"
    ESTAT_REBUTJAT = "rebutjat"
    ESTAT_CHOICES = [
        (ESTAT_PENDENT, "Pendent"),
        (ESTAT_APROVAT, "Aprovat"),
        (ESTAT_REBUTJAT, "Rebutjat"),
    ]

    usuari = models.ForeignKey(
        Usuari,
        on_delete=models.CASCADE,
        related_name="propostes_artista",
    )
    # Artist info
    nom = models.CharField(max_length=255)
    justificacio = models.TextField()

    # Social links (all optional). S8: validators restricted to http/https.
    spotify_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    viasona_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    web_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    bandcamp_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    youtube_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    viquipedia_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    soundcloud_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    tiktok_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    facebook_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    instagram_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    twitter_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])

    # D3: list of Deezer IDs. Previously a comma-separated CharField; now a
    # JSONField so the ORM parses it for us. Default `list` so `.deezer_ids`
    # always iterates without a None-check.
    deezer_ids = models.JSONField(default=list, blank=True)

    # D4: list of location dicts: [{"municipi_id": 123} | {"manual": "..."}, …].
    # Previously a TextField with a JSON string we parsed by hand.
    localitzacions = models.JSONField(default=list, blank=True)

    # Status
    estat = models.CharField(
        max_length=10,
        choices=ESTAT_CHOICES,
        default=ESTAT_PENDENT,
    )
    # FK to the artist created from this proposal (set on approval)
    artista_creat = models.ForeignKey(
        "music.Artista",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propostes_origen",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Proposta d'artista"
        verbose_name_plural = "Propostes d'artista"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.usuari} proposa: {self.nom} ({self.estat})"

    def get_deezer_id_list(self) -> list[int]:
        """Return Deezer IDs as a list of ints.

        D3: now that `deezer_ids` is a JSONField, the list is already
        structured — but this shim stays so callers don't care about the
        storage shape, and to coerce strings that sneak in via the form
        to int before they hit the downstream ORM.
        """
        out: list[int] = []
        for raw in self.deezer_ids or []:
            try:
                out.append(int(raw))
            except (TypeError, ValueError):
                continue
        return out


class Feedback(models.Model):
    """User-submitted correction / error report for a public page.

    Any authenticated user can file one from a `/artista/`, `/album/`
    or `/canco/` page when they spot something wrong. Staff reviews
    them at /staff/feedback/ and either applies the fix via the normal
    edit flow and marks the entry resolved, or rejects it with a note.

    Anonymous visitors hitting the "Corregir" button are bounced to
    registration first — so `usuari` is non-null.
    """

    TARGET_ARTISTA = "artista"
    TARGET_ALBUM = "album"
    TARGET_CANCO = "canco"
    TARGET_ALTRES = "altres"
    TARGET_CHOICES = [
        (TARGET_ARTISTA, "Artista"),
        (TARGET_ALBUM, "Àlbum"),
        (TARGET_CANCO, "Cançó"),
        (TARGET_ALTRES, "Altres"),
    ]

    usuari = models.ForeignKey(
        Usuari,
        on_delete=models.CASCADE,
        related_name="feedbacks",
    )
    # Context of the page the user was on when they reported.
    url = models.CharField(max_length=500)
    target_type = models.CharField(
        max_length=10, choices=TARGET_CHOICES, default=TARGET_ALTRES
    )
    target_pk = models.BigIntegerField(null=True, blank=True)
    target_slug = models.CharField(max_length=550, blank=True)
    # Snapshot of the target's display name — so the staff list remains
    # meaningful even if the target is later renamed or deleted.
    target_label = models.CharField(max_length=500, blank=True)

    missatge = models.TextField()

    resolt = models.BooleanField(default=False)
    notes_staff = models.TextField(blank=True)
    resolt_at = models.DateTimeField(null=True, blank=True)
    resolt_per = models.ForeignKey(
        Usuari,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedbacks_resolts",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Feedback d'usuari"
        verbose_name_plural = "Feedback d'usuaris"
        indexes = [
            models.Index(fields=["resolt", "-created_at"]),
            models.Index(fields=["target_type", "target_pk"]),
        ]

    def __str__(self) -> str:
        return f"{self.usuari} · {self.target_type}:{self.target_label or self.target_slug}"


# ─────────────────────────────────────────────────────────────────────────
# Grup C — Plataforma de comunitat
# ─────────────────────────────────────────────────────────────────────────


class PerfilUsuari(models.Model):
    """Extended profile for each Usuari.

    Created automatically via post_save signal on Usuari creation (see
    `comptes/signals.py`) so every account always has a row — never
    null-guard downstream.

    `visible_directori` is the gate for /comunitat/directori listing;
    defaults to False, users opt in from onboarding or later from their
    account settings.
    """

    ROL_ESCOLTADOR = "escoltador"
    ROL_MUSIC = "music"
    ROL_PRODUCTOR = "productor"
    ROL_ALTRE = "altre"
    ROL_CHOICES = [
        (ROL_ESCOLTADOR, "Oïdor/a"),
        (ROL_MUSIC, "Músic/a"),
        (ROL_PRODUCTOR, "Productor/a"),
        (ROL_ALTRE, "Altre"),
    ]

    usuari = models.OneToOneField(
        Usuari, on_delete=models.CASCADE, related_name="perfil"
    )
    nom_public = models.CharField(max_length=120, blank=True)
    localitat = models.ForeignKey(
        "music.Municipi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="perfil_usuaris",
    )
    imatge_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    bio = models.TextField(blank=True, max_length=2000)

    # Socials — mirror of Artista.SOCIAL_LINK_FIELDS. Kept as flat fields
    # (not JSON) so filtering by "who has a bandcamp" is a simple query
    # and the admin/staff UIs can label them cleanly.
    spotify_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    viasona_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    web_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    bandcamp_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    youtube_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    viquipedia_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    soundcloud_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    tiktok_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    facebook_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    instagram_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])
    twitter_url = models.URLField(blank=True, validators=[HTTP_ONLY_URL])

    rol_musical = models.CharField(
        max_length=20, choices=ROL_CHOICES, default=ROL_ESCOLTADOR
    )
    instruments = models.CharField(max_length=255, blank=True)

    visible_directori = models.BooleanField(default=False, db_index=True)
    obert_colaboracions = models.BooleanField(default=False)

    # Notification preferences. Default ON — users explicitly opt out.
    notificar_missatges_email = models.BooleanField(default=True)
    notificar_comentaris_email = models.BooleanField(default=True)

    # Onboarding completion flag. Set when the user either fills the form
    # or explicitly dismisses it; used by the React AuthContext to know
    # whether to auto-route to /onboarding on first session.
    onboarding_complet = models.BooleanField(default=False)

    # ── Legal consent tracking (Sprint J) ──
    # Recorded on registration. We store the version of the legal docs
    # the user accepted so we can ask for a fresh acceptance when the
    # docs are updated in a way that materially changes them. Version
    # is the publication date of the docs, e.g. "2026-04-26".
    consent_termes_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user accepted the terms + privacy policy.",
    )
    consent_termes_versio = models.CharField(
        max_length=20,
        blank=True,
        help_text="Version (publication date) of the docs accepted.",
    )

    # Newsletter subscription (recorded separately from terms — RGPD
    # requires explicit, distinct consent for marketing emails).
    # Default False: opt-in only. The actual sending cron does not
    # exist yet (Sprint J just lays the groundwork).
    vol_newsletter = models.BooleanField(default=False, db_index=True)
    consent_newsletter_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Canonical iteration tuple from music.constants. Attribute name
    # kept for backward-compat with existing serializers and views
    # (PerfilUsuari.SOCIAL_FIELDS is referenced from several places).
    SOCIAL_FIELDS = _SOCIAL_LINK_FIELDS

    class Meta:
        verbose_name = "Perfil d'usuari"
        verbose_name_plural = "Perfils d'usuari"

    def __str__(self) -> str:
        return f"Perfil de {self.usuari}"


class Publicacio(models.Model):
    """User-authored content published at /comunitat.

    Staff writes directly in any visibility (estat=publicat).
    A regular user with visibilitat=interna posts directly (visible only
    to registered users). A regular user with visibilitat=publica goes
    through estat=pendent until staff approves. Rejection flags
    estat=rebutjat and staff may attach notes.
    """

    VISIBILITAT_INTERNA = "interna"
    VISIBILITAT_PUBLICA = "publica"
    VISIBILITAT_CHOICES = [
        (VISIBILITAT_INTERNA, "Interna (només usuaris registrats)"),
        (VISIBILITAT_PUBLICA, "Pública (tothom)"),
    ]

    ESTAT_ESBORRANY = "esborrany"
    ESTAT_PENDENT = "pendent"
    ESTAT_PUBLICAT = "publicat"
    ESTAT_REBUTJAT = "rebutjat"
    ESTAT_CHOICES = [
        (ESTAT_ESBORRANY, "Esborrany"),
        (ESTAT_PENDENT, "Pendent d'aprovació"),
        (ESTAT_PUBLICAT, "Publicada"),
        (ESTAT_REBUTJAT, "Rebutjada"),
    ]

    autor = models.ForeignKey(
        Usuari, on_delete=models.CASCADE, related_name="publicacions"
    )
    titol = models.CharField(max_length=200)
    # Body is stored as markdown (rendered client-side). Caps it at 20k
    # chars which is generous for a post but bounds worst-case payload.
    cos = models.TextField(max_length=20000)
    visibilitat = models.CharField(
        max_length=20,
        choices=VISIBILITAT_CHOICES,
        default=VISIBILITAT_INTERNA,
    )
    estat = models.CharField(
        max_length=20,
        choices=ESTAT_CHOICES,
        default=ESTAT_ESBORRANY,
        db_index=True,
    )

    # Staff note surfaced on rejection.
    notes_staff = models.TextField(blank=True)

    publicat_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Publicació"
        verbose_name_plural = "Publicacions"
        ordering = ["-publicat_at", "-created_at"]
        indexes = [
            models.Index(fields=["estat", "-created_at"]),
            models.Index(fields=["visibilitat", "estat", "-publicat_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.titol} — {self.autor}"


# ─────────────────────────────────────────────────────────────────────────
# Missatgeria interna
# ─────────────────────────────────────────────────────────────────────────


class Missatge(models.Model):
    """Direct message between two users.

    Simple inbox model — no threading, no attachments. Each message
    lives independently; "conversations" are reconstructed in the UI by
    pairing sender/receiver.
    """

    remitent = models.ForeignKey(
        Usuari, on_delete=models.SET_NULL, null=True, related_name="missatges_enviats"
    )
    destinatari = models.ForeignKey(
        Usuari, on_delete=models.CASCADE, related_name="missatges_rebuts"
    )
    assumpte = models.CharField(max_length=200, blank=True)
    cos = models.TextField(max_length=10000)

    llegit_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["destinatari", "-created_at"]),
            models.Index(fields=["remitent", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.remitent} → {self.destinatari}: {self.assumpte}"


# ─────────────────────────────────────────────────────────────────────────
# Comentaris a publicacions de la comunitat
# ─────────────────────────────────────────────────────────────────────────


class Comentari(models.Model):
    """Flat comment attached to a Publicacio.

    No nested threads — a single list per post ordered by creation.
    Moderation lives on the parent post (staff can delete individual
    comments via the detail page).
    """

    publicacio = models.ForeignKey(
        Publicacio, on_delete=models.CASCADE, related_name="comentaris"
    )
    autor = models.ForeignKey(
        Usuari, on_delete=models.SET_NULL, null=True, related_name="comentaris"
    )
    cos = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"comentari #{self.pk} de {self.autor} a {self.publicacio_id}"


# ─────────────────────────────────────────────────────────────────────────
# Sol·licituds de revisió (gestor → staff)
# ─────────────────────────────────────────────────────────────────────────


class SolicitudRevisio(models.Model):
    """Workflow row for a gestor's "please review these songs" request.

    Replaces the previous DM-based ping (a free-form `Missatge` to the
    Admin pseudouser) with a structured workflow that staff can triage
    at /staff/sollicituds-revisio/. Each row pairs:

      * The Cançons pending verification the gestor wants reviewed
        (snapshotted as `pendents_ids: list[int]` of `Canco.pk`). A
        Canco can be deleted between submission and resolution; the
        workbench queries by id and tolerates misses.
      * The HistorialRevisio rejections the gestor wants reconsidered
        (snapshotted as `rebutjades_snapshot: list[dict]` with the
        Deezer/ISRC/motiu denormalised so the staff sees the original
        context even if HistorialRevisio rows are merged or trimmed).

    Cooldown of 7 days lives on `Artista.ultim_ping_revisio_at` (one
    artist → one rolling window), independent from this row's state.

    Lifecycle:
      pendent   → staff hasn't started yet (default on create).
      revisada  → staff acknowledged + is working on it.
      resolta   → staff finished; the gestor receives a notification
                  email with the optional `nota_resolucio`.
    """

    ESTAT_PENDENT = "pendent"
    ESTAT_REVISADA = "revisada"
    ESTAT_RESOLTA = "resolta"
    ESTAT_CHOICES = [
        (ESTAT_PENDENT, "Pendent"),
        (ESTAT_REVISADA, "En revisió"),
        (ESTAT_RESOLTA, "Resolta"),
    ]

    gestor = models.ForeignKey(
        Usuari,
        on_delete=models.PROTECT,
        related_name="sollicituds_revisio",
        help_text="Gestor que va crear la sol·licitud.",
    )
    artista = models.ForeignKey(
        "music.Artista",
        on_delete=models.CASCADE,
        related_name="sollicituds_revisio",
    )
    pendents_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Llista de Canco.pk pendents de verificar incloses.",
    )
    rebutjades_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Llista de dicts amb el snapshot de cada rebutjada inclosa: "
            "{historial_pk, deezer_id, isrc, nom, album_nom, motiu}."
        ),
    )
    estat = models.CharField(
        max_length=20,
        choices=ESTAT_CHOICES,
        default=ESTAT_PENDENT,
        db_index=True,
    )
    nota_resolucio = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    resolt_at = models.DateTimeField(null=True, blank=True)
    resolt_per = models.ForeignKey(
        Usuari,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sollicituds_revisio_resoltes",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Sol·licitud de revisió"
        verbose_name_plural = "Sol·licituds de revisió"
        indexes = [
            # Workbench lists by `estat` filter + recency. Composite
            # serves both `estat=pendent` and the unfiltered `-created`
            # via leading-column lookup.
            models.Index(fields=["estat", "-created_at"]),
            models.Index(fields=["artista", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Sol·licitud #{self.pk} {self.artista.nom} ({self.estat})"

    @property
    def n_pendents(self) -> int:
        return len(self.pendents_ids or [])

    @property
    def n_rebutjades(self) -> int:
        return len(self.rebutjades_snapshot or [])


class NewsletterDraft(models.Model):
    """Opt-out review draft for the weekly subscriber newsletter.

    Generated on Saturday from the consolidated weekly top by the
    narrative engine (`generar_esborrany_newsletter`), reviewed by staff
    via an email link, and sent on Sunday (`enviar_newsletter`) unless
    cancelled. There is deliberately NO "approved" state: `pendent` means
    "will be sent" — review is opt-out, not opt-in.

    Only `subject` + `narrative_html` are stored. The rest of the email
    context (podi, entries, covers) is rebuilt from the FINAL top at send
    time, so a draft generated Saturday reflects any ranking change up to
    Sunday. `font` records who produced the text (the engine today; an
    LLM in a later phase).
    """

    ESTAT_PENDENT = "pendent"
    ESTAT_ENVIAT = "enviat"
    ESTAT_CANCELLAT = "cancellat"
    ESTAT_CHOICES = [
        (ESTAT_PENDENT, "Pendent (s'enviarà)"),
        (ESTAT_ENVIAT, "Enviat"),
        (ESTAT_CANCELLAT, "Cancel·lat"),
    ]

    FONT_MOTOR = "motor"
    FONT_LLM = "llm"
    FONT_CHOICES = [
        (FONT_MOTOR, "Motor narratiu"),
        (FONT_LLM, "LLM"),
    ]

    tipus = models.CharField(max_length=30)
    territori = models.CharField(max_length=4, blank=True, default="")
    setmana = models.DateField(
        db_index=True, help_text="Dilluns de la setmana ISO del top."
    )
    subject = models.CharField(max_length=300)
    narrative_html = models.TextField(blank=True, default="")
    estat = models.CharField(
        max_length=20,
        choices=ESTAT_CHOICES,
        default=ESTAT_PENDENT,
        db_index=True,
    )
    font = models.CharField(max_length=10, choices=FONT_CHOICES, default=FONT_MOTOR)
    editat = models.BooleanField(
        default=False, help_text="True si l'staff ha editat subject o narrative_html."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    enviat_at = models.DateTimeField(null=True, blank=True)

    # ── Newsletter → Publicació bridge (additive, gated) ────────────
    # When staff publishes a draft as a public community post, this links
    # the draft to the created `Publicacio` so the action is idempotent
    # (a draft maps to at most one community post). Nullable: the vast
    # majority of drafts are never mirrored to the feed. Gated by
    # `ConfiguracioGlobal.newsletter_publicacio_pont_actiu`. SET_NULL so
    # deleting a Publicació never cascades to (or deletes) the draft.
    publicacio = models.OneToOneField(
        "comptes.Publicacio",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="newsletter_origen",
        help_text="Publicació pública creada a partir d'aquest esborrany "
        "(pont Newsletter→Comunitat). Null si mai s'ha publicat al feed.",
    )

    class Meta:
        ordering = ["-setmana"]
        verbose_name = "Esborrany de newsletter"
        verbose_name_plural = "Esborranys de newsletter"
        constraints = [
            models.UniqueConstraint(
                fields=["tipus", "territori", "setmana"],
                name="newsletterdraft_unique_slot",
            )
        ]

    def __str__(self) -> str:
        return f"NewsletterDraft {self.tipus}/{self.territori} {self.setmana} ({self.estat})"
