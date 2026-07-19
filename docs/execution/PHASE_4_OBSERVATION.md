# Phase 4: Observation — Simple (from ORU^R01)

## Objective

Implement ORU^R01 → FHIR R4 Observation transformation for simple (non-BP) vitals: body weight and fetal heart rate. A new `POST /fhir/Observation/bundle` endpoint receives an array of OBX-derived observations, transforms each into an Observation resource linked to Patient and Encounter, and persists them to HAPI FHIR.

**This phase handles single-OBX observations only.** Blood pressure panel merging (systolic + diastolic → composite) is Phase 5.

## Pre-conditions

- Phase 3 complete — Patient and Encounter exist in HAPI
- Patient MRN `1234567` and Encounter visit number `VN00012` exist
- HAPI FHIR healthy

## Tasks

Execute in order.

---

### Task 1: Create `fastapi/app/models/oru_payload.py`

Pydantic model representing the flat JSON that Mirth sends for an ORU^R01 message.

```python
from pydantic import BaseModel, Field


class ObservationPayload(BaseModel):
    setId: int
    valueType: str = "NM"
    code: str
    display: str
    codeSystem: str = "LN"
    value: float | str
    unitCode: str
    unitDisplay: str = ""
    referenceRange: str = ""
    abnormalFlag: str = ""
    status: str = "F"
    observationDatetime: str = ""


class OruPayload(BaseModel):
    correlationId: str
    messageType: str = "ORU^R01"
    mrn: str
    visitNumber: str = ""
    orderCode: str = ""
    orderDisplay: str = ""
    observations: list[ObservationPayload] = Field(default_factory=list)
```

---

### Task 2: Create `fastapi/app/valuesets/hl7_to_fhir_observation.py`

Mapping tables for OBX status and abnormal flags.

```python
OBX_STATUS_MAP: dict[str, str] = {
    "F": "final",
    "P": "preliminary",
    "C": "corrected",
    "R": "registered",
    "I": "registered",
    "D": "cancelled",
    "W": "entered-in-error",
    "X": "cancelled",
}


def map_observation_status(obx_status: str) -> str:
    return OBX_STATUS_MAP.get(obx_status.upper(), "unknown")


ABNORMAL_FLAG_MAP: dict[str, dict[str, str]] = {
    "N": {"code": "N", "display": "Normal"},
    "H": {"code": "H", "display": "High"},
    "L": {"code": "L", "display": "Low"},
    "HH": {"code": "HH", "display": "Critical high"},
    "LL": {"code": "LL", "display": "Critical low"},
    "A": {"code": "A", "display": "Abnormal"},
}

INTERPRETATION_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"


def map_abnormal_flag(flag: str) -> dict[str, str] | None:
    entry = ABNORMAL_FLAG_MAP.get(flag.upper())
    if not entry:
        return None
    return {
        "system": INTERPRETATION_SYSTEM,
        "code": entry["code"],
        "display": entry["display"],
    }


LOINC_SYSTEM = "http://loinc.org"
UCUM_SYSTEM = "http://unitsofmeasure.org"
VITAL_SIGNS_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"

BP_SYSTOLIC_CODE = "8480-6"
BP_DIASTOLIC_CODE = "8462-4"
BP_PANEL_CODE = "85354-9"
BP_PANEL_DISPLAY = "Blood pressure panel"
BP_CODES = {BP_SYSTOLIC_CODE, BP_DIASTOLIC_CODE}
```

---

### Task 3: Create `fastapi/app/transformers/observation.py`

Transforms `ObservationPayload` items into FHIR R4 Observation resources. This phase builds simple (non-BP) observations only. BP panel merging is added in Phase 5.

**Field mapping reference** (from `docs/02_TECHNICAL_PLAN.md` §3.3):

