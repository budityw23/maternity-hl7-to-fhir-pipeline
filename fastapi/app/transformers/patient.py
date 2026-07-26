import re

from fhir.resources.address import Address
from fhir.resources.contactpoint import ContactPoint
from fhir.resources.humanname import HumanName
from fhir.resources.identifier import Identifier
from fhir.resources.narrative import Narrative
from fhir.resources.patient import Patient

from app.config import settings
from app.models.adt_payload import AdtPayload
from app.profiles.base import ProfileConfig
from app.valuesets.hl7_to_fhir_gender import map_gender

MR_TYPE_CODING = {
    "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
    "code": "MR",
}


def _hl7_date_to_iso(hl7_date: str) -> str:
    """Convert HL7 date YYYYMMDD to ISO YYYY-MM-DD."""
    cleaned = re.sub(r"[^0-9]", "", hl7_date)[:8]
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
    return hl7_date


def build_patient(payload: AdtPayload, profile: ProfileConfig) -> Patient:
    identifiers = [
        Identifier(
            system=settings.mrn_system,
            value=payload.mrn,
            type={"coding": [MR_TYPE_CODING]},
        )
    ]

    if payload.ihi:
        identifiers.append(
            Identifier(system=profile.national_id_system, value=payload.ihi)
        )

    given_names = [payload.name.given]
    if payload.name.middle:
        given_names.append(payload.name.middle)

    name = HumanName(
        use="official",
        family=payload.name.family,
        given=given_names,
        prefix=[payload.name.prefix] if payload.name.prefix else None,
    )

    address_kwargs: dict[str, object] = {
        "use": "home",
        "line": [payload.address.line],
        "city": payload.address.city,
        "postalCode": payload.address.postalCode,
        "country": payload.address.country or profile.default_country,
    }
    if payload.address.state:
        address_kwargs["state"] = payload.address.state
    address = Address(**address_kwargs)

    telecom = None
    if payload.phone:
        telecom = [ContactPoint(system="phone", use="mobile", value=payload.phone)]

    patient = Patient(
        meta={"profile": [profile.patient_profile_url]},
        text=Narrative(
            status="generated",
            div=f"<div xmlns=\"http://www.w3.org/1999/xhtml\">Patient MRN {payload.mrn}</div>",
        ),
        identifier=identifiers,
        active=True,
        name=[name],
        gender=map_gender(payload.gender),
        birthDate=_hl7_date_to_iso(payload.birthDate),
        address=[address],
        telecom=telecom,
    )

    return patient
