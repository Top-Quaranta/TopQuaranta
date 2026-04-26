"""A8: API versioning — stamp the response header with the served version.

Currently every route under `/api/v1/*` returns `X-API-Version: 1`. When v2
arrives under `/api/v2/*` the same middleware will return `2` for those
routes. Clients that read the header can sanity-check they're talking to
the version they expected.

See docs/architecture/api-versioning.md for the policy and bump procedure.
"""

from typing import Callable

from django.http import HttpRequest, HttpResponse


class ApiVersionHeaderMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        path = request.path
        if path.startswith("/api/v1/"):
            response["X-API-Version"] = "1"
        elif path.startswith("/api/v2/"):
            response["X-API-Version"] = "2"
        return response
