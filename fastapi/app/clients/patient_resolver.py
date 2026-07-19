import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def resolve_patient_id(http_client: httpx.AsyncClient, mrn: str) -> str | None:
    """Look up a Patient's FHIR ID by MRN."""
    url = f"{settings.hapi_base_url}/Patient"
    params = {"identifier": f"{settings.mrn_system}|{mrn}"}

    response = await http_client.get(url, params=params)
    if response.status_code != 200:
        logger.warning("Patient lookup failed: %s", response.status_code)
        return None

    bundle = response.json()
    total = bundle.get("total", 0)
    if total == 0:
        logger.warning("No Patient found for MRN=%s", mrn)
        return None

    entries = bundle.get("entry", [])
    if not entries:
        return None

    resource = entries[0].get("resource", {})
    patient_id = resource.get("id")
    return str(patient_id) if patient_id else None
