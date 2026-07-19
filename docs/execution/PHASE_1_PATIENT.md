# Phase 1: Patient Happy-Path

## Objective

Implement the ADT^A01 → FHIR Patient transformation. A flat JSON payload (as Mirth would send) hits `POST /fhir/Patient`, gets transformed into a valid AU Base Patient resource, and is persisted to HAPI FHIR with MRN-based idempotency.

**Note**: This phase does NOT include Condition resources from DG1 segments — that's Phase 2. Diagnoses in the payload are accepted but ignored for now.

## Pre-conditions

- Phase 0 complete — Docker stack healthy, `/health` returns OK
- HAPI FHIR reachable from FastAPI container at `http://hapi:8080/fhir`

## Tasks

Execute in order.

---

### Task 1: Create `fastapi/app/models/adt_payload.py`

Pydantic model representing the flat JSON that Mirth sends for an ADT^A01 message. This is NOT a FHIR resource — it's the intermediate format between Mirth and FastAPI.

```python
from pydantic import BaseModel


class NamePayload(BaseModel):
    family: str
    given: str
    middle: str = ""
    prefix: str = ""


class AddressPayload(BaseModel):
    line: str
    city: str
    state: str
    postalCode: str
    country: str = "AU"


class DiagnosisPayload(BaseModel):
    code: str
    display: str
    codeSystem: str = ""
    recordedDate: str = ""


class AdtPayload(BaseModel):
    correlationId: str
    messageType: str = "ADT^A01"
    mrn: str
    ihi: str = ""
    name: NamePayload
    birthDate: str
    gender: str
    address: AddressPayload
    phone: str = ""
    diagnoses: list[DiagnosisPayload] = []
```

---

### Task 2: Create `fastapi/app/valuesets/hl7_to_fhir_gender.py`

```python
GENDER_MAP: dict[str, str] = {
    "F": "female",
    "M": "male",
    "O": "other",
    "U": "unknown",
    "A": "other",
    "N": "unknown",
}


def map_gender(hl7_gender: str) -> str:
    return GENDER_MAP.get(hl7_gender.upper(), "unknown")
```

---

### Task 3: Create `fastapi/app/transformers/patient.py`

Transforms `AdtPayload` into a FHIR R4 Patient resource using the `fhir.resources` library.

**Field mapping reference** (from `docs/02_TECHNICAL_PLAN.md` §3.1):

| Source | Target | Notes |
|---|---|---|
| `payload.mrn` | `Patient.identifier[0].value` | MRN with type code `MR` |
| `payload.ihi` (if present) | `Patient.identifier[1].value` | IHI system URI |
| `payload.name.family` | `Patient.name[0].family` | |
| `payload.name.given` | `Patient.name[0].given[0]` | |
| `payload.name.middle` (if present) | `Patient.name[0].given[1]` | |
| `payload.name.prefix` (if present) | `Patient.name[0].prefix[0]` | |
| `payload.birthDate` | `Patient.birthDate` | Convert `YYYYMMDD` → `YYYY-MM-DD` |
| `payload.gender` | `Patient.gender` | Via `map_gender()` |
| `payload.address.*` | `Patient.address[0].*` | Use `home`, country defaults `AU` |
| `payload.phone` | `Patient.telecom[0].value` | System `phone`, use `mobile` |

