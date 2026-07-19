# Phase 7: Structured JSON Logging & Correlation ID Propagation

## Objective

Replace Python's default text logging with structured JSON logging (one JSON object per line). Propagate a `X-Correlation-ID` header through all requests — generated if not provided. Every log line includes the correlation ID. No PHI (names, DOB) at INFO level.

After this phase, log output is machine-parseable, correlation IDs trace requests end-to-end, and logs are safe for aggregation without PHI exposure.

## Pre-conditions

- Phase 6 complete — error handling in place
- `app/logging_setup.py` does not exist yet
- `app/config.py` has `log_level` setting

## Design

- **JSON formatter**: Custom `logging.Formatter` that outputs `{"timestamp", "level", "logger", "message", "correlationId", ...}` per line
- **Correlation middleware**: FastAPI middleware that reads `X-Correlation-ID` from request header, generates UUID4 if missing, stores in `contextvars.ContextVar`, sets on response header
- **Context-aware logging**: JSON formatter reads correlation ID from context var
- **Log levels**: INFO for happy path (resource IDs only), WARN for validation degradations, ERROR for failures
- **No PHI**: Never log patient name, DOB, address, phone at INFO. Only identifiers (MRN, IHI) at INFO.

## Tasks

Execute in order.

---

### Task 1: Create `fastapi/app/logging_setup.py`

Structured JSON logging configuration with correlation ID support.

```python
import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter with correlation ID from context."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlationId": correlation_id_var.get(""),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with JSON formatter writing to stdout."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicate output
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
```

---

### Task 2: Create `fastapi/app/middleware.py`

Correlation ID middleware that reads/generates correlation ID and sets it in context.

```python
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
        # Read from header or generate new
        corr_id = request.headers.get(CORRELATION_HEADER, "")
        if not corr_id:
            corr_id = str(uuid.uuid4())

        # Set in context var for logging
        token = correlation_id_var.set(corr_id)
        try:
            response = await call_next(request)
            response.headers[CORRELATION_HEADER] = corr_id
            return response
        finally:
            correlation_id_var.reset(token)
```

---

### Task 3: Update `fastapi/app/main.py`

1. Import and call `setup_logging` at module level (before app creation).
2. Add correlation middleware to app.
3. Update endpoint loggers to use the context correlation ID (they already log correlation from payload — keep that, but the JSON formatter now also adds it from context).

Add imports:

```python
from app.logging_setup import setup_logging
from app.middleware import CorrelationIdMiddleware
```

Add before app creation:

```python
setup_logging(settings.log_level)
```

Add after `register_error_handlers(app)`:

```python
app.add_middleware(CorrelationIdMiddleware)
```

The endpoint code does NOT need changes — it already logs `correlationId` from the payload. The middleware ensures the JSON formatter also includes it from the context var. The middleware correlation ID (from header) and payload correlation ID (from JSON body) may differ — that's fine, both are useful.

---

### Task 4: Update `fastapi/app/errors.py`

