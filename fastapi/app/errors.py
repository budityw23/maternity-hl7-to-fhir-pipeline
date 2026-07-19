import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

DEFAULT_DEADLETTER_DIR = "./deadletter"


def problem_response(
    status: int,
    title: str,
    detail: str,
    correlation_id: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Build an RFC 7807 problem+json response."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
    }
    if correlation_id:
        body["correlationId"] = correlation_id
    if errors:
        body["errors"] = errors
    return JSONResponse(
        status_code=status,
        content=body,
        media_type="application/problem+json",
    )


def write_deadletter(
    payload: Any,
    error_detail: str,
    correlation_id: str | None = None,
) -> str | None:
    """Write failed payload to deadletter directory. Returns filename or None on failure."""
    try:
        deadletter_dir = os.environ.get("DEADLETTER_DIR", DEFAULT_DEADLETTER_DIR)
        os.makedirs(deadletter_dir, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        corr_suffix = f"_{correlation_id[:8]}" if correlation_id else ""
        filename = f"{timestamp}{corr_suffix}.json"
        filepath = os.path.join(deadletter_dir, filename)

        deadletter_content = {
            "timestamp": timestamp,
            "correlationId": correlation_id,
            "error": error_detail,
            "payload": payload,
        }

        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(deadletter_content, file, indent=2, default=str)

        logger.info("Dead-letter written: %s", filename)
        return filename
    except Exception:
        logger.exception("Failed to write dead-letter file")
        return None


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", []))
            errors.append(
                {
                    "field": loc,
                    "message": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
            )

        body_bytes = b""
        correlation_id = None
        payload: Any = None
        try:
            body_bytes = await request.body()
            payload = body_bytes.decode("utf-8", errors="replace")
            body_json = json.loads(body_bytes)
            if isinstance(body_json, dict):
                correlation_id = body_json.get("correlationId")
        except Exception:
            payload = body_bytes.decode("utf-8", errors="replace") if body_bytes else None

        detail = f"Validation failed: {len(errors)} error(s)"
        logger.warning("Validation error correlationId=%s: %s", correlation_id, errors)

        write_deadletter(
            payload=payload,
            error_detail=detail,
            correlation_id=correlation_id,
        )

        return problem_response(
            status=422,
            title="Validation Error",
            detail=detail,
            correlation_id=correlation_id,
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return problem_response(
            status=exc.status_code,
            title="Error",
            detail=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return problem_response(
            status=500,
            title="Internal Server Error",
            detail="An unexpected error occurred. Check server logs.",
        )
