# ruff: noqa: N815
from pydantic import BaseModel, Field, field_validator


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

    @field_validator("code")
    @classmethod
    def code_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Observation code (LOINC) is required")
        return value.strip()

    @field_validator("value")
    @classmethod
    def value_must_be_valid(cls, value: float | str) -> float | str:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Observation value must not be empty")
        return value


class OruPayload(BaseModel):
    correlationId: str
    messageType: str = "ORU^R01"
    mrn: str
    visitNumber: str = ""
    orderCode: str = ""
    orderDisplay: str = ""
    observations: list[ObservationPayload] = Field(default_factory=list)

    @field_validator("mrn")
    @classmethod
    def mrn_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("MRN is required and must not be empty")
        return value.strip()
