"""`a7_long_runner` says how OLD a song is, never how long it has charted.

The detector reads `Canco.data_llancament` and emits months since
release. Until 2026-08-17 it called that `mesos`, and 35 of the 41
phrases in its bank spent it as tenure — "suma {mesos} mesos a la
llista", "encadena {mesos} mesos al top". Those are different claims,
and the second one was false.

Reported by Miquel from a published Balearic post: *«Júlia Colom suma 9
mesos a la llista amb Gelosies»*. Gelosies was released 2025-10-31 (9
months — the number was right) and had charted for 14 weeks between
2026-04-20 and 2026-08-10, **with gaps**. Roughly 2.5× inflated.

And it could not have been right for any song: `TopSetmanal` starts on
2026-04-13. A tenure claim beyond ~4 months is not merely unverified, it
is arithmetically impossible — which is exactly why a caption must not
make one.
"""

from __future__ import annotations

import datetime
import re
import unicodedata

import pytest

from social.narrative.banks import hero

# Words that turn the number into a claim about time spent charting.
# `mesos_estrena` is an age, so none of these may sit next to it.
PERMANENCIA = re.compile(
    r"\{mesos_estrena\}\s*mesos?\s+(?:a|al|de)\s+(?:la\s+)?(?:llista|top)\b"
    r"|(?:suma|encadena|duu|porta|figura|viu|resisteix)\w*\s+\{mesos_estrena\}",
    re.IGNORECASE,
)


def _frases() -> list[tuple[str, str]]:
    banc = hero.HERO["a7_long_runner"]
    return [(reg, f) for reg, frases in banc.items() for f in frases]


def test_the_bank_is_not_empty():
    """A guard on the guard: a renamed bank key would make every check
    below vacuous."""
    assert len(_frases()) >= 30


@pytest.mark.parametrize("registre,frase", _frases())
def test_no_phrase_claims_time_spent_in_the_chart(registre, frase):
    m = PERMANENCIA.search(frase)
    assert not m, (
        f"[{registre}] afirma permanència al top, i el número és l'edat de "
        f"la cançó: …{m.group(0)}… → {frase}"
    )


@pytest.mark.parametrize("registre,frase", _frases())
def test_a_phrase_with_the_number_anchors_it_to_the_release(registre, frase):
    """Stating the age is only honest if the sentence says it is an age.
    Bare "{mesos_estrena} mesos" next to the chart reads as tenure."""
    if "{mesos_estrena}" not in frase:
        return  # phrases that skip the number entirely are fine
    # Mutation audit 2026-08-18: the placeholder name itself contains
    # "estrena", so anchors must be looked for AFTER the placeholder is
    # replaced — otherwise every phrase passes vacuously.
    text = unicodedata.normalize("NFC", frase.replace("{mesos_estrena}", "N")).lower()
    ancores = (
        "eixir",
        "estrena",
        "publica",
        "després",
        "de fa",
        "té N",
        "ja té",
        "a l'esquena",
        "de cançó",
        "treure",
    )
    assert any(
        unicodedata.normalize("NFC", a).lower() in text for a in ancores
    ), f"[{registre}] dona el número sense dir que és l'edat de la cançó: {frase}"


def test_the_old_key_is_gone():
    """`mesos` meant tenure to whoever wrote those phrases. If it comes
    back, the phrases will read as tenure again."""
    for _, frase in _frases():
        assert "{mesos}" not in frase, frase


@pytest.mark.django_db
def test_the_detector_emits_the_age_not_the_tenure():
    """The real Gelosies shape: old song, short and gappy chart run."""
    from music.models import Album, Artista, Canco, Territori
    from ranking.models import ConfiguracioGlobal, TopSetmanal
    from social.narrative.scenarios import detect_a7_long_runner

    ConfiguracioGlobal.objects.get_or_create(pk=1)
    t, _ = Territori.objects.get_or_create(codi="BAL", defaults={"nom": "Illes"})
    a = Artista.objects.create(nom="Júlia Test", lastfm_nom="Júlia Test", aprovat=True)
    a.territoris.add(t)
    setmana = datetime.date(2026, 8, 10)
    llancament = datetime.date(2025, 10, 31)  # 9 months before
    alb = Album.objects.create(artista=a, nom="D", data_llancament=llancament)
    c = Canco.objects.create(
        artista=a,
        album=alb,
        nom="Gelosies Test",
        data_llancament=llancament,
        verificada=True,
        activa=True,
    )
    # Charted for two weeks only — a fifth of the song's age.
    for i, s in enumerate([setmana - datetime.timedelta(days=7), setmana]):
        TopSetmanal.objects.create(
            canco=c,
            territori="BAL",
            setmana=s,
            posicio=1,
            score_setmanal=100,
            weekly_plays=100,
            algorithm_version="v2.0",
        )

    sc = detect_a7_long_runner("BAL", setmana)
    assert sc is not None
    assert sc.data["mesos_estrena"] == 9  # age, not the 2 weeks charted
    assert "mesos" not in sc.data  # the ambiguous key must be gone


