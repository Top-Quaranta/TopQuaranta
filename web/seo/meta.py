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

from music.constants import TERRITORI_NOMS as _TERRITORI_NOMS_BASE
from music.models import Album, Artista, Canco

CANONICAL_HOST = settings.SITE_URL  # → "https://www.topquaranta.cat"
SITE_NAME = "TopQuaranta"

# Editorial byline for the human-written landing prose + the "Estat de
# la música en català" report. A consistent named author is an E-E-A-T
# signal (Google + AI crawlers favour attributed editorial content).
EDITORIAL_BYLINE = "Josep Quaranta"
DEFAULT_OG_IMAGE = f"{CANONICAL_HOST}/og/default.png"
LOCALE = "ca_ES"

# Visitor-facing labels override the canonical map for two codes:
#   - "PPCC" is rendered as "Global" on public surfaces (Sprint I bis,
#     also enforced in editorial.jsx::TERRITORI_NOM). The DB code and
#     API query params keep using "PPCC".
#   - "ALT" trims the trailing " territoris" so it reads cleaner in
#     short meta strings.
TERRITORI_NOMS = {**_TERRITORI_NOMS_BASE, "PPCC": "Global", "ALT": "Altres"}

# Robots directives. Default = fully indexable. NOINDEX is used for
# thin pages (e.g. an approved artista with no indexable cançó yet):
# returning 200 + noindex keeps Google from re-crawling them as 404s
# while preserving any accumulated authority, and the directive drops
# automatically the moment the page gains indexable content.
DEFAULT_ROBOTS = (
    "index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1"
)
NOINDEX_ROBOTS = "noindex, follow"

# Last.fm returns "Read more on Last.fm" as the entire bio when an
# artist has no real biography, and appends it as boilerplate to real
# ones. Either way it's noise in a <meta description>.
_LASTFM_BOILERPLATE = "Read more on Last.fm"


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
    # Real pixel dimensions of `og_image`. Default matches the dynamic
    # OG card generator (web/seo/ogimage.py emits 1200×630 PNGs).
    # Pages that fall back to a raw Deezer cover override these with
    # the cover's real size (Deezer `cover_xl` is square 1000×1000),
    # so social scrapers (Twitter/Facebook/WhatsApp) don't crop or
    # mis-scale the preview against a wrong declared aspect ratio.
    og_image_width: int = 1200
    og_image_height: int = 630
    og_type: str = "website"  # website | article | music.album | …
    twitter_card: str = "summary_large_image"
    keywords: list[str] | None = None
    locale: str = LOCALE
    site_name: str = SITE_NAME
    robots: str = DEFAULT_ROBOTS

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


def clean_lastfm_bio(raw: str | None) -> str:
    """Strip HTML and the Last.fm "Read more on Last.fm" boilerplate.

    Returns "" when nothing meaningful is left (i.e. the bio was only
    the placeholder), so callers can fall back to a generated
    description instead of emitting the placeholder verbatim.
    """
    text = strip_tags(raw or "").strip()
    if not text:
        return ""
    # Remove a trailing boilerplate phrase (real bios append it after
    # the actual text; empty bios are *only* the phrase).
    if text.endswith(_LASTFM_BOILERPLATE):
        text = text[: -len(_LASTFM_BOILERPLATE)].rstrip(" .…")
    return text.strip()


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
        title=f"Top 40 i millors cançons en català de {nom} · TopQuaranta",
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


