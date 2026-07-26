from app.profiles.base import ProfileConfig

EU_NATIONAL_ID_SYSTEMS: dict[str, tuple[str, str]] = {
    "uk": ("https://fhir.nhs.uk/Id/nhs-number", "NHS Number"),
    "nl": ("http://fhir.nl/fhir/NamingSystem/bsn", "BSN"),
    "de": ("http://fhir.de/sid/gkv/kvid-10", "KVNR"),
    "ie": ("https://fhir.ie/sid/ppsn", "PPS Number"),
}

EU_DEFAULT_ID_SYSTEM = "http://hl7.eu/fhir/base/NamingSystem/national-id"
EU_DEFAULT_ID_DISPLAY = "National ID"


def build_eu_profile(country: str = "") -> ProfileConfig:
    country_lower = country.lower().strip()
    if country_lower in EU_NATIONAL_ID_SYSTEMS:
        national_id_system, national_id_display = EU_NATIONAL_ID_SYSTEMS[country_lower]
    else:
        national_id_system = EU_DEFAULT_ID_SYSTEM
        national_id_display = EU_DEFAULT_ID_DISPLAY

    return ProfileConfig(
        region="eu",
        patient_profile_url="http://hl7.eu/fhir/base/StructureDefinition/patient-eu",
        condition_profile_url="http://hl7.eu/fhir/base/StructureDefinition/condition-eu-core",
        encounter_profile_url="http://hl7.org/fhir/StructureDefinition/Encounter",
        bp_observation_profile_url="http://hl7.org/fhir/StructureDefinition/bp",
        observation_profile_url="http://hl7.org/fhir/StructureDefinition/vitalsigns",
        national_id_system=national_id_system,
        national_id_display=national_id_display,
        diagnosis_code_system="http://hl7.org/fhir/sid/icd-10",
        snomed_system="http://snomed.info/sct",
        timezone_offset="+01:00",
        default_country=country_lower.upper() if country_lower else "EU",
        profile_definitions=[
            {
                "id": "patient-eu",
                "url": "http://hl7.eu/fhir/base/StructureDefinition/patient-eu",
                "name": "PatientEU",
                "type": "Patient",
            },
            {
                "id": "condition-eu-core",
                "url": "http://hl7.eu/fhir/base/StructureDefinition/condition-eu-core",
                "name": "ConditionEUCore",
                "type": "Condition",
            },
            {
                "id": "fhir-bp",
                "url": "http://hl7.org/fhir/StructureDefinition/bp",
                "name": "FHIRBloodPressure",
                "type": "Observation",
            },
        ],
    )
