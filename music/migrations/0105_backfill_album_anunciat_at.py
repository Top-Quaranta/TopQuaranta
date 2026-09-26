"""Reconstruct which releases the novetats posts actually carried.

Going forward `anunciat_at` is stamped when a publication ships. For
everything already published there is no record, so we replay the window
the old `build_novetats` used — `(previous publication's date, this
publication's date]` on `data_llancament` — over the real publication
timeline and stamp whatever each post would have picked up.

The replay is deliberately biased towards leaving rows NULL. A false
NULL only means the release gets priority as «cançó del dia» — the
remedy we want for the ones we missed. A false stamp would hide it for
good. So the bounds are strict and an album with no eligible song today
is left alone.

Its own output is the point: the releases this leaves NULL are the 41 of
136 (July-September 2026) that the old window swallowed, among them
Marta Shanti «Flama», the case that got reported.
"""

from datetime import timedelta

from django.db import migrations
from django.db.models import Q

DIES_ENRERE_PRIMERA = 7  # el `dies_enrere` per defecte del codi antic

TIPUS_ALBUM = {"nous_albums": ["album"], "nous_singles": ["single", "ep"]}


def endavant(apps, schema_editor):
    Album = apps.get_model("music", "Album")
    SocialPost = apps.get_model("social", "SocialPost")

    for tipus_post, tipus_album in TIPUS_ALBUM.items():
        publicacions = list(
            SocialPost.objects.filter(tipus=tipus_post, status="publicat")
            .exclude(published_at=None)
            .order_by("published_at")
            .values_list("published_at", flat=True)
        )
        anterior = None
        for pub in publicacions:
            filtre_tipus = Q()
            for t in tipus_album:
                filtre_tipus |= Q(tipus__iexact=t)
            qs = (
                Album.objects.filter(filtre_tipus)
                .filter(
                    anunciat_at__isnull=True,
                    # el post no podia vore el que encara no existia
                    created_at__lte=pub,
                    data_llancament__isnull=False,
                    data_llancament__lte=pub.date(),
                    # el codi antic exigia una cançó viva a l'àlbum
                    cancons__verificada=True,
                    cancons__activa=True,
                )
                .distinct()
            )
            if anterior is None:
                qs = qs.filter(
                    data_llancament__gte=pub.date()
                    - timedelta(days=DIES_ENRERE_PRIMERA)
                )
            else:
                # estrictament posterior: era el tall «+1 dia» del codi antic
                qs = qs.filter(data_llancament__gt=anterior.date())
            # `update()` no admet `distinct()`: materialitzem els ids.
            ids = list(qs.values_list("pk", flat=True))
            if ids:
                Album.objects.filter(pk__in=ids).update(anunciat_at=pub)
            anterior = pub


def enrere(apps, schema_editor):
    apps.get_model("music", "Album").objects.update(anunciat_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0104_album_anunciat_at"),
        ("social", "0010_alter_socialpost_unique_together_socialpost_slot_key_and_more"),
    ]

    operations = [migrations.RunPython(endavant, enrere)]
