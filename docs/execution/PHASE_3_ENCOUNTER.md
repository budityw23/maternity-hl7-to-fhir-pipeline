# Phase 3: Encounter (from ORM^O01)

## Objective

Implement the ORM^O01 → FHIR R4 Encounter transformation. A new `POST /fhir/Encounter` endpoint receives flat JSON (as Mirth would send for an ORM message), transforms it into an Encounter resource linked to an existing Patient by MRN, and persists it to HAPI FHIR with visit-number-based idempotency.

## Pre-conditions

- Phase 2 complete — Patient + Condition pipeline working
- Patient with MRN `1234567` exists in HAPI (from Phase 1/2 testing)
- HAPI FHIR healthy

## Tasks

Execute in order.

---

### Task 1: Create `fastapi/app/models/orm_payload.py`

Pydantic model representing the flat JSON that Mirth sends for an ORM^O01 message.

```python
from pydantic import BaseModel


class ParticipantPayload(BaseModel):
    id: str
    familyName: str
    givenName: str


class LocationPayload(BaseModel):
    ward: str
    room: str = ""
    facility: str = ""


class OrmPayload(BaseModel):
    correlationId: str
    messageType: str = "ORM^O01"
    mrn: str
    visitNumber: str
    patientClass: str
    admitDatetime: str
    dischargeDatetime: str = ""
    location: LocationPayload
    attendingDoctor: ParticipantPayload
    orderControl: str = "NW"
    serviceCode: str = ""
    serviceDisplay: str = ""
```

---

### Task 2: Create `fastapi/app/valuesets/hl7_to_fhir_encounter.py`

Mapping tables for PV1 patient class → Encounter.class and ORC order control → Encounter.status.

```python
PATIENT_CLASS_MAP: dict[str, dict[str, str]] = {
    "I": {"code": "IMP", "display": "inpatient encounter"},
    "O": {"code": "AMB", "display": "ambulatory"},
    "E": {"code": "EMER", "display": "emergency"},
    "P": {"code": "PRENC", "display": "pre-admission"},
    "R": {"code": "IMP", "display": "inpatient encounter"},
    "B": {"code": "IMP", "display": "inpatient encounter"},
}

ENCOUNTER_CLASS_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"


def map_patient_class(hl7_class: str) -> dict[str, str]:
    entry = PATIENT_CLASS_MAP.get(hl7_class.upper(), {"code": "AMB", "display": "ambulatory"})
    return {
        "system": ENCOUNTER_CLASS_SYSTEM,
        "code": entry["code"],
        "display": entry["display"],
    }


ORDER_CONTROL_STATUS_MAP: dict[str, str] = {
    "NW": "planned",
    "IP": "in-progress",
    "CM": "finished",
    "CA": "cancelled",
    "SC": "planned",
    "XO": "planned",
}


def map_encounter_status(order_control: str) -> str:
    return ORDER_CONTROL_STATUS_MAP.get(order_control.upper(), "unknown")
```

---

### Task 3: Create `fastapi/app/transformers/encounter.py`

Transforms `OrmPayload` into a FHIR R4 Encounter resource.

**Field mapping reference** (from `docs/02_TECHNICAL_PLAN.md` §3.4):

| Source | Target | Notes |
|---|---|---|
| `payload.visitNumber` | `Encounter.identifier[0].value` | System: `http://hospital.local/visit-number` |
| `payload.patientClass` | `Encounter.class` | I→IMP, O→AMB, E→EMER via map |
| `payload.orderControl` | `Encounter.status` | NW→planned, IP→in-progress, CM→finished |
| `payload.admitDatetime` | `Encounter.period.start` | ISO 8601 with AEST |
| `payload.dischargeDatetime` | `Encounter.period.end` | ISO 8601 with AEST (if present) |
| `payload.location.ward` | `Encounter.location[0].location.display` | Ward name |
| `payload.location.room` | `Encounter.location[0].location.identifier.value` | Room number |
| `payload.attendingDoctor.*` | `Encounter.participant[0].individual.*` | Type: ATND |
| `payload.serviceCode` | `Encounter.serviceType.coding[0].code` | SNOMED code |
| Patient by MRN | `Encounter.subject.reference` | `Patient/{id}` |

