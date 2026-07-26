import os
from unittest.mock import AsyncMock, patch

import pytest
from app.config import Settings
from app.profiles.eu_profile import build_eu_profile
from httpx import ASGITransport, AsyncClient, Response

EU_PROFILE = build_eu_profile("uk")


def _mock_hapi_response(status_code: int = 201, resource_id: str = "eu-test-1"):
    return Response(
        status_code,
        json={"id": resource_id, "resourceType": "Patient"},
        headers={"Location": f"Patient/{resource_id}/_history/1"},
    )


@pytest.fixture
def eu_env():
    with (
        patch.dict(os.environ, {"PROFILE_REGION": "eu", "PROFILE_COUNTRY": "uk"}),
        patch("app.profiles.registry.settings", Settings(profile_region="eu", profile_country="uk")),
    ):
        yield


@pytest.fixture
def mock_http_client():
    mock_client = AsyncMock()
    mock_client.put = AsyncMock(return_value=_mock_hapi_response())
    mock_client.post = AsyncMock(return_value=_mock_hapi_response())
    mock_client.get = AsyncMock(return_value=_mock_hapi_response(200))
    mock_client.aclose = AsyncMock()
    return mock_client


class TestEuPatientEndpoint:
    @pytest.mark.asyncio
    async def test_eu_patient_returns_success(self, eu_env, mock_http_client):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            app.state.http_client = mock_http_client
            payload = {
                "correlationId": "eu-int-001",
                "messageType": "ADT^A01",
                "mrn": "MRN-EU-001",
                "ihi": "9434765919",
                "name": {"family": "SMITH", "given": "EMMA"},
                "birthDate": "19900210",
                "gender": "F",
                "address": {
                    "line": "42 BAKER STREET",
                    "city": "LONDON",
                    "state": "",
                    "postalCode": "NW1 6XE",
                    "country": "GB",
                },
                "diagnoses": [
                    {
                        "code": "O80",
                        "display": "Normal delivery",
                        "codeSystem": "I10",
                        "recordedDate": "20260527093000",
                    }
                ],
            }
            response = await client.post("/fhir/Patient", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "patientId" in data
        assert data["correlationId"] == "eu-int-001"


class TestEuEncounterEndpoint:
    @pytest.mark.asyncio
    async def test_eu_encounter_requires_patient(self, eu_env, mock_http_client):
        from app.main import app

        search_response = Response(200, json={"total": 0, "entry": []})
        mock_http_client.get = AsyncMock(return_value=search_response)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            app.state.http_client = mock_http_client
            payload = {
                "correlationId": "eu-int-002",
                "mrn": "MRN-EU-MISSING",
                "visitNumber": "VN-EU-001",
                "patientClass": "O",
                "admitDatetime": "20260420100000",
                "location": {"ward": "MATERNITY_WARD"},
                "attendingDoctor": {"id": "DR_JONES", "familyName": "JONES", "givenName": "SARAH"},
                "orderControl": "NW",
            }
            response = await client.post("/fhir/Encounter", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_eu_encounter_success(self, eu_env, mock_http_client):
        from app.main import app

        patient_data = {
            "resourceType": "Patient",
            "id": "pat-eu-enc-1",
            "identifier": [{"system": "http://hospital.local/mrn", "value": "MRN-EU-001"}],
        }
        search_response = Response(
            200,
            json={"total": 1, "entry": [{"resource": patient_data}]},
        )
        mock_http_client.get = AsyncMock(return_value=search_response)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            app.state.http_client = mock_http_client
            payload = {
                "correlationId": "eu-int-enc-001",
                "mrn": "MRN-EU-001",
                "visitNumber": "VN-EU-001",
                "patientClass": "O",
                "admitDatetime": "20260420100000",
                "location": {
                    "ward": "MATERNITY_WARD",
                    "room": "MW-01",
                    "facility": "ST_THOMAS",
                },
                "attendingDoctor": {
                    "id": "DR_JONES",
                    "familyName": "JONES",
                    "givenName": "SARAH",
                },
                "orderControl": "NW",
                "serviceCode": "424525001",
                "serviceDisplay": "Antenatal care",
            }
            response = await client.post("/fhir/Encounter", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "encounterId" in data


class TestEuObservationEndpoint:
    @pytest.mark.asyncio
    async def test_eu_observation_requires_patient(self, eu_env, mock_http_client):
        from app.main import app

        search_response = Response(200, json={"total": 0, "entry": []})
        mock_http_client.get = AsyncMock(return_value=search_response)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            app.state.http_client = mock_http_client
            payload = {
                "correlationId": "eu-int-003",
                "mrn": "MRN-EU-MISSING",
                "visitNumber": "VN-EU-001",
                "observations": [
                    {
                        "setId": 1,
                        "valueType": "NM",
                        "code": "29463-7",
                        "display": "Body weight",
                        "codeSystem": "LN",
                        "value": 72.0,
                        "unitCode": "kg",
                        "unitDisplay": "kilogram",
                        "referenceRange": "",
                        "abnormalFlag": "N",
                        "status": "F",
                        "observationDatetime": "20260420103000",
                    }
                ],
            }
            response = await client.post("/fhir/Observation/bundle", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_eu_observation_success(self, eu_env, mock_http_client):
        from app.main import app

        patient_data = {
            "resourceType": "Patient",
            "id": "pat-eu-obs-1",
            "identifier": [{"system": "http://hospital.local/mrn", "value": "MRN-EU-001"}],
        }
        encounter_data = {
            "resourceType": "Encounter",
            "id": "enc-eu-obs-1",
        }

        def _get_side_effect(url, **kwargs):
            if "Patient" in url:
                return Response(
                    200,
                    json={"total": 1, "entry": [{"resource": patient_data}]},
                )
            if "Encounter" in url:
                return Response(
                    200,
                    json={"total": 1, "entry": [{"resource": encounter_data}]},
                )
            return Response(200, json={"total": 0, "entry": []})

        mock_http_client.get = AsyncMock(side_effect=_get_side_effect)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            app.state.http_client = mock_http_client
            payload = {
                "correlationId": "eu-int-obs-001",
                "mrn": "MRN-EU-001",
                "visitNumber": "VN-EU-001",
                "observations": [
                    {
                        "setId": 1,
                        "valueType": "NM",
                        "code": "29463-7",
                        "display": "Body weight",
                        "codeSystem": "LN",
                        "value": 72.0,
                        "unitCode": "kg",
                        "unitDisplay": "kilogram",
                        "referenceRange": "50-100",
                        "abnormalFlag": "N",
                        "status": "F",
                        "observationDatetime": "20260420103000",
                    }
                ],
            }
            response = await client.post("/fhir/Observation/bundle", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "observationIds" in data
