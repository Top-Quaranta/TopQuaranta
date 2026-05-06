"""Shared helpers and throttle classes for the compte_views subpackage."""

from rest_framework.throttling import ScopedRateThrottle


class _DataExportThrottle(ScopedRateThrottle):
    scope = "data_export"


class _NewsletterUnsubThrottle(ScopedRateThrottle):
    scope = "newsletter_unsubscribe"


class _FeedbackCreateThrottle(ScopedRateThrottle):
    scope = "feedback_crear"


class _AccountDeleteThrottle(ScopedRateThrottle):
    scope = "account_delete"


class _DMSendThrottle(ScopedRateThrottle):
    scope = "dm_send"


def _serialize_user_artista(ua) -> dict:
    a = ua.artista
    return {
        "pk": ua.pk,
        "estat": ua.estat,
        "verificat": ua.verificat,
        "created_at": ua.created_at.isoformat() if ua.created_at else None,
        "artista": {
            # `pk` is needed by the SPA so verified managers can deep-link
            # into /compte/artista/<pk>/editar (the gestor self-edit form).
            "pk": a.pk,
            "slug": a.slug,
            "nom": a.nom,
        },
    }


def _serialize_proposta(p) -> dict:
    return {
        "pk": p.pk,
        "nom": p.nom,
        "estat": p.estat,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "justificacio": p.justificacio,
        "artista_creat": (
            {"slug": p.artista_creat.slug, "nom": p.artista_creat.nom}
            if p.artista_creat
            else None
        ),
    }


def _profile_payload(user) -> dict:
    # Newsletter preference lives on the related PerfilUsuari row,
    # which is auto-created via post_save signal — but be defensive
    # in case of legacy users created before the signal existed.
    perfil = getattr(user, "perfil", None)
    return {
        "email": user.email,
        "username": user.username,
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        "is_staff": bool(user.is_staff),
        "is_superuser": bool(user.is_superuser),
        "vol_newsletter": bool(perfil and perfil.vol_newsletter),
    }
