# Phase 8: Testing — Integration Tests, CI Pipeline, Coverage

## Objective

Add integration tests (using FastAPI TestClient against real FHIR resource construction), fix CI pipeline for GitHub Actions, add pytest-cov for coverage measurement, and reach ≥80% coverage. Also fix any mypy/ruff issues so CI goes green.

**Integration tests run without Docker** — they test the full FastAPI request/response cycle using TestClient with HAPI calls mocked via `httpx` respx or manual monkeypatch. This keeps CI fast and Docker-free while still testing endpoint wiring, validation, serialization, and error handling end-to-end.

## Pre-conditions

- Phases 0-7 complete — 144 unit tests passing
- CI workflow exists at `.github/workflows/ci.yml` (skeleton)
- `pyproject.toml` has dev dependencies

## Tasks

Execute in order.

---

### Task 1: Add `pytest-cov` and `respx` to dev dependencies

Update `fastapi/pyproject.toml` dev dependencies:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "respx>=0.21",
    "ruff>=0.5.0",
    "mypy>=1.10",
]
```

Install in venv:

```bash
venv/bin/pip install "fastapi/.[dev]"
```

---

### Task 2: Create `tests/integration/test_patient_endpoint.py`

Test the `/fhir/Patient` endpoint through TestClient with HAPI mocked.

```python
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.main import app


def _hapi_mock():
    """Set up respx routes for HAPI FHIR mock responses."""
    mock = respx.mock(base_url="http://localhost:8080/fhir")

    # Profile seeding
    mock.put("/StructureDefinition/au-patient").mock(
        return_value=Response(200, json={"resourceType": "StructureDefinition", "id": "au-patient"})
    )

    # Patient upsert — conditional PUT
    mock.put("/Patient", params__contains={"identifier": True}).mock(
        return_value=Response(201, json={"resourceType": "Patient", "id": "pat-1"}, headers={"Location": "/Patient/pat-1/_history/1"})
    )

    # Condition create
    mock.post("/Condition").mock(
        return_value=Response(201, json={"resourceType": "Condition", "id": "cond-1"})
    )

    return mock


