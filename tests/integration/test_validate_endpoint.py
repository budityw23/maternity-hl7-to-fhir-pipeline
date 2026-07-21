"""Integration tests for /fhir/validate/{resource_type} endpoint."""

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response

from app.main import app


def _hapi_validate_mock(valid: bool = True) -> respx.MockRouter:
    mock = respx.mock(base_url="http://localhost:8080/fhir", assert_all_called=False)
    if valid:
        outcome = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "information", "diagnostics": "All OK"}],
        }
    else:
        outcome = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "diagnostics": "Patient.name: minimum required = 1",
                }
            ],
        }
    mock.post("/Patient/$validate").mock(return_value=Response(200, json=outcome))
    return mock


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


class TestValidateEndpoint:
    @pytest.mark.asyncio
    async def test_valid_resource_returns_outcome(self) -> None:
        with _hapi_validate_mock(valid=True):
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/validate/Patient",
                        json={"resourceType": "Patient", "name": [{"family": "Test"}]},
                    )

        assert response.status_code == 200
        body = response.json()
        assert body["resourceType"] == "OperationOutcome"

    @pytest.mark.asyncio
    async def test_invalid_resource_returns_errors(self) -> None:
        with _hapi_validate_mock(valid=False):
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/validate/Patient",
                        json={"resourceType": "Patient"},
                    )

        assert response.status_code == 200
        body = response.json()
        errors = [issue for issue in body["issue"] if issue["severity"] == "error"]
        assert errors
