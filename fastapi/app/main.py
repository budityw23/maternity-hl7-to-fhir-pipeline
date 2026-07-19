import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException

from app.clients.encounter_resolver import resolve_encounter_id
from app.clients.hapi_client import HapiClient
from app.clients.patient_resolver import resolve_patient_id
from app.config import settings
from app.models.adt_payload import AdtPayload
from app.models.orm_payload import OrmPayload
from app.models.oru_payload import OruPayload
from app.transformers.condition import build_conditions
from app.transformers.encounter import VISIT_NUMBER_SYSTEM, build_encounter
from app.transformers.observation import build_observations
from app.transformers.patient import build_patient


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Maternity FHIR Converter",
    description="HL7 v2 to FHIR R4 transformation service for Australian maternity care",
    version="0.1.0",
    lifespan=lifespan,
)


def _resource_to_json(resource: Any) -> dict[str, Any]:
    if hasattr(resource, "model_dump"):
        return resource.model_dump(mode="json", exclude_none=True)
    return json.loads(resource.json(by_alias=True, exclude_none=True))


@app.get("/health")
async def health_check() -> dict[str, Any]:
    hapi_status = "unknown"
    try:
        client: httpx.AsyncClient = app.state.http_client
        response = await client.get(f"{settings.hapi_base_url}/metadata")
        hapi_status = "up" if response.status_code == 200 else "down"
    except httpx.HTTPError:
        hapi_status = "down"

    overall = "ok" if hapi_status == "up" else "degraded"

    return {
        "status": overall,
        "hapi": hapi_status,
        "version": "0.1.0",
    }


@app.post("/fhir/Patient")
async def transform_patient(payload: AdtPayload) -> dict[str, Any]:
    logger = logging.getLogger("app.fhir.patient")
    logger.info(
        "Processing ADT^A01 for MRN=%s correlationId=%s",
        payload.mrn,
        payload.correlationId,
    )

    patient = build_patient(payload)
    patient_data = _resource_to_json(patient)

    hapi = HapiClient(app.state.http_client)
    await hapi.ensure_au_patient_profile()
    identifier_query = f"{settings.mrn_system}|{payload.mrn}"
    patient_id = await hapi.upsert_resource("Patient", patient_data, identifier_query)

    logger.info(
        "Patient persisted id=%s correlationId=%s",
        patient_id,
        payload.correlationId,
    )

    condition_ids: list[str] = []
    if payload.diagnoses:
        patient_reference = f"Patient/{patient_id}"
        conditions = build_conditions(payload, patient_reference)
        for condition in conditions:
            condition_data = _resource_to_json(condition)
            condition_id = await hapi.create_resource("Condition", condition_data)
            condition_ids.append(condition_id)
            logger.info(
                "Condition persisted id=%s correlationId=%s",
                condition_id,
                payload.correlationId,
            )

    return {
        "patientId": patient_id,
        "conditionIds": condition_ids,
        "correlationId": payload.correlationId,
    }


@app.post("/fhir/Encounter")
async def transform_encounter(payload: OrmPayload) -> dict[str, Any]:
    logger = logging.getLogger("app.fhir.encounter")
    logger.info(
        "Processing ORM^O01 for MRN=%s visitNumber=%s correlationId=%s",
        payload.mrn,
        payload.visitNumber,
        payload.correlationId,
    )

    patient_id = await resolve_patient_id(app.state.http_client, payload.mrn)
    if not patient_id:
        raise HTTPException(
            status_code=422,
            detail=f"Patient not found for MRN={payload.mrn}. Send ADT^A01 first.",
        )

    patient_reference = f"Patient/{patient_id}"
    encounter = build_encounter(payload, patient_reference)
    encounter_data = _resource_to_json(encounter)

    hapi = HapiClient(app.state.http_client)
    identifier_query = f"{VISIT_NUMBER_SYSTEM}|{payload.visitNumber}"
    encounter_id = await hapi.upsert_resource("Encounter", encounter_data, identifier_query)

    logger.info(
        "Encounter persisted id=%s correlationId=%s",
        encounter_id,
        payload.correlationId,
    )

    return {
        "encounterId": encounter_id,
        "correlationId": payload.correlationId,
    }


@app.post("/fhir/Observation/bundle")
async def transform_observations(payload: OruPayload) -> dict[str, Any]:
    logger = logging.getLogger("app.fhir.observation")
    logger.info(
        "Processing ORU^R01 for MRN=%s visitNumber=%s correlationId=%s",
        payload.mrn,
        payload.visitNumber,
        payload.correlationId,
    )

    patient_id = await resolve_patient_id(app.state.http_client, payload.mrn)
    if not patient_id:
        raise HTTPException(
            status_code=422,
            detail=f"Patient not found for MRN={payload.mrn}. Send ADT^A01 first.",
        )
    patient_reference = f"Patient/{patient_id}"

    encounter_reference: str | None = None
    if payload.visitNumber:
        encounter_id = await resolve_encounter_id(
            app.state.http_client, payload.visitNumber
        )
        if encounter_id:
            encounter_reference = f"Encounter/{encounter_id}"

    observations = build_observations(
        payload, patient_reference, encounter_reference
    )

    hapi = HapiClient(app.state.http_client)
    observation_ids: list[str] = []
    for obs in observations:
        obs_data = _resource_to_json(obs)
        obs_id = await hapi.create_resource("Observation", obs_data)
        observation_ids.append(obs_id)
        logger.info(
            "Observation persisted id=%s correlationId=%s",
            obs_id,
            payload.correlationId,
        )

    return {
        "observationIds": observation_ids,
        "correlationId": payload.correlationId,
    }
