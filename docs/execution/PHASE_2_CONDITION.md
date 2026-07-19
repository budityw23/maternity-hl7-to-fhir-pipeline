# Phase 2: Condition (from ADT^A01 DG1 Segments)

## Objective

Transform `diagnoses[]` from the ADT^A01 payload into FHIR R4 Condition resources linked to the Patient. Each DG1 segment becomes one Condition. The `POST /fhir/Patient` endpoint now creates Patient + Condition(s) together.

## Pre-conditions

- Phase 1 complete — `POST /fhir/Patient` creates Patient in HAPI
- `AdtPayload` already accepts `diagnoses: list[DiagnosisPayload]` (created in Phase 1, currently ignored)
- HAPI FHIR healthy

## Tasks

Execute in order.

---

### Task 1: Create `fastapi/app/transformers/condition.py`

Transforms `DiagnosisPayload` items into FHIR Condition resources.

**Field mapping reference** (from `docs/02_TECHNICAL_PLAN.md` §3.2):

| Source | Target | Notes |
|---|---|---|
| Patient reference | `Condition.subject.reference` | `Patient/{id}` resolved after Patient upsert |
| `diagnosis.code` | `Condition.code.coding[0].code` | ICD-10-AM code (e.g., `O80`) |
| `diagnosis.display` | `Condition.code.coding[0].display` | Diagnosis text |
| Constant | `Condition.code.coding[0].system` | `http://hl7.org.au/fhir/CodeSystem/icd-10-am` |
| `diagnosis.recordedDate` | `Condition.recordedDate` | ISO 8601 datetime |
| Constant | `Condition.clinicalStatus` | `active` |
| Constant | `Condition.verificationStatus` | `confirmed` |
| Constant | `Condition.category` | `encounter-diagnosis` |

```python
import re
from datetime import datetime

from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.condition import Condition
from fhir.resources.narrative import Narrative
from fhir.resources.reference import Reference

from app.models.adt_payload import AdtPayload, DiagnosisPayload

ICD10AM_SYSTEM = "http://hl7.org.au/fhir/CodeSystem/icd-10-am"
CLINICAL_STATUS_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-clinical"
VERIFICATION_STATUS_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-category"


def _hl7_datetime_to_iso(hl7_dt: str) -> str:
    """Convert HL7 datetime YYYYMMDDHHMMSS to ISO 8601 with AEST offset."""
    cleaned = re.sub(r"[^0-9]", "", hl7_dt)
    if len(cleaned) >= 14:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}T{cleaned[8:10]}:{cleaned[10:12]}:{cleaned[12:14]}+10:00"
    if len(cleaned) >= 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
    return hl7_dt


def build_condition(
    diagnosis: DiagnosisPayload,
    patient_reference: str,
) -> Condition:
    """Build a single FHIR Condition from a DiagnosisPayload.

    Args:
        diagnosis: Parsed DG1 segment data.
        patient_reference: FHIR reference string, e.g. "Patient/2".
    """
    condition = Condition(
        text=Narrative(
            status="generated",
            div=f'<div xmlns="http://www.w3.org/1999/xhtml">Condition {diagnosis.code}</div>',
        ),
        clinicalStatus=CodeableConcept(
            coding=[Coding(system=CLINICAL_STATUS_SYSTEM, code="active")]
        ),
        verificationStatus=CodeableConcept(
            coding=[Coding(system=VERIFICATION_STATUS_SYSTEM, code="confirmed")]
        ),
        category=[
            CodeableConcept(
                coding=[Coding(system=CATEGORY_SYSTEM, code="encounter-diagnosis")]
            )
        ],
        code=CodeableConcept(
            coding=[
                Coding(
                    system=ICD10AM_SYSTEM,
                    code=diagnosis.code,
                    display=diagnosis.display,
                )
            ]
        ),
        subject=Reference(reference=patient_reference),
    )

    if diagnosis.recordedDate:
        condition.recordedDate = _hl7_datetime_to_iso(diagnosis.recordedDate)

    return condition


def build_conditions(
    payload: AdtPayload,
    patient_reference: str,
) -> list[Condition]:
    """Build Condition resources for all diagnoses in an ADT payload."""
    return [
        build_condition(dx, patient_reference)
        for dx in payload.diagnoses
    ]
```

---

### Task 2: Update `fastapi/app/clients/hapi_client.py`

Add a method for creating Condition resources. Conditions use POST (not conditional PUT) because they don't have a natural business identifier for deduplication. Add a `create_resource` method alongside the existing `upsert_resource`.

Add this method to the `HapiClient` class:

