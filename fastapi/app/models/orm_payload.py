# ruff: noqa: N815
from pydantic import BaseModel, field_validator


class ParticipantPayload(BaseModel):
    id: str
    familyName: str
    givenName: str


class LocationPayload(BaseModel):
    ward: str
    room: str = ""
    facility: str = ""


class OrmPayload(BaseModel):
    correlationId: str
    messageType: str = "ORM^O01"
    mrn: str
    visitNumber: str
    patientClass: str
    admitDatetime: str
    dischargeDatetime: str = ""
    location: LocationPayload
    attendingDoctor: ParticipantPayload
    orderControl: str = "NW"
    serviceCode: str = ""
    serviceDisplay: str = ""

    @field_validator("mrn")
    @classmethod
    def mrn_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("MRN is required and must not be empty")
        return value.strip()

    @field_validator("visitNumber")
    @classmethod
    def visit_number_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Visit number is required and must not be empty")
        return value.strip()
