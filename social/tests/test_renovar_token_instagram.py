# Spec: docs/architecture/social.md

"""The monthly refresh must persist the new token, not only print it.

2026-09-09: the cron refreshed the token on 1 Sep, printed it to the
log and nobody applied it; the DB row kept the July token and the
expiry alarm fired the day before it died.
"""

from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from social.models import InstagramAuth

pytestmark = pytest.mark.django_db


def test_refresh_writes_token_and_expiry_to_db_row():
    InstagramAuth.objects.create(
        pk=1,
        access_token="OLD" * 10,
        instagram_user_id="123",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    new_expiry = datetime.now(timezone.utc) + timedelta(days=60)
    out = StringIO()
    with (
        patch(
            "social.management.commands.renovar_token_instagram.is_dry_run",
            return_value=False,
        ),
        patch(
            "social.management.commands.renovar_token_instagram.refresh_token",
            return_value=("NEW" * 10, new_expiry),
        ),
    ):
        call_command("renovar_token_instagram", stdout=out)

    row = InstagramAuth.load()
    assert row.access_token == "NEW" * 10
    assert row.expires_at == new_expiry
    assert "NEW" * 10 not in out.getvalue(), "the token must not be printed to the log"
