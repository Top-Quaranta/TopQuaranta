"""SEO landing editorial prose.

Filled asynchronously by the landing cloud routine (see
`web/api/landing_routine.py`) — never generated server-side, no paid API
calls in-process. Empty by default, so an editorial landing degrades to
its existing structured content (top, artist/song lists) without ever
breaking the thin/noindex gate.

# Spec: docs/architecture/web.md
"""

from __future__ import annotations

from django.db import models


class LandingProsa(models.Model):
    """Editorial prose for one SEO landing, keyed by (kind, clau).

    `kind` is the landing family (`territori` / `genere` / `decada`) and
    `clau` its identifier (territori codi, genere slug, decade string).
    `prosa` is plain text (rendered with `linebreaks`, never `safe`), so
    a compromised routine token can't inject markup. Additive table; no
    backfill — rows appear only when the routine writes them.
    """

    KIND_TERRITORI = "territori"
    KIND_GENERE = "genere"
    KIND_DECADA = "decada"
    KIND_TOP = "top"
    KIND_MAPA = "mapa"
    KIND_CHOICES = [
        (KIND_TERRITORI, "Territori"),
        (KIND_GENERE, "Gènere"),
        (KIND_DECADA, "Dècada"),
        (KIND_TOP, "Top"),
        (KIND_MAPA, "Mapa"),
    ]

    FONT_LLM = "llm"
    FONT_MANUAL = "manual"

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, db_index=True)
    clau = models.CharField(max_length=80)
    prosa = models.TextField(blank=True, default="")
    font = models.CharField(max_length=20, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "clau"], name="uniq_landingprosa_kind_clau"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.clau}"

    @classmethod
    def text_for(cls, kind: str, clau: str) -> str:
        """Return the stored prose for a landing, or empty string. One
        cheap indexed lookup; safe to call from a render path."""
        return (
            cls.objects.filter(kind=kind, clau=clau)
            .values_list("prosa", flat=True)
            .first()
            or ""
        )
