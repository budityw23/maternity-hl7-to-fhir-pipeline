# Phase 6: Validation & Error Handling

## Objective

Add input validation, RFC 7807 problem+json error responses, HAPI error handling, and dead-letter file persistence. After this phase, invalid payloads get structured error responses, HAPI failures are caught and surfaced cleanly, and unprocessable messages are written to `./deadletter/` for inspection.

## Pre-conditions

- Phases 0-5 complete — all endpoints functional
- `deadletter/` directory exists with `.gitkeep`

## Tasks

Execute in order.

---

### Task 1: Create `fastapi/app/errors.py`

RFC 7807 problem+json error model and exception handler.

```python
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

DEADLETTER_DIR = os.environ.get("DEADLETTER_DIR", "./deadletter")


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
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")


def write_deadletter(
    payload: Any,
    error_detail: str,
    correlation_id: str | None = None,
) -> str | None:
    """Write failed payload to deadletter directory. Returns filename or None on failure."""
    try:
        os.makedirs(DEADLETTER_DIR, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        corr_suffix = f"_{correlation_id[:8]}" if correlation_id else ""
        filename = f"{timestamp}{corr_suffix}.json"
        filepath = os.path.join(DEADLETTER_DIR, filename)

        deadletter_content = {
            "timestamp": timestamp,
            "correlationId": correlation_id,
            "error": error_detail,
            "payload": payload,
        }

        with open(filepath, "w") as f:
            json.dump(deadletter_content, f, indent=2, default=str)

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
            errors.append({
                "field": loc,
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            })

        # Try to extract correlation ID from raw body
        correlation_id = None
        try:
            body_bytes = await request.body()
            body_json = json.loads(body_bytes)
            correlation_id = body_json.get("correlationId")
        except Exception:
            pass

        detail = f"Validation failed: {len(errors)} error(s)"
        logger.warning("Validation error correlationId=%s: %s", correlation_id, errors)

        write_deadletter(
            payload=str(body_bytes.decode("utf-8", errors="replace")) if "body_bytes" in dir() else None,
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
```

---

### Task 2: Update `fastapi/app/models/adt_payload.py`

Add field validators for required fields. MRN must be present and non-empty. Gender must be a valid HL7 code.

Add these validators to `AdtPayload`:

```python
from pydantic import BaseModel, Field, field_validator

# ... existing fields ...

class AdtPayload(BaseModel):
    # ... existing fields stay unchanged ...

    @field_validator("mrn")
    @classmethod
    def mrn_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("MRN is required and must not be empty")
        return v.strip()

    @field_validator("gender")
    @classmethod
    def gender_must_be_valid(cls, v: str) -> str:
        valid = {"F", "M", "O", "U", "A", "N", ""}
        if v.upper() not in valid:
            raise ValueError(f"Invalid gender code '{v}'. Must be one of: F, M, O, U, A, N")
        return v
```

---

### Task 3: Update `fastapi/app/models/orm_payload.py`

Add field validators. MRN and visitNumber required.

```python
from pydantic import BaseModel, field_validator

class OrmPayload(BaseModel):
    # ... existing fields stay unchanged ...

    @field_validator("mrn")
    @classmethod
    def mrn_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("MRN is required and must not be empty")
        return v.strip()

    @field_validator("visitNumber")
    @classmethod
    def visit_number_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Visit number is required and must not be empty")
        return v.strip()
```

---

### Task 4: Update `fastapi/app/models/oru_payload.py`

Add field validators. MRN required. Observations must have valid LOINC code and numeric value when valueType is NM.

```python
from pydantic import BaseModel, Field, field_validator

class ObservationPayload(BaseModel):
    # ... existing fields stay unchanged ...

    @field_validator("code")
    @classmethod
    def code_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Observation code (LOINC) is required")
        return v.strip()

    @field_validator("value")
    @classmethod
    def value_must_be_valid(cls, v: float | str) -> float | str:
        if isinstance(v, str) and not v.strip():
            raise ValueError("Observation value must not be empty")
        return v

class OruPayload(BaseModel):
    # ... existing fields stay unchanged ...

    @field_validator("mrn")
    @classmethod
    def mrn_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("MRN is required and must not be empty")
        return v.strip()
```

