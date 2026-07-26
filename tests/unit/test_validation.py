import pytest
from app.models.adt_payload import AdtPayload
from app.models.orm_payload import OrmPayload
from app.models.oru_payload import ObservationPayload, OruPayload
from pydantic import ValidationError


class TestAdtPayloadValidation:
    def _valid_adt(self, **overrides):
        defaults = {
            "correlationId": "test-uuid",
            "mrn": "1234567",
            "name": {"family": "Smith", "given": "Jane"},
            "birthDate": "19920315",
            "gender": "F",
            "address": {
                "line": "1 Test St",
                "city": "Sydney",
                "state": "NSW",
                "postalCode": "2000",
            },
        }
        defaults.update(overrides)
        return defaults

    def test_valid_payload(self):
        AdtPayload(**self._valid_adt())

    def test_empty_mrn_rejected(self):
        with pytest.raises(ValidationError, match="MRN"):
            AdtPayload(**self._valid_adt(mrn=""))

    def test_whitespace_mrn_rejected(self):
        with pytest.raises(ValidationError, match="MRN"):
            AdtPayload(**self._valid_adt(mrn="   "))

    def test_invalid_gender_rejected(self):
        with pytest.raises(ValidationError, match="gender"):
            AdtPayload(**self._valid_adt(gender="Z"))

    def test_empty_gender_accepted(self):
        payload = AdtPayload(**self._valid_adt(gender=""))
        assert payload.gender == ""

    def test_mrn_stripped(self):
        payload = AdtPayload(**self._valid_adt(mrn=" 1234567 "))
        assert payload.mrn == "1234567"


class TestOrmPayloadValidation:
    def _valid_orm(self, **overrides):
        defaults = {
            "correlationId": "test-uuid",
            "mrn": "1234567",
            "visitNumber": "VN00012",
            "patientClass": "O",
            "admitDatetime": "20260420090000",
            "location": {"ward": "Ward A"},
            "attendingDoctor": {
                "id": "DR1",
                "familyName": "Smith",
                "givenName": "John",
            },
            "orderControl": "NW",
        }
        defaults.update(overrides)
        return defaults

    def test_valid_payload(self):
        OrmPayload(**self._valid_orm())

    def test_empty_mrn_rejected(self):
        with pytest.raises(ValidationError, match="MRN"):
            OrmPayload(**self._valid_orm(mrn=""))

    def test_empty_visit_number_rejected(self):
        with pytest.raises(ValidationError, match="Visit number"):
            OrmPayload(**self._valid_orm(visitNumber=""))


class TestOruPayloadValidation:
    def _valid_obs(self, **overrides):
        defaults = {
            "setId": 1,
            "code": "29463-7",
            "display": "Body weight",
            "value": 68.5,
            "unitCode": "kg",
        }
        defaults.update(overrides)
        return defaults

    def test_valid_payload(self):
        OruPayload(
            correlationId="x",
            mrn="123",
            observations=[ObservationPayload(**self._valid_obs())],
        )

    def test_empty_mrn_rejected(self):
        with pytest.raises(ValidationError, match="MRN"):
            OruPayload(correlationId="x", mrn="", observations=[])

    def test_empty_observation_code_rejected(self):
        with pytest.raises(ValidationError, match="code"):
            ObservationPayload(**self._valid_obs(code=""))

    def test_empty_string_value_rejected(self):
        with pytest.raises(ValidationError, match="value"):
            ObservationPayload(**self._valid_obs(value=""))