```python
import re

from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.encounter import Encounter
from fhir.resources.identifier import Identifier
from fhir.resources.narrative import Narrative
from fhir.resources.period import Period
from fhir.resources.reference import Reference

from app.config import settings
from app.models.orm_payload import OrmPayload
from app.valuesets.hl7_to_fhir_encounter import map_encounter_status, map_patient_class

VISIT_NUMBER_SYSTEM = "http://hospital.local/visit-number"
PARTICIPATION_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ParticipationType"
SNOMED_SYSTEM = "http://snomed.info/sct"
ANTENATAL_CARE_CODE = "424525001"
ANTENATAL_CARE_DISPLAY = "Antenatal care"


def _hl7_datetime_to_iso(hl7_dt: str) -> str:
    """Convert HL7 datetime YYYYMMDDHHMMSS to ISO 8601 with AEST offset."""
    cleaned = re.sub(r"[^0-9]", "", hl7_dt)
    if len(cleaned) >= 14:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}T{cleaned[8:10]}:{cleaned[10:12]}:{cleaned[12:14]}+10:00"
    if len(cleaned) >= 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
    return hl7_dt


def build_encounter(
    payload: OrmPayload,
    patient_reference: str,
) -> Encounter:
    period_kwargs: dict[str, str] = {
        "start": _hl7_datetime_to_iso(payload.admitDatetime),
    }
    if payload.dischargeDatetime:
        period_kwargs["end"] = _hl7_datetime_to_iso(payload.dischargeDatetime)

    service_type = None
    if payload.serviceCode:
        service_type = CodeableConcept(
            coding=[
                Coding(
                    system=SNOMED_SYSTEM,
                    code=payload.serviceCode,
                    display=payload.serviceDisplay or payload.serviceCode,
                )
            ]
        )
    else:
        service_type = CodeableConcept(
            coding=[
                Coding(
                    system=SNOMED_SYSTEM,
                    code=ANTENATAL_CARE_CODE,
                    display=ANTENATAL_CARE_DISPLAY,
                )
            ]
        )

    location_entry = {
        "location": {
            "display": payload.location.ward,
        }
    }
    if payload.location.room:
        location_entry["location"]["identifier"] = {"value": payload.location.room}

    participant_entry = {
        "type": [
            {
                "coding": [
                    {
                        "system": PARTICIPATION_TYPE_SYSTEM,
                        "code": "ATND",
                        "display": "attender",
                    }
                ]
            }
        ],
        "individual": {
            "identifier": {"value": payload.attendingDoctor.id},
            "display": f"{payload.attendingDoctor.familyName}, {payload.attendingDoctor.givenName}",
        },
    }

    encounter = Encounter(
        text=Narrative(
            status="generated",
            div=f'<div xmlns="http://www.w3.org/1999/xhtml">Encounter {payload.visitNumber}</div>',
        ),
        status=map_encounter_status(payload.orderControl),
        identifier=[
            Identifier(system=VISIT_NUMBER_SYSTEM, value=payload.visitNumber)
        ],
        class_fhir=map_patient_class(payload.patientClass),
        serviceType=service_type,
        subject=Reference(reference=patient_reference),
        participant=[participant_entry],
        period=Period(**period_kwargs),
        location=[location_entry],
    )

    return encounter
```

**Note on `class_fhir`**: The `fhir.resources` library uses `class_fhir` as the Python attribute name for the FHIR `class` field (since `class` is a Python reserved word). It serializes to `"class"` in JSON automatically. If the library version uses a different alias (e.g., `class_` or you get a validation error), check the installed `fhir.resources` version and adjust the attribute name. The test in Task 5 will catch this.

---

### Task 4: Create `fastapi/app/clients/patient_resolver.py`

Resolves a Patient's HAPI FHIR ID from an MRN. Used by the Encounter endpoint to link `Encounter.subject` to an existing Patient.

```python
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def resolve_patient_id(http_client: httpx.AsyncClient, mrn: str) -> str | None:
    """Look up a Patient's FHIR ID by MRN.

    Returns the FHIR resource ID string, or None if not found.
    """
    url = f"{settings.hapi_base_url}/Patient"
    params = {"identifier": f"{settings.mrn_system}|{mrn}"}

    response = await http_client.get(url, params=params)
    if response.status_code != 200:
        logger.warning("Patient lookup failed: %s", response.status_code)
        return None

    bundle = response.json()
    total = bundle.get("total", 0)
    if total == 0:
        logger.warning("No Patient found for MRN=%s", mrn)
        return None

    entries = bundle.get("entry", [])
    if not entries:
        return None

    resource = entries[0].get("resource", {})
    return resource.get("id")
```

---

### Task 5: Update `fastapi/app/main.py`

Add the `POST /fhir/Encounter` endpoint. Keep existing endpoints unchanged.

Add imports at top:

```python
from app.clients.patient_resolver import resolve_patient_id
from app.models.orm_payload import OrmPayload
from app.transformers.encounter import build_encounter
```

Add this route after the `/fhir/Patient` endpoint:

