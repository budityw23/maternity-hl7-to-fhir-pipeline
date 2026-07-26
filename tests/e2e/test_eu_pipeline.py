"""E2E tests — EU mode: HTTP POST → FastAPI → HAPI FHIR.

Requires a live Docker stack started with:
    PROFILE_REGION=eu PROFILE_COUNTRY=uk ./scripts/up.sh

Skipped automatically when the stack is in AU mode.
"""

import time

import httpx
import pytest

pytestmark = pytest.mark.e2e

EU_PATIENT_PROFILE = "http://hl7.eu/fhir/base/StructureDefinition/patient-eu"
ICD10_WHO_SYSTEM = "http://hl7.org/fhir/sid/icd-10"
NHS_NUMBER_SYSTEM = "http://fhir.nhs.uk/Id/nhs-number"
IPS_BUNDLE_PROFILE = "http://hl7.org/fhir/uv/ips/StructureDefinition/Bundle-uv-ips"
MRN_SYSTEM = "http://hospital.local/mrn"


def _is_eu_mode(fastapi_http: httpx.Client) -> bool:
    """Check if the stack is running in EU mode by sending a test request."""
    try:
        r = fastapi_http.post(
            "/fhir/Patient",
            json={
                "correlationId": "eu-probe",
                "messageType": "ADT^A01",
                "mrn": "EU-PROBE-000",
                "name": {"family": "PROBE", "given": "EU"},
                "birthDate": "20000101",
                "gender": "F",
                "address": {"line": "1 TEST ST", "city": "LONDON", "postalCode": "SW1A 1AA", "country": "GB"},
                "diagnoses": [],
            },
            headers={"X-Correlation-ID": "eu-probe"},
        )
        if r.status_code != 200:
            return False
        hapi = httpx.Client(base_url="http://localhost:8080/fhir", timeout=10)
        try:
            time.sleep(1)
            bundle = hapi.get(f"/Patient?identifier={MRN_SYSTEM}|EU-PROBE-000").json()
            if not bundle.get("entry"):
                return False
            patient = bundle["entry"][0]["resource"]
            profiles = patient.get("meta", {}).get("profile", [])
            return EU_PATIENT_PROFILE in profiles
        finally:
            hapi.close()
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def _require_eu_mode(fastapi_http: httpx.Client) -> None:
    if not _is_eu_mode(fastapi_http):
        pytest.skip("Stack is not in EU mode (PROFILE_REGION != eu)")


def _wait_for_resource(hapi: httpx.Client, path: str, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = hapi.get(path)
        bundle = r.json()
        if bundle.get("total", 0) > 0 or bundle.get("entry"):
            return bundle
        time.sleep(0.5)
    raise AssertionError(f"No entries found at {path} within {timeout}s")


EU_ADT_PAYLOAD = {
    "correlationId": "e2e-eu-001",
    "messageType": "ADT^A01",
    "mrn": "MRN-E2E-EU",
    "ihi": "9434765919",
    "name": {"family": "SMITH", "given": "EMMA", "middle": "JANE", "prefix": "MRS"},
    "birthDate": "19900210",
    "gender": "F",
    "address": {"line": "42 BAKER ST", "city": "LONDON", "postalCode": "NW1 6XE", "country": "GB"},
    "phone": "+447911123456",
    "diagnoses": [
        {"code": "O80", "display": "Encounter for full-term uncomplicated delivery", "codeSystem": "I10", "recordedDate": "20260527093000"},
    ],
}


class TestEuPatient:
    def test_eu_patient_created(self, fastapi_http: httpx.Client, hapi: httpx.Client) -> None:
        r = fastapi_http.post(
            "/fhir/Patient",
            json=EU_ADT_PAYLOAD,
            headers={"X-Correlation-ID": "e2e-eu-001"},
        )
        assert r.status_code == 200
        bundle = _wait_for_resource(hapi, f"/Patient?identifier={MRN_SYSTEM}|MRN-E2E-EU")
        patient = bundle["entry"][0]["resource"]
        profiles = patient.get("meta", {}).get("profile", [])
        assert EU_PATIENT_PROFILE in profiles

    def test_eu_national_id(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, f"/Patient?identifier={MRN_SYSTEM}|MRN-E2E-EU")
        patient = bundle["entry"][0]["resource"]
        identifiers = patient.get("identifier", [])
        nhs = [i for i in identifiers if i.get("system") == NHS_NUMBER_SYSTEM]
        assert len(nhs) >= 1, f"Expected NHS Number identifier, got systems: {[i.get('system') for i in identifiers]}"

    def test_eu_condition_icd10_who(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, "/Condition")
        conditions = [e["resource"] for e in bundle.get("entry", [])]
        o80 = [
            c for c in conditions
            if any(coding.get("code") == "O80" for coding in c.get("code", {}).get("coding", []))
        ]
        assert len(o80) >= 1
        system = o80[0]["code"]["coding"][0]["system"]
        assert system == ICD10_WHO_SYSTEM, f"Expected ICD-10 WHO system, got {system}"


class TestEuIps:
    def test_ips_bundle(self, fastapi_http: httpx.Client) -> None:
        r = fastapi_http.post(
            "/fhir/IPS",
            json={"correlationId": "e2e-eu-ips", "mrn": "MRN-E2E-EU"},
            headers={"X-Correlation-ID": "e2e-eu-ips"},
        )
        assert r.status_code == 200
        bundle = r.json()
        assert bundle["resourceType"] == "Bundle"
        profiles = bundle.get("meta", {}).get("profile", [])
        assert IPS_BUNDLE_PROFILE in profiles


class TestEuConsent:
    def test_gdpr_consent(self, fastapi_http: httpx.Client, hapi: httpx.Client) -> None:
        r = fastapi_http.post(
            "/fhir/Consent",
            json={
                "correlationId": "e2e-eu-consent",
                "mrn": "MRN-E2E-EU",
                "policyRule": "gdpr-art-6-1-a",
                "provisionType": "permit",
                "periodStart": "20260101",
                "periodEnd": "20271231",
            },
            headers={"X-Correlation-ID": "e2e-eu-consent"},
        )
        assert r.status_code == 200
        bundle = _wait_for_resource(hapi, "/Consent")
        consents = [e["resource"] for e in bundle.get("entry", [])]
        assert len(consents) >= 1
        assert consents[0]["resourceType"] == "Consent"
