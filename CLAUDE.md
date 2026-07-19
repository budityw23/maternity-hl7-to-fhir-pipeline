# Maternity HL7-to-FHIR Pipeline

## Project Overview

Portfolio/demonstration project showing end-to-end HL7 v2 → FHIR R4 transformation for Australian healthcare. **Not clinical-grade** — must look production-minded (logging, validation, error handling, separation of concerns) without claiming clinical safety certification.

Target audience: AU Health IT recruiters, hiring engineering managers, senior FHIR engineers.

## Architecture

Three Docker Compose services on `maternity-net` bridge network:

1. **Mirth Connect 4.5** (port 6661) — MLLP listener, HL7 v2.5 parser, JavaScript transformers, routes flat JSON to FastAPI by message type
2. **Python FastAPI** (port 8000) — receives flat JSON from Mirth, builds/validates FHIR R4 resources via `fhir.resources` (Pydantic), POSTs to HAPI FHIR
3. **HAPI FHIR Server v7.0.3** (port 8080) — persists FHIR R4 resources, REST API, `$validate` support

Data flow: Hospital → MLLP → Mirth (parse + extract + route) → HTTP POST → FastAPI (transform + validate) → HAPI FHIR (persist)

## Standards & Terminologies

| Standard | Version/Detail |
|---|---|
| HL7 v2 | 2.5 |
| FHIR | R4 (4.0.1) |
| AU Base | 4.x profiles |
| IHI system | `http://ns.electronichealth.net.au/id/hi/ihi/1.0` |
| MRN system | `http://hospital.local/mrn` |
| ICD-10-AM | `http://hl7.org.au/fhir/CodeSystem/icd-10-am` |
| SNOMED CT | `http://snomed.info/sct` (AU edition) |
| LOINC | `http://loinc.org` |
| UCUM | `http://unitsofmeasure.org` |

## Message Types → FHIR Resources

| HL7 Message | FHIR Resources Produced | Key Segments |
|---|---|---|
| ADT^A01 (Admission) | Patient + Condition(s) | PID, DG1 |
| ORM^O01 (Order) | Encounter | PV1, ORC, OBR |
| ORU^R01 (Observation) | Observation(s) | OBX, OBR, PV1 |

## Key Design Decisions

- **Blood pressure panel merging**: Consecutive OBX segments with LOINC 8480-6 (systolic) and 8462-4 (diastolic) merge into single Observation with code 85354-9 and two `component[]` entries
- **Idempotency**: Conditional create/update via `PUT /Patient?identifier=...` — re-sending same HL7 message produces no duplicates
- **FHIR Transaction Bundles**: Multi-resource messages (e.g., ADT with Patient + Condition) submitted as atomic Bundle transactions
- **Error handling**: Mirth returns HL7 ACK/NAK (AA/AE/AR); FastAPI returns RFC 7807 problem+json; dead-letter queue in `./deadletter/`
- **Correlation ID**: UUID v4 generated in Mirth, passed via `X-Correlation-ID` header, logged everywhere
- **No PHI in logs**: Log identifiers only at INFO level, not names/DOB

## Tech Stack

- **Python 3.11+**, FastAPI, `fhir.resources`, `httpx`, `pydantic-settings`
- **Mirth Connect 4.5** (NextGen Healthcare) with JavaScript transformers
- **HAPI FHIR Server v7.0.3** (H2 for demo, Postgres swap documented)
- **Docker Compose** orchestration
- **pytest** for testing, **ruff** for linting, **mypy --strict** for type checking
- **GitHub Actions** for CI

## Planned Directory Structure

