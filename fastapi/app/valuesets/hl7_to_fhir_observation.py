OBX_STATUS_MAP: dict[str, str] = {
    "F": "final",
    "P": "preliminary",
    "C": "corrected",
    "R": "registered",
    "I": "registered",
    "D": "cancelled",
    "W": "entered-in-error",
    "X": "cancelled",
}


def map_observation_status(obx_status: str) -> str:
    return OBX_STATUS_MAP.get(obx_status.upper(), "unknown")


ABNORMAL_FLAG_MAP: dict[str, dict[str, str]] = {
    "N": {"code": "N", "display": "Normal"},
    "H": {"code": "H", "display": "High"},
    "L": {"code": "L", "display": "Low"},
    "HH": {"code": "HH", "display": "Critical high"},
    "LL": {"code": "LL", "display": "Critical low"},
    "A": {"code": "A", "display": "Abnormal"},
}

INTERPRETATION_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"


def map_abnormal_flag(flag: str) -> dict[str, str] | None:
    entry = ABNORMAL_FLAG_MAP.get(flag.upper())
    if not entry:
        return None
    return {
        "system": INTERPRETATION_SYSTEM,
        "code": entry["code"],
        "display": entry["display"],
    }


LOINC_SYSTEM = "http://loinc.org"
UCUM_SYSTEM = "http://unitsofmeasure.org"
VITAL_SIGNS_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"

BP_SYSTOLIC_CODE = "8480-6"
BP_DIASTOLIC_CODE = "8462-4"
BP_PANEL_CODE = "85354-9"
BP_PANEL_DISPLAY = "Blood pressure panel"
BP_CODES = {BP_SYSTOLIC_CODE, BP_DIASTOLIC_CODE}
