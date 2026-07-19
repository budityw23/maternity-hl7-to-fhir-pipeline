# Technical Planning Document
## Maternity HL7 v2 → FHIR R4 Integration Pipeline

| Field | Value |
|---|---|
| **Document Version** | 1.0 |
| **Companion to** | `01_PRD.md` |
| **Target Standards** | HL7 v2.5, FHIR R4 (4.0.1), AU Base 4.x |

---

## 1. System Architecture

### 1.1 High-Level Architecture (Text Diagram)

```
                  ┌──────────────────────────────────────────────────────────────────────────┐
                  │                         DOCKER COMPOSE NETWORK                           │
                  │                            (maternity-net)                               │
                  │                                                                          │
  ┌─────────────┐ │  ┌──────────────────┐    ┌───────────────────┐    ┌─────────────────┐   │
  │  Simulated  │ │  │                  │    │                   │    │                 │   │
  │  Maternity  │ │  │  Mirth Connect   │    │   FastAPI         │    │   HAPI FHIR     │   │
  │  Hospital   │ │  │  4.5             │    │   Converter       │    │   Server        │   │
  │  System     │ │  │                  │    │                   │    │                 │   │
  │             │ │  │  ┌────────────┐  │    │  ┌─────────────┐  │    │                 │   │
  │ mllp_send   │ │  │  │ MLLP       │  │    │  │ /fhir/      │  │    │  REST API       │   │
  │ test.sh     │─┼─►│  │ Listener   │  │    │  │  Patient    │  │    │  /Patient       │   │
  │             │ │  │  │ :6661      │  │    │  │  Encounter  │  │    │  /Encounter     │   │
  │  ADT^A01    │ │  │  └─────┬──────┘  │    │  │  Observation│  │    │  /Observation   │   │
  │  ORM^O01    │ │  │        │         │    │  │  Condition  │  │    │  /Condition     │   │
  │  ORU^R01    │ │  │        ▼         │    │  │  /bundle    │  │    │                 │   │
  └─────────────┘ │  │  ┌────────────┐  │    │  └──────┬──────┘  │    │  H2 DB (demo)   │   │
                  │  │  │ Channel    │  │    │         │         │    │  Postgres (prod)│   │
                  │  │  │ Routers    │  │    │         ▼         │    │                 │   │
                  │  │  │ (3 chans)  │  │    │  ┌─────────────┐  │    │  $validate Op   │   │
                  │  │  └─────┬──────┘  │    │  │ Transformer │  │    │                 │   │
                  │  │        │         │    │  │ (Pydantic   │  │    │  :8080          │   │
                  │  │        ▼         │    │  │  fhir.      │  │    │                 │   │
                  │  │  ┌────────────┐  │    │  │  resources) │  │    │                 │   │
                  │  │  │ JS         │  │    │  └──────┬──────┘  │    │                 │   │
                  │  │  │ Transformer│  │    │         │         │    │                 │   │
                  │  │  │ (HL7 → JSON│  │    │         ▼         │    │                 │   │
                  │  │  └─────┬──────┘  │    │  ┌─────────────┐  │    │                 │   │
                  │  │        │         │    │  │ HAPI Client │  │    │                 │   │
                  │  │        ▼         │ POST │  │ (httpx)    │──┼──► │                 │   │
                  │  │  ┌────────────┐  │ JSON │  └─────────────┘  │    │                 │   │
                  │  │  │ HTTP       │──┼──────┼─►                 │    │                 │   │
                  │  │  │ Sender     │  │      │  :8000            │    │                 │   │
                  │  │  └─────┬──────┘  │      │                   │    │                 │   │
                  │  │        │         │      └───────────────────┘    └─────────────────┘   │
                  │  │        ▼         │                                                     │
                  │  │  ┌────────────┐  │                                                     │
                  │  │  │ ACK        │  │                                                     │
                  │  │  │ Generator  │  │                                                     │
                  │  │  └─────┬──────┘  │                                                     │
                  │  │        │         │                                                     │
                  │  │  :6661 ▼ (ACK)   │                                                     │
                  │  └──────────────────┘                                                     │
                  │         ▲                                                                 │
                  └─────────┼─────────────────────────────────────────────────────────────────┘
                            │
                            └─── back to sender (MLLP ACK)


  Cross-cutting:
  ──────────────
  • Correlation ID:      X-Correlation-ID generated in Mirth, passed in HTTP header to FastAPI,
                         logged everywhere
  • Dead-letter:         ./deadletter/ shared volume between Mirth and FastAPI
  • Logs:                ./logs/ shared volume (JSON lines)
  • Health checks:       Mirth /api/server/status, FastAPI /health, HAPI /fhir/metadata
```

### 1.2 Data Flow (Sequence)

