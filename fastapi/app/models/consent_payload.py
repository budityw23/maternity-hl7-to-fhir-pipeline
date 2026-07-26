from pydantic import BaseModel


class ConsentPayload(BaseModel):
    correlationId: str  # noqa: N815
    mrn: str
    policyRule: str = "gdpr-art-6-1-a"  # noqa: N815
    provisionType: str = "permit"  # noqa: N815
    periodStart: str = ""  # noqa: N815
    periodEnd: str = ""  # noqa: N815
