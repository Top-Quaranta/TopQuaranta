"""Schema.org JSON-LD generators for SEO surfaces.

Each function returns a Python dict that's serialised to a
`<script type="application/ld+json">` block in the SSR templates.
Validates against schema.org via the Rich Results Test
(https://search.google.com/test/rich-results) — keep the field
names exact and avoid unknown properties.

Coverage:
  - WebSite + Organization (homepage)
  - MusicGroup (artist)
  - MusicAlbum (album)
  - MusicRecording (track)
  - MusicPlaylist (top)
  - BreadcrumbList (every nested page)
"""

from __future__ import annotations

import datetime
from typing import Any

from music.models import Album, Artista, Canco

from .meta import CANONICAL_HOST, SITE_NAME, TERRITORI_NOMS


def _abs(path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return f"{CANONICAL_HOST}{path}"


def _iso_duration(ms: int | None) -> str | None:
    """ISO 8601 duration, e.g. PT3M42S — schema.org's expected format."""
    if not ms:
        return None
    s = ms // 1000
    return f"PT{s // 60}M{s % 60}S"


def _social_links(a: Artista) -> list[str]:
    """`sameAs` is the schema.org property that ties the entity to
    its presence on other authoritative sources. We fill it with
    every external profile we track on the Artista row."""
    fields = [
        "spotify_url",
        "viasona_url",
        "web_url",
        "bandcamp_url",
        "youtube_url",
        "viquipedia_url",
        "soundcloud_url",
        "tiktok_url",
        "facebook_url",
        "instagram_url",
        "twitter_url",
    ]
    out: list[str] = []
    for f in fields:
        v = getattr(a, f, "") or ""
        if v.startswith(("http://", "https://")):
            out.append(v)
    if a.musicbrainz_id:
        out.append(f"https://musicbrainz.org/artist/{a.musicbrainz_id}")
    return out


def website_jsonld() -> dict[str, Any]:
    """Top-level WebSite + Organization for the homepage. Includes
    a `SearchAction` so Google can surface our search box in a
    sitelinks searchbox SERP feature."""
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{CANONICAL_HOST}/#website",
                "url": CANONICAL_HOST + "/",
                "name": SITE_NAME,
                "description": "Rànquing setmanal de música en català",
                "inLanguage": "ca",
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": {
                        "@type": "EntryPoint",
                        "urlTemplate": f"{CANONICAL_HOST}/artistes?q={{search_term_string}}",
                    },
                    "query-input": "required name=search_term_string",
                },
            },
            {
                "@type": "Organization",
                "@id": f"{CANONICAL_HOST}/#org",
                "name": SITE_NAME,
                "url": CANONICAL_HOST + "/",
                "logo": f"{CANONICAL_HOST}/static/brand/logo-topquaranta.png",
                "sameAs": [
                    "https://mastodont.cat/@topquaranta",
                    "https://bsky.app/profile/topquaranta.bsky.social",
                    "https://www.instagram.com/topquaranta/",
                    "https://t.me/topquaranta",
                ],
            },
        ],
    }


def artista_jsonld(a: Artista) -> dict[str, Any]:
    """`MusicGroup` works for both bands and solo artists per
    schema.org guidance. Includes top albums (`album`) and top
    tracks (`track`) when available so Google can show a richer
    knowledge panel."""
    territori_nom = ""
    locs = a.localitats.select_related("municipi__territori").all()
    if locs:
        codes = {ll.municipi.territori_id for ll in locs if ll.municipi}
        nicies = sorted({TERRITORI_NOMS.get(c, c) for c in codes})
        territori_nom = ", ".join(nicies)

    albums = list(
        Album.objects.filter(artista=a, descartat=False).order_by("-data_llancament")[
            :10
        ]
    )
    tracks = list(
        Canco.objects.filter(artista=a, verificada=True, activa=True)
        .select_related("album")
        .order_by("-data_llancament")[:10]
    )

    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "MusicGroup",
        "@id": f"{CANONICAL_HOST}/artista/{a.slug}#group",
        "name": a.nom,
        "url": f"{CANONICAL_HOST}/artista/{a.slug}",
        "inLanguage": "ca",
    }
    if a.bio:
        data["description"] = a.bio[:600]
    if a.genere:
        data["genre"] = a.genere
    if territori_nom:
        data["foundingLocation"] = {"@type": "Place", "name": territori_nom}
    if a.mb_begin_date:
        data["foundingDate"] = a.mb_begin_date.isoformat()
    if a.mb_end_date:
        data["dissolutionDate"] = a.mb_end_date.isoformat()
    sameas = _social_links(a)
    if sameas:
        data["sameAs"] = sameas
    if albums:
        data["album"] = [
            {
                "@type": "MusicAlbum",
                "name": al.nom,
                "url": f"{CANONICAL_HOST}/album/{al.slug}",
                **(
                    {"datePublished": al.data_llancament.isoformat()}
                    if al.data_llancament
                    else {}
                ),
            }
            for al in albums
        ]
    if tracks:
        data["track"] = [
            {
                "@type": "MusicRecording",
                "name": t.nom,
                "url": f"{CANONICAL_HOST}/canco/{t.slug}",
                **({"isrcCode": t.isrc} if t.isrc else {}),
            }
            for t in tracks
        ]
    return data


