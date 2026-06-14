"""Authenticated /compte/ endpoints for the React SPA.

GET   /api/v1/compte/dashboard/   — managed artists + proposals + stats
GET   /api/v1/compte/perfil/      — current profile snapshot
PATCH /api/v1/compte/perfil/      — update email / username / password
POST  /api/v1/compte/propostes/   — submit a new-artist proposal
POST  /api/v1/compte/solicituds/  — submit a management request for an
                                    existing artist
"""

from . import gestor_artista
from .dashboard import dashboard, perfil
from .feedback import feedback_crear
from .propostes import gestor_artista_editar, proposta_crear, solicitud_crear
from .rgpd import (
    baixa_avis_top,
    baixa_newsletter,
    compte_esborrar_sollicitar,
    exportar_dades,
)

__all__ = [
    "dashboard",
    "perfil",
    "proposta_crear",
    "solicitud_crear",
    "gestor_artista_editar",
    "gestor_artista",
    "feedback_crear",
    "compte_esborrar_sollicitar",
    "exportar_dades",
    "baixa_newsletter",
    "baixa_avis_top",
]
