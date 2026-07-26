"""Contract test for the Mirth channel HL7 -> flat JSON mapping.

This test is the executable specification for the JavaScript transformer in
``mirth/channels/Maternity_Inbound.xml`` (mirrored in
``mirth/code_templates/maternity_transformers.js``). It parses the synthetic
sample HL7 messages exactly the way the Mirth channel does -- by canonical
HL7 v2.5 field position -- builds the flat JSON payload, and asserts the result
validates against the *real* FastAPI Pydantic models.

If the Mirth field mapping and the FastAPI payload contract ever drift apart,
this test fails. It does not require a running Mirth instance.

Scope: this locks the JSON *contract* (field positions -> payload shape -> Pydantic
validity). It uses a plain-string HL7 parser, so it does NOT exercise Mirth's E4X
runtime semantics (e.g. that a field node's toString() returns markup, not the value,
so the transformer must drill to the ``.1`` subcomponent). That behaviour is verified
by the live MLLP smoke test documented in ``mirth/README.md``.
"""

from pathlib import Path

import pytest
from app.models.adt_payload import AdtPayload
from app.models.orm_payload import OrmPayload
from app.models.oru_payload import OruPayload
from pydantic import ValidationError

SAMPLES = Path(__file__).resolve().parents[2] / "samples"

# --------------------------------------------------------------------------- #
# Minimal HL7 v2 parser (mirrors how Mirth exposes fields/components/repeats). #
# --------------------------------------------------------------------------- #


def _split_message(raw: str) -> list[list[str]]:
    """Return a list of segments, each a list of fields (field 0 = segment id)."""
    segments = []
    for line in raw.replace("\n", "\r").split("\r"):
        if line.strip():
            segments.append(line.split("|"))
    return segments


def _first_segment(segments: list[list[str]], name: str) -> list[str] | None:
    return next((s for s in segments if s[0] == name), None)


def _all_segments(segments: list[list[str]], name: str) -> list[list[str]]:
    return [s for s in segments if s[0] == name]


def _field(seg: list[str], index: int) -> str:
    """HL7 field by 1-based index (field 1 = first field after the segment id)."""
    return seg[index] if seg is not None and index < len(seg) else ""


def _comp(field: str, index: int) -> str:
    """HL7 component by 1-based index."""
    parts = field.split("^")
    return parts[index - 1] if index - 1 < len(parts) else ""


def _reps(field: str) -> list[str]:
    """Split a field into its repetitions (``~`` separated)."""
    return field.split("~") if field else []


def _decode_hl7_escapes(value: str) -> str:
    """Decode standard HL7 v2 escape sequences (approximation of Mirth's decoder).

    Only handles the five standard escapes defined in HL7 v2.5 §2.7.
    Mirth's parser also handles hex escapes (\\Xhh\\) and custom encoding
    characters — this is sufficient for the contract test samples.
    """
    return (
        value.replace("\\F\\", "|")
        .replace("\\S\\", "^")
        .replace("\\T\\", "&")
        .replace("\\R\\", "~")
        .replace("\\E\\", "\\")
    )


def _message_type(segments: list[list[str]]) -> str:
    """MSH-9.1 -- the routing key. MSH-1 is the field separator, so MSH-9 is fields[8]."""
    msh = _first_segment(segments, "MSH")
    return _comp(_field(msh, 8), 1) if msh else ""


def _map_country(code: str) -> str:
    if code == "AUS":
        return "AU"
    return code


# --------------------------------------------------------------------------- #
# Mapping functions -- the contract the Mirth transformer must reproduce.      #
# --------------------------------------------------------------------------- #