```python
import re

from fhir.resources.address import Address
from fhir.resources.contactpoint import ContactPoint
from fhir.resources.humanname import HumanName
from fhir.resources.identifier import Identifier
from fhir.resources.patient import Patient

from app.config import settings
from app.models.adt_payload import AdtPayload
from app.valuesets.hl7_to_fhir_gender import map_gender

AU_PATIENT_PROFILE = "http://hl7.org.au/fhir/StructureDefinition/au-patient"
MR_TYPE_CODING = {
    "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
    "code": "MR",
}


def _hl7_date_to_iso(hl7_date: str) -> str:
    """Convert HL7 date YYYYMMDD to ISO YYYY-MM-DD."""
    cleaned = re.sub(r"[^0-9]", "", hl7_date)[:8]
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
    return hl7_date


def build_patient(payload: AdtPayload) -> Patient:
    identifiers = [
        Identifier(
            system=settings.mrn_system,
            value=payload.mrn,
            type={"coding": [MR_TYPE_CODING]},
        )
    ]

    if payload.ihi:
        identifiers.append(
            Identifier(system=settings.ihi_system, value=payload.ihi)
        )

    given_names = [payload.name.given]
    if payload.name.middle:
        given_names.append(payload.name.middle)

    name = HumanName(
        use="official",
        family=payload.name.family,
        given=given_names,
        prefix=[payload.name.prefix] if payload.name.prefix else None,
    )

    address = Address(
        use="home",
        line=[payload.address.line],
        city=payload.address.city,
        state=payload.address.state,
        postalCode=payload.address.postalCode,
        country=payload.address.country or "AU",
    )

    telecom = None
    if payload.phone:
        telecom = [
            ContactPoint(system="phone", use="mobile", value=payload.phone)
        ]

    patient = Patient(
        meta={"profile": [AU_PATIENT_PROFILE]},
        identifier=identifiers,
        active=True,
        name=[name],
        gender=map_gender(payload.gender),
        birthDate=_hl7_date_to_iso(payload.birthDate),
        address=[address],
        telecom=telecom,
    )

    return patient
```

---

### Task 4: Create `fastapi/app/clients/hapi_client.py`

HTTP client for HAPI FHIR server. Uses conditional update (PUT with identifier query) for idempotency.

```python
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class HapiClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client
        self._base = settings.hapi_base_url

    async def upsert_resource(
        self,
        resource_type: str,
        resource_data: dict[str, Any],
        identifier_query: str,
    ) -> str:
        """Conditional update: creates if not found, updates if single match.

        Args:
            resource_type: FHIR resource type (e.g., "Patient")
            resource_data: Serialized FHIR resource dict
            identifier_query: Query string for conditional match
                              (e.g., "http://hospital.local/mrn|1234567")

        Returns:
            Server-assigned resource ID.
        """
        url = f"{self._base}/{resource_type}"
        headers = {
            "Content-Type": "application/fhir+json",
            "If-None-Exist": f"identifier={identifier_query}",
        }

        response = await self._client.put(
            url,
            params={"identifier": identifier_query},
            json=resource_data,
            headers=headers,
        )

        if response.status_code not in (200, 201):
            logger.error(
                "HAPI upsert failed: %s %s", response.status_code, response.text
            )
            response.raise_for_status()

        location = response.headers.get("Location", "")
        if "/" in location:
            return location.rsplit("/", 1)[-1]

        body = response.json()
        return body.get("id", "unknown")
```

---

### Task 5: Update `fastapi/app/main.py`

Add the `POST /fhir/Patient` endpoint. Keep the existing `/health` endpoint unchanged.

Add these imports at the top:

```python
import logging

from app.clients.hapi_client import HapiClient
from app.models.adt_payload import AdtPayload
from app.transformers.patient import build_patient
```

Add this route after the `/health` endpoint:

```python
@app.post("/fhir/Patient")
async def transform_patient(payload: AdtPayload) -> dict[str, Any]:
    logger = logging.getLogger("app.fhir.patient")
    logger.info("Processing ADT^A01 for MRN=%s correlationId=%s",
                payload.mrn, payload.correlationId)

    patient = build_patient(payload)

    patient_data = patient.model_dump(exclude_none=True)

    hapi = HapiClient(app.state.http_client)
    identifier_query = f"{settings.mrn_system}|{payload.mrn}"
    patient_id = await hapi.upsert_resource("Patient", patient_data, identifier_query)

    logger.info("Patient persisted id=%s correlationId=%s",
                patient_id, payload.correlationId)

    return {
        "patientId": patient_id,
        "correlationId": payload.correlationId,
    }
```

