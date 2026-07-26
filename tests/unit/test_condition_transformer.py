from app.models.adt_payload import (
    AddressPayload,
    AdtPayload,
    DiagnosisPayload,
    NamePayload,
)
from app.profiles.au_profile import AU_PROFILE
from app.transformers.condition import (
    _hl7_datetime_to_iso,
    build_condition,
    build_conditions,
)


def _resource_type(resource) -> str | None:
    return getattr(resource, "__resource_type__", getattr(resource, "resource_type", None))


def _sample_diagnosis(**overrides) -> DiagnosisPayload:
    defaults = {
        "code": "O80",
        "display": "Encounter for full-term uncomplicated delivery",
        "codeSystem": "I10",
        "recordedDate": "20260527093000",
    }
    defaults.update(overrides)
    return DiagnosisPayload(**defaults)


def _sample_payload_with_diagnoses(
    diagnoses: list[DiagnosisPayload] | None = None,
) -> AdtPayload:
    return AdtPayload(
        correlationId="test-uuid-002",
        mrn="1234567",
        name=NamePayload(family="TEST", given="PATIENT"),
        birthDate="19920315",
        gender="F",
        address=AddressPayload(
            line="14 SAMPLE ST",
            city="SYDNEY",
            state="NSW",
            postalCode="2000",
        ),
        diagnoses=[_sample_diagnosis()] if diagnoses is None else diagnoses,
    )


class TestBuildCondition:
    def test_resource_type(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2", AU_PROFILE)
        assert _resource_type(cond) == "Condition"

    def test_subject_reference(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2", AU_PROFILE)
        assert cond.subject.reference == "Patient/2"

    def test_code_icd10am(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2", AU_PROFILE)
        coding = cond.code.coding[0]
        assert coding.code == "O80"
        assert coding.display == "Encounter for full-term uncomplicated delivery"
        assert coding.system == "http://hl7.org.au/fhir/CodeSystem/icd-10-am"

    def test_clinical_status_active(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2", AU_PROFILE)
        assert cond.clinicalStatus.coding[0].code == "active"

    def test_verification_status_confirmed(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2", AU_PROFILE)
        assert cond.verificationStatus.coding[0].code == "confirmed"

    def test_category_encounter_diagnosis(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2", AU_PROFILE)
        assert cond.category[0].coding[0].code == "encounter-diagnosis"

    def test_recorded_date(self):
        cond = build_condition(_sample_diagnosis(recordedDate="20260527093000"), "Patient/2", AU_PROFILE)
        assert cond.recordedDate.isoformat() == "2026-05-27T09:30:00+10:00"

    def test_no_recorded_date_when_empty(self):
        cond = build_condition(_sample_diagnosis(recordedDate=""), "Patient/2", AU_PROFILE)
        assert cond.recordedDate is None


class TestBuildConditions:
    def test_one_diagnosis(self):
        payload = _sample_payload_with_diagnoses([_sample_diagnosis()])
        conditions = build_conditions(payload, "Patient/2", AU_PROFILE)
        assert len(conditions) == 1

    def test_multiple_diagnoses(self):
        payload = _sample_payload_with_diagnoses(
            [
                _sample_diagnosis(code="O80", display="Normal delivery"),
                _sample_diagnosis(code="O48", display="Late pregnancy"),
            ]
        )
        conditions = build_conditions(payload, "Patient/2", AU_PROFILE)
        assert len(conditions) == 2
        assert conditions[0].code.coding[0].code == "O80"
        assert conditions[1].code.coding[0].code == "O48"

    def test_empty_diagnoses(self):
        payload = _sample_payload_with_diagnoses([])
        conditions = build_conditions(payload, "Patient/2", AU_PROFILE)
        assert len(conditions) == 0

    def test_all_reference_same_patient(self):
        payload = _sample_payload_with_diagnoses(
            [
                _sample_diagnosis(code="O80"),
                _sample_diagnosis(code="O48"),
            ]
        )
        conditions = build_conditions(payload, "Patient/99", AU_PROFILE)
        for cond in conditions:
            assert cond.subject.reference == "Patient/99"


class TestHl7DatetimeToIso:
    def test_full_datetime(self):
        assert _hl7_datetime_to_iso("20260527093000", AU_PROFILE.timezone_offset) == "2026-05-27T09:30:00+10:00"

    def test_date_only(self):
        assert _hl7_datetime_to_iso("20260527", AU_PROFILE.timezone_offset) == "2026-05-27"

    def test_short_string(self):
        assert _hl7_datetime_to_iso("202605", AU_PROFILE.timezone_offset) == "202605"