```
Sender                Mirth                 FastAPI               HAPI
  │                     │                      │                    │
  │  HL7 ADT^A01 (MLLP) │                      │                    │
  ├────────────────────►│                      │                    │
  │                     │ parse + transform    │                    │
  │                     │ to flat JSON         │                    │
  │                     │                      │                    │
  │                     │  POST /fhir/Patient  │                    │
  │                     │  X-Correlation-ID    │                    │
  │                     ├─────────────────────►│                    │
  │                     │                      │ validate (Pydantic)│
  │                     │                      │ build FHIR resource│
  │                     │                      │                    │
  │                     │                      │ PUT /Patient?id=MRN│
  │                     │                      ├───────────────────►│
  │                     │                      │                    │ store
  │                     │                      │   201/200 + id     │
  │                     │                      │◄───────────────────┤
  │                     │   200 {fhirId}       │                    │
  │                     │◄─────────────────────┤                    │
  │  MLLP ACK (AA)      │                      │                    │
  │◄────────────────────┤                      │                    │
```

---

## 2. HL7 v2 Message Examples

> **Encoding characters** for all messages: `|^~\&`  
> **Field separator**: `|`  Component: `^`  Repetition: `~`  Escape: `\`  Subcomponent: `&`

### 2.1 ADT^A01 — Admission (Mother arrives for delivery, with pregnancy diagnosis)

```hl7
MSH|^~\&|MAT_PAS|RPA_MATERNITY|MIRTH|INTEGRATION|20260527093000||ADT^A01^ADT_A01|MSG00001|P|2.5|||AL|NE|AUS
EVN|A01|20260527093000|||DR_JONES
PID|1||1234567^^^RPA^MR~8003608166690503^^^AUSHIC^NI||TEST^PATIENT^MARY^^MS||19920315|F|||14 SAMPLE ST^^SYDNEY^NSW^2000^AUS||0412345678^PRN^CP~0298765432^PRN^PH|||M||||||||||||||
NK1|1|TEST^JOHN|SPO||0411111111
PV1|1|I|MAT_WARD^301^A^RPA||||DR_SMITH^SARAH^A^^^DR|||OBS||||1|||DR_JONES^JAMES^B^^^DR|INP|VN00001|||||||||||||||||||||||||20260527093000
DG1|1|I10|O80^Encounter for full-term uncomplicated delivery^I10|Encounter for full-term uncomplicated delivery|20260527093000|A|
GT1|1||TEST^PATIENT^MARY||14 SAMPLE ST^^SYDNEY^NSW^2000^AUS|0412345678|||||SELF
IN1|1|MEDICARE|MEDICARE|MEDICARE AUSTRALIA|||||||||||TEST^PATIENT^MARY|SELF|19920315|14 SAMPLE ST^^SYDNEY^NSW^2000^AUS
```

**Field highlights:**
- `PID-3`: dual identifiers — local MRN (`1234567`) and an example IHI (`8003608166690503` — note: real IHI checksum format, value is synthetic)
- `PID-11`: AU-formatted address with state code `NSW`
- `DG1-3`: ICD-10-AM code `O80` for normal delivery
- `PV1-2 = I`: Inpatient (will map to `Encounter.class = IMP` for the delivery; antenatal visits use `ORM^O01` with `PV1-2 = O`)

### 2.2 ORM^O01 — Antenatal Visit Order (28-week checkup)

```hl7
MSH|^~\&|MAT_BOOKING|RPA_MATERNITY|MIRTH|INTEGRATION|20260420100000||ORM^O01^ORM_O01|MSG00002|P|2.5|||AL|NE|AUS
PID|1||1234567^^^RPA^MR||TEST^PATIENT^MARY^^MS||19920315|F|||14 SAMPLE ST^^SYDNEY^NSW^2000^AUS||0412345678^PRN^CP
PV1|1|O|MAT_CLINIC^OPD^^RPA||||DR_SMITH^SARAH^A^^^DR|||OBS|||||||OUT|VN00012|||||||||||||||||||||||||20260420100000|20260420110000
ORC|NW|ORD0001^MAT_BOOKING|||SC||^^^20260420100000^^R||20260420100000|DR_SMITH^SARAH^A^^^DR|||||||||||||
OBR|1|ORD0001^MAT_BOOKING||ANC^Antenatal Checkup^L|||20260420100000|||||||||DR_SMITH^SARAH^A^^^DR
```

**Field highlights:**
- `PV1-2 = O`: Outpatient → maps to `Encounter.class = AMB` (ambulatory)
- `PV1-19`: Visit number `VN00012`
- `PV1-44 / PV1-45`: Admit/discharge timestamps for the antenatal visit
- `ORC-1 = NW`: New order

### 2.3 ORU^R01 — Antenatal Vitals Result

```hl7
MSH|^~\&|MAT_EMR|RPA_MATERNITY|MIRTH|INTEGRATION|20260420103000||ORU^R01^ORU_R01|MSG00003|P|2.5|||AL|NE|AUS
PID|1||1234567^^^RPA^MR||TEST^PATIENT^MARY^^MS||19920315|F
PV1|1|O|MAT_CLINIC^OPD^^RPA||||DR_SMITH^SARAH^A^^^DR|||OBS|||||||OUT|VN00012
OBR|1|ORD0001^MAT_BOOKING||ANC^Antenatal Checkup^L|||20260420103000|||||||||DR_SMITH^SARAH^A^^^DR|||||||F
OBX|1|NM|8480-6^Systolic blood pressure^LN||118|mm[Hg]^millimeters of mercury^UCUM|90-140|N|||F|||20260420103000
OBX|2|NM|8462-4^Diastolic blood pressure^LN||76|mm[Hg]^millimeters of mercury^UCUM|60-90|N|||F|||20260420103000
OBX|3|NM|29463-7^Body weight^LN||68.5|kg^kilogram^UCUM|||N|||F|||20260420103000
OBX|4|NM|55283-6^Fetal heart rate^LN||145|/min^per minute^UCUM|110-160|N|||F|||20260420103000
```

**Field highlights:**
- `OBX-3`: LOINC code (preferred over local codes for AU Core conformance)
- `OBX-5`: numeric value
- `OBX-6`: UCUM units (`mm[Hg]`, `kg`, `/min`)
- `OBX-7`: reference range
- `OBX-11 = F`: Final → maps to `Observation.status = final`
- `OBX-14`: observation date/time

---

## 3. Field Mapping Tables

> **Notation:** HL7 references use `SEGMENT-FIELD.COMPONENT` (1-indexed per HL7 convention). FHIR paths use FHIRPath. `→` means "maps to". `⊕` means "constructed/derived".

### 3.1 Patient (from ADT^A01)

| HL7 Source | FHIR Target | Notes |
|---|---|---|
| `PID-3.1` (where `PID-3.5 = MR`) | `Patient.identifier[0].value` | Local MRN |
| `PID-3.4` | `Patient.identifier[0].assigner.display` | Assigning facility |
| ⊕ Constant | `Patient.identifier[0].system` | `http://hospital.local/mrn` (or facility OID) |
| ⊕ Constant | `Patient.identifier[0].type.coding` | `MR` from `http://terminology.hl7.org/CodeSystem/v2-0203` |
| `PID-3.1` (where `PID-3.5 = NI`) | `Patient.identifier[1].value` | IHI |
| ⊕ Constant | `Patient.identifier[1].system` | `http://ns.electronichealth.net.au/id/hi/ihi/1.0` |
| `PID-5.1` | `Patient.name[0].family` | Family name |
| `PID-5.2` | `Patient.name[0].given[0]` | First given name |
| `PID-5.3` | `Patient.name[0].given[1]` | Middle name |
| `PID-5.5` | `Patient.name[0].prefix[0]` | Title (MS, MR, DR) |
| ⊕ Constant | `Patient.name[0].use` | `official` |
| `PID-7` | `Patient.birthDate` | Format `YYYY-MM-DD` (truncate HL7 `YYYYMMDD`) |
| `PID-8` | `Patient.gender` | `F`→`female`, `M`→`male`, `O`→`other`, `U`→`unknown` |
| `PID-11.1` | `Patient.address[0].line[0]` | Street |
| `PID-11.3` | `Patient.address[0].city` | Suburb/city |
| `PID-11.4` | `Patient.address[0].state` | AU state code (NSW, VIC, QLD, etc.) |
| `PID-11.5` | `Patient.address[0].postalCode` | 4-digit AU postcode |
| `PID-11.6` | `Patient.address[0].country` | `AU` |
| ⊕ Constant | `Patient.address[0].use` | `home` |
| `PID-13.1` (`PID-13.3 = CP`) | `Patient.telecom[0].value` | Mobile |
| ⊕ Constant | `Patient.telecom[0].system` | `phone` |
| ⊕ Constant | `Patient.telecom[0].use` | `mobile` |
| `PID-13.1` (`PID-13.3 = PH`) | `Patient.telecom[1].value` | Landline |
| ⊕ Constant | `Patient.active` | `true` (on A01) |
| ⊕ Constant | `Patient.meta.profile[0]` | `http://hl7.org.au/fhir/StructureDefinition/au-patient` |

