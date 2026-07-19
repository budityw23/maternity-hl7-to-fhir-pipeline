# Product Requirements Document (PRD)
## Maternity HL7 v2 → FHIR R4 Integration Pipeline

| Field | Value |
|---|---|
| **Project Name** | Maternity HL7-to-FHIR Pipeline |
| **Document Version** | 1.0 |
| **Status** | Portfolio / Demonstration Project |
| **Target Standards** | HL7 v2.5, FHIR R4 (4.0.1), AU Base 4.x |
| **Document Owner** | [Your Name] — FHIR Software Engineer Candidate |

---

## 1. Project Purpose

### 1.1 Problem Statement
Australian maternity hospitals run heterogeneous clinical systems (PAS, EMR, LIS, perinatal data registries) that overwhelmingly speak **HL7 v2** for real-time messaging. Modern interoperability initiatives — including the **Australian Digital Health Agency's (ADHA)** Sparked program, **My Health Record**, and the **AU Core** FHIR Implementation Guide — require data to flow as **FHIR R4** resources.

This creates a persistent integration gap: legacy HL7 v2 must be reliably transformed, validated, and persisted as conformant FHIR R4 in real time, with appropriate audit trails and error handling.

### 1.2 Solution
A working, end-to-end pipeline that:
1. Receives HL7 v2 ADT, ORM, and ORU messages over MLLP from a simulated maternity hospital
2. Parses and pre-maps them in **Mirth Connect**
3. Transforms, validates, and enriches them via a **Python FastAPI** service using the `fhir.resources` library
4. Persists conformant FHIR R4 resources to a **HAPI FHIR Server**
5. Exposes a queryable FHIR REST API for downstream consumers (clinical viewers, registries, MHR adapters)

### 1.3 Goals
- **Primary:** Demonstrate end-to-end mastery of HL7 v2 → FHIR R4 transformation suitable for the Australian healthcare market.
- **Secondary:** Produce a recruiter-readable GitHub artefact (clean repo, runnable in one `docker compose up`, comprehensive README).
- **Tertiary:** Establish a reusable pattern extensible to additional message types and AU Core profiles.

---

## 2. Target Audience

| Audience | What They'll Evaluate |
|---|---|
| **Health IT recruiters (AU)** | Evidence of FHIR, HL7 v2, Mirth, and AU standards literacy |
| **Hiring engineering managers** | Code quality, validation rigour, Docker hygiene, documentation |
| **Senior FHIR engineers / architects** | Correctness of resource shapes, profile awareness, mapping fidelity |
| **Future me / contributors** | Maintainability, extensibility, clarity of mapping decisions |

This is a **portfolio project**, not a clinical-grade product. It must *look* production-minded — logging, validation, error handling, separation of concerns — without claiming clinical safety certification.

---

## 3. Functional Requirements

### 3.1 FR-1: Patient Resource (from ADT^A01)
The system shall transform the `PID` segment of an `ADT^A01` (Admit/Visit Notification) into a valid FHIR `Patient` resource representing the **mother**.

| ID | Requirement |
|---|---|
| FR-1.1 | Capture mother's identifiers (MRN, optionally IHI) from `PID-3` |
| FR-1.2 | Capture legal name (family + given) from `PID-5` |
| FR-1.3 | Capture date of birth from `PID-7` |
| FR-1.4 | Capture administrative sex from `PID-8`, mapped to FHIR `administrative-gender` |
| FR-1.5 | Capture address from `PID-11` including AU state codes |
| FR-1.6 | Capture phone (home/mobile) from `PID-13` |
| FR-1.7 | Mark `Patient.active = true` on `A01` |
| FR-1.8 | Where present, populate `meta.profile` with AU Base Patient profile URL |

### 3.2 FR-2: Condition Resource (from ADT^A01 DG1 segments)
The system shall transform `DG1` (Diagnosis) segments accompanying an `ADT^A01` into FHIR `Condition` resources representing the pregnancy diagnosis.

| ID | Requirement |
|---|---|
| FR-2.1 | Create one `Condition` per `DG1` segment |
| FR-2.2 | Map `DG1-3` (Diagnosis Code) to `Condition.code` using SNOMED CT-AU where ICD-10-AM codes can be cross-walked |
| FR-2.3 | Link `Condition.subject` to the Patient resource via reference |
| FR-2.4 | Map `DG1-5` (Diagnosis Date/Time) to `Condition.recordedDate` |
| FR-2.5 | Set `Condition.clinicalStatus = active` and `verificationStatus = confirmed` |
| FR-2.6 | Set `Condition.category = encounter-diagnosis` |

