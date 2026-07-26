"""Tests that FHIR resources include AU Base profile URLs."""

from app.models.adt_payload import (
    AddressPayload,
    AdtPayload,
    DiagnosisPayload,
    NamePayload,
)
from app.models.orm_payload import LocationPayload, OrmPayload, ParticipantPayload
from app.models.oru_payload import ObservationPayload
from app.profiles.au_profile import AU_PROFILE
from app.transformers.condition import build_condition
from app.transformers.encounter import build_encounter
from app.transformers.observation import _build_bp_panel_observation, _build_single_observation
from app.transformers.patient import build_patient


class TestPatientProfile:
    def _payload(self) -> AdtPayload:
        return AdtPayload(
            correlationId="test",
            mrn="123",
            name=NamePayload(family="Test", given="Pat"),
            birthDate="19900101",
            gender="F",
            address=AddressPayload(
                line="1 St", city="Sydney", state="NSW", postalCode="2000"
            ),
        )

    def test_patient_has_au_profile(self) -> None:
        patient = build_patient(self._payload(), AU_PROFILE)
        assert AU_PROFILE.patient_profile_url in patient.meta.profile


class TestConditionProfile:
    def test_condition_has_au_profile(self) -> None:
        diagnosis = DiagnosisPayload(code="O80", display="Normal delivery")
        condition = build_condition(diagnosis, "Patient/1", AU_PROFILE)
        assert AU_PROFILE.condition_profile_url in condition.meta.profile


class TestEncounterProfile:
    def _payload(self) -> OrmPayload:
        return OrmPayload(
            correlationId="test",
            mrn="123",
            visitNumber="VN001",
            patientClass="I",
            admitDatetime="20260420090000",
            location=LocationPayload(ward="Ward A"),
            attendingDoctor=ParticipantPayload(
                id="DR1", familyName="Smith", givenName="John"
            ),
        )

    def test_encounter_has_au_profile(self) -> None:
        encounter = build_encounter(self._payload(), "Patient/1", AU_PROFILE)
        assert AU_PROFILE.encounter_profile_url in encounter.meta.profile


class TestObservationProfiles:
    def _obs(self, code: str = "29463-7", display: str = "Weight") -> ObservationPayload:
        return ObservationPayload(
            setId=1, code=code, display=display, value=70.0, unitCode="kg"
        )

    def test_single_observation_no_special_profile(self) -> None:
        obs = _build_single_observation(self._obs(), "Patient/1", None, AU_PROFILE)
        assert obs.meta is None or not getattr(obs.meta, "profile", None)

    def test_bp_panel_has_au_bp_profile(self) -> None:
        sys_obs = self._obs("8480-6", "Systolic")
        dia_obs = self._obs("8462-4", "Diastolic")
        obs = _build_bp_panel_observation(sys_obs, dia_obs, "Patient/1", None, AU_PROFILE)
        assert AU_PROFILE.bp_observation_profile_url in obs.meta.profile