### 3.2 Condition (from ADT^A01 DG1)

| HL7 Source | FHIR Target | Notes |
|---|---|---|
| `PID-3.1` (MR) | `Condition.subject.reference` | `Patient/{id}` resolved by MRN |
| `DG1-3.1` | `Condition.code.coding[0].code` | ICD-10-AM code (e.g., `O80`) |
| `DG1-3.2` | `Condition.code.coding[0].display` | Diagnosis text |
| ⊕ Constant | `Condition.code.coding[0].system` | `http://hl7.org.au/fhir/CodeSystem/icd-10-am` |
| `DG1-5` | `Condition.recordedDate` | ISO 8601 |
| ⊕ Constant | `Condition.clinicalStatus.coding[0]` | `active` from `http://terminology.hl7.org/CodeSystem/condition-clinical` |
| ⊕ Constant | `Condition.verificationStatus.coding[0]` | `confirmed` from `http://terminology.hl7.org/CodeSystem/condition-ver-status` |
| ⊕ Constant | `Condition.category[0].coding[0]` | `encounter-diagnosis` |
| `PV1-19` | `Condition.encounter.reference` | `Encounter/{id}` if present |

### 3.3 Observation (from ORU^R01 OBX)

| HL7 Source | FHIR Target | Notes |
|---|---|---|
| `OBX-3.1` | `Observation.code.coding[0].code` | LOINC code |
| `OBX-3.2` | `Observation.code.coding[0].display` | Display |
| ⊕ Constant | `Observation.code.coding[0].system` | `http://loinc.org` |
| `OBX-5` | `Observation.valueQuantity.value` | Numeric value (`OBX-2 = NM`) |
| `OBX-6.1` | `Observation.valueQuantity.code` | UCUM code |
| `OBX-6.2` | `Observation.valueQuantity.unit` | Display unit |
| ⊕ Constant | `Observation.valueQuantity.system` | `http://unitsofmeasure.org` |
| `OBX-7` | `Observation.referenceRange[0].text` | Low-high text |
| `OBX-8` | `Observation.interpretation[0].coding[0].code` | `N`/`H`/`L` from v3-ObservationInterpretation |
| `OBX-11` | `Observation.status` | `F`→`final`, `P`→`preliminary`, `C`→`corrected` |
| `OBX-14` | `Observation.effectiveDateTime` | Fallback to `OBR-7` |
| `PID-3.1` (MR) | `Observation.subject.reference` | `Patient/{id}` |
| `PV1-19` | `Observation.encounter.reference` | `Encounter/{id}` |
| ⊕ Constant | `Observation.category[0].coding[0]` | `vital-signs` from `http://terminology.hl7.org/CodeSystem/observation-category` |