| Source | Target |
|---|---|
| `obs.code` | `Observation.code.coding[0].code` (LOINC) |
| `obs.display` | `Observation.code.coding[0].display` |
| `obs.value` | `Observation.valueQuantity.value` |
| `obs.unitCode` | `Observation.valueQuantity.code` (UCUM) |
| `obs.unitDisplay` | `Observation.valueQuantity.unit` |
| `obs.referenceRange` | `Observation.referenceRange[0].text` |
| `obs.abnormalFlag` | `Observation.interpretation[0].coding[0]` |
| `obs.status` | `Observation.status` (F→final, P→preliminary) |
| `obs.observationDatetime` | `Observation.effectiveDateTime` |
| Patient reference | `Observation.subject.reference` |
| Encounter reference | `Observation.encounter.reference` |
| Constant | `Observation.category` = vital-signs |

```python
import re

from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.narrative import Narrative
from fhir.resources.observation import Observation
from fhir.resources.quantity import Quantity
from fhir.resources.reference import Reference

from app.models.oru_payload import ObservationPayload, OruPayload
from app.valuesets.hl7_to_fhir_observation import (
    BP_CODES,
    LOINC_SYSTEM,
    UCUM_SYSTEM,
    VITAL_SIGNS_CATEGORY_SYSTEM,
    map_abnormal_flag,
    map_observation_status,
)


def _hl7_datetime_to_iso(hl7_dt: str) -> str:
    """Convert HL7 datetime YYYYMMDDHHMMSS to ISO 8601 with AEST offset."""
    cleaned = re.sub(r"[^0-9]", "", hl7_dt)
    if len(cleaned) >= 14:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}T{cleaned[8:10]}:{cleaned[10:12]}:{cleaned[12:14]}+10:00"
    if len(cleaned) >= 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
    return hl7_dt


def _build_single_observation(
    obs: ObservationPayload,
    patient_reference: str,
    encounter_reference: str | None,
) -> Observation:
    """Build a FHIR Observation from a single OBX segment."""
    category = [
        CodeableConcept(
            coding=[Coding(system=VITAL_SIGNS_CATEGORY_SYSTEM, code="vital-signs")]
        )
    ]

    code = CodeableConcept(
        coding=[Coding(system=LOINC_SYSTEM, code=obs.code, display=obs.display)]
    )

    value_quantity = None
    if obs.valueType == "NM":
        numeric_value = float(obs.value) if isinstance(obs.value, str) else obs.value
        value_quantity = Quantity(
            value=numeric_value,
            unit=obs.unitDisplay or obs.unitCode,
            system=UCUM_SYSTEM,
            code=obs.unitCode,
        )

    interpretation = None
    if obs.abnormalFlag:
        flag_coding = map_abnormal_flag(obs.abnormalFlag)
        if flag_coding:
            interpretation = [CodeableConcept(coding=[Coding(**flag_coding)])]

    reference_range = None
    if obs.referenceRange:
        reference_range = [{"text": obs.referenceRange}]

    encounter_ref = None
    if encounter_reference:
        encounter_ref = Reference(reference=encounter_reference)

    effective_dt = None
    if obs.observationDatetime:
        effective_dt = _hl7_datetime_to_iso(obs.observationDatetime)

    observation = Observation(
        text=Narrative(
            status="generated",
            div=f'<div xmlns="http://www.w3.org/1999/xhtml">Observation {obs.code}</div>',
        ),
        status=map_observation_status(obs.status),
        category=category,
        code=code,
        subject=Reference(reference=patient_reference),
        encounter=encounter_ref,
        effectiveDateTime=effective_dt,
        valueQuantity=value_quantity,
        interpretation=interpretation,
        referenceRange=reference_range,
    )

    return observation


def build_observations(
    payload: OruPayload,
    patient_reference: str,
    encounter_reference: str | None = None,
) -> list[Observation]:
    """Build Observation resources from ORU payload.

    Simple observations (non-BP) are built individually.
    BP panel merging is handled in Phase 5.
    """
    observations: list[Observation] = []

    for obs in payload.observations:
        if obs.code in BP_CODES:
            # Phase 5 will handle BP panel merging.
            # For now, build them individually.
            observations.append(
                _build_single_observation(obs, patient_reference, encounter_reference)
            )
        else:
            observations.append(
                _build_single_observation(obs, patient_reference, encounter_reference)
            )

    return observations
```