```python
async def create_resource(
    self,
    resource_type: str,
    resource_data: dict[str, Any],
) -> str:
    """Create a new resource via POST. Returns server-assigned ID."""
    url = f"{self._base}/{resource_type}"
    headers = {"Content-Type": "application/fhir+json"}

    response = await self._client.post(
        url,
        json=resource_data,
        headers=headers,
    )

    if response.status_code not in (200, 201):
        logger.error(
            "HAPI create failed: %s %s", response.status_code, response.text
        )
        response.raise_for_status()

    location = response.headers.get("Location", "")
    if location:
        parts = [p for p in location.split("/") if p and p != "_history"]
        if parts:
            return parts[-1]

    body = response.json()
    if isinstance(body, dict) and body.get("id"):
        return str(body["id"])

    return "unknown"
```

---

### Task 3: Update `fastapi/app/main.py`

Modify the `transform_patient` endpoint to also create Condition resources from the `diagnoses[]` array after the Patient is persisted.

Add import at top:

```python
from app.transformers.condition import build_conditions
```

Update the `transform_patient` function — after `patient_id` is obtained, add Condition creation:

```python
@app.post("/fhir/Patient")
async def transform_patient(payload: AdtPayload) -> dict[str, Any]:
    logger = logging.getLogger("app.fhir.patient")
    logger.info(
        "Processing ADT^A01 for MRN=%s correlationId=%s",
        payload.mrn,
        payload.correlationId,
    )

    patient = build_patient(payload)
    patient_data = patient.model_dump(mode="json", exclude_none=True)

    hapi = HapiClient(app.state.http_client)
    await hapi.ensure_au_patient_profile()
    identifier_query = f"{settings.mrn_system}|{payload.mrn}"
    patient_id = await hapi.upsert_resource(
        "Patient", patient_data, identifier_query
    )

    logger.info(
        "Patient persisted id=%s correlationId=%s",
        patient_id,
        payload.correlationId,
    )

    condition_ids: list[str] = []
    if payload.diagnoses:
        patient_reference = f"Patient/{patient_id}"
        conditions = build_conditions(payload, patient_reference)
        for condition in conditions:
            condition_data = condition.model_dump(mode="json", exclude_none=True)
            cond_id = await hapi.create_resource("Condition", condition_data)
            condition_ids.append(cond_id)
            logger.info(
                "Condition persisted id=%s correlationId=%s",
                cond_id,
                payload.correlationId,
            )

    return {
        "patientId": patient_id,
        "conditionIds": condition_ids,
        "correlationId": payload.correlationId,
    }
```

**Key change**: Response now includes `conditionIds[]` array.

---

### Task 4: Create `tests/unit/test_condition_transformer.py`

```python
from app.models.adt_payload import (
    AddressPayload,
    AdtPayload,
    DiagnosisPayload,
    NamePayload,
)
from app.transformers.condition import (
    _hl7_datetime_to_iso,
    build_condition,
    build_conditions,
)


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
        diagnoses=diagnoses or [_sample_diagnosis()],
    )


class TestBuildCondition:
    def test_resource_type(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2")
        assert cond.__resource_type__ == "Condition"

    def test_subject_reference(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2")
        assert cond.subject.reference == "Patient/2"

    def test_code_icd10am(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2")
        coding = cond.code.coding[0]
        assert coding.code == "O80"
        assert coding.display == "Encounter for full-term uncomplicated delivery"
        assert coding.system == "http://hl7.org.au/fhir/CodeSystem/icd-10-am"

    def test_clinical_status_active(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2")
        assert cond.clinicalStatus.coding[0].code == "active"

    def test_verification_status_confirmed(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2")
        assert cond.verificationStatus.coding[0].code == "confirmed"

    def test_category_encounter_diagnosis(self):
        cond = build_condition(_sample_diagnosis(), "Patient/2")
        assert cond.category[0].coding[0].code == "encounter-diagnosis"

    def test_recorded_date(self):
        cond = build_condition(_sample_diagnosis(recordedDate="20260527093000"), "Patient/2")
        assert cond.recordedDate == "2026-05-27T09:30:00+10:00"

    def test_no_recorded_date_when_empty(self):
        cond = build_condition(_sample_diagnosis(recordedDate=""), "Patient/2")
        assert cond.recordedDate is None


class TestBuildConditions:
    def test_one_diagnosis(self):
        payload = _sample_payload_with_diagnoses([_sample_diagnosis()])
        conditions = build_conditions(payload, "Patient/2")
        assert len(conditions) == 1

    def test_multiple_diagnoses(self):
        payload = _sample_payload_with_diagnoses([
            _sample_diagnosis(code="O80", display="Normal delivery"),
            _sample_diagnosis(code="O48", display="Late pregnancy"),
        ])
        conditions = build_conditions(payload, "Patient/2")
        assert len(conditions) == 2
        assert conditions[0].code.coding[0].code == "O80"
        assert conditions[1].code.coding[0].code == "O48"

    def test_empty_diagnoses(self):
        payload = _sample_payload_with_diagnoses([])
        conditions = build_conditions(payload, "Patient/2")
        assert len(conditions) == 0

    def test_all_reference_same_patient(self):
        payload = _sample_payload_with_diagnoses([
            _sample_diagnosis(code="O80"),
            _sample_diagnosis(code="O48"),
        ])
        conditions = build_conditions(payload, "Patient/99")
        for cond in conditions:
            assert cond.subject.reference == "Patient/99"


class TestHl7DatetimeToIso:
    def test_full_datetime(self):
        assert _hl7_datetime_to_iso("20260527093000") == "2026-05-27T09:30:00+10:00"

    def test_date_only(self):
        assert _hl7_datetime_to_iso("20260527") == "2026-05-27"

    def test_short_string(self):
        assert _hl7_datetime_to_iso("202605") == "202605"
```