---

### Task 5: Update `fastapi/app/main.py`

1. Import and register error handlers.
2. Wrap HAPI client calls in try/except to catch `httpx.HTTPStatusError` and return problem+json with dead-letter.

Add import at top:

```python
from app.errors import problem_response, register_error_handlers, write_deadletter
```

Register handlers after app creation:

```python
app = FastAPI(...)
register_error_handlers(app)
```

Wrap each endpoint's HAPI calls. For example, in `transform_patient`:

```python
@app.post("/fhir/Patient")
async def transform_patient(payload: AdtPayload) -> dict[str, Any]:
    logger = logging.getLogger("app.fhir.patient")
    logger.info(
        "Processing ADT^A01 for MRN=%s correlationId=%s",
        payload.mrn,
        payload.correlationId,
    )

    try:
        patient = build_patient(payload)
        patient_data = _resource_to_json(patient)

        hapi = HapiClient(app.state.http_client)
        await hapi.ensure_au_patient_profile()
        identifier_query = f"{settings.mrn_system}|{payload.mrn}"
        patient_id = await hapi.upsert_resource("Patient", patient_data, identifier_query)

        logger.info(
            "Patient persisted id=%s correlationId=%s",
            patient_id,
            payload.correlationId,
        )

        condition_ids: list[str] = []
        if payload.diagnoses:
            patient_reference = f"Patient/{patient_id}"
            conditions = build_conditions(payload, patient_reference)
            for condition in conditions:
                condition_data = _resource_to_json(condition)
                condition_id = await hapi.create_resource("Condition", condition_data)
                condition_ids.append(condition_id)
                logger.info(
                    "Condition persisted id=%s correlationId=%s",
                    condition_id,
                    payload.correlationId,
                )

        return {
            "patientId": patient_id,
            "conditionIds": condition_ids,
            "correlationId": payload.correlationId,
        }

    except httpx.HTTPStatusError as exc:
        logger.error(
            "HAPI error correlationId=%s: %s %s",
            payload.correlationId,
            exc.response.status_code,
            exc.response.text,
        )
        write_deadletter(
            payload=payload.model_dump(mode="json"),
            error_detail=f"HAPI error: {exc.response.status_code}",
            correlation_id=payload.correlationId,
        )
        return problem_response(
            status=502,
            title="HAPI FHIR Error",
            detail=f"FHIR server returned {exc.response.status_code}",
            correlation_id=payload.correlationId,
        )
```

Apply the same try/except + dead-letter pattern to `transform_encounter` and `transform_observations`. Each catches `httpx.HTTPStatusError`, writes dead-letter, and returns `problem_response(502, ...)`.

**Important**: Change the return type annotation of all three endpoints from `-> dict[str, Any]` to `-> Any` to accommodate both dict and JSONResponse returns. Or use `response_model=None` on the route decorator instead.

---

### Task 6: Create `tests/unit/test_errors.py`

Test the error handling utilities.