**Special case — Blood Pressure panel:** When two consecutive `OBX` segments carry `8480-6` (systolic) and `8462-4` (diastolic), the FastAPI transformer merges them into a single `Observation` with code `85354-9` (Blood pressure panel) and two `component[]` entries.

### 3.4 Encounter (from ORM^O01 PV1)

| HL7 Source | FHIR Target | Notes |
|---|---|---|
| `PV1-19` | `Encounter.identifier[0].value` | Visit number |
| ⊕ Constant | `Encounter.identifier[0].system` | `http://hospital.local/visit-number` |
| `PV1-2` | `Encounter.class.code` | `I`→`IMP`, `O`→`AMB`, `E`→`EMER` |
| ⊕ Constant | `Encounter.class.system` | `http://terminology.hl7.org/CodeSystem/v3-ActCode` |
| `ORC-1` | `Encounter.status` | `NW`→`planned`, `IP`→`in-progress`, `CM`→`finished` |
| `PV1-44` | `Encounter.period.start` | ISO 8601 |
| `PV1-45` | `Encounter.period.end` | ISO 8601 |
| `PV1-3.1` | `Encounter.location[0].location.display` | Ward |
| `PV1-3.2` | `Encounter.location[0].location.identifier.value` | Room |
| `PV1-7.1` | `Encounter.participant[0].individual.identifier.value` | Attending clinician ID |
| `PV1-7.2 + PV1-7.3` | `Encounter.participant[0].individual.display` | "Family, Given" |
| ⊕ Constant | `Encounter.participant[0].type[0].coding[0]` | `ATND` from `v3-ParticipationType` |
| `OBR-4.1` (from ORM) | `Encounter.serviceType.coding[0].code` | e.g., `ANC` → mapped to SNOMED `424525001` (Antenatal care) |
| `PID-3.1` (MR) | `Encounter.subject.reference` | `Patient/{id}` |

---

## 4. Mirth Connect Channel Design

Three channels — one per message type — sharing a common `Mother MRN Resolver` code template.

### 4.1 Channel: `Maternity_ADT_Inbound`

| Property | Value |
|---|---|
| **Source connector** | MLLP Listener |
| **Port** | 6661 |
| **Response from** | Destination 1 (or "Auto-generate ACK" with override on error) |
| **Inbound data type** | HL7 v2.x |
| **Inbound version** | 2.5 |
| **Strip BOM** | True |
| **Convert LF to CR** | True |

**Source Transformer (JavaScript):**
```javascript
// Validate trigger event is A01 (ADT^A01 is the only one we support in this channel)
var trigger = msg['MSH']['MSH.9']['MSH.9.2'].toString();
if (trigger !== 'A01') {
    responseStatus = ERROR;
    responseStatusMessage = 'Unsupported ADT trigger: ' + trigger;
    return;
}

// Generate correlation ID and stash for downstream
var correlationId = UUIDGenerator.getUUID();
channelMap.put('correlationId', correlationId);
logger.info('[' + correlationId + '] ADT^A01 received from ' +
            msg['MSH']['MSH.3']['MSH.3.1'].toString());

// Build minimal flat JSON for FastAPI
var payload = {
    correlationId: correlationId,
    messageType: 'ADT^A01',
    mrn: msg['PID']['PID.3'][0]['PID.3.1'].toString(),
    ihi: '', // populated below if present
    name: {
        family: msg['PID']['PID.5']['PID.5.1'].toString(),
        given: msg['PID']['PID.5']['PID.5.2'].toString(),
        middle: msg['PID']['PID.5']['PID.5.3'].toString(),
        prefix: msg['PID']['PID.5']['PID.5.5'].toString()
    },
    birthDate: msg['PID']['PID.7']['PID.7.1'].toString(),
    gender: msg['PID']['PID.8']['PID.8.1'].toString(),
    address: {
        line: msg['PID']['PID.11']['PID.11.1'].toString(),
        city: msg['PID']['PID.11']['PID.11.3'].toString(),
        state: msg['PID']['PID.11']['PID.11.4'].toString(),
        postalCode: msg['PID']['PID.11']['PID.11.5'].toString(),
        country: msg['PID']['PID.11']['PID.11.6'].toString() || 'AU'
    },
    phone: msg['PID']['PID.13'][0]['PID.13.1'].toString(),
    diagnoses: []
};

// Iterate PID-3 repetitions to find IHI (type code 'NI')
var pid3 = msg['PID']['PID.3'];
for (var i = 0; i < pid3.length(); i++) {
    if (pid3[i]['PID.3.5'].toString() === 'NI') {
        payload.ihi = pid3[i]['PID.3.1'].toString();
    }
}

// Iterate DG1 segments
var dg1Segs = msg['DG1'];
for (var j = 0; j < dg1Segs.length(); j++) {
    payload.diagnoses.push({
        code: dg1Segs[j]['DG1.3']['DG1.3.1'].toString(),
        display: dg1Segs[j]['DG1.3']['DG1.3.2'].toString(),
        codeSystem: dg1Segs[j]['DG1.3']['DG1.3.3'].toString(),
        recordedDate: dg1Segs[j]['DG1.5']['DG1.5.1'].toString()
    });
}

channelMap.put('payload', JSON.stringify(payload));
```

