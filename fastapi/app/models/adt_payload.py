# ruff: noqa: N815
from pydantic import BaseModel, Field, field_validator


class NamePayload(BaseModel):
    family: str
    given: str
    middle: str = ""
    prefix: str = ""


class AddressPayload(BaseModel):
    line: str
    city: str
    state: str
    postalCode: str
    country: str = "AU"


class DiagnosisPayload(BaseModel):
    code: str
    display: str
    codeSystem: str = ""
    recordedDate: str = ""


class AdtPayload(BaseModel):
    correlationId: str
    messageType: str = "ADT^A01"
    mrn: str
    ihi: str = ""
    name: NamePayload
    birthDate: str
    gender: str
    address: AddressPayload
    phone: str = ""
    diagnoses: list[DiagnosisPayload] = Field(default_factory=list)

    @field_validator("mrn")
    @classmethod
    def mrn_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("MRN is required and must not be empty")
        return value.strip()

    @field_validator("gender")
    @classmethod
    def gender_must_be_valid(cls, value: str) -> str:
        valid = {"F", "M", "O", "U", "A", "N", ""}
        if value.upper() not in valid:
            raise ValueError(
                f"Invalid gender code '{value}'. Must be one of: F, M, O, U, A, N"
            )
        return value
