from app.models.adt_payload import AddressPayload, AdtPayload, DiagnosisPayload, NamePayload
from app.models.orm_payload import LocationPayload, OrmPayload, ParticipantPayload
from app.models.oru_payload import ObservationPayload, OruPayload
from app.profiles.eu_profile import build_eu_profile
from app.transformers.condition import build_condition
from app.transformers.encounter import build_encounter
from app.transformers.observation import _build_bp_panel_observation, build_observations
from app.transformers.patient import build_patient

EU_PROFILE = build_eu_profile("uk")


def _resource_json(resource) -> dict:
    if hasattr(resource, "model_dump"):
        return resource.model_dump(mode="json", exclude_none=True)
    return resource.dict(by_alias=True, exclude_none=True)


def _sample_adt(**overrides) -> AdtPayload:
    defaults = {
        "correlationId": "eu-test-001",
        "messageType": "ADT^A01",
        "mrn": "NHS1234567",
        "ihi": "9434765919",
        "name": NamePayload(family="SMITH", given="EMMA", middle="JANE", prefix="MRS"),
        "birthDate": "19900210",
        "gender": "F",
        "address": AddressPayload(
            line="42 BAKER STREET",
            city="LONDON",
            state="",
            postalCode="NW1 6XE",
            country="GB",
        ),
        "phone": "+447911123456",
    }
    defaults.update(overrides)
    return AdtPayload(**defaults)


def _sample_diagnosis(**overrides) -> DiagnosisPayload:
    defaults = {
        "code": "O80",
        "display": "Encounter for full-term uncomplicated delivery",
        "codeSystem": "I10",
        "recordedDate": "20260527093000",
    }
    defaults.update(overrides)
    return DiagnosisPayload(**defaults)


def _sample_orm(**overrides) -> OrmPayload:
    defaults = {
        "correlationId": "eu-test-002",
        "messageType": "ORM^O01",
        "mrn": "NHS1234567",
        "visitNumber": "VN-EU-001",
        "patientClass": "O",
        "admitDatetime": "20260420100000",
        "dischargeDatetime": "20260420110000",
        "location": LocationPayload(ward="MATERNITY_WARD", room="MW-01", facility="ST_THOMAS"),
        "attendingDoctor": ParticipantPayload(id="DR_JONES", familyName="JONES", givenName="SARAH"),
        "orderControl": "NW",
        "serviceCode": "424525001",
        "serviceDisplay": "Antenatal care",
    }
    defaults.update(overrides)
    return OrmPayload(**defaults)


def _sample_obs(**overrides) -> ObservationPayload:
    defaults = {
        "setId": 1,
        "valueType": "NM",
        "code": "29463-7",
        "display": "Body weight",
        "codeSystem": "LN",
        "value": 72.0,
        "unitCode": "kg",
        "unitDisplay": "kilogram",
        "referenceRange": "",
        "abnormalFlag": "N",
        "status": "F",
        "observationDatetime": "20260420103000",
    }
    defaults.update(overrides)
    return ObservationPayload(**defaults)


class TestEuPatient:
    def test_eu_profile_url(self):
        patient = build_patient(_sample_adt(), EU_PROFILE)
        assert "http://hl7.eu/fhir/base/StructureDefinition/patient-eu" in patient.meta.profile

    def test_nhs_number_identifier(self):
        patient = build_patient(_sample_adt(), EU_PROFILE)
        national_id = patient.identifier[1]
        assert national_id.system == "https://fhir.nhs.uk/Id/nhs-number"
        assert national_id.value == "9434765919"

    def test_country_gb(self):
        patient = build_patient(_sample_adt(), EU_PROFILE)
        assert patient.address[0].country == "GB"

    def test_default_country_uses_profile(self):
        patient = build_patient(
            _sample_adt(
                address=AddressPayload(
                    line="1 MAIN ST",
                    city="AMSTERDAM",
                    state="",
                    postalCode="1012",
                    country="",
                )
            ),
            EU_PROFILE,
        )
        assert patient.address[0].country == "UK"


class TestEuCondition:
    def test_eu_profile_url(self):
        cond = build_condition(_sample_diagnosis(), "Patient/10", EU_PROFILE)
        cond_dict = _resource_json(cond)
        assert "http://hl7.eu/fhir/base/StructureDefinition/condition-eu-core" in cond_dict["meta"]["profile"]

    def test_icd10_who_system(self):
        cond = build_condition(_sample_diagnosis(), "Patient/10", EU_PROFILE)
        assert cond.code.coding[0].system == "http://hl7.org/fhir/sid/icd-10"

    def test_timezone_cet(self):
        cond = build_condition(
            _sample_diagnosis(recordedDate="20260527093000"), "Patient/10", EU_PROFILE
        )
        assert "+01:00" in cond.recordedDate.isoformat()


class TestEuEncounter:
    def test_eu_profile_url(self):
        enc = build_encounter(_sample_orm(), "Patient/10", EU_PROFILE)
        enc_dict = _resource_json(enc)
        assert "http://hl7.org/fhir/StructureDefinition/Encounter" in enc_dict["meta"]["profile"]

    def test_timezone_cet(self):
        enc = build_encounter(_sample_orm(), "Patient/10", EU_PROFILE)
        assert "+01:00" in enc.period.start.isoformat()


class TestEuObservation:
    def test_bp_eu_profile_url(self):
        sys_obs = _sample_obs(code="8480-6", display="Systolic BP", value=120, unitCode="mm[Hg]")
        dia_obs = _sample_obs(code="8462-4", display="Diastolic BP", value=80, unitCode="mm[Hg]")
        obs = _build_bp_panel_observation(sys_obs, dia_obs, "Patient/10", None, EU_PROFILE)
        obs_dict = _resource_json(obs)
        assert "http://hl7.org/fhir/StructureDefinition/bp" in obs_dict["meta"]["profile"]

    def test_single_obs_timezone_cet(self):
        payload = OruPayload(
            correlationId="eu-test-003",
            mrn="NHS1234567",
            visitNumber="VN-EU-001",
            observations=[_sample_obs()],
        )
        results = build_observations(payload, "Patient/10", None, EU_PROFILE)
        assert "+01:00" in results[0].effectiveDateTime.isoformat()