**Destination 1: HTTP Sender**
| Property | Value |
|---|---|
| URL | `http://fastapi:8000/fhir/Patient` |
| Method | POST |
| Content type | `application/json` |
| Headers | `X-Correlation-ID: ${correlationId}` |
| Body | `${payload}` |
| Response | parsed into `responseMap` |
| On error | retry 3× with 2s/4s/8s backoff, then write `${originalMessage}` to `/deadletter/adt/` |

### 4.2 Channel: `Maternity_ORM_Inbound`

| Property | Value |
|---|---|
| **Source** | MLLP Listener (same port 6661, channel routing by trigger event) |
| **Filter** | Message must have `MSH-9.1 = ORM` AND `MSH-9.2 = O01` |

**Source Transformer (JS):** extracts `PID-3.1`, all `PV1` fields listed in §3.4, and the order details from `OBR-4`. Posts to `http://fastapi:8000/fhir/Encounter`.

### 4.3 Channel: `Maternity_ORU_Inbound`

| Property | Value |
|---|---|
| **Source** | MLLP Listener |
| **Filter** | `MSH-9.1 = ORU` AND `MSH-9.2 = R01` |

**Source Transformer (JS):** extracts `PID-3.1`, `PV1-19`, and iterates all `OBX` segments into an `observations[]` array. Posts the entire array as a bundle to `http://fastapi:8000/fhir/Observation/bundle` (so blood pressure pairing can happen server-side).

> **Note on single-port multiplexing:** A single MLLP listener can dispatch to multiple channels using Mirth's channel router or by deploying three listeners on different ports (6661/6662/6663). The first approach matches a real hospital setup; the second is simpler for the demo. The repo uses one listener on 6661 with channel routing.

---

## 5. FastAPI Service Design

### 5.1 Endpoint Surface

| Method | Path | Purpose | Body | Response |
|---|---|---|---|---|
| `GET` | `/health` | Health probe (Mirth + HAPI status) | — | `{ "status": "ok", "mirth": "up", "hapi": "up" }` |
| `POST` | `/fhir/Patient` | Receive ADT-derived flat JSON, build Patient + Conditions | `AdtPayload` | `{ patientId, conditionIds[], correlationId }` |
| `POST` | `/fhir/Encounter` | Receive ORM-derived flat JSON, build Encounter | `OrmPayload` | `{ encounterId, correlationId }` |
| `POST` | `/fhir/Observation/bundle` | Receive ORU-derived observations array, build Observations (with BP pairing) | `OruPayload` | `{ observationIds[], correlationId }` |
| `GET` | `/fhir/Patient/{mrn}` | Convenience lookup by MRN → returns FHIR Patient | — | FHIR `Patient` JSON |

### 5.2 Module Layout

```
app/
├── main.py                    # FastAPI app, routes, dependency wiring
├── config.py                  # Settings via pydantic-settings (env vars)
├── models/
│   ├── adt_payload.py         # Pydantic models matching Mirth output
│   ├── orm_payload.py
│   └── oru_payload.py
├── transformers/
│   ├── patient.py             # build_patient(payload) -> Patient
│   ├── condition.py           # build_conditions(payload, patient_ref) -> list[Condition]
│   ├── encounter.py           # build_encounter(payload, patient_ref) -> Encounter
│   └── observation.py         # build_observations(payload, ...) -> list[Observation]
├── clients/
│   └── hapi_client.py         # httpx client, conditional create by identifier
├── valuesets/
│   ├── icd10am_to_snomed.py   # static dict (subset)
│   └── hl7_to_fhir_gender.py
├── logging_setup.py           # JSON logging with correlation ID context var
└── errors.py                  # ProblemDetail (RFC 7807) responses
```

### 5.3 Transformer Pattern (illustrative)