```
maternity-hl7-to-fhir/
├── docker-compose.yml
├── fastapi/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── app/
│       ├── main.py                 # FastAPI app, routes
│       ├── config.py               # pydantic-settings (env vars)
│       ├── logging_setup.py        # JSON logging with correlation ID
│       ├── errors.py               # RFC 7807 problem+json
│       ├── models/                 # Pydantic models for Mirth payloads
│       │   ├── adt_payload.py
│       │   ├── orm_payload.py
│       │   └── oru_payload.py
│       ├── transformers/           # HL7→FHIR mapping logic
│       │   ├── patient.py          # build_patient() → Patient
│       │   ├── condition.py        # build_conditions() → list[Condition]
│       │   ├── encounter.py        # build_encounter() → Encounter
│       │   └── observation.py      # build_observations() → list[Observation]
│       ├── clients/
│       │   └── hapi_client.py      # httpx client, conditional create
│       └── valuesets/
│           ├── icd10am_to_snomed.py
│           └── hl7_to_fhir_gender.py
├── mirth/
│   ├── channels/                   # Exported channel XML configs
│   └── code_templates/
├── samples/                        # Sample HL7 messages (synthetic)
├── scripts/
│   ├── mllp_send.py               # MLLP test client
│   ├── seed_hapi.sh
│   └── reset.sh                   # docker compose down -v
├── tests/
│   ├── unit/
│   └── integration/
├── deadletter/                     # Runtime, gitignored
└── logs/                           # Runtime, gitignored
```

## FastAPI Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health probe (Mirth + HAPI status) |
| POST | `/fhir/Patient` | ADT flat JSON → Patient + Conditions |
| POST | `/fhir/Encounter` | ORM flat JSON → Encounter |
| POST | `/fhir/Observation/bundle` | ORU observations array → Observations (with BP pairing) |
| GET | `/fhir/Patient/{mrn}` | Convenience lookup by MRN |

## AU Base Profile URLs

- Patient: `http://hl7.org.au/fhir/StructureDefinition/au-patient`
- Condition: `http://hl7.org.au/fhir/StructureDefinition/au-condition`
- Encounter: `http://hl7.org.au/fhir/StructureDefinition/au-encounter`
- Observation (BP): `http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure`

## Development Phases

0. Bootstrap — Docker Compose, `/health` endpoint
1. Patient happy-path — ADT^A01 → Patient, MRN idempotency
2. Condition — DG1 → Condition with Patient reference
3. Encounter — ORM^O01 → Encounter linked to Patient
4. Observation (simple) — ORU^R01 single OBX → Observation
5. Observation (BP panel) — Systolic + diastolic merge
6. Validation & errors — NAK on bad input, dead-letter
7. Logging & correlation — JSON logs, correlation ID propagation
8. Testing — Unit + integration, CI green, ≥80% coverage
9. Polish — README, architecture diagram, demo GIF
10. (Stretch) AU Core validation

## Code Conventions

- Linting: `ruff` (no high-severity warnings)
- Type checking: `mypy --strict`
- Testing: `pytest` with unit + integration layers
- Logging: structured JSON, one event per line, correlation ID on every log
- Log levels: INFO happy path, WARN validation degradations, ERROR failures
- All sample data must be clearly marked as synthetic ("SYNTHETIC — NOT REAL PATIENT DATA")
- All FHIR resources must pass `fhir.resources` Pydantic validation before HAPI submission

## Related Codebase

Existing FHIR conversion utilities at:
`/home/budi/code/sphere_project/main_converter_folder/process-fhir-converter/extra_logics/`

Potentially reusable modules:
- `snomed.py` — SNOMED CT utilities
- `loinc.py` — LOINC code utilities
- `icd10.py` — ICD-10 utilities
- `general.py` — General FHIR resource builders
- `fhir_query.py` — FHIR query utilities
- `references.py` — FHIR reference handling
- `hl7.py` — HL7 utilities

## Quick Reference

- Run: `docker compose up`
- Test: `pytest`
- Send HL7: `python scripts/mllp_send.py samples/adt_a01_normal_delivery.hl7`
- HAPI API: `http://localhost:8080/fhir/`
- FastAPI: `http://localhost:8000/`
- Mirth Admin: `https://localhost:8443/`
- Reset: `./scripts/reset.sh` (docker compose down -v)
