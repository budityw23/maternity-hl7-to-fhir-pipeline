#!/usr/bin/env bash
set -euo pipefail

# Demo script for Maternity HL7-to-FHIR Pipeline
# Usage: ./scripts/demo.sh
# Recording: asciinema rec demo.cast -c "./scripts/demo.sh"

API="http://localhost:8000"
HAPI="http://localhost:8080/fhir"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

pause() {
  echo ""
  read -r -p "Press Enter to continue..."
  echo ""
}

echo -e "${BLUE}+------------------------------------------------------+${NC}"
echo -e "${BLUE}|  Maternity HL7-to-FHIR Pipeline - Live Demo          |${NC}"
echo -e "${BLUE}|  SYNTHETIC DATA ONLY - Not for clinical use          |${NC}"
echo -e "${BLUE}+------------------------------------------------------+${NC}"
echo ""

echo -e "${YELLOW}[0/5] Health Check${NC}"
echo "curl $API/health"
curl -s "$API/health" | python3 -m json.tool
pause

echo -e "${YELLOW}[1/5] Admitting Patient - ADT^A01 -> Patient + Condition${NC}"
echo "Message: samples/adt_a01_normal_delivery.hl7"
echo ""
curl -s -X POST "$API/fhir/Patient" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-001" \
  -d '{
    "correlationId": "demo-001",
    "messageType": "ADT^A01",
    "mrn": "1234567",
    "ihi": "8003608166690503",
    "name": {"family": "TEST", "given": "PATIENT", "middle": "MARY", "prefix": "MS"},
    "birthDate": "19920315",
    "gender": "F",
    "address": {"line": "14 SAMPLE ST", "city": "SYDNEY", "state": "NSW", "postalCode": "2000", "country": "AU"},
    "phone": "0412345678",
    "diagnoses": [{"code": "O80", "display": "Encounter for full-term uncomplicated delivery", "recordedDate": "20260527093000"}]
  }' | python3 -m json.tool
echo ""
echo -e "${GREEN}Patient + Condition created in HAPI FHIR${NC}"
pause

echo -e "${YELLOW}[2/5] Placing Order - ORM^O01 -> Encounter${NC}"
echo "Message: samples/orm_o01_antenatal_28w.hl7"
echo ""
curl -s -X POST "$API/fhir/Encounter" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-002" \
  -d '{
    "correlationId": "demo-002",
    "messageType": "ORM^O01",
    "mrn": "1234567",
    "visitNumber": "VN00001",
    "patientClass": "I",
    "admitDatetime": "20260527093000",
    "location": {"ward": "MAT_WARD", "room": "301", "facility": "RPA"},
    "attendingDoctor": {"id": "DR_SMITH", "familyName": "SMITH", "givenName": "SARAH"},
    "orderControl": "NW",
    "serviceCode": "424525001",
    "serviceDisplay": "Antenatal care"
  }' | python3 -m json.tool
echo ""
echo -e "${GREEN}Encounter created in HAPI FHIR${NC}"
pause

echo -e "${YELLOW}[3/5] Sending Observations - ORU^R01 -> Observations with BP panel merge${NC}"
echo "Message: samples/oru_r01_vitals.hl7"
echo "BP panel: systolic 8480-6 + diastolic 8462-4 -> merged panel 85354-9"
echo ""
curl -s -X POST "$API/fhir/Observation/bundle" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-003" \
  -d '{
    "correlationId": "demo-003",
    "messageType": "ORU^R01",
    "mrn": "1234567",
    "visitNumber": "VN00001",
    "observations": [
      {"setId": 1, "code": "8480-6", "display": "Systolic BP", "value": 118, "unitCode": "mm[Hg]", "unitDisplay": "mmHg", "status": "F"},
      {"setId": 2, "code": "8462-4", "display": "Diastolic BP", "value": 76, "unitCode": "mm[Hg]", "unitDisplay": "mmHg", "status": "F"},
      {"setId": 3, "code": "29463-7", "display": "Body weight", "value": 68.5, "unitCode": "kg", "unitDisplay": "kg", "status": "F"},
      {"setId": 4, "code": "11616-0", "display": "Fetal Heart Rate", "value": 145, "unitCode": "/min", "unitDisplay": "beats/min", "status": "F"}
    ]
  }' | python3 -m json.tool
