import pytest
import respx
from app.main import app
from httpx import ASGITransport, AsyncClient, Response


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_hapi_up(self):
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.get("/metadata").mock(
                return_value=Response(
                    200, json={"resourceType": "CapabilityStatement"}
                )
            )
            async with app.router.lifespan_context(app), await _client() as client:
                response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["hapi"] == "up"

    @pytest.mark.asyncio
    async def test_health_hapi_down(self):
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.get("/metadata").mock(return_value=Response(503))
            async with app.router.lifespan_context(app), await _client() as client:
                response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["hapi"] == "down"

    @pytest.mark.asyncio
    async def test_health_returns_version(self):
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.get("/metadata").mock(return_value=Response(200, json={}))
            async with app.router.lifespan_context(app), await _client() as client:
                response = await client.get("/health")
        body = response.json()
        assert body["version"] == "0.1.0"

    @pytest.mark.asyncio
    async def test_health_has_correlation_id_header(self):
        with respx.mock(base_url="http://localhost:8080/fhir") as mock:
            mock.get("/metadata").mock(return_value=Response(200, json={}))
            async with app.router.lifespan_context(app), await _client() as client:
                response = await client.get("/health")
        assert "X-Correlation-ID" in response.headers
