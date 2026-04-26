"""Backward-compatibility shim — Sprint C (2026-04-25).

The historical 3 300-LoC monolith was split into the
`web/api/staff/` package (one module per area). This file re-exports
every public name so `urls.py`, `comunitat_views.py` and any other
caller that did `from web.api import staff_views` keeps working.

For new endpoints, edit the relevant module under `web/api/staff/`
and add the name to `web/api/staff/__init__.py`. Don't add code here.
"""

# Star-import the package, which re-exports each module's public names.
from web.api.staff import *  # noqa: F401, F403

# IsStaff is required by `comptes/comunitat_views.py`. The star import
# above doesn't pull underscore-free private names that aren't in
# `__all__`; importing it explicitly is safest.
from web.api.staff._common import IsStaff  # noqa: F401