```python
# transformers/patient.py
from fhir.resources.patient import Patient
from fhir.resources.humanname import HumanName
from fhir.resources.identifier import Identifier
from fhir.resources.address import Address
from fhir.resources.contactpoint import ContactPoint
from app.models.adt_payload import AdtPayload

AU_PATIENT_PROFILE = "http://hl7.org.au/fhir/StructureDefinition/au-patient"
IHI_SYSTEM = "http://ns.electronichealth.net.au/id/hi/ihi/1.0"
MRN_SYSTEM = "http://hospital.local/mrn"
GENDER_MAP = {"F": "female", "M": "male", "O": "other", "U": "unknown"}

def build_patient(payload: AdtPayload) -> Patient:
    identifiers = [
        Identifier(
            system=MRN_SYSTEM,
            value=payload.mrn,
            type={"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                "code": "MR"
            }]}
        )
    ]
    if payload.ihi:
        identifiers.append(Identifier(system=IHI_SYSTEM, value=payload.ihi))

    patient = Patient(
        meta={"profile": [AU_PATIENT_PROFILE]},
        identifier=identifiers,
        active=True,
        name=[HumanName(
            use="official",
            family=payload.name.family,
            given=[g for g in [payload.name.given, payload.name.middle] if g],
            prefix=[payload.name.prefix] if payload.name.prefix else None,
        )],
        gender=GENDER_MAP.get(payload.gender, "unknown"),
        birthDate=_hl7_date_to_iso(payload.birthDate),
        address=[Address(
            use="home",
            line=[payload.address.line],
            city=payload.address.city,
            state=payload.address.state,
            postalCode=payload.address.postalCode,
            country=payload.address.country or "AU",
        )],
        telecom=[ContactPoint(system="phone", use="mobile", value=payload.phone)]
            if payload.phone else None,
    )
    return patient
```

Validation is automatic via `fhir.resources` Pydantic models — invalid input raises `ValidationError`, which is caught by a FastAPI exception handler that returns RFC 7807 problem+json.

### 5.4 Conditional Create (Idempotency)

```python
# clients/hapi_client.py
async def upsert_patient_by_mrn(patient: Patient, mrn: str) -> str:
    response = await client.put(
        f"{HAPI_BASE}/Patient",
        params={"identifier": f"{MRN_SYSTEM}|{mrn}"},
        json=patient.dict(exclude_none=True),
        headers={"Content-Type": "application/fhir+json"},
    )
    response.raise_for_status()
    return response.json()["id"]
```

`PUT /Patient?identifier=...` instructs HAPI to perform a conditional update — replacing if a single match exists, creating otherwise. Re-running the same ADT message produces no duplicates.

---

## 6. FHIR R4 Resource Structures

### 6.1 Patient (Example Output)

```json
{
  "resourceType": "Patient",
  "meta": {
    "profile": ["http://hl7.org.au/fhir/StructureDefinition/au-patient"]
  },
  "identifier": [
    {
      "system": "http://hospital.local/mrn",
      "value": "1234567",
      "type": {
        "coding": [{
          "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
          "code": "MR"
        }]
      }
    },
    {
      "system": "http://ns.electronichealth.net.au/id/hi/ihi/1.0",
      "value": "8003608166690503"
    }
  ],
  "active": true,
  "name": [{
    "use": "official",
    "family": "TEST",
    "given": ["PATIENT", "MARY"],
    "prefix": ["MS"]
  }],
  "gender": "female",
  "birthDate": "1992-03-15",
  "address": [{
    "use": "home",
    "line": ["14 SAMPLE ST"],
    "city": "SYDNEY",
    "state": "NSW",
    "postalCode": "2000",
    "country": "AU"
  }],
  "telecom": [{
    "system": "phone",
    "use": "mobile",
    "value": "0412345678"
  }]
}
```

### 6.2 Condition (Example Output)

```json
{
  "resourceType": "Condition",
  "subject": { "reference": "Patient/1234567" },
  "encounter": { "reference": "Encounter/VN00001" },
  "clinicalStatus": {
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
      "code": "active"
    }]
  },
  "verificationStatus": {
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
      "code": "confirmed"
    }]
  },
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/condition-category",
      "code": "encounter-diagnosis"
    }]
  }],
  "code": {
    "coding": [{
      "system": "http://hl7.org.au/fhir/CodeSystem/icd-10-am",
      "code": "O80",
      "display": "Encounter for full-term uncomplicated delivery"
    }]
  },
  "recordedDate": "2026-05-27T09:30:00+10:00"
}
```

### 6.3 Observation (Blood Pressure panel — Example Output)

```json
{
  "resourceType": "Observation",
  "status": "final",
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/observation-category",
      "code": "vital-signs"
    }]
  }],
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "85354-9",
      "display": "Blood pressure panel"
    }]
  },
  "subject": { "reference": "Patient/1234567" },
  "encounter": { "reference": "Encounter/VN00012" },
  "effectiveDateTime": "2026-04-20T10:30:00+10:00",
  "component": [
    {
      "code": {
        "coding": [{
          "system": "http://loinc.org",
          "code": "8480-6",
          "display": "Systolic blood pressure"
        }]
      },
      "valueQuantity": {
        "value": 118,
        "unit": "mmHg",
        "system": "http://unitsofmeasure.org",
        "code": "mm[Hg]"
      }
    },
    {
      "code": {
        "coding": [{
          "system": "http://loinc.org",
          "code": "8462-4",
          "display": "Diastolic blood pressure"
        }]
      },
      "valueQuantity": {
        "value": 76,
        "unit": "mmHg",
        "system": "http://unitsofmeasure.org",
        "code": "mm[Hg]"
      }
    }
  ]
}
```

