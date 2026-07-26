import logging
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

CONSENT_SCOPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/consentscope"
CONSENT_CATEGORY_SYSTEM = "http://loinc.org"
CONSENT_CATEGORY_CODE = "59284-0"
CONSENT_CATEGORY_DISPLAY = "Consent Document"

GDPR_POLICY_RULES: dict[str, str] = {
    "gdpr-art-6-1-a": "GDPR Article 6(1)(a) - Explicit consent",
    "gdpr-art-9-2-h": "GDPR Article 9(2)(h) - Health data processing",
    "gdpr-art-6-1-e": "GDPR Article 6(1)(e) - Public interest",
}


def _hl7_date_to_iso(hl7_date: str) -> str:
    """Convert HL7 date YYYYMMDD to ISO YYYY-MM-DD."""
    cleaned = re.sub(r"[^0-9]", "", hl7_date)[:8]
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
    return hl7_date


def build_consent(
    patient_reference: str,
    policy_rule: str,
    provision_type: str,
    period_start: str = "",
    period_end: str = "",
) -> dict[str, Any]:
    """Build a FHIR Consent resource for GDPR legal basis."""
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    policy_display = GDPR_POLICY_RULES.get(policy_rule, policy_rule)

    consent: dict[str, Any] = {
        "resourceType": "Consent",
        "status": "active",
        "scope": {
            "coding": [
                {
                    "system": CONSENT_SCOPE_SYSTEM,
                    "code": "patient-privacy",
                    "display": "Privacy Consent",
                }
            ]
        },
        "category": [
            {
                "coding": [
                    {
                        "system": CONSENT_CATEGORY_SYSTEM,
                        "code": CONSENT_CATEGORY_CODE,
                        "display": CONSENT_CATEGORY_DISPLAY,
                    }
                ]
            }
        ],
        "patient": {"reference": patient_reference},
        "dateTime": now,
        "policyRule": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": policy_rule,
                    "display": policy_display,
                }
            ]
        },
        "provision": {
            "type": provision_type,
        },
    }

    if period_start or period_end:
        period: dict[str, str] = {}
        if period_start:
            period["start"] = _hl7_date_to_iso(period_start)
        if period_end:
            period["end"] = _hl7_date_to_iso(period_end)
        consent["provision"]["period"] = period

    logger.info(
        "Consent built for %s policy=%s type=%s",
        patient_reference,
        policy_rule,
        provision_type,
    )

    return consent
