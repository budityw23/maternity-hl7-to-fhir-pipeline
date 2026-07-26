import re

from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.condition import Condition
from fhir.resources.meta import Meta
from fhir.resources.narrative import Narrative
from fhir.resources.reference import Reference

from app.models.adt_payload import AdtPayload, DiagnosisPayload
from app.profiles.base import ProfileConfig

CLINICAL_STATUS_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-clinical"
VERIFICATION_STATUS_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-category"


def _hl7_datetime_to_iso(hl7_dt: str, timezone_offset: str) -> str:
    """Convert HL7 datetime YYYYMMDDHHMMSS to ISO 8601 with configurable offset."""
    cleaned = re.sub(r"[^0-9]", "", hl7_dt)
    if len(cleaned) >= 14:
        return (
            f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
            f"T{cleaned[8:10]}:{cleaned[10:12]}:{cleaned[12:14]}{timezone_offset}"
        )
    if len(cleaned) >= 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
    return hl7_dt


def build_condition(
    diagnosis: DiagnosisPayload,
    patient_reference: str,
    profile: ProfileConfig,
) -> Condition:
    """Build a single FHIR Condition from a DiagnosisPayload."""
    condition = Condition(
        meta=Meta(profile=[profile.condition_profile_url]),
        text=Narrative(
            status="generated",
            div=f'<div xmlns="http://www.w3.org/1999/xhtml">Condition {diagnosis.code}</div>',
        ),
        clinicalStatus=CodeableConcept(coding=[Coding(system=CLINICAL_STATUS_SYSTEM, code="active")]),
        verificationStatus=CodeableConcept(coding=[Coding(system=VERIFICATION_STATUS_SYSTEM, code="confirmed")]),
        category=[CodeableConcept(coding=[Coding(system=CATEGORY_SYSTEM, code="encounter-diagnosis")])],
        code=CodeableConcept(
            coding=[
                Coding(
                    system=profile.diagnosis_code_system,
                    code=diagnosis.code,
                    display=diagnosis.display,
                )
            ]
        ),
        subject=Reference(reference=patient_reference),
    )

    if diagnosis.recordedDate:
        condition.recordedDate = _hl7_datetime_to_iso(
            diagnosis.recordedDate, profile.timezone_offset
        )

    return condition


def build_conditions(
    payload: AdtPayload,
    patient_reference: str,
    profile: ProfileConfig,
) -> list[Condition]:
    """Build Condition resources for all diagnoses in an ADT payload."""
    return [build_condition(dx, patient_reference, profile) for dx in payload.diagnoses]