### 6.4 Encounter (Example Output)

```json
{
  "resourceType": "Encounter",
  "status": "finished",
  "identifier": [{
    "system": "http://hospital.local/visit-number",
    "value": "VN00012"
  }],
  "class": {
    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
    "code": "AMB",
    "display": "ambulatory"
  },
  "serviceType": {
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "424525001",
      "display": "Antenatal care"
    }]
  },
  "subject": { "reference": "Patient/1234567" },
  "participant": [{
    "type": [{
      "coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
        "code": "ATND",
        "display": "attender"
      }]
    }],
    "individual": {
      "identifier": { "value": "DR_SMITH" },
      "display": "SMITH, SARAH"
    }
  }],
  "period": {
    "start": "2026-04-20T10:00:00+10:00",
    "end":   "2026-04-20T11:00:00+10:00"
  },
  "location": [{
    "location": {
      "display": "MAT_CLINIC",
      "identifier": { "value": "OPD" }
    }
  }]
}
```

---

## 7. Docker Compose Service Definitions

`docker-compose.yml`:

```yaml
version: "3.9"

networks:
  maternity-net:
    driver: bridge

volumes:
  hapi-data:
  mirth-data:

services:
  mirth:
    image: nextgenhealthcare/connect:4.5
    container_name: mirth
    ports:
      - "6661:6661"        # MLLP listener
      - "8443:8443"        # Mirth Administrator (HTTPS)
    environment:
      DATABASE: derby
      DATABASE_URL: jdbc:derby:/opt/connect/appdata/mirthdb;create=true
    volumes:
      - mirth-data:/opt/connect/appdata
      - ./mirth/channels:/opt/connect/channels:ro
      - ./deadletter:/opt/connect/deadletter
      - ./logs/mirth:/opt/connect/logs
    networks: [maternity-net]
    depends_on:
      fastapi:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-fk", "https://localhost:8443/api/server/status"]
      interval: 30s
      retries: 5

  fastapi:
    build:
      context: ./fastapi
      dockerfile: Dockerfile
    container_name: fastapi
    ports:
      - "8000:8000"
    environment:
      HAPI_BASE_URL: http://hapi:8080/fhir
      LOG_LEVEL: INFO
      MRN_SYSTEM: http://hospital.local/mrn
      IHI_SYSTEM: http://ns.electronichealth.net.au/id/hi/ihi/1.0
    volumes:
      - ./logs/fastapi:/app/logs
      - ./deadletter:/app/deadletter
    networks: [maternity-net]
    depends_on:
      hapi:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s
      retries: 5

  hapi:
    image: hapiproject/hapi:v7.0.3
    container_name: hapi
    ports:
      - "8080:8080"
    environment:
      hapi.fhir.fhir_version: R4
      hapi.fhir.validation.requests_enabled: "true"
      hapi.fhir.validation.responses_enabled: "true"
      hapi.fhir.cors.allow_credentials: "true"
      hapi.fhir.cors.allowed_origin: "*"
    volumes:
      - hapi-data:/data/hapi
    networks: [maternity-net]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/fhir/metadata"]
      interval: 30s
      retries: 10
      start_period: 60s
```

---

## 8. GitHub Repository Structure

```
maternity-hl7-to-fhir/
├── README.md                          # Project overview, quickstart, screenshots
├── LICENSE                            # MIT
├── docker-compose.yml
├── .github/
│   └── workflows/
│       ├── ci.yml                     # ruff, mypy, pytest on PR
│       └── docker-build.yml           # build & push fastapi image
├── docs/
│   ├── 01_PRD.md                      # this PRD
│   ├── 02_TECHNICAL_PLAN.md           # this doc
│   ├── 03_AUSTRALIAN_CONTEXT.md       # ADHA / AU Base / MHR notes
│   ├── MAPPING.md                     # field-by-field mapping cheat-sheet
│   ├── ARCHITECTURE.md                # diagrams (this content)
│   └── images/
│       ├── architecture.png
│       └── mirth-channel.png
├── mirth/
│   ├── README.md                      # how to import channels
│   ├── channels/
│   │   ├── Maternity_ADT_Inbound.xml
│   │   ├── Maternity_ORM_Inbound.xml
│   │   └── Maternity_ORU_Inbound.xml
│   └── code_templates/
│       └── MotherMrnResolver.xml
├── fastapi/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── README.md
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── logging_setup.py
│   │   ├── errors.py
│   │   ├── models/
│   │   ├── transformers/
│   │   ├── clients/
│   │   └── valuesets/
│   └── tests/
│       ├── unit/
│       │   ├── test_patient_transformer.py
│       │   ├── test_condition_transformer.py
│       │   ├── test_observation_transformer.py
│       │   └── test_encounter_transformer.py
│       └── integration/
│           └── test_end_to_end.py
├── samples/
│   ├── adt_a01_normal_delivery.hl7
│   ├── adt_a01_high_risk.hl7
│   ├── orm_o01_antenatal_28w.hl7
│   ├── oru_r01_vitals.hl7
│   ├── oru_r01_abnormal_bp.hl7
│   └── invalid/
│       ├── adt_missing_mrn.hl7        # tests NAK path
│       └── oru_bad_units.hl7
├── scripts/
│   ├── mllp_send.py                   # tiny MLLP client for testing
│   ├── seed_hapi.sh                   # warms up HAPI capability statement
│   └── reset.sh                       # docker compose down -v
├── deadletter/                        # gitignored runtime dir, kept with .gitkeep
└── logs/                              # gitignored, kept with .gitkeep
```

