# Maternity HL7-to-FHIR Pipeline: Bridging Legacy Hospital Messages to Modern Healthcare APIs

![Cover Image Placeholder: A pipeline diagram showing HL7 v2 messages flowing through Mirth Connect and Python/FastAPI into a HAPI FHIR Server]

---

## 🌱 How It Started

A few months ago, I was browsing remote FHIR engineer roles in Australia. Every single job description mentioned the same thing: *experience integrating HL7 v2 with FHIR R4*.

This makes sense. Australian hospitals — like most hospitals worldwide — still run on HL7 v2. Patient admissions, lab results, orders — they all flow as pipe-delimited messages over MLLP. But the direction is clear: the Australian Digital Health Agency (ADHA) is pushing hard toward FHIR R4 through the Sparked FHIR Accelerator and the AU Core Framework. Somebody has to build the bridge between these two worlds.

I decided to build one myself: a working pipeline that takes real HL7 v2 maternity messages and transforms them into valid, AU-profiled FHIR R4 resources. Not a toy. Not a tutorial. A real integration that I could show in interviews and say: *"I built this. Here's how it works. Here's where it breaks."*

This article walks through how I designed it — including the mistakes I made along the way.

---

## ⚡ My Initial (Naïve) Approach

My first instinct was simple. HL7 v2 comes in, I parse it in Python, I build a FHIR JSON, I POST it to a FHIR server. Done.

```
Hospital Maternity System
  │
  │  HL7 v2 messages (MLLP)
  ↓
Python Script
  │  → parse HL7
  │  → build FHIR JSON manually
  │  → POST to FHIR server
  ↓
HAPI FHIR Server
```

I wrote a quick script. It worked for a single `ADT^A01` (patient admission) message. I felt good about it. Then the problems started:

- **No MLLP handling**: My script was reading messages from a file. Real hospital systems don't send files — they send HL7 over MLLP (a TCP-based protocol with specific framing). My script had no way to receive live messages.
- **Brittle parsing**: I was splitting on `|` and counting positions. One unexpected empty field and the whole mapping shifted. A message with a maiden name in `PID-6` but nothing in `PID-5.4` (suffix) would silently put the wrong data in the wrong FHIR field.
- **No validation**: I was constructing FHIR JSON by hand as Python dicts. Typo in a field name? Missing a required element? The script happily sent invalid resources to the FHIR server, which sometimes accepted them and sometimes threw cryptic errors.
- **No multi-resource linking**: A maternity visit involves a Patient, an Encounter, Observations (blood pressure, weight, fetal heartbeat), and a Condition (pregnancy diagnosis). These resources need to reference each other. My script created them independently with no linking — the Observation had no idea which Encounter it belonged to.
- **No rollback**: If the Patient was created successfully but the Observation failed, I had orphaned resources sitting in the FHIR server with no cleanup.