---

### Task 4: Create `fastapi/app/clients/encounter_resolver.py`

Resolves an Encounter's HAPI FHIR ID from a visit number. Used by the Observation endpoint to link `Observation.encounter`.

```python
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VISIT_NUMBER_SYSTEM = "http://hospital.local/visit-number"


async def resolve_encounter_id(
    http_client: httpx.AsyncClient, visit_number: str
) -> str | None:
    """Look up an Encounter's FHIR ID by visit number.

    Returns the FHIR resource ID string, or None if not found.
    """
    url = f"{settings.hapi_base_url}/Encounter"
    params = {"identifier": f"{VISIT_NUMBER_SYSTEM}|{visit_number}"}

    response = await http_client.get(url, params=params)
    if response.status_code != 200:
        logger.warning("Encounter lookup failed: %s", response.status_code)
        return None

    bundle = response.json()
    total = bundle.get("total", 0)
    if total == 0:
        logger.warning("No Encounter found for visit_number=%s", visit_number)
        return None

    entries = bundle.get("entry", [])
    if not entries:
        return None

    resource = entries[0].get("resource", {})
    encounter_id = resource.get("id")
    return str(encounter_id) if encounter_id else None
```

---

### Task 5: Update `fastapi/app/main.py`

Add the `POST /fhir/Observation/bundle` endpoint. Keep existing endpoints unchanged.

Add imports at top:

```python
from app.clients.encounter_resolver import resolve_encounter_id
from app.models.oru_payload import OruPayload
from app.transformers.observation import build_observations
```

Add this route after the `/fhir/Encounter` endpoint:

```python
@app.post("/fhir/Observation/bundle")
async def transform_observations(payload: OruPayload) -> dict[str, Any]:
    logger = logging.getLogger("app.fhir.observation")
    logger.info(
        "Processing ORU^R01 for MRN=%s visitNumber=%s correlationId=%s",
        payload.mrn,
        payload.visitNumber,
        payload.correlationId,
    )

    patient_id = await resolve_patient_id(app.state.http_client, payload.mrn)
    if not patient_id:
        raise HTTPException(
            status_code=422,
            detail=f"Patient not found for MRN={payload.mrn}. Send ADT^A01 first.",
        )
    patient_reference = f"Patient/{patient_id}"

    encounter_reference: str | None = None
    if payload.visitNumber:
        encounter_id = await resolve_encounter_id(
            app.state.http_client, payload.visitNumber
        )
        if encounter_id:
            encounter_reference = f"Encounter/{encounter_id}"

    observations = build_observations(
        payload, patient_reference, encounter_reference
    )

    hapi = HapiClient(app.state.http_client)
    observation_ids: list[str] = []
    for obs in observations:
        obs_data = _resource_to_json(obs)
        obs_id = await hapi.create_resource("Observation", obs_data)
        observation_ids.append(obs_id)
        logger.info(
            "Observation persisted id=%s correlationId=%s",
            obs_id,
            payload.correlationId,
        )

    return {
        "observationIds": observation_ids,
        "correlationId": payload.correlationId,
    }
```

The full `main.py` should have these routes after this task:
1. `GET /health` (unchanged)
2. `POST /fhir/Patient` (unchanged)
3. `POST /fhir/Encounter` (unchanged)
4. `POST /fhir/Observation/bundle` (new)

---

### Task 6: Create test fixture for ORU payload

**File**: `tests/fixtures/oru_r01_payload.json`