---

## 9. Development Phases / Milestones

| # | Phase | Deliverables | Definition of Done |
|---|---|---|---|
| **0** | Bootstrap | Repo, README skeleton, docker-compose with all 3 services starting, `/health` returns green | `docker compose up` → all healthy; `curl localhost:8080/fhir/metadata` returns CapabilityStatement |
| **1** | Patient happy-path | ADT^A01 → Patient end-to-end | One sample message in, one Patient in HAPI, MRN-based idempotency proven |
| **2** | Condition | DG1 parsing, Condition resource | Patient + Condition created from same ADT, references valid |
| **3** | Encounter | ORM^O01 → Encounter | Encounter linked to Patient by MRN |
| **4** | Observation (simple) | ORU^R01 → single OBX → Observation | Weight, fetal HR observations valid |
| **5** | Observation (BP panel) | Systolic + diastolic merged into one Observation | Component-based BP observation in HAPI |
| **6** | Validation & errors | NAK on bad input, RFC 7807 errors, dead-letter | Invalid message → NAK + file in `/deadletter/`, no HAPI write |
| **7** | Logging & correlation | JSON logs, correlation ID propagated end-to-end | `grep correlationId logs/*.log` finds the same ID in all 3 services |
| **8** | Testing | Unit + integration tests, CI green | `pytest` ≥ 80% coverage; GitHub Actions badge green |
| **9** | Polish | README screenshots, Architecture diagram PNG, recorded demo GIF | Recruiter can understand the project in < 2 minutes |
| **10** | (Stretch) AU Core validation | Add `$validate?profile=...au-core-patient` check | Validation runs in CI against published IG |

---

## 10. Testing Strategy

### 10.1 Test Pyramid

| Layer | Tool | Coverage |
|---|---|---|
| **Unit (Python)** | `pytest` + `fhir.resources` | Each transformer, each valueset map, edge cases |
| **Integration (Python)** | `pytest` + `httpx` against running stack | POST flat JSON → FastAPI → verify HAPI has resource |
| **End-to-end (HL7)** | `scripts/mllp_send.py` + `pytest` | Send `.hl7` file via MLLP → verify HAPI |
| **Validation** | HAPI `$validate` operation | Every output resource validates against R4 + AU Base where claimed |
| **Negative** | Invalid sample files | Confirm NAK + dead-letter behaviour |

### 10.2 Sample Test Cases

| Test | Input | Expected |
|---|---|---|
| `test_adt_a01_creates_patient` | `samples/adt_a01_normal_delivery.hl7` | Patient with MRN `1234567` exists in HAPI; IHI present |
| `test_adt_a01_idempotent` | Send same message twice | Single Patient, same logical id; no duplicate Conditions |
| `test_orm_o01_creates_encounter` | `samples/orm_o01_antenatal_28w.hl7` | Encounter with class=AMB, subject=Patient/1234567 |
| `test_oru_r01_bp_pairing` | `samples/oru_r01_vitals.hl7` | One Observation with code `85354-9` and two `component[]` |
| `test_oru_r01_fetal_hr` | same | Observation with LOINC `55283-6`, value 145, unit `/min` |
| `test_adt_missing_mrn_naks` | `samples/invalid/adt_missing_mrn.hl7` | Mirth returns NAK `AE`; no HAPI write; deadletter file written |
| `test_oru_bad_units_naks` | `samples/invalid/oru_bad_units.hl7` | FastAPI returns 422 problem+json; Mirth dead-letters |
| `test_health_endpoint` | `GET /health` | 200 with all services up |
| `test_correlation_id_propagates` | Any message | Same UUID in Mirth log, FastAPI log, HAPI request trace |
| `test_fhir_r4_validates` | All outputs | HAPI `$validate` → no errors |

### 10.3 The `mllp_send.py` Helper

A tiny MLLP client to drive tests without needing the Mirth Administrator UI:

```python
# scripts/mllp_send.py
import socket, sys, uuid
from pathlib import Path

VT, FS, CR = b"\x0b", b"\x1c", b"\x0d"

def send(host: str, port: int, hl7_path: str) -> str:
    msg = Path(hl7_path).read_bytes().replace(b"\n", b"\r")
    frame = VT + msg + FS + CR
    with socket.create_connection((host, port), timeout=5) as s:
        s.sendall(frame)
        buf = b""
        while not buf.endswith(FS + CR):
            chunk = s.recv(4096)
            if not chunk: break
            buf += chunk
    return buf.strip(VT + FS + CR).decode("latin-1")

if __name__ == "__main__":
    print(send("localhost", 6661, sys.argv[1]))
```

Usage: `python scripts/mllp_send.py samples/adt_a01_normal_delivery.hl7`
