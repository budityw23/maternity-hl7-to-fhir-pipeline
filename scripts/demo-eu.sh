#!/usr/bin/env bash
set -euo pipefail

# EU Demo Script — sends EU-contextualized HL7 data through the pipeline
# Requires: docker compose up with PROFILE_REGION=eu PROFILE_COUNTRY=uk

BASE_URL="${FASTAPI_URL:-http://localhost:8000}"

echo "=== EU Maternity HL7-to-FHIR Demo ==="
echo "Target: $BASE_URL"
echo ""

echo "--- Step 1: Health check ---"
curl -s "$BASE_URL/health" | python3 -m json.tool
echo ""

echo "--- Step 2: Send EU ADT^A01 (Patient + Conditions) ---"
curl -s -X POST "$BASE_URL/fhir/Patient" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: eu-demo-001" \
  -d '{
    "correlationId": "eu-demo-001",
    "messageType": "ADT^A01",
    "mrn": "MRN-EU-001",
    "ihi": "9434765919",
    "name": {"family": "SMITH", "given": "EMMA", "middle": "JANE", "prefix": "MRS"},
    "birthDate": "19900210",
    "gender": "F",
    "address": {"line": "42 BAKER STREET", "city": "LONDON", "state": "", "postalCode": "NW1 6XE", "country": "GB"},
    "phone": "+447911123456",
    "diagnoses": [
      {"code": "O80", "display": "Encounter for full-term uncomplicated delivery", "codeSystem": "I10", "recordedDate": "20260527093000"},
      {"code": "O48", "display": "Late pregnancy", "codeSystem": "I10", "recordedDate": "20260527093000"}
    ]
  }' | python3 -m json.tool
echo ""

echo "--- Step 3: Send EU ORM^O01 (Encounter) ---"
curl -s -X POST "$BASE_URL/fhir/Encounter" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: eu-demo-002" \
  -d '{
    "correlationId": "eu-demo-002",
    "messageType": "ORM^O01",
    "mrn": "MRN-EU-001",
    "visitNumber": "VN-EU-001",
    "patientClass": "O",
    "admitDatetime": "20260420100000",
    "dischargeDatetime": "20260420110000",
    "location": {"ward": "MATERNITY_WARD", "room": "MW-01", "facility": "ST_THOMAS"},
    "attendingDoctor": {"id": "DR_JONES", "familyName": "JONES", "givenName": "SARAH"},
    "orderControl": "NW",
    "serviceCode": "424525001",
    "serviceDisplay": "Antenatal care"
  }' | python3 -m json.tool
echo ""

echo "--- Step 4: Send EU ORU^R01 (Observations with BP panel) ---"
curl -s -X POST "$BASE_URL/fhir/Observation/bundle" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: eu-demo-003" \
  -d '{
    "correlationId": "eu-demo-003",
    "mrn": "MRN-EU-001",
    "visitNumber": "VN-EU-001",
    "observations": [
      {"setId": 1, "valueType": "NM", "code": "8480-6", "display": "Systolic blood pressure", "codeSystem": "LN", "value": 118, "unitCode": "mm[Hg]", "unitDisplay": "mmHg", "referenceRange": "90-120", "abnormalFlag": "N", "status": "F", "observationDatetime": "20260420103000"},
      {"setId": 2, "valueType": "NM", "code": "8462-4", "display": "Diastolic blood pressure", "codeSystem": "LN", "value": 76, "unitCode": "mm[Hg]", "unitDisplay": "mmHg", "referenceRange": "60-80", "abnormalFlag": "N", "status": "F", "observationDatetime": "20260420103000"},
      {"setId": 3, "valueType": "NM", "code": "29463-7", "display": "Body weight", "codeSystem": "LN", "value": 72.0, "unitCode": "kg", "unitDisplay": "kilogram", "referenceRange": "50-100", "abnormalFlag": "N", "status": "F", "observationDatetime": "20260420103000"},
      {"setId": 4, "valueType": "NM", "code": "55283-6", "display": "Fetal heart rate", "codeSystem": "LN", "value": 142, "unitCode": "/min", "unitDisplay": "per minute", "referenceRange": "110-160", "abnormalFlag": "N", "status": "F", "observationDatetime": "20260420103000"}
    ]
  }' | python3 -m json.tool
echo ""

echo "--- Step 5: Verify Patient in HAPI FHIR ---"
curl -s "http://localhost:8080/fhir/Patient?identifier=http://hospital.local/mrn|MRN-EU-001" | python3 -m json.tool
echo ""

echo "--- Step 6: Generate International Patient Summary (IPS) ---"
curl -s -X POST "$BASE_URL/fhir/IPS" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: eu-demo-004" \
  -d '{
    "correlationId": "eu-demo-004",
    "mrn": "MRN-EU-001"
  }' | python3 -m json.tool
echo ""

echo "--- Step 7: Create GDPR Consent ---"
curl -s -X POST "$BASE_URL/fhir/Consent" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: eu-demo-005" \
  -d '{
    "correlationId": "eu-demo-005",
    "mrn": "MRN-EU-001",
    "policyRule": "gdpr-art-6-1-a",
    "provisionType": "permit",
    "periodStart": "20260101",
    "periodEnd": "20271231"
  }' | python3 -m json.tool
echo ""

echo "=== EU Demo Complete (7 steps) ==="