echo ""
echo -e "${GREEN}3 Observations created: 1 BP panel + 2 individual observations${NC}"
pause

echo -e "${YELLOW}[4/5] Generating International Patient Summary (IPS)${NC}"
echo "Composing IPS document bundle from persisted resources"
echo ""
curl -s -X POST "$API/fhir/IPS" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-ips-001" \
  -d '{
    "correlationId": "demo-ips-001",
    "mrn": "1234567"
  }' | python3 -m json.tool
echo ""
echo -e "${GREEN}IPS document bundle generated${NC}"
pause

echo -e "${YELLOW}[5/5] Verifying Resources in HAPI FHIR${NC}"
echo ""

echo -e "${BLUE}Patient:${NC}"
curl -s "$HAPI/Patient?identifier=http://hospital.local/mrn|1234567" | python3 -c '
import json
import sys

bundle = json.load(sys.stdin)
for entry in bundle.get("entry", []):
    resource = entry["resource"]
    name = resource.get("name", [{}])[0]
    given = name.get("given", ["?"])
    print(
        "  ID: {}  Name: {}, {}  Gender: {}".format(
            resource.get("id", "?"),
            name.get("family", "?"),
            given[0],
            resource.get("gender", "?"),
        )
    )
'

echo -e "${BLUE}Conditions:${NC}"
curl -s "$HAPI/Condition" | python3 -c '
import json
import sys

bundle = json.load(sys.stdin)
for entry in bundle.get("entry", []):
    resource = entry["resource"]
    code = resource.get("code", {}).get("coding", [{}])[0]
    print(
        "  ID: {}  Code: {} - {}".format(
            resource.get("id", "?"),
            code.get("code", "?"),
            code.get("display", "?"),
        )
    )
'

echo -e "${BLUE}Encounters:${NC}"
curl -s "$HAPI/Encounter" | python3 -c '
import json
import sys

bundle = json.load(sys.stdin)
for entry in bundle.get("entry", []):
    resource = entry["resource"]
    print(
        "  ID: {}  Status: {}  Class: {}".format(
            resource.get("id", "?"),
            resource.get("status", "?"),
            resource.get("class", {}).get("code", "?"),
        )
    )
'

echo -e "${BLUE}Observations:${NC}"
curl -s "$HAPI/Observation" | python3 -c '
import json
import sys

bundle = json.load(sys.stdin)
for entry in bundle.get("entry", []):
    resource = entry["resource"]
    code = resource.get("code", {}).get("coding", [{}])[0]
    value = resource.get("valueQuantity", {})
    components = resource.get("component", [])
    if components:
        parts = ", ".join(
            "{}: {}".format(
                component["code"]["coding"][0]["display"],
                component["valueQuantity"]["value"],
            )
            for component in components
        )
        print(
            "  ID: {}  {} (panel: {})".format(
                resource.get("id", "?"),
                code.get("display", "?"),
                parts,
            )
        )
    elif value:
        print(
            "  ID: {}  {}: {} {}".format(
                resource.get("id", "?"),
                code.get("display", "?"),
                value.get("value", "?"),
                value.get("unit", ""),
            )
        )
    else:
        print("  ID: {}  {}".format(resource.get("id", "?"), code.get("display", "?")))
'

echo ""
echo -e "${GREEN}+------------------------------------------------------+${NC}"
echo -e "${GREEN}|  Demo complete - all FHIR resources persisted        |${NC}"
echo -e "${GREEN}+------------------------------------------------------+${NC}"
