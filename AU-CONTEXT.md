# Australian Context
## Maternity HL7 v2 → FHIR R4 Pipeline — AU Standards Alignment

This document explains how the project aligns with Australian digital health standards and where, if extended to production, it would need to plug into the national infrastructure.

---

## 1. Why This Matters for AU Healthcare Roles

Australian health IT is in the middle of a multi-year shift from HL7 v2 messaging to FHIR R4, driven by:

- The **Australian Digital Health Agency (ADHA)** as system operator of national infrastructure
- **HL7 Australia** as the standards authoring body for AU Base
- The **Sparked AU FHIR Accelerator** — the multi-stakeholder program that produced the **AU Core** Implementation Guide
- State and territory health departments running their own FHIR-forward programs (e.g., NSW Health Single Digital Patient Record, Queensland Health ieMR)

Any FHIR engineer working in Australia in 2026 is expected to understand:

1. The relationship between **AU Base** (the broad set of profiles) and **AU Core** (the narrower must-support subset)
2. The role of **My Health Record** and how systems integrate with it
3. The **Healthcare Identifiers (HI) Service** — IHI, HPI-I, HPI-O
4. Use of **SNOMED CT-AU**, **AMT** (Australian Medicines Terminology), **LOINC**, **UCUM**, and **ICD-10-AM**

This project demonstrates literacy in points 1, 3, and 4, and a clear understanding of point 2.

---

## 2. AU Base FHIR Profile Considerations

### 2.1 What AU Base Is
**AU Base** is the foundational set of FHIR profiles published by HL7 Australia that constrain base R4 resources for the Australian context. Profiles relevant to this project:

| Base Resource | AU Base Profile |
|---|---|
| `Patient` | `http://hl7.org.au/fhir/StructureDefinition/au-patient` |
| `Condition` | `http://hl7.org.au/fhir/StructureDefinition/au-condition` |
| `Encounter` | `http://hl7.org.au/fhir/StructureDefinition/au-encounter` |
| `Observation` | `http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure` (and similar specialised vitals) |

### 2.2 Key Constraints Applied in This Project

| Constraint | Where It Appears |
|---|---|
| Patient `identifier` includes IHI with system `http://ns.electronichealth.net.au/id/hi/ihi/1.0` | `Patient.identifier[1]` in §3.1 mapping |
| Patient `identifier` MRN typed with v2-0203 code `MR` | `Patient.identifier[0].type.coding` |
| Address uses AU state codes (NSW/VIC/QLD/WA/SA/TAS/ACT/NT) and 4-digit postcodes | `Patient.address.state`, `Patient.address.postalCode` |
| Address `country` defaults to `AU` | `Patient.address.country` |
| `meta.profile` claims AU Base conformance | `Patient.meta.profile[0]` |
| ICD-10-AM as the diagnosis code system | `Condition.code.coding[0].system` |
| SNOMED CT for service type (using international SNOMED `http://snomed.info/sct` — SNOMED CT-AU resolves through the same canonical) | `Encounter.serviceType` |
| LOINC + UCUM for vitals | `Observation.code` and `Observation.valueQuantity` |

### 2.3 AU Core vs AU Base
**AU Core** is a tighter subset of AU Base, modelled on US Core, designed to be the minimum baseline for AU FHIR interoperability. As of 2026 it's the IG most likely to be enforced by national programs.

This project **claims AU Base** in `meta.profile` (a reasonable, achievable scope for a portfolio) and documents what would change to claim AU Core:

| AU Core Requirement | Status in this Project |
|---|---|
| Must-support `Patient.identifier` (IHI) | ✅ Implemented when present in HL7 |
| Must-support `Patient.name` | ✅ |
| Must-support `Patient.gender`, `Patient.birthDate` | ✅ |
| Must-support `Patient.address` | ✅ |
| Indigenous status extension (`indigenous-status`) | ⚠️ Not modelled — would need a new HL7 field (e.g., custom `ZID-1`) |
| Pronoun extension | ⚠️ Out of scope |
| AU Core Observation conformance (BP, body weight, etc.) | ⚠️ Partially — would need full slicing of components |

The stretch milestone (Phase 10 in the technical plan) is to enable HAPI's `$validate?profile=...au-core-patient` and iterate until clean.

---

## 3. ADHA Standards Alignment

The **Australian Digital Health Agency** publishes several specifications that touch this pipeline.

### 3.1 Healthcare Identifiers (HI) Service
- **IHI (Individual Healthcare Identifier)**: 16-digit number for consumers. Assigned by Services Australia. Used as a `Patient.identifier` with system `http://ns.electronichealth.net.au/id/hi/ihi/1.0`.
- **HPI-I (Provider — Individual)**: for clinicians. Would be added to `Practitioner.identifier` and `Encounter.participant.individual.identifier` in a production extension of this project.
- **HPI-O (Provider — Organisation)**: for facilities. Would belong on `Organization.identifier` and `Location.managingOrganization`.

In this project: IHI is **shown as a literal value** in sample HL7 messages and copied through to FHIR. A **production extension** would call the HI Service B2B SOAP/REST interface from the FastAPI service to resolve/validate IHI from name+DOB+Medicare — that requires a Notice of Integration with ADHA, contracted access, and a PKI certificate, all out of scope for a portfolio piece but worth naming as a known gap.