```json
{
    "correlationId": "770e8400-e29b-41d4-a716-446655440002",
    "messageType": "ORU^R01",
    "mrn": "1234567",
    "visitNumber": "VN00012",
    "orderCode": "ANC",
    "orderDisplay": "Antenatal Checkup",
    "observations": [
        {
            "setId": 1,
            "valueType": "NM",
            "code": "8480-6",
            "display": "Systolic blood pressure",
            "codeSystem": "LN",
            "value": 118,
            "unitCode": "mm[Hg]",
            "unitDisplay": "millimeters of mercury",
            "referenceRange": "90-140",
            "abnormalFlag": "N",
            "status": "F",
            "observationDatetime": "20260420103000"
        },
        {
            "setId": 2,
            "valueType": "NM",
            "code": "8462-4",
            "display": "Diastolic blood pressure",
            "codeSystem": "LN",
            "value": 76,
            "unitCode": "mm[Hg]",
            "unitDisplay": "millimeters of mercury",
            "referenceRange": "60-90",
            "abnormalFlag": "N",
            "status": "F",
            "observationDatetime": "20260420103000"
        },
        {
            "setId": 3,
            "valueType": "NM",
            "code": "29463-7",
            "display": "Body weight",
            "codeSystem": "LN",
            "value": 68.5,
            "unitCode": "kg",
            "unitDisplay": "kilogram",
            "referenceRange": "",
            "abnormalFlag": "N",
            "status": "F",
            "observationDatetime": "20260420103000"
        },
        {
            "setId": 4,
            "valueType": "NM",
            "code": "55283-6",
            "display": "Fetal heart rate",
            "codeSystem": "LN",
            "value": 145,
            "unitCode": "/min",
            "unitDisplay": "per minute",
            "referenceRange": "110-160",
            "abnormalFlag": "N",
            "status": "F",
            "observationDatetime": "20260420103000"
        }
    ]
}
```

---

### Task 7: Create `tests/unit/test_observation_transformer.py`

