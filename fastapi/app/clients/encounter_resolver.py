import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VISIT_NUMBER_SYSTEM = "http://hospital.local/visit-number"


async def resolve_encounter_id(
    http_client: httpx.AsyncClient, visit_number: str
) -> str | None:
    """Look up an Encounter's FHIR ID by visit number."""
    url = f"{settings.hapi_base_url}/Encounter"
    params = {"identifier": f"{VISIT_NUMBER_SYSTEM}|{visit_number}"}

    response = await http_client.get(url, params=params)
    if response.status_code != 200:
        logger.warning("Encounter lookup failed: %s", response.status_code)
        return None

    bundle = response.json()
    total = bundle.get("total", 0)
    if total == 0:
        logger.warning("No Encounter found for visit_number=%s", visit_number)
        return None

    entries = bundle.get("entry", [])
    if not entries:
        return None

    resource = entries[0].get("resource", {})
    encounter_id = resource.get("id")
    return str(encounter_id) if encounter_id else None