### 3.2 Secure Messaging (Argus / HealthLink / Medical Objects)
Not directly relevant to in-hospital integration, but worth noting: ADHA's **Secure Message Delivery (SMD)** standard governs B2B clinical messaging between organisations. This project handles intra-hospital messaging only; SMD would apply if the maternity service had to send discharge summaries to a GP.

### 3.3 Terminology
The pipeline uses internationally aligned terminologies that are accepted by AU programs:

| Terminology | Use | Notes |
|---|---|---|
| **SNOMED CT-AU** | Clinical findings, procedures, service types | Distributed by NCTS (National Clinical Terminology Service). Resolves via `http://snomed.info/sct` with implicit Australian edition module. |
| **AMT (Australian Medicines Terminology)** | Medications | Out of scope for this project (no MedicationRequest). |
| **LOINC** | Observations | Endorsed by ADHA for lab and vital signs. |
| **UCUM** | Units of measure | Required by FHIR R4 for `valueQuantity.system`. |
| **ICD-10-AM** | Inpatient diagnoses (admitted episodes) | Used in `Condition.code` from `DG1-3`. Captured with system `http://hl7.org.au/fhir/CodeSystem/icd-10-am`. |
| **METeOR Data Standards** | National reporting (AIHW) | Not directly mapped, but downstream perinatal reporting would draw from FHIR resources produced here. |

A production extension would add a terminology server lookup (e.g., **Ontoserver**, the CSIRO-built terminology server used by NCTS) to validate codes before persistence.

---

## 4. My Health Record (MHR) Relevance

**My Health Record** is the national consumer health record run by ADHA. It is **not** a clinical system — it's an aggregate summary repository. Relevance to this project:

### 4.1 What MHR Would Receive From a Maternity System
- **Discharge summaries** (eDS) after delivery — would be produced as CDA documents or FHIR Composition resources
- **Pathology and DI reports** — independent of this pipeline
- **Shared Health Summary** updates from the GP, not the hospital
- **Antenatal summary** — currently not a defined MHR document type, but proposed under the maternity work stream

### 4.2 What MHR Would *Not* Receive
- Raw ADT messages
- Individual antenatal vital signs (the use case this pipeline handles)
- Routine ORM orders

MHR is summary-grade, not stream-grade. **This pipeline produces stream-grade FHIR resources** — the right shape to feed a hospital's internal FHIR repository, which could then generate periodic CDA documents for MHR upload.

### 4.3 What Would Be Needed for Live MHR Integration
- **NASH certificate** (National Authentication Service for Health) for the organisation
- **Provider Connect Australia** registration
- **MHR B2B Gateway** integration (SOAP-based, with SAML assertions)
- **Patient consent** workflow — MHR participation is opt-out at the consumer level, but per-document consent applies
- **CDA generation** (or FHIR-to-CDA bridge) for documents like Discharge Summary

None of these are in scope, but the architecture deliberately leaves room: the HAPI FHIR Server can act as the source-of-truth from which a downstream MHR Upload Service would generate CDA documents.

---

## 5. Practical Notes for AU Readers / Recruiters

A few signals embedded in this project that an AU health IT recruiter or senior engineer will recognise:

1. **AU state codes in address** (`NSW`, `VIC`) — instead of US-style 2-letter codes
2. **AU postcode** (4-digit, not 5-digit ZIP)
3. **AU mobile format** (`04xx xxx xxx`) in HL7 `PID-13`
4. **IHI in PID-3** with type code `NI` (per HL7 v2 AU localisation guidance)
5. **ICD-10-AM** (not US ICD-10-CM, not WHO ICD-10) for `DG1-3`
6. **AU Base profile URLs** in `meta.profile`
7. **Timezone** `+10:00` (AEST) on timestamps in FHIR output
8. **Country** `AU` defaulted on addresses
9. **Maternity context** — recognising that Australian maternity services collect specific data (e.g., gestational age, parity, indigenous status) that map to extensions not present in vanilla US Core

---

## 6. Where This Project Stops and Production Begins

A clean way to frame this project in interviews:

> *"This portfolio piece is the **hospital-internal** half of the integration story — taking HL7 v2 from a clinical system and producing AU Base–profiled FHIR R4 resources in a hospital FHIR repository. The **national** half — HI Service resolution, NASH/PKI auth, MHR document upload, secure messaging to GPs — sits one layer up and needs ADHA-issued credentials I wouldn't have outside a contracted engagement. I've documented those touchpoints so you can see I understand where this layer fits."*

That framing demonstrates: (a) knowing the scope of the standard, (b) knowing what you don't know, and (c) being able to extend the work into the national context once you do have access.

---

## 7. References

| Resource | URL |
|---|---|
| HL7 Australia AU Base IG | `https://hl7.org.au/fhir/` |
| Sparked / AU Core IG | `https://hl7.org.au/fhir/core/` |
| ADHA (Australian Digital Health Agency) | `https://www.digitalhealth.gov.au/` |
| My Health Record | `https://www.myhealthrecord.gov.au/` |
| NCTS (terminology) | `https://www.healthterminologies.gov.au/` |
| Ontoserver | `https://ontoserver.csiro.au/` |
| Services Australia — HI Service | `https://www.servicesaustralia.gov.au/healthcare-identifiers-service` |
| METeOR (AIHW data standards) | `https://meteor.aihw.gov.au/` |

> All URLs current at time of writing (May 2026); verify before citing in any production document.