def for_artista(a: Artista, *, thin: bool = False) -> Meta:
    """Build artiste metadata.

    `thin=True` is the approved-but-no-indexable-cançó case: the SEO
    view renders a 200 + noindex page instead of a 404 (see
    web/seo/views.py::artista_seo). The description is generated
    programmatically and the page is flagged noindex.
    """
    territoris: list[str] = []
    loc_qs = a.localitats.select_related("municipi__territori").all()
    if loc_qs:
        codes = {ll.municipi.territori_id for ll in loc_qs if ll.municipi}
        territoris = sorted({TERRITORI_NOMS.get(c, c) for c in codes})
    territori_suffix = (" · " + ", ".join(territoris)) if territoris else ""

    genere = (a.genere or "").strip()

    if thin:
        # No indexable content yet — generate a clean programmatic
        # description (never the Last.fm placeholder) and noindex.
        bits = ["Artista del catàleg de TopQuaranta."]
        if territoris:
            bits.append(f"Música en català de {', '.join(territoris)}.")
        if genere:
            bits.append(f"Gènere: {genere}.")
        bits.append(
            "Encara no hi ha cançons al rànquing; si en tens informació, "
            "contacta'ns."
        )
        return Meta(
            title=f"{a.nom} — Música en català · TopQuaranta",
            description=_trim(" ".join(bits)),
            canonical_url=f"{CANONICAL_HOST}/artista/{a.slug}",
            og_image=f"{CANONICAL_HOST}/og/artista/{a.slug}.png",
            og_type="profile",
            keywords=[a.nom, f"{a.nom} música", "música en català"],
            robots=NOINDEX_ROBOTS,
        )

    n_cancons = a.cancons.filter(verificada=True, activa=True).count()

    # Bio fallback chain. As of 2026-05 every approved Artista row has
    # `bio=""` (no editorial bios written yet), but most carry a
    # `lastfm_bio_summary` from the Last.fm ingest. `clean_lastfm_bio`
    # strips HTML *and* the "Read more on Last.fm" boilerplate, so a
    # placeholder-only bio falls through to the generated line instead
    # of emitting the placeholder verbatim (audit flag #3).
    fallback_bio = clean_lastfm_bio(a.lastfm_bio_summary)
    desc = (
        (a.bio or "").strip()
        or fallback_bio
        or f"{a.nom} és un artista de música en català{territori_suffix}. "
        + (f"Té {n_cancons} cançons verificades a TopQuaranta. " if n_cancons else "")
        + "Coneix-li la discografia, el top setmanal i els enllaços per escoltar-lo."
    )

    return Meta(
        title=f"{a.nom} — Música en català · TopQuaranta",
        description=_trim(desc),
        canonical_url=f"{CANONICAL_HOST}/artista/{a.slug}",
        og_image=f"{CANONICAL_HOST}/og/artista/{a.slug}.png",
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
    # Deezer cover (cover_xl, square 1000×1000) is the better social
    # card for an album; fall back to the dynamic 1200×630 generator
    # only when no cover is stored. Declare the matching dimensions.
    if al.imatge_url:
        og_image, og_w, og_h = al.imatge_url, 1000, 1000
    else:
        og_image, og_w, og_h = f"{CANONICAL_HOST}/og/album/{al.slug}.png", 1200, 630
    return Meta(
        title=f"{al.nom} — {artist_nom} · TopQuaranta",
        description=_trim(desc),
        canonical_url=f"{CANONICAL_HOST}/album/{al.slug}",
        og_image=og_image,
        og_image_width=og_w,
        og_image_height=og_h,
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
    # Deezer cover_xl is square 1000×1000; fall back to the dynamic
    # 1200×630 generator only when the song carries no album cover.
    cover = c.album.imatge_url if c.album_id else None
    if cover:
        og_image, og_w, og_h = cover, 1000, 1000
    else:
        og_image, og_w, og_h = f"{CANONICAL_HOST}/og/canco/{c.slug}.png", 1200, 630
    return Meta(
        title=f"{c.nom} — {artist_nom} · TopQuaranta",
        description=_trim(desc),
        canonical_url=f"{CANONICAL_HOST}/canco/{c.slug}",
        og_image=og_image,
        og_image_width=og_w,
        og_image_height=og_h,
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


def for_comunitat() -> Meta:
    return Meta(
        title="Comunitat de músics en català: busca grup i col·laboradors",
        description=_trim(
            "Fas música en català? Troba grup, busca col·laboradors i "
            "connecta amb cantants, instrumentistes i productors de tots "
            "els territoris. La comunitat de músics en català de TopQuaranta."
        ),
        canonical_url=f"{CANONICAL_HOST}/comunitat-musics",
        og_image=f"{CANONICAL_HOST}/og/home.png",
        og_type="website",
        keywords=[
            "busco grup música català",
            "músics en català busquen banda",
            "col·laboradors música catalana",
            "comunitat músics català",
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


def for_estat_musica() -> Meta:
    return Meta(
        title="L'estat de la música en català · Dades · TopQuaranta",
        description=_trim(
            "Quantes cançons i artistes en català hi ha? Dades obertes "
            "sobre l'estat de la música en català: catàleg verificat, "
            "artistes per territori i cobertura, actualitzat setmanalment."
        ),
        canonical_url=f"{CANONICAL_HOST}/estat-musica-catala",
        og_image=f"{CANONICAL_HOST}/og/default.png",
        og_type="article",
        keywords=[
            "música en català dades",
            "quantes cançons en català",
            "estat música catalana",
            "música en català 2026",
        ],
    )