```python
import json
import os
import tempfile

from app.errors import problem_response, write_deadletter


class TestProblemResponse:
    def test_status_code(self):
        resp = problem_response(422, "Validation Error", "Missing field")
        assert resp.status_code == 422

    def test_content_type(self):
        resp = problem_response(422, "Validation Error", "Missing field")
        assert resp.media_type == "application/problem+json"

    def test_body_structure(self):
        resp = problem_response(422, "Validation Error", "Missing field", correlation_id="abc-123")
        body = json.loads(resp.body)
        assert body["type"] == "about:blank"
        assert body["title"] == "Validation Error"
        assert body["status"] == 422
        assert body["detail"] == "Missing field"
        assert body["correlationId"] == "abc-123"

    def test_body_without_correlation_id(self):
        resp = problem_response(500, "Error", "Something broke")
        body = json.loads(resp.body)
        assert "correlationId" not in body

    def test_body_with_errors(self):
        errors = [{"field": "mrn", "message": "required"}]
        resp = problem_response(422, "Validation Error", "Bad input", errors=errors)
        body = json.loads(resp.body)
        assert len(body["errors"]) == 1
        assert body["errors"][0]["field"] == "mrn"


class TestWriteDeadletter:
    def test_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["DEADLETTER_DIR"] = tmpdir
            from app.errors import write_deadletter as wdl
            # Re-import to pick up env var — but DEADLETTER_DIR is read at call time
            filename = write_deadletter(
                payload={"mrn": "123"},
                error_detail="test error",
                correlation_id="corr-001",
            )
            assert filename is not None
            filepath = os.path.join(tmpdir, filename)
            assert os.path.exists(filepath)
            with open(filepath) as f:
                content = json.load(f)
            assert content["error"] == "test error"
            assert content["correlationId"] == "corr-001"
            assert content["payload"] == {"mrn": "123"}

    def test_filename_contains_correlation_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["DEADLETTER_DIR"] = tmpdir
            filename = write_deadletter(
                payload={},
                error_detail="err",
                correlation_id="abcdef12-rest-of-uuid",
            )
            assert "abcdef12" in filename

    def test_handles_no_correlation_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["DEADLETTER_DIR"] = tmpdir
            filename = write_deadletter(
                payload={},
                error_detail="err",
                correlation_id=None,
            )
            assert filename is not None
```

---

### Task 7: Create `tests/unit/test_validation.py`

Test that payload validators reject bad input.

```python
import pytest
from pydantic import ValidationError

from app.models.adt_payload import AdtPayload
from app.models.orm_payload import OrmPayload
from app.models.oru_payload import ObservationPayload, OruPayload


class TestAdtPayloadValidation:
    def _valid_adt(self, **overrides):
        defaults = {
            "correlationId": "test-uuid",
            "mrn": "1234567",
            "name": {"familyName": "Smith", "givenName": "Jane"},
            "birthDate": "19920315",
            "gender": "F",
        }
        defaults.update(overrides)
        return defaults

    def test_valid_payload(self):
        AdtPayload(**self._valid_adt())

    def test_empty_mrn_rejected(self):
        with pytest.raises(ValidationError, match="MRN"):
            AdtPayload(**self._valid_adt(mrn=""))

    def test_whitespace_mrn_rejected(self):
        with pytest.raises(ValidationError, match="MRN"):
            AdtPayload(**self._valid_adt(mrn="   "))

    def test_invalid_gender_rejected(self):
        with pytest.raises(ValidationError, match="gender"):
            AdtPayload(**self._valid_adt(gender="Z"))

    def test_empty_gender_accepted(self):
        p = AdtPayload(**self._valid_adt(gender=""))
        assert p.gender == ""

    def test_mrn_stripped(self):
        p = AdtPayload(**self._valid_adt(mrn=" 1234567 "))
        assert p.mrn == "1234567"


class TestOrmPayloadValidation:
    def _valid_orm(self, **overrides):
        defaults = {
            "correlationId": "test-uuid",
            "mrn": "1234567",
            "visitNumber": "VN00012",
            "patientClass": "O",
            "admitDatetime": "20260420090000",
            "location": {"ward": "Ward A"},
            "attendingDoctor": {"id": "DR1", "familyName": "Smith", "givenName": "John"},
            "orderControl": "NW",
        }
        defaults.update(overrides)
        return defaults

    def test_valid_payload(self):
        OrmPayload(**self._valid_orm())

    def test_empty_mrn_rejected(self):
        with pytest.raises(ValidationError, match="MRN"):
            OrmPayload(**self._valid_orm(mrn=""))

    def test_empty_visit_number_rejected(self):
        with pytest.raises(ValidationError, match="Visit number"):
            OrmPayload(**self._valid_orm(visitNumber=""))


class TestOruPayloadValidation:
    def _valid_obs(self, **overrides):
        defaults = {
            "setId": 1,
            "code": "29463-7",
            "display": "Body weight",
            "value": 68.5,
            "unitCode": "kg",
        }
        defaults.update(overrides)
        return defaults

    def test_valid_payload(self):
        OruPayload(correlationId="x", mrn="123", observations=[ObservationPayload(**self._valid_obs())])

    def test_empty_mrn_rejected(self):
        with pytest.raises(ValidationError, match="MRN"):
            OruPayload(correlationId="x", mrn="", observations=[])

    def test_empty_observation_code_rejected(self):
        with pytest.raises(ValidationError, match="code"):
            ObservationPayload(**self._valid_obs(code=""))

    def test_empty_string_value_rejected(self):
        with pytest.raises(ValidationError, match="value"):
            ObservationPayload(**self._valid_obs(value=""))
```

