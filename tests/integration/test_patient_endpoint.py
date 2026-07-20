import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response

from app.main import app


def _hapi_mock():
    mock = respx.mock(base_url="http://localhost:8080/fhir", assert_all_called=False)

    mock.put("/StructureDefinition/au-patient").mock(
        return_value=Response(
            200, json={"resourceType": "StructureDefinition", "id": "au-patient"}
        )
    )
    mock.put("/Patient").mock(
        return_value=Response(
            201,
            json={"resourceType": "Patient", "id": "pat-1"},
            headers={"Location": "/Patient/pat-1/_history/1"},
        )
    )
    mock.post("/Condition").mock(
        return_value=Response(201, json={"resourceType": "Condition", "id": "cond-1"})
    )

    return mock


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


class TestPatientEndpoint:
    @pytest.mark.asyncio
    async def test_success_returns_patient_id(self):
        with _hapi_mock():
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/Patient",
                        json={
                            "correlationId": "int-test-001",
                            "mrn": "1234567",
                            "name": {"family": "Smith", "given": "Jane"},
                            "birthDate": "19920315",
                            "gender": "F",
                            "address": {
                                "line": "1 Test St",
                                "city": "Sydney",
                                "state": "NSW",
                                "postalCode": "2000",
                            },
                        },
                    )
        assert response.status_code == 200
        body = response.json()
        assert body["patientId"] == "pat-1"
        assert body["correlationId"] == "int-test-001"

    @pytest.mark.asyncio
    async def test_with_diagnosis_returns_condition_ids(self):
        with _hapi_mock():
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/Patient",
                        json={
                            "correlationId": "int-test-002",
                            "mrn": "1234567",
                            "name": {"family": "Smith", "given": "Jane"},
                            "birthDate": "19920315",
                            "gender": "F",
                            "address": {
                                "line": "1 Test St",
                                "city": "Sydney",
                                "state": "NSW",
                                "postalCode": "2000",
                            },
                            "diagnoses": [{"code": "O80", "display": "Normal delivery"}],
                        },
                    )
        assert response.status_code == 200
        body = response.json()
        assert body["conditionIds"] == ["cond-1"]

    @pytest.mark.asyncio
    async def test_empty_mrn_returns_422(self):
        async with app.router.lifespan_context(app):
            async with await _client() as client:
                response = await client.post(
                    "/fhir/Patient",
                    json={
                        "correlationId": "int-test-003",
                        "mrn": "",
                        "name": {"family": "Smith", "given": "Jane"},
                        "birthDate": "19920315",
                        "gender": "F",
                        "address": {
                            "line": "1 Test St",
                            "city": "Sydney",
                            "state": "NSW",
                            "postalCode": "2000",
                        },
                    },
                )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"

    @pytest.mark.asyncio
    async def test_invalid_gender_returns_422(self):
        async with app.router.lifespan_context(app):
            async with await _client() as client:
                response = await client.post(
                    "/fhir/Patient",
                    json={
                        "correlationId": "int-test-004",
                        "mrn": "1234567",
                        "name": {"family": "Smith", "given": "Jane"},
                        "birthDate": "19920315",
                        "gender": "Z",
                        "address": {
                            "line": "1 Test St",
                            "city": "Sydney",
                            "state": "NSW",
                            "postalCode": "2000",
                        },
                    },
                )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_correlation_id_in_response_header(self):
        with _hapi_mock():
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/Patient",
                        json={
                            "correlationId": "int-test-005",
                            "mrn": "1234567",
                            "name": {"family": "Smith", "given": "Jane"},
                            "birthDate": "19920315",
                            "gender": "F",
                            "address": {
                                "line": "1 Test St",
                                "city": "Sydney",
                                "state": "NSW",
                                "postalCode": "2000",
                            },
                        },
                        headers={"X-Correlation-ID": "my-corr-id"},
                    )
        assert response.headers.get("X-Correlation-ID") == "my-corr-id"