class TestPatientEndpoint:
    def test_success_returns_patient_id(self):
        with _hapi_mock():
            client = TestClient(app)
            response = client.post(
                "/fhir/Patient",
                json={
                    "correlationId": "int-test-001",
                    "mrn": "1234567",
                    "name": {"family": "Smith", "given": "Jane"},
                    "birthDate": "19920315",
                    "gender": "F",
                    "address": {"line": "1 Test St", "city": "Sydney", "state": "NSW", "postalCode": "2000"},
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert "patientId" in body
        assert body["correlationId"] == "int-test-001"

    def test_with_diagnosis_returns_condition_ids(self):
        with _hapi_mock():
            client = TestClient(app)
            response = client.post(
                "/fhir/Patient",
                json={
                    "correlationId": "int-test-002",
                    "mrn": "1234567",
                    "name": {"family": "Smith", "given": "Jane"},
                    "birthDate": "19920315",
                    "gender": "F",
                    "address": {"line": "1 Test St", "city": "Sydney", "state": "NSW", "postalCode": "2000"},
                    "diagnoses": [{"code": "O80", "display": "Normal delivery"}],
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert len(body["conditionIds"]) == 1

    def test_empty_mrn_returns_422(self):
        client = TestClient(app)
        response = client.post(
            "/fhir/Patient",
            json={
                "correlationId": "int-test-003",
                "mrn": "",
                "name": {"family": "Smith", "given": "Jane"},
                "birthDate": "19920315",
                "gender": "F",
                "address": {"line": "1 Test St", "city": "Sydney", "state": "NSW", "postalCode": "2000"},
            },
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"

    def test_invalid_gender_returns_422(self):
        client = TestClient(app)
        response = client.post(
            "/fhir/Patient",
            json={
                "correlationId": "int-test-004",
                "mrn": "1234567",
                "name": {"family": "Smith", "given": "Jane"},
                "birthDate": "19920315",
                "gender": "Z",
                "address": {"line": "1 Test St", "city": "Sydney", "state": "NSW", "postalCode": "2000"},
            },
        )
        assert response.status_code == 422

    def test_correlation_id_in_response_header(self):
        with _hapi_mock():
            client = TestClient(app)
            response = client.post(
                "/fhir/Patient",
                json={
                    "correlationId": "int-test-005",
                    "mrn": "1234567",
                    "name": {"family": "Smith", "given": "Jane"},
                    "birthDate": "19920315",
                    "gender": "F",
                    "address": {"line": "1 Test St", "city": "Sydney", "state": "NSW", "postalCode": "2000"},
                },
                headers={"X-Correlation-ID": "my-corr-id"},
            )
        assert response.headers.get("X-Correlation-ID") == "my-corr-id"
```

---

### Task 3: Create `tests/integration/test_encounter_endpoint.py`

```python
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.main import app


def _hapi_mock_with_patient():
    """Mock HAPI with existing patient for encounter tests."""
    mock = respx.mock(base_url="http://localhost:8080/fhir")

    # Patient lookup by MRN
    mock.get("/Patient", params__contains={"identifier": True}).mock(
        return_value=Response(200, json={
            "resourceType": "Bundle",
            "total": 1,
            "entry": [{"resource": {"resourceType": "Patient", "id": "pat-1"}}],
        })
    )

    # Encounter upsert
    mock.put("/Encounter", params__contains={"identifier": True}).mock(
        return_value=Response(201, json={"resourceType": "Encounter", "id": "enc-1"})
    )

    return mock


def _hapi_mock_no_patient():
    mock = respx.mock(base_url="http://localhost:8080/fhir")
    mock.get("/Patient", params__contains={"identifier": True}).mock(
        return_value=Response(200, json={"resourceType": "Bundle", "total": 0, "entry": []})
    )
    return mock


class TestEncounterEndpoint:
    def _valid_payload(self, **overrides):
        defaults = {
            "correlationId": "int-enc-001",
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

    def test_success_returns_encounter_id(self):
        with _hapi_mock_with_patient():
            client = TestClient(app)
            response = client.post("/fhir/Encounter", json=self._valid_payload())
        assert response.status_code == 200
        body = response.json()
        assert "encounterId" in body

    def test_missing_patient_returns_422(self):
        with _hapi_mock_no_patient():
            client = TestClient(app)
            response = client.post("/fhir/Encounter", json=self._valid_payload())
        assert response.status_code == 422
        body = response.json()
        assert "Patient not found" in body["detail"]

    def test_empty_visit_number_returns_422(self):
        client = TestClient(app)
        response = client.post("/fhir/Encounter", json=self._valid_payload(visitNumber=""))
        assert response.status_code == 422

    def test_empty_mrn_returns_422(self):
        client = TestClient(app)
        response = client.post("/fhir/Encounter", json=self._valid_payload(mrn=""))
        assert response.status_code == 422
```

---

### Task 4: Create `tests/integration/test_observation_endpoint.py`

```python
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.main import app


def _hapi_mock_full():
    """Mock HAPI with patient, encounter, and observation support."""
    mock = respx.mock(base_url="http://localhost:8080/fhir")

    # Patient lookup
    mock.get("/Patient", params__contains={"identifier": True}).mock(
        return_value=Response(200, json={
            "resourceType": "Bundle",
            "total": 1,
            "entry": [{"resource": {"resourceType": "Patient", "id": "pat-1"}}],
        })
    )

    # Encounter lookup
    mock.get("/Encounter", params__contains={"identifier": True}).mock(
        return_value=Response(200, json={
            "resourceType": "Bundle",
            "total": 1,
            "entry": [{"resource": {"resourceType": "Encounter", "id": "enc-1"}}],
        })
    )

    # BP profile seeding
    mock.put("/StructureDefinition/au-vitalsigns-bloodpressure").mock(
        return_value=Response(200, json={"resourceType": "StructureDefinition", "id": "au-vitalsigns-bloodpressure"})
    )

    # Observation create
    observation_counter = {"n": 0}

    def _obs_response(request):
        observation_counter["n"] += 1
        return Response(201, json={"resourceType": "Observation", "id": f"obs-{observation_counter['n']}"})

    mock.post("/Observation").mock(side_effect=_obs_response)

    return mock


def _hapi_mock_no_patient():
    mock = respx.mock(base_url="http://localhost:8080/fhir")
    mock.get("/Patient", params__contains={"identifier": True}).mock(
        return_value=Response(200, json={"resourceType": "Bundle", "total": 0, "entry": []})
    )
    return mock


class TestObservationEndpoint:
    def _valid_payload(self, observations=None):
        return {
            "correlationId": "int-obs-001",
            "mrn": "1234567",
            "visitNumber": "VN00012",
            "observations": observations or [
                {"setId": 1, "code": "29463-7", "display": "Body weight", "value": 68.5, "unitCode": "kg", "status": "F"},
            ],
        }

    def test_simple_observation_success(self):
        with _hapi_mock_full():
            client = TestClient(app)
            response = client.post("/fhir/Observation/bundle", json=self._valid_payload())
        assert response.status_code == 200
        body = response.json()
        assert len(body["observationIds"]) == 1

    def test_bp_panel_merging(self):
        observations = [
            {"setId": 1, "code": "8480-6", "display": "Systolic BP", "value": 120, "unitCode": "mm[Hg]", "status": "F"},
            {"setId": 2, "code": "8462-4", "display": "Diastolic BP", "value": 80, "unitCode": "mm[Hg]", "status": "F"},
            {"setId": 3, "code": "29463-7", "display": "Body weight", "value": 68.5, "unitCode": "kg", "status": "F"},
        ]
        with _hapi_mock_full():
            client = TestClient(app)
            response = client.post("/fhir/Observation/bundle", json=self._valid_payload(observations))
        assert response.status_code == 200
        body = response.json()
        assert len(body["observationIds"]) == 2  # 1 BP panel + 1 weight

    def test_empty_observations_returns_empty(self):
        with _hapi_mock_full():
            client = TestClient(app)
            response = client.post("/fhir/Observation/bundle", json=self._valid_payload(observations=[]))
        assert response.status_code == 200
        body = response.json()
        assert body["observationIds"] == []

    def test_missing_patient_returns_422(self):
        with _hapi_mock_no_patient():
            client = TestClient(app)
            response = client.post("/fhir/Observation/bundle", json=self._valid_payload())
        assert response.status_code == 422

    def test_empty_mrn_returns_422(self):
        client = TestClient(app)
        payload = self._valid_payload()
        payload["mrn"] = ""
        response = client.post("/fhir/Observation/bundle", json=payload)
        assert response.status_code == 422
```

---

### Task 5: Create `tests/integration/test_health_endpoint.py`

```python
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.main import app


class TestHealthEndpoint:
    def test_health_hapi_up(self):
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.get("/metadata").mock(return_value=Response(200, json={"resourceType": "CapabilityStatement"}))
            client = TestClient(app)
            response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["hapi"] == "up"

    def test_health_hapi_down(self):
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.get("/metadata").mock(return_value=Response(503))
            client = TestClient(app)
            response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["hapi"] == "down"

    def test_health_returns_version(self):
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.get("/metadata").mock(return_value=Response(200, json={}))
            client = TestClient(app)
            response = client.get("/health")
        body = response.json()
        assert body["version"] == "0.1.0"

    def test_health_has_correlation_id_header(self):
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.get("/metadata").mock(return_value=Response(200, json={}))
            client = TestClient(app)
            response = client.get("/health")
        assert "X-Correlation-ID" in response.headers
```

---

### Task 6: Update CI workflow `.github/workflows/ci.yml`

Fix CI to work with project layout (tests/ is at project root, app/ is under fastapi/). Add coverage reporting.

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        working-directory: ./fastapi
        run: pip install ".[dev]"

      - name: Lint with ruff
        working-directory: ./fastapi
        run: ruff check app/

      - name: Lint tests with ruff
        run: ruff check tests/

      - name: Type check with mypy
        working-directory: ./fastapi
        run: mypy app/ --ignore-missing-imports

      - name: Run tests with coverage
        run: |
          cd "$GITHUB_WORKSPACE"
          python -m pytest tests/ -v --cov=fastapi/app --cov-report=term-missing --cov-fail-under=80
```

**Key changes from skeleton:**
- Trigger on both `main` and `master` branches
- Tests run from project root (not fastapi/ working dir) since conftest.py handles sys.path
- Coverage measured against `fastapi/app/` source
- `--cov-fail-under=80` enforces 80% minimum
- `--ignore-missing-imports` for mypy (third-party stubs may be missing in CI)
- Ruff lints tests/ separately from project root

---

### Task 7: Add pytest-cov configuration to `pyproject.toml`

Add coverage config section:

```toml
[tool.coverage.run]
source = ["app"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if __name__",
    "if TYPE_CHECKING",
]
show_missing = true
```

---

## Verification

```bash
# 1. Install new dev dependencies
venv/bin/pip install "fastapi/.[dev]"

# 2. Run all tests with coverage
venv/bin/python -m pytest tests/ -v --cov=fastapi/app --cov-report=term-missing --cov-fail-under=80

# Expected: ~160+ tests (144 unit + ~18 integration), ≥80% coverage

# 3. Run ruff on all code
venv/bin/ruff check fastapi/app/ tests/

# Expected: No errors

# 4. Run mypy
cd fastapi && ../venv/bin/mypy app/ --ignore-missing-imports; cd ..

# Expected: No errors (or only third-party stub warnings)

# 5. Verify integration tests work independently
venv/bin/python -m pytest tests/integration/ -v

# Expected: All integration tests pass without Docker running
```

## Definition of Done

- [ ] `pytest-cov` and `respx` added to dev dependencies
- [ ] Integration tests for all 4 endpoints: health, Patient, Encounter, Observation
- [ ] Integration tests cover: happy path, validation errors, missing prerequisites, BP merging
- [ ] Integration tests run without Docker (HAPI mocked via respx)
- [ ] Coverage ≥80% across `fastapi/app/`
- [ ] CI workflow triggers on push/PR to main and master
- [ ] CI runs: ruff lint, mypy type check, pytest with coverage
- [ ] `--cov-fail-under=80` enforces coverage minimum in CI
- [ ] All 144 existing unit tests still pass
- [ ] No ruff errors

## Notes

- Integration tests use `respx` to mock httpx requests to HAPI. This tests the full FastAPI → transformer → HAPI client pipeline without requiring a running HAPI server.
- The `TestClient` from FastAPI/Starlette handles the ASGI lifecycle, so middleware (correlation ID) is also exercised.
- Coverage may need attention on error paths in `hapi_client.py` and edge cases in transformers — add targeted tests if under 80%.
