from app.models.adt_payload import AddressPayload, AdtPayload, NamePayload
from app.profiles.au_profile import AU_PROFILE
from app.transformers.patient import _hl7_date_to_iso, build_patient


def _resource_type(resource) -> str | None:
    return getattr(resource, "__resource_type__", getattr(resource, "resource_type", None))


def _sample_payload(**overrides) -> AdtPayload:
    defaults = {
        "correlationId": "test-uuid-001",
        "messageType": "ADT^A01",
        "mrn": "1234567",
        "ihi": "8003608166690503",
        "name": NamePayload(family="TEST", given="PATIENT", middle="MARY", prefix="MS"),
        "birthDate": "19920315",
        "gender": "F",
        "address": AddressPayload(
            line="14 SAMPLE ST",
            city="SYDNEY",
            state="NSW",
            postalCode="2000",
            country="AU",
        ),
        "phone": "0412345678",
    }
    defaults.update(overrides)
    return AdtPayload(**defaults)


class TestBuildPatient:
    def test_resource_type(self):
        patient = build_patient(_sample_payload(), AU_PROFILE)
        assert _resource_type(patient) == "Patient"

    def test_mrn_identifier(self):
        patient = build_patient(_sample_payload(), AU_PROFILE)
        mrn_id = patient.identifier[0]
        assert mrn_id.value == "1234567"
        assert mrn_id.system == "http://hospital.local/mrn"
        assert mrn_id.type.coding[0].code == "MR"

    def test_ihi_identifier(self):
        patient = build_patient(_sample_payload(), AU_PROFILE)
        assert len(patient.identifier) == 2
        ihi_id = patient.identifier[1]
        assert ihi_id.value == "8003608166690503"
        assert ihi_id.system == "http://ns.electronichealth.net.au/id/hi/ihi/1.0"

    def test_no_ihi_when_empty(self):
        patient = build_patient(_sample_payload(ihi=""), AU_PROFILE)
        assert len(patient.identifier) == 1

    def test_name(self):
        patient = build_patient(_sample_payload(), AU_PROFILE)
        name = patient.name[0]
        assert name.family == "TEST"
        assert name.given == ["PATIENT", "MARY"]
        assert name.prefix == ["MS"]
        assert name.use == "official"

    def test_name_no_middle(self):
        payload = _sample_payload(name=NamePayload(family="DOE", given="JANE", middle="", prefix=""))
        patient = build_patient(payload, AU_PROFILE)
        name = patient.name[0]
        assert name.given == ["JANE"]
        assert name.prefix is None

    def test_gender_female(self):
        patient = build_patient(_sample_payload(gender="F"), AU_PROFILE)
        assert patient.gender == "female"

    def test_gender_male(self):
        patient = build_patient(_sample_payload(gender="M"), AU_PROFILE)
        assert patient.gender == "male"

    def test_gender_unknown(self):
        patient = build_patient(_sample_payload(gender="U"), AU_PROFILE)
        assert patient.gender == "unknown"

    def test_birth_date(self):
        patient = build_patient(_sample_payload(birthDate="19920315"), AU_PROFILE)
        assert patient.birthDate.isoformat() == "1992-03-15"

    def test_address(self):
        patient = build_patient(_sample_payload(), AU_PROFILE)
        addr = patient.address[0]
        assert addr.line == ["14 SAMPLE ST"]
        assert addr.city == "SYDNEY"
        assert addr.state == "NSW"
        assert addr.postalCode == "2000"
        assert addr.country == "AU"
        assert addr.use == "home"

    def test_telecom(self):
        patient = build_patient(_sample_payload(), AU_PROFILE)
        phone = patient.telecom[0]
        assert phone.value == "0412345678"
        assert phone.system == "phone"
        assert phone.use == "mobile"

    def test_no_telecom_when_empty(self):
        patient = build_patient(_sample_payload(phone=""), AU_PROFILE)
        assert patient.telecom is None

    def test_active(self):
        patient = build_patient(_sample_payload(), AU_PROFILE)
        assert patient.active is True

    def test_au_base_profile(self):
        patient = build_patient(_sample_payload(), AU_PROFILE)
        assert "http://hl7.org.au/fhir/StructureDefinition/au-patient" in patient.meta.profile


class TestHl7DateToIso:
    def test_standard(self):
        assert _hl7_date_to_iso("19920315") == "1992-03-15"

    def test_with_time(self):
        assert _hl7_date_to_iso("19920315093000") == "1992-03-15"

    def test_already_iso(self):
        assert _hl7_date_to_iso("1992-03-15") == "1992-03-15"

    def test_short_date(self):
        assert _hl7_date_to_iso("199203") == "199203"