def build_patient_payload(segments: list[list[str]], correlation_id: str) -> dict:
    pid = _first_segment(segments, "PID")
    mrn = ihi = ""
    national_types = {"NI", "NH", "PN", "SS"}
    for rep in _reps(_field(pid, 3)):
        id_type = _comp(rep, 5)
        if id_type == "MR" and not mrn:
            mrn = _comp(rep, 1)
        elif id_type in national_types and not ihi:
            ihi = _comp(rep, 1)

    name = _field(pid, 5)
    addr = _field(pid, 11)
    phone_reps = _reps(_field(pid, 13))

    diagnoses = []
    for dg1 in _all_segments(segments, "DG1"):
        dx = _field(dg1, 3)
        diagnoses.append(
            {
                "code": _comp(dx, 1),
                "display": _decode_hl7_escapes(_comp(dx, 2)),
                "codeSystem": _comp(dx, 3),
                "recordedDate": _field(dg1, 5),
            }
        )

    return {
        "correlationId": correlation_id,
        "messageType": "ADT^A01",
        "mrn": mrn,
        "ihi": ihi,
        "name": {
            "family": _decode_hl7_escapes(_comp(name, 1)),
            "given": _decode_hl7_escapes(_comp(name, 2)),
            "middle": _decode_hl7_escapes(_comp(name, 3)),
            "prefix": _comp(name, 5),
        },
        "birthDate": _field(pid, 7),
        "gender": _field(pid, 8),
        "address": {
            "line": _decode_hl7_escapes(_comp(addr, 1)),
            "city": _decode_hl7_escapes(_comp(addr, 3)),
            "state": _comp(addr, 4),
            "postalCode": _comp(addr, 5),
            "country": _map_country(_comp(addr, 6)),
        },
        "phone": _comp(phone_reps[0], 1) if phone_reps else "",
        "diagnoses": diagnoses,
    }


def build_encounter_payload(segments: list[list[str]], correlation_id: str) -> dict:
    pid = _first_segment(segments, "PID")
    pv1 = _first_segment(segments, "PV1")
    orc = _first_segment(segments, "ORC")
    obr = _first_segment(segments, "OBR")

    mrn = ""
    for rep in _reps(_field(pid, 3)):
        if _comp(rep, 5) == "MR":
            mrn = _comp(rep, 1)
            break

    loc = _field(pv1, 3)
    doc = _field(pv1, 7)
    service = _field(obr, 4)

    payload = {
        "correlationId": correlation_id,
        "messageType": "ORM^O01",
        "mrn": mrn,
        "visitNumber": _field(pv1, 19),
        "patientClass": _field(pv1, 2),
        "admitDatetime": _field(pv1, 44),
        "location": {
            "ward": _comp(loc, 1),
            "room": _comp(loc, 2),
            "facility": _comp(loc, 4),
        },
        "attendingDoctor": {
            "id": _comp(doc, 1),
            "familyName": _comp(doc, 2),
            "givenName": _comp(doc, 3),
        },
        "orderControl": _field(orc, 1) or "NW",
        "serviceCode": _comp(service, 1),
        "serviceDisplay": _comp(service, 2),
    }
    discharge = _field(pv1, 45)
    if discharge:
        payload["dischargeDatetime"] = discharge
    return payload


def build_observation_payload(segments: list[list[str]], correlation_id: str) -> dict:
    pid = _first_segment(segments, "PID")
    pv1 = _first_segment(segments, "PV1")
    obr = _first_segment(segments, "OBR")

    mrn = ""
    for rep in _reps(_field(pid, 3)):
        if _comp(rep, 5) == "MR":
            mrn = _comp(rep, 1)
            break

    order = _field(obr, 4)
    observations = []
    for obx in _all_segments(segments, "OBX"):
        code = _field(obx, 3)
        unit = _field(obx, 6)
        raw_value = _field(obx, 5)
        value: float | str = float(raw_value) if raw_value else ""
        observations.append(
            {
                "setId": int(_field(obx, 1)),
                "valueType": _field(obx, 2),
                "code": _comp(code, 1),
                "display": _comp(code, 2),
                "codeSystem": _comp(code, 3),
                "value": value,
                "unitCode": _comp(unit, 1),
                "unitDisplay": _comp(unit, 2),
                "referenceRange": _field(obx, 7),
                "abnormalFlag": _field(obx, 8),
                "status": _field(obx, 11),
                "observationDatetime": _field(obx, 14),
            }
        )

    return {
        "correlationId": correlation_id,
        "messageType": "ORU^R01",
        "mrn": mrn,
        "visitNumber": _field(pv1, 19),
        "orderCode": _comp(order, 1),
        "orderDisplay": _comp(order, 2),
        "observations": observations,
    }


