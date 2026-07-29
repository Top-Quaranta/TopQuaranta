"""Instagram suggestion buffer + first batch of 29 candidates.

The two new fields are a staff-review buffer for the
`/staff/artistes/sense-instagram` workflow: a candidate handle lands in
`instagram_url_suggerit` and only reaches the canonical `instagram_url`
when staff clicks through. See `music/models.py` for why the canonical
field can never be written automatically.

The seed below is the first batch, produced 2026-07-29 by an out-of-band
web search over the 67 first (alphabetically) of the 264 approved artists
with live songs and no Instagram. Applying it is idempotent and
conservative: an artista that already has an `instagram_url`, or that no
longer exists, is skipped.

ponytail: the batch is inlined here rather than behind an import command
because it is one-shot data that has to reach prod, and a migration
rides the existing deploy. A second batch deserves the command.
"""

from django.db import migrations, models

# (artista_pk, instagram_url, evidence shown to staff)
SUGGERIMENTS = [
    (
        3668,
        "https://www.instagram.com/ainareig/",
        "post que anuncia «Un matí més», cançó nostra",
    ),  # Aina Reig
    (
        2563,
        "https://www.instagram.com/aleixquirii_/",
        "lligat a «Suc de Préssec», cançó nostra",
    ),  # Aleix Quirii
    (
        3739,
        "https://www.instagram.com/alexcircuns/",
        "bio menciona «32 d'agost», cançó nostra",
    ),  # Alex Circuns
    (
        3822,
        "https://www.instagram.com/alvert.alvert/",
        "«GAMBERRU» + Mataró, tot dos nostres",
    ),  # Alvert
    (
        3845,
        "https://www.instagram.com/amicdelscirerers/",
        "perfil d'artista, «Tan perfecte» 2023 associat",
    ),  # Amic dels Cirerers
    (
        3685,
        "https://www.instagram.com/andanaoficial_/",
        "handle citat en prosa; Mataró + Boom Boom Fighters, tots dos nostres",
    ),  # Andana
    (
        2599,
        "https://www.instagram.com/apologiagrup/",
        "punk-rock de Vila-real, municipi nostre",
    ),  # Apologia Grup
    (
        3239,
        "https://www.instagram.com/aradiadenit/",
        "handle = nom exacte, rap/hip-hop",
    ),  # Aradia de Nit
    (
        2450,
        "https://www.instagram.com/aritubau/",
        "Premià de Mar, municipi nostre",
    ),  # Ariadna Tubau
    (
        2887,
        "https://www.instagram.com/autentichomelludriga/",
        "handle citat en prosa; Barcelona, hip-hop",
    ),  # Autèntic Home Llúdriga
    (
        3121,
        "https://www.instagram.com/bertasalariba/",
        "bio «Cantant i compositora», Manresa",
    ),  # Berta Sala
    (3356, "https://www.instagram.com/blaumut/", "25k seg., grup exacte"),  # Blaumut
    (
        2707,
        "https://www.instagram.com/blu_nana_music/",
        "«Com jo et veig» 2026, cançó nostra",
    ),  # Blu Nana
    (
        3168,
        "https://www.instagram.com/brighton64bcn/",
        "grup mod de Barcelona, 4k seg.",
    ),  # Brighton 64
    (
        2407,
        "https://www.instagram.com/bru_oro/",
        "154k seg., «Vinagreta» confirmat",
    ),  # Bruno Oro
    (
        4041,
        "https://www.instagram.com/cabot_music/",
        "grup de Marratxí, municipi nostre",
    ),  # Cabot
    (
        4150,
        "https://www.instagram.com/calagherpooh/",
        "DUBTE: hi ha @calagherpooh i @calagher_; «Galimaties» confirmat com a seu",
    ),  # Calagher
    (
        2761,
        "https://www.instagram.com/cappelaoficial/",
        "grup a cappella de Mallorca",
    ),  # Cap Pela
    (
        4158,
        "https://www.instagram.com/carlessanahujavalls/",
        "DUBTE: handle diu «valls» i el nostre és de Vilafranca; «Notes de pas» sí que és seu",
    ),  # Carles Sanahuja
    (
        2544,
        "https://www.instagram.com/cax1to/",
        "«Mediterrània» amb En Rick confirmada",
    ),  # Caxito
    (
        2718,
        "https://www.instagram.com/somcelobert/",
        "promou l'EP «Xamfrà», que conté «Bar de l'Eixample»",
    ),  # Celobert
    (
        3842,
        "https://www.instagram.com/centvidg/",
        "MITJÀ: handle citat des d'un vídeo de Centvi dg",
    ),  # Centvi Dg
    (
        3551,
        "https://www.instagram.com/ceskfreixas/",
        "cantautor de Sant Pere de Riudebitlles, municipi nostre",
    ),  # Cesk Freixas
    (
        3175,
        "https://www.instagram.com/clamsmusica/",
        "«Ara et toca a tu» és del seu disc «Punts de Fuga»",
    ),  # Clams
    (
        3948,
        "https://www.instagram.com/clarafiol/",
        "cantautora de Palma, municipi nostre",
    ),  # Clara Fiol
    (
        2712,
        "https://www.instagram.com/clarapeya/",
        "64k seg., bio «Pianista • Creadora»",
    ),  # Clara Peya
    (
        2783,
        "https://www.instagram.com/claudiadoxiva/",
        "DUBTE: handle citat en prosa; TikTok és @claudia_xiva. Verificar.",
    ),  # Clàudia Xiva
    (
        4119,
        "https://www.instagram.com/cristinavallribera/",
        "bio «Cantactriu», 1.4k seg.",
    ),  # Cristina Vallribera
    (
        2406,
        "https://www.instagram.com/davidcanalmusic/",
        "MITJÀ: músic amb 4.3k seg.; sense confirmar Olost ni la cançó",
    ),  # David Canal
]


def seed(apps, schema_editor):
    Artista = apps.get_model("music", "Artista")
    for pk, url, nota in SUGGERIMENTS:
        Artista.objects.filter(pk=pk, instagram_url="").update(
            instagram_url_suggerit=url,
            instagram_suggerit_nota=nota,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0093_auto_whisper_motiu"),
    ]

    operations = [
        migrations.AddField(
            model_name="artista",
            name="instagram_url_suggerit",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="artista",
            name="instagram_suggerit_nota",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Evid\u00e8ncia que sost\u00e9 el suggeriment (per qu\u00e8 creiem que "
                    "aquest perfil \u00e9s d'aquest artista). Es mostra a l'staff."
                ),
                max_length=200,
            ),
        ),
        # RunPython reverse is a no-op: the two RemoveField operations
        # that undo this migration drop the columns and the data with
        # them, so there is nothing to unwind separately.
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
