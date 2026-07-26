import re

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.meta import Meta
from fhir.resources.R4B.narrative import Narrative
from fhir.resources.R4B.observation import Observation, ObservationComponent
from fhir.resources.R4B.quantity import Quantity
from fhir.resources.R4B.reference import Reference

from app.models.oru_payload import ObservationPayload, OruPayload
from app.profiles.base import ProfileConfig
from app.valuesets.hl7_to_fhir_observation import (
    BP_DIASTOLIC_CODE,
    BP_PANEL_CODE,
    BP_PANEL_DISPLAY,
    BP_SYSTOLIC_CODE,
    LOINC_SYSTEM,
    UCUM_SYSTEM,
    VITAL_SIGNS_CATEGORY_SYSTEM,
    map_abnormal_flag,
    map_observation_status,
)


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


def _build_single_observation(
    obs: ObservationPayload,
    patient_reference: str,
    encounter_reference: str | None,
    profile: ProfileConfig,
) -> Observation:
    """Build a FHIR Observation from a single OBX segment."""
    category = [
        CodeableConcept(
            coding=[Coding(system=VITAL_SIGNS_CATEGORY_SYSTEM, code="vital-signs")]
        )
    ]

    code = CodeableConcept(
        coding=[Coding(system=LOINC_SYSTEM, code=obs.code, display=obs.display)]
    )

    value_quantity = None
    if obs.valueType == "NM":
        numeric_value = float(obs.value) if isinstance(obs.value, str) else obs.value
        value_quantity = Quantity(
            value=numeric_value,
            unit=obs.unitDisplay or obs.unitCode,
            system=UCUM_SYSTEM,
            code=obs.unitCode,
        )

    interpretation = None
    if obs.abnormalFlag:
        flag_coding = map_abnormal_flag(obs.abnormalFlag)
        if flag_coding:
            interpretation = [CodeableConcept(coding=[Coding(**flag_coding)])]

    reference_range = None
    if obs.referenceRange:
        reference_range = [{"text": obs.referenceRange}]

    encounter_ref = None
    if encounter_reference:
        encounter_ref = Reference(reference=encounter_reference)

    effective_dt = None
    if obs.observationDatetime:
        effective_dt = _hl7_datetime_to_iso(obs.observationDatetime, profile.timezone_offset)

    observation = Observation(
        text=Narrative(
            status="generated",
            div=f'<div xmlns="http://www.w3.org/1999/xhtml">Observation {obs.code}</div>',
        ),
        status=map_observation_status(obs.status),
        category=category,
        code=code,
        subject=Reference(reference=patient_reference),
        encounter=encounter_ref,
        effectiveDateTime=effective_dt,
        valueQuantity=value_quantity,
        interpretation=interpretation,
        referenceRange=reference_range,
    )

    return observation


def _build_bp_panel_observation(
    systolic: ObservationPayload,
    diastolic: ObservationPayload,
    patient_reference: str,
    encounter_reference: str | None,
    profile: ProfileConfig,
) -> Observation:
    """Build a BP panel Observation from paired systolic + diastolic OBX segments."""
    category = [
        CodeableConcept(
            coding=[Coding(system=VITAL_SIGNS_CATEGORY_SYSTEM, code="vital-signs")]
        )
    ]

    code = CodeableConcept(
        coding=[Coding(system=LOINC_SYSTEM, code=BP_PANEL_CODE, display=BP_PANEL_DISPLAY)]
    )

    def _make_component(obs: ObservationPayload) -> ObservationComponent:
        comp_code = CodeableConcept(
            coding=[Coding(system=LOINC_SYSTEM, code=obs.code, display=obs.display)]
        )
        numeric_value = float(obs.value) if isinstance(obs.value, str) else obs.value
        comp_value = Quantity(
            value=numeric_value,
            unit=obs.unitDisplay or obs.unitCode,
            system=UCUM_SYSTEM,
            code=obs.unitCode,
        )
        comp_interpretation = None
        if obs.abnormalFlag:
            flag_coding = map_abnormal_flag(obs.abnormalFlag)
            if flag_coding:
                comp_interpretation = [CodeableConcept(coding=[Coding(**flag_coding)])]

        return ObservationComponent(
            code=comp_code,
            valueQuantity=comp_value,
            interpretation=comp_interpretation,
        )

    components = [_make_component(systolic), _make_component(diastolic)]

    effective_src = systolic.observationDatetime or diastolic.observationDatetime
    effective_dt = _hl7_datetime_to_iso(effective_src, profile.timezone_offset) if effective_src else None

    status_priority = {"preliminary": 0, "registered": 1, "final": 2, "corrected": 3}
    sys_status = map_observation_status(systolic.status)
    dia_status = map_observation_status(diastolic.status)
    panel_status = (
        sys_status
        if status_priority.get(sys_status, 99) <= status_priority.get(dia_status, 99)
        else dia_status
    )

    panel_interpretation = None
    for obs_item in [systolic, diastolic]:
        if obs_item.abnormalFlag and obs_item.abnormalFlag.upper() not in ("N", ""):
            flag_coding = map_abnormal_flag(obs_item.abnormalFlag)
            if flag_coding:
                panel_interpretation = [CodeableConcept(coding=[Coding(**flag_coding)])]
                break

    encounter_ref = None
    if encounter_reference:
        encounter_ref = Reference(reference=encounter_reference)

    observation = Observation(
        meta=Meta(profile=[profile.bp_observation_profile_url]),
        text=Narrative(
            status="generated",
            div='<div xmlns="http://www.w3.org/1999/xhtml">Blood pressure panel</div>',
        ),
        status=panel_status,
        category=category,
        code=code,
        subject=Reference(reference=patient_reference),
        encounter=encounter_ref,
        effectiveDateTime=effective_dt,
        interpretation=panel_interpretation,
        component=components,
    )

    return observation


def build_observations(
    payload: OruPayload,
    patient_reference: str,
    encounter_reference: str | None,
    profile: ProfileConfig,
) -> list[Observation]:
    """Build Observation resources from ORU payload.

    Detects paired systolic (8480-6) + diastolic (8462-4) OBX segments
    and merges them into a single BP panel Observation (85354-9).
    All other OBX segments are built as individual Observations.
    """
    observations: list[Observation] = []
    bp_systolic: ObservationPayload | None = None
    bp_diastolic: ObservationPayload | None = None

    for obs in payload.observations:
        if obs.code == BP_SYSTOLIC_CODE:
            bp_systolic = obs
        elif obs.code == BP_DIASTOLIC_CODE:
            bp_diastolic = obs
        else:
            observations.append(
                _build_single_observation(obs, patient_reference, encounter_reference, profile)
            )

    if bp_systolic and bp_diastolic:
        observations.insert(
            0,
            _build_bp_panel_observation(
                bp_systolic, bp_diastolic, patient_reference, encounter_reference, profile
            ),
        )
    else:
        if bp_systolic:
            observations.append(
                _build_single_observation(bp_systolic, patient_reference, encounter_reference, profile)
            )
        if bp_diastolic:
            observations.append(
                _build_single_observation(bp_diastolic, patient_reference, encounter_reference, profile)
            )

    return observations
