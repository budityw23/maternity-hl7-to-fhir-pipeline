GENDER_MAP: dict[str, str] = {
    "F": "female",
    "M": "male",
    "O": "other",
    "U": "unknown",
    "A": "other",
    "N": "unknown",
}


def map_gender(hl7_gender: str) -> str:
    return GENDER_MAP.get(hl7_gender.upper(), "unknown")
