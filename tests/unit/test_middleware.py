import uuid

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.logging_setup import correlation_id_var
from app.middleware import CorrelationIdMiddleware


def _request(correlation_id: str | None = None) -> Request:
    headers = []
    if correlation_id is not None:
        headers.append((b"x-correlation-id", correlation_id.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": headers,
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


class TestCorrelationIdMiddleware:
    @pytest.mark.asyncio
    async def test_generates_correlation_id_when_missing(self):
        middleware = CorrelationIdMiddleware(app=None)

        async def call_next(request: Request) -> JSONResponse:
            return JSONResponse({"correlationId": correlation_id_var.get("")})

        response = await middleware.dispatch(_request(), call_next)
        corr_id = response.headers.get("X-Correlation-ID")
        assert corr_id is not None
        uuid.UUID(corr_id)

    @pytest.mark.asyncio
    async def test_uses_provided_correlation_id(self):
        middleware = CorrelationIdMiddleware(app=None)

        async def call_next(request: Request) -> JSONResponse:
            return JSONResponse({"correlationId": correlation_id_var.get("")})

        response = await middleware.dispatch(_request("my-corr-id"), call_next)
        assert response.headers["X-Correlation-ID"] == "my-corr-id"
        assert response.body == b'{"correlationId":"my-corr-id"}'

    @pytest.mark.asyncio
    async def test_correlation_id_in_response_header(self):
        middleware = CorrelationIdMiddleware(app=None)

        async def call_next(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        response = await middleware.dispatch(_request(), call_next)
        assert "X-Correlation-ID" in response.headers

    @pytest.mark.asyncio
    async def test_context_var_set_in_endpoint(self):
        middleware = CorrelationIdMiddleware(app=None)

        async def call_next(request: Request) -> JSONResponse:
            return JSONResponse({"correlationId": correlation_id_var.get("")})

        response = await middleware.dispatch(_request("ctx-test"), call_next)
        assert response.body == b'{"correlationId":"ctx-test"}'