Import and use `correlation_id_var` from logging_setup so that error handlers also have access to the correlation ID from the middleware context (in case payload parsing failed and we don't have a body-level correlationId).

Add import:

```python
from app.logging_setup import correlation_id_var
```

In `validation_error_handler`, after trying to extract `correlation_id` from body, fall back to context:

```python
        # Fall back to middleware correlation ID if body parse failed
        if not correlation_id:
            ctx_corr = correlation_id_var.get("")
            if ctx_corr:
                correlation_id = ctx_corr
```

In `unhandled_exception_handler`, include correlation ID from context:

```python
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        corr_id = correlation_id_var.get("")
        logger.exception("Unhandled exception correlationId=%s: %s", corr_id, exc)
        return problem_response(
            status=500,
            title="Internal Server Error",
            detail="An unexpected error occurred. Check server logs.",
            correlation_id=corr_id or None,
        )
```

---

### Task 5: Create `tests/unit/test_logging.py`

Test the JSON formatter and correlation ID context.

```python
import json
import logging

from app.logging_setup import JsonFormatter, correlation_id_var, setup_logging


class TestJsonFormatter:
    def test_output_is_valid_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "test message"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"

    def test_includes_correlation_id_from_context(self):
        formatter = JsonFormatter()
        token = correlation_id_var.set("abc-123")
        try:
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="test", args=(), exc_info=None,
            )
            output = formatter.format(record)
            parsed = json.loads(output)
            assert parsed["correlationId"] == "abc-123"
        finally:
            correlation_id_var.reset(token)

    def test_empty_correlation_id_when_not_set(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["correlationId"] == ""

    def test_includes_timestamp(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed

    def test_includes_exception(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="", lineno=0,
                msg="error", args=(), exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "ValueError: boom" in parsed["exception"]


class TestSetupLogging:
    def test_sets_root_level(self):
        setup_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG
        setup_logging("INFO")  # Reset

    def test_suppresses_uvicorn_access(self):
        setup_logging("INFO")
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
```

---

### Task 6: Create `tests/unit/test_middleware.py`

Test the correlation ID middleware with a test FastAPI client.

```python
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.logging_setup import correlation_id_var
from app.middleware import CorrelationIdMiddleware


def _make_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(CorrelationIdMiddleware)

    @test_app.get("/test")
    async def test_endpoint():
        return {"correlationId": correlation_id_var.get("")}

    return test_app


class TestCorrelationIdMiddleware:
    def test_generates_correlation_id_when_missing(self):
        client = TestClient(_make_app())
        response = client.get("/test")
        assert response.status_code == 200
        corr_id = response.headers.get("X-Correlation-ID")
        assert corr_id is not None
        uuid.UUID(corr_id)  # Should not raise — valid UUID

    def test_uses_provided_correlation_id(self):
        client = TestClient(_make_app())
        response = client.get("/test", headers={"X-Correlation-ID": "my-corr-id"})
        assert response.headers["X-Correlation-ID"] == "my-corr-id"
        body = response.json()
        assert body["correlationId"] == "my-corr-id"

    def test_correlation_id_in_response_header(self):
        client = TestClient(_make_app())
        response = client.get("/test")
        assert "X-Correlation-ID" in response.headers

    def test_context_var_set_in_endpoint(self):
        client = TestClient(_make_app())
        response = client.get("/test", headers={"X-Correlation-ID": "ctx-test"})
        body = response.json()
        assert body["correlationId"] == "ctx-test"
```

---

## Verification

```bash
# 1. Run all unit tests
venv/bin/python -m pytest tests/unit/ -v

# Expected: ~145+ tests (133 prior + ~12 new)

# 2. Rebuild FastAPI
docker compose up -d --build fastapi
sleep 10

# 3. Send request WITHOUT correlation ID — should get auto-generated one back
curl -s -i -X GET http://localhost:8000/health

# Expected: Response includes X-Correlation-ID header with UUID4

# 4. Send request WITH correlation ID — should echo it back
curl -s -i -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: test-corr-123" \
  -d @tests/fixtures/adt_a01_payload.json

# Expected: Response includes X-Correlation-ID: test-corr-123

# 5. Check Docker logs for JSON format
docker compose logs fastapi --tail=20

# Expected: Each log line is a JSON object like:
# {"timestamp":"...","level":"INFO","logger":"app.fhir.patient","message":"Processing ADT^A01 ...","correlationId":"test-corr-123"}

# 6. Verify no PHI in INFO logs
docker compose logs fastapi --tail=50 | grep -i "smith\|jane\|19920315\|123 Main"

# Expected: No matches (names, DOB, address not logged at INFO)

# 7. Trigger validation error and check error response has correlation ID from middleware
curl -s -i -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: err-corr-456" \
  -d '{"mrn":"","gender":"F"}'

# Expected: 422 response with correlationId in problem+json body
# X-Correlation-ID: err-corr-456 in response header
```

## Definition of Done

- [ ] All log output is JSON (one object per line)
- [ ] Each log entry has: timestamp, level, logger, message, correlationId
- [ ] `X-Correlation-ID` header read from request; UUID4 generated if missing
- [ ] `X-Correlation-ID` returned in all response headers
- [ ] Correlation ID available in context var for logging and error handlers
- [ ] Error responses include correlation ID (from body or middleware context)
- [ ] No PHI (names, DOB, address, phone) in INFO-level logs
- [ ] Noisy third-party loggers (uvicorn.access, httpx, httpcore) suppressed
- [ ] Exception stack traces included in ERROR-level JSON logs
- [ ] All prior tests still pass
- [ ] `setup_logging()` called before app creation
