"""`descobrir_enderrock` reads Enderrock's weekly list and says who we
have not approved. It never writes.

# Spec: docs/architecture/ingesta.md
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from ingesta.management.commands import descobrir_enderrock as cmd
from music.models import Artista

# Real markup, enderrock.cat/noticia/32144 (2026-11-13), trimmed.
ARTICLE = """
<span id='txtactualitzatel' class='txtactualitzatel'>| 13/11/2026 a les 12:00h</span>
<h3><u>Les can&ccedil;ons de la setmana</u></h3>
<strong>23HOLANDES</strong><br />
&ldquo;Hoe BCN&rdquo; (Team Za4ever) Trap&#39;n&#39;rap<br />
<br />
<iframe src="https://embed.music.apple.com/es/album/hoe-bcn/1"></iframe><br />
<strong>ADMIRAL KLATSCH &amp; KATTA LANA</strong><br />
&ldquo;Ballar&rdquo; (autoeditat) Trap&#39;n&#39;rap<br />
<strong>MEL I SUCRE</strong><br />
&ldquo;S&#39;olor de s&#39;estiu&rdquo; (autoeditat) Infantil<br />
<strong>DDAA</strong><br />
&ldquo;Estimada Valentina&rdquo; (Halley) Pop-rock<br />
"""
INDEX = "<a href='https://www.enderrock.cat/noticia/32144/noves-cancons-catala-son-x'>"


def test_un_article_dona_un_artista_per_credit():
    data, entrades = cmd.parse_article(ARTICLE)
    assert data == "2026-11-13"
    assert entrades == [
        ("23HOLANDES", "Hoe BCN"),
        ("ADMIRAL KLATSCH", "Ballar"),
        ("KATTA LANA", "Ballar"),
        # « i » is part of the name, and «DDAA» is not an artist.
        ("MEL I SUCRE", "S'olor de s'estiu"),
    ]


@pytest.mark.django_db
def test_nomes_ixen_els_que_no_tenim_aprovats(monkeypatch):
    Artista.objects.create(nom="Katta Lana", lastfm_nom="Katta Lana", aprovat=True)
    Artista.objects.create(nom="Mel i Sucre", lastfm_nom="Mel i Sucre", aprovat=False)
    Artista.objects.create(
        nom="Admiral Klatsch",
        lastfm_nom="Admiral Klatsch",
        aprovat=False,
        pendent_review=True,
    )
    monkeypatch.setattr(
        cmd, "_get", lambda url: INDEX if "especial" in url else ARTICLE
    )
    monkeypatch.setattr(cmd.time, "sleep", lambda s: None)
    abans = Artista.objects.count()

    out = StringIO()
    call_command("descobrir_enderrock", stdout=out)
    eixida = out.getvalue()

    assert "KATTA LANA" not in eixida
    linies = {
        nom: next(line for line in eixida.splitlines() if nom in line)
        for nom in ("23HOLANDES", "ADMIRAL KLATSCH", "MEL I SUCRE")
    }
    assert "no hi és" in linies["23HOLANDES"]
    assert "pendent" in linies["ADMIRAL KLATSCH"]
    assert "descartat" in linies["MEL I SUCRE"]
    assert Artista.objects.count() == abans
