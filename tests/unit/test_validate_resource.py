"""Tests for HapiClient.validate_resource()."""

import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient, Response

from app.clients.hapi_client import HapiClient


@pytest_asyncio.fixture
async def http_client() -> AsyncClient:
    async with AsyncClient() as client:
        yield client


class TestValidateResource:
    @pytest.mark.asyncio
    async def test_valid_resource_returns_none(self, http_client: AsyncClient) -> None:
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.post("/Patient/$validate").mock(
                return_value=Response(
                    200,
                    json={
                        "resourceType": "OperationOutcome",
                        "issue": [
                            {"severity": "information", "diagnostics": "All OK"}
                        ],
                    },
                )
            )
            hapi = HapiClient(http_client)
            result = await hapi.validate_resource(
                "Patient", {"resourceType": "Patient"}
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_resource_returns_outcome(self, http_client: AsyncClient) -> None:
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.post("/Patient/$validate").mock(
                return_value=Response(
                    200,
                    json={
                        "resourceType": "OperationOutcome",
                        "issue": [
                            {
                                "severity": "error",
                                "diagnostics": "Patient.name: minimum required = 1",
                            }
                        ],
                    },
                )
            )
            hapi = HapiClient(http_client)
            result = await hapi.validate_resource(
                "Patient", {"resourceType": "Patient"}
            )

        assert result is not None
        assert result["resourceType"] == "OperationOutcome"
        assert any(issue["severity"] == "error" for issue in result["issue"])

    @pytest.mark.asyncio
    async def test_hapi_error_returns_none(self, http_client: AsyncClient) -> None:
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.post("/Patient/$validate").mock(
                return_value=Response(500, text="Internal Server Error")
            )
            hapi = HapiClient(http_client)
            result = await hapi.validate_resource(
                "Patient", {"resourceType": "Patient"}
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_warnings_only_returns_none(self, http_client: AsyncClient) -> None:
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.post("/Patient/$validate").mock(
                return_value=Response(
                    200,
                    json={
                        "resourceType": "OperationOutcome",
                        "issue": [
                            {
                                "severity": "warning",
                                "diagnostics": "Terminology server unreachable",
                            }
                        ],
                    },
                )
            )
            hapi = HapiClient(http_client)
            result = await hapi.validate_resource(
                "Patient", {"resourceType": "Patient"}
            )

        assert result is None
