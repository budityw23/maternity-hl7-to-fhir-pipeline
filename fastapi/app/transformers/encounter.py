import re

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.encounter import Encounter
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.meta import Meta
from fhir.resources.R4B.narrative import Narrative
from fhir.resources.R4B.period import Period
from fhir.resources.R4B.reference import Reference

from app.models.orm_payload import OrmPayload
from app.valuesets.hl7_to_fhir_encounter import map_encounter_status, map_patient_class

VISIT_NUMBER_SYSTEM = "http://hospital.local/visit-number"
AU_ENCOUNTER_PROFILE = "http://hl7.org.au/fhir/StructureDefinition/au-encounter"
PARTICIPATION_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ParticipationType"
SNOMED_SYSTEM = "http://snomed.info/sct"
ANTENATAL_CARE_CODE = "424525001"
ANTENATAL_CARE_DISPLAY = "Antenatal care"


def _hl7_datetime_to_iso(hl7_dt: str) -> str:
    """Convert HL7 datetime YYYYMMDDHHMMSS to ISO 8601 with AEST offset."""
    cleaned = re.sub(r"[^0-9]", "", hl7_dt)
    if len(cleaned) >= 14:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}T{cleaned[8:10]}:{cleaned[10:12]}:{cleaned[12:14]}+10:00"
    if len(cleaned) >= 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
    return hl7_dt


def build_encounter(
    payload: OrmPayload,
    patient_reference: str,
) -> Encounter:
    period_kwargs: dict[str, str] = {
        "start": _hl7_datetime_to_iso(payload.admitDatetime),
    }
    if payload.dischargeDatetime:
        period_kwargs["end"] = _hl7_datetime_to_iso(payload.dischargeDatetime)

    if payload.serviceCode:
        service_type = CodeableConcept(
            coding=[
                Coding(
                    system=SNOMED_SYSTEM,
                    code=payload.serviceCode,
                    display=payload.serviceDisplay or payload.serviceCode,
                )
            ]
        )
    else:
        service_type = CodeableConcept(
            coding=[
                Coding(
                    system=SNOMED_SYSTEM,
                    code=ANTENATAL_CARE_CODE,
                    display=ANTENATAL_CARE_DISPLAY,
                )
            ]
        )

    location_entry = {
        "location": {
            "display": payload.location.ward,
        }
    }
    if payload.location.room:
        location_entry["location"]["identifier"] = {"value": payload.location.room}

    participant_entry = {
        "type": [
            {
                "coding": [
                    {
                        "system": PARTICIPATION_TYPE_SYSTEM,
                        "code": "ATND",
                        "display": "attender",
                    }
                ]
            }
        ],
        "individual": {
            "identifier": {"value": payload.attendingDoctor.id},
            "display": f"{payload.attendingDoctor.familyName}, {payload.attendingDoctor.givenName}",
        },
    }

    encounter = Encounter(
        meta=Meta(profile=[AU_ENCOUNTER_PROFILE]),
        text=Narrative(
            status="generated",
            div=f'<div xmlns="http://www.w3.org/1999/xhtml">Encounter {payload.visitNumber}</div>',
        ),
        status=map_encounter_status(payload.orderControl),
        identifier=[Identifier(system=VISIT_NUMBER_SYSTEM, value=payload.visitNumber)],
        class_fhir=map_patient_class(payload.patientClass),
        serviceType=service_type,
        subject=Reference(reference=patient_reference),
        participant=[participant_entry],
        period=Period(**period_kwargs),
        location=[location_entry],
    )

    return encounter
