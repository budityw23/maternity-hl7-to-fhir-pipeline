from pydantic import BaseModel


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
