# Spec: docs/architecture/social.md

"""Refresh the long-lived Instagram token.

Cron mensual (1r del mes a les 03:00 UTC). The Graph API allows
refreshing a long-lived token any time after it's at least 24 h
old; the refresh resets the expiry to ~60 days from now.

When the `InstagramAuth` row is in use (the normal case) the new
token and expiry are written there directly. Only the `.env`
fallback path prints the values, since we never edit `.env`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from social.instagram_client import is_dry_run, refresh_token
from social.models import InstagramAuth


class Command(BaseCommand):
    help = "Refresca el long-lived token d'Instagram (~60 dies més)."

    def handle(self, *args, **opts):
        if is_dry_run():
            self.stdout.write("Token no configurat (mode DRY_RUN). Surt.")
            return
        try:
            new_token, expiry = refresh_token()
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"refresh_token: {exc}")
        row = InstagramAuth.load()
        if row and row.access_token:
            row.access_token = new_token
            row.expires_at = expiry
            row.save(update_fields=["access_token", "expires_at", "updated_at"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Token refrescat i desat (caduca {expiry:%Y-%m-%d})."
                )
            )
            return
        self.stdout.write(self.style.SUCCESS("Token refrescat."))
        self.stdout.write(f"  INSTAGRAM_ACCESS_TOKEN={new_token}")
        self.stdout.write(f"  INSTAGRAM_TOKEN_EXPIRES_AT={expiry.isoformat()}")
