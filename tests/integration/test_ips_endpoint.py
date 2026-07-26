import os
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.config import Settings


def _mock_search_response(resources):
    return Response(
        200,
        json={
            "total": len(resources),
            "entry": [{"resource": r} for r in resources],
        },
    )


class TestIpsEndpoint:
    @pytest.mark.asyncio
    async def test_ips_missing_patient(self):
        from app.main import app

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_search_response([]))
        mock_client.aclose = AsyncMock()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            app.state.http_client = mock_client
            response = await client.post(
                "/fhir/IPS",
                json={"correlationId": "ips-test-001", "mrn": "MISSING-MRN"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_ips_returns_bundle(self):
        from app.main import app

        patient_data = {
            "resourceType": "Patient",
            "id": "pat-ips-1",
            "identifier": [{"system": "http://hospital.local/mrn", "value": "MRN-IPS-001"}],
        }

        def _get_side_effect(url, **kwargs):
            params = kwargs.get("params", {})
            if "Patient" in url and "_id" not in str(params):
                return _mock_search_response([patient_data])
            if "Patient" in url and "_id" in str(params):
                return _mock_search_response([patient_data])
            return _mock_search_response([])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_get_side_effect)
        mock_client.aclose = AsyncMock()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            app.state.http_client = mock_client
            response = await client.post(
                "/fhir/IPS",
                json={"correlationId": "ips-test-002", "mrn": "MRN-IPS-001"},
            )
        assert response.status_code == 200
        bundle = response.json()
        assert bundle["type"] == "document"
        assert bundle["entry"][0]["resource"]["resourceType"] == "Composition"


class TestIpsEndpointEuMode:
    @pytest.mark.asyncio
    async def test_ips_returns_bundle_eu_mode(self):
        with (
            patch.dict(os.environ, {"PROFILE_REGION": "eu", "PROFILE_COUNTRY": "uk"}),
            patch(
                "app.profiles.registry.settings",
                Settings(profile_region="eu", profile_country="uk"),
            ),
        ):
            from app.main import app

            patient_data = {
                "resourceType": "Patient",
                "id": "pat-ips-eu-1",
                "identifier": [
                    {
                        "system": "http://hospital.local/mrn",
                        "value": "MRN-IPS-EU-001",
                    }
                ],
            }

            def _get_side_effect(url, **kwargs):
                params = kwargs.get("params", {})
                if "Patient" in url and "_id" not in str(params):
                    return _mock_search_response([patient_data])
                if "Patient" in url and "_id" in str(params):
                    return _mock_search_response([patient_data])
                return _mock_search_response([])

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=_get_side_effect)
            mock_client.aclose = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                app.state.http_client = mock_client
                response = await client.post(
                    "/fhir/IPS",
                    json={
                        "correlationId": "ips-eu-test-001",
                        "mrn": "MRN-IPS-EU-001",
                    },
                )
            assert response.status_code == 200
            bundle = response.json()
            assert bundle["type"] == "document"
            assert bundle["entry"][0]["resource"]["resourceType"] == "Composition"
