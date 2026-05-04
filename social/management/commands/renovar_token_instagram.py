"""Refresh the long-lived Instagram token.

Cron mensual (1r del mes a les 03:00 UTC). The Graph API allows
refreshing a long-lived token any time after it's at least 24 h
old; the refresh resets the expiry to ~60 days from now.

Output: prints the new values for `.env`. Doesn't write the file
itself — that's an ops decision (sometimes you want to inspect
before applying). For a fully automatic flow, redirect the output
to a deploy script.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from social.instagram_client import is_dry_run, refresh_token


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
        self.stdout.write(self.style.SUCCESS("Token refrescat."))
        self.stdout.write(f"  INSTAGRAM_ACCESS_TOKEN={new_token}")
        self.stdout.write(f"  INSTAGRAM_TOKEN_EXPIRES_AT={expiry.isoformat()}")