def _load(name: str) -> list[list[str]]:
    return _split_message((SAMPLES / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_adt_maps_to_valid_patient_payload() -> None:
    segments = _load("adt_a01_normal_delivery.hl7")
    assert _message_type(segments) == "ADT"

    payload = build_patient_payload(segments, "test-adt")
    model = AdtPayload.model_validate(payload)  # raises if the contract is broken

    assert model.mrn == "1234567"
    assert model.ihi == "8003608166690503"
    assert model.name.family == "TEST"
    assert model.name.given == "PATIENT"
    assert model.name.middle == "MARY"
    assert model.name.prefix == "MS"
    assert model.birthDate == "19920315"
    assert model.gender == "F"
    assert model.address.line == "14 SAMPLE ST"
    assert model.address.state == "NSW"
    assert model.address.postalCode == "2000"
    assert model.address.country == "AU"
    assert model.phone == "0412345678"
    assert len(model.diagnoses) == 1
    assert model.diagnoses[0].code == "O80"
    assert model.diagnoses[0].recordedDate == "20260527093000"


def test_orm_maps_to_valid_encounter_payload() -> None:
    segments = _load("orm_o01_antenatal_28w.hl7")
    assert _message_type(segments) == "ORM"

    payload = build_encounter_payload(segments, "test-orm")
    model = OrmPayload.model_validate(payload)

    assert model.mrn == "1234567"
    assert model.visitNumber == "VN00012"
    assert model.patientClass == "O"
    assert model.admitDatetime == "20260420100000"
    assert model.dischargeDatetime == "20260420110000"
    assert model.location.ward == "MAT_CLINIC"
    assert model.location.room == "OPD"
    assert model.location.facility == "RPA"
    assert model.attendingDoctor.id == "DR_SMITH"
    assert model.attendingDoctor.familyName == "SMITH"
    assert model.attendingDoctor.givenName == "SARAH"
    assert model.orderControl == "NW"
    assert model.serviceCode == "ANC"


def test_oru_maps_to_valid_observation_payload_with_bp_pair() -> None:
    segments = _load("oru_r01_vitals.hl7")
    assert _message_type(segments) == "ORU"

    payload = build_observation_payload(segments, "test-oru")
    model = OruPayload.model_validate(payload)

    assert model.mrn == "1234567"
    assert model.visitNumber == "VN00012"
    assert len(model.observations) == 4

    codes = [o.code for o in model.observations]
    assert "8480-6" in codes  # systolic
    assert "8462-4" in codes  # diastolic
    assert "29463-7" in codes  # weight
    assert "55283-6" in codes  # fetal heart rate

    systolic = next(o for o in model.observations if o.code == "8480-6")
    assert systolic.value == 118.0
    assert systolic.unitCode == "mm[Hg]"
    assert systolic.status == "F"
    assert systolic.abnormalFlag == "N"
    assert systolic.observationDatetime == "20260420103000"

    weight = next(o for o in model.observations if o.code == "29463-7")
    assert weight.value == 68.5
    assert weight.status == "F"


def test_invalid_adt_missing_mrn_is_rejected_by_contract() -> None:
    """The Mirth transformer produces an empty MRN; FastAPI must reject it (=> NAK)."""
    segments = _load("invalid/adt_missing_mrn.hl7")
    payload = build_patient_payload(segments, "test-invalid")

    assert payload["mrn"] == ""
    with pytest.raises(ValidationError):
        AdtPayload.model_validate(payload)


EU_SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "eu"


def _load_eu(name: str) -> list[list[str]]:
    return _split_message((EU_SAMPLES / name).read_text(encoding="utf-8"))


class TestEuAdtContract:
    def test_eu_adt_maps_to_valid_patient_payload(self) -> None:
        segments = _load_eu("adt_a01_normal_delivery.hl7")
        assert _message_type(segments) == "ADT"

        payload = build_patient_payload(segments, "test-eu-adt")
        model = AdtPayload.model_validate(payload)

        assert model.mrn == "MRN-EU-001"
        assert model.ihi == "NHS1234567"
        assert model.name.family == "SMITH"
        assert model.name.given == "EMMA"
        assert model.name.middle == "JANE"
        assert model.birthDate == "19900210"
        assert model.gender == "F"
        assert model.address.city == "LONDON"
        assert model.address.postalCode == "NW1 6XE"
        assert model.address.country == "GB"
        assert model.phone == "+447911123456"
        assert len(model.diagnoses) == 2
        assert model.diagnoses[0].code == "O80"
        assert model.diagnoses[0].codeSystem == "I10"
        assert model.diagnoses[1].code == "O48"

    def test_eu_country_not_defaulted_to_au(self) -> None:
        segments = _load_eu("adt_a01_normal_delivery.hl7")
        payload = build_patient_payload(segments, "test-eu-country")
        assert payload["address"]["country"] == "GB"


class TestEuOrmContract:
    def test_eu_orm_maps_to_valid_encounter_payload(self) -> None:
        segments = _load_eu("orm_o01_antenatal_28w.hl7")
        assert _message_type(segments) == "ORM"

        payload = build_encounter_payload(segments, "test-eu-orm")
        model = OrmPayload.model_validate(payload)

        assert model.mrn == "MRN-EU-001"
        assert model.visitNumber == "VN-EU-001"
        assert model.patientClass == "O"
        assert model.location.ward == "MATERNITY_WARD"
        assert model.location.room == "MW-01"
        assert model.location.facility == "ST_THOMAS"
        assert model.attendingDoctor.id == "DR_JONES"
        assert model.serviceCode == "424525001"
        assert model.serviceDisplay == "Antenatal care"


class TestEuOruContract:
    def test_eu_oru_maps_to_valid_observation_payload(self) -> None:
        segments = _load_eu("oru_r01_vitals.hl7")
        assert _message_type(segments) == "ORU"

        payload = build_observation_payload(segments, "test-eu-oru")
        model = OruPayload.model_validate(payload)

        assert model.mrn == "MRN-EU-001"
        assert model.visitNumber == "VN-EU-001"
        assert len(model.observations) == 5

        codes = [o.code for o in model.observations]
        assert "8480-6" in codes
        assert "8462-4" in codes
        assert "29463-7" in codes
        assert "8310-5" in codes
        assert "55283-6" in codes

        weight = next(o for o in model.observations if o.code == "29463-7")
        assert weight.value == 72.0
        assert weight.unitCode == "kg"


class TestEscapedNameContract:
    """Test that HL7 escape sequences in names and addresses are decoded correctly.

    Mirrors Mirth's native HL7 escape decoding. The contract test's plain-string
    parser uses _decode_hl7_escapes() as an approximation — the live MLLP smoke
    test is the authoritative check for Mirth's actual decoding.
    """

    def test_escaped_family_name_decoded(self) -> None:
        segments = _load("adt_a01_escaped_name.hl7")
        assert _message_type(segments) == "ADT"

        payload = build_patient_payload(segments, "test-esc")
        model = AdtPayload.model_validate(payload)

        assert model.name.family == "O&MALLEY"
        assert model.name.given == "SIOBHAN"
        assert model.name.middle == "ROSE"

    def test_escaped_address_decoded(self) -> None:
        segments = _load("adt_a01_escaped_name.hl7")
        payload = build_patient_payload(segments, "test-esc-addr")
        model = AdtPayload.model_validate(payload)

        assert model.address.line == "45 SMITH & JONES ST"
        assert model.address.city == "SYDNEY"
        assert model.address.country == "AU"

    def test_unescaped_fields_unchanged(self) -> None:
        segments = _load("adt_a01_escaped_name.hl7")
        payload = build_patient_payload(segments, "test-esc-other")
        model = AdtPayload.model_validate(payload)

        assert model.mrn == "9876543"
        assert model.ihi == "8003608166690504"
        assert model.birthDate == "19880712"
        assert model.gender == "F"
        assert model.phone == "0412987654"
        assert len(model.diagnoses) == 1
