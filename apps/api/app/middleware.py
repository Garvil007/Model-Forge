"""Request body size limit.

Every route here is JSON-only — the only large binary payloads in the product (model and
dataset files) go direct-to-S3 via presigned URLs and are never read by the API (see root
CLAUDE.md). Behind API Gateway's Lambda proxy integration the body is already capped at
API Gateway's own hard 10 MB limit before this code ever runs, but the local dev server
(`uvicorn`, see CLAUDE.md's `make api`) has no such cap, and rejecting an oversized body
by its declared `Content-Length` up front (rather than after FastAPI has parsed it) keeps
a stray huge request from reaching Pydantic validation or jsonschema at all.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB — generous for the largest JSON body (job params)


class MaxBodySizeMiddleware:
    """Plain ASGI middleware (not BaseHTTPMiddleware) so it can run ahead of all routing
    and dependency resolution with no extra buffering of the request body."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self._app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = None
            if declared_size is not None and declared_size > MAX_BODY_BYTES:
                response: Response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": "Request body is too large.",
                        }
                    },
                )
                await response(scope, receive, send)
                return

        await self._app(scope, receive, send)