### 3.3 FR-3: Observation Resource (from ORU^R01)
The system shall transform `OBX` segments of an `ORU^R01` (Unsolicited Observation Result) into FHIR `Observation` resources for antenatal vitals.

| ID | Requirement |
|---|---|
| FR-3.1 | Create one `Observation` per `OBX` segment |
| FR-3.2 | Support blood pressure (systolic + diastolic as a panel using LOINC `85354-9`) |
| FR-3.3 | Support maternal weight (LOINC `29463-7`) |
| FR-3.4 | Support fetal heart rate (LOINC `55283-6`) |
| FR-3.5 | Map `OBX-5` to `valueQuantity` with UCUM units from `OBX-6` |
| FR-3.6 | Map `OBX-14` (or `OBR-7`) to `effectiveDateTime` |
| FR-3.7 | Set `status = final` when `OBX-11 = F` |
| FR-3.8 | Link `Observation.subject` to Patient and `Observation.encounter` to Encounter |
| FR-3.9 | Set `category = vital-signs` |

### 3.4 FR-4: Encounter Resource (from ORM^O01)
The system shall transform `PV1` and `ORC` segments of an `ORM^O01` (Order Message) into a FHIR `Encounter` resource representing the antenatal visit.

| ID | Requirement |
|---|---|
| FR-4.1 | Capture visit number from `PV1-19` as `Encounter.identifier` |
| FR-4.2 | Map `PV1-2` (Patient Class) to `Encounter.class` using v3 ActCode (`AMB` for ambulatory) |
| FR-4.3 | Map `PV1-44` (Admit Date) to `Encounter.period.start` |
| FR-4.4 | Map `PV1-45` (Discharge Date) to `Encounter.period.end` |
| FR-4.5 | Set `Encounter.serviceType` to a maternity/antenatal SNOMED code |
| FR-4.6 | Link `Encounter.subject` to Patient |
| FR-4.7 | Link `Encounter.participant` to the attending clinician from `PV1-7` |

### 3.5 FR-5: Cross-Cutting Functional Requirements
| ID | Requirement |
|---|---|
| FR-5.1 | All resources must reference the same logical Patient (resolved by MRN) |
| FR-5.2 | The pipeline must be idempotent — re-sending the same HL7 message must not create duplicate resources (use conditional create on identifier) |
| FR-5.3 | The pipeline must support bundle transactions for multi-resource messages (e.g., ORU with multiple OBX) |
| FR-5.4 | All FHIR resources must validate against the FHIR R4 base spec before submission |
| FR-5.5 | A `/health` endpoint must report status of Mirth → FastAPI → HAPI chain |

---

## 4. Non-Functional Requirements

### 4.1 Validation
| ID | Requirement |
|---|---|
| NFR-V.1 | All inbound HL7 messages must be parseable; malformed messages → NAK with `AE` (application error) acknowledgement |
| NFR-V.2 | All outbound FHIR resources must pass `fhir.resources` Pydantic validation before HAPI submission |
| NFR-V.3 | HAPI server validation mode set to `STRICT` for the demo |
| NFR-V.4 | Reject messages missing mandatory identifiers (no MRN → reject with reason logged) |

### 4.2 Error Handling
| ID | Requirement |
|---|---|
| NFR-E.1 | Mirth must return correct HL7 ACK/NAK (`AA`, `AE`, `AR`) for every inbound message |
| NFR-E.2 | FastAPI must return RFC 7807 problem+json for transformation errors |
| NFR-E.3 | Errors at the HAPI submission step must be retried with exponential backoff (max 3 attempts) |
| NFR-E.4 | Dead-letter queue: messages that fail terminally are written to `./deadletter/` as `.hl7` files with a sibling `.error.json` |

### 4.3 Logging
| ID | Requirement |
|---|---|
| NFR-L.1 | Structured JSON logging (one event per line) in FastAPI |
| NFR-L.2 | Each message tagged with a correlation ID (UUID v4) propagated from Mirth through to HAPI |
| NFR-L.3 | Log levels: `INFO` for happy path, `WARN` for validation degradations, `ERROR` for failures |
| NFR-L.4 | No PHI in log messages above `DEBUG` — log identifiers only, not names/DOB at INFO level |

### 4.4 Performance (demo-grade targets, not clinical)
| ID | Requirement |
|---|---|
| NFR-P.1 | End-to-end transform latency < 500 ms per message at p95 on a developer laptop |
| NFR-P.2 | Sustain 10 messages/sec for a 60-second burst without dropped messages |

