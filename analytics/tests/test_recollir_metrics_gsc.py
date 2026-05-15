"""GSC cron failure propagation.

The previous version of `recollir_metrics_gsc` swallowed exceptions
inside the `searchanalytics().query().execute()` try/except and
returned cleanly, leaving `tq-run` with exit 0 and `tq-health` blind
to a broken cron. After the 2026-05-15 OAuth-token-expiry incident
the except block re-raises, and this test locks that contract in.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.test import override_settings


@pytest.mark.django_db
@override_settings(
    GSC_SITE_URL="sc-domain:topquaranta.cat",
    GSC_OAUTH_CLIENT_ID="dummy",
    GSC_OAUTH_CLIENT_SECRET="dummy",
    GSC_OAUTH_REFRESH_TOKEN="dummy",
)
def test_gsc_fetch_failure_propagates_and_logs(caplog):
    """A failure inside `searchanalytics().query().execute()` must
    propagate out of `call_command`, AND log via `logger.exception`
    so the traceback lands in errors.log."""
    fake_service = MagicMock()
    fake_service.searchanalytics.return_value.query.return_value.execute.side_effect = (
        RuntimeError("invalid_grant: Token has been expired or revoked.")
    )

    with (
        patch(
            "analytics.management.commands.recollir_metrics_gsc."
            "Command._build_credentials",
            return_value=MagicMock(name="creds"),
        ),
        patch(
            "googleapiclient.discovery.build",
            return_value=fake_service,
        ),
        caplog.at_level(
            logging.ERROR,
            logger="analytics.management.commands.recollir_metrics_gsc",
        ),
    ):
        with pytest.raises(RuntimeError, match="invalid_grant"):
            call_command("recollir_metrics_gsc")

    # logger.exception("GSC fetch failed") must have fired so the
    # traceback ends up in errors.log even when tq-run sees the
    # non-zero exit and writes status=FAIL.
    assert any(
        "GSC fetch failed" in record.getMessage() for record in caplog.records
    ), "logger.exception('GSC fetch failed') was not called"
