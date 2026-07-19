PATIENT_CLASS_MAP: dict[str, dict[str, str]] = {
    "I": {"code": "IMP", "display": "inpatient encounter"},
    "O": {"code": "AMB", "display": "ambulatory"},
    "E": {"code": "EMER", "display": "emergency"},
    "P": {"code": "PRENC", "display": "pre-admission"},
    "R": {"code": "IMP", "display": "inpatient encounter"},
    "B": {"code": "IMP", "display": "inpatient encounter"},
}

ENCOUNTER_CLASS_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"


def map_patient_class(hl7_class: str) -> dict[str, str]:
    entry = PATIENT_CLASS_MAP.get(hl7_class.upper(), {"code": "AMB", "display": "ambulatory"})
    return {
        "system": ENCOUNTER_CLASS_SYSTEM,
        "code": entry["code"],
        "display": entry["display"],
    }


ORDER_CONTROL_STATUS_MAP: dict[str, str] = {
    "NW": "planned",
    "IP": "in-progress",
    "CM": "finished",
    "CA": "cancelled",
    "SC": "planned",
    "XO": "planned",
}


def map_encounter_status(order_control: str) -> str:
    return ORDER_CONTROL_STATUS_MAP.get(order_control.upper(), "unknown")