The full `main.py` should look like this after edits:

```python
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from app.clients.hapi_client import HapiClient
from app.config import settings
from app.models.adt_payload import AdtPayload
from app.transformers.patient import build_patient


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Maternity FHIR Converter",
    description="HL7 v2 to FHIR R4 transformation service for Australian maternity care",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict[str, Any]:
    hapi_status = "unknown"
    try:
        client: httpx.AsyncClient = app.state.http_client
        response = await client.get(f"{settings.hapi_base_url}/metadata")
        hapi_status = "up" if response.status_code == 200 else "down"
    except httpx.HTTPError:
        hapi_status = "down"

    overall = "ok" if hapi_status == "up" else "degraded"

    return {
        "status": overall,
        "hapi": hapi_status,
        "version": "0.1.0",
    }


@app.post("/fhir/Patient")
async def transform_patient(payload: AdtPayload) -> dict[str, Any]:
    logger = logging.getLogger("app.fhir.patient")
    logger.info(
        "Processing ADT^A01 for MRN=%s correlationId=%s",
        payload.mrn,
        payload.correlationId,
    )

    patient = build_patient(payload)

    patient_data = patient.model_dump(exclude_none=True)

    hapi = HapiClient(app.state.http_client)
    identifier_query = f"{settings.mrn_system}|{payload.mrn}"
    patient_id = await hapi.upsert_resource(
        "Patient", patient_data, identifier_query
    )

    logger.info(
        "Patient persisted id=%s correlationId=%s",
        patient_id,
        payload.correlationId,
    )

    return {
        "patientId": patient_id,
        "correlationId": payload.correlationId,
    }
```

---

### Task 6: Create `tests/unit/test_patient_transformer.py`

Unit tests for the patient transformer. These test the mapping logic WITHOUT calling HAPI.

```python
from app.models.adt_payload import AdtPayload, AddressPayload, NamePayload
from app.transformers.patient import build_patient, _hl7_date_to_iso


def _sample_payload(**overrides) -> AdtPayload:
    defaults = {
        "correlationId": "test-uuid-001",
        "messageType": "ADT^A01",
        "mrn": "1234567",
        "ihi": "8003608166690503",
        "name": NamePayload(
            family="TEST", given="PATIENT", middle="MARY", prefix="MS"
        ),
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
        patient = build_patient(_sample_payload())
        assert patient.resource_type == "Patient"

    def test_mrn_identifier(self):
        patient = build_patient(_sample_payload())
        mrn_id = patient.identifier[0]
        assert mrn_id.value == "1234567"
        assert mrn_id.system == "http://hospital.local/mrn"
        assert mrn_id.type.coding[0].code == "MR"

    def test_ihi_identifier(self):
        patient = build_patient(_sample_payload())
        assert len(patient.identifier) == 2
        ihi_id = patient.identifier[1]
        assert ihi_id.value == "8003608166690503"
        assert ihi_id.system == "http://ns.electronichealth.net.au/id/hi/ihi/1.0"

    def test_no_ihi_when_empty(self):
        patient = build_patient(_sample_payload(ihi=""))
        assert len(patient.identifier) == 1

    def test_name(self):
        patient = build_patient(_sample_payload())
        name = patient.name[0]
        assert name.family == "TEST"
        assert name.given == ["PATIENT", "MARY"]
        assert name.prefix == ["MS"]
        assert name.use == "official"

    def test_name_no_middle(self):
        payload = _sample_payload(
            name=NamePayload(family="DOE", given="JANE", middle="", prefix="")
        )
        patient = build_patient(payload)
        name = patient.name[0]
        assert name.given == ["JANE"]
        assert name.prefix is None

    def test_gender_female(self):
        patient = build_patient(_sample_payload(gender="F"))
        assert patient.gender == "female"

    def test_gender_male(self):
        patient = build_patient(_sample_payload(gender="M"))
        assert patient.gender == "male"

    def test_gender_unknown(self):
        patient = build_patient(_sample_payload(gender="X"))
        assert patient.gender == "unknown"

    def test_birth_date(self):
        patient = build_patient(_sample_payload(birthDate="19920315"))
        assert patient.birthDate.isoformat() == "1992-03-15"

    def test_address(self):
        patient = build_patient(_sample_payload())
        addr = patient.address[0]
        assert addr.line == ["14 SAMPLE ST"]
        assert addr.city == "SYDNEY"
        assert addr.state == "NSW"
        assert addr.postalCode == "2000"
        assert addr.country == "AU"
        assert addr.use == "home"

    def test_telecom(self):
        patient = build_patient(_sample_payload())
        phone = patient.telecom[0]
        assert phone.value == "0412345678"
        assert phone.system == "phone"
        assert phone.use == "mobile"

    def test_no_telecom_when_empty(self):
        patient = build_patient(_sample_payload(phone=""))
        assert patient.telecom is None

    def test_active(self):
        patient = build_patient(_sample_payload())
        assert patient.active is True

    def test_au_base_profile(self):
        patient = build_patient(_sample_payload())
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
```

