from pydantic import BaseModel, Field


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
