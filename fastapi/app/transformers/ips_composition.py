import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

IPS_COMPOSITION_PROFILE = "http://hl7.org/fhir/uv/ips/StructureDefinition/Composition-uv-ips"
IPS_BUNDLE_PROFILE = "http://hl7.org/fhir/uv/ips/StructureDefinition/Bundle-uv-ips"
IPS_TYPE_CODE = "60591-5"
IPS_TYPE_DISPLAY = "Patient summary Document"
LOINC_SYSTEM = "http://loinc.org"

SECTION_CODES = {
    "allergies": {"code": "48765-2", "display": "Allergies and adverse reactions Document"},
    "medications": {"code": "10160-0", "display": "History of Medication use Narrative"},
    "problems": {"code": "11450-4", "display": "Problem list - Reported"},
    "results": {"code": "30954-2", "display": "Relevant diagnostic tests/laboratory data Narrative"},
    "vital_signs": {"code": "8716-3", "display": "Vital signs"},
    "pregnancy": {"code": "10162-6", "display": "History of pregnancies Narrative"},
}

PREGNANCY_SNOMED_CODES = {"77386006", "72892002", "169826009", "118185001"}
PREGNANCY_ICD10_PREFIXES = ("O",)


def _is_pregnancy_condition(condition: dict[str, Any]) -> bool:
    """Check if a Condition is pregnancy-related by SNOMED or ICD-10 code."""
    codings = condition.get("code", {}).get("coding", [])
    for coding in codings:
        code = coding.get("code", "")
        if code in PREGNANCY_SNOMED_CODES:
            return True
        if any(code.startswith(prefix) for prefix in PREGNANCY_ICD10_PREFIXES):
            return True
    return False


def _is_vital_sign(observation: dict[str, Any]) -> bool:
    """Check if an Observation is a vital sign by category."""
    categories = observation.get("category", [])
    for cat in categories:
        codings = cat.get("coding", [])
        for coding in codings:
            if coding.get("code") == "vital-signs":
                return True
    return False


def _make_section(
    title: str,
    section_key: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build an IPS Composition section."""
    section_code = SECTION_CODES[section_key]
    section: dict[str, Any] = {
        "title": title,
        "code": {
            "coding": [
                {
                    "system": LOINC_SYSTEM,
                    "code": section_code["code"],
                    "display": section_code["display"],
                }
            ]
        },
    }

    if entries:
        section["entry"] = [
            {"reference": f"{e['resourceType']}/{e['id']}"} for e in entries if e.get("id")
        ]
        section["text"] = {
            "status": "generated",
            "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{title}: {len(entries)} entries</div>',
        }
    else:
        section["emptyReason"] = {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/list-empty-reason",
                    "code": "notasked",
                    "display": "Not Asked",
                }
            ]
        }
        section["text"] = {
            "status": "generated",
            "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{title}: No data available</div>',
        }

    return section


def build_ips_bundle(
    patient: dict[str, Any],
    conditions: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    encounters: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a complete IPS Document Bundle."""
    patient_id = patient.get("id", "unknown")
    patient_ref = f"Patient/{patient_id}"
    now = datetime.now(UTC).isoformat()
    composition_id = str(uuid.uuid4())

    pregnancy_conditions = [c for c in conditions if _is_pregnancy_condition(c)]
    problem_conditions = conditions
    vital_signs = [o for o in observations if _is_vital_sign(o)]
    lab_results = [o for o in observations if not _is_vital_sign(o)]

    sections = [
        _make_section("Allergies and Intolerances", "allergies", []),
        _make_section("Medications", "medications", []),
        _make_section("Problems", "problems", problem_conditions),
        _make_section("Results", "results", lab_results),
        _make_section("Vital Signs", "vital_signs", vital_signs),
        _make_section("Pregnancy History", "pregnancy", pregnancy_conditions),
    ]

    composition: dict[str, Any] = {
        "resourceType": "Composition",
        "id": composition_id,
        "meta": {"profile": [IPS_COMPOSITION_PROFILE]},
        "status": "final",
        "type": {
            "coding": [
                {
                    "system": LOINC_SYSTEM,
                    "code": IPS_TYPE_CODE,
                    "display": IPS_TYPE_DISPLAY,
                }
            ]
        },
        "subject": {"reference": patient_ref},
        "date": now,
        "title": f"International Patient Summary for {patient_ref}",
        "author": [{"display": "Maternity FHIR Converter"}],
        "section": sections,
    }

    bundle_entries: list[dict[str, Any]] = [
        {"fullUrl": f"urn:uuid:{composition_id}", "resource": composition},
        {"fullUrl": f"urn:uuid:{patient_id}", "resource": patient},
    ]

    all_referenced = conditions + observations + encounters
    for resource in all_referenced:
        res_id = resource.get("id")
        if res_id:
            bundle_entries.append(
                {"fullUrl": f"urn:uuid:{res_id}", "resource": resource}
            )

    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "meta": {"profile": [IPS_BUNDLE_PROFILE]},
        "type": "document",
        "timestamp": now,
        "entry": bundle_entries,
    }

    logger.info(
        "IPS Bundle built for %s: %d conditions, %d observations, %d encounters",
        patient_ref,
        len(conditions),
        len(observations),
        len(encounters),
    )

    return bundle
