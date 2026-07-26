"""E2E tests — AU mode: MLLP → Mirth → FastAPI → HAPI FHIR.

Requires a live Docker stack started with ./scripts/up.sh (AU mode, the default).
These tests send real HL7 v2.5 messages via MLLP and verify resources persisted in HAPI.
"""

import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.e2e

MRN_SYSTEM = "http://hospital.local/mrn"
AU_PATIENT_PROFILE = "http://hl7.org.au/fhir/StructureDefinition/au-patient"
AU_CONDITION_PROFILE = "http://hl7.org.au/fhir/StructureDefinition/au-condition"
AU_BP_PROFILE = "http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure"
ICD10AM_SYSTEM = "http://hl7.org.au/fhir/CodeSystem/icd-10-am"


def _wait_for_resource(hapi: httpx.Client, path: str, timeout: float = 10) -> dict:
    """Poll HAPI until at least one entry appears in the search bundle."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = hapi.get(path)
        bundle = r.json()
        if bundle.get("total", 0) > 0 or bundle.get("entry"):
            return bundle
        time.sleep(0.5)
    raise AssertionError(f"No entries found at {path} within {timeout}s")


class TestHealthCheck:
    def test_fastapi_healthy(self, fastapi_http: httpx.Client) -> None:
        r = fastapi_http.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["hapi"] == "up"


class TestAdtPatientAdmission:
    """Send ADT^A01 via MLLP → verify Patient + Condition in HAPI."""

    def test_adt_returns_aa_ack(self, mllp, samples_dir: Path) -> None:
        ack = mllp(str(samples_dir / "adt_a01_normal_delivery.hl7"))
        assert "MSA|AA" in ack

    def test_patient_created_in_hapi(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, f"/Patient?identifier={MRN_SYSTEM}|1234567")
        patient = bundle["entry"][0]["resource"]
        assert patient["resourceType"] == "Patient"
        assert patient["gender"] == "female"
        assert patient["birthDate"] == "1992-03-15"
        names = patient.get("name", [])
        assert any(n.get("family") == "TEST" for n in names)

    def test_patient_has_au_profile(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, f"/Patient?identifier={MRN_SYSTEM}|1234567")
        patient = bundle["entry"][0]["resource"]
        profiles = patient.get("meta", {}).get("profile", [])
        assert AU_PATIENT_PROFILE in profiles

    def test_condition_created_in_hapi(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, "/Condition")
        conditions = [e["resource"] for e in bundle.get("entry", [])]
        o80_conditions = [
            c for c in conditions
            if any(
                coding.get("code") == "O80"
                for coding in c.get("code", {}).get("coding", [])
            )
        ]
        assert len(o80_conditions) >= 1
        coding = o80_conditions[0]["code"]["coding"][0]
        assert coding["system"] == ICD10AM_SYSTEM


class TestOrmEncounter:
    """Send ORM^O01 via MLLP → verify Encounter in HAPI."""

    def test_orm_returns_aa_ack(self, mllp, samples_dir: Path) -> None:
        ack = mllp(str(samples_dir / "orm_o01_antenatal_28w.hl7"))
        assert "MSA|AA" in ack

    def test_encounter_created_in_hapi(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, "/Encounter")
        encounters = [e["resource"] for e in bundle.get("entry", [])]
        assert len(encounters) >= 1
        enc = encounters[0]
        assert enc["resourceType"] == "Encounter"
        assert enc["status"] in ("in-progress", "finished", "arrived", "planned")


class TestOruObservations:
    """Send ORU^R01 via MLLP → verify Observations + BP panel merge in HAPI."""

    def test_oru_returns_aa_ack(self, mllp, samples_dir: Path) -> None:
        ack = mllp(str(samples_dir / "oru_r01_vitals.hl7"))
        assert "MSA|AA" in ack

    def test_observations_created_in_hapi(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, "/Observation")
        observations = [e["resource"] for e in bundle.get("entry", [])]
        assert len(observations) >= 3

    def test_bp_panel_merged(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, "/Observation?code=85354-9")
        bp_obs = bundle["entry"][0]["resource"]
        assert bp_obs["resourceType"] == "Observation"
        components = bp_obs.get("component", [])
        assert len(components) == 2
        codes = {c["code"]["coding"][0]["code"] for c in components}
        assert "8480-6" in codes
        assert "8462-4" in codes
        values = {
            c["code"]["coding"][0]["code"]: c["valueQuantity"]["value"]
            for c in components
        }
        assert values["8480-6"] == 118
        assert values["8462-4"] == 76

    def test_bp_panel_has_au_profile(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, "/Observation?code=85354-9")
        bp_obs = bundle["entry"][0]["resource"]
        profiles = bp_obs.get("meta", {}).get("profile", [])
        assert AU_BP_PROFILE in profiles


class TestIdempotency:
    """Re-sending the same ADT^A01 must NOT create a duplicate Patient."""

    def test_no_duplicate_patient(self, mllp, hapi: httpx.Client, samples_dir: Path) -> None:
        mllp(str(samples_dir / "adt_a01_normal_delivery.hl7"))
        time.sleep(2)
        bundle = hapi.get(f"/Patient?identifier={MRN_SYSTEM}|1234567").json()
        assert bundle.get("total", len(bundle.get("entry", []))) == 1


class TestEscapedName:
    """HL7 escape sequences decoded correctly in HAPI."""

    def test_escaped_adt_returns_aa(self, mllp, samples_dir: Path) -> None:
        ack = mllp(str(samples_dir / "adt_a01_escaped_name.hl7"))
        assert "MSA|AA" in ack

    def test_escaped_name_in_hapi(self, hapi: httpx.Client) -> None:
        bundle = _wait_for_resource(hapi, f"/Patient?identifier={MRN_SYSTEM}|9876543")
        patient = bundle["entry"][0]["resource"]
        family = patient["name"][0]["family"]
        assert family == "O&MALLEY"


class TestInvalidMessage:
    """Invalid HL7 → MSA|AE + dead-letter file."""

    def test_invalid_returns_ae_ack(self, mllp, samples_dir: Path) -> None:
        ack = mllp(str(samples_dir / "invalid" / "adt_missing_mrn.hl7"))
        assert "MSA|AE" in ack

    def test_deadletter_file_created(self, deadletter_dir: Path) -> None:
        dl_files = list(deadletter_dir.glob("*.json"))
        assert len(dl_files) >= 1, "Expected at least one dead-letter file"
