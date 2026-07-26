from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProfileConfig:
    region: str
    patient_profile_url: str
    condition_profile_url: str
    encounter_profile_url: str
    bp_observation_profile_url: str
    observation_profile_url: str
    national_id_system: str
    national_id_display: str
    diagnosis_code_system: str
    snomed_system: str
    timezone_offset: str
    default_country: str
    profile_definitions: list[dict[str, str]] = field(default_factory=list)