def album_jsonld(al: Album) -> dict[str, Any]:
    tracks = list(al.cancons.filter(activa=True).order_by("id"))
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "MusicAlbum",
        "@id": f"{CANONICAL_HOST}/album/{al.slug}#album",
        "name": al.nom,
        "url": f"{CANONICAL_HOST}/album/{al.slug}",
        "byArtist": {
            "@type": "MusicGroup",
            "name": al.artista.nom,
            "url": f"{CANONICAL_HOST}/artista/{al.artista.slug}",
        },
        "numTracks": len(tracks),
    }
    if al.imatge_url:
        data["image"] = al.imatge_url
    if al.data_llancament:
        data["datePublished"] = al.data_llancament.isoformat()
    if tracks:
        data["track"] = [
            {
                "@type": "MusicRecording",
                "name": t.nom,
                "url": f"{CANONICAL_HOST}/canco/{t.slug}",
                **({"duration": _iso_duration(t.durada_ms)} if t.durada_ms else {}),
                **({"isrcCode": t.isrc} if t.isrc else {}),
            }
            for t in tracks
        ]
    return data


def canco_jsonld(c: Canco) -> dict[str, Any]:
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "MusicRecording",
        "@id": f"{CANONICAL_HOST}/canco/{c.slug}#recording",
        "name": c.nom,
        "url": f"{CANONICAL_HOST}/canco/{c.slug}",
        "byArtist": {
            "@type": "MusicGroup",
            "name": c.artista.nom,
            "url": f"{CANONICAL_HOST}/artista/{c.artista.slug}",
        },
        "inLanguage": "ca",
    }
    if c.album_id:
        data["inAlbum"] = {
            "@type": "MusicAlbum",
            "name": c.album.nom,
            "url": f"{CANONICAL_HOST}/album/{c.album.slug}",
        }
        if c.album.imatge_url:
            data["image"] = c.album.imatge_url
    if c.data_llancament:
        data["datePublished"] = c.data_llancament.isoformat()
    if c.durada_ms:
        data["duration"] = _iso_duration(c.durada_ms)
    if c.isrc:
        data["isrcCode"] = c.isrc
    if c.preview_url:
        data["audio"] = {"@type": "AudioObject", "contentUrl": c.preview_url}
    return data


def top_jsonld(territori: str, setmana: datetime.date, entries: list) -> dict[str, Any]:
    """`MusicPlaylist` for the weekly top. `entries` are dict-like
    with at least `posicio`, `canco_nom`, `artista_nom`,
    `canco_slug`, `artista_slug`."""
    nom_terr = TERRITORI_NOMS.get(territori, territori)
    return {
        "@context": "https://schema.org",
        "@type": "MusicPlaylist",
        "@id": f"{CANONICAL_HOST}/top#{territori}-{setmana.isoformat()}",
        "name": f"Top {nom_terr} — Setmana {setmana.strftime('%G-W%V')}",
        "url": f"{CANONICAL_HOST}/top",
        "numTracks": len(entries),
        "dateModified": setmana.isoformat(),
        "track": [
            {
                "@type": "MusicRecording",
                "position": e.get("posicio"),
                "name": e.get("canco_nom"),
                "url": _abs(f"/canco/{e.get('canco_slug', '')}"),
                "byArtist": {
                    "@type": "MusicGroup",
                    "name": e.get("artista_nom"),
                    "url": _abs(f"/artista/{e.get('artista_slug', '')}"),
                },
            }
            for e in entries
        ],
    }


def breadcrumbs_jsonld(items: list[tuple[str, str]]) -> dict[str, Any]:
    """`items` is a list of (name, url_path) pairs from root to
    current page. URLs may be paths or absolute — both work."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": name,
                "item": _abs(url),
            }
            for i, (name, url) in enumerate(items)
        ],
    }