---

### Task 5: Update test fixture

Update `tests/fixtures/adt_a01_payload.json` to ensure it includes diagnoses (it should already from Phase 1, but verify the `diagnoses` array is present with at least one entry containing `code`, `display`, `codeSystem`, `recordedDate`).

The fixture should match this structure (keep existing fields, ensure diagnoses present):

```json
{
    "correlationId": "550e8400-e29b-41d4-a716-446655440000",
    "messageType": "ADT^A01",
    "mrn": "1234567",
    "ihi": "8003608166690503",
    "name": {
        "family": "TEST",
        "given": "PATIENT",
        "middle": "MARY",
        "prefix": "MS"
    },
    "birthDate": "19920315",
    "gender": "F",
    "address": {
        "line": "14 SAMPLE ST",
        "city": "SYDNEY",
        "state": "NSW",
        "postalCode": "2000",
        "country": "AU"
    },
    "phone": "0412345678",
    "diagnoses": [
        {
            "code": "O80",
            "display": "Encounter for full-term uncomplicated delivery",
            "codeSystem": "I10",
            "recordedDate": "20260527093000"
        }
    ]
}
```

---

## Verification

```bash
# 1. Run all unit tests (use project venv)
venv/bin/python -m pytest tests/unit/ -v

# Expected: All Phase 1 tests (19) + Phase 2 tests (~14) pass

# 2. Rebuild FastAPI
docker compose up -d --build fastapi
sleep 10

# 3. Reset HAPI data for clean test (optional but recommended)
# docker compose down hapi && docker volume rm maternity-hl7-to-fhir-pipeline_hapi-data && docker compose up -d
# OR just test with existing data — idempotent Patient, new Conditions

# 4. POST the ADT payload
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/adt_a01_payload.json

# Expected response includes conditionIds:
# {
#   "patientId": "2",
#   "conditionIds": ["<id>"],
#   "correlationId": "550e8400-e29b-41d4-a716-446655440000"
# }

# 5. Verify Condition in HAPI (from inside Docker)
docker exec fastapi curl -s "http://hapi:8080/fhir/Condition?subject=Patient/2"

# Expected: Bundle with 1+ Condition entries, each with:
#   - code.coding[0].code = "O80"
#   - code.coding[0].system = "http://hl7.org.au/fhir/CodeSystem/icd-10-am"
#   - subject.reference = "Patient/2"
#   - clinicalStatus = active
#   - verificationStatus = confirmed
#   - category = encounter-diagnosis
#   - recordedDate present

# 6. Verify Patient still exists and is unchanged
docker exec fastapi curl -s "http://hapi:8080/fhir/Patient/2" | python3 -c "import sys,json; p=json.load(sys.stdin); print(p['name'][0]['family'], p['identifier'][0]['value'])"

# Expected: TEST 1234567
```

## Definition of Done

- [ ] `condition.py` transformer creates valid FHIR Condition from DiagnosisPayload
- [ ] `hapi_client.py` has `create_resource()` method for POST
- [ ] `POST /fhir/Patient` response now includes `conditionIds[]`
- [ ] Condition has ICD-10-AM code system
- [ ] Condition has clinicalStatus=active, verificationStatus=confirmed
- [ ] Condition has category=encounter-diagnosis
- [ ] Condition.subject references the correct Patient
- [ ] Condition.recordedDate is ISO 8601 with AEST +10:00 offset
- [ ] Empty diagnoses array → no Conditions created, empty conditionIds
- [ ] Unit tests pass for condition transformer
- [ ] All Phase 1 tests still pass (no regression)

## Notes for Next Phase

Phase 3 will add Encounter from ORM^O01. This requires:
- New `OrmPayload` model
- New `POST /fhir/Encounter` endpoint
- `encounter.py` transformer
- PV1 field mapping (visit number, class, period, location, participant)