I was building for the happy path again — the same mistake I described in my [vaccine appointment system article](https://dev.to/budiwidhiyanto/national-vaccine-appointment-administration-system-303o). One clean message in, one clean resource out. But healthcare data is never clean.

---

## 🔍 Rethinking the Architecture

The core insight was: **this is not a single transformation. It's a pipeline with distinct responsibilities.**

Receiving MLLP messages is a different concern from parsing HL7. Parsing is different from mapping. Mapping is different from FHIR validation. Validation is different from persistence. Each stage can fail independently, and each needs its own error handling.

I also realized that an integration engine like Mirth Connect already solves the hardest part — MLLP reception, HL7 parsing, and message routing. Fighting that battle in raw Python was wasting time on a solved problem.

Here's the redesigned architecture:

```
Hospital Maternity System
  │
  │  HL7 v2.5 messages over MLLP:
  │    ADT^A01  → patient admitted for antenatal care
  │    ORM^O01  → antenatal checkup ordered
  │    ORU^R01  → checkup results (BP, weight, fetal heartbeat)
  ↓
Mirth Connect 4.5 (port 6661)
  │  → receives MLLP, parses HL7 natively
  │  → extracts key segments (PID, PV1, OBX, DG1, OBR)
  │  → builds structured JSON payload
  │  → routes by message type to correct endpoint
  ↓
Python 3.11 + FastAPI
  │  → receives typed JSON from Mirth
  │  → maps fields to FHIR R4 with AU Base profiles
  │  → validates via fhir.resources (Pydantic models)
  │  → builds FHIR Bundle (Transaction) for atomic writes
  │  → POSTs Bundle to HAPI FHIR
  ↓
HAPI FHIR Server
  │  → stores Patient, Condition, Observation, Encounter
  │  → enforces referential integrity
  │  → serves FHIR REST API
  ↓
Accessible via standard FHIR queries
```

The key difference: **every component does one thing well**, and failure at any stage doesn't corrupt the others.

---

## 🧩 The Improved Design

### 1. Mirth Connect: The HL7 Gatekeeper

Mirth Connect listens on MLLP port 6661 and handles the protocol-level complexity that I was trying to reinvent in Python. It natively understands HL7 v2.5 segment structure, so I can reference `msg['PID']['PID.5']['PID.5.1']` directly in a JavaScript transformer — no string splitting, no position counting.

Mirth does three jobs:

- **Receives and parses**: Handles MLLP framing (the `\x0b` header and `\x1c\x0d` trailer), parses segments, and sends ACK/NACK responses back to the sender.
- **Extracts and restructures**: A JavaScript transformer pulls the fields I need and builds a clean JSON payload. This is where I handle HL7 quirks — like the fact that `PID-8` encodes sex as `F`/`M`/`U` but FHIR uses `female`/`male`/`unknown`.
- **Routes by message type**: `ADT^A01` goes to `/transform/adt`, `ORU^R01` goes to `/transform/oru`, `ORM^O01` goes to `/transform/orm`. Each endpoint in FastAPI knows exactly what shape of data to expect.

**Why not do everything in Mirth?** You can — plenty of teams build entire FHIR transformations in Mirth's JavaScript engine. But I wanted the FHIR validation layer in Python using `fhir.resources`, which gives me Pydantic-based validation against the full FHIR R4 spec. If I accidentally set `Observation.status` to `"done"` instead of `"final"`, Pydantic catches it before it ever reaches the FHIR server. You don't get that level of type safety in Mirth's JavaScript.

### 2. The Mapping Layer: Where the Real Work Happens

This is the heart of the pipeline. Each HL7 message type maps to one or more FHIR resources:

**ADT^A01 (Patient Admission)** produces:
- **Patient** — from `PID` segment (name, DOB, sex, address, IHI identifier)
- **Condition** — from `DG1` segment (pregnancy diagnosis, ICD-10-AM coded)
- **Encounter** — from `PV1` segment (visit number, class, admission date)

**ORU^R01 (Observation Result)** produces:
- **Observation** — from `OBX` segments (vital signs: blood pressure, weight, fetal heartbeat)
- References back to existing Patient and Encounter

**ORM^O01 (Order)** produces:
- **Encounter** — from `PV1` (the antenatal visit itself)
- References back to existing Patient

Here's where the complexity lives. A simple mapping like `PID-5.1` → `Patient.name[0].family` is straightforward. But consider blood pressure. In HL7 v2, systolic and diastolic come as two separate `OBX` segments:

```
OBX|1|NM|8480-6^Systolic BP^LN||120|mm[Hg]|90-120|N|||F
OBX|2|NM|8462-4^Diastolic BP^LN||80|mm[Hg]|60-80|N|||F
```

In FHIR R4, blood pressure is a single `Observation` resource with LOINC code `85354-9` (Blood pressure panel) containing two `component[]` entries — one for systolic, one for diastolic. So the transformer needs to detect consecutive BP-related OBX segments, merge them, and emit a composite resource. This is the kind of domain logic that makes healthcare integration genuinely hard — it's not just field-to-field mapping.

### 3. Australian Localisation

Since this targets the AU market, the FHIR resources conform to **AU Base profiles** where relevant:

- `Patient.meta.profile` references `http://hl7.org.au/fhir/StructureDefinition/au-patient`
- Patient identifiers include the **IHI** (Individual Healthcare Identifier) with system URI `http://ns.electronichealth.net.au/id/hi/ihi/1.0`
- Diagnosis coding uses **ICD-10-AM** (Australian Modification) rather than plain ICD-10
- Clinical terminology uses **SNOMED CT-AU** where applicable
- Addresses use 4-digit Australian postcodes and state codes (NSW, VIC, QLD, etc.)

This isn't just cosmetic. AU Base profiles have specific cardinality and terminology constraints. An `au-patient` resource without a valid identifier type code will fail validation against the profile. Getting this right demonstrates that I understand the difference between *generic FHIR* and *FHIR as it's actually used in Australian healthcare*.

### 4. FHIR Bundles: Atomic Writes

This was one of the biggest improvements over my naïve approach. Instead of creating resources one by one with individual POST requests, I build a **FHIR Transaction Bundle** that contains all related resources from a single message.

For an `ADT^A01`, the Bundle contains a Patient, a Condition, and an Encounter — all in one request. HAPI FHIR processes the entire Bundle as a transaction: either everything succeeds, or everything rolls back. No orphaned resources.

The Bundle also handles internal references. The Condition needs to reference the Patient, but the Patient doesn't have a server-assigned ID yet (it's being created in the same request). FHIR solves this with `fullUrl` entries and relative references within the Bundle — the server resolves them during transaction processing.

