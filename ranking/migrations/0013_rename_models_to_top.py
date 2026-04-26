"""Sprint Naming consolidation (2026-04-25): rename
`RankingSetmanal` → `TopSetmanal` and `RankingProvisional` → `TopProvisional`.

Hand-written `RenameModel` operations — Django's auto-detector
proposed a destructive drop+create chain because the rename was
discovered alongside other unrelated edits, and we MUST preserve the
historical ranking rows. This migration is purely structural: tables
become `ranking_topsetmanal` / `ranking_topprovisional`, all rows
survive intact.

App label stays `ranking` (renaming it would shake the ContentType
table and every reverse FK out of place; out of scope here).
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ranking", "0012_sprint_a_cleanup"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="RankingSetmanal",
            new_name="TopSetmanal",
        ),
        migrations.RenameModel(
            old_name="RankingProvisional",
            new_name="TopProvisional",
        ),
    ]
