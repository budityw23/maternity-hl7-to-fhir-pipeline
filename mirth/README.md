# Mirth Connect — HL7 v2.5 Ingestion Layer

This directory holds the Mirth Connect configuration for the pipeline's front door:
the MLLP listener, HL7 v2.5 parsing, and message-type routing to the FastAPI service.

> **SYNTHETIC DATA ONLY — not for clinical use.**

## Contents

| Path | What it is |
|---|---|
| `channels/Maternity_Inbound.xml` | Exported Mirth 4.5 channel: MLLP source (port 6661) + HTTP Sender destination. Importable via the Admin UI or `scripts/import_channels.sh`. |
| `code_templates/maternity_transformers.js` | Source-of-truth JavaScript for the destination transformer. The channel XML embeds a copy; keep them in sync. |
| `tools/GenerateChannel.java` | Regenerates `channels/Maternity_Inbound.xml` from Mirth's own model classes (see [How the channel XML is generated](#how-the-channel-xml-is-generated)). |

## Channel design — `Maternity Inbound HL7`

```
MLLP :6661 (HL7 v2.5)
  │  source connector: TCP Listener, MLLP frame (0x0B … 0x1C 0x0D)
  │  inbound datatype HL7V2 → auto-generates ACK (AA) / NAK (AE/AR)
  ▼
preprocessor: correlationId = UUIDGenerator.getUUID()   (one per message)
  ▼
destination "FastAPI FHIR Transform" (HTTP Sender)
  │  JavaScript transformer parses msg by canonical HL7 position and routes on MSH-9.1:
  │    ADT → /fhir/Patient   ORM → /fhir/Encounter   ORU → /fhir/Observation/bundle
  │  POST http://fastapi:8000${path}
  │  headers: Content-Type: application/json, X-Correlation-ID: ${correlationId}
  ▼
FastAPI (transform + validate + persist to HAPI FHIR)
```

The transformer emits the exact flat-JSON contract the FastAPI Pydantic models expect
(`AdtPayload` / `OrmPayload` / `OruPayload`). Date/gender/terminology conversion happens
downstream in FastAPI — Mirth passes raw HL7 field values through.

## Deploy

The stock `nextgenhealthcare/connect` image does **not** auto-load channels from the
mounted `channels/` directory (channels live in Mirth's internal DB).

**Recommended (one command):**

```bash
./scripts/up.sh                       # starts services + deploys channel
```

**Manual (two steps):**

```bash
docker compose up -d --build
./scripts/import_channels.sh          # imports + deploys via the Mirth REST API
```

**Admin UI:** Mirth Administrator → Channels → Import Channel →
select `channels/Maternity_Inbound.xml` → Deploy.

## Verify (end-to-end smoke test)

```bash
python scripts/mllp_send.py samples/adt_a01_normal_delivery.hl7    # expect MSA|AA ACK
python scripts/mllp_send.py samples/orm_o01_antenatal_28w.hl7
python scripts/mllp_send.py samples/oru_r01_vitals.hl7
curl "http://localhost:8080/fhir/Patient?identifier=http://hospital.local/mrn|1234567"
```

The source connector ACKs after **destinations complete** (`Auto-generate (Destinations completed)`),
so the ACK code reflects the real processing outcome:

| Scenario | HTTP Status | ACK Code | Meaning |
|---|---|---|---|
| Valid message, FastAPI accepts | 2xx | `MSA\|AA` | Accepted |
| Well-formed but invalid (e.g. missing MRN) | 422 | `MSA\|AE` | Error — investigate / fix payload |
| FastAPI/HAPI down or internal error | 5xx | `MSA\|AE` | Error — retry later |

```bash
# Test error path:
python scripts/mllp_send.py samples/invalid/adt_missing_mrn.hl7   # MSA|AE + deadletter/ file
```

### Escape sequence handling

```bash
python scripts/mllp_send.py samples/adt_a01_escaped_name.hl7    # expect MSA|AA
curl -s "http://localhost:8080/fhir/Patient?identifier=http://hospital.local/mrn|9876543" | python3 -m json.tool
# Verify: family name = "O&MALLEY", address line = "45 SMITH & JONES ST"
```

The HL7 sample contains `\T\` escape sequences (subcomponent separator = `&`). Mirth's parser
decodes these natively; the contract test mirrors this with `_decode_hl7_escapes()`.

(Mirth's response transformer scope only exposes `SENT`, `QUEUED`, `ERROR` status constants —
both 4xx and 5xx map to `ERROR` → `AE`. The `responseStatusMessage` field distinguishes
"rejected" from "error". `MSA|AR` is reserved for HL7 parsing failures before the message
reaches the destination.)

## Contract test (no Mirth required)

`tests/unit/test_mirth_channel_contract.py` parses the sample HL7 by the same canonical field
positions this channel uses and asserts the resulting JSON validates against the real FastAPI
payload models. It locks the JSON *contract* the transformer must satisfy. Note it uses a
plain-string HL7 parser, so it does **not** exercise Mirth's E4X runtime — the live smoke test
above is what verifies the actual channel behaviour.

## How the channel XML is generated

`channels/Maternity_Inbound.xml` is not hand-written. Hand-authoring a Mirth 4.5 channel export
is fragile — one wrong property class (e.g. `MLLPModeProperties` instead of the correct
`FrameModeProperties`) makes Mirth silently import the channel as *invalid* with its connectors
stripped, no error logged. Instead, `tools/GenerateChannel.java` builds the channel from Mirth's
own model classes (whose no-arg constructors yield the correct defaults) and serializes it with
`ObjectXMLSerializer`, so the output always matches the exact schema the running Mirth expects.
The JavaScript transformer body is read from `code_templates/maternity_transformers.js`, keeping
a single source of truth. Build/run instructions are in the file header.

## Verification status — VERIFIED end-to-end

Confirmed against a live stack (`nextgenhealthcare/connect:4.5.2`, HAPI v7.0.3):

- Channel imports + deploys to **STARTED**; MLLP listener live on 6661.
- `ADT^A01` → `MSA|AA` → Patient (`gender=female`, `birthDate=1992-03-15`, MRN + IHI) + Condition (O80, ICD-10-AM) persisted in HAPI.
- `ORM^O01` → Encounter (`class=AMB`, visit `VN00012`, admit `…+10:00`) persisted.
- `ORU^R01` → 3 Observations incl. the **BP panel merge** (85354-9 with systolic 118 + diastolic 76) under the AU BP profile.
- Re-sending `ADT^A01` does **not** duplicate the Patient (idempotent conditional update).
- `invalid/adt_missing_mrn.hl7` → FastAPI 422 → `MSA|AE` + dead-letter file written with correlation ID.
- FastAPI down (stopped) → `MSA|AE` (HTTP Sender timeout triggers ERROR status).