```json
{
  "resourceType": "Bundle",
  "type": "transaction",
  "entry": [
    {
      "fullUrl": "urn:uuid:patient-1",
      "resource": { "resourceType": "Patient", "..." : "..." },
      "request": { "method": "POST", "url": "Patient" }
    },
    {
      "fullUrl": "urn:uuid:condition-1",
      "resource": {
        "resourceType": "Condition",
        "subject": { "reference": "urn:uuid:patient-1" }
      },
      "request": { "method": "POST", "url": "Condition" }
    }
  ]
}
```

### 5. Failure Scenarios

Just like with the vaccine system, I forced myself to think about what breaks:

- **Malformed HL7 message**: Mirth rejects it at the protocol level and sends a NACK. The message never reaches FastAPI. Logged for review.
- **Missing required fields**: FastAPI receives the JSON but the transformer can't find `PID-5` (patient name). The endpoint returns a 422 with a clear error message. Mirth logs the failure and can route the original message to a dead-letter queue.
- **FHIR validation failure**: The `fhir.resources` Pydantic model rejects the resource — maybe `Observation.status` has an invalid value, or a required CodeableConcept is missing. The error includes exactly which field failed and why.
- **HAPI FHIR rejects the Bundle**: Maybe a duplicate Patient already exists and the conditional create logic isn't configured correctly. The entire transaction rolls back. FastAPI returns the OperationOutcome from HAPI so the error is traceable.
- **Duplicate messages**: Hospital systems sometimes send the same message twice (network retry, interface engine restart). The pipeline uses conditional creates (`If-None-Exist` headers in the Bundle) based on the Medical Record Number (MRN) for Patient and visit number for Encounter. Second submission is a no-op, not a duplicate record.

---

## 🏗️ System Components

Here's the full component view:

```
┌──────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                          │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────┐  │
│  │   Mirth      │    │   FastAPI     │    │  HAPI FHIR │  │
│  │  Connect     │───▶│   Python      │───▶│   Server   │  │
│  │  4.5         │    │   3.11+       │    │            │  │
│  │              │    │              │    │            │  │
│  │  Port: 6661  │    │  Port: 8000  │    │ Port: 8080 │  │
│  │  (MLLP)      │    │  (HTTP)      │    │ (FHIR REST)│  │
│  └─────────────┘    └──────────────┘    └────────────┘  │
│                                                          │
│  Services:                                               │
│  - mirth         (nextgenhealthcare/connect:4.5)        │
│  - transformer   (python:3.11-slim + FastAPI)           │
│  - fhir-server   (hapiproject/hapi:latest)              │
│  - fhir-db       (postgres:15 — HAPI backend)           │
└──────────────────────────────────────────────────────────┘
```

