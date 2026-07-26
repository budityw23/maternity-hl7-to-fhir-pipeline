import logging
from typing import Any, cast

import httpx

from app.config import settings
from app.profiles.base import ProfileConfig

logger = logging.getLogger(__name__)


class HapiClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client
        self._base = settings.hapi_base_url

    async def upsert_resource(
        self,
        resource_type: str,
        resource_data: dict[str, Any],
        identifier_query: str,
    ) -> str:
        """Conditional update: creates if not found, updates if single match."""
        url = f"{self._base}/{resource_type}"
        headers = {
            "Content-Type": "application/fhir+json",
            "If-None-Exist": f"identifier={identifier_query}",
        }

        response = await self._client.put(
            url,
            params={"identifier": identifier_query},
            json=resource_data,
            headers=headers,
        )

        if response.status_code not in (200, 201):
            logger.error("HAPI upsert failed: %s %s", response.status_code, response.text)
            response.raise_for_status()

        body = cast("dict[str, Any] | list[Any] | str | int | float | bool | None", response.json())
        if isinstance(body, dict) and body.get("id"):
            return str(body["id"])

        location = response.headers.get("Location", "")
        if location:
            parts = [part for part in location.split("/") if part and part != "_history"]
            if parts:
                return str(parts[-1])

        return "unknown"

    async def create_resource(
        self,
        resource_type: str,
        resource_data: dict[str, Any],
    ) -> str:
        """Create a new resource via POST. Returns server-assigned ID."""
        url = f"{self._base}/{resource_type}"
        headers = {"Content-Type": "application/fhir+json"}

        response = await self._client.post(
            url,
            json=resource_data,
            headers=headers,
        )

        if response.status_code not in (200, 201):
            logger.error("HAPI create failed: %s %s", response.status_code, response.text)
            response.raise_for_status()

        body = cast("dict[str, Any] | list[Any] | str | int | float | bool | None", response.json())
        if isinstance(body, dict) and body.get("id"):
            return str(body["id"])

        location = response.headers.get("Location", "")
        if location:
            parts = [part for part in location.split("/") if part and part != "_history"]
            if parts:
                return str(parts[-1])

        return "unknown"

    async def validate_resource(
        self,
        resource_type: str,
        resource_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Validate a resource against HAPI's loaded profiles.

        Returns None if valid, or the OperationOutcome dict if validation fails.
        """
        url = f"{self._base}/{resource_type}/$validate"
        headers = {"Content-Type": "application/fhir+json"}

        response = await self._client.post(
            url,
            json=resource_data,
            headers=headers,
        )

        if response.status_code not in (200, 201):
            logger.warning(
                "HAPI $validate returned %s: %s",
                response.status_code,
                response.text[:500],
            )
            return None

        outcome = cast("dict[str, Any]", response.json())
        issues = outcome.get("issue", [])

        has_errors = any(
            issue.get("severity") in ("error", "fatal")
            for issue in issues
        )

        if has_errors:
            return outcome

        return None

    async def ensure_profiles(self, profile: ProfileConfig) -> None:
        """Seed minimal StructureDefinition placeholders for the active profile."""
        for defn in profile.profile_definitions:
            resource = {
                "resourceType": "StructureDefinition",
                "id": defn["id"],
                "url": defn["url"],
                "name": defn["name"],
                "status": "active",
                "kind": "resource",
                "abstract": False,
                "type": defn["type"],
                "baseDefinition": f"http://hl7.org/fhir/StructureDefinition/{defn['type']}",
                "derivation": "constraint",
                "differential": {
                    "element": [{"id": defn["type"], "path": defn["type"]}]
                },
            }
            response = await self._client.put(
                f"{self._base}/StructureDefinition/{defn['id']}",
                json=resource,
                headers={"Content-Type": "application/fhir+json"},
            )
            if response.status_code not in (200, 201):
                logger.error(
                    "HAPI profile seed failed for %s: %s %s",
                    defn["id"],
                    response.status_code,
                    response.text,
                )
                response.raise_for_status()
