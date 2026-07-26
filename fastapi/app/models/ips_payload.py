from pydantic import BaseModel


class IpsPayload(BaseModel):
    correlationId: str  # noqa: N815
    mrn: str
    dateFrom: str = ""  # noqa: N815
    dateTo: str = ""  # noqa: N815
