# ruff: noqa: N815
from pydantic import BaseModel, Field


class ObservationPayload(BaseModel):
    setId: int
    valueType: str = "NM"
    code: str
    display: str
    codeSystem: str = "LN"
    value: float | str
    unitCode: str
    unitDisplay: str = ""
    referenceRange: str = ""
    abnormalFlag: str = ""
    status: str = "F"
    observationDatetime: str = ""


class OruPayload(BaseModel):
    correlationId: str
    messageType: str = "ORU^R01"
    mrn: str
    visitNumber: str = ""
    orderCode: str = ""
    orderDisplay: str = ""
    observations: list[ObservationPayload] = Field(default_factory=list)