# ── Contracted prepositions (same post, second defect) ─────────────


@pytest.mark.parametrize(
    "cas",
    [
        {"posicio_anterior_str": "al 15è", "posicio_anterior_de": "del 15è"},
        {
            "posicio_anterior_str": "fora del top",
            "posicio_anterior_de": "de fora del top",
        },
    ],
    ids=["dins-del-top", "fora-del-top"],
)
def test_no_phrase_stacks_two_prepositions(cas):
    """The same Balearic post read «puja **de al** 15è al 1r».

    `posicio_anterior_str` already carries its article ("al 15è"), so a
    phrase writing "de {posicio_anterior_str}" stacked a second one.
    Catalan contracts it — "del 15è" — but the outside-the-top value
    ("fora del top") takes a plain "de", so one field cannot serve both
    positions. Hence `posicio_anterior_de`, and this check on every
    phrase that uses either.
    """
    dades = dict(
        canco="Festa i Drama",
        artista="Maria Jaume",
        de_artista="de Maria Jaume",
        territori_label="Illes Balears",
        territori_ordinal="balear",
        **cas,
    )
    dolents = (" de al ", " de del ", " des de del ", " de de ", "del fora")
    for registre, frases in hero.HERO["a1_outside_to_top1"].items():
        for f in frases:
            if "posicio_anterior" not in f:
                continue
            text = f.format(**dades)
            for mal in dolents:
                assert mal not in text, f"[{registre}] {mal!r} → {text}"


@pytest.mark.django_db
@pytest.mark.parametrize("posicio_previa,esperat", [(15, "del 15è"), (7, "del 7è")])
def test_the_detector_emits_the_contracted_form(posicio_previa, esperat):
    """The bank check above builds the strings itself, so it cannot see a
    regression on the detector side. This one reads what the detector
    actually emits."""
    from music.models import Album, Artista, Canco, Territori
    from ranking.models import ConfiguracioGlobal, TopSetmanal
    from social.narrative.scenarios import detect_a1_outside_to_top1

    ConfiguracioGlobal.objects.get_or_create(pk=1)
    t, _ = Territori.objects.get_or_create(codi="BAL", defaults={"nom": "Illes"})
    a = Artista.objects.create(nom="Puja Test", lastfm_nom="Puja Test", aprovat=True)
    a.territoris.add(t)
    setmana = datetime.date(2026, 8, 10)
    anterior = setmana - datetime.timedelta(days=7)
    alb = Album.objects.create(artista=a, nom="D", data_llancament=anterior)
    c = Canco.objects.create(
        artista=a,
        album=alb,
        nom="Puja",
        data_llancament=anterior,
        verificada=True,
        activa=True,
    )
    # A filler song so the previous week exists and is not just our climber.
    altra = Canco.objects.create(
        artista=a,
        album=alb,
        nom="Farciment",
        data_llancament=anterior,
        verificada=True,
        activa=True,
    )
    for canco, setm, pos in (
        (c, anterior, posicio_previa),
        (altra, anterior, 1),
        (c, setmana, 1),
    ):
        TopSetmanal.objects.create(
            canco=canco,
            territori="BAL",
            setmana=setm,
            posicio=pos,
            score_setmanal=100,
            weekly_plays=100,
            algorithm_version="v2.0",
        )

    sc = detect_a1_outside_to_top1("BAL", setmana)
    assert sc is not None
    assert sc.data["posicio_anterior_de"] == esperat
    assert not sc.data["posicio_anterior_de"].startswith("de al")