```python
@app.post("/fhir/Encounter")
async def transform_encounter(payload: OrmPayload) -> dict[str, Any]:
    logger = logging.getLogger("app.fhir.encounter")
    logger.info(
        "Processing ORM^O01 for MRN=%s visitNumber=%s correlationId=%s",
        payload.mrn,
        payload.visitNumber,
        payload.correlationId,
    )

    patient_id = await resolve_patient_id(app.state.http_client, payload.mrn)
    if not patient_id:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"Patient not found for MRN={payload.mrn}. Send ADT^A01 first.",
        )

    patient_reference = f"Patient/{patient_id}"
    encounter = build_encounter(payload, patient_reference)
    encounter_data = encounter.model_dump(mode="json", exclude_none=True)

    hapi = HapiClient(app.state.http_client)
    identifier_query = f"{VISIT_NUMBER_SYSTEM}|{payload.visitNumber}"
    encounter_id = await hapi.upsert_resource(
        "Encounter", encounter_data, identifier_query
    )

    logger.info(
        "Encounter persisted id=%s correlationId=%s",
        encounter_id,
        payload.correlationId,
    )

    return {
        "encounterId": encounter_id,
        "correlationId": payload.correlationId,
    }
```

Also add the constant import near the top of the file:

```python
from app.transformers.encounter import VISIT_NUMBER_SYSTEM
```

The full updated `main.py` should have these routes:
1. `GET /health` (unchanged)
2. `POST /fhir/Patient` (unchanged from Phase 2)
3. `POST /fhir/Encounter` (new)

---

### Task 6: Create test fixture for ORM payload

**File**: `tests/fixtures/orm_o01_payload.json`

```json
{
    "correlationId": "660e8400-e29b-41d4-a716-446655440001",
    "messageType": "ORM^O01",
    "mrn": "1234567",
    "visitNumber": "VN00012",
    "patientClass": "O",
    "admitDatetime": "20260420100000",
    "dischargeDatetime": "20260420110000",
    "location": {
        "ward": "MAT_CLINIC",
        "room": "OPD",
        "facility": "RPA"
    },
    "attendingDoctor": {
        "id": "DR_SMITH",
        "familyName": "SMITH",
        "givenName": "SARAH"
    },
    "orderControl": "NW",
    "serviceCode": "424525001",
    "serviceDisplay": "Antenatal care"
}
```

---

### Task 7: Create `tests/unit/test_encounter_transformer.py`

```python
from app.models.orm_payload import (
    LocationPayload,
    OrmPayload,
    ParticipantPayload,
)
from app.transformers.encounter import _hl7_datetime_to_iso, build_encounter
from app.valuesets.hl7_to_fhir_encounter import map_encounter_status, map_patient_class


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
        "attendingDoctor": ParticipantPayload(
            id="DR_SMITH", familyName="SMITH", givenName="SARAH"
        ),
        "orderControl": "NW",
        "serviceCode": "424525001",
        "serviceDisplay": "Antenatal care",
    }
    defaults.update(overrides)
    return OrmPayload(**defaults)


class TestBuildEncounter:
    def test_resource_type(self):
        enc = build_encounter(_sample_payload(), "Patient/2")
        assert enc.__resource_type__ == "Encounter"

    def test_subject_reference(self):
        enc = build_encounter(_sample_payload(), "Patient/2")
        assert enc.subject.reference == "Patient/2"

    def test_visit_number_identifier(self):
        enc = build_encounter(_sample_payload(), "Patient/2")
        assert enc.identifier[0].value == "VN00012"
        assert enc.identifier[0].system == "http://hospital.local/visit-number"

    def test_class_ambulatory(self):
        enc = build_encounter(_sample_payload(patientClass="O"), "Patient/2")
        enc_dict = enc.model_dump(mode="json", exclude_none=True)
        enc_class = enc_dict.get("class")
        assert enc_class["code"] == "AMB"
        assert enc_class["system"] == "http://terminology.hl7.org/CodeSystem/v3-ActCode"

    def test_class_inpatient(self):
        enc = build_encounter(_sample_payload(patientClass="I"), "Patient/2")
        enc_dict = enc.model_dump(mode="json", exclude_none=True)
        assert enc_dict["class"]["code"] == "IMP"

    def test_status_planned(self):
        enc = build_encounter(_sample_payload(orderControl="NW"), "Patient/2")
        assert enc.status == "planned"

    def test_status_finished(self):
        enc = build_encounter(_sample_payload(orderControl="CM"), "Patient/2")
        assert enc.status == "finished"

    def test_period_start(self):
        enc = build_encounter(_sample_payload(), "Patient/2")
        assert enc.period.start.isoformat() == "2026-04-20T10:00:00+10:00"

    def test_period_end(self):
        enc = build_encounter(_sample_payload(), "Patient/2")
        assert enc.period.end.isoformat() == "2026-04-20T11:00:00+10:00"

    def test_period_no_end(self):
        enc = build_encounter(_sample_payload(dischargeDatetime=""), "Patient/2")
        assert enc.period.end is None

    def test_location_ward(self):
        enc = build_encounter(_sample_payload(), "Patient/2")
        enc_dict = enc.model_dump(mode="json", exclude_none=True)
        loc = enc_dict["location"][0]["location"]
        assert loc["display"] == "MAT_CLINIC"

    def test_location_room(self):
        enc = build_encounter(_sample_payload(), "Patient/2")
        enc_dict = enc.model_dump(mode="json", exclude_none=True)
        loc = enc_dict["location"][0]["location"]
        assert loc["identifier"]["value"] == "OPD"

    def test_participant_attender(self):
        enc = build_encounter(_sample_payload(), "Patient/2")
        enc_dict = enc.model_dump(mode="json", exclude_none=True)
        part = enc_dict["participant"][0]
        assert part["type"][0]["coding"][0]["code"] == "ATND"
        assert part["individual"]["display"] == "SMITH, SARAH"
        assert part["individual"]["identifier"]["value"] == "DR_SMITH"

    def test_service_type_snomed(self):
        enc = build_encounter(_sample_payload(), "Patient/2")
        coding = enc.serviceType.coding[0]
        assert coding.system == "http://snomed.info/sct"
        assert coding.code == "424525001"
        assert coding.display == "Antenatal care"

    def test_default_service_type(self):
        enc = build_encounter(_sample_payload(serviceCode=""), "Patient/2")
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
```

