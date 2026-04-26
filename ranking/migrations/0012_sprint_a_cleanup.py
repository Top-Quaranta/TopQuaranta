"""Sprint A cleanup (2026-04-25).

Three coordinated changes on the ranking app:

  * `RankingProvisional.dies_en_top` → drop. Has been NULL since the
    v2.0 algorithm refactor (2026-04-23); no reader left.
  * `RankingProvisional.lastfm_playcount` → rename to
    `escoltes_setmanals`. Since v2.0 the column has stored the rolling
    7-day plays delta (algorithm output `weekly_plays`), not a
    cumulative total. The new name finally matches the semantics.
  * `ConfiguracioGlobal.ppcc_penalitzacio_per_posicio` → add. Promotes
    the previously module-level `PPCC_PENALITZACIO_PER_POSICIO = 0.04`
    constant in `ranking/algorisme.py` to a tunable setting next to
    the rest of the ranking coefficients.

No data migration needed — both `lastfm_playcount` and `dies_en_top`
on `RankingProvisional` are recomputed from scratch on every nightly
`calcular_ranking --provisional` run, so the rename is a pure SQL
ALTER and the drop loses nothing of value.
"""

from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ranking", "0011_rankingprovisional_age_factor_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="rankingprovisional",
            old_name="lastfm_playcount",
            new_name="escoltes_setmanals",
        ),
        migrations.RemoveField(
            model_name="rankingprovisional",
            name="dies_en_top",
        ),
        migrations.AddField(
            model_name="configuracioglobal",
            name="ppcc_penalitzacio_per_posicio",
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal("0.04"),
                help_text=(
                    "PPCC: penalització per posició a la llista d'origen. "
                    "Cada cançó d'un top territorial entra a PPCC amb un "
                    "score multiplicat per (1 - (posició - 1) × valor). "
                    "Ex amb 0.04: la #1 entra al 100 %, la #2 al 96 %, "
                    "la #25 al 4 %."
                ),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(1),
                ],
            ),
        ),
    ]