- **Mirth Connect 4.5** — The integration engine. Handles MLLP, parses HL7, routes by message type, sends structured JSON downstream.
- **Python FastAPI** — The transformation and validation layer. Three endpoints (`/transform/adt`, `/transform/oru`, `/transform/orm`), each with dedicated converter modules (`patient.py`, `condition.py`, `observation.py`, `encounter.py`). Uses `fhir.resources` for Pydantic-based FHIR R4 validation.
- **HAPI FHIR Server** — The FHIR repository. Stores resources, serves the REST API, handles Transaction Bundles, and enforces referential integrity.
- **PostgreSQL** — HAPI's persistence backend.

Everything runs with `docker-compose up`. One command, full pipeline.

### Repository Structure

```
maternity-fhir-pipeline/
├── mirth/
│   └── channels/               # Mirth channel XML configs
├── python/
│   ├── main.py                 # FastAPI app
│   ├── converters/
│   │   ├── patient.py          # HL7 → FHIR Patient (AU Base)
│   │   ├── observation.py      # HL7 → FHIR Observation (BP panel logic)
│   │   ├── encounter.py        # HL7 → FHIR Encounter
│   │   └── condition.py        # HL7 → FHIR Condition (ICD-10-AM)
│   ├── bundle_builder.py       # Transaction Bundle assembly
│   ├── tests/
│   │   ├── test_patient.py     # Unit tests per converter
│   │   ├── test_observation.py
│   │   ├── fixtures/           # Sample HL7 messages
│   │   └── integration/        # End-to-end pipeline tests
│   └── requirements.txt
├── docker-compose.yml
├── scripts/
│   └── mllp_send.py            # Test utility: send HL7 over MLLP
├── docs/
│   ├── PRD.md
│   ├── TECHNICAL_PLAN.md
│   └── AU_CONTEXT.md
└── README.md
```

---

## 🎯 What I Learned

Building this project taught me things I couldn't have learned from reading the FHIR spec alone.

**HL7 v2 is deceptively simple.** The pipe-delimited format looks easy to parse until you encounter repeating fields, component separators, escape characters, and the fact that different hospitals implement the same message type differently. An integration engine like Mirth saves enormous time here — it's purpose-built for this chaos.

**FHIR validation is your safety net, not your enemy.** My naïve approach skipped validation because it felt like extra work. In practice, the Pydantic models from `fhir.resources` caught errors that would have taken hours to debug at the FHIR server level. A missing `Observation.code.coding[0].system`? Pydantic tells you immediately. HAPI FHIR gives you a generic 400.

**Transaction Bundles change everything.** The moment I switched from individual POSTs to Bundles, the entire error handling story simplified. Either all resources from a message are persisted, or none are. No more orphan cleanup, no more inconsistent state.

**The AU localisation is what separates a tutorial from a portfolio project.** Anyone can map `PID-5` to `Patient.name`. Knowing that Australian systems use IHI identifiers, ICD-10-AM coding, AU Base profile URLs, and SNOMED CT-AU — and encoding all of that correctly in the FHIR resources — shows real domain expertise. In interviews, this is what gets follow-up questions.

**Start with failure scenarios, not the happy path.** This is the same lesson from my vaccine appointment system design, and it applies everywhere. The first question to ask about any integration is not "how does it work?" but "what happens when it breaks?"

---

## 🔗 What's Next

This pipeline currently covers 4 FHIR resources and 3 HL7 message types — deliberately scoped to be buildable as a portfolio project while demonstrating real integration patterns. Extensions I'm considering:

- **AU Core compliance** — moving beyond AU Base profiles to the stricter AU Core Implementation Guide that Australia is actively rolling out through the Sparked program
- **Terminology validation** — integrating with a FHIR terminology server to validate SNOMED CT-AU and LOINC codes at transformation time, not just at persistence
- **Monitoring dashboard** — a simple frontend showing message throughput, transformation success/failure rates, and recent errors

The full documentation (PRD, Technical Planning Document, and Australian Context Guide) is in the `docs/` folder of the repository.

---

*If you're working on HL7-to-FHIR integrations or preparing for health IT interviews, I'd like to hear what challenges you've run into. You might also find my earlier article on the [National Vaccine Appointment & Administration System](https://dev.to/budiwidhiyanto/national-vaccine-appointment-administration-system-303o) useful — it covers similar design thinking around failure handling and rollback patterns.*

---

**Tags:** `#fhir` `#healthit` `#hl7` `#architecture`