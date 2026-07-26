import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def search_resources(
    http_client: httpx.AsyncClient,
    resource_type: str,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    """Search HAPI FHIR for resources matching the given parameters."""
    url = f"{settings.hapi_base_url}/{resource_type}"
    response = await http_client.get(url, params=params)

    if response.status_code != 200:
        logger.warning(
            "HAPI search %s returned %s", resource_type, response.status_code
        )
        return []

    bundle = response.json()
    entries = bundle.get("entry", [])
    return [entry.get("resource", {}) for entry in entries if "resource" in entry]


async def get_patient_resources(
    http_client: httpx.AsyncClient,
    patient_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Retrieve all relevant resources for a patient for IPS generation."""
    patient_ref = f"Patient/{patient_id}"
    results: dict[str, list[dict[str, Any]]] = {}

    results["conditions"] = await search_resources(
        http_client, "Condition", {"subject": patient_ref, "_count": "100"}
    )

    results["observations"] = await search_resources(
        http_client, "Observation", {"subject": patient_ref, "_count": "100"}
    )

    results["encounters"] = await search_resources(
        http_client, "Encounter", {"subject": patient_ref, "_count": "100"}
    )

    patient_resources = await search_resources(
        http_client, "Patient", {"_id": patient_id}
    )
    results["patient"] = patient_resources

    return results
