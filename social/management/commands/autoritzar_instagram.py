"""Interactive flow to obtain a long-lived Instagram access token.

Usage:
    python manage.py autoritzar_instagram

Walks you through the steps:
  1. Visit Meta's authentication URL (printed) and grab the short-
     lived `access_token` from the redirect's query string.
  2. Paste the short-lived token here when prompted.
  3. The command exchanges it for a long-lived (60-day) token via
     the Graph API and prints the values you need to paste into
     `.env` (`INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`,
     `INSTAGRAM_TOKEN_EXPIRES_AT`).

Prerequisites:
  - INSTAGRAM_APP_ID + INSTAGRAM_APP_SECRET set in .env (used to
    perform the exchange).
  - The Instagram Business / Creator account is linked to a
    Facebook Page and the App is approved for `instagram_basic` +
    `instagram_content_publish`.
"""

from __future__ import annotations

import datetime

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Bytte short-lived Instagram token per long-lived (60 dies)."

    def handle(self, *args, **opts):
        app_id = getattr(settings, "INSTAGRAM_APP_ID", "") or ""
        app_secret = getattr(settings, "INSTAGRAM_APP_SECRET", "") or ""
        if not app_id or not app_secret:
            raise CommandError(
                "Cal definir INSTAGRAM_APP_ID i INSTAGRAM_APP_SECRET a .env "
                "abans d'executar autoritzar_instagram."
            )
        self.stdout.write(
            self.style.NOTICE(
                "1. Obre el següent URL al navegador (login com a admin de l'app):"
            )
        )
        redirect = "https://www.topquaranta.cat/spotify/callback"
        self.stdout.write(
            f"https://www.instagram.com/oauth/authorize?client_id={app_id}"
            f"&redirect_uri={redirect}"
            f"&scope=instagram_business_basic,instagram_business_content_publish"
            f"&response_type=code"
        )
        self.stdout.write(
            "2. Després de l'autorització, copia el `code` de la query string "
            "del callback i enganxa'l aquí."
        )
        code = input("code> ").strip()
        if not code:
            raise CommandError("Cap code introduït.")

        # 1) code → short-lived token
        r = requests.post(
            "https://api.instagram.com/oauth/access_token",
            data={
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect,
                "code": code,
            },
            timeout=20,
        )
        if not r.ok:
            raise CommandError(
                f"Bytte code → short-lived: {r.status_code} {r.text[:300]}"
            )
        body = r.json()
        short = body["access_token"]
        user_id = str(body["user_id"])

        # 2) short-lived → long-lived (60 dies)
        r2 = requests.get(
            "https://graph.instagram.com/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": app_secret,
                "access_token": short,
            },
            timeout=20,
        )
        if not r2.ok:
            raise CommandError(f"short → long: {r2.status_code} {r2.text[:300]}")
        body2 = r2.json()
        long_token = body2["access_token"]
        expires_in = int(body2.get("expires_in", 60 * 86400))
        expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            seconds=expires_in
        )

        self.stdout.write(self.style.SUCCESS("\nLong-lived token obtingut!"))
        self.stdout.write("\nAfegeix al .env:")
        self.stdout.write(f"  INSTAGRAM_ACCESS_TOKEN={long_token}")
        self.stdout.write(f"  INSTAGRAM_USER_ID={user_id}")
        self.stdout.write(f"  INSTAGRAM_TOKEN_EXPIRES_AT={expiry.isoformat()}")
        self.stdout.write(
            "\nDesprés: `sudo systemctl reload topquaranta-web` per " "aplicar."
        )
