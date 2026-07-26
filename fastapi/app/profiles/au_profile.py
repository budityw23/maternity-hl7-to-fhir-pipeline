from app.profiles.base import ProfileConfig

AU_PROFILE = ProfileConfig(
    region="au",
    patient_profile_url="http://hl7.org.au/fhir/StructureDefinition/au-patient",
    condition_profile_url="http://hl7.org.au/fhir/StructureDefinition/au-condition",
    encounter_profile_url="http://hl7.org.au/fhir/StructureDefinition/au-encounter",
    bp_observation_profile_url="http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure",
    observation_profile_url="http://hl7.org/fhir/StructureDefinition/vitalsigns",
    national_id_system="http://ns.electronichealth.net.au/id/hi/ihi/1.0",
    national_id_display="IHI",
    diagnosis_code_system="http://hl7.org.au/fhir/CodeSystem/icd-10-am",
    snomed_system="http://snomed.info/sct",
    timezone_offset="+10:00",
    default_country="AU",
    profile_definitions=[
        {
            "id": "au-patient",
            "url": "http://hl7.org.au/fhir/StructureDefinition/au-patient",
            "name": "AUPatient",
            "type": "Patient",
        },
        {
            "id": "au-condition",
            "url": "http://hl7.org.au/fhir/StructureDefinition/au-condition",
            "name": "AUCondition",
            "type": "Condition",
        },
        {
            "id": "au-encounter",
            "url": "http://hl7.org.au/fhir/StructureDefinition/au-encounter",
            "name": "AUEncounter",
            "type": "Encounter",
        },
        {
            "id": "au-vitalsigns-bloodpressure",
            "url": "http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure",
            "name": "AUVitalSignsBloodPressure",
            "type": "Observation",
        },
    ],
)