### 4.5 Security (portfolio-appropriate)
| ID | Requirement |
|---|---|
| NFR-S.1 | All services run in an isolated Docker network |
| NFR-S.2 | No real PHI — sample data only, clearly marked as synthetic |
| NFR-S.3 | HAPI server runs with anonymous access for demo; README documents how to add SMART on FHIR for production |

---

## 5. Out of Scope

The following are deliberately excluded to keep the portfolio focused:

- **Clinical safety certification** (ISO 14971, IEC 62304)
- **My Health Record live connectivity** — referenced but not integrated (requires Provider Connect Australia / B2B SAML)
- **Healthcare Identifiers Service (HI Service)** live lookup — IHI is shown as a static example
- **SMART on FHIR / OAuth2** authentication on HAPI
- **Production-grade persistent storage** (HAPI uses default H2 in demo; Postgres swap documented)
- **HL7 v2.x versions other than 2.5** (e.g., 2.3.1, 2.8)
- **Other message types** (e.g., SIU, MDM, BAR) — extension pattern documented, not implemented
- **Other FHIR resources** beyond Patient, Condition, Observation, Encounter
- **AU Core profile validation** — AU Base profile referenced, full IG validation not enforced
- **TLS / mTLS** between services
- **Horizontal scaling / Kubernetes deployment**
- **UI / clinical viewer** — REST API only

---

## 6. Success Criteria

The project is successful when **all** of the following are true:

| ID | Criterion | Verification |
|---|---|---|
| SC-1 | A reviewer can clone the repo and run `docker compose up` to bring the full stack online | Manual test, documented in README |
| SC-2 | Sending each of the 3 sample HL7 messages (ADT^A01, ORM^O01, ORU^R01) via `mllp_send` results in correctly shaped FHIR resources in HAPI | Verified via `GET` to HAPI REST API + assertions in `tests/integration/` |
| SC-3 | All FHIR resources persist with FHIR R4 validation errors = 0 | HAPI `$validate` operation returns no errors |
| SC-4 | Mirth returns `AA` ACK for valid messages, `AE` NAK for malformed | Captured in integration tests |
| SC-5 | Mapping documentation (`docs/MAPPING.md`) covers every field used, with HL7 → FHIR provenance | Manual review |
| SC-6 | README has architecture diagram, quickstart, sample messages, and "Australian context" section | Manual review |
| SC-7 | CI pipeline (GitHub Actions) runs unit + integration tests on push | Green build badge |
| SC-8 | Repo has zero high-severity linter warnings (`ruff`, `mypy --strict` on the Python service) | Green CI |

---

## 7. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| HL7 v2 dialects differ between vendors | Medium | Medium | Document assumed dialect (HL7 v2.5 vanilla); use Mirth transformer to absorb minor variations |
| AU Base profile constraints change | Low | Low | Pin to a specific AU Base version in `meta.profile`; document upgrade path |
| `fhir.resources` library lag behind FHIR errata | Low | Medium | Pin version; document known gaps |
| Reviewers unfamiliar with Mirth | Medium | Low | Screenshots + exported channel XML in `mirth/channels/` |
| Synthetic data mistaken for real PHI | Low | High | Watermark sample messages with "SYNTHETIC — NOT REAL PATIENT DATA"; use obviously fake names (e.g., "Test, Patient") |

---

## 8. Glossary

| Term | Definition |
|---|---|
| **ADT** | Admit, Discharge, Transfer — HL7 v2 message family |
| **ORM** | Order Message — HL7 v2 message for orders |
| **ORU** | Observation Result — HL7 v2 message for results |
| **MLLP** | Minimal Lower Layer Protocol — TCP framing for HL7 v2 |
| **PID** | Patient Identification segment |
| **PV1** | Patient Visit segment |
| **OBX** | Observation/Result segment |
| **OBR** | Observation Request segment |
| **DG1** | Diagnosis segment |
| **ORC** | Common Order segment |
| **FHIR** | Fast Healthcare Interoperability Resources |
| **AU Base** | Australian base FHIR profiles published by HL7 Australia |
| **AU Core** | The narrower Sparked-led AU Core IG (subset of AU Base) |
| **ADHA** | Australian Digital Health Agency |
| **MHR** | My Health Record |
| **IHI** | Individual Healthcare Identifier (16-digit) |
| **HPI-I / HPI-O** | Healthcare Provider Identifiers (Individual / Organisation) |
| **SNOMED CT-AU** | Australian extension of SNOMED CT |
| **UCUM** | Unified Code for Units of Measure |
