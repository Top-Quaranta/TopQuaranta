"""Token-authed endpoints for the SEO landing cloud routine (Fase 2, B).

Mirror of `web/api/newsletter_routine.py`: a cloud routine READS a brief
(which landings still lack prose + the editorial voice + grounding
context) and WRITES plain-text prose back. Never generates server-side,
never calls a paid API in-process. Reuses the same bearer-token gate
(`require_routine_token`) as the newsletter routine.

  GET  /api/v1/landing-routine/brief/   → pending landings + editorial_veu
  POST /api/v1/landing-routine/prosa/   → upsert one landing's prose

# Spec: docs/architecture/web.md
"""

from __future__ import annotations

from django.db.models import Count, Q
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from music.models import Artista, Canco
from ranking.models import ConfiguracioGlobal
from web.models import LandingProsa
from web.seo import meta

from .newsletter_routine import require_routine_token

# Sample size of entity names handed to the routine per landing, as
# grounding for the prose. Bounded so the brief stays small.
_SAMPLE = 10


def _territori_landings() -> list[dict]:
    out = []
    existing = dict(
        LandingProsa.objects.filter(kind=LandingProsa.KIND_TERRITORI).values_list(
            "clau", "prosa"
        )
    )
    for codi, nom in meta.TERRITORI_NOMS.items():
        if codi == "ALT":
            continue
        artistes = list(
            Artista.objects.public()
            .filter(localitats__municipi__territori_id=codi)
            .annotate(
                n=Count(
                    "cancons",
                    filter=Q(cancons__verificada=True, cancons__activa=True),
                    distinct=True,
                )
            )
            .filter(n__gt=0)
            .distinct()
            .order_by("-n", "nom")
            .values_list("nom", flat=True)[:_SAMPLE]
        )
        if not artistes:
            continue
        out.append(
            {
                "kind": LandingProsa.KIND_TERRITORI,
                "clau": codi,
                "nom": nom,
                "te_prosa": bool(existing.get(codi)),
                "items": list(artistes),
            }
        )
    return out


def _genere_landings() -> list[dict]:
    out = []
    existing = dict(
        LandingProsa.objects.filter(kind=LandingProsa.KIND_GENERE).values_list(
            "clau", "prosa"
        )
    )
    for slug, label in Artista.GENERE_CANONICAL_CHOICES:
        artistes = list(
            Artista.objects.public()
            .filter(genere_canonical=slug)
            .annotate(
                n=Count(
                    "cancons",
                    filter=Q(cancons__verificada=True, cancons__activa=True),
                    distinct=True,
                )
            )
            .order_by("-n", "nom")
            .values_list("nom", flat=True)[:_SAMPLE]
        )
        # Mirror the genere_seo 404 gate: < 3 artistes → no page.
        if len(artistes) < 3:
            continue
        out.append(
            {
                "kind": LandingProsa.KIND_GENERE,
                "clau": slug,
                "nom": label,
                "te_prosa": bool(existing.get(slug)),
                "items": list(artistes),
            }
        )
    return out