```python
from app.models.oru_payload import ObservationPayload, OruPayload
from app.transformers.observation import (
    _build_single_observation,
    _hl7_datetime_to_iso,
    build_observations,
)
from app.valuesets.hl7_to_fhir_observation import (
    map_abnormal_flag,
    map_observation_status,
)


def _sample_obs(**overrides) -> ObservationPayload:
    defaults = {
        "setId": 1,
        "valueType": "NM",
        "code": "29463-7",
        "display": "Body weight",
        "codeSystem": "LN",
        "value": 68.5,
        "unitCode": "kg",
        "unitDisplay": "kilogram",
        "referenceRange": "",
        "abnormalFlag": "N",
        "status": "F",
        "observationDatetime": "20260420103000",
    }
    defaults.update(overrides)
    return ObservationPayload(**defaults)


def _sample_payload(observations: list[ObservationPayload] | None = None) -> OruPayload:
    return OruPayload(
        correlationId="test-uuid-004",
        mrn="1234567",
        visitNumber="VN00012",
        observations=observations if observations is not None else [_sample_obs()],
    )


class TestBuildSingleObservation:
    def test_resource_type(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", "Encounter/4")
        assert obs.__resource_type__ == "Observation"

    def test_status_final(self):
        obs = _build_single_observation(_sample_obs(status="F"), "Patient/2", None)
        assert obs.status == "final"

    def test_status_preliminary(self):
        obs = _build_single_observation(_sample_obs(status="P"), "Patient/2", None)
        assert obs.status == "preliminary"

    def test_category_vital_signs(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None)
        assert obs.category[0].coding[0].code == "vital-signs"

    def test_code_loinc(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None)
        coding = obs.code.coding[0]
        assert coding.system == "http://loinc.org"
        assert coding.code == "29463-7"
        assert coding.display == "Body weight"

    def test_value_quantity(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None)
        vq = obs.valueQuantity
        assert vq.value == 68.5
        assert vq.code == "kg"
        assert vq.unit == "kilogram"
        assert vq.system == "http://unitsofmeasure.org"

    def test_subject_reference(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None)
        assert obs.subject.reference == "Patient/2"

    def test_encounter_reference(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", "Encounter/4")
        assert obs.encounter.reference == "Encounter/4"

    def test_no_encounter_reference(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None)
        assert obs.encounter is None

    def test_effective_datetime(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None)
        assert obs.effectiveDateTime.isoformat() == "2026-04-20T10:30:00+10:00"

    def test_no_effective_datetime(self):
        obs = _build_single_observation(
            _sample_obs(observationDatetime=""), "Patient/2", None
        )
        assert obs.effectiveDateTime is None

    def test_interpretation_normal(self):
        obs = _build_single_observation(_sample_obs(abnormalFlag="N"), "Patient/2", None)
        assert obs.interpretation[0].coding[0].code == "N"
        assert obs.interpretation[0].coding[0].display == "Normal"

    def test_interpretation_high(self):
        obs = _build_single_observation(_sample_obs(abnormalFlag="H"), "Patient/2", None)
        assert obs.interpretation[0].coding[0].code == "H"

    def test_no_interpretation(self):
        obs = _build_single_observation(
            _sample_obs(abnormalFlag=""), "Patient/2", None
        )
        assert obs.interpretation is None

    def test_reference_range(self):
        obs = _build_single_observation(
            _sample_obs(referenceRange="50-100"), "Patient/2", None
        )
        obs_dict = obs.model_dump(mode="json", exclude_none=True)
        assert obs_dict["referenceRange"][0]["text"] == "50-100"

    def test_no_reference_range(self):
        obs = _build_single_observation(
            _sample_obs(referenceRange=""), "Patient/2", None
        )
        assert obs.referenceRange is None

    def test_fetal_heart_rate(self):
        obs = _build_single_observation(
            _sample_obs(code="55283-6", display="Fetal heart rate", value=145, unitCode="/min", unitDisplay="per minute"),
            "Patient/2",
            None,
        )
        assert obs.code.coding[0].code == "55283-6"
        assert obs.valueQuantity.value == 145
        assert obs.valueQuantity.code == "/min"


class TestBuildObservations:
    def test_single_observation(self):
        payload = _sample_payload([_sample_obs()])
        results = build_observations(payload, "Patient/2", "Encounter/4")
        assert len(results) == 1

    def test_multiple_observations(self):
        payload = _sample_payload([
            _sample_obs(code="29463-7", display="Body weight"),
            _sample_obs(code="55283-6", display="Fetal heart rate"),
        ])
        results = build_observations(payload, "Patient/2", "Encounter/4")
        assert len(results) == 2
        assert results[0].code.coding[0].code == "29463-7"
        assert results[1].code.coding[0].code == "55283-6"

    def test_empty_observations(self):
        payload = _sample_payload([])
        results = build_observations(payload, "Patient/2", None)
        assert len(results) == 0

    def test_bp_codes_still_built_individually(self):
        """Phase 4: BP OBX segments are built as individual observations.
        Phase 5 will merge them into a panel."""
        payload = _sample_payload([
            _sample_obs(code="8480-6", display="Systolic BP"),
            _sample_obs(code="8462-4", display="Diastolic BP"),
        ])
        results = build_observations(payload, "Patient/2", None)
        assert len(results) == 2


class TestMapObservationStatus:
    def test_final(self):
        assert map_observation_status("F") == "final"

    def test_preliminary(self):
        assert map_observation_status("P") == "preliminary"

    def test_corrected(self):
        assert map_observation_status("C") == "corrected"

    def test_unknown(self):
        assert map_observation_status("Z") == "unknown"


class TestMapAbnormalFlag:
    def test_normal(self):
        result = map_abnormal_flag("N")
        assert result["code"] == "N"

    def test_high(self):
        result = map_abnormal_flag("H")
        assert result["code"] == "H"

    def test_low(self):
        result = map_abnormal_flag("L")
        assert result["code"] == "L"

    def test_empty(self):
        result = map_abnormal_flag("")
        assert result is None

    def test_unknown_flag(self):
        result = map_abnormal_flag("Z")
        assert result is None
```

---

## Verification

