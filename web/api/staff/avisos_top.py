"""Staff endpoint to run the "has entrat al top" manager alert.

Wraps the `enviar_avisos_top` management command so staff can trigger it
from the panel. DRY-RUN by default; the real send requires an explicit
`{"send": true}` (the button passes it). All dedup/preference guards live
in the command, not here.

# Spec: docs/architecture/comptes.md
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

from django.core.management import CommandError, call_command
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from web.api.staff._common import IsStaff


@api_view(["POST"])
@permission_classes([IsStaff])
def enviar_avisos_top(request: Request) -> Response:
    """Run `enviar_avisos_top`. Body: `{"send": bool, "setmana":
    "YYYY-MM-DD"?}`. Default DRY-RUN (no email, no ledger write); pass
    `send=true` for the real send. Streams the command output back so the
    operator sees exactly who was (or would be) notified."""
    send = bool(request.data.get("send"))
    setmana = (request.data.get("setmana") or "").strip()

    kwargs: dict = {}
    if send:
        kwargs["send"] = True
    if setmana:
        kwargs["setmana"] = setmana

    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            call_command("enviar_avisos_top", **kwargs)
    except CommandError as exc:
        return Response({"error": str(exc), "stdout": out.getvalue()}, status=400)
    except Exception as exc:  # noqa: BLE001
        return Response(
            {"error": f"{type(exc).__name__}: {exc}", "stdout": out.getvalue()},
            status=500,
        )
    return Response({"ok": True, "send": send, "stdout": out.getvalue()})
