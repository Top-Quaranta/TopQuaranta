"""List the artists Enderrock publishes that we have not approved.

Enderrock's weekly «Les noves cançons en català són de…» is the closest
thing to a census of new music in Catalan. On 2026-11-20, of the 1,435
artists it had listed in twelve months, only 370 were approved here;
231 were tombstones (`netejar_pendents_no_ppcc` discards a pendent
nobody triaged, and nothing ever brings it back) and 788 did not exist.

Read-only: this command never writes. It prints who is missing so a
human can approve them with a municipi and a verified Deezer profile —
the two things a name in a magazine does not give.

    python manage.py descobrir_enderrock [--setmanes N]

# Spec: docs/architecture/ingesta.md
"""

from __future__ import annotations

import html
import re
import time
from collections import defaultdict

import requests
from django.core.management.base import BaseCommand

from music.models import Artista, normalitza_nom_homonim

INDEX = "https://www.enderrock.cat/especial/1303/novetats-discografiques?&pag={}"
UA = {
    "User-Agent": "Mozilla/5.0 (compatible; TopQuaranta/1.0; +https://topquaranta.cat)"
}
# ponytail: one article a week, ~20 links per index page.
_PER_PAGINA = 20

_ENLLAC = re.compile(r"https://www\.enderrock\.cat/noticia/(\d+)/noves-cancons[^'\"]*")
_ENTRADA = re.compile(r"<strong>([^<]+)</strong>\s*<br\s*/?>\s*[“\"]([^”\"<]+)[”\"]")
_DATA = re.compile(r"(\d\d)/(\d\d)/(20\d\d) a les")
# NOT « i »: it is part of names («Mel i Sucre», «Cargols i Ceba»).
_SEPARADOR = re.compile(r"\s+(?:&|AMB|FEAT\.?|FT\.?)\s+|,\s*")
# «DDAA» = diversos autors, a collective credit, not an artist.
_NO_ARTISTA = {"DDAA"}


def _get(url: str) -> str:
    resp = requests.get(url, headers=UA, timeout=20)
    resp.raise_for_status()
    return resp.text


def enllacos(index_html: str) -> dict[int, str]:
    return {int(m.group(1)): m.group(0) for m in _ENLLAC.finditer(index_html)}


def parteix(credit: str) -> list[str]:
    noms = [n.strip() for n in _SEPARADOR.split(credit)]
    return [n for n in noms if len(n) > 1 and n not in _NO_ARTISTA]


def parse_article(article_html: str) -> tuple[str, list[tuple[str, str]]]:
    """`(data ISO, [(artista, títol), …])`, one pair per credited artist."""
    text = html.unescape(article_html)
    m = _DATA.search(text)
    data = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""
    return data, [
        (nom, titol.strip())
        for credit, titol in _ENTRADA.findall(text)
        for nom in parteix(credit.strip())
    ]


def estat(nom: str) -> str:
    """`aprovat` / `pendent` / `descartat` / `no hi és`, by homonym key."""
    files = list(
        Artista.objects.filter(nom_normalitzat=normalitza_nom_homonim(nom)).values_list(
            "aprovat", "pendent_review"
        )
    )
    if any(aprovat for aprovat, _ in files):
        return "aprovat"
    if any(pendent for _, pendent in files):
        return "pendent"
    return "descartat" if files else "no hi és"


class Command(BaseCommand):
    help = "Llista els artistes de les novetats d'Enderrock que no tenim aprovats."

    def add_arguments(self, parser):
        parser.add_argument("--setmanes", type=int, default=4)

    def handle(self, *args, **opts) -> None:
        setmanes = opts["setmanes"]
        articles: dict[int, str] = {}
        for pagina in range(1, -(-setmanes // _PER_PAGINA) + 1):
            articles.update(enllacos(_get(INDEX.format(pagina))))

        vistos: dict[str, dict] = defaultdict(lambda: {"n": 0, "data": "", "titol": ""})
        for num in sorted(articles, reverse=True)[:setmanes]:
            data, entrades = parse_article(_get(articles[num]))
            for nom, titol in entrades:
                v = vistos[nom]
                v["n"] += 1
                if data >= v["data"]:
                    v["data"], v["titol"] = data, titol
            time.sleep(0.3)

        falten = [(estat(nom), nom, v) for nom, v in vistos.items()]
        falten = [f for f in falten if f[0] != "aprovat"]
        for e, nom, v in sorted(falten, key=lambda f: (-f[2]["n"], f[1])):
            self.stdout.write(
                f"{v['n']:>2}  {e:<9}  {nom} — «{v['titol']}» ({v['data']})"
            )
        self.stdout.write(
            f"\n{len(vistos)} artistes en {min(setmanes, len(articles))} setmanes; "
            f"{len(falten)} sense aprovar."
        )