---

## Verification

```bash
# 1. Run all unit tests
venv/bin/python -m pytest tests/unit/ -v

# Expected: ~130+ tests (112 prior + ~18 new)

# 2. Rebuild FastAPI
docker compose up -d --build fastapi
sleep 10

# 3. Test RFC 7807 on missing required field
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d '{"correlationId":"bad-1","mrn":"","name":{"familyName":"X","givenName":"Y"},"birthDate":"19900101","gender":"F"}'

# Expected: 422 with application/problem+json content type:
# {"type":"about:blank","title":"Validation Error","status":422,...}

# 4. Test invalid gender
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d '{"correlationId":"bad-2","mrn":"999","name":{"familyName":"X","givenName":"Y"},"birthDate":"19900101","gender":"Z"}'

# Expected: 422 with validation error mentioning gender

# 5. Test missing body entirely
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d '{}'

# Expected: 422 with validation errors for required fields

# 6. Test ORM missing visit number
curl -s -X POST http://localhost:8000/fhir/Encounter \
  -H "Content-Type: application/json" \
  -d '{"correlationId":"bad-3","mrn":"123","visitNumber":"","patientClass":"O","admitDatetime":"20260101","location":{"ward":"W"},"attendingDoctor":{"id":"D","familyName":"S","givenName":"J"},"orderControl":"NW"}'

# Expected: 422 with visit number error

# 7. Check dead-letter directory has files
ls -la deadletter/

# Expected: .json files for each failed request

# 8. Inspect a dead-letter file
cat deadletter/*.json | python3 -m json.tool | head -20

# Expected: JSON with timestamp, correlationId, error, payload

# 9. Verify valid requests still work
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/adt_a01_payload.json

# Expected: 200 with patientId (unchanged from before)

# 10. Verify unhandled exception returns 500 problem+json (not HTML)
# This is hard to trigger intentionally — check by reviewing code
```

## Definition of Done

- [ ] `errors.py` provides `problem_response()` and `write_deadletter()` utilities
- [ ] All error responses use `application/problem+json` content type
- [ ] Error bodies conform to RFC 7807 (type, title, status, detail)
- [ ] Pydantic validation errors return 422 with structured error list
- [ ] HAPI failures return 502 with problem+json and write dead-letter
- [ ] Unhandled exceptions return 500 problem+json (no HTML stack traces)
- [ ] Dead-letter files written to `./deadletter/` with timestamp, correlationId, payload
- [ ] `AdtPayload.mrn` validated non-empty, `gender` validated against allowed codes
- [ ] `OrmPayload.mrn` and `visitNumber` validated non-empty
- [ ] `OruPayload.mrn` validated non-empty, `ObservationPayload.code` validated non-empty
- [ ] Valid payloads still processed normally (no regression)
- [ ] All prior tests still pass
