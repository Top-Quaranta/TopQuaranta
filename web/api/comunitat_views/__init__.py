"""Community-platform endpoints (Grup C).

All routes live under `/api/v1/`. This module owns:

  * `/compte/perfil-usuari/`         GET + PATCH — authenticated user's own profile
  * `/comunitat/directori/`          GET — listing of users with visible_directori=True
  * `/comunitat/publicacions/`       GET (list) + POST (create)
  * `/comunitat/publicacions/<pk>/`  GET + PATCH + DELETE (owner or staff)
  * `/comunitat/publicacions-publiques/`  GET — unauthenticated public feed
  * `/staff/publicacions/`           GET — staff moderation list
  * `/staff/publicacions/<pk>/decidir/`   POST — publicar / rebutjar
  * `/staff/directori-usuaris/`      GET + `/staff/directori-usuaris/<pk>/toggle/`

Visibility rules:

  - `interna` + `publicat` → visible to any authenticated user.
  - `publica` + `publicat` → visible to everyone (no auth needed).
  - `esborrany` / `pendent` / `rebutjat` → visible only to the author
    and to staff.

Staff bypass: staff posts skip the `pendent` step and land in `publicat`
immediately. Non-staff posts with `visibilitat=publica` start in
`pendent` and wait for staff review.
"""

from .missatgeria import missatge_crear, missatges_amb_usuari, missatges_inbox
from .perfil import directori, perfil_usuari, upload_imatge
from .publicacions import (
    comentari_esborrar,
    publicacio_comentaris,
    publicacio_detail,
    publicacions,
    publicacions_publiques,
)
from .seguretat import bloquejar, denunciar, desbloquejar
from .staff_moderacio import (
    staff_denuncia_resoldre,
    staff_denuncies,
    staff_directori_toggle_visible,
    staff_directori_usuaris,
    staff_publicacio_decidir,
    staff_publicacions,
)

__all__ = [
    "perfil_usuari",
    "directori",
    "publicacions",
    "publicacio_detail",
    "publicacions_publiques",
    "staff_publicacions",
    "staff_publicacio_decidir",
    "staff_directori_usuaris",
    "staff_directori_toggle_visible",
    "staff_denuncies",
    "staff_denuncia_resoldre",
    "upload_imatge",
    "missatges_inbox",
    "missatges_amb_usuari",
    "missatge_crear",
    "publicacio_comentaris",
    "comentari_esborrar",
    "bloquejar",
    "desbloquejar",
    "denunciar",
]
