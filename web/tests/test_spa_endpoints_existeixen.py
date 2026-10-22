"""Every literal endpoint the SPA calls must exist in the API.

2026-05-04 renamed `/comunitat/perfil/` to `/compte/perfil-usuari/` and
`OnboardingPage.jsx` kept the old path: the 404 was swallowed and every
new user since then sat on «Carregant…» after logging in, for five
months, until an artist wrote us on Instagram (2026-10-22). Nothing in
CI crosses the SPA/Django line, so this does: it scans the SPA sources
for `api.<verb>('/literal/')` calls and resolves each against the URL
conf. Paths built from variables (template literals, concatenation)
are not literals and are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.urls import Resolver404, resolve

SPA_SRC = Path(__file__).resolve().parents[2] / "web-react" / "src"
API_PREFIX = "/api/v1"
# api.get('/x/'), api.post( "/x/", ...): single or double quotes, no `${`.
_CALL = re.compile(r"""\bapi\.(?:get|post|patch|put|delete)\(\s*(['"])(/[^'"$]*)\1""")


def _literal_paths() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for f in list(SPA_SRC.rglob("*.jsx")) + list(SPA_SRC.rglob("*.js")):
        if ".test." in f.name:
            continue
        for m in _CALL.finditer(f.read_text(encoding="utf-8")):
            path = m.group(2).split("?")[0]
            found.setdefault(path, []).append(str(f.relative_to(SPA_SRC)))
    return found


@pytest.mark.django_db
def test_every_spa_literal_endpoint_resolves():
    paths = _literal_paths()
    assert len(paths) > 20, "the scan found suspiciously few api.* calls"
    missing = []
    for path, files in sorted(paths.items()):
        try:
            resolve(API_PREFIX + path)
        except Resolver404:
            missing.append(f"{path}  ←  {', '.join(sorted(set(files)))}")
    assert not missing, "SPA calls endpoints that do not exist:\n" + "\n".join(missing)
