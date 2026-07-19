import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logging_setup import correlation_id_var

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate correlation ID for every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        corr_id = request.headers.get(CORRELATION_HEADER, "")
        if not corr_id:
            corr_id = str(uuid.uuid4())

        token = correlation_id_var.set(corr_id)
        try:
            response = await call_next(request)
            response.headers[CORRELATION_HEADER] = corr_id
            return response
        finally:
            correlation_id_var.reset(token)