def _decada_landings() -> list[dict]:
    out = []
    existing = dict(
        LandingProsa.objects.filter(kind=LandingProsa.KIND_DECADA).values_list(
            "clau", "prosa"
        )
    )
    years = Canco.objects.filter(
        verificada=True, activa=True, data_llancament__isnull=False
    ).dates("data_llancament", "year")
    decades = sorted({(d.year // 10) * 10 for d in years})
    for dec in decades:
        cancons = list(
            Canco.objects.filter(
                verificada=True,
                activa=True,
                data_llancament__year__gte=dec,
                data_llancament__year__lte=dec + 9,
            )
            .order_by("-data_llancament")
            .values_list("nom", flat=True)[:_SAMPLE]
        )
        # Mirror the decada_seo 404 gate: < 5 cançons → no page.
        if len(cancons) < 5:
            continue
        clau = str(dec)
        out.append(
            {
                "kind": LandingProsa.KIND_DECADA,
                "clau": clau,
                "nom": f"dècada {clau}",
                "te_prosa": bool(existing.get(clau)),
                "items": list(cancons),
            }
        )
    return out


def _clau_valida(kind: str, clau: str) -> bool:
    """True iff (kind, clau) names a landing that would actually resolve,
    so the routine can't store prose for a non-existent / 404 page."""
    if kind == LandingProsa.KIND_TERRITORI:
        return clau in meta.TERRITORI_NOMS and clau != "ALT"
    if kind == LandingProsa.KIND_GENERE:
        return clau in {k for k, _ in Artista.GENERE_CANONICAL_CHOICES}
    if kind == LandingProsa.KIND_DECADA:
        return clau.isdigit() and len(clau) == 4 and clau.endswith("0")
    if kind in (LandingProsa.KIND_TOP, LandingProsa.KIND_MAPA):
        # Singleton landings: the canonical /top and /mapa pages. One
        # row each, keyed by the empty clau.
        return clau == ""
    return False


def _singleton_landings() -> list[dict]:
    """The /top and /mapa landings (one each). Grounding: the current
    PPCC top song names for /top, the territori names for /mapa."""
    from music.constants import TERRITORIS_VALIDS

    TopProvisional = __import__(
        "ranking.models", fromlist=["TopProvisional"]
    ).TopProvisional
    existing = dict(
        LandingProsa.objects.filter(
            kind__in=[LandingProsa.KIND_TOP, LandingProsa.KIND_MAPA]
        ).values_list("kind", "prosa")
    )
    top_items = list(
        TopProvisional.objects.filter(territori="PPCC")
        .select_related("canco")
        .order_by("posicio")
        .values_list("canco__nom", flat=True)[:_SAMPLE]
    )
    mapa_items = [meta.TERRITORI_NOMS.get(c, c) for c in TERRITORIS_VALIDS]
    return [
        {
            "kind": LandingProsa.KIND_TOP,
            "clau": "",
            "nom": "Top setmanal (Global)",
            "te_prosa": bool(existing.get(LandingProsa.KIND_TOP)),
            "items": [t for t in top_items if t],
        },
        {
            "kind": LandingProsa.KIND_MAPA,
            "clau": "",
            "nom": "Mapa de la música en català",
            "te_prosa": bool(existing.get(LandingProsa.KIND_MAPA)),
            "items": mapa_items,
        },
    ]


@api_view(["GET"])
@require_routine_token
def brief(request: Request) -> Response:
    """Pending landings + editorial voice. `landings` carries every
    resolvable landing with a `te_prosa` flag so the routine can fill
    only the gaps, plus a small sample of entity names for grounding."""
    cfg = ConfiguracioGlobal.load()
    landings = (
        _territori_landings()
        + _genere_landings()
        + _decada_landings()
        + _singleton_landings()
    )
    # Dedicated landing voice (NOT the newsletter's editorial_veu) so the
    # two tones never collide. Empty => the routine generates nothing
    # (clean STOP until staff sets it in Configuració).
    return Response(
        {
            "editorial_veu": cfg.landing_editorial_veu or "",
            "landings": landings,
        }
    )


@api_view(["POST"])
@require_routine_token
def prosa(request: Request) -> Response:
    """Upsert plain-text prose for one landing. Stored as text (rendered
    with `linebreaks`, never `safe`). Rejects unknown kinds and clau
    values that don't resolve to a real landing."""
    kind = (request.data.get("kind") or "").strip()
    clau = (request.data.get("clau") or "").strip()
    text = (request.data.get("prosa") or "").strip()
    if kind not in {
        LandingProsa.KIND_TERRITORI,
        LandingProsa.KIND_GENERE,
        LandingProsa.KIND_DECADA,
    }:
        return Response({"error": "kind invàlid"}, status=400)
    if not _clau_valida(kind, clau):
        return Response({"error": "clau no resol a cap landing real"}, status=400)
    obj, created = LandingProsa.objects.update_or_create(
        kind=kind,
        clau=clau,
        defaults={"prosa": text, "font": LandingProsa.FONT_LLM},
    )
    return Response(
        {"status": "ok", "created": created, "kind": kind, "clau": clau},
        status=201 if created else 200,
    )
