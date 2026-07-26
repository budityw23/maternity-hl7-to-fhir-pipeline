import pytest
import respx
from app.main import app
from httpx import ASGITransport, AsyncClient, Response


def _hapi_mock_full():
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
    mock.get("/Encounter").mock(
        return_value=Response(
            200,
            json={
                "resourceType": "Bundle",
                "total": 1,
                "entry": [{"resource": {"resourceType": "Encounter", "id": "enc-1"}}],
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
    mock.put("/StructureDefinition/au-vitalsigns-bloodpressure").mock(
        return_value=Response(
            200,
            json={
                "resourceType": "StructureDefinition",
                "id": "au-vitalsigns-bloodpressure",
            },
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
    mock.put("/StructureDefinition/au-encounter").mock(
        return_value=Response(
            200, json={"resourceType": "StructureDefinition", "id": "au-encounter"}
        )
    )

    observation_counter = {"n": 0}

    def _obs_response(request):
        observation_counter["n"] += 1
        return Response(
            201,
            json={
                "resourceType": "Observation",
                "id": f"obs-{observation_counter['n']}",
            },
        )

    mock.post("/Observation").mock(side_effect=_obs_response)
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


class TestObservationEndpoint:
    def _valid_payload(self, observations=None):
        return {
            "correlationId": "int-obs-001",
            "mrn": "1234567",
            "visitNumber": "VN00012",
            "observations": observations
            if observations is not None
            else [
                {
                    "setId": 1,
                    "code": "29463-7",
                    "display": "Body weight",
                    "value": 68.5,
                    "unitCode": "kg",
                    "status": "F",
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_simple_observation_success(self):
        with _hapi_mock_full():
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/Observation/bundle", json=self._valid_payload()
                    )
        assert response.status_code == 200
        body = response.json()
        assert body["observationIds"] == ["obs-1"]

    @pytest.mark.asyncio
    async def test_bp_panel_merging(self):
        observations = [
            {
                "setId": 1,
                "code": "8480-6",
                "display": "Systolic BP",
                "value": 120,
                "unitCode": "mm[Hg]",
                "status": "F",
            },
            {
                "setId": 2,
                "code": "8462-4",
                "display": "Diastolic BP",
                "value": 80,
                "unitCode": "mm[Hg]",
                "status": "F",
            },
            {
                "setId": 3,
                "code": "29463-7",
                "display": "Body weight",
                "value": 68.5,
                "unitCode": "kg",
                "status": "F",
            },
        ]
        with _hapi_mock_full():
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/Observation/bundle",
                        json=self._valid_payload(observations),
                    )
        assert response.status_code == 200
        body = response.json()
        assert body["observationIds"] == ["obs-1", "obs-2"]

    @pytest.mark.asyncio
    async def test_empty_observations_returns_empty(self):
        with _hapi_mock_full():
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/Observation/bundle",
                        json=self._valid_payload(observations=[]),
                    )
        assert response.status_code == 200
        body = response.json()
        assert body["observationIds"] == []

    @pytest.mark.asyncio
    async def test_missing_patient_returns_422(self):
        with _hapi_mock_no_patient():
            async with app.router.lifespan_context(app):
                async with await _client() as client:
                    response = await client.post(
                        "/fhir/Observation/bundle", json=self._valid_payload()
                    )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_mrn_returns_422(self):
        payload = self._valid_payload()
        payload["mrn"] = ""
        async with app.router.lifespan_context(app), await _client() as client:
            response = await client.post("/fhir/Observation/bundle", json=payload)
        assert response.status_code == 422