---

### Task 7: Create test payload fixture

**File**: `tests/fixtures/adt_a01_payload.json`

Create `tests/fixtures/` directory first, then this file:

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

After all tasks complete, rebuild and test:

```bash
# 1. Rebuild FastAPI container
docker compose up -d --build fastapi

# 2. Wait for it to be healthy
sleep 10

# 3. Run unit tests locally (install deps first if needed)
cd fastapi && pip install ".[dev]" && cd ..
pytest tests/unit/test_patient_transformer.py -v

# 4. Test the endpoint with sample payload
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/adt_a01_payload.json | python3 -m json.tool

# Expected response:
# {
#     "patientId": "<some-uuid-or-id>",
#     "correlationId": "550e8400-e29b-41d4-a716-446655440000"
# }

# 5. Verify Patient exists in HAPI (from inside Docker network)
docker exec fastapi curl -s "http://hapi:8080/fhir/Patient?identifier=http://hospital.local/mrn|1234567" | python3 -m json.tool

# Expected: Bundle with 1 entry, Patient resource with MRN 1234567

# 6. Test idempotency — send same payload again
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/adt_a01_payload.json | python3 -m json.tool

# Should return same patientId — no duplicate created

# 7. Verify still only one Patient with that MRN
docker exec fastapi curl -s "http://hapi:8080/fhir/Patient?identifier=http://hospital.local/mrn|1234567" | python3 -m json.tool

# Expected: Bundle.total = 1
```

## Definition of Done

- [ ] `POST /fhir/Patient` accepts AdtPayload JSON and returns `{patientId, correlationId}`
- [ ] Patient resource in HAPI has correct MRN identifier with type code `MR`
- [ ] Patient resource has IHI identifier when provided
- [ ] Patient resource has AU Base profile in `meta.profile`
- [ ] Name mapping: family, given, middle (as second given), prefix
- [ ] Gender mapping: F→female, M→male, O→other, U→unknown
- [ ] Birth date: `YYYYMMDD` → `YYYY-MM-DD`
- [ ] Address: AU format (state code, 4-digit postcode, country AU)
- [ ] Telecom: phone/mobile when present
- [ ] `Patient.active = true`
- [ ] Idempotency: sending same MRN twice does NOT create duplicate Patient
- [ ] Unit tests pass: `pytest tests/unit/test_patient_transformer.py`
- [ ] FHIR validation: resource passes `fhir.resources` Pydantic validation (implicit in `build_patient`)

## Notes for Next Phase

Phase 2 will add Condition resources from the `diagnoses[]` array in AdtPayload. The payload model already accepts diagnoses — Phase 2 adds `fastapi/app/transformers/condition.py` and updates the `/fhir/Patient` endpoint to also create Conditions linked to the Patient.
