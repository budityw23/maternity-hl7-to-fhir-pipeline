import os
from unittest.mock import patch

from app.profiles.au_profile import AU_PROFILE
from app.profiles.eu_profile import build_eu_profile
from app.profiles.registry import get_profile


class TestGetProfile:
    @patch.dict(os.environ, {"PROFILE_REGION": "au"})
    def test_default_is_au(self):
        from app.config import Settings

        with patch("app.profiles.registry.settings", Settings()):
            profile = get_profile()
            assert profile.region == "au"

    @patch.dict(os.environ, {"PROFILE_REGION": "eu"})
    def test_eu_region(self):
        from app.config import Settings

        with patch("app.profiles.registry.settings", Settings()):
            from app.profiles.registry import get_profile as gp

            profile = gp()
            assert profile.region == "eu"

    def test_au_profile_values(self):
        assert AU_PROFILE.patient_profile_url == "http://hl7.org.au/fhir/StructureDefinition/au-patient"
        assert AU_PROFILE.condition_profile_url == "http://hl7.org.au/fhir/StructureDefinition/au-condition"
        assert AU_PROFILE.encounter_profile_url == "http://hl7.org.au/fhir/StructureDefinition/au-encounter"
        assert AU_PROFILE.bp_observation_profile_url == "http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure"
        assert AU_PROFILE.national_id_system == "http://ns.electronichealth.net.au/id/hi/ihi/1.0"
        assert AU_PROFILE.diagnosis_code_system == "http://hl7.org.au/fhir/CodeSystem/icd-10-am"
        assert AU_PROFILE.timezone_offset == "+10:00"
        assert AU_PROFILE.default_country == "AU"


class TestBuildEuProfile:
    def test_default_eu(self):
        profile = build_eu_profile()
        assert profile.region == "eu"
        assert profile.patient_profile_url == "http://hl7.eu/fhir/base/StructureDefinition/patient-eu"
        assert profile.condition_profile_url == "http://hl7.eu/fhir/base/StructureDefinition/condition-eu-core"
        assert profile.encounter_profile_url == "http://hl7.org/fhir/StructureDefinition/Encounter"
        assert profile.bp_observation_profile_url == "http://hl7.org/fhir/StructureDefinition/bp"
        assert profile.diagnosis_code_system == "http://hl7.org/fhir/sid/icd-10"
        assert profile.timezone_offset == "+01:00"
        assert profile.default_country == "EU"

    def test_uk_national_id(self):
        profile = build_eu_profile("uk")
        assert profile.national_id_system == "https://fhir.nhs.uk/Id/nhs-number"
        assert profile.national_id_display == "NHS Number"

    def test_nl_national_id(self):
        profile = build_eu_profile("nl")
        assert profile.national_id_system == "http://fhir.nl/fhir/NamingSystem/bsn"
        assert profile.national_id_display == "BSN"

    def test_de_national_id(self):
        profile = build_eu_profile("de")
        assert profile.national_id_system == "http://fhir.de/sid/gkv/kvid-10"
        assert profile.national_id_display == "KVNR"

    def test_ie_national_id(self):
        profile = build_eu_profile("ie")
        assert profile.national_id_system == "https://fhir.ie/sid/ppsn"
        assert profile.national_id_display == "PPS Number"

    def test_unknown_country_uses_generic(self):
        profile = build_eu_profile("fr")
        assert profile.national_id_system == "http://hl7.eu/fhir/base/NamingSystem/national-id"
        assert profile.national_id_display == "National ID"
        assert profile.default_country == "FR"

    def test_case_insensitive(self):
        profile = build_eu_profile("UK")
        assert profile.national_id_system == "https://fhir.nhs.uk/Id/nhs-number"


class TestProfileConfigFrozen:
    def test_immutable(self):
        try:
            AU_PROFILE.region = "eu"  # type: ignore[misc]
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass
