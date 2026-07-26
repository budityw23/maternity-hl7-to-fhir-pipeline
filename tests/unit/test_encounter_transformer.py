from app.models.orm_payload import (
    LocationPayload,
    OrmPayload,
    ParticipantPayload,
)
from app.profiles.au_profile import AU_PROFILE
from app.transformers.encounter import build_encounter
from app.valuesets.hl7_to_fhir_encounter import map_encounter_status, map_patient_class


def _resource_type(resource) -> str | None:
    return getattr(resource, "__resource_type__", getattr(resource, "resource_type", None))


def _resource_json(resource) -> dict:
    if hasattr(resource, "model_dump"):
        return resource.model_dump(mode="json", exclude_none=True)
    return resource.dict(by_alias=True, exclude_none=True)


def _sample_payload(**overrides) -> OrmPayload:
    defaults = {
        "correlationId": "test-uuid-003",
        "messageType": "ORM^O01",
        "mrn": "1234567",
        "visitNumber": "VN00012",
        "patientClass": "O",
        "admitDatetime": "20260420100000",
        "dischargeDatetime": "20260420110000",
        "location": LocationPayload(ward="MAT_CLINIC", room="OPD", facility="RPA"),
        "attendingDoctor": ParticipantPayload(id="DR_SMITH", familyName="SMITH", givenName="SARAH"),
        "orderControl": "NW",
        "serviceCode": "424525001",
        "serviceDisplay": "Antenatal care",
    }
    defaults.update(overrides)
    return OrmPayload(**defaults)


class TestBuildEncounter:
    def test_resource_type(self):
        enc = build_encounter(_sample_payload(), "Patient/2", AU_PROFILE)
        assert _resource_type(enc) == "Encounter"

    def test_subject_reference(self):
        enc = build_encounter(_sample_payload(), "Patient/2", AU_PROFILE)
        assert enc.subject.reference == "Patient/2"

    def test_visit_number_identifier(self):
        enc = build_encounter(_sample_payload(), "Patient/2", AU_PROFILE)
        assert enc.identifier[0].value == "VN00012"
        assert enc.identifier[0].system == "http://hospital.local/visit-number"

    def test_class_ambulatory(self):
        enc = build_encounter(_sample_payload(patientClass="O"), "Patient/2", AU_PROFILE)
        enc_dict = _resource_json(enc)
        enc_class = enc_dict.get("class")
        assert enc_class["code"] == "AMB"
        assert enc_class["system"] == "http://terminology.hl7.org/CodeSystem/v3-ActCode"

    def test_class_inpatient(self):
        enc = build_encounter(_sample_payload(patientClass="I"), "Patient/2", AU_PROFILE)
        enc_dict = _resource_json(enc)
        assert enc_dict["class"]["code"] == "IMP"

    def test_status_planned(self):
        enc = build_encounter(_sample_payload(orderControl="NW"), "Patient/2", AU_PROFILE)
        assert enc.status == "planned"

    def test_status_finished(self):
        enc = build_encounter(_sample_payload(orderControl="CM"), "Patient/2", AU_PROFILE)
        assert enc.status == "finished"

    def test_period_start(self):
        enc = build_encounter(_sample_payload(), "Patient/2", AU_PROFILE)
        assert enc.period.start.isoformat() == "2026-04-20T10:00:00+10:00"

    def test_period_end(self):
        enc = build_encounter(_sample_payload(), "Patient/2", AU_PROFILE)
        assert enc.period.end.isoformat() == "2026-04-20T11:00:00+10:00"

    def test_period_no_end(self):
        enc = build_encounter(_sample_payload(dischargeDatetime=""), "Patient/2", AU_PROFILE)
        assert enc.period.end is None

    def test_location_ward(self):
        enc = build_encounter(_sample_payload(), "Patient/2", AU_PROFILE)
        enc_dict = _resource_json(enc)
        loc = enc_dict["location"][0]["location"]
        assert loc["display"] == "MAT_CLINIC"

    def test_location_room(self):
        enc = build_encounter(_sample_payload(), "Patient/2", AU_PROFILE)
        enc_dict = _resource_json(enc)
        loc = enc_dict["location"][0]["location"]
        assert loc["identifier"]["value"] == "OPD"

    def test_participant_attender(self):
        enc = build_encounter(_sample_payload(), "Patient/2", AU_PROFILE)
        enc_dict = _resource_json(enc)
        part = enc_dict["participant"][0]
        assert part["type"][0]["coding"][0]["code"] == "ATND"
        assert part["individual"]["display"] == "SMITH, SARAH"
        assert part["individual"]["identifier"]["value"] == "DR_SMITH"

    def test_service_type_snomed(self):
        enc = build_encounter(_sample_payload(), "Patient/2", AU_PROFILE)
        coding = enc.serviceType.coding[0]
        assert coding.system == "http://snomed.info/sct"
        assert coding.code == "424525001"
        assert coding.display == "Antenatal care"

    def test_default_service_type(self):
        enc = build_encounter(_sample_payload(serviceCode=""), "Patient/2", AU_PROFILE)
        coding = enc.serviceType.coding[0]
        assert coding.code == "424525001"


class TestMapPatientClass:
    def test_outpatient(self):
        result = map_patient_class("O")
        assert result["code"] == "AMB"

    def test_inpatient(self):
        result = map_patient_class("I")
        assert result["code"] == "IMP"

    def test_emergency(self):
        result = map_patient_class("E")
        assert result["code"] == "EMER"

    def test_unknown_defaults_ambulatory(self):
        result = map_patient_class("Z")
        assert result["code"] == "AMB"


class TestMapEncounterStatus:
    def test_new_order(self):
        assert map_encounter_status("NW") == "planned"

    def test_in_progress(self):
        assert map_encounter_status("IP") == "in-progress"

    def test_completed(self):
        assert map_encounter_status("CM") == "finished"

    def test_cancelled(self):
        assert map_encounter_status("CA") == "cancelled"

    def test_unknown(self):
        assert map_encounter_status("XX") == "unknown"
