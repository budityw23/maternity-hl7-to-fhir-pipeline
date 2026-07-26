import os
from unittest.mock import AsyncMock, patch

import pytest
from app.config import Settings
from httpx import ASGITransport, AsyncClient, Response


def _mock_search_response(resources):
    return Response(
        200,
        json={
            "total": len(resources),
            "entry": [{"resource": r} for r in resources],
        },
    )


def _mock_create_response(resource_id="consent-1"):
    return Response(
        201,
        json={"id": resource_id},
        headers={"Location": f"Consent/{resource_id}/_history/1"},
    )


class TestConsentEndpointAuMode:
    @pytest.mark.asyncio
    async def test_returns_404_in_au_mode(self):
        with (
            patch.dict(os.environ, {"PROFILE_REGION": "au"}),
            patch("app.profiles.registry.settings", Settings(profile_region="au")),
        ):
            from app.main import app

            mock_client = AsyncMock()
            mock_client.aclose = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                app.state.http_client = mock_client
                response = await client.post(
                    "/fhir/Consent",
                    json={
                        "correlationId": "consent-au-001",
                        "mrn": "MRN-001",
                        "policyRule": "gdpr-art-6-1-a",
                        "provisionType": "permit",
                    },
                )
            assert response.status_code == 404


class TestConsentEndpointEuMode:
    @pytest.mark.asyncio
    async def test_consent_missing_patient(self):
        with (
            patch.dict(os.environ, {"PROFILE_REGION": "eu", "PROFILE_COUNTRY": "uk"}),
            patch("app.profiles.registry.settings", Settings(profile_region="eu", profile_country="uk")),
        ):
            from app.main import app

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_search_response([]))
            mock_client.aclose = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                app.state.http_client = mock_client
                response = await client.post(
                    "/fhir/Consent",
                    json={
                        "correlationId": "consent-eu-001",
                        "mrn": "MRN-MISSING",
                        "policyRule": "gdpr-art-6-1-a",
                        "provisionType": "permit",
                    },
                )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_consent_success(self):
        with (
            patch.dict(os.environ, {"PROFILE_REGION": "eu", "PROFILE_COUNTRY": "uk"}),
            patch("app.profiles.registry.settings", Settings(profile_region="eu", profile_country="uk")),
        ):
            from app.main import app

            patient_data = {
                "resourceType": "Patient",
                "id": "pat-eu-1",
                "identifier": [{"system": "http://hospital.local/mrn", "value": "MRN-EU-001"}],
            }

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_search_response([patient_data]))
            mock_client.post = AsyncMock(return_value=_mock_create_response("consent-eu-1"))
            mock_client.put = AsyncMock(return_value=_mock_create_response())
            mock_client.aclose = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                app.state.http_client = mock_client
                response = await client.post(
                    "/fhir/Consent",
                    json={
                        "correlationId": "consent-eu-002",
                        "mrn": "MRN-EU-001",
                        "policyRule": "gdpr-art-9-2-h",
                        "provisionType": "permit",
                        "periodStart": "20260101",
                        "periodEnd": "20271231",
                    },
                )
            assert response.status_code == 200
            data = response.json()
            assert "consentId" in data
