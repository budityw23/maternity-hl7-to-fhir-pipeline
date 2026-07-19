import logging
from typing import Any

import httpx

from app.config import settings

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

        body = response.json()
        if isinstance(body, dict) and body.get("id"):
            return str(body["id"])

        location = response.headers.get("Location", "")
        if location:
            parts = [part for part in location.split("/") if part and part != "_history"]
            if parts:
                return parts[-1]

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

        body = response.json()
        if isinstance(body, dict) and body.get("id"):
            return str(body["id"])

        location = response.headers.get("Location", "")
        if location:
            parts = [part for part in location.split("/") if part and part != "_history"]
            if parts:
                return parts[-1]

        return "unknown"

    async def ensure_au_patient_profile(self) -> None:
        """Seed a minimal AU Patient profile placeholder for demo validation."""
        profile_id = "au-patient"
        profile_url = "http://hl7.org.au/fhir/StructureDefinition/au-patient"
        resource = {
            "resourceType": "StructureDefinition",
            "id": profile_id,
            "url": profile_url,
            "name": "AUPatient",
            "status": "active",
            "kind": "resource",
            "abstract": False,
            "type": "Patient",
            "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Patient",
            "derivation": "constraint",
            "differential": {"element": [{"id": "Patient", "path": "Patient"}]},
        }
        response = await self._client.put(
            f"{self._base}/StructureDefinition/{profile_id}",
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
        )
        if response.status_code not in (200, 201):
            logger.error("HAPI profile seed failed: %s %s", response.status_code, response.text)
            response.raise_for_status()

    async def ensure_au_bp_profile(self) -> None:
        """Seed a minimal AU BP Observation profile placeholder for demo validation."""
        profile_id = "au-vitalsigns-bloodpressure"
        profile_url = "http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure"
        resource = {
            "resourceType": "StructureDefinition",
            "id": profile_id,
            "url": profile_url,
            "name": "AUVitalSignsBloodPressure",
            "status": "active",
            "kind": "resource",
            "abstract": False,
            "type": "Observation",
            "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Observation",
            "derivation": "constraint",
            "differential": {"element": [{"id": "Observation", "path": "Observation"}]},
        }
        response = await self._client.put(
            f"{self._base}/StructureDefinition/{profile_id}",
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
        )
        if response.status_code not in (200, 201):
            logger.error("HAPI BP profile seed failed: %s %s", response.status_code, response.text)
            response.raise_for_status()
