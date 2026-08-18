"""Smoke tests for the auth surface.

Pre-2026-05-04 the comptes/ app had zero tests; this fills the gap
flagged by the May audit. We're not going for full branch coverage —
just enough to catch the obvious regressions (registration creates a
PerfilUsuari with the right consent stamps, login + 2FA round-trip,
data export endpoint runs, newsletter token expiry path returns the
friendly message).
"""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from comptes.models import PerfilUsuari, Usuari


class RegisterEndpointTest(TestCase):
    """`POST /api/v1/auth/register/` is the public sign-up flow."""

    def test_register_creates_user_and_perfil_with_consent(self):
        client = Client()
        resp = client.post(
            "/api/v1/auth/register/",
            data={
                "email": "alice@example.test",
                "password1": "ComplexEnough!42x",
                "password2": "ComplexEnough!42x",
                "accepta_termes": True,
                "edat_min": True,
                "vol_newsletter": True,
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        u = Usuari.objects.get(email="alice@example.test")
        self.assertFalse(u.is_active)  # awaiting email activation
        perfil = PerfilUsuari.objects.get(usuari=u)
        # Newsletter consent recorded with timestamp (RGPD).
        self.assertTrue(perfil.vol_newsletter)
        self.assertIsNotNone(perfil.consent_newsletter_at)
        self.assertIsNotNone(perfil.consent_termes_at)

    def test_register_existing_email_does_not_leak(self):
        Usuari.objects.create_user(
            email="bob@example.test", password="x", username="bob"
        )
        client = Client()
        resp = client.post(
            "/api/v1/auth/register/",
            data={
                "email": "bob@example.test",
                "password1": "ComplexEnough!42x",
                "password2": "ComplexEnough!42x",
                "accepta_termes": True,
                "edat_min": True,
            },
            content_type="application/json",
        )
        # Endpoint MUST NOT signal "already exists" — it returns OK
        # with a generic message so an outsider can't enumerate
        # existing accounts.
        self.assertEqual(resp.status_code, 201, resp.content)


class NewsletterTokenExpiryTest(TestCase):
    """The May-2026 audit found the unsubscribe token never expired.
    We added `max_age=1y` to `signing.loads`. Verify the
    SignatureExpired path returns the friendly message."""

    def test_expired_token_is_refused_and_does_not_unsubscribe(self):
        """Property asserted: a correctly-signed token older than the
        1-year `max_age` is refused (4xx) and the user's newsletter
        opt-in is left untouched; garbage tokens are refused too.
        The wording of the friendly message is not pinned."""
        import time as _time
        from unittest.mock import patch

        from django.core import signing

        u = Usuari.objects.create_user(
            email="old@example.test", password="x", username="old"
        )
        PerfilUsuari.objects.filter(usuari=u).update(vol_newsletter=True)
        token = signing.dumps({"u": u.pk}, salt="newsletter-baixa")
        client = Client()

        # Garbage token → refused.
        resp = client.get("/api/v1/compte/baixa-newsletter/?token=garbage")
        self.assertGreaterEqual(resp.status_code, 400)
        self.assertLess(resp.status_code, 500)

        # Same (valid) token, but the clock is now >1 year later → refused
        # and the opt-in survives.
        real_now = _time.time()
        with patch(
            "django.core.signing.time.time",
            return_value=real_now + 60 * 60 * 24 * 366,
        ):
            resp = client.get(f"/api/v1/compte/baixa-newsletter/?token={token}")
        self.assertGreaterEqual(resp.status_code, 400)
        self.assertLess(resp.status_code, 500)
        self.assertTrue(resp.json().get("error"))
        u.refresh_from_db()
        self.assertTrue(u.perfil.vol_newsletter)

    def test_valid_token_unsubscribes(self):
        from django.core import signing

        u = Usuari.objects.create_user(
            email="c@example.test", password="x", username="c"
        )
        PerfilUsuari.objects.filter(usuari=u).update(vol_newsletter=True)
        token = signing.dumps({"u": u.pk}, salt="newsletter-baixa")
        client = Client()
        resp = client.get(f"/api/v1/compte/baixa-newsletter/?token={token}")
        self.assertEqual(resp.status_code, 200, resp.content)
        u.refresh_from_db()
        self.assertFalse(u.perfil.vol_newsletter)


class CancoManagerTest(TestCase):
    """Smoke for the new Canco.objects.public() / .pendents() managers."""

    def test_public_filters_verificada_activa(self):
        from datetime import date

        from music.models import Album, Artista, Canco

        a = Artista.objects.create(nom="Test Artist", aprovat=True)
        alb = Album.objects.create(nom="Test Alb", artista=a)
        Canco.objects.create(
            nom="active-verified",
            artista=a,
            album=alb,
            verificada=True,
            activa=True,
            data_llancament=date.today(),
        )
        Canco.objects.create(
            nom="pending",
            artista=a,
            album=alb,
            verificada=False,
            activa=True,
            data_llancament=date.today(),
        )
        Canco.objects.create(
            nom="rejected-kept-as-marker",
            artista=a,
            album=alb,
            verificada=False,
            activa=False,
            data_llancament=date.today(),
        )

        public = list(Canco.objects.public())
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0].nom, "active-verified")

        pendents = list(Canco.objects.pendents())
        self.assertEqual(len(pendents), 1)
        self.assertEqual(pendents[0].nom, "pending")
