"""Build per-page metadata dicts (title, description, canonical, OG,
Twitter card, hreflang). Single source of truth for both the Django
SSR templates AND the SPA's react-helmet-async hooks.

The SPA fetches `/api/v1/seo/<entity>/<slug>/` to read this exact
payload at runtime, guaranteeing the `<head>` is identical whether
served pre-rendered (bot path) or SPA-injected (human path).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from django.conf import settings
from django.utils.html import strip_tags

from music.models import Album, Artista, Canco

CANONICAL_HOST = settings.SITE_URL  # → "https://www.topquaranta.cat"
SITE_NAME = "TopQuaranta"
DEFAULT_OG_IMAGE = f"{CANONICAL_HOST}/og/default.png"
LOCALE = "ca_ES"

TERRITORI_NOMS = {
    "PPCC": "Global",
    "CAT": "Catalunya",
    "VAL": "País Valencià",
    "BAL": "Illes Balears",
    "AND": "Andorra",
    "CNO": "Catalunya del Nord",
    "FRA": "Franja de Ponent",
    "ALG": "L'Alguer",
    "ALT": "Altres",
}


@dataclass
class Meta:
    """Lowest-common-denominator metadata for any SEO surface.

    Renders identically as Django template context, JSON for the
    SPA endpoint, and a Helmet hook on the React side.
    """

    title: str
    description: str
    canonical_url: str
    og_image: str  # absolute URL
    og_type: str = "website"  # website | article | music.album | …
    twitter_card: str = "summary_large_image"
    keywords: list[str] | None = None
    locale: str = LOCALE
    site_name: str = SITE_NAME

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


def _trim(text: str, n: int = 160) -> str:
    """Truncate to N chars on a word boundary, no trailing ellipsis."""
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "…"


# ── Per-entity builders ─────────────────────────────────────────────


def for_homepage() -> Meta:
    return Meta(
        title="TopQuaranta — Rànquing setmanal de música en català",
        description=_trim(
            "El rànquing setmanal de música en català als Països Catalans. "
            "Mesurem què sona a Last.fm cada setmana per demostrar que la "
            "nostra música no para de créixer."
        ),
        canonical_url=f"{CANONICAL_HOST}/",
        og_image=f"{CANONICAL_HOST}/og/home.png",
        og_type="website",
        keywords=["música en català", "rànquing", "Països Catalans", "top"],
    )


def for_top(territori: str | None = None) -> Meta:
    territori = (territori or "PPCC").upper()
    nom = TERRITORI_NOMS.get(territori, territori)
    return Meta(
        title=f"Top {nom} — Música en català · TopQuaranta",
        description=_trim(
            f"Les 40 cançons en català més escoltades de {nom} aquesta setmana, "
            "actualitzat cada dissabte. Top setmanal mesurat amb dades reals "
            "de Last.fm i Deezer."
        ),
        canonical_url=f"{CANONICAL_HOST}/top",
        og_image=f"{CANONICAL_HOST}/og/top/{territori}.png",
        og_type="website",
        keywords=[
            "top música català",
            f"música {nom}",
            "rànquing musical",
            "música en català 2026",
        ],
    )


def for_artistes_list() -> Meta:
    return Meta(
        title="Artistes en català — Directori · TopQuaranta",
        description=_trim(
            "Directori complet d'artistes que fan música en català. "
            "Cerca per territori, comarca o nom. Inclou totes les bandes "
            "i cantants verificats al sistema."
        ),
        canonical_url=f"{CANONICAL_HOST}/artistes",
        og_image=DEFAULT_OG_IMAGE,
        og_type="website",
        keywords=["artistes en català", "bandes catalanes", "directori música"],
    )


def for_artista(a: Artista) -> Meta:
    territori_nom = ""
    loc_qs = a.localitats.select_related("municipi__territori").all()
    if loc_qs:
        codes = {ll.municipi.territori_id for ll in loc_qs if ll.municipi}
        nicies = [TERRITORI_NOMS.get(c, c) for c in codes]
        if nicies:
            territori_nom = " · " + ", ".join(sorted(set(nicies)))

    n_cancons = a.cancons.filter(verificada=True, activa=True).count()

    # Bio fallback chain. As of 2026-05 every approved Artista row has
    # `bio=""` (no editorial bios written yet), but 1948/1989 of them
    # carry a non-empty `lastfm_bio_summary` from the Last.fm ingest.
    # Use that as the description when our own bio is empty, so 98% of
    # /artista/ SEO pages stop emitting the templated generic line that
    # GSC was likely flagging as thin/duplicate content. strip_tags
    # because Last.fm bios occasionally include <a> tags and we don't
    # want raw HTML in <meta description>.
    fallback_bio = strip_tags(a.lastfm_bio_summary or "").strip()
    desc = (
        a.bio
        or fallback_bio
        or f"{a.nom} és un artista de música en català{territori_nom}. "
        + (f"Té {n_cancons} cançons verificades a TopQuaranta. " if n_cancons else "")
        + "Coneix-li la discografia, el top setmanal i els enllaços per escoltar-lo."
    )
    # Pick the OG image. Priority:
    # 1) Dynamic card (always — generated on-the-fly from latest data).
    og_image = f"{CANONICAL_HOST}/og/artista/{a.slug}.png"

    return Meta(
        title=f"{a.nom} — Música en català · TopQuaranta",
        description=_trim(desc),
        canonical_url=f"{CANONICAL_HOST}/artista/{a.slug}",
        og_image=og_image,
        og_type="profile",
        keywords=[
            a.nom,
            f"{a.nom} cançons",
            f"{a.nom} música",
            "música en català",
        ],
    )


def for_album(al: Album) -> Meta:
    artist_nom = al.artista.nom if al.artista_id else ""
    desc = (
        f"{al.nom}, àlbum de {artist_nom}"
        + (f" publicat el {al.data_llancament.year}" if al.data_llancament else "")
        + ". Tracklist complet, info de cada cançó i enllaços per escoltar-lo a "
        "Spotify, Deezer, YouTube Music i Apple Music."
    )
    og_image = al.imatge_url or f"{CANONICAL_HOST}/og/album/{al.slug}.png"
    return Meta(
        title=f"{al.nom} — {artist_nom} · TopQuaranta",
        description=_trim(desc),
        canonical_url=f"{CANONICAL_HOST}/album/{al.slug}",
        og_image=og_image,
        og_type="music.album",
        keywords=[al.nom, artist_nom, "àlbum en català"],
    )


def for_canco(c: Canco) -> Meta:
    artist_nom = c.artista.nom if c.artista_id else ""
    album_nom = c.album.nom if c.album_id else ""
    desc = (
        f"«{c.nom}» de {artist_nom}, "
        + (f"de l'àlbum «{album_nom}». " if album_nom else "")
        + "Posicionament al top setmanal de TopQuaranta i enllaços per "
        "escoltar-la a Spotify, Deezer, YouTube Music i Apple Music."
    )
    # Album cover is a far better card image than a generic page card,
    # because it's what social previews already expect for a song.
    og_image = (
        c.album.imatge_url if c.album_id else None
    ) or f"{CANONICAL_HOST}/og/canco/{c.slug}.png"
    return Meta(
        title=f"{c.nom} — {artist_nom} · TopQuaranta",
        description=_trim(desc),
        canonical_url=f"{CANONICAL_HOST}/canco/{c.slug}",
        og_image=og_image,
        og_type="music.song",
        keywords=[c.nom, artist_nom, "cançó en català"],
    )


def for_com_funciona() -> Meta:
    return Meta(
        title="Com funciona TopQuaranta · El rànquing de música en català",
        description=_trim(
            "Com mesurem el top setmanal de música en català: dades reals "
            "d'escoltes a Last.fm, fórmula pública i revisió humana. Reproduïble."
        ),
        canonical_url=f"{CANONICAL_HOST}/com-funciona",
        og_image=f"{CANONICAL_HOST}/og/home.png",
        og_type="article",
        keywords=[
            "com funciona topquaranta",
            "rànquing música català",
            "metodologia",
            "música en català",
        ],
    )


def for_mapa() -> Meta:
    return Meta(
        title="Mapa de la música en català · TopQuaranta",
        description=_trim(
            "Explora el mapa interactiu de la música en català: "
            "territoris, comarques i municipis amb els artistes que "
            "hi viuen i fan música en la nostra llengua."
        ),
        canonical_url=f"{CANONICAL_HOST}/mapa",
        og_image=f"{CANONICAL_HOST}/og/mapa.png",
        og_type="website",
        keywords=["mapa música català", "geografia música catalana", "Països Catalans"],
    )