```bash
# 1. Run all unit tests
venv/bin/python -m pytest tests/unit/ -v

# Expected: Phase 1 (19) + Phase 2 (15) + Phase 3 (24) + Phase 4 (~30) = ~88 tests

# 2. Rebuild FastAPI
docker compose up -d --build fastapi
sleep 10

# 3. Ensure Patient and Encounter exist
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/adt_a01_payload.json

curl -s -X POST http://localhost:8000/fhir/Encounter \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/orm_o01_payload.json

# 4. Send ORU payload
curl -s -X POST http://localhost:8000/fhir/Observation/bundle \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/oru_r01_payload.json

# Expected:
# {"observationIds": ["<id1>","<id2>","<id3>","<id4>"], "correlationId": "..."}
# (4 observations: systolic, diastolic, weight, fetal HR — all individual in Phase 4)

# 5. Verify Observations in HAPI
docker exec fastapi curl -s "http://hapi:8080/fhir/Observation?subject=Patient/2&category=vital-signs"

# Expected: Bundle with 4 Observation entries

# 6. Spot-check body weight observation
# Find the Observation with code 29463-7
docker exec fastapi curl -s "http://hapi:8080/fhir/Observation?subject=Patient/2&code=29463-7" | python3 -c "
import sys, json
b = json.load(sys.stdin)
if b.get('entry'):
    o = b['entry'][0]['resource']
    print('code:', o['code']['coding'][0]['code'], o['code']['coding'][0]['display'])
    print('value:', o['valueQuantity']['value'], o['valueQuantity']['code'])
    print('status:', o['status'])
    print('subject:', o['subject']['reference'])
    print('encounter:', o.get('encounter',{}).get('reference','none'))
    print('effectiveDateTime:', o.get('effectiveDateTime'))
"

# Expected:
# code: 29463-7 Body weight
# value: 68.5 kg
# status: final
# subject: Patient/2
# encounter: Encounter/4
# effectiveDateTime: 2026-04-20T10:30:00+10:00

# 7. Spot-check fetal heart rate observation
docker exec fastapi curl -s "http://hapi:8080/fhir/Observation?subject=Patient/2&code=55283-6" | python3 -c "
import sys, json
b = json.load(sys.stdin)
if b.get('entry'):
    o = b['entry'][0]['resource']
    print('code:', o['code']['coding'][0]['code'])
    print('value:', o['valueQuantity']['value'], o['valueQuantity']['code'])
"

# Expected: code: 55283-6, value: 145 /min

# 8. Test missing Patient
curl -s -X POST http://localhost:8000/fhir/Observation/bundle \
  -H "Content-Type: application/json" \
  -d '{"correlationId":"x","mrn":"9999999","observations":[]}'

# Expected: 422 "Patient not found"
```

## Definition of Done

- [ ] `POST /fhir/Observation/bundle` accepts OruPayload and returns `{observationIds[], correlationId}`
- [ ] Each Observation has LOINC code with correct system
- [ ] Each Observation has valueQuantity with UCUM units
- [ ] Observation.status maps correctly (F→final, P→preliminary)
- [ ] Observation.category = vital-signs
- [ ] Observation.subject references correct Patient
- [ ] Observation.encounter references correct Encounter (when visit number provided)
- [ ] Observation.encounter absent when no visit number
- [ ] Observation.effectiveDateTime is ISO 8601 with AEST +10:00
- [ ] Observation.interpretation maps abnormal flags (N, H, L)
- [ ] Observation.referenceRange.text populated when present
- [ ] Empty observations array → empty observationIds
- [ ] 422 returned when Patient MRN not found
- [ ] BP codes (8480-6, 8462-4) still work as individual observations (Phase 5 merges them)
- [ ] Unit tests pass for observation transformer + valueset mappings
- [ ] All Phase 1 + 2 + 3 tests still pass

## Notes for Next Phase

Phase 5 will modify `build_observations()` to detect consecutive OBX segments with codes `8480-6` (systolic) and `8462-4` (diastolic), and merge them into a single Observation with:
- Code: LOINC `85354-9` (Blood pressure panel)
- Two `component[]` entries (systolic + diastolic)
- No top-level `valueQuantity`

The existing `_build_single_observation()` will be reused for the components. Phase 5 modifies `build_observations()` only — no endpoint changes needed.