---

## Verification

```bash
# 1. Run all unit tests
venv/bin/python -m pytest tests/unit/ -v

# Expected: Phase 1 (19) + Phase 2 (15) + Phase 3 (~24) = ~58 tests pass

# 2. Rebuild FastAPI
docker compose up -d --build fastapi
sleep 10

# 3. Ensure Patient exists (re-send ADT if needed)
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/adt_a01_payload.json

# 4. Send ORM payload
curl -s -X POST http://localhost:8000/fhir/Encounter \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/orm_o01_payload.json

# Expected:
# {"encounterId": "<id>", "correlationId": "660e8400-e29b-41d4-a716-446655440001"}

# 5. Verify Encounter in HAPI
docker exec fastapi curl -s "http://hapi:8080/fhir/Encounter?identifier=http://hospital.local/visit-number%7CVN00012"

# Expected: Bundle with 1 Encounter entry:
#   - status = planned
#   - class.code = AMB
#   - subject.reference = Patient/2
#   - period.start = 2026-04-20T10:00:00+10:00
#   - period.end = 2026-04-20T11:00:00+10:00
#   - participant[0].individual.display = SMITH, SARAH
#   - serviceType = 424525001 (Antenatal care)
#   - location[0].location.display = MAT_CLINIC

# 6. Test idempotency
curl -s -X POST http://localhost:8000/fhir/Encounter \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/orm_o01_payload.json

# Same encounterId returned, no duplicate

# 7. Test missing Patient (should return 422)
curl -s -X POST http://localhost:8000/fhir/Encounter \
  -H "Content-Type: application/json" \
  -d '{"correlationId":"x","mrn":"9999999","visitNumber":"VN99","patientClass":"O","admitDatetime":"20260420100000","location":{"ward":"X"},"attendingDoctor":{"id":"DR_X","familyName":"X","givenName":"X"}}'

# Expected: 422 with "Patient not found for MRN=9999999"
```

## Definition of Done

- [ ] `POST /fhir/Encounter` accepts OrmPayload JSON and returns `{encounterId, correlationId}`
- [ ] Encounter has visit number identifier with correct system
- [ ] Encounter.class maps correctly (O→AMB, I→IMP, E→EMER)
- [ ] Encounter.status maps from order control (NW→planned, CM→finished)
- [ ] Encounter.period.start and .end are ISO 8601 with AEST +10:00
- [ ] Encounter.period.end is absent when dischargeDatetime is empty
- [ ] Encounter.subject references correct Patient (resolved by MRN)
- [ ] Encounter.participant has ATND type with doctor name and ID
- [ ] Encounter.serviceType has SNOMED antenatal care code
- [ ] Encounter.location has ward display and room identifier
- [ ] Idempotency: same visit number → same Encounter, no duplicate
- [ ] 422 returned when Patient MRN not found in HAPI
- [ ] Unit tests pass for encounter transformer + valueset mappings
- [ ] All Phase 1 + Phase 2 tests still pass

## Notes for Next Phase

Phase 4 will add simple Observation from ORU^R01 (single OBX segments: weight, fetal heart rate). Phase 5 then handles the BP panel merging (systolic + diastolic → composite Observation). These require:
- New `OruPayload` model with `observations[]` array
- New `POST /fhir/Observation/bundle` endpoint
- `observation.py` transformer
- Patient + Encounter resolution by MRN and visit number
