from app.transformers.consent import build_consent


class TestBuildConsent:
    def test_resource_type(self):
        consent = build_consent("Patient/1", "gdpr-art-6-1-a", "permit")
        assert consent["resourceType"] == "Consent"

    def test_status_active(self):
        consent = build_consent("Patient/1", "gdpr-art-6-1-a", "permit")
        assert consent["status"] == "active"

    def test_scope_patient_privacy(self):
        consent = build_consent("Patient/1", "gdpr-art-6-1-a", "permit")
        assert consent["scope"]["coding"][0]["code"] == "patient-privacy"

    def test_category_consent_document(self):
        consent = build_consent("Patient/1", "gdpr-art-6-1-a", "permit")
        assert consent["category"][0]["coding"][0]["code"] == "59284-0"

    def test_patient_reference(self):
        consent = build_consent("Patient/42", "gdpr-art-6-1-a", "permit")
        assert consent["patient"]["reference"] == "Patient/42"

    def test_datetime_set(self):
        consent = build_consent("Patient/1", "gdpr-art-6-1-a", "permit")
        assert "dateTime" in consent
        assert len(consent["dateTime"]) == 10

    def test_policy_rule_explicit_consent(self):
        consent = build_consent("Patient/1", "gdpr-art-6-1-a", "permit")
        assert consent["policyRule"]["coding"][0]["code"] == "gdpr-art-6-1-a"

    def test_policy_rule_health_data(self):
        consent = build_consent("Patient/1", "gdpr-art-9-2-h", "permit")
        assert consent["policyRule"]["coding"][0]["code"] == "gdpr-art-9-2-h"

    def test_provision_type_permit(self):
        consent = build_consent("Patient/1", "gdpr-art-6-1-a", "permit")
        assert consent["provision"]["type"] == "permit"

    def test_provision_type_deny(self):
        consent = build_consent("Patient/1", "gdpr-art-6-1-a", "deny")
        assert consent["provision"]["type"] == "deny"

    def test_provision_period(self):
        consent = build_consent(
            "Patient/1",
            "gdpr-art-6-1-a",
            "permit",
            period_start="20260101",
            period_end="20271231",
        )
        assert consent["provision"]["period"]["start"] == "2026-01-01"
        assert consent["provision"]["period"]["end"] == "2027-12-31"

    def test_no_period_when_empty(self):
        consent = build_consent("Patient/1", "gdpr-art-6-1-a", "permit")
        assert "period" not in consent["provision"]

    def test_unknown_policy_uses_raw_code(self):
        consent = build_consent("Patient/1", "custom-policy", "permit")
        assert consent["policyRule"]["coding"][0]["code"] == "custom-policy"
        assert consent["policyRule"]["coding"][0]["display"] == "custom-policy"
