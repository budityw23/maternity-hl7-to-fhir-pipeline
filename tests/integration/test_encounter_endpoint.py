import pytest
import respx
from app.main import app
from httpx import ASGITransport, AsyncClient, Response


def _hapi_mock_with_patient():
    mock = respx.mock(base_url="http://localhost:8080/fhir", assert_all_called=False)
    mock.get("/Patient").mock(
        return_value=Response(
            200,
            json={
                "resourceType": "Bundle",
                "total": 1,
                "entry": [{"resource": {"resourceType": "Patient", "id": "pat-1"}}],
            },
        )
    )
    mock.put("/StructureDefinition/patient-eu").mock(
        return_value=Response(
            200, json={"resourceType": "StructureDefinition", "id": "patient-eu"}
        )
    )
    mock.put("/StructureDefinition/condition-eu-core").mock(
        return_value=Response(
            200,
            json={"resourceType": "StructureDefinition", "id": "condition-eu-core"},
        )
    )
    mock.put("/StructureDefinition/fhir-bp").mock(
        return_value=Response(
            200, json={"resourceType": "StructureDefinition", "id": "fhir-bp"}
        )
    )
    mock.put("/StructureDefinition/au-encounter").mock(
        return_value=Response(
            200, json={"resourceType": "StructureDefinition", "id": "au-encounter"}
        )
    )
    mock.put("/StructureDefinition/au-patient").mock(
        return_value=Response(
            200, json={"resourceType": "StructureDefinition", "id": "au-patient"}
        )
    )
    mock.put("/StructureDefinition/au-condition").mock(
        return_value=Response(
            200, json={"resourceType": "StructureDefinition", "id": "au-condition"}
        )
    )
    mock.put("/StructureDefinition/au-vitalsigns-bloodpressure").mock(
        return_value=Response(
            200,
            json={
                "resourceType": "StructureDefinition",
                "id": "au-vitalsigns-bloodpressure",
            },
        )
    )
    mock.put("/Encounter").mock(
        return_value=Response(201, json={"resourceType": "Encounter", "id": "enc-1"})
    )
    return mock


def _hapi_mock_no_patient():
    mock = respx.mock(base_url="http://localhost:8080/fhir")
    mock.get("/Patient").mock(
        return_value=Response(
            200, json={"resourceType": "Bundle", "total": 0, "entry": []}
        )
    )
    return mock


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


class TestEncounterEndpoint:
    def _valid_payload(self, **overrides):
        defaults = {
            "correlationId": "int-enc-001",
            "mrn": "1234567",
            "visitNumber": "VN00012",
            "patientClass": "O",
            "admitDatetime": "20260420090000",
            "location": {"ward": "Ward A"},
            "attendingDoctor": {
                "id": "DR1",
                "familyName": "Smith",
                "givenName": "John",
            },
            "orderControl": "NW",
        }
        defaults.update(overrides)
        return defaults

    @pytest.mark.asyncio
    async def test_success_returns_encounter_id(self):
        with _hapi_mock_with_patient():
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/Encounter", json=self._valid_payload()
                    )
        assert response.status_code == 200
        body = response.json()
        assert body["encounterId"] == "enc-1"

    @pytest.mark.asyncio
    async def test_missing_patient_returns_422(self):
        with _hapi_mock_no_patient():
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/Encounter", json=self._valid_payload()
                    )
        assert response.status_code == 422
        body = response.json()
        assert "Patient not found" in body["detail"]

    @pytest.mark.asyncio
    async def test_empty_visit_number_returns_422(self):
        async with app.router.lifespan_context(app), await _client() as client:
            response = await client.post(
                "/fhir/Encounter", json=self._valid_payload(visitNumber="")
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_mrn_returns_422(self):
        async with app.router.lifespan_context(app), await _client() as client:
            response = await client.post(
                "/fhir/Encounter", json=self._valid_payload(mrn="")
            )
        assert response.status_code == 422
