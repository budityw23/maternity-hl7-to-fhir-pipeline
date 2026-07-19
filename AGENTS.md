# Maternity HL7-to-FHIR Pipeline — Codex Agent Instructions

## Role

You are the **executor** for this project. A human planner (using Claude Opus) writes phase execution docs in `docs/execution/`. Your job is to follow those docs precisely, creating files and running commands as specified.

## Project Overview

Portfolio/demonstration project: end-to-end HL7 v2 → FHIR R4 transformation for Australian healthcare. **Not clinical-grade** — must look production-minded (logging, validation, error handling, separation of concerns) without claiming clinical safety certification.

## Architecture

Three Docker Compose services on `maternity-net` bridge network:

1. **Mirth Connect 4.5** (port 6661) — MLLP listener, HL7 v2.5 parser, JavaScript transformers, routes flat JSON to FastAPI by message type
2. **Python FastAPI** (port 8000) — receives flat JSON from Mirth, builds/validates FHIR R4 resources via `fhir.resources` (Pydantic), POSTs to HAPI FHIR
3. **HAPI FHIR Server v7.0.3** (port 8080) — persists FHIR R4 resources, REST API, `$validate` support

Data flow: `Hospital → MLLP → Mirth → HTTP POST → FastAPI → HAPI FHIR`

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

## Tech Stack

- **Python 3.11+**, FastAPI, `fhir.resources`, `httpx`, `pydantic-settings`
- **Mirth Connect 4.5** (NextGen Healthcare) with JavaScript transformers
- **HAPI FHIR Server v7.0.3** (H2 for demo)
- **Docker Compose** orchestration
- **pytest** for testing, **ruff** for linting, **mypy --strict** for type checking

## Code Conventions

- Linting: `ruff` — zero high-severity warnings
- Type checking: `mypy --strict`
- Testing: `pytest` with unit + integration layers
- Logging: structured JSON, one event per line, correlation ID on every log entry
- Log levels: `INFO` happy path, `WARN` validation degradations, `ERROR` failures
- All sample data must be clearly marked as synthetic: include "SYNTHETIC — NOT REAL PATIENT DATA" in sample HL7 messages
- All FHIR resources must pass `fhir.resources` Pydantic validation before HAPI submission
- No PHI in logs above DEBUG level — log identifiers only, not names/DOB

## Directory Structure

```
maternity-hl7-to-fhir/
├── AGENTS.md                       ← you are here
├── CLAUDE.md                       ← Claude Opus planner instructions
├── docker-compose.yml
├── .gitignore
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
│       │   ├── patient.py
│       │   ├── condition.py
│       │   ├── encounter.py
│       │   └── observation.py
│       ├── clients/
│       │   └── hapi_client.py
│       └── valuesets/
│           ├── icd10am_to_snomed.py
│           └── hl7_to_fhir_gender.py
├── mirth/
│   ├── channels/
│   └── code_templates/
├── samples/
├── scripts/
│   ├── mllp_send.py
│   ├── seed_hapi.sh
│   └── reset.sh
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   ├── 01_PRD.md
│   ├── 02_TECHNICAL_PLAN.md
│   ├── 03_AUSTRALIAN_CONTEXT.md
│   ├── 04_ARTICLE.md
│   └── execution/                  # Phase execution docs (you follow these)
├── deadletter/                     # Runtime, gitignored
└── logs/                           # Runtime, gitignored
```

## How to Execute a Phase

1. Read the current phase doc at `docs/execution/PHASE_N_*.md`
2. Follow tasks in order — each task specifies exact file paths and content
3. Run verification commands listed at the end of the phase doc
4. Report results — what succeeded, what failed, any issues encountered

## Key Design Decisions (Reference)

- **Blood pressure panel merging**: Consecutive OBX segments with LOINC 8480-6 (systolic) and 8462-4 (diastolic) → single Observation with code 85354-9 and two `component[]` entries
- **Idempotency**: Conditional create/update via `PUT /Resource?identifier=...` — re-sending same HL7 message produces no duplicates
- **FHIR Transaction Bundles**: Multi-resource messages submitted as atomic Bundle transactions
- **Error handling**: Mirth returns HL7 ACK/NAK; FastAPI returns RFC 7807 problem+json; dead-letter queue in `./deadletter/`
- **Correlation ID**: UUID v4 generated in Mirth, passed via `X-Correlation-ID` header, logged everywhere

## AU Base Profile URLs

- Patient: `http://hl7.org.au/fhir/StructureDefinition/au-patient`
- Condition: `http://hl7.org.au/fhir/StructureDefinition/au-condition`
- Encounter: `http://hl7.org.au/fhir/StructureDefinition/au-encounter`
- Observation (BP): `http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure`

## FastAPI Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health probe (Mirth + HAPI status) |
| POST | `/fhir/Patient` | ADT flat JSON → Patient + Conditions |
| POST | `/fhir/Encounter` | ORM flat JSON → Encounter |
| POST | `/fhir/Observation/bundle` | ORU observations array → Observations |
| GET | `/fhir/Patient/{mrn}` | Convenience lookup by MRN |

## Message Types → FHIR Resources

| HL7 Message | FHIR Resources | Key Segments |
|---|---|---|
| ADT^A01 (Admission) | Patient + Condition(s) | PID, DG1 |
| ORM^O01 (Order) | Encounter | PV1, ORC, OBR |
| ORU^R01 (Observation) | Observation(s) | OBX, OBR, PV1 |

## Development Phases

| # | Phase | Status |
|---|---|---|
| 0 | Bootstrap — Docker Compose, `/health` endpoint | Current |
| 1 | Patient happy-path — ADT^A01 → Patient | Pending |
| 2 | Condition — DG1 → Condition | Pending |
| 3 | Encounter — ORM^O01 → Encounter | Pending |
| 4 | Observation (simple) — single OBX | Pending |
| 5 | Observation (BP panel) — merge systolic+diastolic | Pending |
| 6 | Validation & errors — NAK, dead-letter | Pending |
| 7 | Logging & correlation — JSON logs, correlation ID | Pending |
| 8 | Testing — unit + integration, CI | Pending |
| 9 | Polish — README, diagrams, demo | Pending |
| 10 | (Stretch) AU Core validation | Pending |
